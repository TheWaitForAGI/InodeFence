"""The launch diagnostics: preflight / postflight checks and the launch-outcome classification.

The interface (what an observer sees and may return, and the rules that keep STRICT unchanged) is
:mod:`inodefence.drivers.runtime.hooks`. This module only lists the observers and the classifier;
the session (:mod:`inodefence.drivers.runtime.session`) looks both up here at launch time.

Empty for now: no observer, and the classifier names only success / failure from the exit code.
"""

from __future__ import annotations

from inodefence.drivers.runtime.hooks import LaunchObserver, LaunchOutcome

#: The observers run around every launch, in order.
OBSERVERS: tuple[LaunchObserver, ...] = ()


def classify(outcome: LaunchOutcome) -> str:
    """A short name for how a launch ended (recorded; never changes the exit code or verdict)."""
    if outcome.returncode is None:
        return "runner-error"
    return "completed" if outcome.returncode == 0 else "failed"
