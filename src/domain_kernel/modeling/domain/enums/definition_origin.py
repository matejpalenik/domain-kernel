"""DefinitionOrigin choices for its owning domain."""

from enum import StrEnum, unique


@unique
class DefinitionOrigin(StrEnum):
    """Origin of a company model definition."""

    COMPANY = "company"
    REFERENCE_PACK_ADAPTATION = "reference_pack_adaptation"
    SCHEMA_IMPORT = "schema_import"
    LOCAL_EXTENSION = "local_extension"
    BASELINE = "baseline"
