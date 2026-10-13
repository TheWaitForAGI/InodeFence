# extractor 실행 경계

## 입력과 출력

[TargetAdapter](base.py)의 `run(archive_path: Path, extraction_root: Path) -> ExecutionResult`는 target이 멈춘 뒤 반환한다. Adapter가 command/version/options와 success/rejection/failure/timeout 분류를 소유한다. Observer·Oracle·Feedback은 target command를 알지 않는다.

CampaignTarget은 기존 단일 실행 Protocol에 `provenance: TargetProvenance` property를 추가한다.
Campaign은 실행 전 target ID/version/timeout을 고정하며 result drift를 거부한다. Reference는
같은 property의 ID/version과 configured timeout을 사용해 ExecutionResult를 반환한다.

## Reference target

[PythonTarfileTarget](python_tarfile.py)은 별도 interpreter에서 [_python_worker](_python_worker.py)를 실행한다. Worker는 uncompressed TAR와 명시적인 `filter="data"`, `errorlevel=2`를 사용한다. FilterError는 REJECTED, parser/IO 오류는 FAILED로 반환한다. Timeout은 subprocess.run이 worker를 종료·회수한 뒤 반환한다. Unexpected harness 실패는 exception으로 올린다.

Command, Python patch version, configured `timeout_seconds`, actual `duration_seconds`와 stdout/stderr를 모든 반환 status에 기록한다. Duration은 `perf_counter()`로 subprocess.run 직전부터 완료 또는 timeout kill/wait 후까지 측정하며 process startup과 timeout cleanup/wait overhead를 포함한다. Path validation과 pipeline의 setup/snapshot/판정/cleanup은 제외하고 timeout 설정값을 복사하지 않는다. Raw execution evidence이며 security verdict, StateSignature나 case identity로 사용하지 않는다. Output은 UTF-8/surrogateescape로 decode하여 undecodable bytes도 JSON evidence에서 복원할 수 있다. Data filter가 archive mode를 제한하거나 일부 입력을 변형할 수 있으므로 builder의 mode 보존과 reference의 extraction policy를 구분한다. 실패 후 부분 state도 runner가 관찰한다. 동작 기준은 [Python tarfile 문서](https://docs.python.org/3.12/library/tarfile.html#extraction-filters)다.

이 target은 **architecture 검증·integration·reference baseline용**이며 node-tar 대체 benchmark가 아니다. 최종 adapter 우선순위 node-tar → oras-go → 선택 GNU tar는 유지한다.

## Node-tar container invocation

`NodeTarTarget.bind(backend, image_id, timeout_seconds)` identifies exact Node/tar
and worker/lock digests inside the immutable target image, then returns an
`IsolatedTarget`. `NodeTarTarget` is an immutable WHAT-to-execute descriptor, with
no direct subprocess/run fallback. `IsolatedTarget` owns HOW-to-execute through
an explicit trusted `ExecutionBackend` implementation. Future targets can supply
commands/classification without changing Campaign, Observer, Oracle or Feedback.
A new backend implementation is a controller trust decision, not a target boolean.

The [pinned image](../../../tools/node-tar/README.md#disposable-target-image-v1) uses
Node 22.22.0/tar 7.5.22. Worker options remain strict=true/preservePaths=false and
upstream defaults. ID is node-tar-strict, version node=<exact>;tar=<exact>.
Version drift exits before extraction and raises a harness error. TAR_* errors
are REJECTED, other worker errors FAILED, deadline expiry TIMED_OUT. Raw command,
streams, duration and timeout are preserved. Output exceeding the backend's
capture bound raises OutputLimitError with the bounded raw prefix, rather than
returning incomplete evidence as a completed run. Security truth stays outside.

`PreparedTarget.prepare()` brackets the observation window: setup → BEFORE →
yielded invocation → AFTER → context cleanup. The pipeline uses this contract for
contained targets and retains the one-case/one-execution/one-snapshot-pair behavior.
Stopped PID context is checked before AFTER; removal follows AFTER, including on
observation exceptions. A start deadline before launch destroys the container
before AFTER to rule out a delayed daemon start; this changes no controlled-run
namespace. All paths share the same Linux volume inode identity.

The seven original real fixture cases (four ordinary baselines, invalid format,
real timeout and worker version guard) now execute only through the container
backend in `tests/container_integration/check_node_target.py`. An additional
AFTER-error cleanup case is mandatory. Portable tests cover invocation/binding/
status/safety rejection; they do not claim real containment. Campaign admits ISOLATION_REQUIRED only through this final composed wrapper, with
backend attestation and matching policy frozen before the first archive.

## Node-tar effect producer v2

`NodeTarEffectTarget` is a separate contained adapter for Gate 3. It invokes the dedicated
`effect-producer.cjs` worker while retaining the same complete asynchronous
`tar.x({strict: true, preservePaths: false})` call. Binding fixes Node/tar, producer, package
lock, bundled package entrypoint and readable `unpack.js` digests. It has no direct local
subprocess fallback.

The full profile propagates exact entry identity with `AsyncLocalStorage`, wraps the declared
callback-based `fs` vocabulary, assigns one sequence to lifecycle/operation boundary records,
and captures stable sandbox-relative lstat/content evidence. The minimal profile retains
lifecycle/context/framing without operation wrappers. The finite record bound is checked
before recording; overflow is explicit and no older record is overwritten. One stdout frame
contains the raw records, digest, target outcome and terminal synchronous-write marker.

The adapter verifies source binding, record digest and terminal sequence after the target
stops and before `effect_pipeline` captures AFTER. Missing/malformed/truncated/overflowed
evidence produces an incomplete or invalid trace; target rejection, timeout and backend/
observer exceptions remain distinct. Operation success without class-specific state evidence
stays `OPERATION_OBSERVED`. `evaluation.native_effect_evidence` publishes the exact raw frame
and typed result with checksums and no overwrite.

Portable tests validate this contract. The actual eight-fixture container suite is
`validate-node-effect-producer` and passed all 10 checks through the existing WSL host broker
at clean revision `36ff7fd`. The separate `qualify-node-effect-v2` mode completed all 480 runs.
Required replacement coverage failed because duplicate-path reused/truncated the same inode;
the exact decision is `V2_NATIVE_EFFECT_OBSERVATION_NOT_QUALIFIED`. The producer remains
unqualified and is not connected to a campaign. Raw evidence and audits are linked from the
[qualification summary](../../../experiments/summaries/node-native-effect-observation-qualification-v2.md).

## 공통 실행 경계

TargetProvenance.execution_safety는 explicit ExecutionSafety enum이며 default ISOLATION_REQUIRED다.
Python reference는 TRUSTED_REFERENCE를 선언한다. Campaign은 requirement를 첫 run_case 이전에
검증하며 미선언/uncontained isolation-required target은 거부한다. Contained target은
exact IsolatedTarget composition과 frozen backend policy/attestation이 필요하다. Caller override/bypass는 없다. Manifest는
frozen requirement를 보존한다. 이는 trust 선언이며 OS isolation 보장이 아니다.

Low-level isolated adapter.run/run_case also enforces the backend; no direct Node fallback exists.
The configured contained campaign path is bound and validated by the approved tiny benign smoke.
현재 engineering Task Contract는 이 정상 입력 검증까지만 승인한다. Accepted global Phase-4 closeout 이후의
security evaluation에는 별도 연구 Task Contract가 필요하다. Adapter는 안전성을 version이나 path에서 추론하거나
TRUSTED_REFERENCE를 third-party에 붙여 이 gate를 우회하지 않는다.

Reference는 동일 run의 archive/input.tar와 extract/ 경로를 검증하고 runtime symlink component를 거부한다. Directory layout은 cleanup 경계이고 OS 권한 격리가 아니다. Contained target은 validated backend의 filesystem/process 경계와 timeout 후 전체 context 종료를 사용한다. [architecture](../../../docs/research/design/architecture.md)와 [observer](../observer/README.md)를 따른다.

`run`은 BEFORE/AFTER 관찰 구간 안에서 호출된다. Harness setup/log/bookkeeping의 namespace write는 이 구간 밖에서 해야 한다. Diagnostics는 현재 reference처럼 ExecutionResult로 반환한다. Region.HARNESS는 target mutation의 면제 영역이 아니므로 adapter bookkeeping을 archive 아래에 기록해도 C0에서 자동 제외되지 않는다. Snapshot은 actor provenance가 없어 계약을 어긴 harness write를 target effect와 구분하지 못한다. 향후 adapter가 이 lifecycle을 지킬 수 없으면 별도 provenance/관찰 설계가 필요하다.
