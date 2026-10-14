"""Execute the fixed Gate 4 native effect qualification matrix."""

import json

from scripts.qualify_node_effect_observation import (
    NOT_QUALIFIED,
    QUALIFIED,
    run_qualification,
)


def test_native_effect_observation_qualification(
    container_backend, container_image, campaign_evidence
) -> None:
    report, digest, decision = run_qualification(
        container_backend,
        container_image,
        campaign_evidence,
        repetitions=20,
    )
    value = json.loads(report.read_bytes())
    assert decision in (QUALIFIED, NOT_QUALIFIED)
    assert value["summary"]["decision"] == decision
    assert value["classification"] == ("REPRODUCIBLE" if decision == QUALIFIED else "RAW_ONLY")
    assert len(digest) == 64
    print(
        json.dumps(
            {
                "qualification": str(report),
                "qualification_sha256": digest,
                "decision": decision,
            },
            sort_keys=True,
        )
    )
