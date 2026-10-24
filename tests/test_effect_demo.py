import argparse
from dataclasses import replace
from typing import Any

import pytest
from scripts.compare_effect_policies import synthetic_policy_comparison
from scripts.run_effect_demo import (
    MAX_NATIVE_BUDGET,
    add_demo_arguments,
    check_demo_arguments,
    native_demo_report,
    pinned_node_tar_version,
    synthetic_demo_json,
    synthetic_demo_report,
)

from inodefence import effect_demo
from inodefence.effect_demo import (
    TRACE_LEGEND,
    _stderr_record,
    _trace_report,
    compare_effect_campaign_reports,
    render_effect_campaign_report,
    render_effect_trace,
)
from inodefence.effect_synthetic import synthetic_effect_result
from inodefence.feedback import EffectSearchPolicy
from inodefence.generator import minimal_seed_corpus
from inodefence.model import (
    EffectClass,
    EffectEvidenceStrength,
    EffectObjectObservation,
    EffectObservationStatus,
)
from inodefence.mutator import MutationPolicy


def test_synthetic_demo_json_is_byte_identical_for_same_seed() -> None:
    first = synthetic_demo_json(123, 20, EffectSearchPolicy.P2_EFFECT_ADAPTIVE, MutationPolicy.M1)
    second = synthetic_demo_json(123, 20, EffectSearchPolicy.P2_EFFECT_ADAPTIVE, MutationPolicy.M1)

    assert first == second


@pytest.mark.parametrize("budget", (0, MAX_NATIVE_BUDGET + 1, -1))
def test_native_demo_budget_cap_is_enforced_before_any_target_binding(budget) -> None:
    with pytest.raises(ValueError, match="budget"):
        native_demo_report(object(), "sha256:" + "0" * 64, budget=budget)  # type: ignore[arg-type]


def _demo_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    add_demo_arguments(parser)
    parser.add_argument("mode")
    return parser


def test_demo_arguments_are_restricted_to_effect_demo() -> None:
    parser = _demo_parser()
    args = parser.parse_args(["--seed", "7", "benign-node-smoke"])
    with pytest.raises(SystemExit):
        check_demo_arguments(parser, args)
    check_demo_arguments(parser, parser.parse_args(["--seed", "7", "effect-demo"]))
    check_demo_arguments(parser, parser.parse_args(["benign-node-smoke"]))


@pytest.mark.parametrize("budget", ("0", str(MAX_NATIVE_BUDGET + 1)))
def test_demo_argument_budget_cap(budget) -> None:
    parser = _demo_parser()
    with pytest.raises(SystemExit):
        check_demo_arguments(parser, parser.parse_args(["--budget", budget, "effect-demo"]))


def test_pinned_node_tar_version_reads_the_repository_pin() -> None:
    assert pinned_node_tar_version() == "7.5.22"


@pytest.mark.parametrize(
    "left", (EffectSearchPolicy.P1_EFFECT_RETENTION, EffectSearchPolicy.P0_FINAL_STATE)
)
def test_policy_comparison_is_byte_identical_for_same_input(left) -> None:
    def render() -> str:
        return render_effect_campaign_report(
            synthetic_policy_comparison(
                123, 20, MutationPolicy.M1, left, EffectSearchPolicy.P2_EFFECT_ADAPTIVE
            )
        )

    assert render() == render()


@pytest.mark.parametrize("seed", range(8))
def test_p1_p2_divergence_is_never_attributed_to_corpus_admission(seed) -> None:
    comparison = synthetic_policy_comparison(
        seed,
        40,
        MutationPolicy.M1,
        EffectSearchPolicy.P1_EFFECT_RETENTION,
        EffectSearchPolicy.P2_EFFECT_ADAPTIVE,
    )

    divergence = comparison["first_divergence"]
    if divergence is not None:
        assert isinstance(divergence, dict)
        assert divergence["source"] == "weights_feedback"
        assert divergence["first_corpus_difference_step"] is None


@pytest.mark.parametrize(
    "right_args",
    (
        (124, 20, EffectSearchPolicy.P2_EFFECT_ADAPTIVE, MutationPolicy.M1),
        (123, 21, EffectSearchPolicy.P2_EFFECT_ADAPTIVE, MutationPolicy.M1),
        (123, 20, EffectSearchPolicy.P2_EFFECT_ADAPTIVE, MutationPolicy.LEGACY),
    ),
)
def test_policy_comparison_rejects_differences_beyond_search_policy(right_args) -> None:
    left = synthetic_demo_report(123, 20, EffectSearchPolicy.P1_EFFECT_RETENTION, MutationPolicy.M1)

    with pytest.raises(ValueError, match="differ"):
        compare_effect_campaign_reports(left, synthetic_demo_report(*right_args))


def test_policy_comparison_rejects_a_different_producer() -> None:
    left = synthetic_demo_report(123, 20, EffectSearchPolicy.P1_EFFECT_RETENTION, MutationPolicy.M1)
    right = dict(left, producer="native")

    with pytest.raises(ValueError, match="producer"):
        compare_effect_campaign_reports(left, right)


_EVEN = {"a": 1, "b": 1}
_A_REWARDED = {"a": 2, "b": 1}


def _fixture_report(policy: str, mutations: list[tuple]) -> dict:
    """One retained seed `s0`, then (parent, operator, child, weights_before, retained, reward)."""
    steps: list[dict] = [
        {
            "index": 0,
            "case_id": "s0",
            "parent_case_id": None,
            "feedback": {"retained": True, "new_effect_keys": []},
            "scheduler_evidence": None,
        }
    ]
    for parent, operator, child, weights, retained, reward in mutations:
        after = dict(weights)
        after[operator] += reward
        steps.append(
            {
                "index": len(steps),
                "case_id": child,
                "parent_case_id": parent,
                "feedback": {"retained": retained, "new_effect_keys": [{"key": child}] * reward},
                "scheduler_evidence": {
                    "selected_operator_id": operator,
                    "weights_before": weights,
                    "selected_weight": weights[operator],
                    "reward": reward,
                    "weights_after": after,
                },
            }
        )
    return {
        "demo_report_schema": 1,
        "producer": "fixture",
        "initial_case_ids": ["s0"],
        "config": {
            "random_seed": 1,
            "execution_budget": len(steps),
            "search_policy": policy,
            "mutation_policy": "m",
        },
        "steps": steps,
    }


def test_identical_selections_do_not_diverge() -> None:
    mutations = [("s0", "a", "c1", _EVEN, False, 0), ("s0", "b", "c2", _EVEN, False, 0)]

    comparison = compare_effect_campaign_reports(
        _fixture_report("left", mutations), _fixture_report("right", mutations)
    )

    assert comparison["first_divergence"] is None
    assert comparison["operator_match_ratio"] == 1.0
    assert comparison["selection_match_ratio"] == 1.0


def test_divergence_after_reward_is_attributed_to_weights_feedback() -> None:
    left = _fixture_report(
        "uniform", [("s0", "a", "c1", _EVEN, True, 0), ("s0", "b", "c2", _EVEN, False, 0)]
    )
    right = _fixture_report(
        "adaptive", [("s0", "a", "c1", _EVEN, True, 1), ("s0", "a", "c3", _A_REWARDED, False, 0)]
    )

    comparison = compare_effect_campaign_reports(left, right)

    divergence = comparison["first_divergence"]
    assert isinstance(divergence, dict)
    assert divergence["step"] == 2
    assert divergence["immediate_difference"] == "weights"
    assert divergence["source"] == "weights_feedback"
    assert comparison["operator_match_ratio"] == 0.5
    assert comparison["feedback_events"] == {
        "left": [],
        "right": [
            {
                "index": 1,
                "selected_operator_id": "a",
                "new_effect_key_count": 1,
                "reward": 1,
                "selected_weight_before": 1,
                "selected_weight_after": 2,
            }
        ],
    }


@pytest.mark.parametrize(
    ("right_second", "immediate"),
    (
        (("c1", "b", "c3", _EVEN, False, 0), "parent"),
        (("s0", "a", "c3", _EVEN, False, 0), "rng_desync"),
    ),
)
def test_divergence_after_admission_difference_is_attributed_to_corpus(
    right_second, immediate
) -> None:
    left = _fixture_report(
        "final-state", [("s0", "a", "c1", _EVEN, False, 0), ("s0", "b", "c2", _EVEN, False, 0)]
    )
    right = _fixture_report("effect", [("s0", "a", "c1", _EVEN, True, 0), right_second])

    divergence = compare_effect_campaign_reports(left, right)["first_divergence"]

    assert isinstance(divergence, dict)
    assert divergence["step"] == 2
    assert divergence["immediate_difference"] == immediate
    assert divergence["source"] == "corpus_admission"
    assert divergence["first_corpus_difference_step"] == 2


def _synthetic_hardlink_result():
    return synthetic_effect_result(minimal_seed_corpus()[2])


def test_effect_trace_marks_synthetic_and_labels_each_value_origin() -> None:
    result = _synthetic_hardlink_result()
    lines = render_effect_trace(result).splitlines()

    assert lines[0].startswith("SYNTHETIC — 관찰값 아님")
    assert lines[1].startswith("extractor: synthetic 1")
    for label, _ in TRACE_LEGEND:
        assert sum(line.startswith(f"  [{label}] ") for line in lines) == 1
    entries = [line for line in lines if line.startswith("entry ")]
    assert entries == [
        "entry 0 [archive] path=a.txt type=regular",
        "entry 1 [archive] path=b.txt type=hardlink link=a.txt",
    ]
    assert "  [*·SYNTHETIC] synthetic producer가 만든 값. 실제 관찰·분류 아님." in lines
    assert (
        "    path extract/object-1 before [observed·SYNTHETIC] absent "
        "-> after [observed·SYNTHETIC] present regular dev:ino 7:101"
    ) in lines
    assert (
        "    [derived·SYNTHETIC] class=hardlink_identity_relation_creation "
        "strength=identity_verified"
    ) in lines
    assert "  effect seq 6-7 [observed·SYNTHETIC] op=link outcome=succeeded" in lines
    # Outside the legend, no producer-made value carries an unmarked label.
    body = lines[lines.index("legend:") + len(TRACE_LEGEND) + 2 :]
    assert not any(
        f"[{name}]" in line for line in body for name in ("observed", "not_observed", "derived")
    )


def test_effect_trace_prints_not_observed_and_operation_result_without_values() -> None:
    result = _synthetic_hardlink_result()
    event = result.trace.effect_events[0]
    (evidence,) = event.object_evidence
    unobserved = replace(
        event,
        effect_class=EffectClass.OPERATION_OBSERVED,
        evidence_strength=EffectEvidenceStrength.OPERATION_RESULT,
        object_evidence=(
            replace(
                evidence,
                after=EffectObjectObservation(EffectObservationStatus.NOT_OBSERVED, None),
            ),
        ),
    )
    trace = replace(result.trace, effect_events=(unobserved, *result.trace.effect_events[1:]))
    rendered = render_effect_trace(replace(result, trace=trace))

    assert "    [derived·SYNTHETIC] class=operation_observed strength=operation_result" in rendered
    assert (
        "    path extract/object-0 before [observed·SYNTHETIC] absent "
        "-> after [not_observed·SYNTHETIC]\n"
    ) in rendered


def test_effect_trace_has_no_synthetic_header_for_other_sources() -> None:
    result = _synthetic_hardlink_result()
    source = replace(result.trace.provenance.sources[0], mechanism="other-test")
    provenance = replace(result.trace.provenance, sources=(source,))
    trace = replace(result.trace, provenance=provenance)
    rendered = render_effect_trace(replace(result, trace=trace))

    assert "SYNTHETIC" not in rendered
    assert rendered.startswith("extractor: synthetic 1")
    assert "  effect seq 6-7 [observed] op=link outcome=succeeded\n" in rendered
    assert "    [derived] class=hardlink_identity_relation_creation" in rendered


def _p2_steps() -> list[dict[str, Any]]:
    report: dict[str, Any] = synthetic_demo_report(
        123, 20, EffectSearchPolicy.P2_EFFECT_ADAPTIVE, MutationPolicy.M1
    )
    assert report["demo_report_schema"] == 2
    return report["steps"]


def test_demo_report_step_carries_synthetic_trace_and_stderr() -> None:
    steps = _p2_steps()

    for step in steps:
        trace = step["trace"]
        assert trace["synthetic"] is True
        assert trace["sources"] == [
            {"source_id": "synthetic", "mechanism": "synthetic-test", "version": "1"}
        ]
        assert trace["effect_events_truncated"] is False
        assert len(trace["effect_events"]) == trace["effect_events_total"]
        assert (
            sum(entry["effect_event_count"] for entry in trace["entries"])
            == (trace["effect_events_total"])
        )
        assert step["target_stderr"] == {"text": "", "chars": 0, "truncated": False}
    hardlink = steps[2]["trace"]
    assert [(entry["path"], entry["type"]) for entry in hardlink["entries"]] == [
        ("a.txt", "regular"),
        ("b.txt", "hardlink"),
    ]
    link = hardlink["effect_events"][1]
    assert {key: link[key] for key in ("entry_index", "operation", "outcome", "association")} == {
        "entry_index": 1,
        "operation": "link",
        "outcome": "succeeded",
        "association": "async_context",
    }
    assert link["paths"][1] == {
        "path": "extract/object-1",
        "before": {"status": "absent"},
        "after": {
            "status": "present",
            "object_type": "regular",
            "st_dev": 7,
            "st_ino": 101,
            "st_nlink": 1,
            "size": 1,
        },
    }


def test_demo_report_selection_splits_admission_and_weight_channels() -> None:
    steps = _p2_steps()
    corpus: list[str] = []
    rewarded = admitted = 0

    for step in steps:
        selection = step["selection"]
        evidence = step["scheduler_evidence"]
        if evidence is None:
            assert selection is None
        else:
            assert selection["parent_case_id"] == step["parent_case_id"] in corpus
            assert selection["selected_operator_id"] == evidence["selected_operator_id"]
            assert selection["selected_weight"] == evidence["selected_weight"]
            assert selection["new_effect_key_count"] == len(step["feedback"]["new_effect_keys"])
            assert selection["corpus_admission"] == {
                "corpus_size_before": len(corpus),
                "retained": step["feedback"]["retained"],
            }
            weights = selection["operator_weights"]
            assert weights == {
                "weights_before": evidence["weights_before"],
                "reward": evidence["reward"],
                "weights_after": evidence["weights_after"],
            }
            rewarded += weights["reward"]
            admitted += step["feedback"]["retained"]
        if step["feedback"]["retained"]:
            corpus.append(step["case_id"])

    assert rewarded and admitted


def test_trace_report_keeps_not_observed_apart_from_missing_evidence() -> None:
    result = _synthetic_hardlink_result()
    first, second = result.trace.effect_events
    (evidence,) = first.object_evidence
    unobserved = replace(
        first,
        object_evidence=(
            replace(
                evidence,
                after=EffectObjectObservation(EffectObservationStatus.NOT_OBSERVED, None),
            ),
        ),
    )
    trace = replace(result.trace, effect_events=(unobserved, replace(second, object_evidence=())))
    report: dict[str, Any] = _trace_report(replace(result, trace=trace))
    events = report["effect_events"]

    assert events[0]["paths"] == [
        {
            "path": "extract/object-0",
            "before": {"status": "absent"},
            "after": {"status": "not_observed"},
        }
    ]
    assert [path["before"] for path in events[1]["paths"]] == [None, None]
    assert [path["after"] for path in events[1]["paths"]] == [None, None]


def test_trace_report_is_not_synthetic_for_other_sources() -> None:
    result = _synthetic_hardlink_result()
    source = replace(result.trace.provenance.sources[0], mechanism="other-test")
    provenance = replace(result.trace.provenance, sources=(source,))
    trace = replace(result.trace, provenance=provenance)

    assert _trace_report(replace(result, trace=trace))["synthetic"] is False


def test_trace_report_caps_effect_events_and_states_the_cut(monkeypatch) -> None:
    monkeypatch.setattr(effect_demo, "MAX_TRACE_EFFECT_EVENTS", 1)
    report: dict[str, Any] = _trace_report(_synthetic_hardlink_result())

    assert [event["operation"] for event in report["effect_events"]] == ["open"]
    assert report["effect_events_total"] == 2
    assert report["effect_events_truncated"] is True
    assert [entry["effect_event_count"] for entry in report["entries"]] == [1, 1]


def test_stderr_record_keeps_head_and_tail_with_omission_marker() -> None:
    edge = effect_demo.STDERR_EDGE_CHARS
    whole = "h" * edge + "m" * 500 + "t" * edge
    record = _stderr_record(whole)

    assert record["chars"] == len(whole)
    assert record["truncated"] is True
    assert record["text"] == "h" * edge + "\n[... 500 chars omitted ...]\n" + "t" * edge
    assert _stderr_record("x" * 2 * edge) == {
        "text": "x" * 2 * edge,
        "chars": 2 * edge,
        "truncated": False,
    }
