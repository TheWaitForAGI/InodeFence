# Track A final-state exploratory feasibility protocol v1

**Date:** 2026-10-16

**Status:** FROZEN METHOD / RESOURCE AUTHORIZATION NOT RECORDED / PREFLIGHT NOT_RUN / PILOT NOT_RUN

**Preparation base:** `main` `21e317281a2d2a7faf6198f66302f3912b429011`
**Machine-readable protocol:**
[`track-a-final-state-exploratory-feasibility-v1.json`](../../../experiments/configs/track-a-final-state-exploratory-feasibility-v1.json),
SHA-256 `88ed4fde6e3f926099a9e28d978b583c5eedcb4b4074b37a4b1e7bca1c26f19c`.

This is the separately versioned exploratory path allowed by the prospective N04 proposal in
PR #106. It does not amend the N03 historical pilot, satisfy the N01 human correspondence
gate, authorize target execution, or classify a machine match as confirmed rediscovery.

The target-free Unit 2 implementation preserves a separately validated pilot authorization and
N05 v2 references under the Track A root, but does not connect the host/controller prepare path.
The old digest-only prepare arguments are explicitly rejected. This is engineering evidence only;
N05 and the pilot remain **NOT_RUN**.

## 1. Objective and claim boundary

The protocol asks whether the existing final-state B0/B1/B3 path can complete a bounded,
reproducible 20-cell run against the exact node-tar pair while preserving adequate raw
evidence, cost measurements and independent-reader inputs. It may report:

- generic persistent C0/C1/C2 observations;
- state/fingerprint discovery and corpus behavior;
- target outcomes, full-step cost, controller process-lifetime HWM and storage volume;
- deterministic N01-like candidate nominations for later separately budgeted replay; and
- descriptive, exploratory affected-B0/B1/B3 differences.

It may not report historical qualification, confirmed known-class rediscovery, statistical
superiority, central intermediate-state hypothesis support, a new vulnerability, or release
safety. State novelty and violation-fingerprint novelty are not vulnerability counts. P0/P1/P2
and v3 entry-effect observation are out of scope.

## 2. Two independent authorization gates

This prompt is not resource authorization. Before any target launch, the project owner must
record a bounded **5-second Preflight authorization**. Before plan creation or any campaign,
the owner must separately record a **4,000-execution pilot authorization**. Each authorization
record is an external immutable artifact. The initial admission receives the expected pilot digest
and approval reference from a human-controlled route, then reopens the exact pilot and authoritative
N05 host/Linux evidence. Freeze copies the exact pilot bytes and binds the local admission records
into `execution.json`. Retained digests preserve the selected evidence graph; they do not by
themselves authenticate the named human.

The exact clean execution Git SHA cannot be self-embedded in a Git-tracked file. After the
implementation stack is reviewed and before the first campaign, the admission and eventual Track A
`prepare` path must bind the clean full Git SHA into immutable evidence. Unit 2 binds the exact
pilot authorization, N05 reference, protocol JSON and repetition plan; the unconnected prepare path
remains disabled. No campaign may run from a different or dirty checkout.

## 3. Phase R read-only audit

Before authorization, only read-only audit is permitted:

1. Verify `origin/main`, active PR refs and a separate clean Track A worktree.
2. Check retained N02 evidence availability; inaccessible data is `HOST_RAW_NOT_ACCESSIBLE`,
   never PASS.
3. Compare lock and worker bytes with the historical digests without building or executing.
4. Check whether the exact immutable images and trusted runtime are inspectable. A historical
   report is not current 5-second admission.
5. Recompute the four benign case/TAR identities and review the policy/reader paths.

The current audit result is recorded in
[Track A read-only audit](../diagnostics/track-a-read-only-audit-2026-10-16.md).

## 4. Exact target and environment candidate

| Field | affected | fixed |
| --- | --- | --- |
| Node / node-tar | 22.22.0 / 7.5.2 | 22.22.0 / 7.5.3 |
| npm tarball SHA-256 | `22d8b674a68754ea909d03aa13958a7d2fd5e78af8a8f0cde6455babef7aaf1a` | `9d95d0cf786786360f97c1e414caea8a14452dc337fda17ba256ae7762c2ec66` |
| lock SHA-256 | `31792107e9442ab18b04661d10ca0a0053db1fb7c58ca3aa702f1abb9908e243` | `a63d02f09d9a9fb2def77da84d5145984ff260fcedd19839ba96ec858fdfae24` |
| image ID | `sha256:8b44887734511dbe9462f9b82f1c3128a8b445ebab2fa9b8db3fadcbc659c520` | `sha256:ed428826dd4b561f5b23035539137f0e7fe86c03c92eb5c7cae54a684fc7880f` |
| arm64 manifest | `sha256:b5ae7f5d2f85f12fa417ecece3e9089001266cc6bf4a997724c225a40ce8b542` | `sha256:3a1bcf4dffcd21ddc4fa6645980bebd96dceda4ceee0ddfe033abd0d50dd6ee0` |

Both images must report worker SHA-256
`feb13d7be5f5718769bebd4b0e375ea3f535abffd45223494dd518263593498b`.
The exact environment profile is `n05-arm64-orbstack-five-second-v2`. The trusted controller and
target runtime must be Linux arm64/aarch64, non-root UID/GID 1000,
network `none`, read-only rootfs, all capabilities dropped, no-new-privileges, private
PID/IPC/cgroup namespaces and one fresh volume subpath per input. Source and runtime volume
must remain distinct.

Per-target-container bounds are exactly 512 MiB memory and swap, 64 PIDs, 1,024 open files,
64 MiB file size, 32 MiB `/tmp`, 16 MiB shared memory and 1 MiB captured bytes per stream.
The target timeout is exactly 5.0 seconds. A campaign has a separate 7,200-second host
watchdog. `linux-proc-self-vmhwm-v1` records controller process-lifetime peak RSS; it is not
target memory or a campaign delta.

Current historical IDs are candidates until an authorized Preflight observes them through
the current controller/runtime. Image, package, lock, worker, architecture, containment or
timeout mismatch is a STOP, not a reason to rebuild silently or switch to 10 seconds.

## 5. Authorized 5-second Preflight prerequisite

The pilot requires a fresh, independently read N05 v2 Preflight manifest and complete host ledger.
They must bind the same clean source SHA, both exact images/artifacts, current
controller/runtime/volume, all isolation/resource fields above, unchanged negative and harness
positive oracle controls, all four benign seeds on both targets at 5 seconds, cleanup and an
independent reader result. The known positive-control TAR is not a Preflight seed.

Any failed/missing/mismatched check preserves its partial evidence and blocks plan creation.
No Preflight result existed in the current environment when this protocol was prepared.

## 6. Frozen input, policies, schedule and output

The initial corpus is the ordered `minimal_seed_corpus()` with IDs:

1. `c56da02197b3e8959e46c08c476c7fb15a13763ce9d8d57ac5151f4b1d709fd8`
2. `cdcc8045e37293498ff2d8e69e6e5638ee470f1bd11b1d0b8f16f1f9e783208f`
3. `de8ddc5ca4c15fccb638257bbbe671c4fcc9c707962cb92de6589a09f6418620`
4. `842bdde9b083096d6f5f1c93c93efb3ff35d141b7311571dab281c771d83c0d1`

All cells use `uniform-generic-m1-protected-components-v1`, deterministic USTAR v1, full
StateSignature v3 projection, unchanged final persistent C0/C1/C2, default controlled
`outside/sentinel.txt`, five-second target timeout and 200 seed-inclusive executions. Campaign
seeds are 9001–9005. Scheduling seed 4242 has already produced this immutable order:

| Position | Run ID | Position | Run ID |
| ---: | --- | ---: | --- |
| 0 | `n01-affected-b3-9002` | 10 | `n01-fixed-b3-9002` |
| 1 | `n01-fixed-b3-9003` | 11 | `n01-affected-b0-9003` |
| 2 | `n01-affected-b3-9004` | 12 | `n01-affected-b3-9001` |
| 3 | `n01-affected-b1-9003` | 13 | `n01-affected-b3-9005` |
| 4 | `n01-fixed-b3-9001` | 14 | `n01-affected-b1-9002` |
| 5 | `n01-fixed-b3-9005` | 15 | `n01-affected-b0-9005` |
| 6 | `n01-affected-b1-9001` | 16 | `n01-affected-b0-9004` |
| 7 | `n01-fixed-b3-9004` | 17 | `n01-affected-b0-9001` |
| 8 | `n01-affected-b3-9003` | 18 | `n01-affected-b0-9002` |
| 9 | `n01-affected-b1-9005` | 19 | `n01-affected-b1-9004` |

The only Track A raw root is
`/var/lib/inodefence/evidence/track-a-final-state-exploratory-feasibility-v1`.
It must not exist before plan freeze and is never overwritten. Exact pilot authorization bytes are
copied locally; the authoritative N05 host/Linux roots are referenced and must remain reopenable.
Large N05 raw evidence is neither copied into nor pooled with Track A evidence.

## 7. Execution and STOP semantics

Unit 2 provides only the target-free library freeze/reader boundary. The host/controller `prepare`
entry points reject both preparation and the legacy preflight/resource digest arguments before
Docker inspection or controller launch. No replacement host command is enabled in this unit.
Host-attempt durability and admission transport are Unit 3 work; until then, `prepare` and
`run-cell` must not be invoked for a real campaign.

The existing runner executes all 200 cases after target returns, including seed, no-op,
duplicate, rejection, failure and timeout results. A generic observation never stops a
campaign. Infrastructure exceptions create FAILED evidence; hard interruption leaves STARTED
with its readable prefix. Either state blocks later cells. Unsafe containment, configuration
drift, cleanup uncertainty, output loss, watchdog expiration or resource mismatch is a STOP.

At normal completion or STOP, `finalize` inventories every available regular evidence file
with path, size and SHA-256 and writes `final-manifest.json` last. An incomplete finalization
requires an explicit stop reason. Finalization prevents further Track A execution.

```bash
PYTHONPATH=src python -m inodefence.evaluation.track_a_exploratory finalize \
  /var/lib/inodefence/evidence/track-a-final-state-exploratory-feasibility-v1 \
  --execution-sha256 <trusted-execution-sha256> [--stop-reason <reason>]
```

## 8. Evidence and independent reader

Per-step policy journals retain the full `RunResult`: exact case/TAR, mutation attempt and
parent, target result, before/after snapshots, C0/C1/C2, StateSignature, feedback/admission and
cleanup-complete return boundary. Completed campaigns additionally bind full-step monotonic
timing and immutable completed policy bundles. The repetition ledger retains PENDING, STARTED,
COMPLETED, FAILED and INVALID slots; every terminal slot requires controller-memory evidence.

Independent verification is fail-closed:

```bash
PYTHONPATH=src python -m inodefence.evaluation.track_a_exploratory verify \
  /var/lib/inodefence/evidence/track-a-final-state-exploratory-feasibility-v1 \
  --final-manifest-sha256 <trusted-final-manifest-sha256>

PYTHONPATH=src python -m inodefence.evaluation.track_a_exploratory analyze \
  /var/lib/inodefence/evidence/track-a-final-state-exploratory-feasibility-v1 \
  --final-manifest-sha256 <trusted-final-manifest-sha256>
```

The reader reopens the exact local pilot bytes, retained admission record, N05 reference,
authoritative N05 host/Linux roots, protocol/config/plan/journal/timing/memory evidence, verifies
the complete file inventory, reconstructs mutation/search decisions and enumerates N01 nominations from
every completed raw mutation step of completed affected campaigns. A failed/interrupted prefix
still reports generic N01-like C1 occurrences but is not promoted to a completed matcher
nomination. Candidate 3+3 replay remains a separately authorized validation budget.

## 9. Frozen analysis definitions

The derived JSON reports all requested denominators and no automatic exclusions:

- scheduled/completed campaigns and actual/planned executions by arm;
- attempted/applied/no-op mutation operator counts;
- per-campaign cumulative unique StateSignature and violation-fingerprint curves, with arm
  summaries at executions 4, 25, 50, 100, 150 and 200;
- C0/C1/C2 observed-execution counts and machine candidate nominations;
- full-step median and nearest-rank p95 seconds for completed campaigns;
- controller process-lifetime peak bytes and raw evidence bytes;
- rejection, timeout and infrastructure state/rate accounting; and
- first 1-based execution containing any generic C0/C1/C2 violation, or null.

The affected B0/B1/B3 table is descriptive only. No inferential significance test is
predeclared for five seeds. Fixed B3 is target inventory/discrimination context, not another
feedback arm. If the final dataset is incomplete, the reader labels it `RAW ONLY`; a complete,
checksummed, independently readable first execution also remains `RAW ONLY` until same-condition
reproduction supports promotion to `REPRODUCIBLE`. It is never automatically a
`VALIDATED FINDING` or `PAPER-READY EVIDENCE`.

## 10. Current decision

Current-host status is **BLOCKED_BEFORE_PREFLIGHT / NOT_RUN**. The method and software
path are prepared, but the required arm64 runtime/images, N02 raw root, 5-second Preflight
authorization/result and 4,000-execution resource authorization are absent here. No plan,
qualification token, target result or experimental number has been fabricated.
