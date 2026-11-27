"""Resolve stable wire names for SDK records."""

from typing import final

_RENAMED_RECORDS = {
    "ArtifactWriteRequest": "ArtifactWrite",
    "DependencyChangeIntent": "DependencyChangeRequest",
}


@final
class WireRecordName:
    """Resolve durable record names independently of Python type names."""

    @staticmethod
    def for_type(*, record: type[object]) -> str:
        """Return the serialized name of a record across Python type renames."""
        name = record.__name__
        return _RENAMED_RECORDS.get(name, name)
