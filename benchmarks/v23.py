"""Verify the private archived v23 benchmark bundle without calling a provider."""

from pathlib import Path
from runpy import run_path

_BUNDLE = (
    Path(__file__).resolve().parents[1] / "local/benchmarks/runs/full-source-discovery-comparison"
)


def main() -> None:
    """Run the verifier shipped with the retained evidence bundle."""
    verifier = _BUNDLE / "v23_replay.py"
    if not verifier.is_file():
        raise SystemExit(
            "The private v23 evidence bundle is missing. See docs/evidence/discovery-v23.md."
        )
    _ = run_path(str(verifier), run_name="__main__")


if __name__ == "__main__":
    main()
