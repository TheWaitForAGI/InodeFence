"""Where a target hook hands a run to its controller shell launcher: the ONE crossing point.

Every target's explore (and node-tar's replay) hook runs the loop the same way: a host shell
launcher under ``scripts/`` builds the controller, starts it and delegates through
``scripts.container_host``; the target containers' isolation is the controller's. This module
only names those launchers and makes the call; it does not change what a launcher does, the
arguments a hook passes, or the environment (each hook still builds its own ``env``).

Insertion point for the runtime execution policy (later PR): a policy (for example a strict /
fast / replay mode) belongs in :func:`run_launcher`, the one place every hook's run passes
through, instead of in each hook. Today it adds nothing: it calls ``runner`` with exactly the
argv and keyword arguments the hook used before.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

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
    **kwargs: Any,
) -> Any:
    """Run ``bash <script> <args...>`` through ``runner`` (``subprocess.run`` or a test fake).

    ``kwargs`` (``cwd``, ``check``) pass through unchanged, so each hook's call is exactly what it
    was. Returns whatever ``runner`` returns (a ``CompletedProcess``).
    """
    return runner(["bash", str(script), *args], env=env, **kwargs)
