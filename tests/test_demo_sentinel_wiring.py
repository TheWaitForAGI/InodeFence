"""Opt-in multi-sentinel flags wired through the effect-demo controller path.

These tests exercise the flag parsing, validation and the two pure helpers, plus
a monkeypatched native run that captures the sentinels threaded into
``run_node_tar_effect_case``. No docker: the real target bind and native run are
replaced. The default (no flags) must stay the single unchanged sentinel and add
no ``sentinel_set`` report key (byte-identical to before).
"""

import argparse
from types import SimpleNamespace
from typing import cast

import pytest
import scripts.run_effect_demo as demo
from scripts.run_effect_demo import (
    NativeDemoAborted,
    apply_sentinel_set_record,
    check_demo_arguments,
    demo_options,
    native_demo_report,
    sentinel_set_from_args,
)

from inodefence.execution.base import ExecutionBackend
from inodefence.runtime import SentinelSpec
from inodefence.sentinel_set import generate_sentinel_set


def _parse(argv: list[str]) -> tuple[argparse.ArgumentParser, argparse.Namespace]:
    parser = argparse.ArgumentParser()
    demo.add_demo_arguments(parser)
    parser.add_argument("mode")
    args = parser.parse_args(argv)
    check_demo_arguments(parser, args)
    return parser, args


def test_opt_in_builds_generated_set() -> None:
    _, args = _parse(["--sentinel-count", "3", "--sentinel-seed", "600", "effect-demo"])
    generated = sentinel_set_from_args(args)
    assert generated is not None
    assert generated.generator_seed == 600
    assert len(generated.specs) == 3
    assert generated.describe() == generate_sentinel_set(600, 3).describe()


def test_no_flags_means_default_single_sentinel() -> None:
    _, args = _parse(["effect-demo"])
    assert sentinel_set_from_args(args) is None
    # demo_options never carries sentinel keys, so decompress/oras-go modes are untouched.
    assert "sentinel_set" not in demo_options(args)


def test_apply_record_is_noop_for_default() -> None:
    report: dict[str, object] = {"label": "demo run"}
    apply_sentinel_set_record(report, None)
    assert report == {"label": "demo run"}


def test_apply_record_adds_describe_for_opt_in() -> None:
    generated = generate_sentinel_set(600, 3)
    report: dict[str, object] = {}
    apply_sentinel_set_record(report, generated)
    assert report["sentinel_set"] == generated.describe()


@pytest.mark.parametrize(
    "argv",
    [
        ["--sentinel-count", "3", "--sentinel-seed", "1", "decompress-effect-campaign"],
        ["--sentinel-count", "3", "effect-demo"],
        ["--sentinel-seed", "1", "effect-demo"],
        ["--sentinel-count", "0", "--sentinel-seed", "1", "effect-demo"],
        ["--sentinel-count", "99", "--sentinel-seed", "1", "effect-demo"],
    ],
)
def test_invalid_flag_combinations_are_rejected(argv: list[str]) -> None:
    with pytest.raises(SystemExit):
        _parse(argv)


class _StopAfterCapture(RuntimeError):
    pass


def _patch_target(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    captured: dict[str, object] = {}

    def fake_bind(backend: object, image_id: object, profile: object = None) -> SimpleNamespace:
        return SimpleNamespace(tar_version="9.9.9-test", node_version="test")

    def fake_run(case: object, target: object, *, sentinels: tuple[SentinelSpec, ...]) -> object:
        captured["sentinels"] = sentinels
        raise _StopAfterCapture()

    monkeypatch.setattr(demo.NodeTarEffectTarget, "bind", fake_bind)
    monkeypatch.setattr(demo, "pinned_node_tar_version", lambda: "9.9.9-test")
    monkeypatch.setattr(demo, "run_node_tar_effect_case", fake_run)
    return captured


def test_native_run_threads_opt_in_sentinels(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _patch_target(monkeypatch)
    generated = generate_sentinel_set(600, 3)
    with pytest.raises(NativeDemoAborted):
        native_demo_report(
            cast(ExecutionBackend, object()), "image", budget=4, sentinel_set=generated
        )
    assert captured["sentinels"] == generated.specs


def test_native_run_defaults_to_single_sentinel(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _patch_target(monkeypatch)
    with pytest.raises(NativeDemoAborted):
        native_demo_report(cast(ExecutionBackend, object()), "image", budget=4)
    assert captured["sentinels"] == (SentinelSpec(),)
