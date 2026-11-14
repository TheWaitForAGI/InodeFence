"""python-tarfile effect worker: runs INSIDE a derived official ``python:X.Y.Z-slim`` image.

Standard library only (the image is the unmodified official runtime plus this one file at
``/target/worker.py``). The host-side ``inodefence.targets.python_tarfile_container`` invokes it
through the common container backend (no network, read-only root, dropped capabilities, non-root
user); the archive and the extraction root live on the disposable runtime volume.

    python -I /target/worker.py --identify
    python -I /target/worker.py --self-test
    python -I /target/worker.py extract ARCHIVE EXTRACTION_ROOT POLICY

``extract`` extracts member by member with the given extraction filter (``data`` or
``fully_trusted``) and prints one JSON line per member it reached, then one final JSON line:

    {"ordinal": 0, "status": "succeeded", "error": null}
    {"ordinal": 1, "status": "errored", "error": "AbsoluteLinkError"}
    {"format": "inodefence-python-tarfile-run-v1", "status": "rejected", "members": 2, ...}

Exit codes: 0 every member extracted, 2 the filter refused a member, 3 any other extraction
failure, 4 bad usage. The worker reports what ``tarfile`` did; the C0/C1/C2 verdict is made
host-side from the before/after snapshots, never from these lines.
"""

import hashlib
import io
import json
import os
import platform
import sys
import tarfile
import tempfile

FORMAT = "inodefence-python-tarfile-run-v1"
POLICIES = ("data", "fully_trusted")


def _sha256(path):
    with open(path, "rb") as stream:
        return hashlib.sha256(stream.read()).hexdigest()


def identify():
    print(
        json.dumps(
            {
                "python_version": platform.python_version(),
                "tarfile_sha256": _sha256(tarfile.__file__),
                "worker_sha256": _sha256(os.path.abspath(__file__)),
                "has_data_filter": hasattr(tarfile, "data_filter"),
            },
            sort_keys=True,
        )
    )
    return 0


def extract(archive, root, policy):
    reached = 0
    status, code, error = "success", 0, None
    try:
        with tarfile.open(archive, mode="r:") as tar:
            tar.errorlevel = 2
            for ordinal, member in enumerate(tar.getmembers()):
                reached = ordinal + 1
                try:
                    tar.extract(member, root, filter=policy)
                except tarfile.FilterError as exc:
                    print(
                        json.dumps(
                            {"ordinal": ordinal, "status": "errored", "error": type(exc).__name__}
                        )
                    )
                    status, code, error = "rejected", 2, f"{type(exc).__name__}: {exc}"
                    break
                print(json.dumps({"ordinal": ordinal, "status": "succeeded", "error": None}))
    except tarfile.FilterError as exc:
        status, code, error = "rejected", 2, f"{type(exc).__name__}: {exc}"
    except (tarfile.TarError, OSError) as exc:
        status, code, error = "failed", 3, f"{type(exc).__name__}: {exc}"
    print(
        json.dumps(
            {
                "format": FORMAT,
                "status": status,
                "members": reached,
                "policy": policy,
                "python_version": platform.python_version(),
                "error": None if error is None else error[:200],
            },
            sort_keys=True,
        )
    )
    return code


def self_test():
    """Extract one harmless in-memory member under a fresh temporary directory."""
    payload = b"inodefence self-test\n"
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as tar:
        info = tarfile.TarInfo("ok.txt")
        info.size = len(payload)
        tar.addfile(info, io.BytesIO(payload))
    with tempfile.TemporaryDirectory() as work:
        archive = os.path.join(work, "input.tar")
        root = os.path.join(work, "extract")
        os.mkdir(root)
        with open(archive, "wb") as stream:
            stream.write(buffer.getvalue())
        with open(os.devnull, "w") as quiet:
            saved, sys.stdout = sys.stdout, quiet
            try:
                code = extract(archive, root, "data")
            finally:
                sys.stdout = saved
        with open(os.path.join(root, "ok.txt"), "rb") as stream:
            ok = code == 0 and stream.read() == payload
    print(json.dumps({"self_test": "ok" if ok else "failed"}))
    return 0 if ok else 3


def main(argv):
    if argv == ["--identify"]:
        return identify()
    if argv == ["--self-test"]:
        return self_test()
    if len(argv) == 4 and argv[0] == "extract" and argv[3] in POLICIES:
        if not hasattr(tarfile, "data_filter"):
            print(
                json.dumps({"format": FORMAT, "status": "failed", "error": "no extraction filters"})
            )
            return 3
        return extract(argv[1], argv[2], argv[3])
    print(
        "usage: worker.py --identify | --self-test | extract ARCHIVE ROOT POLICY", file=sys.stderr
    )
    return 4


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
