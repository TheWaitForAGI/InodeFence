"""Compatibility alias: this module moved to ``inodefence.drivers.python_tarfile.producer``
(src/inodefence/drivers/python_tarfile/producer.py).

Kept because the controller launcher ``scripts/local_python_tarfile_explore.sh`` and
``tools/python-tarfile/effect/Dockerfile`` (neither edited here) name this path in their messages.
Importing ``scripts.python_tarfile_producer`` gives the real module (the same object, so a
``monkeypatch`` of ``scripts.python_tarfile_producer.<name>`` patches the code that runs). The
module has no command line, as before the move.
"""

import sys
from typing import TYPE_CHECKING

from inodefence.drivers.python_tarfile import producer as _module

if TYPE_CHECKING:  # the alias below is invisible to type checkers
    from inodefence.drivers.python_tarfile.producer import *  # noqa: F403


sys.modules[__name__] = _module
