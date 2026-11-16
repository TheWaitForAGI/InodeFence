"""Where a target hook hands a run to its controller shell launcher: the ONE crossing point.

Every target's explore (and node-tar's replay) hook runs the loop the same way: a host shell
launcher under ``scripts/`` builds the controller, starts it and delegates through
``scripts.container_host``; the target containers' isolation is the controller's. This module
only names those launchers and makes the call; it does not change what a launcher does, the
arguments a hook passes, or the environment (each hook still builds its own ``env``).

The runtime execution policy enters here, the one place every hook's run passes through: a hook
passes its ``RuntimeSession`` (``ExploreOptions.runtime``) and the launch runs through
:meth:`inodefence.drivers.runtime.session.RuntimeSession.launch`, which times and records it.
Under STRICT ``runner`` still gets exactly the argv, environment and keyword arguments the hook
passed; without a session the call is the plain one.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from inodefence.drivers.runtime.session import RuntimeSession

#: The controller shell launcher of each target (under ``<repository>/scripts/``; never moved).
LAUNCHERS: dict[str, str] = {
    "node-tar": "local_node_tar_smoke.sh",
    "decompress": "local_decompress_selfdiscover.sh",
    "oras-go": "local_oras_go_selfdiscover.sh",
    "python-tarfile": "local_python_tarfile_explore.sh",
}


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
    **kwargs: Any,
) -> Any:
    """Run ``bash <script> <args...>`` through ``runner`` (``subprocess.run`` or a test fake).

    ``kwargs`` (``cwd``, ``check``) pass through unchanged, so each hook's call is exactly what it
    was. With a ``session`` the launch is recorded by it; the call is the same.
    Returns whatever ``runner`` returns (a ``CompletedProcess``).
    """
    if session is not None:
        return session.launch(script, args, runner=runner, env=env, **kwargs)
    return runner(["bash", str(script), *args], env=env, **kwargs)
