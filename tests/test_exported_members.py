import httpcore
from httpcore import __all__ as exported_members


def test_all_imports_are_exported() -> None:
    assert exported_members == sorted(
        member for member in vars(httpcore).keys() if not member.startswith("_")
    )
