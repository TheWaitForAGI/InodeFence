"""Phase-2 baseline observations, not production fixes or post-fix acceptance.

The audit reader only reads inert TAR headers; it never extracts or spawns a
target. Its ExecutionResult is explicitly synthetic process evidence. Runtime
setup, snapshots, campaign assembly and export use the actual implementations.
Malformed records and link snapshots below are caller-built evidence, not output
of an extractor or a claim of verified containment. Convert/remove flaw-accepting
assertions when a separately reviewed fix changes these boundaries.
"""

import io
import json
import tarfile
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from typing import cast

import pytest

from inodefence.builder import build_tar
from inodefence.campaign import CampaignConfig, CampaignResult, run_campaign
from inodefence.campaign_export import export_campaign
from inodefence.feedback import Corpus, state_signature, violation_fingerprints
from inodefence.model import (
    ArchiveCase,
    ArchiveEntry,
    ChangeField,
    EntryType,
    ExecutionResult,
    ExecutionStatus,
    ObjectSnapshot,
    ObjectType,
    SignatureObject,
    StateChange,
    canonical_json,
)
from inodefence.model.provenance import ExecutionSafety, TargetProvenance
from inodefence.observer import compare_states
from inodefence.oracle import evaluate_contracts


class HeaderReader:
    """Trusted audit-only reader; no extraction and no actual process outcome."""

    @property
    def provenance(self) -> TargetProvenance:
        return TargetProvenance(
            "audit-header-reader", "synthetic-v1", None, ExecutionSafety.TRUSTED_REFERENCE
        )

    def run(self, archive_path: Path, extraction_root: Path) -> ExecutionResult:
        assert archive_path.parent.parent == extraction_root.parent
        data = archive_path.read_bytes()
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as archive:
            names = [member.name for member in archive.getmembers()]
        return ExecutionResult(
            self.provenance.target_id,
            self.provenance.target_version,
            (),
            ExecutionStatus.SUCCESS,
            0,
            json.dumps({"sha256": sha256(data).hexdigest(), "names": names}),
            "audit-only synthetic process evidence; no extractor executed",
            0.0,
        )


def _campaign() -> CampaignResult:
    case = ArchiveCase((ArchiveEntry("benign", EntryType.REGULAR, content=b"benign"),))
    return run_campaign((case,), HeaderReader(), CampaignConfig(11, 1))


def test_en001_logical_byte_mismatch_survives_pipeline_campaign_and_export(tmp_path: Path) -> None:
    absolute = ArchiveCase((ArchiveEntry("/" + "a" * 100, EntryType.REGULAR, content=b"benign"),))
    relative = replace(absolute, entries=(replace(absolute.entries[0], path="a" * 100),))
    assert absolute.case_id != relative.case_id
    data = build_tar(absolute)
    assert data == build_tar(relative) == build_tar(absolute)
    assert data[345:500].split(b"\0", 1)[0] == b""
    assert data[:100] == b"a" * 100

    campaign = run_campaign((absolute, relative), HeaderReader(), CampaignConfig(11, 2))
    expected_digest = sha256(data).hexdigest()
    for step in campaign.steps:
        result = step.result
        read = json.loads(result.execution.stdout)
        assert read == {"sha256": expected_digest, "names": ["a" * 100]}
        assert result.archive_sha256 == expected_digest
        archive_object = result.before.get("archive/input.tar")
        assert archive_object is not None and archive_object.content_digest == expected_digest
        assert not Path(result.after.sandbox_root).exists()
        assert all(not verdict.violated for verdict in result.violations)
    manifest, steps = export_campaign(campaign, tmp_path / "reader-evidence")
    records = [json.loads(line)["value"] for line in steps.read_text().splitlines()]
    assert [record["result"]["case"]["entries"][0]["path"] for record in records] == [
        absolute.entries[0].path,
        relative.entries[0].path,
    ]
    assert {record["result"]["archive_sha256"] for record in records} == {expected_digest}
    assert json.loads(manifest.read_bytes())["initial_case_ids"] == [
        absolute.case_id,
        relative.case_id,
    ]


def test_en002_caller_mutable_values_export_but_unhashable_signature_aborts(
    tmp_path: Path,
) -> None:
    campaign = _campaign()
    result = campaign.steps[0].result
    sentinel = result.after.get("outside/sentinel.txt")
    assert sentinel is not None and isinstance(sentinel.content_digest, str)
    digest = ["a"] * 64
    malformed = replace(sentinel, content_digest=cast(str, digest))
    digest[0] = "b"
    assert malformed.content_digest is digest
    assert json.loads(canonical_json(malformed))["value"]["content_digest"] == digest

    objects: list[SignatureObject] = []
    signature = replace(result.signature, objects=cast(tuple[SignatureObject, ...], objects))
    malformed_result = replace(
        result,
        after=replace(
            result.after,
            objects=tuple(
                malformed if obj.path == malformed.path else obj for obj in result.after.objects
            ),
        ),
        signature=signature,
    )
    corpus = Corpus()
    with pytest.raises(TypeError, match="unhashable"):
        corpus.consider(malformed_result)
    assert corpus.stats.observations == 0
    objects.extend(result.signature.objects)
    assert signature.objects is objects
    synthetic = replace(campaign, steps=(replace(campaign.steps[0], result=malformed_result),))
    _, steps = export_campaign(synthetic, tmp_path / "caller-built-evidence")
    record = json.loads(steps.read_text())["value"]["result"]
    exported_sentinel = next(
        obj for obj in record["after"]["objects"] if obj["path"] == malformed.path
    )
    assert exported_sentinel["content_digest"] == digest


def test_en003_oracle_recomputes_labels_but_caller_built_changes_export(tmp_path: Path) -> None:
    campaign = _campaign()
    result = campaign.steps[0].result
    before = result.before.get("outside/sentinel.txt")
    assert before is not None
    changed = replace(before, content_digest=sha256(b"different").hexdigest())
    after = replace(
        result.after,
        objects=tuple(
            changed if obj.path == changed.path else obj for obj in result.before.objects
        ),
    )
    misleading = StateChange(before.path, before, changed, (ChangeField.MODE,))
    actual = compare_states(result.before, after)
    assert len(actual) == 1 and actual[0].fields == (ChangeField.CONTENT,)
    verdicts = evaluate_contracts(result.before, after)
    assert not verdicts[0].violated and verdicts[2].violated
    assert verdicts[2].evidence == actual
    synthetic_verdicts = (*verdicts[:2], replace(verdicts[2], evidence=(misleading,)))
    assert violation_fingerprints(verdicts) != violation_fingerprints(synthetic_verdicts)
    synthetic_result = replace(
        result, after=after, changes=(misleading,), violations=synthetic_verdicts
    )
    _, steps = export_campaign(
        replace(campaign, steps=(replace(campaign.steps[0], result=synthetic_result),)),
        tmp_path / "caller-labels",
    )
    assert json.loads(steps.read_text())["value"]["result"]["changes"][0]["fields"] == ["mode"]


def test_en004_distinct_raw_links_share_novelty_and_suppress_second_parent() -> None:
    result = _campaign().steps[0].result
    absolute_target = result.after.sandbox_root + "/outside/sentinel.txt"
    relative_target = "$RUN/outside/sentinel.txt"
    link = ObjectSnapshot(
        "extract/link",
        ObjectType.SYMLINK,
        7,
        777,
        1,
        0o777,
        len(absolute_target),
        1000,
        1000,
        10,
        10,
        absolute_target,
    )
    absolute = replace(
        result.after,
        objects=tuple(sorted((*result.before.objects, link), key=lambda obj: obj.path)),
    )
    relative_link = replace(link, symlink_target=relative_target, size=len(relative_target))
    relative = replace(
        absolute,
        objects=tuple(relative_link if obj.path == link.path else obj for obj in absolute.objects),
    )
    assert absolute != relative
    signatures = [state_signature(result.before, after) for after in (absolute, relative)]
    assert signatures[0] == signatures[1]
    verdicts = [evaluate_contracts(result.before, after) for after in (absolute, relative)]
    assert verdicts[0] == verdicts[1] and all(not verdict.violated for verdict in verdicts[0])
    cases = [
        ArchiveCase((ArchiveEntry("link", EntryType.SYMLINK, link_target=target),))
        for target in (absolute_target, relative_target)
    ]
    assert cases[0].case_id != cases[1].case_id
    corpus = Corpus()
    decisions = [
        corpus.consider(
            replace(result, case=case, after=after, signature=signature, violations=violations)
        )
        for case, after, signature, violations in zip(
            cases, (absolute, relative), signatures, verdicts, strict=True
        )
    ]
    assert decisions[0].retained and not decisions[1].interesting
    assert tuple(entry.case for entry in corpus.entries) == (cases[0],)
