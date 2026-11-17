"""Compatibility alias: this driver moved to ``inodefence.drivers.node_tar.registry_prepare``
(src/inodefence/drivers/node_tar/registry_prepare.py).

Kept because tools/node-tar/versions/README.md (not edited here) names this path. Importing
``scripts.node_tar_registry_prepare`` gives the real module (the same object, so a
``monkeypatch`` of ``scripts.node_tar_registry_prepare.<name>`` patches the code that runs);
``python scripts/node_tar_registry_prepare.py`` and ``python -m
scripts.node_tar_registry_prepare`` run its ``main``.
"""

import sys
from typing import TYPE_CHECKING

from inodefence.drivers.node_tar import registry_prepare as _module

if TYPE_CHECKING:  # the alias below is invisible to type checkers
    from inodefence.drivers.node_tar.registry_prepare import *  # noqa: F403


if __name__ == "__main__":
    raise SystemExit(_module.main())
sys.modules[__name__] = _module
