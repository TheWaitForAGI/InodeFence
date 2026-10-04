# Final Runtime / Execution / Integration audit v1

**Phase 4A — Runtime lane GO.** CR-001, CR-002, EX-003 and the uncounted EX-004
regression recommendation are CLOSED on the integrated production tree. No new
Blocker, Major or Minor was established. Six historical Notes remain valid; one
residual documentation Note is recorded below. This recommendation concerns the
execution/evidence foundation, not benchmark effectiveness or global closeout.

## 1. Audited revision and starting gate

- Repository: `TheWaitForAGI/InodeFence`; audit date: 2026-10-04.
- Audited integrated main: `d1982e4cf3174e28d4eeb73af7b32829f6751b30`.
- Its parent is Runtime #45, `adb43c01bd3de0d6eff578b2294c77dd479836f7`; the
  integrated tip contains Engine #46. Both were inspected independently of their
  PR descriptions.
- `git fetch origin`, `git switch main`, `git pull --ff-only`, `git rev-parse HEAD`
  and `git status --short` succeeded in the requested order. HEAD equaled the
  canonical SHA and status was empty before creating
  `audit/final-runtime-integration-v1` directly from main.
- Task Contract: the maintainer's supplied Phase-4A final re-audit specification.
  The repository Issue list was empty; this explicit contract controls scope.
- Validation-time branch HEAD was the audited SHA with only audit test changes.
  The final artifact commit is the audit PR tip. No production/config/worker,
  fixture, dependency, architecture, STATUS or PR #35 changes are included.

Frozen historical evidence was read at Runtime Phase-2
`f00d6dfb26b47447210341d2c77bc642cc6f20b7` and Engine Phase-2
`42c2afcc4e88d045e94248882311f5c360159016`. These are evidence inputs, not branch
ancestors or current-production assertions. Global Findings Freeze v1 remains the
historical 0 Blocker / 2 Major / 7 Minor / 6 Note / 1 uncounted regression gap;
this document supplies only the assigned lane's final dispositions.

## 2. Scope and evidence method

Reviewed Node binding, composed execution, backend image/container inspection,
Docker CLI/broker lifecycle, Campaign admission/freeze, ExperimentConfig,
ExecutionProvenance, completed export, pipeline/observer/Oracle and Engine v3
signature/public-model/builder integration. The security-contract review skill
and [Security Contract](../research/design/security-contracts.md) supplied the
observation/evidence separation criteria.

Evidence combines source inspection, existing post-fix regressions, 61 added
audit test cases, and the canonical actual container path. New fixtures use
controlled disposable filesystem effects, a trusted Python reference, mocked
backend observations or benign fork/pipe helpers. They do not use exploit TARs,
known PoCs or vulnerable targets. Synthetic process statuses are identified as
such; real target-stop evidence comes from the separate container suite.

## 3. Phase-3 verification matrix

| Historical item | Frozen class | Final disposition | Independently verified evidence |
| --- | --- | --- | --- |
| CR-001 | Major | **CLOSED** | Direct/replaced/other-image declarations fail both Campaign APIs; standalone claims fail; actual image mismatches fail; stale probe after step 1 aborts step 2 before BEFORE; forged supplied origin/digests fail; real Node replacement negatives and frozen manifest origin pass. |
| CR-002 | Minor | **CLOSED** | Actual inspected Entrypoint/Cmd/WorkingDir/Env match request/policy before yield/start; omission, extra argv/env, duplicate/ambiguous env and malformed representation fail; Env ordering and empty Cmd null/[] pass. |
| EX-003 | Minor | **CLOSED** | Frozen exited-parent/pipe-descendant deadline witness passes; new error-path and ESRCH-race counterparts kill the owned group/reap primary and preserve an unrelated group; denied signal remains bounded infrastructure failure; timed-out exit-zero cannot succeed. |
| EX-004 | Uncounted regression gap | **CLOSED** | Existing strengthened tests observe actual stream/syscall order, staging and parent fsync, readback validation and no-replace publication; injected pre-publication failures do not publish. No production durability defect was established. |

## 4. CR-001 — artifact authenticity and attestation

The supported Node path is
`NodeTarTarget.bind/descriptor → IsolatedTarget → inspected backend identity probe
→ capture_isolation → Campaign freeze/admission → ExecutionProvenance →
CampaignResult → manifest v4`. `NodeTarTarget.artifacts` explicitly means expected
digests. [IsolatedTarget](../../src/inodefence/targets/isolated.py) owns probe
execution, and [Node verification](../../src/inodefence/targets/node_tar.py) parses
captured output into an observed identity and requires exact descriptor equality.
This runs before campaign freeze and before every prepared/standalone archive.

Image inspection checks the actual Linux image ID, rejects implicit volumes, and
prepared-container inspection again compares its image to the requested immutable
ID. Backend capture must equal the wrapper's configured policy. The new
`test_final_cr001_actual_image_mismatch_prevents_start` challenges both inspections.

The converted six declaration witnesses in [Node tests](../../tests/test_node_tar.py)
cover direct construction, dataclass replacement and same-version other-image
rebinding through configured and unconfigured Campaign. A matching ExperimentConfig
only binds declared target/policy and cannot waive the probe. Standalone worker,
lock and version mismatches also fail. Added tests prove that an apparently valid
supplied v2 origin with false digests cannot replace captured isolation, and that
probe drift after one complete step prevents second-case execution/BEFORE and
returns no completed CampaignResult. Nonempty artifact declarations without an
observation protocol fail in the generic wrapper.

IsolationProvenance v2 requires `artifact_origin=image-identification-v1` for
nonempty observed artifacts; no-artifact records require null. Historical v1 is
rejected by the current constructor, as independently tested in the new audit
module. No reader/migration silently upgrades old JSON. The canonical export
serializes stored provenance without re-querying or promoting declarations. Real
Node negatives reject independently replaced worker/lock digests before extraction;
the actual configured campaign preserves verified digests/origin/image ID through
manifest v4.

**CR-001: CLOSED.** Runtime/image contents, probe implementation, descriptor
implementation and selected backend remain trusted controller mechanisms. This is
not independent verification of malicious replacement controller/probe code.

## 5. CR-002 — actual invocation verification

[Container preparation](../../src/inodefence/execution/container.py) requires all
four inspected Config fields before yielding: Entrypoint equals the one requested
executable, Cmd equals the remaining argv, WorkingDir equals the current run's
extract directory, and Env equals the image-cleared PATH/LANG policy. Generated
argv is the expectation; inspected Config is the evidence checked against it.

[Backend regressions](../../tests/test_container_backend.py) challenge each missing
field, changed executable/arguments/CWD, extra entrypoint/Cmd arguments, added and
changed environment entries, inherited nonempty image values, identical duplicates,
conflicting duplicate keys, non-list Env and non-text Env members. Every negative
fails during preparation, starts no target and removes its owned context.
Environment order is intentionally ignored. Empty Cmd accepts only the documented
Docker null/[] forms when there are no remaining arguments; both forms are now
explicitly tested. Actual helper/Node checks confirm the supported Docker behavior.

**CR-002: CLOSED.** No additional invocation architecture or future-target CWD
feature is inferred or implemented.

## 6. EX-003 — Docker CLI descendant lifecycle

[DockerCLI.run](../../src/inodefence/execution/docker_client.py) starts its own
session, applies the deadline to draining and waiting, then signals its group
before polling/reaping the primary on incomplete/error paths. An unreaped exited
primary pins the group ID. A primary already reaped by successful wait is never
signalled later. Explicit bounded wait/pipe close avoids an unbounded Popen context
exit after denied signalling.

[Lifecycle tests](../../tests/test_docker_cli_lifecycle.py) rerun the historical
benign parent-exits/child-holds-pipe witness. They verify bounded timeout, stopped
descendant, reaped direct primary and survival of an unrelated same-user group.
New error-path witnesses confirm the primary's zombie state without reaping it,
inject a pipe error, then verify the same ownership/termination properties. A
controlled already-stopped-group ESRCH race is also accepted safely. ENOENT/ESRCH
inspection races are absence, live-descendant evidence fails, and PermissionError
propagates. Denied kill is a bounded BackendError with a still-live primary, never
fabricated cleanup completion. Backend `checked` and the exit-zero timeout regression
prevent timeout from becoming SUCCESS.

**EX-003: CLOSED.** These tests concern trusted CLI transport groups. Actual target
PID-context teardown remains separately enforced/validated by the container backend.

## 7. EX-004 — export durability regression coverage

[Export tests](../../tests/test_campaign_export.py) observe writes, stream flushes,
actual file fsync calls, readback validation, actual staging-directory fsync,
publication and parent-directory fsync, with and without configuration. The final
three events are staging sync → publication → parent sync. Each file's writes
precede flush → file fsync → readback. Publication uses actual Linux
`renameat2(RENAME_NOREPLACE)`; concurrent empty/existing destinations stay intact.

Failures of each file fsync, corrupted steps/manifest/config, encoding/write errors,
unsupported publication and staging-directory sync leave no invalid final bundle.
Parent sync failure is different: publication has already made a complete valid
bundle visible, the exporter raises, and durability success is not returned.

**EX-004: CLOSED as the uncounted regression recommendation.** Atomic visibility
occurs at publication; crash/power-loss durability depends on the separate syncing
protocol and filesystem/runtime assumptions. Tests establish calls/order/error
behavior, not power-loss recovery. Production export was not changed or promoted
back into a defect.

## 8. Engine / Runtime integration

| Integration seam | Current integrated result |
| --- | --- |
| StateSignature v3 | Pipeline emits v3; public constructor rejects v2; Campaign/Corpus hashing, entry admission and canonical export accept v3. Forty new status/effect cases preserve v3 and full raw snapshots; actual Node campaign explicitly verifies v3 before and after export. Existing tagged symlink/cross-run/raw-evidence regressions pass. |
| Current version assumptions | No executable signature producer/consumer requires v2. Isolation v2, config v2 and canonical envelope versions are separate schemas. The legacy `FEEDBACK_POLICY` identifier contains `state-v2`, but is a supported stable policy string, not a signature-schema check; configured v3 execution/export passes. Residual documentation shorthand is RT-N01 below. |
| Strengthened evidence validation | Real reference and contained Node outcomes satisfy ExecutionResult, ObjectSnapshot/StateSnapshot, exact StateChange, SignatureObject/StateSignature, ViolationFingerprint, FeedbackDecision and CorpusEntry validators. New status/effect tests replay Corpus admission and compare stored snapshots/signature to full raw model values. No permissive-constructor dependency was reproduced. |
| Signature/observation failure | Injected BEFORE/AFTER failures and signature-construction ValueError propagate. Partial observations stay provisional; no RunResult reaches Corpus and no completed CampaignResult/security verdict is returned. Cleanup still happens. |
| EN-001 builder rejection | All four entry types with the explicit frozen lossy absolute-path input fail before sandbox creation, target invocation or capture. Corpus observations remain zero. No target SUCCESS/REJECTED result, AFTER evidence or admission is fabricated. Ordinary reference and four real Node baselines still run. |

The new [audit module](../../tests/audit/test_final_runtime_integration_v1.py)
contains the forty status/effect integrations, four pre-execution builder guards,
three infrastructure-failure guards and historical v1 provenance guard. Additional
tests extend the existing backend, Node and CLI modules. No generic Oracle,
mutation, RNG, budget, feedback policy or builder implementation changed.

## 9. Observation lifecycle

Source and the new prepared-target canary trace preserve:

```text
setup → input write → prepare/identity verification → BEFORE
      → target execution → fully stopped → AFTER
      → pure comparison/signature/Oracle → bookkeeping/container cleanup → sandbox cleanup
```

Current pipeline/adapters keep diagnostics in pipes/memory and write no harness
namespace bookkeeping between captures. The canary test puts setup into BEFORE
and post-run bookkeeping after AFTER; neither becomes a target effect. Synthetic
target effects are the only controlled writes in its observation window.

Every classified SUCCESS/REJECTED/FAILED/TIMED_OUT result receives AFTER if capture
succeeds. Real container tests verify stop/PID0/exited before return, detached
child/grandchild teardown, timeout, actual AFTER failure cleanup and runtime cleanup.
A created-at-deadline container is removed and absence-verified before AFTER to
exclude delayed start; this changes container bookkeeping, not observed run paths.

Infrastructure, identity, output truncation, observer and cleanup exceptions propagate;
a provisional RunResult is not returned if context exit fails. An aborted campaign
does not return a completed no-hit result. On uncertain stop/transport loss, cleanup
can fail or partial state can be lost: EN-010/EX-006 remain explicit limitations.
The disposable runtime root is the cleanup boundary. The enforced container
policy/view is the execution isolation boundary. Snapshots infer attribution from
this lifecycle; they do not independently identify actors.

## 10. C0 / C1 / C2 integration sanity

The forty new safe cases run all four execution statuses against ten filesystem
outcomes. C0 detects archive/HARNESS creation, deletion, identity replacement and
type replacement, plus sentinel namespace loss/replacement outside `extract/**`.
C1 detects controlled extraction/sentinel `(st_dev, st_ino)` sharing. C2 detects
sentinel deletion, identity, content, mode and alias-induced nlink/ctime changes.
Benign unchanged snapshots produce no evidence; content/mode-only effects are
C2 rather than invented C0 namespace transitions. Raw identities and input digest
remain in snapshots/export while HARNESS is excluded from signature objects.

Expected verdict tuples, snapshot lifecycle, fingerprints, Corpus stats/admission
and export preservation pass for SUCCESS, REJECTED, FAILED and TIMED_OUT alike.
[Oracle source](../../src/inodefence/oracle/contracts.py) has no execution-status
input or gate. Existing observer/Oracle metadata, symlink and reference rejection/
partial/timeout regressions also pass. No Oracle semantics were redesigned.

## 11. Historical Notes / limitations

| Note | Phase-4A disposition | Evidence / practical limit |
| --- | --- | --- |
| EN-007 | Still-valid limitation | Seed/mutation vocabulary still cannot introduce default sentinel addressing; no grammar/setup feature was added and no rediscovery inference follows. |
| EN-008 | Still-valid research risk | Content/path diversity can increase state novelty; v3 removes a representation collision, not the unmeasured usefulness risk. Six benign states are representation counts. |
| EN-009 | Still-valid accepted semantics | Fingerprints remain aggregate contract-evidence classes, not unique behaviors/bugs; new integrations preserve full raw records separately. |
| EN-010 | Still-valid limitation | No general abort ledger, full campaign/step timing, operator trace or replay/adjudication reader. Failed infrastructure still cannot manufacture completed evidence. |
| EN-011 | Still-valid scope/coverage limitation | Persistent snapshots, no actor/transient/referent tracing; selected guard/lifecycle coverage is stronger but capacity and all traversal/hash failure branches remain unqualified. |
| EX-006 | Still-valid trusted-broker availability limitation | Stdio response readline has no independent deadline. Extra identity contexts require more broker progress; no new correctness failure or unconditional availability guarantee was established. |

None was resolved, invalidated or materially worsened into a new defect by Phase 3.
Image/probe/controller/runtime/kernel trust, no total file/storage/CPU quota, dirty
patch non-retention and portability remain the documented foundation limits.
EN-006 / PR #35 disposition belongs to global closeout; PR #35 was untouched.

## 12. New findings

**New Blocker 0 / Major 0 / Minor 0 / Note 1.**

**RT-N01 — residual signature-version navigation shorthand (Note).**
[START_HERE's module map](../START_HERE.md) and
[engine module map](../../src/inodefence/README.md) still say `signature v2`, while
the detailed model/feedback/design contract and running pipeline use v3. Current
status also retains feature-branch Phase-3 review wording after integration. This
is a bounded navigation/global-closeout refresh item, with no executable v2 gate,
false artifact fact or fabricated verdict established. The frozen EN-005 three
exact capability paragraphs were corrected; this note does not reopen a Runtime
finding. The audit leaves those maps/status and PR #35 unchanged.

## 13. Validation commands and results

Environment: existing Ubuntu 24.04.3 Dev Container, Python 3.12.3
(`/opt/venv/bin/python`), non-root uid/gid 1000, source `/workspaces/InodeFence`,
runtime `/var/lib/inodefence` on the named Linux volume, Linux
`7.0.14-orbstack-00380-ga7e0a2dc9535`, aarch64/glibc 2.39. Host broker: macOS 27.0.1
arm64, Python 3.12.14, Docker 29.4.0/API 1.54, context `orbstack`. Dev Container
privileges were unchanged; the controller receives no Docker socket.

Focused command inside the Dev Container:

```bash
python -m pytest -q tests/audit/test_final_runtime_integration_v1.py \
  tests/test_node_tar.py tests/test_container_backend.py tests/test_docker_cli_lifecycle.py \
  tests/test_isolation_provenance.py tests/test_experiment_config.py tests/test_campaign_export.py \
  tests/test_pipeline.py tests/test_campaign.py tests/test_evidence_validation.py \
  tests/test_state_semantics.py tests/test_feedback_corpus_integration.py tests/test_builder.py
```

| Validation | Result |
| --- | --- |
| Initial Runtime-focused selection | 221 passed, before new audit tests |
| Final focused selection above | **600 passed**; includes new cases and existing post-fix regressions |
| New audit cases | 61 total: 48 in audit module, 2 Node, 9 backend and 2 CLI; all pass |
| `make check` in Dev Container | **PASS; 864 pytest tests passed**, zero skips/failures |
| Lint / format / type | Ruff PASS; 150 Python files formatted; Pyright 0 errors / 0 warnings |
| Environment check | PASS: Linux runtime, hardlink, symlink and shared-object effect |
| Docs check | PASS; 64 Markdown files including this report |
| `git diff --check` | PASS |
| Production-scope diff against audited SHA | Empty for src/scripts/tools/config/CI/build files |
| Actual container integration, separately collected | **19 passed**: boundary 6; Node image 2; Node target 10; benign configured campaign 1 |

The helper and Node images were rebuilt using their canonical pinned Dockerfiles.
Execution received actual inspected immutable IDs:

- Helper: `sha256:e7ea1eb6cc7ed49b6543e7f4751930bafadfcf68841514515da058b9b762b910`.
- Node: `sha256:c0dde2b06b3cd079d7922960a05e8a84e26f2d1121ea8cad05691a4f104b8636`.

All four canonical modes in [container_host](../../scripts/container_host.py)
were executed with host `PYTHONPATH=src python3.12 -m scripts.container_host`,
`--context orbstack --controller 5125569b07fa --volume inodefence-runtime`, and the
appropriate ID: `validate`, `validate-node-image`, `validate-node-target` and
`--evidence /tmp/inodefence-final-runtime-integration-v1-20261004-evidence benign-node-smoke`.
No unavailable-runtime skips were used.

The configured smoke used seed 11/budget 8 and ordinary minimal seeds. Result:
SUCCESS 8; Corpus observations 8 / interesting 6 / retained 6 / unique states 6 /
fingerprints 0; observed violated C0/C1/C2 verdicts 0; v3 signatures 8/8;
containers removed 18/18 (10 identity + 8 archive contexts); runtime cleanup PASS.
Source provenance correctly records the audited SHA with `dirty=true` for audit-only
test changes. An empty production diff establishes the exact production tree tested.
The captured BEFORE/AFTER TAR digests survive export unchanged.

Raw local evidence is retained at the above controller path and copied to the
same host `/tmp` path. It is engineering evidence, not a repository benchmark bundle.

| Artifact | SHA-256 |
| --- | --- |
| Config ID (canonical JSON without file newline) | `87b40ab717b9210248e26df31f9fbc94f556eed361302809cf24d808ee78d3d3` |
| experiment.json | `7c3cc771db5070499a5b0640f60d14682d1f9a051f5b4b6acb92f1901f316069` |
| manifest.json | `0d6c3a4b4d2057712368617803cdd54dae61c9afe7513017c73806533ea49182` |
| steps.jsonl | `1f6fc0fb4aa03f445bdddcba7e205d043da23e4b36c36878d92745a5a11cd0fc` |
| Observed package-lock | `28dc7696eda4a36462e927d5d42c1e764646631aed21d3e004999a7c24db8930` |
| Observed worker | `feb13d7be5f5718769bebd4b0e375ea3f535abffd45223494dd518263593498b` |

## 14. Runtime-lane recommendation

**GO:** the Runtime / Execution / Evidence foundation on the audited integrated
main is suitable for Phase-4 global closeout and later benchmark implementation.
All four assigned historical items are CLOSED, and no new Blocker/Major/Minor or
Engine/Runtime evidence regression was established. Retain the Notes and trust/
scope limits in subsequent research planning. This audit neither proves benchmark
effectiveness nor starts benchmark implementation/execution. The audit PR targets
main and must remain open, unmerged, with auto-merge disabled.
