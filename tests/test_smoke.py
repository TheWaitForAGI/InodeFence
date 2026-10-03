import sys

import inodefence


def test_inodefence_imports() -> None:
    assert inodefence is not None


def test_python_version() -> None:
    assert sys.version_info[:2] == (3, 12)
