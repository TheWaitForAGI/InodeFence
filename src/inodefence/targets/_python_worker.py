"""Private reference worker; invocation and error codes belong to this adapter."""

import argparse
import os
import sys
import tarfile
from pathlib import Path

from inodefence.runtime import open_runtime_directory
from inodefence.targets.python_tarfile import _validate_paths


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("extraction_root", type=Path)
    args = parser.parse_args()
    _validate_paths(args.archive, args.extraction_root)
    try:
        with open_runtime_directory(args.archive.parent) as directory_fd:
            descriptor = os.open(
                args.archive.name,
                os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC,
                dir_fd=directory_fd,
            )
            with (
                os.fdopen(descriptor, "rb") as stream,
                tarfile.open(fileobj=stream, mode="r:") as tar,
            ):
                tar.errorlevel = 2
                tar.extractall(args.extraction_root, filter="data")
    except tarfile.FilterError as error:
        print(f"{type(error).__name__}: {error}", file=sys.stderr)
        return 2
    except tarfile.TarError as error:
        print(f"{type(error).__name__}: {error}", file=sys.stderr)
        return 3
    except OSError as error:
        print(f"{type(error).__name__}: {error}", file=sys.stderr)
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
