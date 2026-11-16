"""Product drivers: the per-target commands behind ``inodefence verify / explore / replay``.

This layer runs a target the way a user asks for it (fixed axes, an exploration, a replay) and
writes the common result file. It only *composes* the engine (generator, mutator, builder,
observer, oracle, feedback, campaign loops) and the isolated execution path; it never
re-implements them, and nothing in the engine imports it.

Layout:

* ``run_target`` -- target registry (``TARGETS``), the ``TargetAdapter`` interface and the
  verify driver; ``run_target_explore`` / ``run_target_replay`` -- the explore and replay drivers;
  ``explore_result`` -- loop report -> common result; ``regression_check`` -- known-fixture
  regression; ``image_prepare`` / ``npm_registry`` -- shared image preparation.
* ``node_tar`` / ``decompress`` / ``oras_go`` / ``python_tarfile`` -- one subpackage per target
  (``adapter`` plus its explore / replay / image / registry hooks).
* ``repo`` -- the single place that resolves the repository checkout (``tools/`` build assets, the
  controller shell launchers under ``scripts/``, the docker build context).
* ``launcher`` -- the single place where a target hook hands a run to a controller shell launcher.

Dependency direction: ``cli -> locate -> drivers -> engine``; ``drivers.repo`` is a leaf
(stdlib + ``inodefence.user_config``). The drivers import neither ``locate`` nor ``cli``.

The old ``scripts/<name>.py`` paths of the externally invoked drivers remain as thin aliases (see
``scripts/README.md``). Running a target still needs a repository clone (``tools/`` and the shell
launchers are not packaged).
"""
