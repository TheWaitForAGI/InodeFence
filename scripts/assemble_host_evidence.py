"""Combine unmodified #313 inventory objects with separately measured evidence."""

import argparse
import json
import sys
from pathlib import Path

from scripts.verify_host_freeze import digest, read_json


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host-id", required=True, choices=("HOST1", "HOST2"))
    for name in ("windows", "linux", "measured", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    try:
        windows, win_hash = read_json(args.windows)
        linux, linux_hash = read_json(args.linux)
        measured, measured_hash = read_json(args.measured)
        value = {
            "schema": "inodefence-host-evidence-v1",
            "host_id": args.host_id,
            "source_sha256": {"windows": win_hash, "linux": linux_hash, "measured": measured_hash},
            "windows_inventory": windows,
            "linux_inventory": linux,
            "measured": measured,
        }
        raw = (json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2) + "\n").encode()
        with args.output.open("xb") as stream:
            stream.write(raw)
        print(f"{digest(raw)}  {args.output}")
        return 0
    except (ValueError, OSError) as error:
        print(f"BLOCKED: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
