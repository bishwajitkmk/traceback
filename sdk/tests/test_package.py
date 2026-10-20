import traceback

import traceback_sdk


def test_does_not_shadow_stdlib_traceback() -> None:
    assert hasattr(traceback, "format_exception")
    assert traceback_sdk.__version__ == "0.1.0"
