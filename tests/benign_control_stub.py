"""A benign-input control that extracted, for tests that are about something else.

``verify`` runs one benign archive before a cell's fixtures (``TargetAdapter.benign``). Tests whose
fake run program answers every archive the same way would read that answer as the control's too;
they install this stub instead. The control itself is tested in ``test_verify_benign_control``.
"""

from __future__ import annotations

import pytest

import inodefence.drivers.run_target as rt


def extracted(cell: rt.RunCell) -> rt.BenignRun:
    return rt.benign_from_raw(
        rt.benign_archive(),
        {"declined": None, "extract_tree": {rt.BENIGN_NAME: {}}},
        rt.BENIGN_NAME,
    )


def install(monkeypatch: pytest.MonkeyPatch, *adapter_modules: object) -> None:
    """Make ``_benign`` of each adapter module report an extracted control."""
    for module in adapter_modules:
        monkeypatch.setattr(module, "_benign", extracted)
