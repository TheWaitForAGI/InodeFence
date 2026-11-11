"""Design v3 (two hosts) parsing: concurrency-scaling-v3.md section 2 and section 9.

The block below is the v3 file's machine block (main dfccedc) with
``probe_retry_max_attempts`` set to 1, the value this driver accepts (the
design correction goes through its own documentation PR).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts import run_concurrency_benchmark as bench

V3_BLOCK = """\
```concurrency-benchmark
design_id = concurrency-scaling-v3
target_version = 7.5.2
image_digest = sha256:22c8734f141d91b333ba37c7fe6a9a7547d7abfab487fa028da2053bed6f3dbb
budget = 2000
seeds = 8110, 8102, 8103, 8106
smoke_budget = 20
smoke_seed = 6100
vocabulary = observed-names
mutation_policy = uniform-generic-m1-state-aware-escape-hardlink-fixed-baseline-v1
arm.R-restart = unretained-seed-restart-v1-uniform-mutation-v1
arm.D = structure-coverage-v1-uniform-mutation-v1
arm.S-u = effect-feedback-v2-or-violation-v1-boundary-attempt-v1-uniform-mutation-v1
sentinel_generator_id = sentinel-names/seed-random-v1
sentinel_generator_seed = 20261104
sentinel_count = 5
observer_integrity_policy = invalid-continue
execution_mode = per-case-container
campaign_watchdog_seconds = 10800
disk_stop_fraction = 0.9
memory_stop_fraction = 0.1
stop_nonzero_cells = 6
preflight_load_fraction = 0.25
cooldown_seconds = 120
retry_max_attempts = 1
v10_monotonic_seconds = 7200
v10_realtime_seconds = 7200
x1_margin = 2
x1_incomparable_cells = 2
probe_seeds = 6200, 6201, 6202, 6203, 6204, 6205, 6206, 6207
probe_budget = 1000
probe_jobs = 4
probe_retry_max_attempts = 1
hosts = HOST1, HOST2
host.HOST1.run_prefix = h1
host.HOST1.docker_engine = TBD-PREFLIGHT
host.HOST2.run_prefix = h2
host.HOST2.docker_engine = TBD-PREFLIGHT
stage.smoke = 2
stage.A = 2,4,4,2
stage.B = 4,6,6,4
stage.C = 6,8,8,6
```
"""


def text(**changes: str | None) -> str:
    """The v3 block with keys replaced or added (``None`` removes a key)."""
    lines = []
    done: set[str] = set()
    for line in V3_BLOCK.splitlines():
        key = line.partition("=")[0].strip()
        if line == "```":
            # Keys the block does not have yet go in just before the closing fence.
            lines += [f"{k} = {v}" for k, v in changes.items() if k not in done and v is not None]
        if key in changes:
            done.add(key)
            if changes[key] is not None:
                lines.append(f"{key} = {changes[key]}")
            continue
        lines.append(line)
    return "\n".join(lines) + "\n"


def test_v3_block_parses_with_every_new_field() -> None:
    design = bench.parse_design(V3_BLOCK)
    assert design.is_v3
    assert design.hosts == {
        "HOST1": bench.HostSpec("h1", "TBD-PREFLIGHT"),
        "HOST2": bench.HostSpec("h2", "TBD-PREFLIGHT"),
    }
    assert design.docker_engine == ""
    assert design.retry_max_attempts == 1
    assert design.probe == bench.ProbeSpec(tuple(range(6200, 6208)), 1000, 4, 1)
    assert (design.v10_monotonic_seconds, design.v10_realtime_seconds) == (7200.0, 7200.0)
    assert (design.x1_margin, design.x1_incomparable_cells) == (2, 2)
    assert design.stages["A"] == (2, 4, 4, 2)


def test_v2_design_is_unchanged() -> None:
    design = bench.load_design(Path("experiments/configs/concurrency-scaling-v2.md"))
    assert not design.is_v3
    assert design.hosts == {}
    assert design.probe is None
    assert design.engine_for(None) == design.docker_engine != ""


def test_unresolved_engine_refuses_a_live_run_only() -> None:
    design = bench.parse_design(V3_BLOCK)  # parsing (plan, status) is allowed
    assert bench.unresolved_values(design, "HOST1") == [
        "host.HOST1.docker_engine = TBD-PREFLIGHT: pin it from a preflight first"
    ]
    pinned = bench.parse_design(text(**{"host.HOST1.docker_engine": "29.8.0"}))
    assert bench.unresolved_values(pinned, "HOST1") == []
    assert pinned.engine_for("HOST1") == "29.8.0"
    assert bench.unresolved_values(pinned, "HOST2") != []


def test_engine_for_requires_a_listed_host() -> None:
    design = bench.parse_design(V3_BLOCK)
    for host in (None, "HOST3"):
        with pytest.raises(bench.DesignError, match="--host must be one of"):
            design.engine_for(host)


@pytest.mark.parametrize("key", ["retry_max_attempts", "probe_retry_max_attempts"])
def test_only_a_single_attempt_is_accepted(key: str) -> None:
    with pytest.raises(bench.DesignError, match=f"{key} = 2: this driver runs each cell once"):
        bench.parse_design(text(**{key: "2"}))


def test_the_main_v3_file_value_two_is_refused_until_corrected() -> None:
    with pytest.raises(bench.DesignError, match="probe_retry_max_attempts = 2"):
        bench.parse_design(text(probe_retry_max_attempts="2"))


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"probe_seeds": "6199, 6200"}, "probe_seeds must be distinct and inside 6200-6207"),
        ({"probe_seeds": "6200, 6200"}, "probe_seeds must be distinct"),
        ({"probe_jobs": "0"}, "probe_jobs must be positive"),
        ({"host.HOST2.run_prefix": "h1"}, "must not share a run_prefix"),
        ({"host.HOST2.run_prefix": "H-2"}, "is not"),
        ({"host.HOST2.docker_engine": None}, "host HOST2 needs"),
        ({"host.HOST3.run_prefix": "h3"}, "unknown host key: host.HOST3.run_prefix"),
        ({"hosts": "HOST1, HOST1"}, "hosts must be distinct"),
        ({"x1_margin": None}, "missing \\['x1_margin'\\]"),
        ({"docker_engine": "29.8.0"}, "unknown \\['docker_engine'\\]"),
    ],
)
def test_v3_refusals(changes: dict[str, str | None], message: str) -> None:
    with pytest.raises(bench.DesignError, match=message):
        bench.parse_design(text(**changes))


def test_probe_seed_range_is_reserved_for_other_uses() -> None:
    # A measured or smoke seed inside the probe range is refused like any reserved seed.
    with pytest.raises(bench.DesignError, match="reserved range 6200-6207"):
        bench.parse_design(text(smoke_seed="6205", probe_seeds="6200, 6201"))
    with pytest.raises(bench.DesignError, match="reserved range 6200-6207"):
        bench.parse_design(text(seeds="8110, 8102, 8103, 6203"))


def test_v2_block_with_host_keys_is_refused() -> None:
    v2 = Path("experiments/configs/concurrency-scaling-v2.md").read_text(encoding="utf-8")
    broken = v2.replace("stage.smoke", "host.HOST1.run_prefix = h1\nstage.smoke", 1)
    with pytest.raises(bench.DesignError, match="unknown \\['host.HOST1.run_prefix'\\]"):
        bench.parse_design(broken)
