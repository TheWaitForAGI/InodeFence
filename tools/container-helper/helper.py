"""Harmless policy/lifecycle helper, never an archive extractor or exploit."""

import errno
import json
import os
import resource
import select
import socket
import sys
from pathlib import Path


def main() -> None:
    mode, root, *canaries = sys.argv[1:]
    if mode == "policy":
        run = Path(root)
        assert (run / "archive/input.tar").read_bytes() == b"benign controlled input"
        assert all(not Path(path).exists() for path in canaries)
        (run / "extract/visible").write_bytes(b"controlled workspace write")
        try:
            Path("/inodefence-disposable-canary").write_bytes(b"only inside target root")
        except OSError as error:
            assert error.errno == errno.EROFS
        else:
            raise AssertionError("root filesystem is writable")
        with socket.socket() as probe:
            assert probe.connect_ex(("192.0.2.1", 9)) == errno.ENETUNREACH
        assert os.listdir("/sys/class/net") == ["lo"]
        status = dict(
            line.split(":", 1)
            for line in Path("/proc/self/status").read_text().splitlines()
            if ":" in line
        )
        assert int(status["CapEff"].strip(), 16) == 0
        assert all(
            int(status[field].strip(), 16) == 0
            for field in ("CapInh", "CapPrm", "CapBnd", "CapAmb")
        )
        assert status["NoNewPrivs"].strip() == "1"
        assert os.getuid() == os.getgid() == 1000
        print(
            json.dumps(
                {
                    "uid": os.getuid(),
                    "gid": os.getgid(),
                    "cap_eff": status["CapEff"].strip(),
                    "no_new_privileges": status["NoNewPrivs"].strip(),
                    "nofile": resource.getrlimit(resource.RLIMIT_NOFILE),
                    "fsize": resource.getrlimit(resource.RLIMIT_FSIZE),
                    "pids_max": Path("/sys/fs/cgroup/pids.max").read_text().strip(),
                    "memory_max": Path("/sys/fs/cgroup/memory.max").read_text().strip(),
                    "swap_max": Path("/sys/fs/cgroup/memory.swap.max").read_text().strip(),
                    "sentinel_identity": [
                        (run / "outside/sentinel.txt").stat().st_dev,
                        (run / "outside/sentinel.txt").stat().st_ino,
                    ],
                }
            ),
            flush=True,
        )
    elif mode in ("descendants", "timeout"):
        reader, writer = os.pipe()
        child = os.fork()
        if child == 0:
            os.close(reader)
            os.setsid()
            grandchild = os.fork()
            if grandchild == 0:
                os.write(writer, b"grandchild ready\n")
            select.select([], [], [])
            raise AssertionError("hanging descendant resumed")
        os.close(writer)
        assert os.read(reader, 100) == b"grandchild ready\n"
        print("detached child and grandchild ready", flush=True)
        if mode == "timeout":
            select.select([], [], [])
    elif mode == "failure":
        print("controlled target failure", file=sys.stderr)
        sys.exit(4)
    elif mode == "output":
        os.write(1, b"a" * (2 * 1024 * 1024))
    else:
        raise ValueError("unknown controlled helper mode")


if __name__ == "__main__":
    main()
