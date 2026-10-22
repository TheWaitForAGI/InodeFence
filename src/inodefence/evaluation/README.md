# Evaluation evidence

This package consumes core results without owning Search / Mutation / Feedback
policy. The direct user Task Contract authorizes evaluation infrastructure at
Layer 6; earlier audit navigation remains a historical record.

`python -m inodefence.evaluation DIRECTORY [--manifest-sha256 TRUSTED_DIGEST]`
reads a completed manifest-v4 export. `verify_campaign(Path(...))` returns an
immutable `VerifiedCampaign` only after the whole bundle passes. Invalid input
raises `VerificationError`; the CLI exits 1. It never executes targets.

Verification covers strict schema/JSON, declared file checksums, optional config
file and config ID, budget/count/index/lineage, canonical ArchiveCase/base64,
recomputed case IDs, current pinned builder format and regenerated TAR SHA-256.
Snapshots, changes, current signature/contracts, sentinel configuration, target
provenance, recorded feedback decisions and final corpus counters are checked
for consistency using existing core functions. No algorithm is reimplemented.

Only the current step-v1, signature-v3 and manifest-v4 formats are supported.
An unsupported historical/future format fails closed. Raw stdout/stderr,
snapshots, timestamps and durations survive typed decoding unchanged.

Checksums establish integrity relative to declarations, not authorship. The
existing exporter declares no checksum of the manifest itself. An optional
externally trusted manifest digest provides that anchor. Without it, a coherent
fabricated bundle cannot be distinguished from genuine evidence. Verification
does not establish runtime qualification, reproduction, rediscovery or paper
readiness. It does not reconstruct RNG/search execution or a dirty source patch.
The caller owns the directory's parents; bundle/file symlinks are rejected.
This reader loads the complete bundle in memory, matching the core's bounded
campaign representation. No partial record is returned as verified evidence.

## Entry-transition evidence

`export_transition_result` passively writes an explicit `TransitionEvaluationConfig`,
the complete transition campaign result and a last-published checksummed manifest.
`verify_transition_evidence` verifies each final RunResult/provenance binding and
replays parent selection, stable operator dispatch, mutation, transition novelty,
retention and scheduler outcome from the recorded RNG seed. Corrupt or coherently
rehashed decision evidence fails closed.

`summarize_transition_evidence` derives transition key/sequence, novelty, scheduler
and checkpoint-cost observations only after fresh verification.
`summarize_transition_statistics` requires equal controls, permits search policy as
the P0/P1/P2 arm, optionally permits declared RNG-seed variation, and reports
censored first-novel observations. These APIs neither execute a target nor qualify
an entry boundary. Native node-tar transition observation and formal benchmarks are
**NOT_RUN**; transition counts are not vulnerability counts.

## Pair records

`compare_pair(case, PairArm(provenance_a, result_a), PairArm(provenance_b, result_b))`
checks two caller-produced runs against the requested case and regenerated TAR.
`export_pair(pair, path)` preserves their full core results and their respective
execution provenance in a canonical checksummed record. `read_pair(path)` fails
closed on corruption or input/binding drift. Targets and outcomes may differ.
No CVE, expected result, ranking or automatic target execution is encoded here.
Execution remains caller-owned; this first pair API is the evidence boundary.

## N01 contained historical qualification

`inodefence.evaluation.n01` is the target-specific Layer 6 orchestration for the approved
node-tar `7.5.2 / 7.5.3` relative-hardlink pair. It does not add a generic oracle or mutation
rule. The runner reconstructs the one frozen case through
`uniform-generic-m1-protected-components-v1`, verifies the full case/TAR/sentinel/worker/lock
identities, admits only two immutable image IDs through the existing isolated Node metadata
probe, runs two filesystem oracle controls, exactly eight benign readiness extractions and,
only after readiness passes, the counterbalanced ten-run pair.

Every valid extraction is published as a checksummed `N01RunRecord` before expected-outcome
evaluation. Five existing `PairComparison` records bind the two arms without replacing either
raw result. Infrastructure exceptions stop further extraction and are written to the failure
ledger; readiness failures retain all eight completed outcomes and do not enter the pair phase.
No arbitrary archive path/case is accepted by this API and the total archive budget cannot
exceed 18.

`python -m inodefence.evaluation.n01_reader EVIDENCE --raw-manifest-sha256 SHA256` is the
fresh-process reader. It verifies every referenced byte, build/admission identity, benign
output, source/environment/sentinel binding, snapshots and pair records, then independently
recomputes inode equality and C0/C1/C2 from the raw evidence. It deliberately ignores the
runner's declared verdict until comparing the independently derived result. Its final
manifest always leaves human correspondence review pending; an automated PASS is only
`N01_PAIR_AUTOMATED_REPLAY_COMPLETE`, never the final pair-qualified token.

## N04 five-second historical-target preflight

`inodefence.evaluation.n04_preflight` is a separately versioned, one-attempt readiness
orchestrator for the exact retained node-tar 7.5.2/7.5.3 images. It binds the historical
build bytes and exported platform-manifest digest, current clean source locks/worker,
the two exact package tarball byte streams, host-broker containment attestation, two harness
oracle controls and the four existing
benign seeds on each target. Every target execution is fixed at five seconds and the archive
budget is eight. The single frozen evidence path prevents a second authorized attempt. It
performs no mutation, known-class replay, corpus evolution or pilot run.

The runner retains completed target outcomes even when readiness fails and writes a terminal
failure ledger for ordinary infrastructure errors. Its manifest cannot authorize a pilot.
`python -m inodefence.evaluation.n04_preflight_reader EVIDENCE
--raw-manifest-sha256 SHA256` checks every available publication prefix, independently
reconstructs complete readiness and emits only `PREFLIGHT_PASS`, `PREFLIGHT_FAIL`,
`PREFLIGHT_INCONCLUSIVE` or `INDEPENDENT_VERIFICATION_FAILED`. This Linux manifest has
`host_cleanup_pending=true`. Only the separately checksummed host ledger can bind its raw/final
digests to the host fallback-cleanup outcome and resolve the overall status. A preflight pass does not
alter the N01 human gate and does not authorize B0/B1/B3 or a native effectiveness campaign.

## N05 five-second historical-target preflight v2

`inodefence.evaluation.n05_preflight` keeps the N04 attempt consumed and introduces a distinct
single-attempt mode. Its schedule and oracle semantics are unchanged: two harness controls followed
by four benign seeds on affected and fixed, for exactly eight possible target extractions at five
seconds each. The new admission additionally requires the complete canonical human authorization
record, clean source revision and per-file hashes, fresh host-attested controller/volume facts and
the frozen target identities before target construction.

`inodefence.evaluation.n05_preflight_reader` reopens the authorization and retained source bytes,
all completed evidence prefixes and the raw manifest. `read_n05_preflight` performs the same raw
reconstruction without writing, so the host ledger reader can bind Linux evidence to bounded
controller stderr and cleanup. A missing terminal, changed authorization/source/image/timeout/
isolation field, interrupted prefix or uncertain cleanup cannot become `PREFLIGHT_PASS`.

This implementation is synthetic-tested but not authorized or run. It emits no pilot authorization.
The existing Track A preparation code must be changed to call the host reader on actual records and
to validate the separate pilot authorization content; storing their digest strings is insufficient.

## Track A target-free admission and host-attempt evidence

`inodefence.evaluation.track_a_admission` is the read-only Unit 1 consumer for the exact
20-campaign, 4,000-execution Track A pilot. `pilot_authorization_from_bytes` accepts only the
canonical typed pilot record. `validate_track_a_admission` additionally requires a caller-supplied
trusted authorization digest and approval reference, calls the existing N05 host verifier, reopens
the N05 authorization/Linux final/raw/admission records, and binds source, targets, controller,
daemon, environment, timeout, isolation, resources, protocol, output locations and the exact
seed-inclusive plan before returning `VerifiedTrackAAdmission`.

The trusted digest and approval reference must come from the human-controlled approval/launch
route. A digest and `authorized_by` text do not authenticate a person. The reader does not write an
admission record, create either Track A root, claim a campaign, launch a controller or execute a
target. Its tests use only synthetic N05 PASS-shaped engineering fixtures.

`freeze_track_a_execution` consumes that exact live capability in the validator process and stores
canonical copied pilot bytes, admission and N05 references. `read_track_a_execution` is the
separate retained-evidence reader: it reopens the authoritative originals but does not recreate a
live capability or authenticate the named reviewer from stored text or digests.

`track_a_host_ledger` adds the authorized host root, one no-overwrite directory per schedule cell,
and read-only canonical readers. `validate_track_a_host_admission` requires the original pilot path
plus trusted digest and approval reference again before host claim. `TrackAHostLedger.claim`
publishes the host-generated attempt ID before controller launch; `execute_track_a_slot` accepts
only that typed start and passes its ID unchanged to `PolicyRepetitionController`. `finish` retains
bounded stderr, campaign prefix, cleanup outcome and terminal/manifest cross-references. A start is
consumed without retry. Failure before campaign claim is explicit PENDING/zero executions; failure
after claim retains the campaign's STARTED/FAILED/INVALID prefix. Missing or incomplete cleanup,
stderr capture, terminal or manifest can never read as host success.

The actual host/controller filesystem mapping remains an integration precondition: the controller
must reopen the authorized host ledger, Track A root, original pilot record, authoritative N05
host/Linux roots and protocol bytes at their recorded paths. Unit 3 does not copy large evidence
trees or turn typed references into approval tokens. Real N05 and pilot execution remain `NOT_RUN`.
Any later approval must bind the final integrated clean source SHA exactly.

Evaluation records use a strict schema-v1 wrapper around existing canonical model
encoding. Payload SHA-256 is declared in the wrapper; whole-file digest is returned
for external anchoring. A synced temporary file is published with Linux atomic
no-overwrite hardlink and parent fsync. Prepublication failure leaves no final
file; postpublication fsync failure may leave a complete file and propagates.
Hard interruption can leave an ignored temporary file. Parents are trusted.

## Infrastructure failure ledger

`failure_record(exception, FailureContext(...))` captures the actual exception
and a timezone-qualified record timestamp; `write_failure(path, record)` publishes
a checksummed schema-v1 record without overwrite. `read_failure` verifies it.
Context preserves attempt/experiment/config/source/target identifiers, attempted
step and phase, last fully completed step, available diagnostics/logs/snapshots,
cleanup status/diagnostics and artifact digest references. Unavailable evidence
is `None`; default cleanup is `UNKNOWN`. Record time is not attempt duration.

Every record is `infrastructure_invalid`, distinct from SUCCESS, REJECTED, FAILED,
TIMED_OUT and C0/C1/C2. It must not enter an execution/nonviolation denominator.
Artifact references describe caller-recorded availability, not guaranteed later
existence. Checksums cover the record itself via the evaluation storage wrapper.

Core `run_campaign` currently propagates infrastructure exceptions and exposes
neither a completed-step callback nor its partial step list on failure. This
ledger cannot recover inaccessible evidence or infer which lifecycle phase
failed. Evaluation callers explicitly supply the evidence they retained and
handle publication errors. No core monkeypatch, fabricated result, automatic
campaign rerun or altered exception/status classification is introduced.

## Incremental evidence journal

`EvidenceJournal.create(directory, JournalHeader(...))` starts a single-writer
sink with explicit config, initial case IDs, optional original config JSON and
frozen provenance. `append(completed_step)` verifies and atomically publishes each
canonical step without overwrite. `read_journal(directory)` validates all prefix
records and returns an explicit incomplete snapshot until completion is marked.
Torn published records, gaps, index/lineage/binding/feedback drift fail closed.
Orphan staging files are ignored; previously published steps remain readable.

`finish()` requires the exact execution budget. It produces the unchanged core
manifest-v4 export and verifies it, then publishes a checksummed completion marker
binding header, all step digests, manifest and JSONL. An interrupted final
publication can be retried without executing targets or overwriting evidence.
A missing marker always means an incomplete journal, including when all records
or a full standalone export exist. A marker is checked against every record.

This is a passive evidence sink, not campaign/search checkpointing. Callers with
completed steps can publish before their next execution; the current opaque
`run_campaign` API cannot stream its internal steps, so direct automatic campaign
attachment remains blocked by that public interface. No monkeypatch is used.
Each append revalidates its prefix (quadratic total work); optimize only with
measured need. There is no concurrent-writer or malicious-parent guarantee.
Checksums do not authenticate authorship, and an externally deleted unfinalized
tail cannot be detected without a separately retained anchor.

## Campaign summary

`python -m inodefence.evaluation.summary DIRECTORY --format json|markdown`
or `summarize_campaign(directory)` verifies the complete input before aggregation.
Both formats anchor the original manifest/steps digests. Counts include all four
target statuses, C0/C1/C2 observed executions, any-contract observations, first
observed violation (zero-based step and one-based execution including seeds),
unique signatures/fingerprints, retained cases and unique executed cases.

A no-hit run has a null first observation within its budget. No duration, rate,
rediscovery, qualification or paper claim is inferred. A single verified campaign
has one validated target/config context; summaries preserve those identifiers.
Multi-run/per-target grouping requires separate dataset compatibility validation.
Infrastructure ledgers and incomplete journals are not execution inputs.

## Policy full-step timing

`run_search_campaign(..., completed_step=sink)` delivers each immutable policy step after
`run_case` returned (including sandbox cleanup) and feedback/step assembly completed, before
the next execution begins. `completed_record` additionally includes the exact generic mutation
attempt (operator, policy, parent, child and applied flag), or `None` for seeds. A sink exception
propagates and prevents the next execution; the core still does not return a partial result.

`run_timed_search_campaign` uses that boundary without changing SearchCampaignResult/Step or
policy identifiers. Profile `policy-full-step-monotonic-v1` records contiguous nanosecond
offsets from immediately before campaign preflight to each completed-step callback and final
result assembly, plus descriptive UTC start/end. These intervals are full orchestration-step
evidence, not `ExecutionResult.duration_seconds`; the latter remains target lifecycle time.

`export_timed_policy_result` publishes the existing bound policy bundle, a separate timing
record and a last manifest. `verify_timed_policy_evidence` independently verifies both
subtrees, checksums, evaluation config ID, step count/profile and contiguous offsets before
returning either. The CLI is `python -m inodefence.evaluation.policy_timing DIRECTORY` with an
optional trusted manifest digest.

By default this v1 wrapper measures in-memory completion. An optional synchronous completed-record
sink runs before the step timestamp, so its latency is included. It does not include later final
bundle publication, adjudicate a known class or make timed datasets poolable. No formal latency,
throughput or effectiveness result exists.

## Incremental policy journal

`run_journaled_timed_search_campaign` creates `PolicyJournalHeader` before execution and sends every
completed record to `PolicyEvidenceJournal`. Each record is atomic/no-overwrite. The independent
reader verifies RunResult/provenance and deterministically replays declared B0/B1/B3 parent selection,
operator dispatch, mutation and feedback from the recorded seed/config. Mutation provenance is kept
outside the unchanged `SearchCampaignResult`/`SearchCampaignStep` schemas.

At exact budget, `finish` binds all record digests to the complete timed policy evidence with a last
completion marker. A missing marker is always incomplete, even if every step or a timed subtree exists.
Ordinary execution exceptions publish a terminal generic failure record whose artifacts bind the
available prefix; they remain infrastructure-invalid and never enter target/no-hit denominators. A hard
process interruption can leave a readable prefix without a failure record. The journal does not resume,
retry, localize opaque target lifecycle failures, adjudicate the known class or prove qualification.
CLI: `python -m inodefence.evaluation.policy_journal DIRECTORY
[--completion-sha256 TRUSTED_DIGEST]`.

## Repeated policy schedule

`PolicyRepetitionPlan` stores an ordered set of unique `PolicyScheduledRun` records. Each run
has an explicit run/arm ID and complete `PolicyEvaluationConfig`; the plan does not infer
comparison fairness. `PolicyRepetitionController.execute` durably claims one slot, executes
the journaled/timed campaign exactly once, and publishes a terminal record bound to either
`evidence/completion.json` or `evidence/failure.json`. Ordinary infrastructure exceptions are
acknowledged as FAILED and re-raised. A hard interruption remains STARTED with its verified
prefix and cannot be automatically retried.

`read_policy_repetitions` verifies the plan, claims, unique attempt IDs, every journal/config
binding and terminal digest. A complete or failed journal without terminal acknowledgement
still remains STARTED. A directory reserved without a durable claim is INVALID. None of these
states is silently excluded or converted to no-hit. This controller provides schedule and
failure accounting, not target construction, authorization, qualification, known-class
adjudication, fairness approval, statistical pooling or recovery/resume.
CLI: `python -m inodefence.evaluation.policy_repeated ROOT
[--plan-sha256 TRUSTED_DIGEST]` reports every verified slot state.

`PolicyRepetitionController.execute_measured` adds the Linux-only
`linux-proc-self-vmhwm-v1` process-lifetime HWM record after a terminal. One OS process can
publish at most one measured slot. The independent reader rejects process identity reuse and
`--require-controller-memory` rejects terminal slots without the bound record. This is a
conservative dedicated controller-process peak, not a campaign delta or target-container
measurement; see the
[measurement contract](../../../docs/research/design/controller-peak-memory-v1.md).

## Candidate affected/fixed replay

`nominate_policy_candidate` selects one exact case only after reopening completed bound policy
evidence. The nomination retains the source binding/config/manifest digests, full case, TAR
identity and every original occurrence. `run_candidate_replays` then executes the unchanged
case in the fixed affected/fixed, fixed/affected, affected/fixed order and publishes each raw
result before continuing. Three generic `PairComparison` records and one final completion
marker bind the exact six-run budget.

`read_candidate_replay` re-verifies the source policy bundle, nomination, target/setup
provenance, run schedule and pair derivation. Ordinary exceptions retain an
infrastructure-invalid prefix; hard interruption leaves an incomplete readable prefix.
Existing roots are never retried or resumed. Missing completion never means complete/no-hit.
CLI: `python -m inodefence.evaluation.candidate_replay EVIDENCE SOURCE_POLICY_EVIDENCE
[--completion-sha256 TRUSTED_DIGEST]`.

This API retains exact-input replay evidence; it does not nominate by CVE, classify a matching
known class, decide affected/fixed expectations or perform human root-cause review. See the
[versioned contract](../../../docs/research/design/candidate-pair-replay-v1.md).

The separate N01-specific
[`n01_candidate_match`](../../../docs/research/benchmarks/n01-candidate-machine-match-v1.md)
reader reopens both the source policy bundle and generic replay, deterministically selects a
mutation-origin persistent relation from source evidence, checks the exact frozen N01 target
bindings and computes affected 3/3 versus fixed 0/3. It preserves C0/C2/status observations but
does not use them as the selected C1 relation. Its strongest status remains
`machine_contrast_pass_pending_human`; it cannot confirm rediscovery or issue a qualification
token. `nominate_n01_policy_candidates` first scans all raw mutation steps, deduplicates exact
case IDs for replay and retains every source occurrence in the nested generic nomination. No
historical candidate replay has been run.

## Dataset compatibility

`validate_dataset((DatasetMember(directory, protocol_version, manifest_digest), ...))`
verifies every bundle and the original stored ExperimentConfig through its public
parser, then checks its binding against execution evidence. Source must be pinned
and clean. Missing config/protocol/source, duplicate raw runs and hard differences
(source, builder/schema/protocol, seed profile/order, budget, timeout, sentinels,
search policy or isolation policy) are `incompatible`, with no pooling strata.

Target/artifact, runtime and environment-profile differences return
`requires_stratification` and explicit member-index groups. Seed differences do
the same unless the caller explicitly sets `allow_seed_variation=True` for
independent repetitions. Only `compatible` permits pooling. All records remain
in the report; invalid members are reported rather than silently discarded.

CLI: `python -m inodefence.evaluation.dataset DIRECTORY... --protocol-version VERSION`
with optional `--allow-seed-variation`. JSON report and exit 0 only on compatibility.
Protocol is an explicit caller binding because raw manifest v4 does not record it;
the validator cannot prove that an operator followed a protocol. Environment
profile is a declared setup label; observed harness/container runtime is checked
separately. Reference Python binary contents and dirty patches are absent from
the existing evidence. Compatibility covers recorded conditions, not authorship,
qualification, statistical sufficiency or paper readiness.

## Qualification reports

`qualification_report(QualificationContext(...), observations)` fills the complete
13-item generic checklist with PASS / FAIL / NOT_RUN. Unreported items stay
NOT_RUN; a failure dominates the overall status. PASS requires at least one
canonical relative artifact reference with SHA-256. Context binds exact requested
target/image/artifacts, captured execution provenance, environment/sentinel
profiles and protocol. No CVE, expected security outcome or target ranking appears.

`write_qualification(path, report)` publishes an immutable checksummed report.
`verify_qualification(path)` verifies report/schema and every linked artifact,
rejecting missing/corrupt files, traversal or symlinks. An all-PASS report also
requires captured clean source/runtime and matching verified image/isolation/
artifact requirements. Only this verified all-PASS report is READY. A partially
checked trusted reference is useful engineering evidence and remains NOT_RUN.
CLI: `python -m inodefence.evaluation.qualification REPORT --format json|markdown`.

The framework records trusted assessor observations linked to artifacts; it does
not independently prove the assertions inside arbitrary assessor output or run
target qualification. A file/digest is integrity evidence, not authorship. Actual
benign/status/timeout/lifecycle probes must be supplied before declaring PASS.
Existing smoke CI and planning catalog are not retroactively marked qualified.

## Target matrix and protocol binding

The separate `EvaluationCatalog` stores unique `ProtocolBinding` records with
benchmark/family, exact A/B TargetProvenance versions, expected full source/
runtime/isolation/image/artifact/sentinel provenance, required profiles/protocol,
pinned builder and checksummed qualification links. Core ExperimentConfig and
the existing planning-only benchmark catalog are unchanged.

`validate_catalog(path)` freshly verifies both qualification reports and their
underlying artifacts, then compares every expected binding. READY requires both
fully qualified reports and matching pair source/sentinels. Missing bindings or
NOT_RUN/FAIL reports are NOT_READY; corrupt/missing/mismatched declared links are
INVALID. `require_ready(path, benchmark_id)` raises unless READY. No input boolean
or document assertion can enable a benchmark. Target release strings retain all
runtime/version components that the actual core adapter records; no missing
version information is invented. This is protocol/evidence binding, not proof
that an assessor's assertions are independently true or a rediscovery outcome.

## Native effect raw export

`native_effect_evidence.export_native_effect_run()` publishes one exact producer stdout
frame, the canonical `EffectRunResult`, and a manifest last. All three files are immutable,
checksummed and refuse overwrite. The manifest binds the case, raw stream and producer source
digest. Gate 3 intentionally provides no reader here; independent reconstruction and
qualification belong to the separate Gate 4 branch.

Gate 4 adds `verify_native_effect_evidence()`. It ignores the producer's integrity declaration,
reconstructs lifecycle/effect/causal evidence from the exact raw frame, verifies source,
archive, command, sequence, correlation, flush and final-state bindings, and recomputes the
normalized feedback keys. `scripts/verify_node_effect_evidence.py` exposes this reader for one
bundle. Invalid or incomplete streams never return verified evidence.

## Track A exploratory final-state pilot

`track_a_exploratory`는 N03의 20-cell affected-B0/B1/B3 + fixed-B3 순서와 5초/200회 조건을
별도 versioned feasibility protocol로 고정한다. 승인된 Preflight와 별도 pilot authorization의
SHA-256이 없으면 plan을 만들지 않는다. 각 cell은 fresh controller process에서 순서대로 한 번만
실행하며 기존 policy journal, full-step timing, repetition ledger, controller VmHWM 및 N01
nomination reader를 재사용한다. STOP 뒤 자동 재시도는 없다.

`finalize`는 complete/failed/invalid/STARTED/PENDING 상태와 모든 raw file digest를 마지막
manifest에 봉인한다. `verify`와 `analyze`는 이를 새로 읽어 arm별 실행/상태/위반/시간/메모리/
저장량 및 탐색적 비교를 계산한다. 이 결과는 final-state feasibility이며 P0/P1/P2, confirmed
rediscovery 또는 통계적 우월성을 뜻하지 않는다. 정확한 계약은
[Track A protocol](../../../docs/research/benchmarks/track-a-final-state-exploratory-feasibility-v1.md)을
따른다.
