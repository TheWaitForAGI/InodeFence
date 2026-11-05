"""Docker-free tests for the Rust `tar` crate fixed-fixture probe and its role registration
(Tier-B, D039). No container runs: the dry-run plan, the C1/C2/outside-namespace derivations from
synthetic raw observations, the preregistered role rule and the registration keys are exercised.
"""

import pytest
import scripts.regression_check as rc
from experiments.repro import rust_tar_fixture_probe as probe

from inodefence.evaluation.rds_preregistration import parse_preregistration

_REF = {"dev": "1", "ino": "5", "nlink": 1, "size": 10, "type": "reg", "target": None}


def _raw(**overrides: object) -> dict:
    raw: dict = {
        "declined": None,
        "reference_before": dict(_REF),
        "reference_after": dict(_REF),
        "shared_identity": [],
        "outside_created": [],
        "outside_removed": [],
        "outside_changed": [],
    }
    raw.update(overrides)
    return raw


def test_dry_run_plans_the_regression_fixtures_and_one_ground_truth_without_docker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _no_docker(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("dry-run must not start any process")

    monkeypatch.setattr(probe.subprocess, "run", _no_docker)
    plan = probe.dry_run()
    names = [row["fixture"] for row in plan["role_fixtures"]]
    # The role fixtures are exactly the advisory-blind `make regression` set.
    assert names == [fixture.name for fixture in rc.build_fixtures()]
    assert plan["ground_truth"]["in_role_rule"] is False
    assert plan["runs_per_image"] == len(names) + 1
    assert plan["roles"] == {"affected": "0.4.35", "fixed": "0.4.36"}
    assert plan["probe_argv_shape"][-1] == "probe"


def test_probe_run_is_hardened_and_never_relaxes_isolation() -> None:
    argv = probe.probe_command("inodefence-rust-tar:0.4.35", "VEFS", "UkVG")
    joined = " ".join(argv)
    for flag in ("--network none", "--read-only", "--cap-drop ALL", "--rm"):
        assert flag in joined
    assert "--privileged" not in joined and "--cap-add" not in joined
    assert "-v" not in argv and "--mount" not in argv
    assert argv[-2:] == ["inodefence-rust-tar:0.4.35", "probe"]
    assert probe.identify_command("img")[-1] == "identify"


def test_role_fixture_rows_reuse_the_regression_c1_c2_derivation() -> None:
    fixture = rc.build_fixtures()[0]
    shared = _raw(
        shared_identity=["extract/link"], reference_after={**_REF, "nlink": 2, "target": None}
    )
    row = probe.evaluate_role_fixture(fixture, shared)
    assert (row["c1_identity_shared"], row["c2_reference_changed"], row["c1_or_c2"]) == (
        True,
        True,
        True,
    )
    assert row["outside_namespace_changed"] is False

    clean = probe.evaluate_role_fixture(fixture, _raw(declined={"message": "refused"}))
    assert clean["c1_or_c2"] is False and clean["outcome"] == "declined"

    errored = probe.evaluate_role_fixture(fixture, {"_run_error": True})
    assert errored["c1_or_c2"] is None and errored["outside_namespace_changed"] is None


def test_role_rule_is_applied_mechanically_to_observations() -> None:
    hit, miss, error = {"c1_or_c2": True}, {"c1_or_c2": False}, {"c1_or_c2": None}
    assert probe.role_by_rule([miss, hit])["role"] == "holdout"
    assert probe.role_by_rule([miss, hit])["hypothesis"] == "H-A"
    assert probe.role_by_rule([miss, miss])["role"] == "fix-verification"
    assert probe.role_by_rule([miss, miss])["hypothesis"] == "H-B"
    assert probe.role_by_rule([hit, error])["role"] is None
    assert probe.role_by_rule([])["role"] is None


def test_ground_truth_reports_outside_namespace_change_separately() -> None:
    truth = probe.ground_truth_fixture()
    created = probe.evaluate_ground_truth(
        truth, _raw(declined={"message": "x"}, outside_created=["created", "created/nested"])
    )
    assert created["outside_namespace_changed"] is True
    assert created["outside_created"] == ["created", "created/nested"]
    assert probe.evaluate_ground_truth(truth, _raw())["outside_namespace_changed"] is False
    assert probe.outside_namespace_changed({"_run_error": True}) is None
    assert probe.outside_namespace_changed({"declined": None}) is None  # malformed raw


def _registration(role: str, hypothesis: str) -> str:
    lines = [
        "experiment_id = exp3",
        "engine_sha = " + "0" * 40,
        "seeds = 1, 2",
        "budget = 10",
        "vocabulary = observed-names",
        "arm.R = unretained-walk-v1-uniform-mutation-v1",
        "arm.D = structure-coverage-v1-uniform-mutation-v1",
        "arm.S-u = effect-feedback-v2-or-violation-v1-boundary-attempt-v1-uniform-mutation-v1",
        "targets.rust-tar-0.4.35.extractor = rust-tar",
        "targets.rust-tar-0.4.35.version = 0.4.35",
        "targets.rust-tar-0.4.35.lock_digest = sha256:" + "ab" * 32,
        f"targets.rust-tar-0.4.35.role = {role}",
        f"targets.rust-tar-0.4.35.hypothesis = {hypothesis}",
        "targets.rust-tar-0.4.35.exposure = none",
        "exposure_ledger = experiments/preregistration/exposure-ledger.md",
        "exposure_ledger_sha256 = " + "c" * 64,
    ]
    if role == "holdout":
        lines += [
            "confirmatory_family = holdout:S-u-vs-R",
            "confirmatory_test = exact-logrank-permutation-v1",
            "multiplicity = holm-fwer-v1",
            "primary_endpoint = t_first",
            "event_threshold = 5",
        ]
    return "```preregistration\n" + "\n".join(lines) + "\n```\n"


@pytest.mark.parametrize(("role", "hypothesis"), [("holdout", "H-A"), ("fix-verification", "H-B")])
def test_either_rule_outcome_registers_without_generic_code_changes(
    role: str, hypothesis: str
) -> None:
    registration = parse_preregistration(_registration(role, hypothesis))
    (target,) = registration.targets
    assert (target.extractor, target.version, target.role, target.hypothesis) == (
        "rust-tar",
        "0.4.35",
        role,
        hypothesis,
    )
    assert target.exposure == "none"
