# Empty result templates — NOT RESULTS

Do not infer zeros from empty cells. Fill only after the
[evaluation protocol](../../docs/research/benchmarks/evaluation-protocol-v1.md)
and experiment-validation review. This location holds planning templates;
validated small tables belong in summaries/ with raw URI/checksums and analysis
revision. Only reviewed evidence can be copied into paper/tables/.

## Benchmark inventory / qualification

The records below are copyable **placeholders, not observed zero-valued results**.
They are planning records, not accepted ExperimentConfig or ingestion schemas.
`expected_result` is a hypothesis from metadata; `observed_result` requires raw
evidence. Qualification status, execution status and evidence classification
(RAW ONLY / REPRODUCIBLE / VALIDATED FINDING / PAPER-READY EVIDENCE) are independent.

```yaml
benchmark_id: TBD
candidate_id: TBD
catalog_revision_sha256: TBD
qualification: PROPOSED
execution: NOT_RUN
gates:
  G1_source: TBD
  G2_exact_pin: TBD
  G3_semantics: TBD
  G4_reachability: TBD
  G5_execution: TBD
  G6_observation: TBD
  G7_expected_outcome: NOT_RUN
  G8_explicit_setup: TBD
expected_result: TBD
observed_result: NOT_RUN
qualification_evidence_refs: TBD
reviewer_and_review_revision: TBD
failed_gate_or_missing_prerequisite: TBD
```

| Benchmark | Class | Vulnerable pin/hash | Fixed pin/hash | Expected contracts | Linux qualification evidence | Admission status/reason |
| --- | --- | --- | --- | --- | --- | --- |

## Rediscovery results

Per-run record; an unstarted attempt remains NOT_RUN. An aborted attempted run
keeps its QUALIFICATION_ONLY/EVALUATION_RUN execution category with a separate
INCOMPLETE result classification, rather than an invented complete RunResult.
One run refers to a scheduled campaign;
one repetition is a benchmark/version/policy/RNG cell.

```yaml
dataset_id: TBD
run_id: TBD
attempt_id: TBD
benchmark_id: TBD
version_role: TBD
exact_target_pin_and_artifact_sha256: TBD
policy_id: TBD
config_id_and_config_artifact: TBD
protocol_revision_sha256: TBD
random_seed: TBD
execution_budget: TBD
timeout_seconds: TBD
execution: NOT_RUN
expected_result: TBD
observed_result: NOT_RUN
complete_step_count: TBD
first_confirmed_step_1_based: TBD
censor_flag_and_budget: TBD
unresolved_nomination_count: TBD
full_step_elapsed_seconds: TBD
process_status_counts: TBD
provenance_ref: TBD
raw_manifest_uri_and_sha256: TBD
failure_ledger_ref: N/A
evidence_classification: N/A
```

| Benchmark | Policy | Budget | Scheduled/complete/invalid | Confirmed/V | Wilson interval | Q1 / median / Q3 first-hit executions incl. censored | Full-step time-to-hit censor summary | Raw evidence |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |

## Vulnerable versus fixed behavior: identical-input replays

| Benchmark | Case ID / original step | TAR hash | Vulnerable matching replays /3 | Fixed matching replays /3 | Contracts/fields | Root-cause review | Classification/reason | Raw evidence |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |

## Baseline comparison

| Benchmark | B0/B1/B3 | Budget / RNG set | Complete/invalid | Success fraction | Censored first-hit quantiles | Full-v3 states | Fingerprints | Seed/end corpus | Policy-interest rate | Paired B3 difference/discordant seeds |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |

## Ablation comparison

| Benchmark/subset | A1/A2/A3 or control | Projection/policy ID | Budget / RNG set | Complete/invalid | Success fraction | Censored first-hit quantiles | Common full-v3 states | Policy-key diversity | Interpretation limits |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |

## Per-seed summary

| Benchmark | Version | Policy | RNG | Config/protocol ID | Complete results | Hit / no-hit / pending / invalid | Earliest confirmed 1-based step or >budget | Elapsed hit/censor seconds | Process statuses | Candidate/replay reference |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |

## Environment and provenance

| Dataset/campaign | Engine clean SHA | Target/runtime/dependency lock | Image/backend/profile | OS/kernel/arch | CPU/memory/resource limits | Filesystem/mount/devices | UID/GID/umask/hardlink policy | CWD/root mapping/sentinels | Grammar/seed/policy | UTC interval | Raw URI/checksum manifest / analysis SHA |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |

## Invalid / ambiguous attempt ledger

```yaml
attempt_id: TBD
planned_comparison_block: TBD
execution: NOT_RUN
failure_category: TBD
exclusion_reason: TBD
last_complete_step: TBD
exception_or_boundary_evidence_ref: TBD
retained_partial_evidence_uri_and_sha256: TBD
denominator_effect: TBD
resolution_and_review_ref: TBD
rerun_block_and_dataset_revision: N/A
```

| Campaign/attempt | Planned condition | Last complete step | Failure or ambiguous reason | Raw evidence retained | Block rerun/dataset revision | Resolution |
| --- | --- | --- | --- | --- | --- | --- |
