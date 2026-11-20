"""Where a target hook hands a run to its controller shell launcher: the ONE crossing point.

Every target's explore (and node-tar's replay) hook runs the loop the same way: a host shell
launcher under ``scripts/`` builds the controller, starts it and delegates through
``scripts.container_host``; the target containers' isolation is the controller's. This module
only names those launchers and makes the call; it does not change what a launcher does, the
arguments a hook passes, or the environment (each hook still builds its own ``env``).

The runtime execution policy enters here, the one place every hook's run passes through: a hook
passes its ``RuntimeSession`` (``ExploreOptions.runtime``) and the launch runs through
:meth:`inodefence.drivers.runtime.session.RuntimeSession.launch`, which times and records it and
runs the diagnostics around it.
Under STRICT ``runner`` still gets exactly the argv, environment and keyword arguments the hook
passed; without a session the call is the plain one.
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from inodefence.drivers.runtime.hooks import LaunchArtifacts
    from inodefence.drivers.runtime.session import RuntimeSession

#: The controller shell launcher of each target (under ``<repository>/scripts/``; never moved).
LAUNCHERS: dict[str, str] = {
    "node-tar": "local_node_tar_smoke.sh",
    "decompress": "local_decompress_selfdiscover.sh",
    "oras-go": "local_oras_go_selfdiscover.sh",
    "python-tarfile": "local_python_tarfile_explore.sh",
}


#: The names each launcher gives its disposable controller and runtime volume, before the
#: ``-<RUN_ID>`` suffix (``CONTROLLER=`` / ``VOLUME=`` in the launcher; a test keeps them in step).
RUN_RESOURCES: dict[str, tuple[str, str]] = {
    "node-tar": ("inodefence-local-controller", "inodefence-local-runtime"),
    "decompress": ("inodefence-decompress-controller", "inodefence-decompress-runtime"),
    "oras-go": ("inodefence-oras-go-controller", "inodefence-oras-go-runtime"),
    "python-tarfile": ("inodefence-python-tarfile-controller", "inodefence-python-tarfile-runtime"),
}


#: The launcher every target's case replay goes through. ``local_node_tar_smoke.sh replay`` is
#: target-neutral at the shell level: it takes an exact image id and one input line, builds only
#: the controller and helper images (never a target image), creates the same non-root controller
#: with the same two mounts as the other three launchers, and runs the one controller mode
#: ``effect-replay-case``. The other launchers have no replay mode and no way to pass an input,
#: so a replay of their targets uses this one; which target runs is decided inside the
#: controller from the input line (``scripts.effect_replay_targets``). The controller and volume
#: of a replay are therefore this launcher's (``inodefence-local-controller-<RUN_ID>``).
REPLAY_LAUNCHER_TARGET = "node-tar"


def run_resources(target: str, run_id: str | None) -> tuple[str, str]:
    """``(controller, volume)`` of ``target``'s launcher for ``RUN_ID`` = ``run_id``.

    The launcher's ``${RUN_ID:+-$RUN_ID}``: the suffix only when ``RUN_ID`` is set and non-empty.
    """
    suffix = f"-{run_id}" if run_id else ""
    controller, volume = RUN_RESOURCES[target]
    return controller + suffix, volume + suffix


def launcher_path(target: str, repo_root: Path) -> Path:
    """The launcher script of ``target`` inside the checkout ``repo_root``."""
    return repo_root / "scripts" / LAUNCHERS[target]


def run_launcher(
    script: Path,
    args: Sequence[str] = (),
    *,
    runner: Callable[..., Any],
    env: dict[str, str],
    session: RuntimeSession | None = None,
    artifacts: LaunchArtifacts | None = None,
    **kwargs: Any,
) -> Any:
    """Run ``bash <script> <args...>`` through ``runner`` (``subprocess.run`` or a test fake).

    ``kwargs`` (``cwd``, ``check``) pass through unchanged, so each hook's call is exactly what it
    was. With a ``session`` the launch is recorded and diagnosed by it (``artifacts``: where the
    run leaves its evidence, for the diagnostics); the call is the same.
    Returns whatever ``runner`` returns (a ``CompletedProcess``).
    """
    env = drop_inherited_identity_check(env, session)
    if session is not None:
        return session.launch(script, args, runner=runner, env=env, artifacts=artifacts, **kwargs)
    return runner(["bash", str(script), *args], env=env, **kwargs)


#: The launcher variable that reduces the targets' image identity probes (#536 option 1).
IDENTITY_CHECK_ENV = "DEMO_IDENTITY_CHECK_EVERY"


def drop_inherited_identity_check(
    env: dict[str, str], session: RuntimeSession | None
) -> dict[str, str]:
    """``env`` without the caller's own ``DEMO_IDENTITY_CHECK_EVERY`` (one stderr warning line).

    A STRICT run or a replay must not probe the image identity less because of an inherited
    variable; only a FAST exploration session sets it, from its policy
    (:meth:`RuntimeSession.launch`). Without an inherited value ``env`` is returned as is.
    """
    inherited = env.get(IDENTITY_CHECK_ENV)
    if inherited is None:
        return env
    prefix = session.prefix if session is not None else "INODEFENCE"
    print(
        f"{prefix} WARNING: environment variable {IDENTITY_CHECK_ENV}={inherited} is ignored; "
        "the image identity probe interval comes from --profile fast only",
        file=sys.stderr,
    )
    return {key: value for key, value in env.items() if key != IDENTITY_CHECK_ENV}
