# EXP-0 pilot summary

_Infrastructure measurement only (prereg v2); observed counts, not an H-A test or an effectiveness claim. An unregistered G1-smoke run is tool verification, not a paper claim._

Cells: 15 (valid 15, invalid 0); arms: D, R, S-u.

## Aborts by reason and arm (denominator = cells in arm)

| arm | cells | complete | abort | invalid | observer_integrity | broker | cleanup_inspect | cleanup_remove | cleanup_reset | other | abort_frac |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| D | 5 | 5 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.000 |
| R | 5 | 5 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.000 |
| S-u | 5 | 5 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.000 |

## First C0/C1/C2 index and combined T_first (right-censored)

| arm | metric | observed | censored | km_median | risk_set_n |
| --- | --- | --- | --- | --- | --- |
| D | C0 | 0 | 5 | None | 5 |
| D | C1 | 0 | 5 | None | 5 |
| D | C2 | 0 | 5 | None | 5 |
| D | T_first | 0 | 5 | None | 5 |
| R | C0 | 0 | 5 | None | 5 |
| R | C1 | 0 | 5 | None | 5 |
| R | C2 | 0 | 5 | None | 5 |
| R | T_first | 0 | 5 | None | 5 |
| S-u | C0 | 0 | 5 | None | 5 |
| S-u | C1 | 0 | 5 | None | 5 |
| S-u | C2 | 0 | 5 | None | 5 |
| S-u | T_first | 0 | 5 | None | 5 |

## Dense signals per arm (denominator = valid cells / executions)

| arm | boundary_keys | mean/cell | rejected | executions | rejected_ratio | u_viol | u_viol_c0 | obs_fail |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| D | 10 | 2.0 | 477 | 1000 | 0.477 | 0 | 0 | 8 |
| R | 2 | 0.4 | 976 | 1000 | 0.976 | 0 | 0 | 0 |
| S-u | 9 | 1.8 | 360 | 1000 | 0.36 | 0 | 0 | 3 |

_boundary_keys is a per-cell sum, not a count of unique keys (deviation 4 of experiments/summaries/exp0-20261105-report.md)._

## Full-step time distribution (pooled, seconds; nearest-rank)

p50 1.4880454699996335 | p95 1.5489997629993013 | max 1.7028755140017893 over 3000 steps.

_p50, p95 and max are monotonic-clock recorded values; real-time conversions of p50 and p95 are in deviation 1 of experiments/summaries/exp0-20261105-report.md._

## Hazard proxy (reference value only, not a verdict)

| arm | hit_steps | executions | proxy/exec |
| --- | --- | --- | --- |
| D | 0 | 1000 | 0.0 |
| R | 0 | 1000 | 0.0 |
| S-u | 0 | 1000 | 0.0 |

Zero-hit: prereg v2 (a): campaign-unit rule-of-three is primary; execution-unit exploratory
| arm | campaign_n | rule_of_three_upper95 | exec_n | exec_upper95 (exploratory) |
| --- | --- | --- | --- | --- |
| D | 5 | 0.6 | 1000 | 0.003 |
| R | 5 | 0.6 | 1000 | 0.003 |
| S-u | 5 | 0.6 | 1000 | 0.003 |

## Environment (provenance)

homogeneous: True; docker_server_version=29.8.0, host_machine=x86_64, host_release=6.18.33.2-microsoft-standard-WSL2, host_system=Linux, image_id=sha256:22c8734f141d91b333ba37c7fe6a9a7547d7abfab487fa028da2053bed6f3dbb, node_tar_version=7.5.2, node_version=22.22.0, recipe_sha256=None
