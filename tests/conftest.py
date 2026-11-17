from collections.abc import Iterator

import pytest

from inodefence.runtime import RuntimeSandbox, disposable_sandbox


@pytest.fixture
def sandbox() -> Iterator[RuntimeSandbox]:
    with disposable_sandbox() as run:
        yield run


@pytest.fixture(autouse=True)
def _no_real_docker_in_launch_diagnostics(monkeypatch) -> None:
    """The shipped launch diagnostics ask the host's Docker (read-only); tests never do.

    A test that exercises them sets ``diagnostics.OBSERVERS`` itself (with a faked runner).
    """
    from inodefence.drivers.runtime import diagnostics

    monkeypatch.setattr(diagnostics, "OBSERVERS", ())
