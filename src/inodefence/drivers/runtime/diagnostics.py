"""The launch diagnostics: preflight / postflight checks and the launch-outcome classification.

The interface (what an observer sees and may return, and the rules that keep STRICT unchanged) is
:mod:`inodefence.drivers.runtime.hooks`. This module only lists the observers and the classifier;
the session (:mod:`inodefence.drivers.runtime.session`) looks both up here at launch time.

One observer, :class:`HealthObserver`, read-only throughout (nothing is removed or restarted):

* **before** a launch: this run's controller / volume name already taken (or Docker cannot say)
  -> ``block``. The launcher stops on that today anyway (exit 1, after building images); the block
  only moves the same refusal first (a setup error, exit 3).
* **after** a launch: one ``<PREFIX> DIAGNOSIS:`` line on stderr when the launch did not end
  cleanly -- the stage it reached, the category (the shared abort classifier's, or
  ``daemon-unreachable`` / ``daemon-timeout``, else ``UNKNOWN``) and which evidence files exist --
  plus a ``warn`` when this run's controller / volume is still there or its state is unknown. The
  three launchers without owner labels do not report a failed cleanup in their exit code, so this
  name check is the only place it shows.

:func:`classify` names how a launch ended from its exit code. The diagnosis uses the exit code and
which files exist; the launcher's terminal output is not
captured, so a cause that shows only there stays ``UNKNOWN``. None of this changes an exit code, an
exception path or a verdict; an observer that raises is recorded by the session, not swallowed.
"""

from __future__ import annotations

import sys

from inodefence.drivers.runtime import health
from inodefence.drivers.runtime.diagnosis import Diagnosis, Stage, run_diagnosis
from inodefence.drivers.runtime.hooks import (
    Finding,
    LaunchObserver,
    LaunchOutcome,
    LaunchRequest,
)


def _diagnose(outcome: LaunchOutcome, daemon: health.DaemonStatus | None) -> Diagnosis | None:
    artifacts = outcome.request.artifacts
    report = artifacts.report
    if outcome.returncode is None:
        present = tuple(path for path in artifacts.evidence() if path.exists())
        loop_started = report is not None and report.exists()
        category = "UNKNOWN"
        if daemon is not None and daemon.state is not health.DaemonState.OK:
            category = f"daemon-{daemon.state.value}"
        return Diagnosis(
            Stage.LOOP if loop_started else Stage.CONTROLLER_SETUP,
            category,
            f"the launcher did not return an exit code ({outcome.error or 'interrupted'})",
            present,
            outcome.result_written,
        )
    if report is None:
        if outcome.returncode == 0:
            return None
        return Diagnosis(
            Stage.CONTROLLER_SETUP,
            "UNKNOWN",
            f"the launcher exited {outcome.returncode}; this target names no loop report",
            (),
            outcome.result_written,
        )
    return run_diagnosis(
        outcome.returncode,
        report,
        evidence=artifacts.evidence()[1:],
        result_written=outcome.result_written,
        daemon_after=daemon,
    )


class HealthObserver:
    """Read-only checks around one launch (see the module docstring)."""

    def before(self, request: LaunchRequest) -> list[Finding]:
        if not request.controller or not request.volume:
            return []
        reason = health.run_resources_exist(request.controller, request.volume)
        return [] if reason is None else [Finding("block", "run-resources-exist", reason)]

    def after(self, outcome: LaunchOutcome) -> list[Finding]:
        findings: list[Finding] = []
        failed = outcome.returncode != 0
        daemon = health.probe_daemon() if failed else None
        diagnosis = _diagnose(outcome, daemon)
        if diagnosis is not None:
            run_id = outcome.request.run_id or "<run>"
            print(
                f"{diagnosis.line(outcome.prefix)} (runtime record: <out>/runtime/"
                f"{run_id}-<UTC>.json)",
                file=sys.stderr,
            )
            record = diagnosis.as_record()  # file names only: no host paths in the record
            findings.append(
                Finding(
                    "info",
                    "stop-diagnosis",
                    f"stage={record['stage']} category={record['category']} "
                    f"result_written={record['result_written']} "
                    f"evidence={','.join(record['evidence']) or 'none'}",
                )
            )
        request = outcome.request
        if request.controller and request.volume:
            leftovers = health.run_leftovers(request.controller, request.volume)
            if leftovers:
                findings.append(Finding("warn", "leftover-resources", "; ".join(leftovers)))
        return findings


#: The observers shipped with STRICT (tests replace :data:`OBSERVERS`; this stays the default).
DEFAULT_OBSERVERS: tuple[LaunchObserver, ...] = (HealthObserver(),)
#: The observers run around every launch, in order.
OBSERVERS: tuple[LaunchObserver, ...] = DEFAULT_OBSERVERS


def classify(outcome: LaunchOutcome) -> str:
    """A short name for how a launch ended (recorded; never changes the exit code or verdict).

    The stage and category of a launch that did not end cleanly are recorded by
    :class:`HealthObserver` as its ``stop-diagnosis`` finding, not here.
    """
    if outcome.returncode is None:
        return "runner-error"
    return "completed" if outcome.returncode == 0 else "failed"
