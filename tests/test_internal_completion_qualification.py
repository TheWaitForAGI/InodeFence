from scripts.qualify_node_internal_completion import assess_run, qualification_cases


def _run(profile: str, completion_sequence: list[int]) -> dict[str, object]:
    identities = [
        {"ordinal": 0, "path": "parent", "type": "Directory", "link_target": None},
        {
            "ordinal": 1,
            "path": "parent/child",
            "type": "File",
            "link_target": None,
        },
    ]
    events: list[dict[str, object]] = [
        {"phase": "archive_entry_read", "identity": identity} for identity in identities
    ]
    completed: set[int] = set()
    for ordinal in completion_sequence:
        completed.add(ordinal)
        paths = [
            {
                "path": "parent",
                "kind": "directory",
                "nlink": 2,
                "mode": 0o700,
                "size": 0,
                "link_target": None,
                "content_sha256": None,
            }
        ]
        if 1 in completed:
            paths.append(
                {
                    "path": "parent/child",
                    "kind": "regular",
                    "nlink": 1,
                    "mode": 0o644,
                    "size": 5,
                    "link_target": None,
                    "content_sha256": (
                        "ddc9e669194254cef019a29d3619a2c16592e76f010a39c0a30547d30c81208"
                    ),
                }
            )
        events.append(
            {
                "phase": "filesystem_effect_complete",
                "identity": identities[ordinal],
                "association_failure": None,
                "target_error": None,
                "completed_ordinals": sorted(completed),
                "snapshot": paths,
                "snapshot_error": None,
            }
        )
    final = events[-1]["snapshot"]
    return {
        "profile": profile,
        "status": "completed",
        "observation": {"events": events, "final_semantic_snapshot": final},
    }


def test_archive_order_snapshots_satisfy_current_transition_contract() -> None:
    case = qualification_cases()["directory-child"]

    assessment = assess_run(case, _run("snapshot", [0, 1]))

    assert assessment["qualified"] is True
    assert assessment["prefix_complete_at_each_callback"] == [True, True]


def test_out_of_order_completion_records_later_entry_contamination() -> None:
    case = qualification_cases()["directory-child"]

    assessment = assess_run(case, _run("snapshot", [1, 0]))

    assert assessment["qualified"] is False
    assert assessment["completion_sequence"] == [1, 0]
    assert {effect["kind"] for effect in assessment["future_effects"]} == {
        "later_entry_completed",
        "later_path_present",
    }
