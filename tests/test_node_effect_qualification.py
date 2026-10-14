"""Portable checks for the fixed Gate 4 qualification decision."""

from copy import deepcopy
from hashlib import sha256

from scripts.qualify_node_causal_effects import REJECTION_CASE, qualification_cases
from scripts.qualify_node_effect_observation import (
    NOT_QUALIFIED,
    PROFILES,
    QUALIFIED,
    _summarize,
)

from inodefence.model import EffectClass


def _complete_matrix() -> list[dict]:
    effects = {
        "regular-file": [
            EffectClass.NAMESPACE_CREATION.value,
            EffectClass.REGULAR_FILE_CONTENT_MODIFICATION.value,
        ],
        "directory-metadata": [
            EffectClass.NAMESPACE_CREATION.value,
            EffectClass.METADATA_MODIFICATION.value,
        ],
        "hardlink-identity": [EffectClass.HARDLINK_IDENTITY_RELATION_CREATION.value],
        "symlink": [EffectClass.SYMLINK_CREATION.value],
        "duplicate-path": [EffectClass.NAMESPACE_REPLACEMENT.value],
    }
    operations = {
        "regular-file": ["open", "write", "close"],
        "directory-metadata": ["mkdir", "chmod"],
        "hardlink-identity": ["link"],
        "symlink": ["symlink"],
        REJECTION_CASE: ["link", "unlink"],
    }
    empty_key = sha256(b"[]").hexdigest()
    runs = []
    for case_name in qualification_cases():
        for profile in PROFILES:
            for repetition in range(20):
                completion = [0]
                if case_name == "independent-files":
                    completion = [0, 1, 3, 2] if repetition % 2 else [0, 1, 2, 3]
                runs.append(
                    {
                        "case": case_name,
                        "profile": profile,
                        "repetition": repetition,
                        "status": "rejected" if case_name == REJECTION_CASE else "success",
                        "semantic_sha256": f"semantic-{case_name}-{repetition}",
                        "completion_order": completion if profile != "stock" else [],
                        "full_duration_ns": 1,
                        "evidence_bytes": 1,
                        "key_sha256": empty_key
                        if case_name == REJECTION_CASE or profile == "stock"
                        else f"key-{case_name}-{profile}",
                        "realized_effect_classes": effects.get(case_name, [])
                        if profile == "full"
                        else [],
                        "operation_types": operations.get(case_name, [])
                        if profile == "full"
                        else [],
                        "integrity_valid": True,
                        "failed_operation_count": int(
                            case_name == REJECTION_CASE and profile == "full"
                        ),
                    }
                )
    return runs


def _decision(runs: list[dict]) -> dict:
    return _summarize(
        runs,
        20,
        True,
        {"each-required-injection": True},
        True,
        True,
        True,
    )


def test_qualification_accepts_only_a_complete_passing_matrix() -> None:
    summary = _decision(_complete_matrix())
    assert summary["decision"] == QUALIFIED
    assert all(summary["criteria"].values())
    assert len(summary["completion_order_distributions"]["independent-files"]["full"]) == 2


def test_qualification_rejects_unstable_key_despite_schedule_reporting() -> None:
    runs = deepcopy(_complete_matrix())
    changed = next(
        item
        for item in runs
        if item["case"] == "independent-files"
        and item["profile"] == "full"
        and item["repetition"] == 1
    )
    changed["key_sha256"] = "schedule-leaked-into-key"
    summary = _decision(runs)
    assert summary["decision"] == NOT_QUALIFIED
    assert not summary["criteria"]["normalized_key_stability"]


def test_qualification_rejects_missing_effect_coverage() -> None:
    runs = deepcopy(_complete_matrix())
    for item in runs:
        if item["case"] == "duplicate-path" and item["profile"] == "full":
            item["realized_effect_classes"] = []
    summary = _decision(runs)
    assert summary["decision"] == NOT_QUALIFIED
    assert not summary["criteria"]["required_effect_coverage"]


def test_duplicate_truncation_does_not_satisfy_replacement_coverage() -> None:
    runs = _complete_matrix()
    for item in runs:
        if item["case"] == "duplicate-path" and item["profile"] == "full":
            item["realized_effect_classes"] = [EffectClass.TRUNCATION.value]
    summary = _decision(runs)
    assert summary["decision"] == NOT_QUALIFIED
    assert {name for name, passed in summary["criteria"].items() if not passed} == {
        "required_effect_coverage"
    }
    assert not summary["coverage"]["required_realized_effect_checks"]["duplicate-path"]


def test_replacement_outside_full_profile_cannot_satisfy_native_coverage() -> None:
    runs = _complete_matrix()
    for item in runs:
        if item["case"] == "duplicate-path":
            item["realized_effect_classes"] = (
                [EffectClass.TRUNCATION.value]
                if item["profile"] == "full"
                else [EffectClass.NAMESPACE_REPLACEMENT.value]
            )
    summary = _decision(runs)
    assert summary["decision"] == NOT_QUALIFIED
    assert not summary["criteria"]["required_effect_coverage"]
