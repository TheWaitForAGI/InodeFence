import json
import random
from hashlib import sha256
from pathlib import Path

from inodefence.evaluation.node_packaging import prepare_node_release
from inodefence.generator import minimal_seed_corpus
from inodefence.model import EntryType, Region
from inodefence.model.filesystem import path_region
from inodefence.mutator.dispatch import MutationOperatorId, mutate_attempt_with_policy
from inodefence.mutator.policy import MutationPolicy

ROOT = Path(__file__).resolve().parents[2]
LOCKS = ROOT / "experiments/benchmarks/locks"
EXPECTED = {
    "7.5.2": (
        "d8bb8b8977460d2c0f7c7942d70a2057ee3cc128d80e115d73a2e00b2b84d112",
        "sha512-7NyxrTE4Anh8km8iEy7o0QYPs+0JKBTj5ZaqHg6B39erLg0qYXN3BijtShwbsNSvQ+LN75+KV+C4QR/f6Gwnpg==",
    ),
    "7.5.3": (
        "33067565217418c02e6cd76483587e46c081625b91de7e73d96405bdef4dc8d4",
        "sha512-ENg5JUHUm2rDD7IvKNFGzyElLXNjachNLp6RaGf4+JOgxXHkqA+gq81ZAMCUmtMtqBsoU62lcp6S27g1LCYGGQ==",
    ),
}


def _lock(version: str) -> tuple[Path, dict]:
    path = LOCKS / f"node-tar-{version}.package-lock.json"
    return path, json.loads(path.read_bytes())


def test_n01_exact_locks_match_official_target_sri_and_packaging_contract(tmp_path) -> None:
    for version, (digest, integrity) in EXPECTED.items():
        path, lock = _lock(version)
        assert sha256(path.read_bytes()).hexdigest() == digest
        assert lock["packages"][""]["dependencies"] == {"tar": version}
        assert lock["packages"]["node_modules/tar"] == {
            **lock["packages"]["node_modules/tar"],
            "version": version,
            "resolved": f"https://registry.npmjs.org/tar/-/tar-{version}.tgz",
            "integrity": integrity,
        }
        manifest = prepare_node_release(path, tmp_path / version, repository=ROOT)
        assert manifest["tar_version"] == version
        assert manifest["files_sha256"]["package-lock.json"] == digest


def test_n01_pair_has_identical_non_target_production_closure() -> None:
    normalized = []
    for version in EXPECTED:
        _, lock = _lock(version)
        root = lock["packages"][""]
        root["dependencies"].pop("tar")
        target = lock["packages"].pop("node_modules/tar")
        normalized.append(lock)
        assert target["version"] == version
    assert normalized[0] == normalized[1]
    assert normalized[0]["packages"]["node_modules/minipass"]["version"] == "7.1.3"


def test_n01_controlled_root_name_is_reachable_by_uniform_m1_dispatch() -> None:
    attempt = mutate_attempt_with_policy(
        minimal_seed_corpus()[2], random.Random(2450), MutationPolicy.M1
    )

    assert attempt.operator_id == MutationOperatorId.MUTATE_LINK_TARGET
    assert attempt.applied
    assert path_region("a") == Region.EXTERNAL
    hardlinks = [
        entry for entry in attempt.child_case.entries if entry.entry_type == EntryType.HARDLINK
    ]
    assert len(hardlinks) == 1 and hardlinks[0].link_target == "../a"
