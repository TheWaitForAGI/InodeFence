"""#536 FAST option 1 wiring: six launch-path files differ from main only by approved lines.

D064 (Jiwoong 2026-11-18: "방안 1 승인", "배선 승인", "2하자"): three files on
SHARED_PATH_FILES (scripts/launcher_guards.py) and the other three targets' launchers gain the
lines below to pass ``--identity-check-every`` from the
launchers to the controller and back the identity-check record into the loop report, within the
approved caps (run_effect_demo.py +9, container_controller.py +7, each launcher +1, deletions 0).
Nothing else in these files may change: with exactly these lines removed, each file must hash to
its main fccdf35 blob, the baseline the lane B shared-path check uses. Without the value nothing
is passed, so STRICT runs keep today's argument lists (pinned by the targets' own tests).

Decision A (#542, Jiwoong 2026-11-19 "결정 A 승인"): container_controller.py streams the decompress
and oras-go campaigns into the report collectors, and run_effect_demo.py lifts the budget cap for
those two modes (caps: container_controller.py 12 lines added incl. replacements, 6 changed;
run_effect_demo.py 1 added, 1 changed). Its additions are in ``APPROVED`` with D064's; its changed
lines are in ``CHANGED`` as (new, old) pairs. Reversing those pairs and removing the added lines
must give the main fccdf35 blob, so nothing else in these files has changed either.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
#: The baseline commit (main fccdf35); its blobs are pinned below by sha256 and line count.
BASELINE = "fccdf35"
_IMPORT = (
    "from inodefence.targets.identity_schedule import apply_identity_schedule, "
    "finish_identity_schedule\n"
)
_LAUNCHER = (
    '[ -n "${DEMO_IDENTITY_CHECK_EVERY:-}" ] && '
    'DEMO_ARGS+=(--identity-check-every "$DEMO_IDENTITY_CHECK_EVERY")\n'
)
_APPLY_ARGS = (
    "    target, schedule = apply_identity_schedule(target, "
    'getattr(args, "identity_check_every", None))\n'
)
_FINISH_REPORT = "        report.update(finish_identity_schedule(target, schedule))\n"
_A_HOOKS_IMPORT = "    from inodefence.campaign_hooks import CampaignHooks\n"
_A_HOOKS = "    hooks = CampaignHooks(on_step=collector.add, retain_steps=False)\n"
_A_REPORT = "        report = collector.report(result)\n"

#: path -> (sha256 of the BASELINE blob, the approved added lines in file order)
APPROVED: dict[str, tuple[str, tuple[str, ...]]] = {
    "scripts/run_effect_demo.py": (
        "0245d380fbcbf93b77b7d481fece4a65315b624e7b8e9b3f7b8b64a3e0adbf45",
        (
            _IMPORT,
            "UNCAPPED_BUDGET_MODES = (EXPLORE_DEMO_MODE, DECOMPRESS_CAMPAIGN_MODE, "
            "ORAS_GO_CAMPAIGN_MODE)  # #542\n",
            '    "identity_check_every",\n',
            '    parser.add_argument("--identity-check-every", type=int)'
            "  # FAST explore only (#536)\n",
            '    if getattr(args, "identity_check_every", None) is not None:\n',
            '        options["identity_check_every"] = args.identity_check_every\n',
            "    identity_check_every: int | None = None,\n",
            "    target, schedule = apply_identity_schedule(target, identity_check_every)\n",
            "        identity_record = finish_identity_schedule(target, schedule)\n",
            "    report.update(identity_record)\n",
        ),
    ),
    "scripts/container_controller.py": (
        "82427127c5943e5de7918dd3fdfded976b89ab3d8f7520e9a1507ed59cacdbd8",
        (
            _IMPORT,
            _A_HOOKS_IMPORT,
            _APPLY_ARGS,
            '    collector = DecompressReportCollector(producer=producer, label="demo run")'
            "  # #542 streaming\n",
            _A_HOOKS,
            _FINISH_REPORT,
            _A_HOOKS_IMPORT,
            _APPLY_ARGS,
            '    collector = OrasGoReportCollector(producer=producer, label="demo run")'
            "  # #542 streaming\n",
            _A_HOOKS,
            _FINISH_REPORT,
        ),
    ),
    "scripts/local_node_tar_smoke.sh": (
        "21c8facf734590abbedfa88cbf2fedc657a29377ea49274e93f00590c6c2994e",
        ("  " + _LAUNCHER,),
    ),
    "scripts/local_python_tarfile_explore.sh": (
        "8be437f8cc64228c1aeadcff08ddd01b4d622ca3d299be738e768c2e8ae6c1ed",
        (_LAUNCHER,),
    ),
    "scripts/local_decompress_selfdiscover.sh": (
        "9a62788da720b72f4c8e0a791e25293fb5db74a39bccccd4d14256544a98d314",
        (_LAUNCHER,),
    ),
    "scripts/local_oras_go_selfdiscover.sh": (
        "8c238120e49a8f82d1fd0a715f974f0d9adbfe9a5c6b0083aeb0e62f71c27ff6",
        (_LAUNCHER,),
    ),
}
#: Decision A's changed lines, in file order: (the line now, the baseline line it replaced).
CHANGED: dict[str, tuple[tuple[str, str], ...]] = {
    "scripts/run_effect_demo.py": (
        (
            "        if args.mode not in UNCAPPED_BUDGET_MODES "
            "and args.budget > MAX_NATIVE_BUDGET:\n",
            "        if args.mode != EXPLORE_DEMO_MODE and args.budget > MAX_NATIVE_BUDGET:\n",
        ),
    ),
    "scripts/container_controller.py": (
        ("        DecompressReportCollector,\n", "        decompress_effect_campaign_report,\n"),
        (
            "        result = run_decompress_effect_campaign("
            "minimal_seed_corpus(), produce, config, hooks=hooks)\n",
            "        result = run_decompress_effect_campaign("
            "minimal_seed_corpus(), produce, config)\n",
        ),
        (
            _A_REPORT,
            "        report = decompress_effect_campaign_report(result, producer=producer, "
            'label="demo run")\n',
        ),
        ("        OrasGoReportCollector,\n", "        oras_go_effect_campaign_report,\n"),
        (
            "        result = run_oras_go_effect_campaign("
            "minimal_seed_corpus(), produce, config, hooks=hooks)\n",
            "        result = run_oras_go_effect_campaign("
            "minimal_seed_corpus(), produce, config)\n",
        ),
        (
            _A_REPORT,
            "        report = oras_go_effect_campaign_report(result, producer=producer, "
            'label="demo run")\n',
        ),
    ),
}
#: Decision A's caps per file: (lines added, counting replacements as added as
#: `git diff --numstat` does; lines changed).
DECISION_A_CAPS = {
    "scripts/run_effect_demo.py": (1 + 1, 1),
    "scripts/container_controller.py": (12, 6),
}
#: Decision A's pure additions per file (the rest of its lines are the CHANGED replacements).
DECISION_A_ADDED = {"scripts/run_effect_demo.py": 1, "scripts/container_controller.py": 6}
#: The approved caps (lines added: D064's plus decision A's pure additions).
CAPS = {
    "scripts/run_effect_demo.py": 9 + 1,
    "scripts/container_controller.py": 7 + 6,
    "scripts/local_node_tar_smoke.sh": 1,
    "scripts/local_python_tarfile_explore.sh": 1,
    "scripts/local_decompress_selfdiscover.sh": 1,
    "scripts/local_oras_go_selfdiscover.sh": 1,
}


SHARED = (
    "scripts/run_effect_demo.py",
    "scripts/container_controller.py",
    "scripts/local_node_tar_smoke.sh",
)


def test_the_six_files_are_the_launch_path_and_within_the_caps() -> None:
    from scripts import launcher_guards

    from inodefence.drivers.launcher import launcher_path

    assert set(SHARED) <= set(launcher_guards.SHARED_PATH_FILES)
    launchers = {
        launcher_path(target, ROOT).relative_to(ROOT).as_posix()
        for target in ("node-tar", "python-tarfile", "decompress", "oras-go")
    }
    assert set(APPROVED) == set(SHARED) | launchers
    assert "scripts/container_host.py" not in APPROVED  # approved at 0 lines
    for path, (_, added) in APPROVED.items():
        assert len(added) <= CAPS[path], path
    assert set(CHANGED) == set(DECISION_A_CAPS) <= set(APPROVED)
    for path, (cap_added, cap_changed) in DECISION_A_CAPS.items():
        changed = len(CHANGED[path])
        assert changed <= cap_changed, path
        assert DECISION_A_ADDED[path] + changed <= cap_added, path


def _restored(path: str) -> list[str]:
    """The file with decision A's changed lines put back to their baseline text, in order."""
    pairs = list(CHANGED.get(path, ()))
    lines = (ROOT / path).read_text(encoding="utf-8").splitlines(keepends=True)
    out, matched = [], 0
    for line in lines:
        if matched < len(pairs) and line == pairs[matched][0]:
            out.append(pairs[matched][1])
            matched += 1
        else:
            out.append(line)
    assert matched == len(pairs), f"{path}: changed lines not found in order"
    return out


@pytest.mark.parametrize("path", sorted(APPROVED))
def test_only_the_approved_lines_differ_from_the_baseline(path: str) -> None:
    baseline_sha256, added = APPROVED[path]
    current = _restored(path)
    assert [line for line in current if line in added] == list(added), path
    stripped = "".join(line for line in current if line not in added)
    assert hashlib.sha256(stripped.encode("utf-8")).hexdigest() == baseline_sha256, path


#: Line count of each BASELINE blob, so the additions-only check needs no git history (a shallow
#: CI checkout has none; a check that skips there is no evidence -- W4, CI 44228097180).
BASELINE_LINES = {
    "scripts/run_effect_demo.py": 1209,
    "scripts/container_controller.py": 907,
    "scripts/local_node_tar_smoke.sh": 539,
    "scripts/local_python_tarfile_explore.sh": 129,
    "scripts/local_decompress_selfdiscover.sh": 150,
    "scripts/local_oras_go_selfdiscover.sh": 151,
}


def test_every_file_has_a_complete_baseline() -> None:
    # A missing or malformed baseline fails here instead of being skipped.
    assert set(BASELINE_LINES) == set(APPROVED)
    for path, (baseline_sha256, added) in APPROVED.items():
        assert len(baseline_sha256) == 64 and int(baseline_sha256, 16) >= 0, path
        assert added and all(line.endswith("\n") for line in added), path
        assert BASELINE_LINES[path] > 0, path


@pytest.mark.parametrize("path", sorted(APPROVED))
def test_the_diff_is_additions_only_without_git_history(path: str) -> None:
    # With the previous test (the rest hashes to the baseline blob) this pins the whole diff:
    # every removed-for-the-check line is one of the approved lines, each counted exactly as
    # approved (no baseline line equal to an approved line was dropped, none was added twice),
    # and nothing was deleted.
    _, added = APPROVED[path]
    new = _restored(path)  # decision A's changed lines replace baseline lines one for one
    kept = [line for line in new if line not in added]
    assert len(kept) == BASELINE_LINES[path], path
    assert len(new) - BASELINE_LINES[path] == len(added), path
