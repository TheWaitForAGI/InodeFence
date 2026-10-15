import json
from copy import deepcopy
from hashlib import sha256
from pathlib import Path

from inodefence.evaluation.node_packaging import prepare_node_release

ROOT = Path(__file__).resolve().parents[2]
LOCKS = ROOT / "experiments/benchmarks/locks"
EXPECTED = {
    "7.5.2": (
        "31792107e9442ab18b04661d10ca0a0053db1fb7c58ca3aa702f1abb9908e243",
        "sha512-7NyxrTE4Anh8km8iEy7o0QYPs+0JKBTj5ZaqHg6B39erLg0qYXN3BijtShwbsNSvQ+LN75+KV+C4QR/f6Gwnpg==",
    ),
    "7.5.3": (
        "a63d02f09d9a9fb2def77da84d5145984ff260fcedd19839ba96ec858fdfae24",
        "sha512-ENg5JUHUm2rDD7IvKNFGzyElLXNjachNLp6RaGf4+JOgxXHkqA+gq81ZAMCUmtMtqBsoU62lcp6S27g1LCYGGQ==",
    ),
}
COMMON_CLOSURE = {
    "node_modules/@isaacs/fs-minipass": (
        "4.0.1",
        "sha512-wgm9Ehl2jpeqP3zw/7mo3kRHFp5MEDhqAdwy1fTGkHAwnkGOVsgpvQhL8B5n1qlb01jV3n/bI0ZfZp5lWA1k4w==",
    ),
    "node_modules/chownr": (
        "3.0.0",
        "sha512-+IxzY9BZOQd/XuYPRmrvEVjF/nqj5kgT4kEq7VofrDoM1MxoRjEWkrCC3EtLi59TVawxTAn+orJwFQcrqEN1+g==",
    ),
    "node_modules/minipass": (
        "7.1.2",
        "sha512-qOOzS1cBTWYF4BH8fVePDBOO9iptMnGUEZwNc/cMWnTV2nVLZ7VoNWEPHkYczZA0pdoA7dl6e7FL659nX9S2aw==",
    ),
    "node_modules/minizlib": (
        "3.1.0",
        "sha512-KZxYo1BUkWD2TVFLr0MQoM8vUUigWD3LlD83a/75BqC+4qE0Hb1Vo5v1FgcfaNXvfXzr+5EhQ6ing/CaBijTlw==",
    ),
    "node_modules/yallist": (
        "5.0.0",
        "sha512-YgvUTfwqyc7UXVMrB+SImsVYSmTS8X/tSrtdNZMImM+n7+QTriRXyXim0mBrTXNeqzVF0KWGgHPeiyViFFrNDw==",
    ),
}


def _lock(version: str) -> tuple[Path, dict]:
    path = LOCKS / f"node-tar-{version}.package-lock.json"
    return path, json.loads(path.read_bytes())


def test_n01_wrapper_locks_match_verified_distribution_identities_and_packaging(tmp_path):
    for version, (lock_digest, integrity) in EXPECTED.items():
        path, lock = _lock(version)
        assert sha256(path.read_bytes()).hexdigest() == lock_digest
        assert lock["packages"][""]["dependencies"] == {"tar": version}
        target = lock["packages"]["node_modules/tar"]
        assert target["version"] == version
        assert target["resolved"] == f"https://registry.npmjs.org/tar/-/tar-{version}.tgz"
        assert target["integrity"] == integrity

        manifest = prepare_node_release(path, tmp_path / version, repository=ROOT)
        assert manifest["tar_version"] == version
        assert manifest["files_sha256"]["package-lock.json"] == lock_digest
        assert (tmp_path / version / "package-lock.json").read_bytes() == path.read_bytes()


def test_n01_pair_has_identical_verified_non_target_production_closure():
    normalized = []
    for version in EXPECTED:
        _, lock = _lock(version)
        packages = lock["packages"]
        for name, (expected_version, integrity) in COMMON_CLOSURE.items():
            assert packages[name]["version"] == expected_version
            assert packages[name]["integrity"] == integrity

        pair_normalized = deepcopy(lock)
        pair_normalized["packages"][""]["dependencies"]["tar"] = "<PAIR-TARGET>"
        target = pair_normalized["packages"]["node_modules/tar"]
        for field in ("version", "resolved", "integrity"):
            target[field] = f"<{field.upper()}>"
        normalized.append(pair_normalized)

    assert normalized[0] == normalized[1]
