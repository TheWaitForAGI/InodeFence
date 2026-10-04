import json
from hashlib import sha256

import pytest

from inodefence.evaluation.encoding import json_bytes
from inodefence.evaluation.verify import VerificationError, verify_campaign


def rewrite_manifest(bundle, edit):
    path = bundle / "manifest.json"
    value = json.loads(path.read_bytes())
    edit(value)
    path.write_bytes(json_bytes(value) + b"\n")


def rewrite_step(bundle, edit):
    path = bundle / "steps.jsonl"
    steps = [json.loads(line) for line in path.read_bytes().splitlines()]
    edit(steps[0]["value"])
    content = b"\n".join(json_bytes(step) for step in steps) + b"\n"
    path.write_bytes(content)
    rewrite_manifest(bundle, lambda m: m.update(steps_sha256=sha256(content).hexdigest()))


def test_complete_benign_export_round_trips_without_target_execution(bundle, campaign):
    verified = verify_campaign(bundle)
    assert verified.result == campaign
    assert verified.manifest_bytes == (bundle / "manifest.json").read_bytes()
    assert verified.manifest_sha256 == sha256(verified.manifest_bytes).hexdigest()
    assert verify_campaign(bundle, expected_manifest_sha256=verified.manifest_sha256) == verified


def test_trusted_manifest_checksum_is_enforced(bundle):
    with pytest.raises(VerificationError, match="manifest checksum"):
        verify_campaign(bundle, expected_manifest_sha256="0" * 64)


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", 3),
        ("schema_version", True),
        ("steps_file", "../other"),
        ("number_of_steps", 99),
        ("number_of_steps", True),
        ("steps_sha256", "0" * 64),
        ("initial_case_ids", ["0" * 64]),
        ("retained_case_ids", []),
        ("execution_contexts", []),
        ("experiment_config_sha256", "0" * 64),
    ],
)
def test_manifest_mismatch_fails_closed(bundle, field, value):
    rewrite_manifest(bundle, lambda m: m.update({field: value}))
    with pytest.raises(VerificationError):
        verify_campaign(bundle)


@pytest.mark.parametrize(
    "edit",
    [
        lambda s: s.update(index=1),
        lambda s: s.update(index=True),
        lambda s: s.update(unrecognized=True),
        lambda s: s["feedback"].update(case_id="0" * 64),
        lambda s: s["result"].update(archive_sha256="0" * 64),
        lambda s: s["result"].update(archive_format="future"),
        lambda s: s["result"].update(violations=[]),
        lambda s: s["result"]["after"].update(phase="before"),
        lambda s: s["result"]["execution"].update(target_version="different"),
        lambda s: s["result"]["case"]["entries"][0].update(path="other.txt"),
        lambda s: s["result"]["case"]["entries"][0].update(
            content={"encoding": "base64", "data": "invalid!"}
        ),
    ],
)
def test_records_are_revalidated_even_when_attacker_recomputes_checksum(bundle, edit):
    rewrite_step(bundle, edit)
    with pytest.raises(VerificationError):
        verify_campaign(bundle)


def test_duplicate_keys_and_nonfinite_values_are_rejected(bundle):
    manifest = bundle / "manifest.json"
    original = manifest.read_bytes()
    for suffix in (b',"schema_version":4}', b',"extra":NaN}'):
        manifest.write_bytes(original.rstrip()[:-1] + suffix)
        with pytest.raises(VerificationError):
            verify_campaign(bundle)


@pytest.mark.parametrize("filename", ["manifest.json", "steps.jsonl"])
def test_missing_torn_or_symlink_file_is_never_complete(bundle, filename):
    path = bundle / filename
    content = path.read_bytes()
    path.write_bytes(content[:-8])
    with pytest.raises(VerificationError):
        verify_campaign(bundle)
    path.unlink()
    with pytest.raises(VerificationError):
        verify_campaign(bundle)
    other = bundle.parent / filename
    other.write_bytes(content)
    path.symlink_to(other)
    with pytest.raises(VerificationError):
        verify_campaign(bundle)


def test_config_checksum_and_identifier_are_independently_checked(tmp_path, campaign):
    from dataclasses import replace

    from inodefence.campaign_export import export_campaign

    config = '{"example":"explicit-config"}'
    result = replace(campaign, experiment_config_id=sha256(config.encode()).hexdigest())
    bundle = tmp_path / "configured"
    export_campaign(result, bundle, experiment_config_json=config)
    assert verify_campaign(bundle).result == result
    (bundle / "experiment.json").write_bytes(b'{"changed":true}\n')
    with pytest.raises(VerificationError, match="file checksum"):
        verify_campaign(bundle)
    rewrite_manifest(
        bundle,
        lambda m: m.update(
            experiment_config_sha256=sha256((bundle / "experiment.json").read_bytes()).hexdigest()
        ),
    )
    with pytest.raises(VerificationError, match="identifier"):
        verify_campaign(bundle)
