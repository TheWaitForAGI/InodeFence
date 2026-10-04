# Runtime, execution and evidence audit v1

**Audit Phase 1; no production fixes included.** One MAJOR remains open: public Node
composition can export artifact declarations as image facts without observing those
artifacts. No BLOCKER was established in this lane. Passing validation does not close
the findings or authorize benchmark implementation/evaluation.

## 1. Baseline and scope

- Repository: `TheWaitForAGI/InodeFence`.
- Audited main: `fae2954906fa1a95235cde5cddd4dcb73f334169`.
- Branch: `audit/runtime-execution-v1`, created directly from that SHA.
- On 2026-10-04, `git fetch origin` succeeded, `origin/main` and local main equaled
  that SHA, and `git status --porcelain=v1` was empty before branch creation.
- Task Contract: the maintainer's directly supplied Primary Runtime / Execution /
  Evidence Audit Engineer specification. Production changes, benchmark work, CVE
  execution, vulnerable target installation, exploit archives and fuzzing are excluded.

Reviewed runtime, execution requests/backend/transport/controller/broker, target
composition and Node packaging/worker, pipeline lifecycle, execution-side Campaign,
ExperimentConfig v1/v2, provenance, completed/emergency export and relevant tests/CI.
The design directory, START_HERE, STATUS, AGENTS/scoped engine instructions,
DECISIONS, CONTRIBUTING, SECURITY and
[pre-audit readiness](../../experiments/summaries/pre-audit-readiness-v1.md) supplied
declared invariants. Source determined the actual path.

[PR #35](https://github.com/TheWaitForAGI/InodeFence/pull/35) was read-only input at
research head `5b3745e40e5d43c3b79fa9fe7ca1872f1d2e1106`; its engine-contract audit
and EC-01 escalation reviewed an older main, `efe1dbb5ec3787dee42eadb643646be2b326b489`.
Neither its branch nor its findings were assumed to be the current baseline. PR #35
was not modified. Parallel read-only subreviews covered container lifecycle and
config/export; the primary independently traced composition/admission and integrated
the evidence. This is the assigned execution lane, not a claim that the other
repository audit lane has completed.

## 2. Execution architecture from source

| Stage | Exact implementation and actual responsibility |
| --- | --- |
| Host/controller selection | `scripts/container_host.py::main`: explicit Docker executable/context, inspect selected controller to obtain its full ID, fresh owner UUID, `docker exec -i --user vscode --workdir /workspaces/InodeFence ... scripts.container_controller`. |
| Reserved broker transport | `scripts/container_controller.py::main` creates `StdioDockerClient(sys.stdin, sys.stdout)` and redirects ordinary stdout to stderr. Host `main` parses requests and dispatches `DockerCLI.run`; target streams are encoded base64 response fields. |
| Backend admission | `execution/container.py::ContainerExecutionBackend.__post_init__`: non-root Linux, full controller ID, volume/owner syntax, Linux server, controller hostname and writable runtime volume mount. |
| Node identity setup | `targets/node_tar.py::NodeTarTarget.bind` → `_identify` → image validation → separate disposable sandbox → backend metadata-only prepared container → `_node_worker.cjs --identify`. Returns an immutable descriptor composed with `IsolatedTarget`. This happens before ExperimentConfig/campaign execution, not inside a case's observation pair. |
| Config binding | `experiment_config.py::ExperimentConfig.from_json/to_json/config_id` and `run_configured_campaign`: strict versioned configuration; exact minimal seed IDs/order, target declaration and isolation policy equality; passes the derived config ID into Campaign. It does not itself choose/build a target. |
| Campaign safety admission | `campaign.py::run_campaign`: nonempty unique seeds/budget, declared TargetProvenance, exact `IsolatedTarget` for `ISOLATION_REQUIRED`, reject wrapper subclasses/downgrades, `capture_isolation`, then `freeze_provenance`. Supplied frozen provenance must match target/sentinel/isolation. |
| Before each case | Campaign's nested `execute`: compare policy/artifacts/target declaration to frozen provenance; call `pipeline.run_case`; validate returned target ID/version/timeout. This checks consistency, not initial artifact authenticity. |
| Input/runtime setup | `builder.py::build_tar`; `runtime.py::disposable_sandbox/runtime_root/open_runtime_directory`; pipeline writes `archive/input.tar` before preparation/BEFORE. Fresh `extract/`, `outside/` sentinels and archive namespace are in the Linux volume. |
| Prepare before BEFORE | `targets/isolated.py::IsolatedTarget.prepare` validates layout, obtains descriptor argv/timeout, creates `execution/base.py::ContainerRequest`. Concrete backend opens nonsymlink run/extract directories, inspects image, creates a UUID-named container, checks policy, yields `PreparedContainer`. |
| BEFORE | `pipeline.py::run_case` calls `observer.capture_state(..., BEFORE, protected_paths)` only after prepared context entry. |
| Launch and completion | `PreparedContainer.execute` starts once through the broker with an explicit timeout; normal wait or timeout kill/wait; re-inspect `Running=False`, `Pid=0`, `Status=exited`; normal attached exit must equal container wait exit. A deadline in `created` state removes/verifies absence to exclude delayed launch. |
| Classification | `IsolatedTarget.prepare` rejects truncated diagnostics with `OutputLimitError`; Node descriptor `classify` maps exit0/2/other/None to SUCCESS/REJECTED/FAILED/TIMED_OUT, except identity exit3 raises. |
| AFTER and RunResult | Pipeline captures AFTER only after a returned execution result; compares states, derives signature and C0/C1/C2 verdicts, constructs RunResult inside the prepared context. |
| Cleanup before return | Prepared context exit calls `remove_owned`; then `TemporaryDirectory` deletes the runtime sandbox. Although constructed earlier, RunResult reaches its caller only if both context exits succeed. |
| CampaignResult | Campaign stores each complete RunResult/feedback/lineage in CampaignStep, then returns the completed immutable campaign after its budget. Infrastructure errors propagate; no partial CampaignResult is returned. |
| Completed export | `campaign_export.py::export_campaign/_write_campaign/_write_file/_sync_directory/_publish_directory`: stored provenance, canonical JSONL and optional config in a sibling stage; fsync/readback; Linux no-replace rename; parent sync. No target or provenance recapture. |
| Unexpected benign evidence | `check_node_campaign.py::guarded_run` validates benign spelling, calls actual run_case, then `scripts/benign_validation.py::preserve_unexpected`. It preserves a completed violating RunResult/config/provenance and stops the approved smoke. Generic Campaign has no such stop policy. |

The prepared-container sequence agrees with the main architecture and execution
README for ordinary returned outcomes. Exceptions, truncation and cleanup failures
have narrower evidence semantics than the normal arrow diagram; see section 6.
Artifact attestation is overstated on public composition (EX-001). Command readback
is incomplete (EX-002). Older navigation/packaging status is stale (EX-005).

## 3. Trust boundaries and fact categories

`DECLARED FACT` describes a statement/configuration, `OBSERVED FACT` an actual read,
`TRUSTED ASSUMPTION` a dependency accepted by the implementation, `CALLER-CONTROLLED
VALUE` an input selected by the controller/operator, and `DERIVED VALUE` a calculation.
A value can be both caller-controlled and declared; that does not make it observed.

| Boundary/value | Categories | Assessment |
| --- | --- | --- |
| Docker executable/context, controller/volume/image selection | CALLER-CONTROLLED VALUE | Explicit operator choices. Broker inherits host authority/environment to access this context; that environment is not forwarded to targets. This is a trusted broker, not a least-authority verifier of malicious controller requests. |
| Controller source, chosen ExecutionBackend/TargetInvocation | TRUSTED ASSUMPTION; CALLER-CONTROLLED VALUE | Implementing ExecutionBackend is a controller trust decision. ABC membership and exact wrapper admission do not independently prove an arbitrary backend safe. |
| Archive entries/content/order | CALLER-CONTROLLED VALUE | Untrusted extraction input; does not control the reserved broker channel. |
| Config target/version/timeout/profile/policies/sentinels | DECLARED FACT; CALLER-CONTROLLED VALUE | Required explicit configuration. Environment profile is a label, not an OS measurement. |
| Config/case/TAR IDs | DERIVED VALUE | Config canonical JSON SHA-256, logical case identity and built archive byte SHA-256 have different meanings. |
| Runtime directory and subpath | CALLER-CONTROLLED VALUE; DERIVED VALUE; OBSERVED FACT | Runtime config selects a path; request derives its relative volume subpath; directory components are opened O_NOFOLLOW. Concurrent harness-owned path replacement is outside the threat model. |
| Server/image inspect fields | OBSERVED FACT, under TRUSTED ASSUMPTION | Docker-compatible API supplies runtime version/OS/architecture and image ID/architecture/repository digests. Runtime truthfulness and image immutability are trusted. |
| Requested isolation policy | DECLARED FACT; DERIVED VALUE | Model policy is built from the backend UID/GID/resources and fixed settings. It is not itself proof that a container has these properties. |
| Inspected container security settings | OBSERVED FACT | Checked before yield/start for the fields in the enforcement table below. Command/default fields are omitted (EX-002). |
| Node normal bind versions/artifacts | OBSERVED FACT, under TRUSTED ASSUMPTION | The trusted image's worker reads process.versions.node/package version and hashes its worker/lock. This is not upstream vendor attestation or proof that a malicious image reports honestly. |
| Node direct-constructor versions/artifacts | DECLARED FACT; CALLER-CONTROLLED VALUE | Shape-valid values. Artifact declarations are copied into IsolationProvenance without origin labeling or independent read (EX-001). |
| Source/environment | OBSERVED FACT or supplied DECLARED FACT | Automatic Git HEAD/status and platform strings; supplied source/environment accuracy is expressly caller-owned. Dirty bit does not preserve a patch or lock source against later operator edits. |
| Configured sentinel digest/mode | DERIVED VALUE; DECLARED FACT | Digest of configured bytes, distinct from observed before/after sentinel state. |
| Container identity/name/owner and duration | DERIVED VALUE plus OBSERVED FACT | Fresh UUID names/owner, returned full container identity, monotonic elapsed duration; inspect/cleanup prove ownership/absence under trusted runtime. |
| Stopped execution context | OBSERVED FACT plus TRUSTED ASSUMPTION | Exit/PID/running checks; Linux private PID namespace teardown is relied upon to stop detached descendants. No kernel/container escape protection is claimed. |
| Snapshots → verdict/signature/feedback/lineage | OBSERVED FACT → DERIVED VALUE | Attribution depends on setup-before-BEFORE and complete-stop-before-AFTER. Snapshot is not actor tracing. Feedback/search semantics primarily belong to the other audit lane. |
| Exported records/checksums | Stored facts; DERIVED VALUE | Publication protects completeness/no-overwrite and binds serialized bytes. It cannot authenticate fabricated caller-built models or correct EX-001. |

### Concrete policy enforcement

| Invariant | Constructed request | Actual check / remaining qualification |
| --- | --- | --- |
| Network none | `--network none` | HostConfig.NetworkMode exact; real helper observes loopback-only and ENETUNREACH. |
| Read-only rootfs | `--read-only` | ReadonlyRootfs true; real helper write gets EROFS. |
| Explicit non-root uid/gid | `--user uid:gid` | Constructor rejects root; Config.User exact; live helper checks credentials. |
| Cap-drop ALL, NNP, no privilege grant | `--cap-drop ALL`, security-opt NNP | CapDrop exact, no CapAdd/Privileged, NNP present; helper reads all capability sets and NoNewPrivs. |
| Private PID/IPC/cgroup | IPC/cgroup explicit; Docker private PID default | PidMode must be empty/default, IPC/cgroup private exact. PID default is a documented runtime assumption, not a silently claimed portable setting. Descendant-stop real test; no direct live check of every namespace. |
| Memory/swap/PID bounds | Explicit memory=swap limit, pids | Exact inspect values; helper reads cgroup memory/pids/swap values. No exhaustion experiment. |
| nofile/FSIZE | Both soft/hard ulimits explicit | Exact sorted Ulimits; helper reads rlimits. FSIZE is per-file. |
| tmpfs/shm | Explicit /tmp options/size and shm size | Exact Tmpfs/ShmSize plus private IPC; live mount options/namespace isolation are not exhaustively tested. |
| Output bound | DockerCLI first1MiB per pipe, drain overflow | Truncation visible; stream transport encodes bytes; adapter aborts incomplete diagnostics. Capture policy is fixed by the concrete implementation, not a total evidence-memory bound. |
| Explicit wall deadline | Request positive finite timeout ≤120s; operations bounded separately | CLI drains/waits against deadline; backend stop/wait/inspect may add overhead. Stalled broker channel lacks its own deadline (EX-006); CLI descendant gap EX-003. |
| Image identity | Request SHA-256 local ID; no tag fallback | Image inspect ID/Linux/no implicit Volumes; created image equality. RepoDigests are optional observations, not image retention/distribution guarantees. |
| Run-root confinement | One named-volume subpath, same absolute target path, volume-nocopy | ASCII/core-run spelling, nonsymlink directories, exact HostConfig mount/options and one inspected mount/destination. API/runtime mount semantics trusted. No repo/home/socket bind or sibling run mount constructed. |
| Target defaults | Entrypoint/argv/workdir/user overrides; image environment values cleared | User readback exists; command/workdir/env readback absent (EX-002). Pinned Dockerfiles have no HEALTHCHECK; arbitrary image healthchecks are not disabled/admitted separately. |
| Ownership/cleanup | Unique name, owner label, full ID removal | `remove_owned` verifies label, removes inspected ID, verifies exact absence. Missing socket/context is not absence; normal second host cleanup is idempotent. Ownership is checked at cleanup, not as an additional prepare-yield condition. |

No current source path supplies target credentials, Docker socket, source/home mount,
host namespace or mutable image-tag fallback. The whole controlled run is writable,
including HARNESS; its mutations remain observable. Default environment keys cleared
to empty may still exist; controller credential values are not copied.

## 4. Findings summary and independent EC verdicts

Counts exclude cross-review candidates and accepted limits without finding IDs:
**BLOCKER 0; MAJOR 1; MINOR 4; NOTE 1.** All defects/gaps below remain unmodified.

| ID | Severity | Status | Subsystem | Finding |
| --- | --- | --- | --- | --- |
| EX-001 | MAJOR | OPEN; confirmed source + benign witnesses | Node composition/provenance | Unobserved worker/lock declarations become exported artifact facts. |
| EX-002 | MINOR | OPEN; confirmed inspection/test gap | Container prepare | Actual command/workdir/env fields are not compared to the request. |
| EX-003 | MINOR | OPEN; confirmed benign subprocess witness | DockerCLI lifecycle | Exited primary prevents termination of surviving CLI pipe owners. |
| EX-004 | MINOR | OPEN; static coverage gap | Export tests | Actual fsync calls/order can regress without a focused negative test. |
| EX-005 | MINOR | OPEN; documentation drift | Design/Node navigation | Current status paragraphs still describe already completed execution work as pending. |
| EX-006 | NOTE | OPEN operational limitation | Broker/controller transport | Timeout requires broker progress; controller response read has no deadline. |

**EC-01: CONFIRMED, MAJOR, OPEN → EX-001.** Both low-level and configured Campaign
paths accept direct/replaced descriptors. Normal bind remains safe within the trusted
image/worker assumption. This is an evidence-integrity defect, not an archive-only
attacker's isolation escape.

**EC-02: CONFIRMED, MINOR, OPEN → EX-002.** Generated current argv is correct; actual
Config readback and portable negative coverage remain incomplete. No current real
Docker/Node mismatch is claimed. PR #35's unrelated historical EC-03 STATUS drift
does not remain in the current STATUS; EX-005 identifies different residual drift.

## 5. Detailed findings

### EX-001 — Node artifact declarations are presented as captured image identity

- **Severity/status/subsystem:** MAJOR / OPEN / Node composition, admission and evidence.
- **Exact location:** [node_tar.py](../../src/inodefence/targets/node_tar.py)
  `NodeTarTarget.__post_init__` lines67–77, `bind` lines79–98, `artifacts` lines108–113;
  [isolated.py](../../src/inodefence/targets/isolated.py) `capture_isolation` lines68–72;
  [campaign.py](../../src/inodefence/campaign.py) `run_campaign` lines123–151;
  [campaign_export.py](../../src/inodefence/campaign_export.py) `_write_campaign` line139.
- **Invariant:** worker/lock fields described as actual captured artifact identity must
  match observations of the executed immutable image, or be clearly labeled declarations.
- **Observed behavior:** direct construction checks only digest/version/image syntax.
  IsolatedTarget validates the image but never calls Node `_identify`. Its capture method
  replaces backend artifacts with `invocation.artifacts`. Campaign checks equality with
  the same declaration and freezes it; exporter serializes it without origin labels.
- **Expected behavior:** verified binding or explicit declaration/observation distinction
  on every supported public composition path before the first campaign case.
- **Evidence/reproduction:** [audit witnesses](../../tests/audit/test_runtime_execution_audit_v1.py)
  `test_ex001_unobserved_artifact_declarations_survive_admission_and_export` runs six
  combinations: direct construction, replacement of normally bound worker/lock, and
  rebinding a descriptor to another valid-looking image; each uses both Campaign APIs.
  Direct construction supplies worker=`d`×64/lock=`e`×64 with **zero identification calls**.
  Replacement follows one mock identification reporting worker=`b`×64/lock=`c`×64.
  Four synthetic steps complete, and manifest v4 retains the substituted tuple. The
  other-image variant proves no identification of that image occurs; it does not claim
  to have measured the contents of a second real image. Backend prepare raises if
  invoked; run_case is replaced by synthetic evidence. No target or archive runs here.
- **Required capability/impact:** controller/API caller can construct or replace a
  descriptor and compose it with an approved backend. No code modification or wrapper
  subclass is needed. An accidental stale composition is sufficient. Archive input
  alone cannot choose these values. Exported artifact facts can contradict the image,
  invalidating their use for benchmark identity/replay. Image content anchor and
  containment remain intact, so this does not invalidate all execution evidence.
- **Affected boundary:** caller declaration → captured IsolationProvenance → frozen
  campaign provenance → exported experiment evidence. `IsolationProvenance`'s model
  docstring calls these actual facts, as do the readiness/attestation narratives.
- **Fix direction:** establish image-verified binding and check stale composition before
  freeze, or retain separate declared/observed artifact records with honest provenance.
  Do not merely add another equality check against the same caller declaration.
- **Regression required:** false worker and lock individually, both together, direct
  constructor, dataclass replacement, same-version changed image, configured and
  low-level admission; reject before first case or mark declarations unambiguously.
- **Dependencies:** coordinate target/artifact model, admission and exporter semantics;
  no benchmark implementation until disposition. Audit witness PASS proves acceptance,
  not a fixed finding; convert/remove it in the separate fix PR.

Adjacent variants independently checked: false Node/tar versions remain declarations
until the worker's version guard; normal worker mismatch exits3 and classification
raises rather than returning fabricated success (portable and real tests exist).
Image syntax/inspect equality and policy-image equality are checked; stale artifact
values can nevertheless move between valid same-version images. Node command is fixed
by descriptor method; command/default verification is EX-002. Repository digests come
from runtime image inspect, source revision from Git or an expressly supplied record,
and all current isolation policy fields enter v2 identity/equality. Neither config ID
nor image ID magically verifies a separately supplied artifact assertion.

### EX-002 — Prepared container does not verify actual command configuration

- **Severity/status/subsystem:** MINOR / OPEN / container policy readback and tests.
- **Exact location:** [container.py](../../src/inodefence/execution/container.py)
  `create_command` lines142–202 and `prepare` lines231–277;
  [test_container_backend.py](../../tests/test_container_backend.py) `FakeDocker.run`
  and `test_policy_has_no_host_exposure_or_inherited_environment`.
- **Invariant:** prepared execution must use the requested executable/argv, controlled
  extraction workdir and cleared image environment before it is allowed to start.
- **Observed/expected:** current command constructs these correctly, but prepare does
  not compare `Config.Entrypoint`, `Cmd`, `WorkingDir`, `Env`. Compare actual fields to
  the canonical expected invocation/default policy before yield/start.
- **Evidence/reproduction:** audit witness
  `test_ex002_prepare_accepts_disagreeing_actual_command_config` changes all four fields
  in the existing FakeDocker response while keeping enforced security fields correct.
  Preparation yields and cleanup succeeds. It never calls start or actual Docker.
  The baseline FakeDocker omits these fields entirely; existing portable assertions
  check environment clearing but not explicit entrypoint/workdir/argv equality.
- **Impact/capability:** a generated-command/runtime-compatibility regression can escape
  portable policy validation. This witness models an inconsistent runtime response,
  not an attacker with control of the trusted daemon or a proven current Docker error.
  Correct current generation, image immutability and real benign worker behavior limit
  severity; core containment is not disproved.
- **Affected boundary:** declared TargetInvocation/request → actual container command
  and execution configuration. `ExecutionResult.command` records generated argv,
  rather than independently observed argv.
- **Fix direction/regression:** explicit command/default expectations and inspection
  comparisons; negative tests for each actual field and explicit generated argv tests.
  Include empty-argument/default-command behavior in the generic request contract.
- **Dependencies:** target/backend interface expectations; no current ORAS/GNU feature.

Adjacent image defaults: image Volumes are rejected; image HEALTHCHECK is neither
disabled nor separately inspected. Current project Dockerfiles have no HEALTHCHECK.
An alternative image may add daemon-initiated in-container work alongside PID1; its
content still has an image anchor and is trusted. Record/admit that assumption or
reject unsupported defaults when extending image qualification. This is not evidence
of a current Node escape. Ownership is independently checked during cleanup, not
as an extra preparation check; generated UUID/label and runtime honesty are trusted.

### EX-003 — CLI child survives deadline when the primary has exited

- **Severity/status/subsystem:** MINOR / OPEN / trusted host Docker transport lifecycle.
- **Exact location:** [docker_client.py](../../src/inodefence/execution/docker_client.py)
  `DockerCLI.run`, especially lines112–117 (`if process.poll() is None: killpg(...)`).
- **Invariant:** the promised deadline terminates the owned CLI process group,
  including pipe-holding descendants, before return or reports unverifiable termination.
- **Observed/expected:** an exited primary can leave a same-group child holding pipes.
  Selector reaches deadline, but the cleanup condition skips group kill. Terminate
  safely owned surviving group members even when the direct primary is already reaped.
- **Evidence/reproduction:** audit witness
  `test_ex003_cli_deadline_leaves_child_when_primary_already_exited` uses a disposable
  fake executable that forks a sleeping child and exits0. `DockerCLI.run(('version',),1)`
  returns `timed_out=True`, `returncode=0`, while `/proc/<child>/stat` shows a live
  non-zombie child and `kill(child,0)` succeeds. A finally block explicitly kills the
  audit child. Independent subreview also reproduced this with a temporary benign
  helper. No runtime, extraction, CVE or vulnerable software is involved.
- **Required capability/impact:** CLI/helper creates a child outliving its primary.
  No evidence establishes that the selected real Docker CLI currently does so.
  Host/controller-side helper processes can survive a timed-out operation; this is
  separate from backend removal/PID-namespace teardown of the target container.
- **Affected boundary:** trusted transport subprocess invocation → termination evidence.
- **Fix direction/regression:** preserve safe group ownership, handle exited-primary
  pipe owners on deadline/exception, account for PID/group identity reuse. Add a test
  asserting child termination before return. Existing closed-pipes regression keeps
  its primary alive and misses this case.
- **Dependencies:** none; witness is deliberately an acceptance proof, not a fix test.

### EX-004 — Export durability protocol lacks syscall/order negative coverage

- **Severity/status/subsystem:** MINOR / OPEN test gap / completed export validation.
- **Exact location:** [campaign_export.py](../../src/inodefence/campaign_export.py)
  `_write_file` lines53–57, `_write_campaign` lines115–128/165–169,
  `export_campaign` lines90–96; [export tests](../../tests/test_campaign_export.py)
  `test_directory_sync_failure_is_visible_with_documented_final_state` lines378–401.
- **Invariant:** file flush/fsync and readback, then staging directory sync, then
  no-replace publication, then parent sync, in that order.
- **Observed/expected:** production calls/order are present and correct. Tests inject
  directory failure above `_sync_directory` and do not observe actual `os.fsync`
  calls/order. A regression omitting file fsync or changing publication order should
  fail a focused negative test, even if byte checks and atomic rename still pass.
- **Evidence:** inspected export tests have write/encoding/readback/publication/sync
  helper fault injection, but no fsync syscall/order assertion. The statement that
  an omitted file sync can remain green is a source/test-derived inference; production
  was not mutated, a crash was not induced, and no current data-loss defect is claimed.
- **Capability/impact/boundary:** future implementation regression; volatile staged
  bytes → durable published evidence. Current core export protocol remains valid.
- **Fix direction/regression:** track actual file/directory descriptors and publication
  events; omission of steps/config/manifest/stage/parent sync and publication-before-sync
  must fail. Keep this focused on guarantees the writer actually claims.
- **Dependencies:** none; separate test change after Phase 1, no production fix here.

### EX-005 — Current documentation still marks completed infrastructure pending

- **Severity/status/subsystem:** MINOR / OPEN / architecture and Node packaging navigation.
- **Exact location:** [design README](../research/design/README.md), current-state
  paragraph line29; [Node tooling README](../../tools/node-tar/README.md), final sentence
  lines36–37.
- **Invariant:** current implementation/status guidance must agree with source and the
  pre-audit freeze; historical plans must be labeled as historical.
- **Observed/expected:** design README says model fields/pipeline are not implemented;
  Node README says full-path benign campaign validation follows next. Current source,
  CI `check_node_campaign.py`, STATUS and pre-audit readiness implement/record both.
  Replace pending statements with bounded current facts or clearly dated history.
- **Evidence/reproduction:** direct read of those paragraphs against architecture
  sections7.8/17/pre-audit freeze and CI's actual configured smoke invocation; no run needed.
- **Capability/impact/boundary:** ordinary documentation reader; stale navigation can
  cause redundant work or incorrect execution-readiness assumptions. It does not
  change current enforcement or approve evaluation.
- **Fix direction/regression:** reconcile only stale current-state statements; docs
  link existence checks alone cannot detect semantic status drift. Human cross-review
  against STATUS/source is required.
- **Dependencies:** maintainers' combined audit disposition; do not advance Layer/status
  or alter research claims as part of this audit artifact PR.

### EX-006 — Stalled broker can make controller timeout unbounded

- **Severity/status/subsystem:** NOTE / OPEN operational limitation / stdio transport.
- **Exact location:** [docker_client.py](../../src/inodefence/execution/docker_client.py)
  `StdioDockerClient.run` lines134–136; `scripts/container_host.py::main` request loop.
- **Invariant:** distinguish the bounded target/CLI timeout from controller progress
  when the trusted broker channel stalls.
- **Observed/expected:** timeout is serialized to the host, followed by blocking
  `reader.readline` without a controller-side deadline. A live broker that stops
  replying can block indefinitely. EOF/malformed responses fail closed, and normal
  DockerCLI operations are bounded. Document broker-progress dependence explicitly
  or enforce a separately defined transport watchdog/failure contract later.
- **Evidence/reproduction:** source inspection; no hanging broker was deliberately
  created. No existing stalled-channel or actual host broker crash/disconnect test
  was found. This extends the documented hard-SIGKILL/daemon-loss limitation, rather
  than proving a target can bypass isolation/its normal deadline.
- **Capability/impact/boundary:** trusted host/broker failure or lack of progress;
  controller may never return, observe AFTER or reach cleanup. No success is fabricated.
- **Fix direction/regression:** first specify ownership/stop/evidence behavior on stalled
  transport; use an externally bounded benign stalled-channel test and disconnect tests.
- **Dependencies:** controller/broker lifecycle and failed-run evidence contract; runtime
  outage can still defeat verified cleanup even with a local watchdog.

## 6. Lifecycle and exceptional-path matrix

The table concerns contained execution. “Stopped” means checked runtime state plus
trusted PID-namespace teardown, not resistance to a kernel/runtime escape. BEFORE/AFTER
attempts that raise are not complete snapshots. No row manufactures success.

| Path | BEFORE taken? | Can target/descendants still run? Can it execute after AFTER? | AFTER / returned RunResult | Partial evidence and cleanup |
| --- | --- | --- | --- | --- |
| A Prepare → SUCCESS | Yes | Stop verified before AFTER; none after AFTER under trusted runtime | Yes / yes | Full evidence; container then sandbox cleanup after AFTER. |
| B Prepare → FAILED | Yes | Same stopped checks | Yes / yes | Nonzero exit/diagnostics and partial extraction state retained. |
| C Prepare → REJECTED | Yes | Same stopped checks | Yes / yes | Rejection remains process evidence; snapshots/verdict still produced. |
| D Execution timeout | Yes | Running context killed/waited/verified; created-state deadline removed/absence verified before AFTER | Yes / yes unless cleanup/truncation fails | Captured prefixes retained, duration includes stop overhead; second removal idempotent. |
| E Startup failure | Yes | Ordinary missing executable leaves created/not-running context; arbitrary runtime error can leave stop unproven | No / no | Backend exception; owned removal attempted, then runtime deletion. No security verdict. |
| F Backend failure before BEFORE | No | Pipeline never requests start; uncertain create handled by owner-name cleanup | No / no | No snapshot; partial preparation/runtime cleanup attempted. |
| G Backend failure after BEFORE | Yes | Possibly; disconnect/kill/wait/inspect failure prevents proof | No / no | Cleanup attempted; earlier snapshot is local and not automatically exported. |
| H BEFORE observation failure | Attempted | Prepared container has not executed | No / no | Context and runtime cleanup; no execution/result. |
| I AFTER observation failure | Yes | Execute already established stopped | Attempted / no | No complete after snapshot/verdict; cleanup follows attempted AFTER. |
| J Container/runtime cleanup failure | Usually yes | On normal completed execution stop already verified; on primary backend error may be unproven | AFTER may already exist / no | Constructed RunResult is withheld by context-exit exception; frozen caller evidence not automatically persisted. |
| K Export failure | All runs completed | Targets already stopped/removed before CampaignResult export | Existing RunResults remain in caller | Staged/publication semantics in section7; no target rerun. |
| L Controller/broker disconnect | Depends | May be live/unproven; host best-effort removes tracked owner names on handled controller failure | No on failed run / no | EOF/protocol errors visible; removal can also fail. Hard broker loss defeats fallback; stalled connection EX-006. |
| M Output truncation | Yes | Backend established stop before adapter raises | No / no | `OutputLimitError.outcome` preserves bounded prefixes; BEFORE/AFTER pair is not exported and AFTER is skipped. |
| N Nested cleanup exception | Depends | Depends on primary error and successful removal | No returned result | Cleanup exception becomes top-level; original stays in Python `__context__`. Broker groups its own cleanup errors; it does not group the primary error as an explicit member. |

Node version mismatch is an infrastructure/identity error after stopped execution,
not REJECTED/FAILED: classification raises before AFTER, cleanup proceeds. Comparison,
signature/oracle or result validation errors likewise return no complete result and
perform cleanup. Builder failure occurs before runtime creation.

Container removal is after AFTER on normal/rejected/failed/timed-out returns. The
created-state timeout deliberately removes early to rule out delayed launch, without
changing controlled-run files. CLI process wait and container wait are waits on different
entities; the later host removal is an owner-checked absence no-op, not unchecked double
destruction. UUID names, ownership-label checks and removal by inspected full container
ID limit accidental cross-invocation cleanup. They are not secret authentication;
concurrent malicious daemon/controller identity replacement is outside trust assumptions.

If backend cleanup fails with stop unproven, outer disposable_sandbox still attempts
runtime directory deletion. This can erase failed-run state while a container remains
alive. Generic Campaign also loses its earlier local steps on a later infrastructure
exception. These are documented absent persistence/failure-evidence guarantees, not
proof of successful containment or preserved partial evidence. Runtime deletion after
an exception can occur without a completed AFTER; no attribution verdict is returned.

## 7. Provenance, reproducibility and evidence export

### Separate identities

Configuration identity binds comparison settings; execution provenance freezes source,
environment and declarations; isolation provenance combines configured policy and trusted
runtime/image reads; artifact identity is bytes claimed/observed for worker and lock;
source identity is a revision plus dirty state. They are not interchangeable attestations.

V1 retains its historical canonical config ID; v2 adds complete IsolationPolicy. All
current fields/resources are included, integer/float timeout spelling is canonicalized,
sentinels sorted, seed order preserved, unknown/missing/duplicate/nonfinite fields rejected.
Target binding and exact policy equality precede Campaign admission/freeze. No accidental
current config-field exclusion was found. Artifacts are not separately in config ID;
ordinary verified binding anchors them through image identity. That does not close EX-001.

Exact wrapper/subclass tests enforce who owns execution, not the honesty of a descriptor
or arbitrary trusted backend. Policy/artifact/target drift checks occur before each case;
result target/version/timeout are checked afterward. Source/environment supplied to the
low-level API and low-level supplied config references remain caller responsibilities.
Configured API correctly binds its config ID. Export uses stored facts, never live backend
defaults; later backend changes cannot rewrite finished provenance.

| Exported binding | What is retained / limitation |
| --- | --- |
| Source | Full Git HEAD and dirty/unavailable record; dirty patch/untracked contents not retained. |
| Config | Campaign config and optional full ExperimentConfig file. Optional input bytes must hash to stored config ID before staging; full file checksum includes its exported LF, so differs from the no-LF config ID. |
| Target/image/artifacts/isolation | Frozen declarations/runtime-image-policy record and each result's execution context; EX-001 affects artifact authenticity, EX-002 actual command readback. Image availability remains operator-owned. |
| ArchiveCase/TAR | Ordered raw logical entries and base64 contents, case identity, builder format and original TAR digest. Same builder/source can reconstruct bytes; archive input after target modification is separately observed, not substituted for initial artifact identity. |
| Execution/observations/verdict | Every returned status, argv/diagnostics/duration/timeout, before/after raw snapshots/changes, normalized signature, verdict/evidence/limitations. Failed infrastructure runs are outside completed writer semantics. |
| Feedback/lineage | Separate feedback decision, index/origin/parent, retained IDs/final stats; search semantics require other-lane cross-review. |
| Publication | Steps checksum, optional config checksum, exact readback for manifest/config. Manifest itself is not internally self-authenticated; external manifest digest/retention is needed for later tamper detection. |

Pinned Node/lock/base manifests make build inputs reviewable. They do not promise
bit-for-bit rebuilding, image distribution/retention, exact controller Python binary,
all filesystem/machine settings or performance repeatability. Target metadata identifies
the trusted image's package-version text and image contents, not independent upstream
authenticity. Semantic lineage repeatability additionally requires equal feedback outcomes
and RNG implementation. Raw inodes/timestamps/duration need not repeat.

### Completed export failure guarantees

| Event | Actual guarantee |
| --- | --- |
| Success | Exclusive file creation in 0700 sibling stage, file flush/fsync, JSONL checksum/config+manifest readback, stage fsync, Linux `renameat2(RENAME_NOREPLACE)` through parent FD, parent fsync; complete bundle returned. |
| Config mismatch / existing destination or dangling symlink | Reject before staging; existing destination not changed. |
| Encode/write/flush/file-fsync/readback or stage-sync failure | Exception; stage cleanup attempted by TemporaryDirectory; final absent if publication did not occur. Newly created parents remain. Cleanup I/O failure can defeat physical deletion and replace top-level error while chaining the primary. |
| Concurrent destination creation | Kernel no-replace rejects; concurrent destination remains intact; stage cleaned on ordinary handled exception. |
| Unsupported OS/libc/kernel/filesystem | No ordinary rename fallback; error and stage cleanup, no manufactured success. |
| Parent fsync error after rename | Complete published bundle remains; exception, no success return and no rollback. |
| Abrupt interruption before publication | Final absent; stage can remain, automatic cleanup not guaranteed. |
| Abrupt interruption after rename | Complete bundle may be visible; crash durability not established until parent sync completes. |
| Newly created nested parent directories | `mkdir(parents=True)` allowed; only immediate publication parent is synced. Newly created ancestor names are not separately synced in their own parents. No whole-new-directory-tree power-loss durability guarantee was established. |
| Emergency partial write / existing path | `preserve_unexpected` uses new directory and ordinary sequential write_text. I/O/conflict errors propagate; partial directory can remain. No fsync/checksum/stage/atomic guarantee. |

The trusted caller owns export's parent directory; concurrent adversarial replacement
of that parent is not the writer's contract. No target mount contains this evidence
destination. Completed publication protects against accidental partial visibility and
overwrite, not malicious edits after export. Current source enforces its staged protocol;
EX-004 concerns regression quality.

## 8. Execution test/invariant matrix

“Real” below describes an existing test's design/CI invocation, not a new local real-target
run by this audit. Portable doubles explicitly do not prove containment. A positive policy
test can pass when its FakeDocker reports required fields independent of generated argv;
use negative checks and real effect probes together.

| Invariant | Tests exist? Layer/examples | Negative regression? Can it pass with wrong implementation? |
| --- | --- | --- | --- |
| Immutable request/image/path/timeout | Yes; unit `test_container_backend.py::test_invalid_execution_request_rejected` | Invalid tags/path/options/argv/timeout rejected; image absence/current inspect separately covered. |
| Network/rootfs/uid/gid/caps/NNP | Yes; mock command+inspect, real `check_boundary.py::test_real_filesystem_network_credentials_and_resource_policy` | Network wrong-policy regression; real helper checks live effects. Most individual readback comparisons lack portable mismatch tests. |
| Exact single-run view; no repo/home/socket/neighbor | Yes; command/inspect + real canaries/shared sentinel identity | Bad mount spelling/DriverConfig covered. Mock command tests alone cannot prove runtime subpath behavior. |
| Private PID/IPC/cgroup and resource bounds | Yes; exact HostConfig + real descendant/cgroup/rlimit helper | No exhaustive live namespace/mount-options or resource-exhaustion tests; some omitted individual comparisons could evade portable suite. |
| Actual command/workdir/env | Partial; correct construction + real ordinary Node behavior | EX-002: missing actual-field negatives; audit witness accepts mismatch. A future generation error may pass mocks. |
| Image/Node/worker/lock normal identity | Yes; portable `test_node_tar`, real `check_node_image` compares source digests | Versions/image/config mismatches tested. Public pre-freeze forged/stale artifacts accepted by EX-001 witnesses; normal-bind-only real test remains green. |
| Exact-wrapper admission before setup | Yes; `test_isolation_provenance`, `test_node_tar` | Bare descriptor/attribute, subclass/downgrade, unavailable backend/wrong policy rejected with forbidden setup hooks. Does not attest arbitrary caller-selected backend. |
| Every resource/policy in v2 config identity | Yes; per-resource/property and exact JSON schema tests | Missing/unknown/weaker policy rejected; fixed v1 ID and roundtrip. Artifact authenticity remains separate. |
| Target/policy drift and result declaration consistency | Yes; campaign/isolation tests | Policy/target/result version/timeout negatives; no independent artifact-drift negative observed, though comparison exists. |
| Setup → BEFORE → execute → AFTER → cleanup | Yes; managed-target mock `test_pipeline.py::test_managed_target_setup_and_cleanup_bracket_observation`, real Node AFTER failure | AFTER-error variant and runtime disappearance checked. No result on cleanup error. |
| Success/reject/failure/timeout remain distinct | Yes; portable Node/campaign, real Python reference and Node ordinary suites | Status/count/raw stream tests. Error exit3 is identity exception; does not produce a false target outcome. |
| Stopped detached descendants | Yes; real helper synchronized setsid child/grandchild and timeout | Runtime stopped/PID0/top failure verified. Mock state alone would not prove descendant termination. |
| Delayed start/deadline and timeout-exit race | Yes; portable backend tests | Created-state deadline removes before return; kill race only accepts confirmed stopped context. Real ordinary tiny timeout exists; no deliberately delayed daemon test. |
| Startup/uncertain prepare failures | Yes; mock create/lost response; real missing executable | Own cleanup/no target-result checked; other partial-prepare comparison faults not exhaustive. |
| Cleanup ownership/absence/idempotence | Yes; mock wrong owner/socket-error/exact absence and real per-context removal | Reject wrong owner/no socket masquerading as absence. Not a malicious-runtime identity-replacement guarantee. |
| Output bounds and bytes | Yes; benign fake CLI dual-stream overflow, real helper overflow, portable adapter truncation | Prefix and truncation/abort asserted. Final buffered timeout bytes deliberately not guaranteed. |
| CLI deadline and all CLI descendants stopped | Partial; existing pipes-close/primary-lives subprocess test | EX-003 audit witness proves exited-primary child survives. Existing test misses it. |
| Broker malformed/disconnected/stalled channel | Malformed/EOF unit exists | No actual broker crash/stall/disconnect main-loop test found; EX-006. Target output cannot become requests because of channel separation/base64. |
| BEFORE/AFTER/nested cleanup failures | Observer failure/cleanup source tests exist, real Node AFTER failure | No focused simultaneous primary+cleanup/broker error grouping test; partial evidence deliberately not completed. |
| Source/dirty/unavailable, stored freeze | Unit + actual temporary Git repo; campaign/config integration | Tracked dirty/supplied mismatch covered; untracked/error/timeout capture negatives narrower. Export forbidden recapture test passes independently of artifact truth. |
| Complete status/evidence/feedback/lineage/config export | Unit + Linux reference integration + real `check_node_campaign` | Canonical full records, frozen backend defaults, config mismatch/checksum checked. Does not authenticate synthetic caller-built records. |
| No overwrite/readback/failure publication | Real Linux rename through tests plus injected faults | Concurrent empty directory/unsupported publication/encoding/corruption failures detected; no ordinary-rename fallback. |
| File/stage/parent fsync ordering | Source correct; helper-level failure tests | EX-004: actual syscall/order omissions not asserted. |
| Unexpected benign verdict stops and preserves | Safe-reference controlled sentinel chmod unit/integration; real smoke wrapper | Existing successful preservation check; partial emergency write/conflict untested. Generic Campaign does not stop automatically on violations. |

[CI](../../.github/workflows/ci.yml) separates `make check` from `container-integration`.
The latter builds current benign helper/Node images and explicitly runs six helper,
two image, eight Node fixture/lifecycle and one configured eight-step smoke test.
`check_*.py` files are outside default `test_*.py` collection; a green make check alone
is not new container boundary validation. Smoke evidence is copied/uploaded with
`if: always`; this is finite raw engineering retention, not benchmark qualification.

## 9. Accepted limits

- Controller/broker/runtime/kernel/image are trusted. No protection from kernel or
  container escape is established; Docker volume-subpath/platform support is required.
- Snapshot-only persistent controlled-run C0/C1/C2, no transient/actor/direct-use tracing,
  symlink referent identity or C3/C4; lifecycle is an attribution prerequisite.
- Per-file/PID/memory/open-file/tmpfs/shm bounds do not impose total volume/storage,
  file-count or CPU quotas. Full CampaignResult costs O(budget) evidence memory.
- Trusted Python reference inherits controller execution environment and uses the recorded
  Python version/source path, not exact executable hashing. It is neither untrusted
  third-party containment nor a research benchmark. Legacy `_process.run_process`
  cannot contain detached children and is not the contained Node path.
- Dirty patches/exact machine reconstruction, image retention/distribution and byte-identical
  rebuilds are not supplied. Source freeze is a record, not a source filesystem lock.
- Generic failed-run/partial campaign persistence is absent. Truncation exposes a bounded
  outcome in the exception, without a complete observed run. Hard broker/daemon loss
  can defeat cleanup; runtime state may be erased after unverifiable stop.
- Completed export is not a database/authenticated store/reader/resume facility. Abrupt
  interruption, cleanup I/O failure, new-ancestor durability and emergency partial writes
  have the limits in section7. No claim of a demonstrated power-loss failure is made.

These limits do not justify weakening controls or skipping EX-001 before evaluation.

## 10. Fix ordering for a later phase

1. Resolve EX-001's observation/declaration invariant across public composition, admission
   and evidence; add negative pre-freeze artifact/image regressions and cross-review semantics.
2. Resolve EX-003's transport group termination with an ownership-safe failure design.
3. Add EX-002 actual command/default checks and negatives; decide image-default qualification
   explicitly, without introducing future target features.
4. Add EX-004 focused durability protocol negatives and reconcile EX-005 stale status text.
5. Disposition EX-006 and failed-run evidence limits before any larger evaluation budget;
   definition of transport/failure evidence must precede any implementation expansion.

No fix was attempted during Phase 1. Findings are not closed by current green tests.

## 11. Handoff to cross-review

| Candidate/item | Other engineer's requested review | Current status/dependency |
| --- | --- | --- |
| CR-001: aborted-run/partial campaign evidence | Verify corpus/search reporting cannot imply a complete dataset when run_case, builder/observation/cleanup or later campaign steps raise; distinguish completed target outcomes from infrastructure failures and validation-only preservation. | Cross-boundary contract candidate, not an additional confirmed defect/count. Current documented API propagates exceptions and returns no partial CampaignResult. Future benchmark requirements must explicitly address it. |
| EX-001 artifact authenticity | Independently trace the initial fact's origin through model serialization and evidence interpretation; verify severity/caller capability and planned artifact-origin wording. | MAJOR OPEN; execution-side acceptance/export witnesses supplied. |
| Case/TAR/signature/feedback/lineage | Verify stored raw case, initial built digest, normalized state, oracle evidence and feedback lineage remain separate; semantic state repeatability is conditional on feedback outcomes. | Other-lane primary ownership; no search-quality conclusion made here. |
| Attribution/failure matrix | Review AFTER-skipped identity/truncation/observer paths and snapshot limitations; no security PASS should be inferred from missing evidence. | No manufactured success found in execution lane; partial persistence remains absent. |
| Combined freeze/readiness disposition | Reconcile both lanes before declaring audit complete/evaluation ready; this draft does not change STATUS or authorize candidate execution. | Await cross-review and separate fix Task Contract. |

CR-001's provisional severity is NOTE, status **cross-review candidate / documented
limitation**, outside the confirmed finding counts. Exact locations are
`pipeline.py::run_case` lines40–57, `campaign.py::run_campaign`'s local steps/execute loop,
and `check_node_campaign.py::guarded_run`. The current invariant is honest completed-only
results: infrastructure failures must not look like completed target outcomes. That is
enforced, but earlier in-memory steps and failed-run snapshots are not exported.
Evidence is the lifecycle source and `test_campaign.py::test_unexpected_run_error_propagates_and_stops`;
no extra reproduction is required to establish the documented absence of partial results.
Impact is loss of denominator/attribution evidence if a future evaluator treats aborted
campaigns as complete. The affected boundary is execution → campaign/search accounting →
evidence retention. Expected behavior for future evaluation must be specified by both
lanes before implementation. Suggested direction is an explicit failure-evidence contract,
not a Phase-1 persistence feature. Required future regression: infrastructure failure
after earlier steps, observer failure, and simultaneous execution/cleanup failure retain
the defined incomplete evidence without manufacturing a completed campaign. Dependencies
are EX-006, cross-lane reporting semantics and a separate benchmark/fix Task Contract.

## 12. Validation record

Executed in the existing Ubuntu24.04/Python3.12.3 Dev Container as `vscode`, source
`/workspaces/InodeFence`, runtime `/var/lib/inodefence`; host Docker context `orbstack`.
No isolation settings, CI gates, dependency versions or image builds were changed.

- Baseline fetch/SHA/worktree/branch verification: PASS.
- Focused existing execution/config/provenance/export/campaign tests plus the first
  seven audit witnesses: **321 passed**. Final isolated audit witness suite: **8 passed**.
- `make check`: **PASS**; Ruff lint/format, Pyright **0 errors/0 warnings**, **622 pytest
  tests passed**, Linux environment/hardlink/symlink/shared-object checks, docs **63 files
  PASS**. Initial witness-only Pyright Path-versus-str and line-length errors were
  corrected before this final pass. No production file was involved.
- Standalone `make docs-check`: **PASS**, 63 Markdown files. Final diff/LF/scope checks
  passed; only the report and benign audit witness file were added.
- Audit witnesses intentionally pass when baseline flaws are accepted. They run six
  synthetic artifact/admission/export combinations, one fake-policy prepare and one
  benign fake-CLI child. Synthetic records are expressly not execution/containment evidence.
- Real target-container/helper/Node suites: source/CI design reviewed, **not rerun locally**.
  New findings are construction/inspection/transport witnesses; no live extractor run
  was needed. Historical pre-audit real-container results were not promoted to new audit
  measurements. The existing canonical suite still runs its supported trusted-reference
  and disposable controlled fixtures.
- A subreview host Python3.14 pytest attempt could not start (pytest unavailable);
  canonical validation was moved to the Dev Container. No host dependencies installed.
- No CVE/affected target, vulnerable-version install/build, exploit archive, vulnerable
  fuzzing, benchmark implementation, production fix, PR #35 edit or merge performed.

Only this report and clearly separated benign audit witness tests belong in the draft PR.
