"""Attestation of the `make demo` node-tar image recipe provenance.

These checks run offline (no Docker). They establish that the committed recipe
fingerprint is deterministic, covers exactly the build-context files, is
sensitive to any input change, and that the demo report records it additively.
"""

import json
from hashlib import sha256

import pytest
from scripts import attest_demo_image_recipe, run_effect_demo
from scripts.run_effect_demo import native_demo_report, pinned_node_tar_version

from inodefence.targets.node_tar_recipe import (
    DEMO_IMAGE_DOCKERFILE,
    DEMO_IMAGE_RECIPE_FILES,
    RECIPE_FORMAT,
    RECIPE_SCHEMA,
    _base_images,
    _read_recipe_file,
    demo_image_recipe,
    recipe_digest,
    repository_root,
)

# The two base images the demo Dockerfile pins, digest-and-all, in sorted order.
EXPECTED_BASE_IMAGES = (
    "gcr.io/distroless/cc-debian12:nonroot@sha256:"
    "9dac0a79194e45a7da0158a9c6da57b217585af0786db3845d1f0ec1a0dd182f",
    "node:22.22.0-bookworm-slim@sha256:"
    "dd9d21971ec4395903fa6143c2b9267d048ae01ca6d3ea96f16cb30df6187d94",
)


def test_demo_image_recipe_is_deterministic() -> None:
    assert demo_image_recipe() == demo_image_recipe()


def test_recipe_records_the_declared_build_context_files() -> None:
    recipe = demo_image_recipe()

    assert recipe["format"] == RECIPE_FORMAT
    assert recipe["schema_version"] == RECIPE_SCHEMA
    assert recipe["dockerfile"] == DEMO_IMAGE_DOCKERFILE
    assert set(recipe["files_sha256"]) == set(DEMO_IMAGE_RECIPE_FILES)


def test_recorded_file_digests_match_the_committed_bytes() -> None:
    root = repository_root()
    recorded = demo_image_recipe()["files_sha256"]

    for name in DEMO_IMAGE_RECIPE_FILES:
        assert recorded[name] == sha256((root / name).read_bytes()).hexdigest()


def test_recipe_sha256_is_the_digest_of_the_file_digests() -> None:
    recipe = demo_image_recipe()

    assert recipe["recipe_sha256"] == recipe_digest(recipe["files_sha256"])


def test_recipe_digest_changes_when_any_input_digest_changes() -> None:
    recipe = demo_image_recipe()
    files = dict(recipe["files_sha256"])
    baseline = recipe_digest(files)

    for name in files:
        perturbed = dict(files)
        perturbed[name] = sha256(perturbed[name].encode("ascii") + b"x").hexdigest()
        assert recipe_digest(perturbed) != baseline


def test_recipe_tar_version_matches_the_repository_pin() -> None:
    assert demo_image_recipe()["tar_version"] == pinned_node_tar_version() == "7.5.22"


def test_recipe_base_images_are_the_committed_digest_pins() -> None:
    base_images = demo_image_recipe()["base_images"]

    assert tuple(base_images) == EXPECTED_BASE_IMAGES
    assert all("@sha256:" in reference for reference in base_images)


def test_base_images_reject_an_unpinned_or_missing_from() -> None:
    with pytest.raises(ValueError, match="not digest-pinned"):
        _base_images(b"FROM alpine:3.20\n")
    with pytest.raises(ValueError, match="no FROM"):
        _base_images(b"RUN echo hi\n")

    refs = _base_images(
        b"FROM one@sha256:" + b"0" * 64 + b" AS build\nFROM two@sha256:" + b"1" * 64 + b"\n"
    )
    assert refs == ("one@sha256:" + "0" * 64, "two@sha256:" + "1" * 64)


def test_read_recipe_file_rejects_a_symlinked_input(tmp_path) -> None:
    real = tmp_path / "real-dockerfile"
    real.write_bytes(b"FROM base@sha256:" + b"0" * 64 + b"\n")
    (tmp_path / "tools" / "node-tar").mkdir(parents=True)
    link = tmp_path / DEMO_IMAGE_DOCKERFILE
    link.symlink_to(real)

    with pytest.raises(ValueError, match="committed regular file"):
        _read_recipe_file(tmp_path, DEMO_IMAGE_DOCKERFILE)


def test_native_demo_report_attaches_the_committed_image_recipe(monkeypatch) -> None:
    """native_demo_report records image_recipe alongside the observed image_id."""
    image_id = "sha256:" + "a" * 64
    pin = pinned_node_tar_version()

    class _StubTarget:
        tar_version = pin
        node_version = "v22.22.0"

    class _StubBind:
        @staticmethod
        def bind(backend, image_id, *, profile):
            return _StubTarget()

    sentinel = object()

    def _stub_campaign(corpus, produce, config, on_step=None):
        return sentinel

    def _stub_report(result, producer):
        assert result is sentinel and producer == "native"
        return {"demo_report_schema": 2, "producer": "native", "steps": []}

    monkeypatch.setattr(run_effect_demo, "NodeTarEffectTarget", _StubBind)
    monkeypatch.setattr(run_effect_demo, "run_effect_campaign", _stub_campaign)
    monkeypatch.setattr(run_effect_demo, "effect_campaign_report", _stub_report)

    report = native_demo_report(object(), image_id, budget=5)  # type: ignore[arg-type]

    assert report["image_id"] == image_id
    assert report["image_recipe"] == demo_image_recipe()
    assert report["node_tar_version"] == pin


def test_attest_check_passes_for_the_committed_recipe() -> None:
    assert attest_demo_image_recipe.check_recipe() == []
    assert attest_demo_image_recipe.main(["--check"]) == 0


def test_attest_report_matches_a_report_carrying_the_current_recipe(tmp_path) -> None:
    matching = tmp_path / "report.json"
    matching.write_text(json.dumps({"image_recipe": demo_image_recipe()}), encoding="utf-8")
    assert attest_demo_image_recipe.compare_report(matching) == []
    assert attest_demo_image_recipe.main(["--report", str(matching)]) == 0

    drifted = tmp_path / "drifted.json"
    recipe = demo_image_recipe()
    recipe["recipe_sha256"] = "0" * 64
    drifted.write_text(json.dumps({"image_recipe": recipe}), encoding="utf-8")
    assert attest_demo_image_recipe.compare_report(drifted)
    assert attest_demo_image_recipe.main(["--report", str(drifted)]) == 1
