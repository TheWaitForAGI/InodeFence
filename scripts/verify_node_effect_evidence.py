"""Independently verify one immutable native effect evidence bundle."""

import argparse
import json
from hashlib import sha256
from pathlib import Path

from inodefence.evaluation.native_effect_evidence import verify_native_effect_evidence
from inodefence.model import canonical_json


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--manifest-sha256")
    args = parser.parse_args()
    verified = verify_native_effect_evidence(
        args.directory,
        expected_manifest_sha256=args.manifest_sha256,
    )
    keys = [json.loads(canonical_json(key)) for key in verified.feedback_keys]
    print(
        json.dumps(
            {
                "classification": "INDEPENDENTLY_VERIFIED_NATIVE_EFFECT_EVIDENCE",
                "manifest_sha256": verified.manifest_sha256,
                "case_id": verified.result.base_result.case.case_id,
                "raw_stream_sha256": sha256(verified.raw_stream).hexdigest(),
                "lifecycle_events": len(verified.result.trace.lifecycle_events),
                "effect_events": len(verified.result.trace.effect_events),
                "causal_relations": len(verified.result.trace.causal_relations),
                "feedback_keys": keys,
            },
            sort_keys=True,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
