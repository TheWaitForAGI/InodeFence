# N01 contained affected/fixed pair qualification v1

Status: **TECHNICALLY_REVIEWED / HUMAN_AUTHORIZATION_RECORDED /
HISTORICAL_IMAGES_NOT_BUILT / NOT_EXECUTED**.
The exact bounded qualification described here is authorized. Historical image build and
execution still require every technical admission and containment precondition below; no
fuzzing campaign or broader target/scope is authorized by this document.

## Research purpose and claim boundary

This contract prepares one contained, same-input qualification of node-tar `7.5.2` and
`7.5.3` for the N01 relative-hardlink arm associated with CVE-2026-23745. Its narrow question
is whether the two frozen releases produce the expected persistent C1 identity difference on
Linux under identical input, setup, worker, dependency closure and resource policy.

This is known-class benchmark ground truth. The deliberately selected positive-control
archive is not a fuzzing rediscovery, must never enter the initial fuzzing seed corpus and
cannot establish feedback effectiveness. A PASS would qualify this pair/arm and the existing
snapshot detector only. It would not prove either release generally vulnerable or safe.

Current Layer: Layer 6 historical-target qualification. Human approval is recorded below.
The remaining stop condition before execution is restoration and successful validation of the
trusted host broker together with all frozen build/admission prerequisites.

## Prerequisite ledger

The candidate base inspected for this proposal is main
`57f751992f60a534c5b07506e72124abe5d6b07d`. The following evidence or changes are separate
and are not silently treated as merged:

| Dependency | Exact revision | Current contribution | Required before execution |
| --- | --- | --- | --- |
| Static N01 investigation / PR #92 | `f8be20a37ea5ffdd64c2b56fbc7bfd14218ab595` | official package bytes, production closure and source-level affected/fixed expectation | retain as documentary/static evidence; do not count as runtime qualification |
| Protected-component mutation policy | `a7aa735bfada38309984066202b1ceda5aa93e34` | versioned default-sentinel vocabulary and constructive case/TAR proof | review and merge, or pin an integration revision containing the byte-identical implementation |
| Exact N01 wrapper locks | `12fe379` | common historical production closure and portable packaging tests | review and merge, or pin an integration revision containing the exact lock bytes |
| Trusted host/controller broker | user-reported macOS/OrbStack validation on 2026-10-15: boundary 6/6, current Node image 2/2, current Node target 10/10 | establishes the existing normal-target transport path, not historical image admission | rerun exact controller/context/volume identity and historical image admission on the frozen execution revision |

The old unmerged `experiment/n01-node-historical-qualification` branch is not a prerequisite.
Its root-level `a` sentinel, later-resolved minipass `7.1.3` locks and older host/controller
mode diff are superseded candidates, not execution evidence. No code is copied from it
without a fresh review against current main.

## Frozen candidate input

The controlled input is constructed from `minimal_seed_corpus()[2]`, not from a public CVE
PoC. It uses the proposed versioned mutation policy
`uniform-generic-m1-protected-components-v1` and the existing
`mutate_link_target` operator with the exact constructive draw transcript retained by
`a7aa735`.

| Field | Frozen value |
| --- | --- |
| Parent entries | regular `a.txt` with bytes `hello inodefence`; hardlink `b.txt -> a.txt` |
| Parent case ID | `de8ddc5ca4c15fccb638257bbbe671c4fcc9c707962cb92de6589a09f6418620` |
| Child entries | same regular entry; hardlink `b.txt -> ../outside/sentinel.txt` |
| Child case ID | `55b8b7eda4bf26ec1e877866a099dd49195754e00e1e6f20dd82b0bb09288a87` |
| Builder | `ustar-utf8-v1` |
| Exact TAR SHA-256 | `2af6de238713e83a630ad8c95f9385f2cf2e6127a9025bd71d7a2377a7e47ba6` |
| Controlled sentinel | `outside/sentinel.txt`, mode `0600`, initial nlink `1` |
| Sentinel bytes SHA-256 | `caed2ac112733b3f5e3f56d9372f7ce6ba88dfafd57eb58807bb29f16548e36b` |

The runner must reconstruct the child through the versioned policy/operator API, verify the
parent/child IDs, regenerate the exact TAR digest and then pass that same immutable byte
sequence to both releases. It must not hand-build a different archive, rewrite the link
target after export or remap the protected path at runtime.

## Frozen candidate target and environment

Only the `tar` package bytes may differ between pair members. Candidate inputs to image
construction are:

| Binding | 7.5.2 arm | 7.5.3 arm |
| --- | --- | --- |
| Wrapper lock SHA-256 | `31792107e9442ab18b04661d10ca0a0053db1fb7c58ca3aa702f1abb9908e243` | `a63d02f09d9a9fb2def77da84d5145984ff260fcedd19839ba96ec858fdfae24` |
| tarball SHA-256 | `22d8b674a68754ea909d03aa13958a7d2fd5e78af8a8f0cde6455babef7aaf1a` | `9d95d0cf786786360f97c1e414caea8a14452dc337fda17ba256ae7762c2ec66` |

Both locks pin `@isaacs/fs-minipass 4.0.1`, `chownr 3.0.0`, `minipass 7.1.2`,
`minizlib 3.1.0` and `yallist 5.0.0`. Both contexts must use:

- Node `22.22.0`;
- build base `node:22.22.0-bookworm-slim@sha256:dd9d21971ec4395903fa6143c2b9267d048ae01ca6d3ea96f16cb30df6187d94`;
- runtime base `gcr.io/distroless/cc-debian12:nonroot@sha256:9dac0a79194e45a7da0158a9c6da57b217585af0786db3845d1f0ec1a0dd182f`;
- current plain CommonJS worker bytes, candidate SHA-256
  `feb13d7be5f5718769bebd4b0e375ea3f535abffd45223494dd518263593498b`;
- `tar.x({strict: true, preservePaths: false})` and all other upstream defaults;
- target timeout 10 seconds; and
- the existing `docker-volume-subpath-v1` policy with UID/GID 1000, network none,
  read-only rootfs, cap-drop ALL, no-new-privileges, private PID/IPC/cgroup namespaces,
  512 MiB memory+swap, 64 PIDs, 1,024 open files, 64 MiB per-file limit, 32 MiB `/tmp`,
  16 MiB `/dev/shm` and 1 MiB capture per stream.

The worker hash is a candidate binding to the reviewed integration revision, not permission
to ignore later source changes. The execution preflight must recompute it and either match or
stop for contract review. Actual immutable image IDs, architecture, repo digests when
available, Docker runtime/API, controller identity, Linux kernel and runtime-volume
filesystem/device must be recorded from the execution environment. Recipe/base digests are
not substitutes for actual built image identities.

The source bind mount must not be the extraction filesystem. Every run uses a new
`/var/lib/inodefence` subdirectory, an empty `extract/`, the default owned sentinel on the
same Linux filesystem and the exact same absolute run path inside controller and target.
Setup ends before BEFORE; target and descendants stop before AFTER; evidence publication and
cleanup happen after AFTER.

## Execution phases and fixed budget

Execution is one bounded qualification attempt with no automatic retry:

1. **Broker preflight:** validate the exact Docker context, controller full ID, runtime
   volume, stdio request validation, target ownership labels and lifecycle cleanup. Any
   mismatch stops before historical target load.
2. **Build and image admission:** prepare two no-overwrite contexts from the exact locks,
   build once, retain `packaging.json`/`build.json`, and verify immutable images through the
   same backend/identity command used for extraction.
3. **Oracle controls:** in disposable runtime roots, capture one unchanged negative and one
   harness-created hardlink positive. The latter must produce C1 and C2 and is labelled
   harness control, never target behavior.
4. **Benign readiness:** run each of the four original benign seeds once against each image.
   All eight runs must complete successfully with no C0/C1/C2 observation and with exact
   input preservation. Failure blocks the pair phase and remains retained.
5. **Known-class pair:** run five fresh repetitions per release using the exact child/TAR.
   Counterbalance execution order as `affected,fixed` for repetitions 0,2,4 and
   `fixed,affected` for repetitions 1,3. No sandbox or target process is reused.
6. **Independent read:** verify all records and checksums in a fresh process, reconstruct the
   same-input pair bindings and mechanically derive counts. Human root-cause review remains
   a separate required disposition.

The maximum authorized archive extractions are eight benign plus ten known-class runs.
Identity/preflight probes and the two oracle controls are reported separately. There is no
random fuzzing budget, corpus evolution, minimization, post-extraction application write or
native effect campaign in this task.

## Admission and decision rule

All repetitions and negative outcomes remain in the denominator. The automated known-class
result is complete only if:

- every affected 7.5.2 run is `SUCCESS`, retains `extract/b.txt`, and observes that path and
  `outside/sentinel.txt` with equal lstat `(st_dev, st_ino)` after extraction;
- every affected run has C1, with C2 sentinel metadata change retained as corroboration;
- every fixed 7.5.3 run has no extraction/protected identity relation, no C1 and no C2;
- the fixed status is retained exactly rather than coerced to success (source review predicts
  strict rejection, but status alone is not the selected effect);
- neither arm changes/deletes the input archive, and neither produces an unexpected C0;
- both arms use byte-identical case/TAR/setup/limits/worker/closure bindings except for the
  selected tar release; and
- every target is stopped, descendants are absent, owned containers are removed and fresh
  runtime roots are cleaned only after their complete evidence is retained.

An unexpected target status, alias result or extra contract observation is a qualification
FAIL or INCONCLUSIVE fact, not something the runner should assert away before export. An
observation, identity, broker, cleanup, artifact or provenance failure is
`infrastructure_invalid`; it is not a fixed-arm nonviolation and cannot be retried within the
same attempt without a newly recorded execution decision.

The automated token, if every mechanical predicate passes, should be
`N01_PAIR_AUTOMATED_REPLAY_COMPLETE`. It is not final admission. Only after independent
verification and human correspondence review may a separate summary record
`N01_RELATIVE_HARDLINK_PAIR_QUALIFIED`. Neither token means rediscovery.

## Required evidence and implementation boundary

A future runner may add only N01-specific orchestration/evidence and additive broker modes.
It may use existing `NodeTarTarget`, `run_case`, `PairArm`/`PairComparison`, provenance,
failure-ledger and no-overwrite storage APIs. It must not duplicate or modify the generic
builder, mutation semantics, sandbox, observer, C0/C1/C2, feedback, native effect reader or
container isolation policy.

The evidence root must be a new absolute path and contain, with checksums:

- approved contract/revision identity and exact run schedule;
- prepared context/build records and actual image/runtime/isolation attestations;
- oracle controls and eight benign `RunResult` records;
- five same-input `PairComparison` records preserving both complete arm results;
- infrastructure-failure and cleanup records, including partial attempts;
- a last-published manifest and mechanical summary; and
- independent-reader output plus a separate human disposition field.

The runner must export observed results before applying the expected-outcome decision. A
failed expectation cannot erase or prevent preservation of a valid `RunResult`. Evidence
files and final destinations are never overwritten.

## Approval and recovery instructions

Before implementation or execution, reviewers must record whether this exact relative arm,
five-repetition budget and decision rule are accepted. After prerequisite branches are
reviewed, pin one clean integration revision and rerun canonical validation.

On the trusted macOS/OrbStack host, restore the existing broker path without mounting a
Docker socket into the Dev Container or granting it privilege. Supply the actual Docker
context, full controller ID, Linux runtime volume and the two immutable built image IDs to an
additive reviewed broker mode. First run metadata/benign admission; do not fall back to a
direct Node subprocess if broker validation fails.

Until approval, prerequisite integration and broker validation all exist together, the
historical execution remains **NOT_RUN**.

## Technical review and human authorization record

Technical review date: **2026-10-15 UTC**. Reviewed integration revision:
`ee6ce6501368ff8a5ab420e254790c3451b997ae`. Review classification:
**engineering contract consistency PASS; scientific authorization NOT RECORDED**.

The review mechanically reproduced these frozen bindings from the integrated source:

- affected/fixed packages: node-tar `7.5.2` / `7.5.3` with exact wrapper-lock SHA-256
  `31792107e9442ab18b04661d10ca0a0053db1fb7c58ca3aa702f1abb9908e243` /
  `a63d02f09d9a9fb2def77da84d5145984ff260fcedd19839ba96ec858fdfae24`;
- worker SHA-256
  `feb13d7be5f5718769bebd4b0e375ea3f535abffd45223494dd518263593498b`;
- generated child case ID
  `55b8b7eda4bf26ec1e877866a099dd49195754e00e1e6f20dd82b0bb09288a87`
  and TAR SHA-256
  `2af6de238713e83a630ad8c95f9385f2cf2e6127a9025bd71d7a2377a7e47ba6`;
- default sentinel bytes SHA-256
  `caed2ac112733b3f5e3f56d9372f7ce6ba88dfafd57eb58807bb29f16548e36b`
  with mode `0600`; and
- Node/base pins, `strict:true`, `preservePaths:false`, 10-second target timeout and the
  existing `docker-volume-subpath-v1` resource/isolation policy stated above.

Code review confirmed that each `run_case` constructs a fresh runtime sandbox, finishes
setup before BEFORE, captures AFTER before cleanup, applies C1/C2 independently of process
status and removes the runtime root. `PairComparison` requires equal case/TAR/builder
identity while preserving both complete arm results; its storage reader verifies canonical
bytes and checksums. The future N01 runner must still export each valid arm result before
applying expected-outcome rules and must add a final manifest that binds all five pair
records, schedule roles, cleanup and independent-reader output.

Frozen execution summary for human decision:

| Decision item | Frozen value |
| --- | --- |
| Input | one policy-generated known-class positive control; exact child/TAR hashes above |
| Pair | affected 7.5.2 versus fixed 7.5.3; only selected `tar` bytes differ |
| Budget | 8 benign extractions, then 5 fresh repetitions per release; no automatic retry |
| Order | affected→fixed for repetitions 0/2/4; fixed→affected for 1/3 |
| Required selected observation | affected 5/5 persistent C1 relation; fixed 0/5 C1/C2 |
| Corroboration | affected C2 sentinel metadata change; content change is not required |
| Failure handling | rejection, timeout, unexpected state and infrastructure failure retained without coercion or denominator removal |
| Containment | existing trusted macOS broker, exact Linux volume/controller, immutable images, network none, non-root and frozen limits |
| Maximum claim | controlled historical behavior is observable by the existing persistent C1/C2 pipeline |
| Excluded claims | fuzzing rediscovery, feedback effectiveness, native-effect qualification, general release safety and new vulnerability discovery |

Human authorization state: **RECORDED** on **2026-10-15 UTC**. The project owner supplied the
exact statement “N01 pair qualification contract v1을 승인한다” in the direct Task Contract
that started `experiment/n01-contained-qualification-v1`. The authorization binds the exact
relative arm, five-repetition budget, decision rule and containment requirements above; it
does not waive admission failures, expand the target set, authorize a fuzzing campaign or
replace the required post-run human correspondence review.
