"""Runtime execution policy of the product drivers: HOW a run executes, never what it judges.

* :mod:`~inodefence.drivers.runtime.policy` -- the profile (STRICT, the verified execution: the
  only one, and the baseline) and the place for host-side flags.
* :mod:`~inodefence.drivers.runtime.session` -- one exploration's session: every controller launch
  passes through it (``inodefence.drivers.launcher.run_launcher``) and it writes the additional
  runtime record ``<out>/runtime/*.json``.
* :mod:`~inodefence.drivers.runtime.hooks` -- what a diagnostic sees of a launch and may report.
* :mod:`~inodefence.drivers.runtime.diagnostics` -- the preflight / postflight observers and the
  launch-outcome classification.

Nothing is imported here: ``import inodefence.drivers.runtime.<module>`` loads only that module
(``doctor`` imports a leaf of this package without the drivers).

Direction: only the drivers use this package; the engine never imports it.
"""
