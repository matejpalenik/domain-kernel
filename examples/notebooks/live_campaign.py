"""Budget actual discovery attempts across local smoke, integrated and release runs."""

from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path
from sqlite3 import connect
from typing import TYPE_CHECKING, final, override
from uuid import uuid4

from domain_kernel import InferenceError, ModelGateway
from domain_kernel.discovery.infrastructure.litellm_gateway import DEFAULT_MODEL, OPENAI_API_BASE

if TYPE_CHECKING:
    from sqlite3 import Connection

    from domain_kernel import LiteLLMGateway, ModelRequest, ModelResponse


MAX_INPUT_TOKENS = 1_000_000
MAX_OUTPUT_TOKENS = 100_000
_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LEDGER = _ROOT / "local/discovery-campaign.sqlite3"

_TABLE = """
CREATE TABLE IF NOT EXISTS attempt (
    id TEXT PRIMARY KEY, request_id TEXT NOT NULL, stage TEXT NOT NULL, status TEXT NOT NULL,
    input_tokens INTEGER NOT NULL, output_tokens INTEGER NOT NULL
)
"""


class CampaignBudgetError(InferenceError):
    """The shared live campaign cannot reserve another bounded call."""


@dataclass(frozen=True, kw_only=True)
class Usage:
    """Charged or conservatively reserved tokens across every attempt."""

    attempts: int
    input_tokens: int
    output_tokens: int


@final
class CampaignBudget:
    """Atomically reserve the provider envelope before each attempt."""

    def __init__(
        self,
        *,
        path: Path,
        max_input: int = MAX_INPUT_TOKENS,
        max_output: int = MAX_OUTPUT_TOKENS,
    ) -> None:
        """Select one durable budget shared by all campaign runners."""
        self._path = path
        self._max_input = max_input
        self._max_output = max_output

    def reserve(self, *, request_id: str, stage: str, input_tokens: int, output_tokens: int) -> str:
        """Count calls with unknown usage at their reserved maximum."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with closing(connect(database=self._path)) as ledger, ledger:
            _ = ledger.execute(_TABLE)
            _ = ledger.execute("BEGIN IMMEDIATE")
            used = self._usage(ledger=ledger)
            if (
                used.input_tokens + input_tokens > self._max_input
                or used.output_tokens + output_tokens > self._max_output
            ):
                raise CampaignBudgetError(
                    message="The shared Luna campaign token limit is reached."
                )
            identifier = uuid4().hex
            _ = ledger.execute(
                "INSERT INTO attempt VALUES (?, ?, ?, 'reserved', ?, ?)",
                (identifier, request_id, stage, input_tokens, output_tokens),
            )
        return identifier

    def settle(self, *, identifier: str, response: ModelResponse) -> None:
        """Record reported usage and keep reservations for any unreported counts."""
        with closing(connect(database=self._path)) as ledger, ledger:
            _ = ledger.execute(
                """UPDATE attempt SET status = 'completed',
                    input_tokens = COALESCE(?, input_tokens),
                    output_tokens = COALESCE(?, output_tokens)
                   WHERE id = ? AND status = 'reserved'""",
                (response.input_tokens, response.output_tokens, identifier),
            )

    def usage(self) -> Usage:
        """Read recorded and conservatively reserved campaign usage."""
        if not self._path.exists():
            return Usage(attempts=0, input_tokens=0, output_tokens=0)
        with closing(connect(database=self._path)) as ledger:
            return self._usage(ledger=ledger)

    @staticmethod
    def _usage(*, ledger: Connection) -> Usage:
        row: object = (
            ledger.execute(
                "SELECT COUNT(*), COALESCE(SUM(input_tokens), 0), "
                "COALESCE(SUM(output_tokens), 0) FROM attempt"
            ).fetchone()
            or None
        )
        match row:
            case int(attempts), int(input_tokens), int(output_tokens):
                return Usage(
                    attempts=attempts, input_tokens=input_tokens, output_tokens=output_tokens
                )
            case _:
                raise CampaignBudgetError(message="Inspect the saved campaign usage.")


@final
@dataclass(frozen=True, kw_only=True)
class CampaignGateway(ModelGateway):
    """Enforce the paid test budget around one explicitly configured gateway."""

    gateway: LiteLLMGateway = field(repr=False)
    budget: CampaignBudget
    stage: str

    def __post_init__(self) -> None:
        """Allow only the agreed low-cost official model in the paid test campaign."""
        if (self.gateway.model, self.gateway.api_base, self.gateway.reasoning_effort) != (
            DEFAULT_MODEL,
            OPENAI_API_BASE,
            "none",
        ):
            raise ValueError("Use the campaign's configured Luna model and reasoning effort.")

    @override
    async def generate(self, *, request: ModelRequest) -> ModelResponse:
        """Reserve exactly one attempt and settle from the returned provider usage."""
        identifier = self.budget.reserve(
            request_id=request.request_id,
            stage=self.stage,
            input_tokens=self.gateway.input_ceiling(request=request),
            output_tokens=self.gateway.max_output_tokens,
        )
        response = await self.gateway.generate(request=request)
        self.budget.settle(identifier=identifier, response=response)
        return response
