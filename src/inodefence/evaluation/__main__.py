"""Read-only evidence verification: python -m inodefence.evaluation DIRECTORY."""

import argparse
import sys
from pathlib import Path

from .encoding import json_bytes
from .verify import VerificationError, verify_campaign


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--manifest-sha256")
    args = parser.parse_args()
    try:
        verified = verify_campaign(args.directory, expected_manifest_sha256=args.manifest_sha256)
    except VerificationError as error:
        print(str(error), file=sys.stderr)
        return 1
    print(
        json_bytes(
            {
                "classification": "verified-raw-evidence",
                "manifest_sha256": verified.manifest_sha256,
                "steps_sha256": verified.steps_sha256,
                "number_of_steps": len(verified.result.steps),
            }
        ).decode("ascii")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
