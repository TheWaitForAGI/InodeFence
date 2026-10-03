from collections.abc import Iterator

import pytest

from inodefence.runtime import RuntimeSandbox, disposable_sandbox


@pytest.fixture
def sandbox() -> Iterator[RuntimeSandbox]:
    with disposable_sandbox() as run:
        yield run
