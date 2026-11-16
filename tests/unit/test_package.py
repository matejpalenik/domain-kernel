from importlib.metadata import metadata
from importlib.resources import files


def test_typed_package_marker_is_distributed() -> None:
    assert files("domain_kernel").joinpath("py.typed").is_file()


def test_package_declares_licensing_and_python_baseline() -> None:
    package_metadata = metadata("domain-kernel")
    assert package_metadata["License-Expression"] == "Apache-2.0"
    assert package_metadata["Requires-Python"] == ">=3.13"
