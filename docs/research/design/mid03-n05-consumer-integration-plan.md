# MID-03 N05 consumer integration plan

Status: **DESIGN PROPOSAL / NOT IMPLEMENTED / NOT AUTHORIZATION**.

Date: **2026-10-21 UTC**. Owner scope: **MID-03 / Search, Mutation, Feedback and
Evaluation**.

This document specifies the smallest fail-closed integration needed for the Track A
B0/B1/B3 pilot to consume a completed process-gate N05 preflight. It is not an execution
record, approval token or finding.

## 1. Reviewed revisions and current gate

| Item | Exact revision reviewed | Observed status on 2026-10-21 UTC |
| --- | --- | --- |
| `origin/main` | `8d29982c26cebfcce7a413b3ba9177fcd28078de` | current fetched main used as the common baseline |
| PR [#108](https://github.com/TheWaitForAGI/InodeFence/pull/108) | `64a7a1645c03512d50ff5e0246108d297d1e6aa8` | open draft; Track A candidate; GitHub Actions `check` and `container-integration` succeeded; pilot NOT_AUTHORIZED / NOT_RUN |
| PR [#114](https://github.com/TheWaitForAGI/InodeFence/pull/114) | `f7aaa33050e247e0718d4ceb1ba01485802e269d` | open draft; N05 implementation candidate; GitHub Actions `check` and `container-integration` succeeded; N05 NOT_AUTHORIZED / NOT_RUN |
| PR [#116](https://github.com/TheWaitForAGI/InodeFence/pull/116) | `7d42799e895eba0f490fbdeaad110fe1407fd664` | open, non-draft; audit head; GitHub Actions `check` and `container-integration` succeeded; requested human review remains pending |
| This document branch point | `7d42799e895eba0f490fbdeaad110fe1407fd664` | documentation-only uncommitted work based on PR #116 head |

The legacy commit-status collections for all three PR heads were empty; the CI statements above
come from the GitHub Actions check runs, not from an inference based on the empty legacy status
collection. The PR heads have not changed since the
[MID-03 code review comment](https://github.com/TheWaitForAGI/InodeFence/pull/108#issuecomment-6318148213).

Current execution/approval state:

| Gate | State | Consequence |
| --- | --- | --- |
| N01 final human correspondence | `AWAITING_HUMAN_CORRESPONDENCE_REVIEW` | automated PASS is not a human qualification token |
| Process-gate N05 authorization | `NOT_AUTHORIZED` | the candidate attempt ID and constants are not an authorization |
| Process-gate N05 execution/evidence | `NOT_RUN`; no retained PASS was found | no `PREFLIGHT_PASS` can be consumed |
| MID-03 N05 consumer | `NOT_IMPLEMENTED` | PR #108 stores two digest-shaped strings but does not open their records |
| Separate 4,000-execution pilot approval | `NOT_AUTHORIZED` | N05 approval, even if later issued, cannot authorize the pilot |
| N05 and Track A execution in this work | `NOT_RUN` | no target, Docker, `prepare`, `run-cell`, smoke or campaign command was run |

The process-gate N05 in this document is the five-second N01-pair preflight from PR #114. It is
not benchmark-catalog N05. The detailed pre-existing MID-03 facts and claim boundary remain in the
[audit report](../diagnostics/mid03-feedback-evaluation-audit-2026-10-21.md).

### Evidence labels used below

- **FACT**: directly observed in the exact revisions above.
- **PROPOSAL**: interface or behavior to implement after the required gates.
- **HUMAN DECISION**: policy or authorization content that code must not invent.

No proposed class or function in this document is described as existing implementation.

## 2. Existing call paths

### 2.1 PR #108 Track A path — FACT

Preparation currently follows this path:

```text
scripts/track_a_container_host.py:_arguments
  accepts two caller-provided 64-hex strings
    -> scripts/track_a_container_host.py:main
       inspects controller and starts docker exec
       passes both strings through
         -> scripts/track_a_container_controller.py:_arguments
            checks presence only
              -> scripts/track_a_container_controller.py:main (prepare)
                 captures live source/environment/target isolation
                   -> freeze_track_a_execution
                      _digest() syntax checks only
                      make_track_a_plan
                      creates output root + repetitions/plan.json
                      writes execution.json
```

One campaign currently follows this path:

```text
track_a_container_host.py:main (run-cell)
  controller inspect + docker exec; no Track A host attempt ledger
    -> track_a_container_controller.py:main (run-cell)
       read_track_a_execution
       binds target and creates a random attempt ID
         -> execute_track_a_slot
            checks order/current source/current target provenance
              -> PolicyRepetitionController.execute_measured
                 -> PolicyRepetitionController.execute
                    -> claim() writes repetitions/run-XX/claim.json
                    -> journaled campaign/target executions
                    -> terminal + controller-memory records
```

Relevant immutable sources are:

- [`TrackAExecutionManifest`, `freeze_track_a_execution` and `read_track_a_execution`](https://github.com/TheWaitForAGI/InodeFence/blob/64a7a1645c03512d50ff5e0246108d297d1e6aa8/src/inodefence/evaluation/track_a_exploratory.py#L452-L579)
- [`execute_track_a_slot`](https://github.com/TheWaitForAGI/InodeFence/blob/64a7a1645c03512d50ff5e0246108d297d1e6aa8/src/inodefence/evaluation/track_a_exploratory.py#L582-L634)
- [Track A controller entry point](https://github.com/TheWaitForAGI/InodeFence/blob/64a7a1645c03512d50ff5e0246108d297d1e6aa8/scripts/track_a_container_controller.py#L24-L127)
- [Track A host entry point](https://github.com/TheWaitForAGI/InodeFence/blob/64a7a1645c03512d50ff5e0246108d297d1e6aa8/scripts/track_a_container_host.py#L20-L158)
- [`PolicyRepetitionController` claim/execute boundary](https://github.com/TheWaitForAGI/InodeFence/blob/64a7a1645c03512d50ff5e0246108d297d1e6aa8/src/inodefence/evaluation/policy_repeated.py#L433-L564)

The durable campaign claim is therefore later than host controller inspection, `docker exec`,
stdio setup and controller startup. A failure in that interval leaves the policy slot `PENDING`
and leaves no Track A host record that distinguishes “never launched” from “host launch failed”.

### 2.2 PR #114 N05 reader path — FACT

PR #114 supplies two complementary readers:

1. [`read_n05_preflight(root, *, expected_final_manifest_sha256) -> VerifiedN05Preflight`](https://github.com/TheWaitForAGI/InodeFence/blob/f7aaa33050e247e0718d4ceb1ba01485802e269d/src/inodefence/evaluation/n05_preflight_reader.py#L580-L624)
   reopens the Linux final manifest, independent verification and raw manifest, then recomputes the
   raw decision. Its Linux final record deliberately has `host_cleanup_pending=True`, so it cannot
   establish host cleanup by itself.
2. [`verify_n05_host_ledger(root, linux_evidence, *, expected_manifest_sha256) -> dict`](https://github.com/TheWaitForAGI/InodeFence/blob/f7aaa33050e247e0718d4ceb1ba01485802e269d/scripts/container_host.py#L657-L900)
   rehashes the N05 host ledger, exact authorization bytes, bounded controller stderr and Linux
   records; cross-checks terminal digests/status; incorporates host deadline and cleanup; and only
   permits overall `PREFLIGHT_PASS` when the independent Linux result is also PASS.

The actual N05 authorization parser is
[`authorization_from_bytes(content: bytes) -> N05PreflightAuthorization`](https://github.com/TheWaitForAGI/InodeFence/blob/f7aaa33050e247e0718d4ceb1ba01485802e269d/src/inodefence/evaluation/n05_preflight.py#L208-L298).
It validates canonical bytes and the complete typed record; it explicitly does not cryptographically
prove the identity named in `authorized_by`. Source admission is exact:
[`verify_authorized_source`](https://github.com/TheWaitForAGI/InodeFence/blob/f7aaa33050e247e0718d4ceb1ba01485802e269d/src/inodefence/evaluation/n05_preflight.py#L301-L321)
requires the clean authorized full revision and every authorized executable-file digest.

The host verifier returns an untyped dictionary with authorization, final/raw manifest, overall
status and source-revision values. It verifies more identities internally than it exposes. A Track A
consumer must not infer omitted target/controller/daemon/environment fields from that small return
dictionary; it must retain and reopen the underlying authorization and manifests.

Exact reviewed API boundary:

| Existing API at PR #114 head | Original input/files opened | Where its expected digest comes from today | What it guarantees | What the Track A caller still must guarantee |
| --- | --- | --- | --- | --- |
| `authorization_from_bytes(content: bytes) -> N05PreflightAuthorization` | caller already read `authorization.json`; parser checks the exact canonical byte representation | it does not accept an expected digest; the caller must hash/read-bind bytes first | complete N05 authorization schema and frozen values, including `pilot_authorized=False` | trusted selection of expected digest/path and actual human identity/review trail |
| `read_n05_preflight(root: Path, *, expected_final_manifest_sha256: str) -> VerifiedN05Preflight` | `manifest.json`, referenced `independent-verification.json`, `raw-manifest.json`, authorization/source/package/build/admission/control/readiness/failure artifacts | caller supplies the Linux final-manifest digest; N05 host terminal is the authoritative cross-reference in the current flow | byte checksums, canonical models, raw recomputation, source/authorization/broker/target/5-second/isolation/readiness consistency and Linux final status | host-ledger integrity, final host cleanup/deadline/stderr, same Track A identity and a separate pilot authorization |
| `verify_n05_preflight(root, *, expected_raw_manifest_sha256) -> VerifiedN05Preflight` | raw evidence, then **writes** independent verification and final manifest | N05 controller supplies the raw-manifest digest after the runner | produces the N05 independent/final records | not a consumer API; Track A must never call it to manufacture a missing terminal record |
| `verify_n05_host_ledger(root: Path, linux_evidence: Path, *, expected_manifest_sha256: str) -> dict` | host `authorization.json`, `controller-stderr.bin`, `started.json`, `terminal.json`, `manifest.json`, then all Linux evidence through `read_n05_preflight` | a future Track A consumer must take it from the separately approved pilot record, not an independent CLI string | host file/attempt binding, authorization copy, host↔Linux digest/status agreement, deadline, controller result/stderr and cleanup; overall PASS requires independent Linux PASS | typed exposure/reopening of every identity, equality with final Track A source/plan/environment, pilot approval scope and preservation of authoritative roots |

`verify_n05_preflight` is intentionally listed to prevent the consumer from choosing the wrong API:
it creates terminal records and belongs to N05 production/finalization. The read-only Track A path is
`verify_n05_host_ledger` plus `read_n05_preflight`/`authorization_from_bytes` over already retained
records.

## 3. Current-to-proposed integration map

| Current file/function | Current input and check — FACT | Reader/check to connect — PROPOSAL | Additional binding — PROPOSAL | Failure handling — PROPOSAL | Record to preserve — PROPOSAL |
| --- | --- | --- | --- | --- | --- |
| `scripts/track_a_container_host.py:_arguments` | digest-shaped preflight and resource strings; image order and mode argument shape | accept exact pilot-authorization path plus trusted expected digest; pilot record supplies the N05 host/Linux roots and expected host-manifest digest | authorization scope, source, controller, images, daemon, environment, schedule, resources and output locations | reject before Docker lookup, controller inspection, output-root creation or campaign claim | no trusted repository record is possible until the pilot authorization path itself validates; caller stderr only |
| `track_a_container_host.py:main` | inspects controller, launches `docker exec`, relays commands, enforces 7,200-second watchdog, cleans owned targets; no ledger | call the proposed read-only admission function before Docker; after admission, create a no-overwrite Track A host-attempt ledger before controller launch | selected run index/ID, plan/execution digest, admission bundle digest, one host-generated attempt ID, actual controller identity | any post-claim failure is terminal and consumes that cell under the proposed fail-closed default; never silently retry | host `started.json`, bounded stderr, `terminal.json`, `manifest.json`; controller claim/terminal references when present |
| `scripts/track_a_container_controller.py:_arguments` | prepare checks only that both strings exist; run-cell accepts execution digest/index | accept a verified admission-bundle reference during prepare; accept host-provided attempt ID during run-cell | the bundle must already bind the exact pilot authorization and N05 evidence | parser failure before target binding; no target call | controller diagnostics plus host ledger; no campaign evidence before claim |
| `track_a_container_controller.py:main` prepare branch | captures current provenance, binds targets, then calls freeze with strings | read the copied admission bundle and exact authorization bytes; verify current clean source and authorized live provenance | same source/target/controller/image/daemon/environment/timeout/isolation/resource profile | do not create the Track A output root if admission or live binding fails | admission references/copies remain in the trusted host admission ledger; execution root remains absent |
| `track_a_exploratory.freeze_track_a_execution` | `_digest()` only checks two strings; creates root before any underlying N05/approval read | receive a typed `VerifiedTrackAAdmission`, not independent strings | protocol/config/plan digest, exact 20-cell order, 4,000 total, N05 and pilot record references, new N05-qualified environment profile | fail before `root.mkdir`; do not downgrade to an empty/no-hit run | exact pilot-authorization bytes, typed admission bundle, immutable references to retained N05 host/Linux roots, then plan/execution records |
| `TrackAExecutionManifest` | stores two opaque digest strings and source revision | replace/augment them with typed artifact references to admission evidence | include N05 attempt/source/host/final/raw digests and pilot authorization/plan/source identities | reader rejects missing, extra, symlinked or mismatched admission evidence | `admission/pilot-authorization.json`, `admission/verified-admission.json`, `execution.json` |
| `read_track_a_execution` | rehashes its own execution/config/plan and exact source in the plan | reopen the admission records and re-run their read-only validators | every later campaign uses the same admission bundle; no caller substitution | fail closed; finalized or partially run evidence remains inspectable but cannot execute | existing immutable prefix plus the admission records |
| `execute_track_a_slot` | checks order, clean source and current target provenance before repetition controller | additionally require admitted host-attempt identity supplied by the host | run index/ID/config, plan SHA, execution SHA, host attempt ID and authorization ID | validation failure occurs before campaign claim; after host claim it is terminal host failure | host terminal links the still-PENDING campaign slot and records zero target executions |
| `PolicyRepetitionController.claim` | durable campaign claim; no duplicate/retry after claim | reuse unchanged | host attempt ID must equal campaign `attempt_id`; no controller-generated replacement | existing STARTED/no-retry behavior remains | current claim, journal prefix, terminal and memory records |
| `n05_preflight_reader.read_n05_preflight` | recomputes Linux raw/final decision; final says host cleanup pending | call through the host verifier, and optionally reopen directly to obtain the typed Linux result | final/raw/independent records must match the host terminal exactly | any non-PASS, incomplete or corrupt record rejects Track A admission | authoritative N05 Linux root stays immutable; Track A stores digests and path reference |
| `scripts/container_host.verify_n05_host_ledger` | rehashes host and Linux evidence and includes cleanup; returns a small `dict` | reuse exactly; wrap result in a proposed typed Track A admission object after separately reopening retained N05 authorization/Linux objects | expose or rederive complete identity set rather than trusting only returned source/status | exception or overall non-PASS rejects before Track A side effects | authoritative N05 host root stays immutable; Track A stores host-manifest digest and path reference |

The first implementation should wrap the existing N05 verifier and reader, not create a second N05
runner. Moving the PR #114 verifier into a library can be considered later, but is not required for
the minimum consumer and would enlarge the source-freeze problem.

## 4. Required admission order

The following is the proposed fail-closed order. Steps 1–8 are read-only and must finish before
Docker lookup, controller inspection/launch, Track A output-root creation, host-attempt claim or
campaign claim.

1. Read the exact pilot authorization file from its expected nonsymlink absolute path.
2. Rehash the actual bytes and compare them with an expected digest received through the explicit
   human-controlled launch process. A 64-character hex string alone proves nothing.
3. Parse and canonicalize the bytes as the proposed `TrackAPilotAuthorization`. Require its scope to
   be the Track A 4,000-execution pilot; reject an N05 preflight authorization record.
4. Resolve the N05 host-ledger root, Linux evidence root and host-manifest digest only from that
   pilot record. Reject N04 attempt IDs, modes, paths and profiles.
5. Call existing `verify_n05_host_ledger(...)` on those actual roots. Require returned overall
   status `PREFLIGHT_PASS` and equality with the authorization's N05 digests/source.
6. Reopen `authorization.json` with `authorization_from_bytes(...)` and the Linux final with
   `read_n05_preflight(...)`. Require independent PASS, Linux final `PREFLIGHT_PASS`,
   `pilot_authorized=False` on the N05 record, and a host result proving cleanup complete or not
   needed. Linux `host_cleanup_pending=True` is expected and is resolved only by the host verifier.
7. Compare source, affected/fixed target package/build/image identities, controller image/container,
   Docker context/daemon, Linux environment, runtime volume, target timeout, isolation and resource
   profiles across N05, pilot authorization and the prospective Track A plan.
8. Build the exact Track A plan in memory and compare its protocol/config digest, ordered cells,
   seeds, budget, repetition count and output locations with the pilot authorization.
9. Publish a no-overwrite admission record containing exact copied pilot-authorization bytes and
   typed references to the authoritative retained N05 roots. Large N05 raw files need not be
   duplicated, but both roots must remain immutable and reopenable by the final Track A reader.
10. Only after admission succeeds may `prepare` capture the live source/environment, create the
    Track A output root and freeze the execution plan. Live values must equal the admitted values.
11. Before each `run-cell` controller launch, publish a distinct host-attempt claim and pass its
    attempt ID to the controller. The controller must not manufacture a different UUID.
12. Only after the controller's existing campaign claim may target executions be counted.

Proposed pure interface names for the implementer are illustrative and do not exist at the reviewed
SHAs:

```python
pilot_authorization_from_bytes(content: bytes) -> TrackAPilotAuthorization

validate_track_a_admission(
    *,
    pilot_authorization_path: Path,
    expected_pilot_authorization_sha256: str,
) -> VerifiedTrackAAdmission
```

`VerifiedTrackAAdmission` should contain typed N05 authorization/Linux results, the verified host
summary, the parsed pilot authorization, exact byte digests and the in-memory Track A plan digest.
It must not contain an “authorized” boolean supplied by the caller.

### 4.1 Hex syntax versus evidence verification

PR #108's `_digest()` checks only `[0-9a-f]{64}`. In contrast, PR #114's Linux `_bytes()` reads the
actual referenced file and compares `sha256(content)`, while the host verifier rehashes every host
record and then calls the Linux reader. The consumer must use the latter evidence path. Passing
`"a" * 64` must never reach `freeze_track_a_execution`, even though it satisfies `_digest()`.

### 4.2 Records retained by Track A

The proposed Linux output layout is:

```text
<authorized-track-a-output-root>/
  admission/
    pilot-authorization.json        # exact external canonical bytes, no envelope
    verified-admission.json         # internal write_record envelope
    n05-evidence-reference.json     # authoritative roots + all expected digests
  execution.json
  repetitions/
  final-manifest.json
```

The proposed trusted-host ledger layout is separate because it must survive failures before the
Linux controller can write:

```text
<authorized-track-a-host-ledger-root>/
  admission/...
  attempts/00-<run-id>/
    started.json
    controller-stderr.bin
    terminal.json
    manifest.json
  ... one directory per claimed schedule cell
```

All publication uses the existing no-overwrite/atomic pattern. The Track A final manifest must
inventory its local admission records. Its N05 reference record must provide enough paths and
digests for an independent reader to reopen the authoritative external host and Linux roots; a
summary copied from `verify_n05_host_ledger` is not a substitute for those roots.

An invalid or untrusted pilot-authorization path cannot safely select a write destination. Such a
pre-trust failure leaves only process diagnostics captured by the human-controlled caller. Once the
pilot authorization is valid, later N05/binding admission failures should be published under its
authorized host `admission/` directory without creating a campaign attempt or Linux Track A root.

## 5. Exact source binding and the post-N05 change problem

### FACT

The N05 draft contract requires one reviewed clean full commit and says the human record freezes
that full commit plus the executable files. `N05PreflightAuthorization.execution_source_revision`
is checked as a clean `SourceProvenance`; the Linux reader requires its raw manifest source revision
to equal it. The Track A plan independently requires one clean source revision for both targets and
`execute_track_a_slot` recaptures exact equality.

No reviewed code or contract at PR #114 head defines a compatible-descendant rule, path-limited SHA
exception, ancestry rule or permission to change only Track A files. Therefore:

```text
N05 PASS at source S0
    + consumer implementation commit S1 (S1 != S0)
    != authorization to use S0 evidence for a pilot at S1
```

The fact that Track A files are not currently in `AUTHORIZED_EXECUTABLE_PATHS` does not override the
full `execution_source_revision` equality.

### HUMAN DECISION

Before any implementation result can admit a pilot, the runtime owner and research/presentation
owner must choose and record one of these paths:

1. **Exact-source path (recommended under the current contract):** implement and independently
   review the consumer, freeze the final integrated SHA, then authorize and perform a newly scoped
   N05 preflight for that exact SHA. If the prior one-attempt N05 was consumed, this requires a new
   Task Contract/attempt ID; it is not a retry of `attempt-001`.
2. **Explicit compatibility-contract path:** amend and review the N05 contract and both readers to
   define exactly which source/file changes preserve applicability, how ancestry and file bytes are
   checked, and who approves that relation. The existing N05 evidence remains unusable until that
   new rule is approved and applied. This document does not propose the exception as already valid.

Silent reuse, comparing only selected file digests, or treating Git ancestry as authorization is
forbidden. This unresolved choice is a gate, not an implementation detail.

## 6. Separate typed pilot authorization

The N05 record authorizes exactly one bounded benign preflight and fixes
`pilot_authorized=False`. The Track A pilot requires a different human-authored canonical record.
The proposed record should be immutable data, not a token generated by the consumer.

### 6.1 Supporting types — PROPOSAL

| Type | Minimum fields | Meaning |
| --- | --- | --- |
| `ArtifactReference` | `path: str`, `sha256: HexDigest` | exact retained bytes; path rules reject symlinks/escape |
| `AuthorizedFile` | repository-relative `path`, `sha256` | executable/config bytes reviewed for the pilot |
| `PilotCampaignCell` | `run_id: str`, `arm_id: Literal[...]`, `random_seed: int` | one ordered plan cell |
| `PilotArmAllocation` | `arm_id`, `campaigns: int`, `executions_per_campaign: int`, `total_executions: int` | explicit 1,000-run allocation per arm |
| `PilotTargetIdentity` | role, Node/tar versions, image ID, platform/package/lock/build/worker digests | affected/fixed immutable target identity |
| `PilotResourceLimits` | memory, PIDs, open files, file size, tmpfs, shm, captured bytes, watchdog | exact controller/target resource contract |
| `N05EvidenceBinding` | attempt/mode, host/Linux roots, authorization/host/final/raw/independent digests, source revision | complete N05 cross-reference, not merely one digest |

### 6.2 Record fields — PROPOSAL

| Field | Type | Required | Verified against |
| --- | --- | --- | --- |
| `schema_version` | exact `int` (`1`) | yes | parser-supported schema |
| `authorization_scope` | literal `TRACK_A_FINAL_STATE_4000_PILOT` | yes | prevents N05 authorization reuse |
| `authorization_id` | nonempty stable `str` | yes | host ledger and every campaign attempt |
| `decision` | literal `AUTHORIZE_EXACT_TRACK_A_PILOT` | yes | explicit human decision, not inferred PASS |
| `authorized_by`, `authorized_at` | nonempty `str`, timezone-aware ISO-8601 | yes | attribution and review record; not cryptographic identity proof |
| `human_review_statement` | exact versioned statement | yes | must say N05 and pilot are separate and authorize 20/4,000 only |
| `approval_basis` | nonempty tuple of immutable review/evidence references | yes | human-controlled review trail; links/digests are reopened where local |
| `source_revision` | full clean Git SHA | yes | current repository, Track A plan and execution manifest |
| `authorized_files` | sorted tuple of `AuthorizedFile` | yes | Track A host/controller, admission/core/protocol files and any imported N05 consumer files |
| `protocol_version` | exact `str` | yes | PR #108 protocol version |
| `protocol_config` | `ArtifactReference` | yes | actual JSON bytes; candidate digest is `88ed4fde6e3f926099a9e28d978b583c5eedcb4b4074b37a4b1e7bca1c26f19c` |
| `repetition_plan_sha256` | `HexDigest` | yes | canonical in-memory 20-cell plan serialized by existing model |
| `campaigns` | tuple of exactly 20 `PilotCampaignCell` | yes | exact schedule and generated `PolicyRepetitionPlan` |
| `arm_allocations` | tuple of four `PilotArmAllocation` | yes | affected B0/B1/B3 and fixed B3: each 5 × 200 = 1,000 |
| `total_campaigns` | exact `int` (`20`) | yes | schedule length |
| `total_executions` | exact `int` (`4000`) | yes | sum of all arm allocations |
| `initial_case_ids` | ordered tuple of four digests | yes | actual `minimal_seed_corpus()` order |
| `seed_profile` | exact versioned `str` | yes | plan's initial-corpus profile |
| `campaign_rng_seeds` | exact tuple `(9001, 9002, 9003, 9004, 9005)` | yes | cells and policy configs |
| `scheduling_rng_seed` | exact `int` (`4242`) | yes | documented shuffle and exact schedule |
| `campaign_execution_budget` | exact `int` (`200`) | yes | every `SearchCampaignConfig` |
| `initial_seeds_in_budget` | exact `bool` (`True`) | yes | campaign semantics; four seeds consume four of 200 |
| `repetitions_per_arm` | exact `int` (`5`) | yes | allocations and cells |
| `target_timeout_seconds` | exact finite number (`5.0`) | yes | N05, targets and plan provenance |
| `mutation_policy` | exact versioned policy ID | yes | all four arms use protected-component M1 |
| `feedback_projection` | exact FULL StateSignature v3 ID | yes | all four arms; no A1/A2 result claim |
| `oracle_contracts` | exact ordered C0/C1/C2 profile ID | yes | plan and current generic oracle configuration |
| `sentinel_profile` | exact versioned profile ID and sentinel digest/mode | yes | plan, N05 and live capture |
| `targets` | exactly two `PilotTargetIdentity` values | yes | N05 authorization/raw admissions and live target inspection |
| `controller_id`, `controller_image_id` | immutable container/image IDs | yes | N05 authorization/host ledger and live host inspection |
| `host_docker_context` | exact `str` | yes | N05 authorization and invocation |
| `daemon_id`, `daemon_version`, `daemon_api_version` | nonempty exact strings | yes | N05 broker/raw evidence and live inspection |
| `environment_system`, `environment_machine`, `environment_profile` | exact versioned values | yes | N05 environment, Track A provenance and replacement for stale N04 profile |
| `runtime_volume_name`, `runtime_root` | exact strings/absolute path | yes | N05, host/controller invocation and Track A provenance |
| `controller_isolation_profile`, `target_isolation_profile` | exact versioned IDs | yes | N05 authorization/admissions and live isolation capture |
| `resource_limits` | `PilotResourceLimits` | yes | protocol JSON and live target/controller policy |
| `campaign_watchdog_seconds` | exact `int` (`7200`) | yes | host invocation and timeout tests |
| `sequential`, `fresh_controller_per_campaign` | exact `True` values | yes | schedule execution and process-HWM semantics |
| `stop_conditions` | ordered tuple of versioned conditions | yes | stop after prior non-complete, watchdog, identity/admission/cleanup failure |
| `no_retry` | exact `True` | yes | host and campaign ledgers |
| `resume_policy` | literal `NONE_NEW_AUTHORIZATION_REQUIRED` | yes | rejects STARTED or host-claimed automatic rerun |
| `track_a_output_root`, `track_a_host_ledger_root` | new exact absolute nonsymlink paths | yes | CLI, freeze and readers; must not pre-exist |
| `n05` | `N05EvidenceBinding` | yes | actual retained N05 authorization, host ledger and Linux evidence |

The exact candidate cell order to encode and compare is:

| Index | Run ID | Arm | RNG seed |
| ---: | --- | --- | ---: |
| 0 | `n01-affected-b3-9002` | affected B3 | 9002 |
| 1 | `n01-fixed-b3-9003` | fixed B3 | 9003 |
| 2 | `n01-affected-b3-9004` | affected B3 | 9004 |
| 3 | `n01-affected-b1-9003` | affected B1 | 9003 |
| 4 | `n01-fixed-b3-9001` | fixed B3 | 9001 |
| 5 | `n01-fixed-b3-9005` | fixed B3 | 9005 |
| 6 | `n01-affected-b1-9001` | affected B1 | 9001 |
| 7 | `n01-fixed-b3-9004` | fixed B3 | 9004 |
| 8 | `n01-affected-b3-9003` | affected B3 | 9003 |
| 9 | `n01-affected-b1-9005` | affected B1 | 9005 |
| 10 | `n01-fixed-b3-9002` | fixed B3 | 9002 |
| 11 | `n01-affected-b0-9003` | affected B0 | 9003 |
| 12 | `n01-affected-b3-9001` | affected B3 | 9001 |
| 13 | `n01-affected-b3-9005` | affected B3 | 9005 |
| 14 | `n01-affected-b1-9002` | affected B1 | 9002 |
| 15 | `n01-affected-b0-9005` | affected B0 | 9005 |
| 16 | `n01-affected-b0-9004` | affected B0 | 9004 |
| 17 | `n01-affected-b0-9001` | affected B0 | 9001 |
| 18 | `n01-affected-b0-9002` | affected B0 | 9002 |
| 19 | `n01-affected-b1-9004` | affected B1 | 9004 |

This schedule is the one enforced in
[`TRACK_A_SCHEDULE`](https://github.com/TheWaitForAGI/InodeFence/blob/64a7a1645c03512d50ff5e0246108d297d1e6aa8/src/inodefence/evaluation/track_a_exploratory.py#L80-L111)
and the [protocol JSON](https://github.com/TheWaitForAGI/InodeFence/blob/64a7a1645c03512d50ff5e0246108d297d1e6aa8/experiments/configs/track-a-final-state-exploratory-feasibility-v1.json#L61-L81).

### 6.3 Canonical bytes, digest and human trust

Follow the N05 authorization convention for the external human record:

1. decode into the exact typed dataclass;
2. require `content == json_bytes(asdict(record)) + b"\n"`;
3. calculate SHA-256 over those exact bytes, including the final newline;
4. compare against the expected digest supplied by the explicit human-controlled launch route;
5. copy those exact bytes without overwrite into both the trusted host ledger and Track A admission
   evidence; and
6. make every derived internal record with the existing `write_record` envelope.

The digest protects bytes after a trusted expected value is selected. Neither a digest nor an
`authorized_by` string authenticates a person. The team must verify the human approval source and
its linkage to the exact digest through its normal trusted review channel. The code can preserve and
compare that linkage; it cannot create it.

## 7. Host attempt and campaign state

### 7.1 Separate identities — PROPOSAL

Keep these concepts distinct:

- **admission request**: read-only verification; no campaign cell consumed;
- **pilot authorization**: human approval for the exact 20-cell plan;
- **host launch attempt**: durable per-cell host claim created before controller launch;
- **campaign claim**: existing `PolicyRunClaim` created inside the controller;
- **target execution**: one returned `RunResult`, including returned FAILED/TIMED_OUT status;
- **campaign terminal state**: current COMPLETED/FAILED/INVALID/STARTED/PENDING accounting; and
- **host terminal state**: whether launch, controller binding, cleanup and campaign cross-reference
  completed consistently.

The host must generate one unique attempt ID, record it before launch and pass it to the controller.
The existing controller-generated `uuid4()` must be removed in the later implementation so that the
host and campaign claims cannot name different attempts.

Proposed host states are `CLAIMED`, `CONTROLLER_LAUNCHED`, `CONTROLLER_NOT_CLAIMED`,
`CAMPAIGN_STARTED`, `CAMPAIGN_TERMINAL`, `HOST_COMPLETE` and `HOST_INVALID`. They are not replacements
for the existing `RunState` values.

### 7.2 Failure accounting

| Failure point | Raw record to retain | State | Execution-count treatment | Re-invocation handling | Human decision needed? |
| --- | --- | --- | --- | --- | --- |
| untrusted/malformed input before pilot record validates | caller-captured diagnostic only; do not write to an untrusted path | no admission, no host/campaign attempt | 0 target executions; not a no-hit | retrying corrected input is a new admission request, not an execution retry | no for a typo; yes if approval content changes |
| valid pilot record but N05/approval verification fails | no-overwrite admission-denial record in authorized host admission directory | `ADMISSION_REJECTED`; no host/campaign claim | 0; not failed campaign and not no-hit | may re-read repaired retained evidence only if bytes/digests remain within the same approval; otherwise new approval | yes for any changed approved identity/digest |
| host-attempt record exists; controller launch/transport fails | host `started`, stderr prefix, terminal and manifest; campaign reference absent | host `CONTROLLER_NOT_CLAIMED`; policy slot remains `PENDING` | 0 target executions; one host attempt consumed | no automatic retry under proposed default; new human authorization/disposition | **yes**; current contract is silent |
| controller starts but fails before campaign claim | same host ledger plus controller diagnostics; no `claim.json` | host `CONTROLLER_NOT_CLAIMED`; policy slot `PENDING` | 0; not a campaign no-hit | no automatic retry; the ledger prevents treating PENDING as untouched | **yes**; current contract is silent |
| campaign `STARTED`, then interrupted | existing claim + complete/incomplete journal prefix + host terminal | policy `STARTED`; host `HOST_INVALID` or campaign-started terminal | count only returned journal records; missing attempt is not synthesized | existing no-automatic-retry rule remains | new approval/disposition required for another attempt |
| target returns FAILED/TIMED_OUT normally | full `RunResult` in journal, then ordinary campaign terminal if campaign continues/completes | target status inside campaign; not infrastructure failure | consumes one of 200, exactly as current campaign code | campaign continues under current rules; no retry of the individual execution | no, unless a stop condition is met |
| cleanup fails | host cleanup errors/owned names plus campaign prefix/terminal | host `HOST_INVALID`; campaign evidence retains its actual state | returned results remain raw counts, but campaign is not admitted as an ordinary valid comparison | no automatic retry | yes before any further cell |
| campaign/host terminal evidence missing or corrupt | retain all no-overwrite prefixes; reader emits validation diagnostic | campaign `STARTED`/`INVALID` or host `HOST_INVALID` | only verified returned records count; never fill to 200 | no automatic retry | yes |
| all campaign and host terminal evidence valid | existing campaign evidence + host terminal cross-reference | campaign `COMPLETED`, host `HOST_COMPLETE` | exactly 200 seed-inclusive returned results | advance to next ordered cell | no new decision within already approved bounds |

The safe default proposed here is that creation of a per-cell host `started.json` consumes that
cell's one launch attempt, even if the controller never creates `claim.json`. This prevents the
current silent PENDING retry. Because the current pilot proposal did not explicitly choose this
boundary, the human pilot authorization must affirm or replace this rule.

The N04/N05 ledger publication pattern can be reused: no-overwrite started/terminal/manifest,
bounded controller stderr, deadline and cleanup fields. The N05 model itself cannot be reused as the
Track A schema because it hard-codes one preflight attempt, N05 paths/mode and an eight-extraction
terminal. Track A needs run index/ID, execution/plan/config/admission references and 20 distinct
per-cell ledgers.

## 8. Regression test specification

No test below requires a Docker daemon or historical target. Fixtures should use temporary
directories, canonical synthetic records and fakes whose Docker/controller/target methods raise
immediately if unexpectedly called.

Proposed function names are from this design. Existing reader names are exact.

| # | Input fixture | Manipulation/failure injection | Function to call | Expected exception/decision | Evidence that must remain | Forbidden side effect | Proposed test file |
| ---: | --- | --- | --- | --- | --- | --- | --- |
| 1 | valid-shaped pilot/N05 paths but expected digest `"a" * 64` unrelated to bytes | supply arbitrary format-valid digest | `validate_track_a_admission` | `VerificationError` for pilot authorization checksum | none before the authorization path is trusted; caller diagnostic | no host ledger, output root, Docker call or campaign claim | `tests/evaluation/test_track_a_admission.py` |
| 2 | synthetic N05 host/Linux roots | delete referenced raw/final file, then separately alter bytes without updating parent manifest | existing `verify_n05_host_ledger` through `validate_track_a_admission` | missing-file/checksum rejection | untouched original prefixes and admission denial after pilot path is trusted | no `freeze_track_a_execution`, launch or target | same |
| 3 | canonical N05 terminal fixture | set overall/final to INCONCLUSIVE/FAIL or leave Linux terminal incomplete | same | reject because overall is not `PREFLIGHT_PASS` | N05 roots unchanged; denial identifies observed status | no Track A root or campaign | same |
| 4 | individually canonical host and Linux fixtures | make host terminal final/raw digest point to different Linux manifest and recompute outer host manifest | existing host verifier | cross-reference mismatch rejection | both synthetic roots remain for diagnosis | no launch/target | same; reuse PR #114 N05 fixture builders |
| 5 | valid PASS-shaped fixture | set cleanup failed/errors, or remove cleanup field/terminal record | existing host verifier | incomplete/cleanup failure rejection or INCONCLUSIVE, never PASS | cleanup/error prefix and admission denial | no Track A root/launch | same; reuse `test_n05_preflight.py` cleanup fixture |
| 6 | otherwise valid admission | parameterize source, affected/fixed package/build/image, controller ID/image or daemon ID/version/API mismatch | `validate_track_a_admission` | exact identity mismatch rejection | trusted denial record with field category, not secrets | no output root/launch | same |
| 7 | otherwise valid admission | parameterize 5-second timeout, controller/target isolation, Linux machine/system, resource profile or runtime volume mismatch | same | environment/timeout/isolation mismatch rejection | trusted denial record | no output root/launch | same |
| 8 | retained N04 ledger/evidence fixture | put N04 attempt ID, mode, paths or N04 environment profile in N05 binding | pilot parser/admission validator | reject N04 reuse explicitly | denial record naming wrong contract class | no N04 mutation, launch or Track A root | same; reuse `test_n04_host_ledger.py` read-only fixture |
| 9 | valid canonical N05 preflight authorization (`pilot_authorized=False`) | pass its bytes/path as the pilot authorization | `pilot_authorization_from_bytes` | model/scope rejection | none at untrusted pilot-auth boundary | no N05 mutation, root or launch | same |
| 10 | no pilot authorization file or no trusted expected digest | omit one required input | host CLI argument validation and `validate_track_a_admission` | fail closed before N05 read | caller diagnostic only | no Docker lookup, evidence write or target | `tests/evaluation/test_track_a_admission.py` and focused host argument test |
| 11 | valid exact plan and authorization | reorder two cells; change one seed; set budget 199/201; alter plan digest in separate parameters | `validate_track_a_admission` plus existing `validate_track_a_plan` | plan/authorization mismatch | authorization fixture unchanged; optional trusted denial | no freeze/launch | same; reuse `test_track_a_exploratory.py` plan builders |
| 12 | valid admitted synthetic bundle | precreate Track A output; precreate same host-attempt directory; duplicate attempt ID in separate parameters | `freeze_track_a_execution` or proposed host-ledger `claim` | no-overwrite/duplicate-attempt rejection | existing bytes unchanged byte-for-byte | no second record, controller or target | `tests/evaluation/test_track_a_host_ledger.py` plus existing exploratory test |
| 13 | valid admitted next PENDING cell | claim host ledger, then inject `Popen`/transport/controller failure before campaign claim; invoke same cell again | proposed Track A host-attempt controller/reader | first terminal is `CONTROLLER_NOT_CLAIMED`; second call rejected as consumed | started/stderr/terminal/manifest; campaign slot still visibly PENDING | no target; no second host claim; no false failed campaign | `tests/evaluation/test_track_a_host_ledger.py` |
| 14 | existing repetition slot with durable claim and no terminal | call run-cell for same index | existing `read_policy_repetitions`, `execute_track_a_slot` and proposed host gate | STARTED/no-automatic-retry rejection | claim and journal prefix unchanged; host rejection/terminal retained | no new claim, target or prefix deletion | same; reuse `test_policy_repeated.py` STARTED fixture |
| 15 | complete canonical synthetic pilot auth, N05 host/Linux PASS records, exact identity/plan fixtures | no manipulation; fake every launch/target method with a forbidden-call sentinel | `validate_track_a_admission` | returns typed verified admission with all expected digests/identities | exact auth copy and/or synthetic admission result only at the explicitly tested publication layer | **no historical target, Docker, controller or `freeze` call** | `tests/evaluation/test_track_a_admission.py` |

### 8.1 Existing tests to reuse rather than duplicate

- PR #114 [`tests/evaluation/test_n05_preflight.py`](https://github.com/TheWaitForAGI/InodeFence/blob/f7aaa33050e247e0718d4ceb1ba01485802e269d/tests/evaluation/test_n05_preflight.py)
  already constructs synthetic N05 raw/final/host records and tests digest-only rejection, identity
  drift, cleanup uncertainty and host/Linux verification. Export small fixture builders into test
  support only if that reduces duplication; do not loosen its assertions.
- [`tests/evaluation/test_n04_host_ledger.py`](../../../tests/evaluation/test_n04_host_ledger.py)
  remains the regression source for consumed N04 records; Track A tests should import/copy fixture
  construction, never rewrite the retained N04 evidence.
- PR #108 [`tests/evaluation/test_track_a_exploratory.py`](https://github.com/TheWaitForAGI/InodeFence/blob/64a7a1645c03512d50ff5e0246108d297d1e6aa8/tests/evaluation/test_track_a_exploratory.py)
  already covers frozen schedule/plan drift and an unrun RAW ONLY finalization.
- [`tests/evaluation/test_policy_repeated.py`](../../../tests/evaluation/test_policy_repeated.py),
  [`test_policy_journal.py`](../../../tests/evaluation/test_policy_journal.py) and
  [`test_policy_timing.py`](../../../tests/evaluation/test_policy_timing.py) remain canonical for
  campaign claim, prefix, journal and timing semantics.
- [`tests/test_container_backend.py`](../../../tests/test_container_backend.py) remains canonical for
  contained target identity, timeout and cleanup behavior. Consumer tests must mock it rather than
  run a container.

For every negative test, assert both the expected exception and an explicit forbidden-call spy.
Testing only that an exception occurred is insufficient if Docker/output creation happened first.

## 9. Follow-up implementation units

These units are intentionally small and do not create a second runner.

### Unit 0 — Resolve the source-applicability gate

- **Candidate files/functions:** no code initially; record the decision in the N05/pilot Task
  Contract and authorization workflow.
- **Minimum interface change:** none.
- **Tests:** none.
- **Precondition:** a retained N05 result exists and its exact source SHA is known.
- **HUMAN DECISION:** exact-source re-preflight versus a separately reviewed compatibility contract.
- **Completion:** a written rule states whether the N05 evidence can bind the eventual consumer
  source. Under the current contract the answer is no when SHAs differ.

### Unit 1 — Typed read-only admission (first code unit after N05)

- **Candidate files/functions:** add
  `src/inodefence/evaluation/track_a_admission.py` with proposed
  `TrackAPilotAuthorization`, `N05EvidenceBinding`, `VerifiedTrackAAdmission`,
  `pilot_authorization_from_bytes` and `validate_track_a_admission`; add
  `tests/evaluation/test_track_a_admission.py`.
- **Minimum interface change:** none to the runner. Delegate to PR #114's
  `verify_n05_host_ledger`, `authorization_from_bytes` and `read_n05_preflight`, then produce one
  typed result. Do not accept standalone preflight/resource digest strings.
- **Tests:** cases 1–11 and 15 above, entirely synthetic and target-free.
- **Preconditions:** reviewed PR #108/#114 integration base and Unit 0 decision recorded. N05 PASS
  bytes may be used as read-only fixture input, but this unit does not authorize a campaign.
- **HUMAN DECISION:** exact pilot record schema/statement, trusted approval channel and source
  applicability.
- **Completion:** all identity mismatches fail before side effects; happy admission reopens and
  binds both authoritative N05 roots; no target path exists in the API.

Because Unit 1 changes the repository SHA, completion reopens the exact-source gate. Under the
current rule, the N05 source must then be re-reviewed/re-frozen and, if required, a newly authorized
preflight must be run before Unit 1's result can admit Track A.

### Unit 2 — Freeze verified admission into Track A evidence

- **Candidate files/functions:** modify `TrackAExecutionManifest`,
  `freeze_track_a_execution`, `read_track_a_execution` and the protocol's stale
  `ENVIRONMENT_PROFILE`; extend `tests/evaluation/test_track_a_exploratory.py`.
- **Minimum interface change:** replace two independent digest parameters with one
  `VerifiedTrackAAdmission`; add artifact references for copied pilot bytes, verified admission and
  N05 binding.
- **Tests:** cases 2–12 as applicable; reader must fail on removed/changed admission records and
  reject existing output roots.
- **Preconditions:** Unit 1, exact source/N05 applicability resolved, and final environment profile
  ID selected.
- **HUMAN DECISION:** authoritative Track A and host ledger paths; whether external N05 roots are
  retained indefinitely or copied to a separately frozen archive.
- **Completion:** final Track A reader can reconstruct every approval/N05 edge from actual bytes;
  no opaque digest-only path remains.

### Unit 3 — Host attempt ledger and attempt-ID propagation

- **Candidate files/functions:** add a small typed Track A host-ledger module under
  `src/inodefence/evaluation/`; modify `scripts/track_a_container_host.py` and
  `scripts/track_a_container_controller.py`; add
  `tests/evaluation/test_track_a_host_ledger.py`.
- **Minimum interface change:** host generates and persists the attempt ID, controller accepts it,
  and the existing campaign claim uses exactly it. Reuse N05 ledger publication patterns without
  reusing N05 hard-coded schema.
- **Tests:** cases 12–14 plus stderr/deadline/cleanup/cross-reference corruption.
- **Preconditions:** Unit 2 and human choice of host-claim consumption/retry semantics.
- **HUMAN DECISION:** whether host-ledger creation consumes one authorized cell attempt; this plan's
  default is yes and no automatic retry.
- **Completion:** every controller launch after admission has a durable terminal host record, and
  a pre-claim failure can no longer look like an untouched PENDING cell.

### Unit 4 — Final reader integration and protocol documentation

- **Candidate files/functions:** extend `finalize_track_a_execution`,
  `verify_track_a_final` and analysis admission reporting; update the Track A protocol/config docs
  only where schema fields require it.
- **Minimum interface change:** final manifest inventories local admission evidence and references
  all 20 host-attempt terminal records; analysis reports admission/host/campaign states separately.
- **Tests:** corrupt/missing/duplicate host record, incomplete finalization and completed synthetic
  20-cell metadata with no target execution.
- **Preconditions:** Units 1–3.
- **HUMAN DECISION:** which host-ledger copy is the publication authority.
- **Completion:** PENDING, pre-claim host failure, STARTED, infrastructure terminal and ordinary
  target status cannot be collapsed into one no-hit category.

## 10. Required order after implementation

The gate order is:

```text
retained N05 result
  -> Unit 0 source-applicability decision
  -> consumer implementation on a branch
  -> target-free regressions + canonical make check
  -> independent code/research review
  -> re-freeze/re-authorize/re-run N05 if exact source no longer matches
  -> separate canonical pilot authorization for exact integrated SHA and evidence
  -> admission-only synthetic check
  -> sequential pilot execution, if still explicitly authorized
```

The `make check` and independent review steps validate implementation, not execution permission.
The later pilot authorization must bind the final source and exact values from Section 6. It must
not be issued by code, inferred from CI, or copied from the N05 approval.

## 11. Design conclusions and unresolved decisions

### FACT

- PR #108 enforces the exact 20 × 200 seed-inclusive schedule and preserves campaign raw/prefix
  evidence, but its two authorization-related inputs are only format-checked digests.
- PR #114 supplies an actual canonical N05 authorization parser, Linux independent reader and
  host/Linux/cleanup verifier. The host verifier, not the Linux reader alone, is the PASS boundary.
- Current Track A host failures before campaign claim are not durably represented and can leave a
  slot apparently PENDING.
- The existing N05 contract uses exact source-revision equality and contains no compatibility rule.
- N05 and the Track A pilot remain NOT_AUTHORIZED / NOT_RUN.

### PROPOSAL

- Add one typed, read-only admission module that delegates to the existing N05 readers.
- Replace digest-only Track A freeze inputs with one verified admission object and immutable source
  records.
- Add a distinct per-cell host attempt ledger and pass one host-generated attempt ID through to the
  existing campaign claim.
- Keep N05 authoritative evidence external and immutable while preserving complete typed references
  and small canonical authorization/manifest copies in Track A evidence.

### HUMAN DECISION

Before implementation can open the execution gate, people must decide:

1. whether an N05 result from a pre-consumer SHA must be repeated on the integrated SHA; the current
   exact-SHA contract says it cannot be silently reused;
2. the canonical pilot authorization text, reviewer/trust route and exact file/source scope;
3. the new N05-qualified Track A environment profile ID and authoritative host/output paths;
4. whether host-attempt claim consumes a cell before controller/campaign claim, and the exact
   reauthorization rule after such a failure; and
5. retention/publication ownership for the external N05 and Track A host ledgers.

Until those decisions, implementation, N05 PASS and pilot authorization all remain separate gates.
Nothing in this design is `PREFLIGHT_PASS`, an attempt ID, an image freeze, a human approval or an
experimental result.
