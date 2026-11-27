"""The LangGraph stage request exceeded its serialized size limit."""

from domain_kernel.discovery.application.errors.inference_error import InferenceError

__all__ = ["_StageFrameLimitError"]


class _StageFrameLimitError(InferenceError):
    """A stage exceeded the serialized request budget before dispatch."""
