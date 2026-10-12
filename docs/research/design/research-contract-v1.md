# Research Contract v1 — G0 documentation freeze

Freeze date: **2026-10-06**. Capability baseline: main
**`8ad07b8e5f23f789d57ea50ba52c7acfcee951ea`**. This is the source revision
reviewed for this contract, not the eventual documentation PR commit or a moving
alias for future main. [STATUS](../../STATUS.md) records the current capability
and evidence map. Earlier audits and engineering summaries retain their original
revisions and measurements; they do not define present implementation status.

This contract closes the documentation requirements of **G0** when reviewed and
accepted. It does not promote G1–G7, qualify any historical target, freeze the
main-experiment schedule, or authorize vulnerability discovery. The minimum
research outcome is a reproducible evaluation of what InodeFence detects and
misses against declared comparisons. A new vulnerability is a stretch outcome.

## Evidence vocabulary and present claim boundary

| Label | Meaning |
| --- | --- |
| DESIGNED | A definition, hypothesis or protocol exists; code/execution need not exist |
| IMPLEMENTED | The baseline has an executable code path; existence alone does not establish correctness |
| TESTED | Named tests or retained engineering checks exercise that capability, within stated limits |
| EXPERIMENTALLY VALIDATED | Qualified targets, frozen conditions, repeated comparisons and retained raw evidence support the particular research claim |

The levels are recorded separately. Synthetic tests and a benign extractor smoke
are TESTED engineering evidence, not EXPERIMENTALLY VALIDATED rediscovery or
feedback effectiveness. At this freeze, **no historical vulnerability has been
rediscovered, no comparative effectiveness result is claimed, and no vulnerability
is currently claimed**. Source-derived expected effects are hypotheses.

## Research question, threat model and security boundary

The [research questions](research-questions.md) test whether generic TAR-entry
mutation guided by filesystem security states explores meaningful persistent
states and violations more effectively than B0/B1, and which A1/A2/A3 components
contribute. Novelty remains a hypothesis informed by
[related-work positioning](related-work-positioning.md).

The attacker supplies an untrusted single TAR to an extractor operating on a
fresh empty extraction directory. Attacker-controlled logical inputs are entry
path spelling, link targets, supported type, order, duplicate names and regular
file bytes/mode within the model/builder bounds. The current eight mutation slots
do not edit every modeled field (e.g. existing content/mode). The target version,
worker/options, images, limits, runtime layout, sentinel contents/paths and initial
benign corpus are researcher-controlled, frozen conditions, not attacker knobs.

The protected boundary is the designated extraction root and the controlled
external sentinel objects in the same disposable runtime. A runtime directory is
not OS isolation. Third-party execution requires the validated container backend,
with the disposable run as the only writable persistent volume and declared
container tmpfs scratch space; controller/host secrets are never experimental targets. The Linux runtime volume is separate from the source bind
mount. Actual image/invocation and target-visible mappings require evidence for
each admitted target. Container engineering checks do not prove arbitrary
extractor compatibility, kernel safety or historical benchmark qualification.

[Security Contracts](security-contracts.md) are canonical:

- C0: detect persistent namespace creation/deletion/identity or type replacement
  outside the extraction root **within the observed sandbox**, including HARNESS.
- C1: detect post-extraction lstat `(st_dev, st_ino)` equality between extraction
  objects and designated protected external sentinels.
- C2: detect designated sentinel changes between BEFORE/AFTER: existence, type,
  identity, digest, size, mode, nlink, ownership and mtime/ctime; exclude atime.

These are persistent-snapshot detectors. They miss transient effects, accesses
outside the observed sandbox, unchanged direct-use and symlink referent identity.
They cannot establish check/use coherence or distinguish inode reuse between
captures. Attribution depends on a stopped extractor and no harness namespace
writes between snapshots. `violated=False` proves only absence of observed
contract evidence. Signature normalization does not expand or narrow the oracle
boundary. C3/C4 remain DESIGNED and outside this freeze's implementation scope.

Initial scope is Linux TAR/USTAR with regular files, directories and link entries,
fresh extraction state and controlled external sentinels. Windows semantics,
races/full tracing, reused multi-archive sessions, PAX/GNU parser ambiguity and
additional formats are excluded. This freeze adds no adapters or mutation rules.

## Targets and qualification order

The executable research adapter is contained **node-tar 7.5.22**, with benign
full-path engineering evidence. Python tarfile/data is a trusted architecture
reference. The GNU evaluation invocation is limited to four allowlisted benign
fixtures; it is not an arbitrary-input historical fuzzing target. No ORAS adapter
exists. Existing source-selected Node/ORAS/GNU candidates remain planning metadata,
not a mandate to implement additional targets or proof of generality.

**N01 node-tar 7.5.2 / 7.5.3 is the first intended historical qualification
pair.** Admit only the selected hardlink arm after exact artifacts/locks, options,
Linux same-device controlled setup, generation reachability and independent
expected-effect/fixed-comparator evidence are validated. The M1 finite vocabulary
cannot spell the default `outside/sentinel.txt`; composition support alone does
not establish that reachability. Any qualification profile must document this
constraint rather than introduce a CVE recipe or silently alter the oracle.

Use [Benchmark Set v1](../benchmarks/benchmark-set-v1.md) for admission rules and
[catalog](../../../experiments/benchmarks/README.md) for source pins/uncertainties.
All 15 static catalog executions remain **NOT_RUN**; none is READY. N03/N04 and
cross-implementation candidates are conditional later work. RQ4 is unproven until
a separately qualified second extractor family has comparable evidence.

## Executable comparisons and methodology

The exact executable comparison is **B0/B1/B3 and A1/A2/A3**, via
`run_search_campaign` / `SearchCampaignConfig`. B0 is an unretained multi-step
random walk; B1 admits unseen full state keys; B3 admits unseen state keys OR
violation fingerprints. B0 changes parent selection and retention together.
A1 removes identity groups from admission keys only; A2 removes external-effect
labels only; A3 replaces the reorder slot with a draw-preserving executed no-op.
Other identity/effect signals and order changes remain, so these are narrow
ablations. There is **no executable path-only or fixed-recipe comparator** and
neither is part of the frozen RQ2/RQ3 claim. B2 is unimplemented and excluded.

[Baselines and ablations](../benchmarks/baseline-and-ablation-v1.md) define policy
IDs and interpretation. Legacy `ExperimentConfig` v1/v2 still supports only
B3/legacy mutation; the separate `PolicyEvaluationConfig` binds completed policy
results. Reader integrity/admission checks do not prove actual RNG execution,
mutation provenance, qualification or rediscovery.

Follow the required order without compensating for missing validation by longer
campaigns:

Research Question → Threat Model → Security Invariant → Oracle Validation →
Harness Validation → Fuzzer Validation → Synthetic Tests → Historical/Known Case
Validation → Pilot Experiment → Experiment Freeze → Main Experiments → Candidate
Triage → Analysis → Paper → Independent Reproduction.

The [evaluation protocol](../benchmarks/evaluation-protocol-v1.md) defines
paired benign initial corpora, common mutation/setup/limits, deterministic seeds,
independent repetitions and all-status seed-inclusive budgets. Its numeric
budgets/subsets are provisional planning parameters. Pilot feasibility and
qualification must precede the separate experiment freeze; amendments must be
recorded before formal results, not selected after favorable outcomes. Preserve
negative results, timeouts, failed qualification and incomplete attempts.

Report unique full semantic states, generic fingerprints, first observed contract
index, status counts, corpus growth and throughput with explicit denominators.
Confirmed known-class rediscovery additionally needs 3/3 fresh affected replays,
0/3 matching fixed replays and human root-cause correspondence. First contract
observation is not first confirmed rediscovery. No-hit is right-censored, never a
fictitious hit at budget end. Full-pipeline timing and automatic interrupted-run
preservation are not supplied by the current policy runner; target duration and
completed-only statistics must not be substituted for those measurements.

## Reproducibility and disclosure

Every experiment must retain engine SHA; target version/commit/artifact locks;
OS/kernel/runtime/architecture/filesystem; exact worker/command/options and image;
configuration, initial corpus, RNG seed, budget/timeout, oracle/feedback/mutation
IDs; start/end timestamps; schedule/protocol revision; raw path/shared storage URI
and checksums. Freeze actual provenance before execution. Checksums provide
integrity, not authorship. Dirty patches and undeclared profiles are insufficient.

Raw data are immutable and never manually edited. Analysis creates separate,
versioned derivatives: raw data → validation/analysis script → figure/table →
paper claim. [Experiments](../../../experiments/README.md) describe the implemented
readers, passive journal/ledger and their attachment limits. A clean-checkout
independent reproduction must verify exact inputs/TAR hashes, fresh environments
and expected observations before final artifact acceptance. No formal dataset
or publication figure pipeline has been validated at this freeze.

A violation is a candidate, not a vulnerability. Under [SECURITY](../../../SECURITY.md),
private triage requires deterministic and clean-environment replay, latest
supported stable verification, minimization, before/after state, impact/boundary
analysis, documented-behavior review, affected-version/root-cause evidence and a
regression test, followed by a private disclosure package. Do not publish
potentially unpatched candidates in public issues, branches or CI logs.

## G0 authority map and remaining uncertainty

| G0 requirement | Canonical definition |
| --- | --- |
| RQs / hypotheses | [Research questions](research-questions.md) |
| Threat model / controlled inputs / boundary / scope | This contract; [architecture](architecture.md) |
| Invariants / C0/C1/C2 / observation limits | [Security Contracts](security-contracts.md) |
| Target selection / admission / uncertainties | [Benchmark Set](../benchmarks/benchmark-set-v1.md); [catalog](../../../experiments/benchmarks/README.md) |
| Baselines / ablations | [Executable policies](../benchmarks/baseline-and-ablation-v1.md) |
| Metrics / methodology / censoring | [Evaluation protocol](../benchmarks/evaluation-protocol-v1.md) |
| Reproducibility / evidence ownership | This contract; [experiments](../../../experiments/README.md) |
| Vulnerability triage / disclosure | This contract; [SECURITY](../../../SECURITY.md) |

G0 fixes definitions and claim scope, not research outcomes. Remaining uncertainty
is historical reachability/qualification, repeated-policy effectiveness, generality,
measurable full-pipeline costs, interrupted-run evidence and final artifact
reproduction. Those are later validation gates, not reasons to claim them PASS.
No benchmark is promoted. Numeric plans and confirmation criteria remain provisional
and unchanged; RQ2/RQ3 claim scope is explicitly reconciled to the executable comparison.
