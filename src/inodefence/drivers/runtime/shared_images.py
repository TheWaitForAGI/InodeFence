"""Are the shared controller / helper images the ones this checkout builds? (FAST's one flag.)

Every controller launcher starts by rebuilding two images that are the same for every target and
every run: ``inodefence-controller:local`` and ``inodefence-helper:local``. With an intact build
cache that rebuild changes nothing, and each launcher already has a switch to leave it out
(``SKIP_BUILD=1``). The switch alone is not safe: the tags are host-global, so the images there
may be older than this checkout, or built from another checkout.

This module holds the proof FAST needs before it sets that switch:

* :func:`inputs_digest` -- a SHA-256 over every file the two builds read from the checkout
  (:data:`BUILD_INPUTS`: the two Dockerfiles and the one file they copy);
* a **stamp** (:func:`stamp_path`, a per-user cache file, never in the repository or the output
  folder) that says: on this Docker context, a build from inputs with this digest gave these two
  image ids, at this time. It is written only by :func:`record`, which the session calls right
  after a launcher's own build-only run (``BUILD_ONLY=1``) succeeded;
* :func:`check` -- the images are *verified* only when the stamp is for this context and this
  digest, is younger than :data:`MAX_AGE_SECONDS`, and both tags still resolve to the stamped ids.
  Anything else -- no stamp, an edited Dockerfile or helper, a rebuilt or removed image, Docker not
  answering, an unreadable stamp -- is *not verified*, with the reason.

What a verified image is, exactly: an image this host built from byte-identical inputs with the
launcher's own build command at most :data:`MAX_AGE_SECONDS` ago. It is not re-resolved against the
registry in between (the controller's base is a tag), which is the one way it can differ from what
STRICT would build now; the age limit bounds that.

Read-only towards Docker (``docker image inspect``); nothing is built, tagged or removed here.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from inodefence.drivers.runtime import health

STAMP_SCHEMA = "inodefence-shared-images-v1"
#: The two images every controller launcher builds (``CONTROLLER_IMAGE=`` / ``HELPER_IMAGE=`` in
#: each ``scripts/local_*.sh``; a test keeps them in step).
SHARED_IMAGES: tuple[str, str] = ("inodefence-controller:local", "inodefence-helper:local")
#: Every checkout file those two builds read: each Dockerfile and what it copies (a test checks
#: the Dockerfiles copy nothing else).
BUILD_INPUTS: tuple[str, ...] = (
    ".devcontainer/Dockerfile",
    "tools/container-helper/Dockerfile",
    "tools/container-helper/helper.py",
)
#: A stamp older than this is not used: the images are rebuilt (as STRICT does every run) at least
#: this often, so a moved base tag is picked up within a day.
MAX_AGE_SECONDS = 24 * 60 * 60

#: The launchers that honour ``SKIP_BUILD=1`` (leave out the shared-image build), by file name.
SKIP_BUILD_LAUNCHERS: frozenset[str] = frozenset(
    {
        "local_node_tar_smoke.sh",
        "local_decompress_selfdiscover.sh",
        "local_oras_go_selfdiscover.sh",
        "local_python_tarfile_explore.sh",
    }
)
#: Those that also have a build-only run (``BUILD_ONLY=1``: build the shared images, then exit
#: before any controller exists) -- the only way FAST verifies the images. A test keeps both sets
#: in step with the scripts.
BUILD_ONLY_LAUNCHERS: frozenset[str] = SKIP_BUILD_LAUNCHERS - {"local_python_tarfile_explore.sh"}

#: ``docker <args>`` -> the answer (``health.ask_docker``; a test passes a fake).
Ask = Callable[[list[str]], health.DockerAnswer]


@dataclass(frozen=True, slots=True)
class SharedImages:
    """The answer of :func:`check` / :func:`record`: verified or not, and what was looked at."""

    verified: bool
    reason: str
    context: str | None = None
    inputs_sha256: str | None = None
    #: image tag -> image id, as Docker answered now (empty if it did not)
    image_ids: Mapping[str, str] | None = None
    verified_at: str | None = None

    def as_record(self) -> dict[str, Any]:
        """For the runtime record: no host path."""
        return {
            "verified": self.verified,
            "reason": self.reason,
            "docker_context": self.context,
            "inputs_sha256": self.inputs_sha256,
            "image_ids": dict(self.image_ids or {}),
            "verified_at": self.verified_at,
        }


def stamp_path(environ: Mapping[str, str] | None = None) -> Path:
    """The per-user stamp file: ``$XDG_CACHE_HOME/inodefence/`` (default ``~/.cache``)."""
    env = os.environ if environ is None else environ
    base = env.get("XDG_CACHE_HOME") or str(Path(env.get("HOME") or Path.home()) / ".cache")
    return Path(base) / "inodefence" / "shared-images-v1.json"


def inputs_digest(repo_root: Path) -> str:
    """SHA-256 over the name and bytes of every build input (raises ``OSError`` if one is gone)."""
    digest = hashlib.sha256()
    for name in BUILD_INPUTS:
        data = (repo_root / name).read_bytes()
        digest.update(f"{name}\0{len(data)}\0".encode())
        digest.update(data)
    return digest.hexdigest()


def docker_context(env: Mapping[str, str], ask: Ask | None = None) -> str | None:
    """The launcher's context: ``INODEFENCE_DOCKER_CONTEXT``, else ``docker context show``."""
    ask = ask or health.ask_docker
    chosen = env.get("INODEFENCE_DOCKER_CONTEXT")
    if chosen:
        return chosen
    answer = ask(["context", "show"])
    name = answer.stdout.strip() if answer.returncode == 0 else ""
    return name or None


def image_ids(context: str, ask: Ask | None = None) -> dict[str, str] | None:
    """Both shared images' ids on ``context``; ``None`` if one is absent or Docker is silent."""
    ask = ask or health.ask_docker
    answer = ask(["--context", context, "image", "inspect", "--format", "{{.Id}}", *SHARED_IMAGES])
    if answer.returncode != 0:
        return None
    ids = answer.stdout.split()
    if len(ids) != len(SHARED_IMAGES) or not all(i.startswith("sha256:") for i in ids):
        return None
    return dict(zip(SHARED_IMAGES, ids, strict=True))


def _read_stamp(path: Path) -> dict[str, Any] | None:
    try:
        stamp = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(stamp, dict) or stamp.get("schema") != STAMP_SCHEMA:
        return None
    return stamp


def check(
    repo_root: Path,
    env: Mapping[str, str],
    *,
    ask: Ask | None = None,
    stamp: Path | None = None,
    now: float | None = None,
) -> SharedImages:
    """Verified only if the stamp matches this context, these inputs and the images there now."""
    try:
        digest = inputs_digest(repo_root)
    except OSError as error:
        return SharedImages(False, f"a build input could not be read ({error.strerror})")
    context = docker_context(env, ask)
    if context is None:
        return SharedImages(False, "Docker did not name its context", inputs_sha256=digest)
    ids = image_ids(context, ask)
    if ids is None:
        return SharedImages(
            False,
            "a shared image is not on this host (or Docker did not answer)",
            context,
            digest,
        )
    found = _read_stamp(stamp or stamp_path(env))
    entry = (found or {}).get("contexts", {}).get(context) if found else None
    if not isinstance(entry, dict):
        reason = "the shared images have not been verified for this Docker context yet"
        return SharedImages(False, reason, context, digest, ids)
    if entry.get("inputs_sha256") != digest:
        reason = "the build inputs changed since the shared images were verified"
        return SharedImages(False, reason, context, digest, ids)
    if entry.get("image_ids") != ids:
        reason = "a shared image was rebuilt or replaced since it was verified"
        return SharedImages(False, reason, context, digest, ids)
    verified_epoch = entry.get("verified_epoch")
    current = time.time() if now is None else now
    if not isinstance(verified_epoch, (int, float)) or not (
        0 <= current - verified_epoch <= MAX_AGE_SECONDS
    ):
        reason = f"the verification is older than {MAX_AGE_SECONDS // 3600} h"
        return SharedImages(False, reason, context, digest, ids)
    return SharedImages(
        True,
        "built from these inputs by a launcher's own build",
        context,
        digest,
        ids,
        str(entry.get("verified_at")),
    )


def record(
    repo_root: Path,
    env: Mapping[str, str],
    *,
    ask: Ask | None = None,
    stamp: Path | None = None,
    now: float | None = None,
) -> SharedImages:
    """Right after a launcher's build-only run succeeded: stamp what is there now, and answer.

    Verified when both images are there; a stamp that cannot be saved does not undo that for this
    run (the reason says so), it only means the next run verifies again.
    """
    try:
        digest = inputs_digest(repo_root)
    except OSError as error:
        return SharedImages(False, f"a build input could not be read ({error.strerror})")
    context = docker_context(env, ask)
    ids = image_ids(context, ask) if context else None
    if context is None or ids is None:
        return SharedImages(
            False,
            "the build reported success but a shared image is not there (or Docker did not answer)",
            context,
            digest,
        )
    current = time.time() if now is None else now
    verified_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(current))
    path = stamp or stamp_path(env)
    found = _read_stamp(path) or {"schema": STAMP_SCHEMA, "contexts": {}}
    contexts = found.get("contexts")
    if not isinstance(contexts, dict):
        contexts = {}
    contexts[context] = {
        "inputs_sha256": digest,
        "image_ids": ids,
        "verified_at": verified_at,
        "verified_epoch": current,
    }
    reason = "built just now by this launcher's build-only run"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=".tmp-", suffix=".json")
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(
                {"schema": STAMP_SCHEMA, "contexts": contexts}, stream, indent=2, sort_keys=True
            )
            stream.write("\n")
        os.replace(temporary, path)
    except OSError as error:
        reason += f" (not remembered for the next run: {error.strerror or error})"
    return SharedImages(True, reason, context, digest, ids, verified_at)
