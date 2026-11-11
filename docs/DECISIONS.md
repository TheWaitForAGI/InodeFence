# 프로젝트 결정 기록

이 문서는 팀이 이미 합의한 **큰 결정만** 기록한다.

코딩 에이전트가 임의로 이 결정을 바꾸지 않도록 하는 것이 목적이다.

결정을 바꾸려면 PR에서 이유를 설명하고 이 문서도 함께 수정한다.

각 decision의 상태/구현 문구는 기록 당시의 단계다. 현재 main capability는
[STATUS](STATUS.md)와 [G0 Research Contract](research/design/research-contract-v1.md)를 따른다.
후속 구현이 존재한다는 이유로 역사적 결정의 검증 수치나 원본 근거를 바꾸지 않는다.

## D001 — 1차 archive format은 TAR

**상태:** 확정

ZIP 등 다른 format을 동시에 지원하지 않는다.

이유:

- hardlink/symlink entry 지원
- 선형적인 entry 구조
- 최신 취약점 benchmark 존재
- 학부 캡스톤 범위에서 관리 가능

## D002 — Linux filesystem semantics를 기준으로 개발

**상태:** 확정

Windows native filesystem semantics는 1차 범위에서 제외한다.

Mac과 Windows 사용자는 동일한 Linux Dev Container를 사용한다.

## D003 — filesystem 실험은 source mount에서 하지 않음

**상태:** 확정

실험 경로:

```text
/var/lib/inodefence
```

소스 경로:

```text
/workspaces/InodeFence
```

두 역할을 분리한다.

## D004 — 초기 Observer는 pre/post snapshot

**상태:** 확정

처음부터 eBPF/fanotify/full syscall tracing을 필수로 두지 않는다.

Minimal pipeline이 동작한 뒤 필요하면 중간 state transition으로 확장한다.

## D005 — CVE-specific oracle 금지

**상태:** 확정

다음과 같은 판정은 금지한다.

```python
if cve_id == "CVE-...":
    vulnerable = True
```

Oracle은 generic Security Contract를 판정해야 한다.

## D006 — Known CVE PoC를 proposed fuzzer 기본 seed로 사용하지 않음

**상태:** 확정

Known CVE는:

- root-cause 분석
- benchmark ground truth
- 결과 검증

에는 사용할 수 있다.

하지만 rediscovery 성능을 평가할 때 해당 PoC 자체를 시작 seed로 주지 않는다.

## D007 — Zero-day는 성공 조건이 아님

**상태:** 확정

프로젝트 성공은 다음으로도 입증할 수 있다.

- known CVE rediscovery
- baseline 대비 차이
- ablation 결과
- cross-implementation 적용
- 재현 가능한 실험

## D008 — 구현은 Layer 단위로 진행

**상태:** 확정

한 번에 전체 fuzzer를 만들지 않는다.

```text
환경
→ 연구 기반
→ Data Model
→ Minimal Pipeline
→ Mutation
→ Feedback
→ Evaluation
```

현재 Layer보다 두세 단계 앞선 기능을 임의로 추가하지 않는다.

## D009 — 첫 구현 target 우선순위

**상태:** 현재 계획

1. node-tar
2. oras-go
3. GNU tar (시간이 허용할 경우)

실제 benchmark 구성 시 version을 별도로 고정한다.

Core foundation의 Python tarfile/data reference adapter는 architecture/integration 검증용이다. 최종 benchmark target 우선순위를 바꾸지 않는다.

## D010 — 문서는 구현의 일부

**상태:** 확정

공통 interface, 연구 범위, 큰 설계 결정이 바뀌면 관련 문서를 함께 수정한다.

특히 바이브코딩에서는 "코드만 맞고 팀이 이해하지 못하는 상태"를 완료로 보지 않는다.

## D011 — 초기 직렬화와 evidence 경계

**상태:** core foundation 구현

Logical case는 raw path/link text와 ordered tuple을 유지한다. 초기 TAR encoding은 strict UTF-8 USTAR와 고정 metadata(`ustar-utf8-v1`)다. Encoding 불가능한 길이는 truncate하거나 다른 format으로 자동 전환하지 않고 거부한다. Fixture script도 core builder를 사용한다.

Model/result export는 versioned canonical JSON이다. Bytes는 base64로 보존하고 raw observations와 portable signature를 구분한다. Inode 숫자·timestamp 원값을 signature key로 쓰지 않는다. 현재 signature는 초기 schema이며 최종 feedback 정책은 Layer 5에서 평가한다.

## D012 — snapshot 판정 범위를 결과에 보존

**상태:** core foundation 구현

C0 external namespace evidence와 C2 object effect를 구분한다. External content change만으로 direct external path use를 추정하지 않는다. Full operation tracing 없이 증명할 수 없는 범위는 ViolationResult.limitations에 기록한다. Observer 오류를 incomplete snapshot이나 PASS로 바꾸지 않는다.

Runtime directory는 cleanup 경계이며 OS execution isolation을 대신하지 않는다. Unsafe benchmark adapter에는 별도 process/filesystem isolation이 필요하다. Reference worker만 추가하며 node-tar/ oras-go benchmark와 연구 효과 검증은 후속 작업으로 유지한다.

## D013 — raw evidence와 normalized security-state scope 분리

**상태:** PR #15 review 수정

Human/AI review에서 snapshot 전체를 signature로 옮기면 `archive/input.tar` digest가 input novelty를 security-state novelty로 오인하게 만든다는 문제가 확인됐다. `StateSnapshot = full raw observation/evidence`를 유지하고 `StateSignature = normalized security-state representation for future feedback/corpus`로 범위를 분리한다. ArchiveCase identity와 TAR artifact identity는 signature에 직접 포함하지 않는다.

공통 `path_region`이 fixed runtime layout의 namespace role을 정의한다. `extract`와 하위는 EXTRACTION, `.`과 `archive` 및 하위는 HARNESS, 나머지는 EXTERNAL이다. Harness bookkeeping은 archive 아래에 둔다. EXTERNAL은 outside만으로 제한하지 않으므로 sandbox root의 `escape.txt`도 C0 evidence와 signature에 남는다. HARNESS는 signature에서 제외하되 raw snapshot/change에서 보존한다. Security trust나 생성 주체를 나타내지 않으며 C0 scope는 D014를 따른다.

StateSignature v2는 HARNESS object를 제외하고 identity group도 같은 scope로 projection하여 singleton을 제거한다. Protected paths와 extraction↔sentinel relation, external-effect labels는 유지한다. `SignatureObject.st_nlink`는 regular file만 정수이며 directory/symlink/other는 None이다. Directory size와 nlink 값은 filesystem allocation/semantics에 따라 달라질 수 있기 때문이다. Raw nlink와 C2 metadata 비교, external nlink-change label은 그대로 보존한다. 따라서 portable representation은 모든 filesystem의 effect pattern이 같다는 보장은 아니다.

Signature 내부 schema는 v1→v2로 변경한다. Canonical JSON envelope v1과 case identity encoding은 유지한다. Corpus/persistence/deserializer는 아직 없고 이전 signature와 같은 key로 비교하지 않는다. 서로 독립인 regular entry 두 개의 순서만 다른 입력을 `run_case()`로 실행해 case/TAR SHA-256은 다르고 signature는 같은지 검증한다. 최종 feedback/corpus 정책과 연구 효과 평가는 Layer 5 이후다.

## D014 — C0 boundary scope와 HARNESS normalization role 분리

**상태:** PR #15 C0/HARNESS follow-up 수정

D013 구현에서 HARNESS를 signature뿐 아니라 C0에서도 제외한 정책은 폐기한다. Target execution 중 `archive/escaped.txt`가 생겨도 HARNESS라서 PASS가 될 수 있었다. Region.HARNESS는 feedback normalization을 위한 namespace role이며 security trust boundary나 actor provenance가 아니다.

Model의 `is_extraction_path`는 fixed layout의 namespace membership만 정의한다. Oracle의 `_is_c0_namespace_transition`은 extraction root 밖 모든 관찰 경로에서 EXISTENCE/IDENTITY/OBJECT_TYPE 변화가 있는지 판정한다. HARNESS와 EXTERNAL에 같은 C0 기준을 적용하고 content/metadata-only effect는 계속 제외한다. 따라서 archive/input.tar 삭제·inode/type 교체도 C0 evidence이며 단순 content/mode 변화는 C0가 아니다. Signature v2와 C1/C2 정책은 변경하지 않는다.

Baseline ownership은 BEFORE의 실제 objects와 runtime lifecycle로 표현한다. `disposable_sandbox`가 `.`, archive/extract/outside와 sentinel을 준비하고 `run_case`가 input.tar를 쓴 뒤 BEFORE를 찍는다. AFTER는 target.run 종료 직후 bookkeeping/cleanup 전에 찍는다. 이 구간에 현재 harness namespace mutation은 없다. Phase enum과 runner/adapter 계약을 문서화하고 C0 limitations에 actor attribution의 전제 조건을 기록한다. Snapshot은 actor를 식별하지 않으므로 가상의 provenance field나 path whitelist로 변화를 면제하지 않는다.

향후 adapter가 관찰 구간 중 log/bookkeeping을 생성·삭제·교체하면 C0 false positive가 생길 수 있다. Diagnostics는 ExecutionResult로 반환하고 setup/bookkeeping은 관찰 구간 밖에 둔다. 이를 지킬 수 없는 adapter에는 별도 provenance/관찰 설계가 필요하며 HARNESS blanket exemption으로 해결하지 않는다. False negative를 숨기는 것보다 lifecycle 위반 가능성을 명시한다.

기존 harness-only regression의 AFTER 생성 + 모든 verdict nonviolation 가정은 actor를 snapshot에서 추론하므로 잘못된 가정이었다. Test는 setup을 BEFORE 전에 마치고 nonviolation assertion을 유지한다. 동시에 setup을 관찰 구간에 잘못 포함한 동일 raw transition은 C0가 되어야 한다고 검증한다. C1/C2 regression의 harness alias도 baseline에 만들고 root replacement의 retained inode는 extraction 안에 보관해 기존 판정 assertion을 유지한다. 실제 run_case/controlled adapter의 생성·삭제·교체·type/content/mode effect regression은 verdict와 signature equality가 독립적임을 증명한다.

## D015 — model stack integration과 actual duration evidence

**상태:** 채택

PR #13의 ArchiveCase order/duplicate/raw archive path 의미는 PR #15가 이미 포함하며 더 강한 field invariants와 canonical case identity를 제공한다. PR #17/#18의 ObjectSnapshot/StateSnapshot에 해당하는 canonical 구현도 PR #15의 실제 Observer/Oracle/Signature pipeline에 연결되어 있다. 특히 #18의 arbitrary duplicate snapshot objects와 extraction/protected objects를 별도 loose collection으로 보존하는 모델은 현재 sorted unique full-sandbox snapshot contract와 맞지 않는다. 따라서 #13/#17/#18의 별도 모델을 병합하지 않는다.

PR #16에서는 `duration_seconds` 개념만 canonical ExecutionResult에 흡수한다. Configured `timeout_seconds`와 별개인 finite/nonnegative actual elapsed evidence를 모든 반환 status에 기록한다. Python reference는 monotonic `perf_counter()`로 subprocess 실행 직전부터 완료 또는 timeout kill/wait 이후까지 측정하므로 process startup과 timeout cleanup overhead를 포함한다. Path validation과 pipeline의 setup/observation/판정/cleanup은 측정 구간 밖이다.

Duration은 RunResult.execution의 기존 canonical JSON 경로로 보존하며 중복 field를 만들지 않는다. Security verdict, StateSignature v2 또는 ArchiveCase identity에 포함하지 않는다. 측정 evidence를 추가하는 결정이며 throughput/time-to-first-violation 평가, Mutation/Corpus 또는 Layer 4/5 구현을 의미하지 않는다.

**Archive input path != Observed filesystem path.** ArchiveEntry.path/link_target은 normalization하지 않는 untrusted raw logical input이고 ObjectSnapshot.path는 Observer가 만든 canonical sandbox-relative evidence다. ArchiveCase의 order/duplicate 의미를 observed objects에 적용하지 않으며 StateSnapshot.objects는 unique/sorted다. StateSnapshot의 sandbox_root/phase/objects/protected_paths 구조를 유지한다. **StateSnapshot = full raw observation/evidence**, **StateSignature = normalized security-state representation**의 경계를 유지한다. `path_region()`은 current runtime-layout classification policy이며 filesystem object의 intrinsic property가 아니다.

## D016 — Feedback / Corpus v1의 독립 novelty와 unique-case retention

**상태:** v1 구현, 연구 효과는 미검증

StateSignature v2 value equality를 normalized-state novelty channel로 사용한다. 기존 schema나
HARNESS exclusion을 변경하지 않는다. Violation novelty는 Oracle의 violated 결과에서 만든
stable semantic fingerprint로 **독립적으로** 추적한다. 같은 signature라는 이유로 새 violation
evidence를 버리지 않는다. 특히 관찰 구간의 `archive/escaped.txt` 생성은 signature가 같아도
새 C0 evidence class로 interesting이어야 한다.

C0/C2 fingerprint는 contract ID와 observed path/ChangeField labels를, C1은 contract ID와
internal/sentinel path 관계를 보존한다. Raw dev/inode allocation, timestamp/content/mode
원값, ObjectSnapshot, explanation/limitations는 key에서 제외한다. 실제 `(st_dev, st_ino)`
identity 판정과 raw evidence는 기존 Oracle/RunResult에 그대로 남는다. 한 violated contract의
전체 sorted unique semantic evidence tuple이 한 class이며 incidental order/중복은 제거한다.
EXISTENCE creation/deletion과 같은 path/field의 서로 다른 변경 값은 같은 class다.

ArchiveCase case_id, TAR SHA-256, input artifact digest/HARNESS metadata와 execution
status/exit code/duration은 state novelty가 아니다. `interesting = new state OR new violation
fingerprint`이며 retention은 미래 mutation parent 보존을 뜻한다. 새로운 상태나 contract
candidate를 취약점 확정과 동일시하지 않는다.

Corpus v1은 feedback package 안의 in-memory object다. 같은 case_id는 한 번만 보존한다.
이미 보존한 case의 새 outcome은 interesting일 수 있지만 새 entry를 만들지 않는다. 이 경우도
seen state/violation indexes는 갱신하고 interesting-observation count를 올린다. 따라서
interesting observation과 retained corpus entry는 다르다. Entry는 ArchiveCase와 최초
admission observation의 signature/모든 fingerprints만 보존하며 full RunResult/raw logs나
mutation history를 저장하지 않는다. 이후 outcome으로 최초 metadata를 덮어쓰지 않는다.

Parent selection은 retained insertion order와 caller-owned random.Random에 대한 균등 baseline이다.
Global RNG/implicit seed를 사용하지 않고 empty corpus는 ValueError다. Corpus가 target 실행이나
mutation을 호출하지 않는다. Mutator → Feedback dependency도 추가하지 않는다. Adaptive scheduler,
energy/reward model, disk persistence와 fuzzing loop는 이번 범위 밖이다.

한 Corpus instance는 한 caller-controlled campaign context에 속한다. RunResult에 완전한 stable
campaign-config key가 없으므로 false campaign ID나 dynamic command hash를 만들지 않는다.
Formal runner가 commit, target/version/config, OS/kernel/architecture, seed/budget/timeout와
dependency provenance 및 raw evidence 보존을 소유한다. Cross-target persistence safety,
연구 effectiveness 또는 evaluation/ablation 성과를 주장하지 않는다. 다음 구현 단위는 별도
Task Contract의 bounded deterministic fuzzing-loop orchestration이다.

## D017 — Bounded campaign은 single-case pipeline의 상위 caller

**상태:** bounded v1 구현

`run_case`는 한 번의 실행을 유지한다. Campaign은 명시적 unique initial seeds를 순서대로
실행한 뒤 새 Corpus의 parent 선택 → mutation → 실행 → consider를 연결한다. Seed-inclusive
execution budget이며 target 반환 status/no-op도 실행 하나다. Seed는 search RNG를 소비하지
않고 이후 한 campaign RNG를 선택과 mutation에 공유한다. Infrastructure exception은 전달한다.
Frozen steps에 parent lineage와 full RunResult를 남겨 O(budget) memory를 허용한다. Default
seeds, persistence/resume와 adaptive scheduler는 추가하지 않는다. 효과 평가는 별도 연구다.

## D018 — Execution provenance는 실행 전에 고정한 configuration

**상태:** v1 구현

CampaignTarget은 단일 실행 TargetAdapter에 pre-execution `TargetProvenance` property를
추가한다. Python reference는 같은 선언에서 실행 결과의 ID/version을 기록한다. Campaign은
첫 run_case 전에 source/environment/target/sentinel 값을 freeze하고 CampaignResult에 같은
immutable 객체를 보존한다. Supplied provenance는 target/sentinel 설정 일치를 검증하며
source/environment 정확성은 caller 책임이다. Adapter 설정 또는 result의 target/version/timeout
불일치는 harness 오류로 중단한다. 실행 결과에서 configuration을 역으로 만들지 않는다.

Source는 checkout root의 full Git object ID와 nonignored tracked/untracked dirty 여부다.
Git unavailable/오류/installed distribution은 revision/dirty 모두 None이다. Dirty 여부는 patch나
source-content hash가 아니므로 dirty 실행은 commit만으로 재현 가능하다고 주장하지 않는다.
Environment는 실행하는 Python process의 platform system/release/machine/python_version이며
release는 kernel/platform 문자열, unavailable platform field는 empty string이다. Host/user 식별자는
없다. Sentinel은 outside/ 상대 name 순서로 정렬한 content SHA-256/mode다. 실제 snapshot evidence와
구분하며 signature/novelty/oracle 입력에 넣지 않는다. Seed/budget은 CampaignConfig에만 둔다.

Manifest v2는 stored execution_provenance와 observed execution_contexts/export_environment를
분리한다. Step의 기존 canonical envelope schema v1은 유지한다. 이 metadata는 raw engineering
provenance이며 scientific interpretation, OS isolation 보장이나 완전한 dependency lock이 아니다.

## D019 — Target execution safety 선언과 campaign fail-closed 경계

**상태:** contract 구현; OS execution isolation은 미구현

TargetProvenance의 ExecutionSafety는 adapter trust/configuration 선언이다. Default는
ISOLATION_REQUIRED이며 string/미선언 값은 허용하지 않는다. 현재 Python reference만
TRUSTED_REFERENCE를 선언한다. Campaign은 isolation-required/미선언 target을 provenance capture,
runtime 생성과 첫 run_case 이전에 거부한다. Caller가 supplied provenance로 requirement를
낮추거나 runtime 경로/container 여부로 isolation을 추정하는 option은 없다. Requirement는
stored provenance/manifest에 남고 StateSignature나 Oracle verdict가 되지 않는다.

이 선언은 OS containment 증명이 아니다. Dev Container/CI는 development 환경으로 source
쓰기/network/설정된 volume/동일 사용자 권한 접근이 남는다. O_NOFOLLOW와 fd-safe cleanup은
harness 경로 검증/cleanup만 담당한다. Future third-party campaign에는 별도로 검증한 OS
process/filesystem/credential/network/resource 경계와 자식 process 종료 보장이 필요하다.
그 전에는 explicit ordinary controlled fixtures를 사용한 adapter engineering만 허용한다.
Low-level TargetAdapter.run/run_case는 caller-owned fixture execution API이며 campaign safety
gate를 대신하지 않는다. 임의 생성 입력 또는 untrusted archive를 third-party에 연결하지 않는다.

## D020 — Node-tar는 고정 tooling으로 정상 fixture integration만 검증

**상태:** adapter v1; third-party campaign isolation은 미구현

Node-specific worker/invocation/version/status와 process lifecycle는 targets/에 둔다. Node/package
version은 setup에서 발견하고 worker가 tar.x 전에 기대 version을 확인한다. Target identity는
node-tar-strict / node=<exact>;tar=<exact>, timeout과 ISOLATION_REQUIRED를 provenance로 선언한다.
Strict=true/preservePaths=false와 나머지 upstream defaults를 사용한다. TAR_* error는 REJECTED,
worker error는 FAILED이며 version mismatch는 harness error다. Raw streams/command/duration은
ExecutionResult에 남고 generic observer/oracle/feedback/mutation에는 Node logic이 없다.

Node 22.22.0/tar 7.5.22와 npm transitive lock은 benign validation baseline이며 vulnerable-version
benchmark 선택이 아니다. Linux process group kill/direct-child wait는 timeout lifecycle이고
OS sandbox/detached descendant containment/subreaper가 아니다. No credential env inheritance,
no observation-window bookkeeping을 지킨다. Campaign의 isolation-required rejection은 유지한다.


## D021 — Experiment config identity와 actual execution provenance를 분리

**상태:** configuration v1 구현

ExperimentConfig는 기존 CampaignConfig/TargetProvenance/SentinelSpec 의미를 재사용한다. 모든
research-critical field를 요구하는 JSON schema v1, immutable value와 explicit seed/target binding을
제공한다. 현재 구현한 seed/mutation/feedback policy만 허용한다. Canonical sorted-key compact
ASCII JSON의 SHA-256이 config_id이며 sentinel order/timeout numeric spelling만 semantic normalize한다.
Ordered initial IDs는 정렬하지 않는다. Source/kernel/runtime allocation/result는 config ID에 없다.
Environment profile은 expected setup label이며 actual execution environment는 frozen provenance다.

Campaign은 optional explicit experiment_config_id를 첫 실행 전에 받고 result/manifest에 그대로
남긴다. None은 formal config 없이 실행한 API다. Config wrapper/CLI는 actual configuration binding을
검증하며 low-level caller assertion과 구분한다. CLI는 safe Python reference 전용이고 immutable
config를 experiment.json으로 raw evidence와 함께 보존한다. Node-tar campaign safety gate는 유지한다.

## D022 — Untrusted target은 별도 disposable Linux container에서 실행

**상태:** container backend와 benign helper 검증; campaign binding은 후속.

PR #34의 Dev Container namespace EPERM을 근거로 maintainer Task Contract가 별도
container boundary를 선택했다. Dev Container privileges를 넓히지 않는다. Trusted
Linux controller는 explicit stdio host CLI broker를 통해 sibling target container를
생성한다. Target에는 controller의 source/home/socket이나 전체 runtime volume을 주지
않고 현재 run의 volume-subpath만 동일 absolute path로 노출한다. Observer의 object
identity와 전체 controlled external/harness effects를 보존한다. Backend는 Oracle,
feedback, mutation과 target-specific policy를 import하지 않는다.

Container setup은 BEFORE 이전, stopped PID namespace 확인은 AFTER 이전, removal은
AFTER 이후다. Host broker는 invocation 소유 identity만 다시 cleanup하며 runtime 오류를
target status로 숨기지 않는다. 구체적 policy/검증/한계는
[execution 계약](../src/inodefence/execution/README.md)을 따른다.

## D023 — Node target image는 build tooling과 runtime을 분리

**상태:** pinned image와 metadata-only container 검증.

Digest-pinned Node build stage에서 committed npm lock으로 dependencies를 설치하고,
digest-pinned distroless Debian 12 runtime에는 Node binary, modules, lock과 worker만
복사한다. Exact Node/tar version 및 worker/lock SHA-256을 container 안에서 확인한다.
실행은 mutable tag가 아닌 immutable local image ID를 받는다. Platform/build metadata로
image ID가 달라질 수 있어 bit-for-bit build reproducibility를 주장하지 않는다.
Image packaging은 campaign permission이나 Security Contract verdict가 아니다.

## D024 — Target invocation과 contained execution을 composition으로 연결

NodeTarTarget은 immutable image/command/version/status descriptor다. bind는 실제
image 안에서 identity를 확인하고 IsolatedTarget을 반환한다. Descriptor에는 run이나
subprocess fallback이 없다. IsolatedTarget과 ExecutionBackend가 lifecycle을 소유하며
새 backend 구현은 trusted controller code의 검토 대상이다. Campaign admission은
별도 frozen isolation/config binding이 완료되기 전까지 기존 rejection을 유지한다.

PreparedTarget context를 pipeline의 BEFORE/AFTER 바깥에 배치한다. Reference path는
기존 run 호출을 유지한다. Setup/cleanup은 관찰 결과를 오염시키지 않고 AFTER 오류에도
container/runtime을 회수한다. Start deadline이 launch 전에 끝나면 daemon의 뒤늦은
start를 막기 위해 container identity를 먼저 파괴·확인하고 AFTER를 캡처한다.


## D025 — Isolation policy identity와 실행 시점 attestation을 freeze

Pure immutable IsolationPolicy는 actual backend configuration과 ExperimentConfig v2를
연결한다. Image ID/uid/gid/network/rootfs/caps/NNP/namespaces/view/environment/resources/
shared-memory/capture limits를 config identity에 넣고 allocation/volume/PID/time은 제외한다.
Config v1의 기존 bytes/ID는 유지한다. Backend/runtime/image/worker/lock facts를 첫 archive
이전에 고정하고 policy/artifact drift 또는 supplied provenance 불일치는 중단한다.

Isolation-required campaign은 exact IsolatedTarget composition만 받는다. Subclass,
attribute/boolean, config나 supplied provenance는 실행 경계를 인증하지 않는다. 새 backend
구현은 trusted controller implementation으로 별도 실제 검증이 필요하다. ExperimentConfig
binding과 gate 모두 fail closed이며 ordinary subprocess fallback은 없다.

ExecutionProvenance/CampaignResult canonical envelope는 v2, manifest는 v3로 명시적으로
version을 올린다. ArchiveCase/RunResult/CampaignStep encoding, C0/C1/C2, signature novelty,
mutation/RNG/budget은 유지한다. Export는 stored facts만 serialize한다. Image ID는 compact
content anchor이며 worker/lock digest를 함께 기록한다. Dirty patch 보존은 미구현이고
container/kernel trust, snapshot-only 관찰 및 storage/CPU 제한은 계속 명시한다.

## D026 — Completed evidence uses Linux staged no-overwrite publication

A completed result writer stages a unique 0700 sibling directory. It flushes/fsyncs closed
files, verifies generated JSONL/checksum/config/manifest, syncs staging, publishes through
renameat2(RENAME_NOREPLACE), then syncs the parent. Ordinary rename is not a fallback because
it can replace a concurrently created empty directory. Unsupported Linux/libc/filesystem fails
visibly; this matches the supported Linux execution workflow, not a portability promise.
Manifest v4 explicitly records optional config file/checksum; supplied config bytes must match
the stored config ID and are published with evidence. Historical manifests remain historical.
Pre-publication exceptions remove staging and leave final absent. Hard interruption may leave
staging; after-publication sync error leaves complete evidence and propagates. Parent creation
is not rolled back. No database/checkpoint/crash-proof storage claim is made.

## D027 — Pre-audit infrastructure freeze after benign contained Node validation

Container backend, pinned target, exact config/provenance binding, lifecycle validation and
staged export establish ENGINE READY / BENCHMARK INFRASTRUCTURE READY for the approved
benign path. Status becomes READY FOR FULL CODE / ARCHITECTURE AUDIT. This is a limited
integration/dependency/attestation review, not the full code audit or evaluation readiness.
Image ID plus worker/lock digests provide the compact content anchor; no extra tree hashing
is justified before that audit. Dirty patch, exact Python binary, runtime/kernel portability,
total storage/CPU limits and hard-interruption persistence remain explicit limitations.
Feature expansion stops; next is the full repository-wide audit, then a separate research
Task Contract before benchmark/CVE evaluation. Historical audit/smoke summaries keep their
original revision and claims rather than being rewritten as current guarantees.

## D028 — Frozen engine findings v1: exact serialization and typed evidence

EN-001–005의 Phase-3 Task Contract는 audited main fae2954906fa1a95235cde5cddd4dcb73f334169에서
시작한다. Audit artifacts는 pinned evidence이며 production ancestry가 아니다.

USTAR builder는 실제 encoded name/prefix에서 복원한 raw path가 input과 정확히 같은지
검증한다. Lossy split은 reject하며 existing valid bytes와 `ustar-utf8-v1` ID를 유지한다.
Public immutable evidence/key constructor는 text/scalar와 nested tuple/member types를 검증한다.
StateChange labels는 모든 실제 차이와 정확히 일치하며 creation/deletion은 EXISTENCE만 가진다.
RunResult의 cross-record derivation은 pipeline-owned이고 campaign/Corpus counter assembly는
trusted producer 경계다. 이 변경은 reader나 provenance authenticity 검증을 제공하지 않는다.

StateSignature v3는 symlink target을 `run:<raw suffix>` 또는 `literal:<raw target>`으로 tag한다.
Run-root allocation만 normalize하며 raw snapshots, repeated slash와 `..`를 보존하고 referent를
resolve하지 않는다. V2 keys와 호환성/migration은 제공하지 않는다. Canonical envelope v1,
ArchiveCase identity, fingerprint/novelty policy, RNG/budget 및 C0/C1/C2 predicates는 유지한다.
Historical decisions/audit/smoke summaries는 이전 revision의 기록으로 남긴다.
[Fix mapping과 frozen evidence](audits/engine-findings-fix-v1.md)를 따른다.

## D029 — Policy-aware campaign caller shares the execution gate

**상태:** independent caller API v1 구현

`SearchCampaignConfig`와 `run_search_campaign`은 B0/B1/B3, versioned mutation과 feedback projection을
bounded single-case pipeline에 연결한다. Legacy campaign과 실행 safety/provenance 검증을 공유하여
alternative search가 isolation requirement를 우회하지 못하게 한다. 원래 runner/Corpus의 B3 동작과
serialized model은 유지하며 새 caller output은 구분된 SearchCampaignResult/Step envelope v1이다.

새 result는 full raw evidence, diagnostic novelty, explicit admission, policy IDs와 B0 working parent를
보존한다. Full-state diagnostic count와 projected-key count를 분리한다. ExperimentConfig와 durable
Evaluation reader/journal/export binding은 해당 ownership의 새 schema 지원까지 독립 dependency로
남긴다. In-memory engineering validation은 정책의 연구상 효과나 benchmark readiness를 의미하지 않는다.

## D030 — G0 documentation freeze anchors claims to an immutable capability baseline

**상태:** user Task Contract에 따른 documentation freeze; PR review/acceptance 대상

Capability baseline은 main `8ad07b8e5f23f789d57ea50ba52c7acfcee951ea`다.
[Research Contract v1](research/design/research-contract-v1.md)은 G0 정의를 한 authority map에
연결하고 DESIGNED / IMPLEMENTED / TESTED / EXPERIMENTALLY VALIDATED를 구분한다.
현재 source가 실행하는 비교는 B0/B1/B3와 A1/A2/A3다. RQ2/RQ3의 오래된 path-only/fixed-recipe
baseline 및 F0–F3 ladder를 이 실제 비교로 reconcile하며, 미구현 비교에 대한 우월성을 주장하지 않는다.

`SearchDecision.interesting`은 full state OR fingerprint diagnostic novelty다.
Protocol의 variant-specific admission rate는 `admission_eligible`을 사용하도록 용어를 정정한다.
Budget/repetition/subset/confirmation criteria는 기존 provisional plan을 유지하며 later
experiment freeze에서 qualification/pilot evidence로 확정한다. 이 변경은 formal methodology를
결과에 맞추는 변경이 아니고 raw output, oracle predicates, config APIs 또는 search를 바꾸지 않는다.

Historical qualification의 첫 intended pair는 N01 node-tar 7.5.2/7.5.3이다. M1 구조가 있어도
finite vocabulary의 default sentinel addressing은 미해결이다. Catalog는 current baseline만
갱신하고 original upstream access date/pins와 all-NOT_RUN states를 보존한다.
역사적 audit/handoff는 명시적으로 superseded하며 원래 validation 기록을 유지한다.
G0 정의 승인은 G1 이후 readiness나 benchmark/CVE evidence로 승격되지 않는다.

## D031 — Node-tar native archive-ordered transition v1은 qualification failure로 중단

**상태:** `BLOCKED_NATIVE_OBSERVATION`; v2 native 구현 아님

Node 22.22.0/node-tar 7.5.22의 public events, Linux filesystem/syscall 관찰,
fresh-process prefix replay, private completion callback snapshot과 async-context causal
filesystem-effect 후보는 모두 current `TransitionTrace` v1의 complete archive-prefix
checkpoint 의미를 통과하지 못했다. 별도 libarchive public boundary도 directory metadata
finalization 때문에 실패했다.

Causal-effect v4는 1,020개 operation을 exact entry에 귀속했지만 independent-files 20/20에서
completion `0,1,3,2`와 earlier marker 전 162개 later-ordinal operation을 관찰했다. 이는
callback receipt를 바꾸거나 snapshot을 다시 걷는 방식으로 제거할 수 없는 실제 namespace
overlap이다. Instrumented profile의 scheduling distribution과 bounded timing도 minimal profile과
달라 neutrality를 입증하지 못했다.

따라서 node-tar native producer를 v1 model에 추가하지 않고 실제 target P0/P1/P2를 실행하지
않는다. Existing C0/C1/C2, `RunResult`, synthetic v1 model/scheduler/evaluation은 유지한다.
대체 방향은 archive order, observed effect order와 supported causality를 분리하는 별도
[partial-order/effect-event v2 observation contract](research/design/entry-effect-observation-v2.md)다. V2가
qualification을 통과하기 전에는 v1 `TransitionFeedbackKey` 또는 P1/P2 policy ID를 재사용하거나
incomplete/lossy event를 reward로 승격하지 않는다.

## D032 — Effect v2는 operation evidence, state claim과 causal relation을 분리한다

**상태:** Design Gate 1 / Synthetic Gate 2 PASS; native는 NOT_QUALIFIED

V2는 archive order, global observed lifecycle/operation-boundary sequence와 supported causal DAG를
서로 다른 relation으로 보존한다. Callback/operation success는 raw result이며 namespace/content/
metadata/identity state change의 충분한 증거가 아니다. Generic effect claim은 class별 qualified
before/after identity/state evidence를 요구하고, hardlink relation은 실제 `(st_dev, st_ino)` 관계
증거를 요구한다. Exact path/inode/timestamp/sequence/count는 normalized key에서 제외한다.

Feedback은 verified individual effect, unique per-entry effect set, one-edge causal motif의 finite
key universe를 사용한다. Completion-order permutation, timestamp proximity, same path, archive
ordinal과 unsupported overlap은 causal edge나 reward를 만들지 않는다. Observation failure,
loss/overflow/conflict/invalid identity/incomplete flush는 novelty index를 갱신하지 않고 corpus와
scheduler 모두에서 fail closed한다. Initial policy는 fully flushed rejection prefix도 admission/
reward하지 않는다.

P0-v2/P1-v2/P2-v2는 새 policy/evidence schema를 사용하고 동일한 full instrumentation cost를
부담한다. P1-v2는 P0-v2 대비 retention만, P2-v2는 P1-v2 대비 bounded 1–8 operator scheduling만
바꾼다. V1 TransitionTrace/keys/IDs, RunResult, legacy serialization과 C0/C1/C2는 변경하지 않는다.
Native work는 별도 producer/reader qualification이
`V2_NATIVE_EFFECT_OBSERVATION_QUALIFIED`를 기록하기 전까지 campaign으로 연결하지 않는다.
세부 계약은 [architecture](research/design/entry-effect-architecture-v2.md),
[feedback](research/design/entry-effect-feedback-v2.md),
[review/plan](research/design/entry-effect-design-review-v2.md)을 따른다.

## D033 — Policy full-step timing은 기존 result와 분리된 evidence다

**상태:** final-state policy engineering interface v1 구현; formal measurement NOT_RUN

`run_search_campaign`은 optional completed-step sink를 각 `run_case` cleanup과 feedback/step
assembly가 끝난 직후, 다음 execution 전에 호출한다. Sink exception은 전달하고 다음 step을
시작하지 않는다. Existing SearchCampaignResult/Step schema, policy ID, RNG, mutation, feedback와
target `duration_seconds` 의미는 바꾸지 않는다. Core는 여전히 failure 시 partial result를 반환하지
않으며 sink가 보존한 incremental evidence의 소유권은 caller에게 있다.

별도 `policy-full-step-monotonic-v1` wrapper는 campaign preflight 직전 monotonic origin에서
각 completed-step callback observation point와 final result assembly까지의 contiguous nanosecond offset,
그리고 descriptive UTC start/end를 기록한다. Step duration은 target process time의 합이나
복사본이 아니며 setup, selection/mutation, full `run_case`/cleanup, feedback와 wrapper overhead를
포함한다. Existing bound policy bundle과 timing bytes는 새 last-published manifest로 함께 bind하고
independent reader가 config/result/count/offset/checksum을 검증한다.

이 interface는 in-memory completed timing evidence만 제공한다. Disk publication latency,
automatic journal attachment, exception-safe aborted prefix/failure ledger, known-class adjudication,
timed dataset pooling과 formal throughput/time-to-hit 결과는 별도 dependency로 남는다.

## D034 — Namespace rebinding v3는 v2 replacement를 바꾸지 않는 composite다

**상태:** generic model/reader/feedback IMPLEMENTED / SYNTHETIC TESTED; native NOT_IMPLEMENTED

V2 `namespace_replacement`는 계속 단일 correlated operation의 present-before/present-after
identity 또는 type change만 뜻한다. 여러 operation으로 이루어진 rebinding은 별도 schema 3
`NamespaceRebindingSequence`로만 표현하며 과거 v2 raw bundle이나 qualification 판정을
재분류하지 않는다.

Composite는 같은 immutable archive entry와 canonical destination path, 성공한 realized
removal/creation(link 포함), removal 이후와 creation 이전의 두 explicit absence, exact endpoint를
잇는 producer branch-continuation dependency, complete/valid/successful v2 trace와 conflict-free
same-path gap을 모두 요구한다. 시간적 인접성, 같은 path/ordinal, inode equality/inequality 또는
기존 v2 context edge만으로 dependency를 추론하지 않는다. Strict reader는 raw v3 envelope를
source/digest로 v2 stream에 묶고, 외부 frozen manifest의 expected v3 raw SHA-256과 실제 bytes를
parsing 전에 비교하며, endpoint 전체를 v2 event와 다시 비교한 뒤 composite를 직접 파생한다.
Envelope 내부 records digest는 trust root가 아니므로 dependency token과 함께 재계산해도 외부
digest 검사를 우회할 수 없다.

Feedback은 기존 `effect_feedback_keys(trace)` tuple을 그대로 보존하고 finite tagged v3 key만
추가한다. Synthetic nonredundancy fixture는 같은 v2 key set을 가진 same-path와 cross-path trace 중
전자에만 v3 key가 생김을 확인했다. 이 결정은 C0/C1/C2, v2 policy ID, native qualification 또는
효과 검증을 변경하지 않는다. Native dependency producer와 matrix는 새 Task Contract와 명시적
승인 전까지 NOT_IMPLEMENTED / NOT_RUN이다.

## D035 — 머지는 사람 게이트가 아니다: 자율 루프가 PR·CI·verifier 통과 후 스스로 머지한다

**상태:** 적용 (2026-10-30, 지웅 결정)

이전 규칙은 "사람의 개입은 머지뿐이다"였다. autoloop·builder·orchestrator 정의, WORKLOG/BACKLOG/CONTRIBUTING/README의
문장, 그리고 가드 훅 R2의 `gh pr merge` 차단이 이를 강제했다. 이 결정으로 머지는 루프의 마지막 단계가 된다:
기록 커밋이 끝난 작업 브랜치로 PR을 열고(`--body-file`, 첫 항목은 AGENTS.md PR 규칙의 질문에 대한 답), CI 두 job 통과와
verifier `PASS`를 확인한 뒤 작성자(사람 또는 에이전트)가 `gh pr merge --squash --delete-branch`로 머지한다. 머지 여부의
기준은 PR 상태다. WORKLOG 상태 `검토대기`의 뜻은 "검증 통과, PR·CI·verifier 검토 후 자율 머지 대상"으로 바뀐다.

바뀌지 않는 것: `main` 직접 push 금지(가드 R2는 push 차단만 남긴다), 스택 PR 금지, 가드·격리·allowlist 설정은 사람만
수정(R4), FROZEN 불변, 새 audit/readiness류 문서 금지. 사람 승인이 남는 결정은 안전경계·연구 불변식에 걸리는 것만이다:
`BREAKING`(oracle 판정 변경, autoloop 5절 4항), 가드·격리·allowlist 설정 변경, FROZEN 변경, 외부 공개. 이런 PR은 열어
두되 머지하지 않고 "사람 결정"으로 기록한다.

근거: 루프의 검증 게이트(`make check`, CI, verifier의 범위·oracle 의미·FROZEN·기록 검토)가 머지 전에 이미 돈다. 사람
머지 대기는 작업 간 의존("대기(머지 필요)")을 쌓아 루프를 멈추게 했을 뿐 검증을 더하지 않았다. GitHub `main`에는
branch protection·ruleset이 없다(observed 2026-10-30, `gh api .../branches/main/protection` 404, rulesets `[]`).
가드 훅 파일 자체는 R4 보호 대상이라 에이전트가 고치지 않고 사람이 패치를 적용했다.

## D036 — 자율 루프의 끝은 BACKLOG 소진이 아니라 프로젝트 완료다

**상태:** 적용 (2026-10-30, 지웅 결정)

이전 autoloop 규칙은 "진행할 안전한 항목이 없으면 대기한다. 일을 만들어 내지 않는다"였다. D035로 머지 대기가
사라지자 남은 정지 조건은 큐 소진 하나였고, 이는 설계가 정한 목적(가설 검증, M1~M4 완료)과 무관한 지점에서
루프를 멈추게 했다. 이 결정으로 루프의 종료 조건은 세 가지가 모두 참일 때로 바뀐다(autoloop 7.1): M1~M4 완료
(M3은 사전 고정 지표·예산·반복으로 기록된 H1 판정 — 검정력 없는 음성은 판정이 아니다), raw → summary →
finding → `paper/`의 증거 사슬, 그리고 더 뽑을 항목이 없는 큐.

큐가 비면 루프는 멈추지 않고 항목 1개를 보충한다(7.2): 해소된 `막힘` 재개 → STATUS Ledger에서 증거 수준이 가장
낮은 미완 마일스톤의 다음 gate(STATUS "다음 연구 gate" 순서와 H1~H4 기준) → 상시 표. 보충 행은 그 항목을
수행하는 작업 브랜치에 함께 커밋한다. "일을 만들어 내지 않는다"의 뜻은 "Ledger 빈 칸에 닿지 않는 일을 만들지
않는다"로 좁힌다: 감사·readiness류 문서, 범위 밖 refactor, 결과를 본 뒤 지표·예산을 바꾸는 일, 발표용 임시
구현은 여전히 금지이고, 독립 반복·사전고정 예산 확대·대조군·2번째 extractor·증거 사슬 보강은 만든다.

바뀌지 않는 것: 안전경계(sandbox+sentinel, 고정 버전, 격리 완화 금지, 훅 우회 금지), 연구 불변식(D005·D006,
observed/inferred, synthetic 비승격, 비교 없는 effectiveness 주장 금지), evaluation 원칙(결과를 보고 방법을
바꾸지 않음), 사람 게이트(외부 공개, 가드·격리·allowlist, FROZEN, BREAKING, 승인 범위 밖 예산). 연속 실행은
`/loop autoloop`으로 하며 턴 종료는 7.1 충족 또는 전부 사람 게이트일 때만이다(7.3).

## D037 — 수술 기간 병합 정책·GitHub 브랜치 보호

**상태:** **결정(지웅, 2026-11-04)** — 선택지 A 채택. 2026-11-03 예약분은 아래 "결정 전 임시 정책"으로 보존.

**결정.** 수술 기간(2026-11-03~11-30) 동안 **지웅은 PR의 최종 squash merge만 직접 수행**하고, 그 외 모든 작업 —
코드 수정, 문서 작성, 사전등록 파일(v2.1·EXP-3) 작성·커밋, PR 생성·갱신, CI 확인, 독립 verifier 검증, 충돌 해소,
BACKLOG/STATUS/WORKLOG 갱신 — 은 오케스트레이터와 레인 세션에 위임한다. 운영 규칙:

- 머지 대기는 작업 중단 사유가 아니다. 의존 작업은 같은 레인의 직전 브랜치 위 스택 PR로 계속한다(AGENTS.md 스택 규칙).
- HEAD SHA가 바뀐 PR(main merge-in 등)은 과거 verifier PASS를 재사용하지 않고 최신 SHA 기준 CI·delta 재검증을 받는다.
  충돌(특히 `docs/LOG.md` EOF 추가 충돌)은 담당 레인이 `git merge`(rebase·force-push 금지)로 보존·해소하고 재검증 후
  최신 SHA로 머지 요청한다. 웹 편집기에서 즉석 해결하며 연속 머지하지 않는다.
- 머지 요청은 PR 번호·HEAD SHA·목적·변경 범위·CI·verifier 판정·선행 PR·권장 순서를 표로 제출한다.
- autoloop·builder의 자율 머지 루프(D035)는 수술 기간 종료(11/30) 또는 지웅의 별도 결정까지 시작하지 않는다.
- 서버 측 브랜치 보호: "PR 필수 + CI 필수 체크"만 권장(설정은 GitHub 관리자인 지웅이 수행; verifier는 필수 체크로
  올리지 않음 — 레인 세션의 PR 코멘트 판정으로 대체).

바뀌지 않는 것은 아래 임시 정책의 마지막 문단과 같다. 수술 기간 뒤 D035로 복귀할지는 별도 결정.

### 결정 전 임시 정책 (2026-11-03 예약, 보존)

수술 기간(2026-11-03~11-30)의 병합 정책과 GitHub `main` 브랜치 보호를 한 번에 결정한다. 결정 전 **임시 정책**:

- PR은 에이전트가 열고(`--body-file`, 첫 항목은 AGENTS.md PR 규칙의 질문에 대한 답), **머지는 지웅이 직접** 한다.
- autoloop·builder의 **자율 머지 루프는 D037 결정 전 시작하지 않는다**(D035의 자율 squash 머지는 보류).
- 서버 측 브랜치 보호(required check·review)를 켜면 D035("머지는 사람 게이트가 아니다")와 충돌하므로,
  verifier를 **필수 체크(required status check)**로 포함할지까지 묶어 한 번에 결정한다. 결정 시 D035를 갱신한다.

바뀌지 않는 것: `main` 직접 push 금지(R2), 가드·격리·allowlist 설정은 사람만(R4), FROZEN 불변, 새 audit/readiness류
문서 금지(R1).

## D038 — 수술 기간 연구 설계 재정립

**상태:** 적용 (2026-11-03, 지웅 결정: 2026-11-03 독립 감사 문서 채택). 실험 순서·규모·종단점·R arm은 [D040](#d040--exp-3-동결-전-재판정-위험도-파일럿-4040-반영)이 개정한다.

2026-11-03 독립 연구 감사(Claude Doc 「InodeFence 독립 연구 감사 및 실험 설계 재정립」, https://claude.ai/artifact/JJtsK3VowEGuBFN3YXZDFq)를
수술 기간의 **계획 기준**으로 채택하고 연구 설계를 다음과 같이 재정립한다. 상세는
[research-questions v2](research/design/research-questions.md).

- **단일 RQ**와 **H-A / H-B / H-C.** H-A(주): 피해 경로 이름을 아는 동일 어휘·동일 예산 아래 filesystem
  security state 피드백 탐색이 무작위·구조 커버리지 탐색보다 첫 경계위반까지 빠르고 고유 위반을 더 찾는가.
  H-B: generic oracle이 ≥3 extractor 취약/수정 쌍을 구분(재확인). H-C(보조): 어휘에 이름이 없으면 전 arm C1
  미도달(음성 통제).
- **비교군 R/D/S-u, 동일 어휘·동일 스케줄러.** R 무작위(retention 없음·uniform), D 구조 커버리지 retention
  (`SearchPolicy.D`)·uniform, **S-u** identity/effect/boundary-attempt retention·**uniform**(주 비교; D와 operator
  정책을 동일하게 통제해 retention 효과만 분리). adaptive 스케줄러를 얹은 S-a는 **탐색적 ablation(선택)**이며
  S-a − S-u는 스케줄러 효과로 따로 해석한다. 관찰 이름 포함 여부는 세 arm에 동일 적용. 기존 기호
  **A1(random floor)/A3full은 폐기**한다(v1 ablation 기호와 충돌).
- **1차 지표 = T_first·U_viol, 생존분석.** T_first는 첫 C1∨C2까지 실행 수(우측중도절단: 완주 무hit=N, abort=abort
  시점), U_viol은 정규화 서명 기준 고유 위반 입력 수. Kaplan–Meier·로그랭크·A12. 새 state key 수는 설명용(EN-008).
- **실험 순서.** EXP-0 파일럿(5 seed×200×R/D/S, 인프라 측정) → **11/18 사전등록**(EXP-3 + EXP-2 GO/NO-GO 규칙,
  x·n은 EXP-0 실측으로 11/14 확정) → EXP-3(20 seed×2000×R/D/S, 다수 sentinel) → **11/20 규칙 기계 적용** → EXP-2
  조건부. 파일럿 데이터는 formal 추정에 합산하지 않는다.
- **MVP 범위.** node-tar 7.5.2/7.5.3·7.5.6/7.5.7 + Python tarfile `fully_trusted`/`data`. 자력발견 타깃은 node-tar
  하나. decompress는 확장, oras-go는 oracle 일반성 증거로만. entry-transition 계열·GNU·Windows는 범위 밖.
- **기준 3층.** 계획 = Claude Doc(포인터만, 복사본 없음) · 실행 = Git에 동결된 사전등록 파일 + 엔진 SHA +
  이미지 digest · 증거 = raw + SHA-256 목록(`experiments/summaries/raw-manifest-*.sha256`, 기준선 태그
  `audit-baseline-20261103`).

**바뀌지 않는 것:** 안전경계(disposable sandbox + sentinel, 고정 버전, 격리 완화 금지, 훅 우회 금지, 실제 민감 파일
금지), D005(CVE-specific oracle 금지)·D006(known PoC seed 금지)·D007(zero-day는 성공 조건 아님), **oracle 정의
(C0/C1/C2 불변)**. C2 대상(sentinel 집합) 확장은 Oracle 레인의 **별도 사람 승인**이 필요하다. 문서가 STATUS·BACKLOG·
AGENTS·메모리·논문 초안과 충돌하면 문서가 맞고 저장소를 문서에 맞춰 바로잡는다.

## D040 — EXP-3 동결 전 재판정: 위험도 파일럿 40/40 반영

**상태:** 적용 (2026-11-07, 지웅 결정: W3 재판정 권고 D1~D21 일괄 채택, 오케스트레이터 전달)

이 기록은 결정이다. 구현과 사전등록 동결은 별도 PR이고, 수치는 계획 입력(추론)이지 결과가 아니다. 어떤 값도 확증 검정력을 뜻하지 않는다.

**번호.** 아래 D1~D21은 재판정 항목 번호이고 이 문서의 D001~ 결정 번호와 다르다. 다른 문서에서 인용할 때는 `D040-D7`처럼 쓴다. D039는 #261 몫으로 비워 둔다.

**근거(저장소).** [파일럿 결과 메모](../experiments/summaries/exp3-hazard-pilot-v1-result.md), [파일럿 설계](../experiments/preregistration/exp3-hazard-pilot-v1.md),
[규모 산정 폴더](../experiments/preregistration/exp3-sizing-20261107/README.md)(`results.json`, `run-grid.log`), [노출 원장](../experiments/preregistration/exposure-ledger.md).
미머지 근거는 사전등록 초안 `exp3-v1.md`(#264 `e11d302`)와 `rust_tar_fixture_probe.json`(#261)이다.

**R=D=0 폐기.** 파일럿에서 첫 C1∨C2 사건은 S-u 6/10, R-restart 4/10, D 4/10, R-walk 1/10이고 구간이 크게 겹친다. 이 표본은 arm 우위의 근거가 아니다.
질문은 "피드백만 도달하는가"가 아니라 "얼마나 빨리 도달하는가"다. 핵심 RQ 문장은 유지한다. 예측은 "T_first 중앙값 2배"에서 HR ≥ 2로 바꾸고, A12는 보조로 둔다.

**규모 모형.** 규칙 C 기계 출력 114는 사전 규칙 출력이라 소급 변경하지 않는다. 계획 기준은 등록 통계량(합동 2-arm 로그랭크, 블록 내 라벨 순열)의 약 76~80이다. 참고값 120은 등록 검정의 모형이 아니므로 쓰지 않는다.

### 항목별 결정

| ID | 질문 | 결정 | 이유·근거 |
| --- | --- | --- | --- |
| D1 | 구조 | **(A) 2단계 유지, 등록 파일 2개.** `exp3-v1`(train n=20, 탐색, 인프라 게이트) → `exp2-v1`(holdout 확증). 11/18에 함께 동결 | D038 순서와 같다. n=20은 확증 규모가 아니다. train 결합 검정력은 약 .17이다(등록 판정(순열) .174, 800회, 표준오차 .013; `exp3_power_registered.py permutation --sims 800 --perms 1000 --n 20`) |
| D2 | holdout 허용 | **(a) 불변 표 1줄.** FROZEN 미변경 | 승인 범위 확대이므로 이 행이 사람 승인이다. `scripts/run_effect_demo.py` |
| D3 | 캠페인 타깃 | **(a) train + holdout만.** 7.5.6/7.5.7·py-tarfile 캠페인과 S-a는 블록에서 뺀다 | 7.5.6/7.5.7은 H-A 추론 제외이고 고정 fixture 증거가 있다 |
| D4 | holdout 선정 | **(a) minor별 최신 patch 5개 {7.0.1, 7.1.0, 7.2.0, 7.3.0, 7.4.4} 상태 확인 후 위반∧어댑터 호환 중 최고 버전.** 부적격 전부면 D1(D, holdout 포기·탐색 등록만)로 자동 전환 | 후보 5개는 원장·이미지 모두에 없다. fixture 위반은 탐색 hazard를 보장하지 않는다. 어댑터 호환은 미검증이다 |
| D5 | 상태 확인 기록 | **(a) `qualification-only` 범주 신설, 게이트가 이 범주만 holdout 허용.** D4보다 먼저 구현 | 아래 조건 4개 |
| D6 | R 변형 | **(b) seed-restart** (`unretained-seed-restart-v1-uniform-mutation-v1`) | 비-사건 지표로 고른다. walk는 거부 99.7%, 변이 성공 .12%, entry 347로 퇴화했다(결과 메모 §7). 사건도 restart가 더 많아 S-u에 불리한 쪽이다 |
| D7 | n, k | **n=120/arm(상한), k=5** | 120은 holdout hazard가 절반(s=.5)이거나 HR이 1.75여도 약 .76~.79를 지킨다(`run-grid.log`, χ² 근사). HR 1.5나 s=.25에서는 어떤 n도 창 안에서 80%가 안 되며 D12 표가 처리한다. k=3 hazard는 미측정이다 |
| D8 | sentinel | **(b) k=5** | D7과 같다. 전 arm 동일 적용 |
| D9 | 파일럿 | **(c) 40캠페인, 완료** | 결과 메모 |
| D10 | 1차 검정 사양 | **(a) 비동일 블록 ≤16이면 exact, 초과면 MC 100000·seed 고정·(ge+1)/(N+1). α = 패밀리 .05 양측 + Holm** | 등록 내용과 실제 동작을 맞춘다 |
| D11 | GO 값 | **GO = E≥1 ∧ ⌊H_rem·r÷(6000·e)⌋ ≥ 76 ∧ train abort ≤ .45** | 아래 정의. E≥1은 사실상 위생 조건이고 실제 판단은 용량과 인프라다 |
| D12 | 비기각 판정 | **(a) 3단 진리표 유지 + 두 줄 추가** | 아래 표. "E≥79"가 도달 가능해져 반증 경로가 실제로 열렸다(앞선 "최대 52.7" 철회) |
| D13 | U_viol 지위 | **(c) T_first 단독 확증 + ①은 U_viol 방향 일치 요구** | RQ ①은 양쪽을 요구하고 α를 쪼개지 않는다. 방향 일치는 retention으로 쉽게 충족되므로 근거로 과대평가하지 않는다. D038의 "둘 다 1차"를 개정한다 |
| D14 | threshold | **(c) 7, 정보 블록.** 분석기 수정이 안 되면 (b) 7, 총 사건 | 최소 p 산술(2^(1−I))로 7블록 .0156, 6블록 .0313. Holm 첫 단계 .025에서 7이 최소다 |
| D15 | 노출 공개 정정 | **(a) 정정.** `exposure = pre-exposed` + ref, seed 9001을 동결 전 4배치 10런으로(원장 포함). 대칭 검사 추가 | 동결본에 틀린 공개를 남기지 않는다 |
| D16 | main 기록 | **(a) 이 항목으로 함께 기록** | 지웅 결정 5~8과 파일럿 결과, D038 개정을 같은 기록에 둔다 |
| D17 | Rust tar | **(b) 사전 노출로 기록, holdout 제외, 미등록 + probe 공개. 런처 규칙 불변.** `exp3-v1.md:116-119`(#264 초안 기준) 문구를 고친다 | probe가 등록 전에 실행돼 결과(양 버전 C1·C2 0)를 이미 안다. 사건이 없어 H-A holdout으로 쓸 이유도 없다. 원장 rust-tar 행, `rust_tar_fixture_probe.json`(#261) |
| D18 | 이미지 동결 | **(a) 빌드 1회 후 id 고정 + docker save 보관** | digest는 재빌드 불변이 아니다 |
| D19 | A1 라벨 | **(b) 라이브 문서 변경:** "A1 (generic 어휘, effect retention; 이름 철자 불가)". summaries·LOG는 그대로. R "바닥"도 함께 고친다. **범위 제외:** 코드 주석은 EXP-2 holdout 완료 뒤 정리(`engine_sha`가 두 등록 파일에서 같아야 함), `arm_comparison.py:138` 문자열 값 불변, 동결 사전등록 2곳(`exp0-pilot-v2.1.md:214`, `exp0-pilot-v2.md:40`) 불변, 과거 셀 이름 "A1 random floor" 불변 | A1은 무작위가 아니라 effect retention 탐색이고 "floor"의 원인은 어휘다. `research-questions.md`, `paper/sections/05-method.md`를 범위에 더한다. 범위 제외는 "라이브 문서만"의 구체화이고 새 결정이 아니다 |
| D20 | 나머지 문구 | **(a) 일괄 승인 + 추가.** train을 탐색으로 명시, hazard proxy 개정 표기, RQ 예측 대체, invalid·abort 민감도·마감 미완주 규칙, dense 지표 고정(집계 방식 포함), FACT③ 강등, 연장 금지 무조건화. 추가: abort 3분할, 결과 미상 step 병기, 단일 시계 배율 금지, 통계량을 "합동 로그랭크, 블록 내 순열"로 명시, 운영 중단 조건 | 결과 메모 §4·§5 |
| D21 | 재시도·제한 조정 | **(a) 지금은 안 함, 재개 조건 고정** | 첫 실패 경로는 로그 소실로 확인 불가다(결과 메모 §4.5). 아래 재개 조건 |

### 등록 파일 2개의 조건 (D1)

등록의 `seeds`는 파일 전역 값이라(`scripts/run_exp0.py:286`) 한 파일에서 train 20과 holdout 120을 함께 표현할 수 없다.

1. **seed:** 겹치지 않게 나눈다. train `{9006..9025}`, holdout `{9026..9145}`.
2. **공통값:** 두 파일의 `engine_sha`, k, sentinel generator, budget, arm이 같아야 한다. 어긋나면 train이 인프라 게이트 역할을 못 한다.
3. **원장:** `exp2-v1`이 원장 해시를 고정하고 게이트가 실행 때 대조한다(`rds_preregistration.py:606`). 그래서 **11/18~25에는 원장을 고치지 않는다.** train 행은 holdout 완료 뒤 넣고, 그 순서를 `exp2-v1`에 적는다.
4. **GO 적용:** 자동이 아니다. `exp2-v1` 시작 전에 W3가 train 리포트 값으로 D11을 적용해 LOG에 남긴다.
5. **형식:** 두 파일 모두 `targets.<id>.*` 형식으로 쓴다. 단일 키 `image_digest` 형식이면 holdout 게이트와 셀 회전이 적용되지 않고 EXP-0 순서로 돈다. target이 하나여도 `targets.<id>`를 쓴다.
6. **확인:** 파서가 train만 있는 파일과 holdout만 있는 파일을 받는 것은 코드를 읽어 판단했다. 동결 전 W1이 두 파일로 `--dry-run`을 돌려 확인한다.

### D5 조건 4개

게이트는 범주 남용을 막지 못하므로 다음은 기록과 W3 검토로 지킨다. `qualification-only`는 D4처럼 미리 정한 규칙의 상태 확인에만 쓴다.

1. **순서:** D4 규칙을 main에 커밋한 뒤 상태 확인을 실행한다. 커밋 시각이 실행보다 앞서야 한다.
2. **전부 공개:** 후보 5개 전부의 행과 결과를 적는다. 뽑히지 않은 버전도 빼지 않는다.
3. **행 내용:** 규칙 근거 D4, seed 해당 없음, 고정 fixture, 후보당 1회, 증거 경로. ERROR 재실행은 행을 따로 남긴다. 행 추가 PR은 W3가 검증한다.
4. **사전등록 공개 문구:**

> holdout은 미리 고정한 규칙으로, 후보 5개의 고정 fixture 상태 확인 결과를 보고 골랐다. 규칙 입력은 버전 번호와 fixture 결과뿐이고 advisory는 쓰지 않았다. 다만 공개 advisory로 결과를 일부 예측할 수 있으므로 결과에 blind한 선택은 아니다. 후보 버전에서 탐색 실행은 하지 않았다.

### D11 GO 식

**GO = E≥1 ∧ ⌊H_rem·r÷(6000·e)⌋ ≥ 76 ∧ train abort ≤ .45**

- E는 train 첫 C1∨C2 캠페인 수다(3 arm 합산, abort 포함, invalid 제외).
- r은 EXP-3 실경과 실측 처리량이다. e는 train 실측 기록/계획 step 비율이다.
- H_rem은 EXP-3 종료부터 실행 마감(11/25 12:00 KST)까지 남은 호스트 시간이다.

### D12 판정 표

I는 두 arm 관측이 다른 정보 블록 수, E는 대비의 총 사건 수다. "기각, X"는 Holm 기각이고 빠른 arm이 X라는 뜻이다. 두 대비의 I·E가 다르면 작은 쪽을 쓴다.

| S-u vs R | S-u vs D | 규모 | 판정 |
| --- | --- | --- | --- |
| 기각, S-u | 기각, S-u | — | ① 가속 주장 |
| 기각, S-u | 비기각 | — | ② 피드백 일반 효과만 |
| 비기각 | 기각, S-u | — | 예측 불충족, 탐색 보고 |
| 기각, R | 무관 | — | ⑧ 반증 |
| 기각 S-u 또는 비기각 | 기각, D | — | S<D: identity 특정 효과 반대 방향(⑧은 아님) |
| 비기각 | 비기각 | E ≥ 79 | 분리 실패 = HR 2 예측 반증 |
| 비기각 | 비기각 | I ≥ 7, E < 79 | 분리 실패, 반증 아님. 배제 범위 병기: E≥15→HR≥5, E≥20→HR≥4, E≥32→HR≥3 |
| 비기각 | 비기각 | I < 7 | 미검정(기각 불가능 규모) |
| 사건 0 | 사건 0 | 0 | ⑤ 미관찰, 캠페인 단위 상한만 서술 |

E 기준은 Schoenfeld 80%, 양측 α .025 계획값이다(HR 5/4/3/2 = 14.7/19.8/31.5/79.1). 추가 두 줄: 세 abort 정책의 `reject_at_alpha`가 갈리면 "abort 가정에 좌우됨"으로 적는다. 예측은 HR로 평가한다.

### D21 재개 조건

벤치마크 jobs=2에서 a > .30이거나 뒤쪽 절반 비율이 앞쪽의 2배 이상이고, `error_chain`과 broker 기록이 한 경로를 다수로 가리킬 때. 고치면 벤치마크 설계의 재측정 규칙(`concurrency-scaling-v1.md:335`, v2 머지 뒤 갱신 필요)대로 jobs 2·j* 각 1블록을 다시 잰다.

재개 조건 판정은 벤치마크 jobs=2 블록 측정 뒤에만 한다. 파일럿 값은 입력이 아니다. 파일럿의 뒤/앞 비율 2.7배는 사후 관찰이고 첫 오류 기록이 없어 경로 판단을 보류한다.

벤치마크 단계 A는 11/07 승인됐고(D041 참조 예정), 실행은 선행 조건 충족 뒤다.

### 일정과 운영 조건

- **11/18** 두 파일 동결, train 시작. **실행 마감 11/25 12:00 KST**(사전 고정). 분석·보고서 반영 11/25–26, 결과보고서·영상 제출 11/26, 최종발표 11/30.
- **호스트 전용:** 11/18~26 다른 docker·`make check` 금지. 처리량 57캠페인분/호스트-일은 호스트를 비울 때만 성립한다.
- **n=120은 상한이다.** 호스트가 멈춰 마감에 닿으면 완료된 블록으로 분석한다. 시점이 결과와 무관하게 사전 고정이라 선택 편향은 없다. 블록 순서로 실행해 남는 것은 뒤쪽 블록뿐이게 한다(런처 변경 전제).
- **운영 중단 조건(oracle을 보지 않음):** 24시간 창에서 캠페인 abort ≥ .60이면 멈추고 보고한다. 연장 사유는 아니다.

### 지웅 결정 5~8의 기록 (D16)

사전등록 초안에만 있던 결정을 여기 남기고, 위 항목이 개정한 부분을 적는다.

| 결정 | 내용 (2026-11-05) | 위 항목의 개정 |
| --- | --- | --- |
| 5 = B | 7.5.6/7.5.7은 hold-out이 아니라 기노출 수정 검증 쌍이다. H-A 효과 추론에서 제외한다 | D3: 캠페인도 돌리지 않는다 |
| 6 | T_first 1차. seed-block 순열 로그랭크 + Holm(holdout 패밀리 S-u vs R → S-u vs D). 확증은 holdout뿐이다. 양측 p + 방향으로 판정한다 | D1: 등록 파일 분리. D10: 검정 사양. D12: "무기각 → ⑤" 대체. D14: event_threshold 5 대체 |
| 7 = B | 독립 hold-out은 노출 node-tar 집합 {7.5.2, 7.5.3, 7.5.6, 7.5.7, 7.5.8, 7.5.22} 밖, LOG 실행 기록 없는 릴리스에서 실행 전 규칙으로 고른다. 고정 fixture 상태 확인만 허용한다 | D4·D5: 규칙과 기록 방식 확정 |
| 8 = B | Rust `tar` 1개 조건부 추가, 11/18 등록을 지연시키면 A(미추가)로 복귀 | D17: 미등록 + probe 공개. W3 권고: #261 보류(지웅 확인 대기). D039 문구는 별도로 이 항목에 맞춘다 |

### D038 개정 범위

실험 순서(EXP-3 20 seed → 11/20 규칙 적용 → EXP-2)는 D1과 일정으로, "1차 지표 = T_first·U_viol"은 D13으로, R arm은 D6으로, 규모는 D7로 바꾼다. **바뀌지 않는 것:** D038의 안전경계, D005·D006·D007, oracle 정의(C0/C1/C2). train에서 holdout으로의 전이와 k=5 밖의 hazard는 미검증으로 남는다.

## D041 — 동시 실행 벤치마크 단계 A 승인과 파일럿 seed 재사용

**상태:** 적용 (2026-11-07, 지웅 결정, 오케스트레이터 전달)

이 기록은 결정이다. 벤치마크는 아래 선행 조건을 채우기 전에는 실행하지 않는다. 판정은 §6 임계로 하며, 어떤 벤치마크 값도 H-A의 근거나 확증 검정력이 아니다. 실험 구조 결정은 [D040](#d040--exp-3-동결-전-재판정-위험도-파일럿-4040-반영)이다.

**근거.** [벤치마크 설계 v1](../experiments/configs/concurrency-scaling-v1.md) §6, [파일럿 결과 메모](../experiments/summaries/exp3-hazard-pilot-v1-result.md), [파일럿 설계](../experiments/preregistration/exp3-hazard-pilot-v1.md). 설계 v2는 #285(`11dffaa`)로, V9·seed 예외는 #287(`99eadbd`)로 머지됐다.

**승인 대상.** 지웅은 수정된 설계·분석기·런북에 대한 검증이 완료되는 것을 조건으로 승인했다. 특정 sha를 승인한 것이 아니다. 승인서·런북은 A 기준 개정판을 실행 직전 재확인(선행 조건 3)하며 그 sha를 실행 LOG에 기록한다.

### 결정

| 항목 | 결정 | 이유·조건 |
| --- | --- | --- |
| 구조 | **stage.A(2,4,4,2) 승인.** 범위는 smoke와 1단계(jobs 2→4)다 | 동시 측정 비교 가능성, abort 판단 신뢰도, 연구 재현성. 더 높은 수준(stage.B, stage.C)은 별도 승인이다 |
| 대안 | **재사용 대안 B, C, C′ 불채택.** 오케스트레이터 통합 보고(2026-11-07)의 C′ 분류를 C 구조(4→2→4) 변형으로 정정한다 | 비동시 기준은 처리량 변동과 이득을 구분할 수 없고, 합친 기준은 abort 시점 교란을 받는다 |
| 파일럿 | **참고 칸만.** 비합산, 처리량 단순 비교 금지, 판정 입력 아님 | 같은 파일럿 안에서도 12셀 구간 처리량이 최대 16.9% 움직였다 |
| 임계 | **§6 임계 유지** | 파일럿을 본 뒤 임계를 다시 정하지 않는다 |
| V9 | **fail-closed.** 한 블록에서 비교 불가 셀이 2개 이상이면 그 수준의 V9를 위반으로 한다. 1개면 보고한다 | 현재 분석기는 비교 셀이 없으면 V9가 경고 없이 통과한다. 판정을 강화하는 방향의 실행 전 변경이다 |
| H3-unmeasured | **기준 수준에서 위 조건이면 H3를 측정 불가로 보고 선택하지 않는다** | W3 판단: `selected_jobs`, `fallback_jobs` 모두 null이고 EXP-3 처리는 지웅 결정이다 |
| 사전등록 검증자 | **독립 검증자 W2/W1 지정.** W2는 조건·원장·수치·통계 입력, W1은 파서·실행 설정·dry-run·구현 일치 | W3 초안은 다른 레인이 검증한다 |
| 세션 | **중복 W2 세션 정리:** 해당 세션은 지웅이 다른 용도('결과보고서')로 전용했고, 오케스트레이터 관리 대상에서 제외한다(미커밋 산출물·프로세스 없음 보고 확인) | 운영 사항 |

**공통 조건.** seed 재사용, `RESERVED_SEED_RANGES` 예외, 원장 표기, V9, H3-unmeasured는 조건부 승인으로 묶는다. V9 변경은 조건 뒤집기 테스트, 관련 회귀 테스트, W3 방법론 검증을 통과해야 한다.

### 파일럿 seed 재사용 (조건부 승인)

측정 seed는 **8110, 8102, 8103, 8106**이다. 파일럿 abort를 본 뒤, 벤치마크 실행 전에 고정한 규칙으로 골랐다: 파일럿에서 R-restart·D·S-u abort가 많은 seed부터 4개, 동률은 낮은 번호. smoke seed는 6100이다. 조건은 다음과 같다.

1. **예외 명시:** `RESERVED_SEED_RANGES`의 예외는 이 4개뿐이다. 코드와 테스트에 적는다.
2. **원장:** 행은 "파일럿 재실행"으로 적는다. 새 seed가 아니다.
3. **목적:** 시드 재사용은 abort 재현성과 안전성을 확인하는 진단 목적이다. W3: 파일럿 abort 위치를 다시 지나가 입력 종속 여부를 본다. 파일럿 판정은 소급 변경하지 않는다.
4. **공개:** 선택 과정과 한계를 보고에 적는다. seed를 abort 이력으로 골랐다는 점을 포함한다.
5. **추정 금지:** 이번 abort율을 EXP-3 전체 abort율의 추정값으로 사용하지 않는다.

### 실행 선행 조건 6개

지웅 문구 그대로다.

1. v2 설계 PR과 V9·시드 예외 PR의 검증 및 순차 머지
2. D040 결정 기록 #282의 W3·W1 검증과 머지
3. 최종 main의 전체 실행 SHA, 승인서 SHA, 런북 SHA 재확인
4. 엔진 경로 diff, 예상 head, 승인 참조, dry-run 확인
5. 디스크·메모리·부하·컨테이너 상태 등 승인서의 호스트 조건 충족
6. 다른 세션에 호스트 점유와 실험 동결 상태 통지 및 LOG 기록

> 모든 선행 조건을 통과하면 smoke를 실행하고, smoke가 clean일 때에만 1단계 A로 진행한다. H1·H5 또는 기타 중단 조건이 발생하면 승인서대로 중단하고 근거를 보존한다. 임의로 jobs=2를 선택하거나 중단 조건을 완화하지 않는다. 계획된 실행 범위 밖의 재측정·재시작·추가 단계는 별도 승인받는다.

6개 시작 조건을 모두 통과하기 전에는 벤치마크를 실행하지 않는다(지웅 재명시, 2026-11-07).

### 실행 마감과 abort 집계 (지웅 결정, 2026-11-07)

**11/25 12:00 KST 종료 규칙.** 12:00 뒤 새 셀 금지. 실행 중 셀은 강제 종료하지 않고 끝까지 돌려 기록을 보존한다. 12:00까지 끝나지 않은 셀이 있는 seed는 미완주로 제외한다. 판정 예상 약 15:00(추정).

**abort 집계.** D040-D11의 GO와 운영 중단 abort 집계에 "abort + 기록 어긋남(record-inconsistent)"을 합산한다. D040-D11 식 자체는 그대로이고 입력 정의만 구체화한다.

W3 판단: `record-inconsistent` 셀은 재시도하지 않고 그 arm이 든 대비에서 블록을 뺀다. abort 표에는 넣지 않고 수를 따로 내며 1건부터 보고한다. 결과 가림 사유가 아니다. 어긋남 민감도(첫 어긋남 앞 prefix 사용)와 판정이 갈리면 "기록 손상 가정에 좌우됨"으로 적는다. watchdog 셀은 abort로 분류한다(런처 기록(`cell-results.jsonl`)의 watchdog 여부 + step index 연속; step 기록 0이면 재시도 규칙; 사유 watchdog 별도 표, 우측절단, 재시도 없음). *(2026-11-07 정정: 구 문구 '종료 코드 watchdog + step index 연속'은 W3 오류다. 코드값 -15는 외부 SIGTERM과 구별되지 않는다. 이 문장을 쓴 실행은 없다.)* 판정표 입력을 구체화한 것이다. 용어: 인프라 실패 비율 = (abort + record-inconsistent)/전체 셀.

### 정지 컨테이너 격리 (지웅 승인 A안, 2026-11-07)

10/14 정지 컨테이너 4개를 `archive-20261014-*`로 이름 변경했다(id `a1e2ba9d6481`, `6c853b5abed2`, `93432fe314e3`, `1fef558df758`). 볼륨·증거는 보존했고 삭제·열람은 없다. 격리 뒤 드라이버 필터(컨테이너 `inodefence-`, 볼륨 `inodefence-local-`) 잔여는 0건이다. 임의 이름의 정지 컨테이너 3개는 건드리지 않았다. **`docker system/container/volume prune`은 금지한다.** 이 자원이 유일한 증거 사본일 수 있다.

대응표: `~/inodefence-evidence/prereg-verification/stale-docker-resources.md`(sha256 `e98d5100…`). 전후 기록: `~/inodefence-evidence/prereg-verification/container-isolation-20261107/`(`SHA256SUMS` sha256 `8404d220…`).

### 운영 중단 규칙 구체화 (W3 권고 수용)

[D040](#d040--exp-3-동결-전-재판정-위험도-파일럿-4040-반영)의 운영 중단 조건을 다음처럼 구체화한다. 최근 24시간에 종료한 셀이 20개 이상일 때 인프라 실패 비율 ≥ .60이면 멈춘다. W2가 6시간마다 확인해 LOG에 남긴다. 재개는 지웅 결정으로, 같은 설정 또는 jobs=2로만 한다(`concurrency-scaling-v1.md:343,348`). `run_exp0`에 자동 정지는 없다.

W3 판단: `concurrency-scaling-v1.md:348`의 "15캠페인 8건"은 D040으로 대체됐다.

### 분석 코드 수정 6건 (지웅 승인)

11/18 사전등록 전 필수다. 11/11~14 구현·검증, 11/15~17 일치 검증·dry-run·SHA 준비, 11/18 확정. 머지는 벤치마크 뒤, `engine_sha` 고정 전이다. 셀 경로가 아니라 재측정이 필요 없다고 W3가 분류했고(3번은 아래 조건대로 따로 판정), 파일 목록을 등록 문서에 적는다.

1. 타깃 1개일 때 확증 절이 호출되지 않는 문제. EXP-0 출력은 바이트 불변이어야 한다.
2. 마감 시 결과 가림: 등록 키로 마감을 고정하고, 미완주 seed는 전체를 제외한다. 봉인 해제는 마감 시각 뒤에만 한다.
3. abort-pending 재실행: 레코드가 있으면 최종, 없으면 1회 재시도. 재시작 시 셀을 교체하지 않는다.
4. D040-D10 3건.
5. D040-D14의 I 구현. 총 사건으로 대체하지 않는다.
6. D040-D12·D13의 I, 세 정책, U_viol 방향. 값만 내고 판정표를 자동화하지 않는다. `direction_note`의 ①·⑧ 문구를 수정한다.

함께: invalid는 대비별로 제외하고, 합성 index 경로 시험을 1회 한다. 재검증 등급은 테스트, 조건 뒤집기, W3 delta다. 일정에 못 미칠 때 축소할 수 있는 항목은 D040-D10의 "≤16 exact" 분기뿐이고, 축소도 지웅 결정이다.

**지웅 조건 (원문).**

- 진행 중인 벤치마크를 변경하거나 방해하지 않는다.
- 벤치마크 완료 후 해당 수정들을 통합한다.
- 3번은 실행 제어 동작 변경이므로 다른 항목과 구분하여 검증한다. 기존 벤치마크와의 실행 조건 차이 및 재측정 필요 여부를 명시적으로 판정한다.
- abort 레코드의 존재만으로 정상 종료를 가정하지 말고, 상태와 기록의 완전성을 검증한다.
- 4번의 p=0 처리 등 통계 계산은 W3가 승인한 정의와 일치시킨다.
- 2번은 미완주 seed의 제외 기준을 사전에 고정하고, 제외 수와 원인을 보고서에 남긴다.
- 합성 데이터로 입력→분석→통계 판정→보고서 생성까지 전체 경로를 테스트한다.
- 변경 파일, SHA, 테스트 결과, 이전 코드와의 차이를 증거로 남긴다.
- W1 구현 → W3 연구 검증 → W1 코드·사전등록 일치 재확인 순으로 진행한다.
- 두 검증이 PASS이고 CI가 통과한 PR만 내게 머지를 요청한다.

> 일정이 밀리면 임의로 검증을 생략하거나 분석 정의를 변경하지 말고, 차단 항목과 영향 범위를 보고하라.

### abort율 a 정의 (지웅 수용)

"각 수치의 사용 목적과 집계 대상은 명확히 분리한다." D040 안의 해석이다.

- **계획 a:** 파일럿 .275, 상한 .43. 벤치마크 a는 계획에 넣지 않는다. seed를 abort 이력으로 골랐기 때문이며, `concurrency-scaling-v1.md` §9의 max(파일럿 a, 벤치마크 a)를 대체한다. 용량 판단은 train 실측 e와 abort(GO)로 한다.
- **§6 H1·V3:** 벤치마크 a를 그대로 쓴다.
- **D040-D21 재개 조건의 a:** jobs=2 24셀 전체 값에, 파일럿에서 abort한 6개 조합(2블록 12셀)을 뺀 12셀 값을 병기한다. 전체 > .30인데 제외값 ≤ .30이면 입력 쪽을 먼저 본다.
- D040-D21의 재측정 규칙 참조는 `concurrency-scaling-v2.md` §9(규칙 줄 `:349`)로 읽는다.

### 머지 순서와 PR 처리

- **머지 순서:** 설계 v2(#285) → V9·seed(#287) → D040(#282). 순서대로 머지됐다.
- **#263 (지웅 문구):** "#280이 병합됐다는 이유만으로 #263을 즉시 닫지는 않는다. #263의 고유 내용과 새 v2 설계·#280을 대조하여 각 항목이 수용·대체·폐기되었는지 표로 확인한다. 그 결과 누락된 유효 내용이 없으면 superseded 근거와 대체 PR을 명시하고 종료하도록 다시 요청하라. #263 자체는 머지하지 않는다."
- **#261 (지웅 문구):** "#261은 현재 보류한다. Rust tar 타깃 구현과 실험 범위를 이번 벤치마크 승인에 포함하지 않는다. 다만 rust_tar_fixture_probe.json이 결정 문서의 근거로 필요하다면, 출처·해시·재현 조건을 검증한 뒤 증거 JSON만 별도 소형 PR로 제안하는 것을 허용한다. 해당 PR은 타깃 구현이나 실행 엔진을 변경해서는 안 되며, 별도의 머지 승인을 요청한다."

**바뀌지 않는 것:** D038의 안전경계, D005·D006·D007, oracle 정의(C0/C1/C2), 파일럿 판정. 봉인: 벤치마크 raw의 oracle 값은 EXP-3 동결 전까지 어떤 세션도 읽지 않는다(§6.6).

## D042 — 인프라 정지 규칙: 연속 3셀 기록 없음

**상태:** 초안 (2026-11-07 지웅 결정, 오케스트레이터 전달). W3 대조: 동작 일치, ISSUE 3건 수정 대기. 아래 값의 출처는 PR-B #297 `be9720a`와 W3 등록 템플릿 `exp2-v1` §8이다.

이 기록은 결정이다. 벤치마크 실행 호스트와 진행 중인 벤치마크는 바꾸지 않는다. D041의 "abort-pending 재실행"(분석 코드 3번)에 EXP-3 등록 규칙 하나를 더한다.

### 결정

PR-B(#297)의 "연속 3셀 기록 없음이면 신규 셀 시작 정지"를 승인한다. oracle을 보지 않는 인프라 안전장치이고, 11/18 동결 전에 등록 문서에 반영한다.

### 고정 항목

| # | 항목 | 값 |
| --- | --- | --- |
| 1 | 레코드 없는 셀의 재시도 | 그 자리에서 즉시 1회. 셀당 최대 2회이고 `start`만 남은 시도도 1회로 센다. 앞 시도 파일은 `attempts/`에 보존한다 |
| 2 | 동시 실행에서 "연속 3셀"의 판정 순서와 카운터 초기화 조건 | 시도가 아니라 셀 단위다. 순서는 셀이 끝나는 순서이고 런처 잠금 안에서 확정한다. 레코드 있는 셀(`complete`, `abort-final`, `record-inconsistent`)이 끝나면 0으로 돌아간다. 호출마다 0에서 시작한다 |
| 3 | 정지 시 처리 | 그 호출이 끝날 때까지 유지한다. 새 셀과 새 재시도를 시작하지 않는다. 실행 중 시도는 완주한다. 시작하지 않은 셀은 시도를 쓰지 않는다. 첫 시도만 끝난 셀은 남은 1회를 유지한다. 런처는 기록과 `attempts/`를 지우거나 덮어쓰지 않고 남은 자원을 정리하지 않는다(실행 중 셀 스크립트의 자기 정리는 평소와 같다). 사유와 시각을 index에 남긴다 |
| 4 | 정지 후 원인 확인과 재개 승인 절차 | W2가 원인을 LOG에 적는다(oracle 값 없이). 오케스트레이터가 중계하고 **지웅이 별도로 승인한다(확정).** 자동 승인은 없고 smoke에도 같다. `--resume-after-stop <승인 참조>`가 필수이고 플래그가 없으면 아무것도 시작하지 않는다. 같은 출력 폴더, `engine_sha`, 이미지를 쓰고 같은 설정 또는 jobs=2로 재개한다. 이 조건은 절차와 기록으로 지키고 코드로 강제하지 않으며, `start` 줄에 jobs를 기록한다. 이미지가 없거나 id가 다르면 재개하지 않는다. `no-record`로 확정된 셀은 다시 돌리지 않는다. 마감은 바뀌지 않는다 |

### 조건

- **순서:** W1 수정(W3 ISSUE 3건) → W3 동작과 등록 문서 일치 재검증.
- **PR-B 머지 가능 상태:** W1 수정판 CI, W3 재검증, 실제 런처 smoke, 원자료 회귀 검증이 모두 끝나야 한다.
- **재측정:** 벤치마크 설계 §9 전체 재측정은 필요 없다(W3 판단). 재시도와 정지 경로는 아래 smoke로 따로 잰다.

### 정지·재개 실측 smoke (조건부 승인)

- **범위:** R/D/S-u × seed 6101~6104, budget 20, jobs 2, 전용 출력 경로.
- **시점과 실행:** 벤치마크 종료와 동결 해제 뒤 W2가 실행한다.
- **사전 확인(W1):** context가 셀 실행 단계에 전달되고, 프로세스에 한정되며, 전역 context가 바뀌지 않는다.
- **검증:** 재개 뒤 멱등 검증까지 한다. W3가 사전 고정 판정 기준(설계 문서 기준, 21개; `experiments/configs/stop-path-smoke-v1.md`, sha `[동결 시 기입]`)과 원자료를 검토한다.
- **기준 정정(지웅 승인):** 앞선 승인 문구의 "15개"는 집계 오류이고 현재 기준은 21개다. 결과를 보지 않았고 판정의 의미·임계값·합격 조건을 사후 변경하지 않았다. 단 문구 수정 이력은 사실대로 적는다: "15"는 오기이고 그 시점 실제 수는 16이다. A4의 "정확히 4"를 "3 또는 4"로 고친 것은 실행 전 정정이다.
- **21개 번호(원본은 설계 §5 표, 다르면 표가 맞다):** A1 정지 기록과 스스로 종료 / A2 no-record 3 또는 4 / A3 각 2시도·즉시 재시도·파일 보존 / A4 시작 셀 3 또는 4, 나머지 시작 줄 없음 / A5 첫 시도만 끝난 셀 0 또는 1 / A6 컨테이너·볼륨 생성 0, context 불변 / A7 결과 가림과 manifest / A8 로그 `FAILED at step: prepare controller`, `engine=` 빈 값 / N1 플래그 없는 호출은 시작 없음 / P1 재개 전 W2 원인 LOG와 지웅 승인 / B1 승인 참조 기록 / B2 재개 뒤 정지 해제·정지 기록 유지 / B3 no-record 셀 재실행 없음 / B4 남은 시도 유지 / B5 나머지 셀 complete 또는 abort-final / B6 `.calls.jsonl`과 시계 / B7 append-only / B8 `cell_completeness` 집계 / B9 invalid 경로와 분석기 정상 종료 / C1 멱등 / F1 PR-D 요약 필드(1차 해당 없음, 2차에 없으면 FAIL).
- **실행 횟수(지웅 승인): 2회.**
  - 1차: 벤치마크 종료와 해제 뒤, PR-B 수정 3건과 W3 재확인을 거친 HEAD에서. PR-B 머지 승인을 위한 장애 복구 검증이다.
  - 2차: 최종 `engine_sha` 후보에서 같은 기본 설계로. PR-D 통합 뒤 회귀 확인이고 최종 SHA 동결 전이다.
  - 증거 경로, 실행 SHA, 판정 결과를 회차별로 나누어 보존한다. 출력 폴더는 `stop-path-smoke-1-<날짜>`, `stop-path-smoke-2-<날짜>`이고, 등록 파일과 판정표도 차수별이다. seed는 양차 모두 6101~6104다. 원장은 차수별로 기록하고 `exposure_ledger_sha256`은 2차 뒤 고정한다.
- **재개:** 매 실행의 재개마다 W2 원인 확인과 지웅 별도 승인을 거친다.
- **제한:** 벤치마크 중에는 실행하지 않는다. 결과는 봉인하고 합산하지 않는다. 첫 실측에서 결함이 나오면 원인과 수정 범위를 기록한 뒤 재검증한다.
- **범위:** 이 결정에 따른 추가 실험 범위 확대는 허용하지 않는다. 본실험 일정과 동결 기준이 우선한다.
- **집계:** 결과를 EXP-3, EXP-2, 파일럿 통계에 합치지 않는다.

## D043 — GO 입력 r에서 등록된 인프라 정지 공백을 뺀다

**상태:** 초안 (2026-11-07 지웅 승인, 오케스트레이터 전달). D040-D11의 r 정의와 H_rem 기준을 고치고 e의 범위를 정한다. GO 식 ⌊H_rem·r÷(6000·e)⌋ ≥ 76과 다른 입력의 임계는 그대로다.

**결과 전 확정.** 이 변경은 EXP-3, EXP-2 실행 전에 확정한 산식 변경이다. 벤치마크 결과와 oracle 값을 보고 정하지 않았고, 그 값에 따라 다시 조정하지 않는다. 계기는 #298 코드 읽기와 계획 입력(r 4750·4295, e .9)의 손 계산이다. 벤치마크와 진행 중인 실험의 조건은 바뀌지 않는다.

### 왜

D040-D11의 r은 "실경과 실측 처리량"이라 정지 뒤 승인 대기 시간이 r을 낮추고 H_rem도 줄인다. 계획 입력 r 4750, e .9, train 20블록, 시작 11/18 12:00, 판정 지연 0 가정에서 공백 16 h이면 옛 정의 용량은 66(NO-GO)이고 이 정의로는 113이다. 공백이 없으면 127이다(손 계산, 계획값, 결과 아님). NO-GO는 되돌리지 않으므로, 한 번의 승인 대기가 처리 능력과 무관하게 확증 실험을 없앨 수 있다. r은 정상 가동 중의 처리 능력 추정치다.

### 산식

시계는 실시간이다. GO 판정 시각을 뺀 값은 `cell-results.jsonl`의 `realtime`이고, 줄은 완전한 줄만 쓴다.

- **T_wall** = 마지막 `end` − 첫 `start`
- **공백 g_i** = `infrastructure-resume`_i − max(`infrastructure-stop`_i, 그 재개 줄 앞의 마지막 `end`). 음수면 0이다.
- **T_up** = T_wall − Σ(g_i 가운데 첫 `start`~마지막 `end` 구간과 겹치는 부분)
- **r** = 시도한 모든 셀의 기록 step ÷ T_up. **r_wall** = 같은 step ÷ T_wall.
- **H_rem** = 실행 마감 − max(마지막 `end`, 마지막 `infrastructure-resume`, GO 판정 시각). 실제 벽시계이고 공백과 판정 지연만큼 줄어든 값 그대로다. GO 판정 시각은 W3가 GO 입력 값을 보기 전에 적는 실제 시각이고, `experiments/summaries/exp3-train-go-decision.json`과 LOG에 남기며 적은 뒤에는 고치지 않는다.
- **e**는 시도한 모든 셀의 기록 step ÷ (시도한 셀 수 × budget)이다.

### 조건 (지웅 승인 7개)

1. r은 정상 가동 중 실행 처리 능력의 추정치다.
2. 사람 승인 대기 같은 일회성 공백이 반복 반영되어 되돌릴 수 없는 NO-GO를 만드는 것을 막는다.
3. H_rem은 실제 벽시계를 유지하고 정지 공백만큼 줄어든다.
4. 공백을 포함한 r_wall을 참고 지표로 병기한다. GO/NO-GO를 뒤집는 데 쓰지 않는다.
5. 뺄 수 있는 공백은 사전 정의된 `infrastructure-stop`, `infrastructure-resume` 기록으로 확인되는 구간뿐이다. 일반 지연, 시간 초과, 비정상 종료, 런처 재시작 공백은 빼지 않는다.
6. 재개되지 않은 상태에서는 정상 재개를 가정해 GO를 산출하지 않는다.
7. 정지 횟수, 누적 시간, 원인, 기존 인프라 실패 기준(D041)은 별도로 유지한다.

### 산식 확정 (지웅 확인, 2026-11-07)

- **공백의 시작:** max(정지 기록 시각, 재개 전 마지막 실행 중 셀 종료 시각)이다. 정지 뒤 실행 중 셀의 step을 분자에 넣으므로 그 시간을 분모에서 빼지 않는다.
- **H_rem의 기준:** max(마지막 셀 종료, 마지막 정상 재개, 실제 GO 판정 시각)이다. 판정이 늦어 이미 지난 시간을 H_rem에 넣지 않는다. 판정 시각을 넣는 것은 중복 반영이 아니다. D040-D11(`docs/DECISIONS.md:731`)과 `exp3-v1` §5의 H_rem은 "EXP-3 종료부터"이고 D040의 GO 적용 항목(`docs/DECISIONS.md:710`)에도 판정 시각이 없다. #298 `T-EXP3-2`도 마지막 `end`부터 계산했다. 판정 시각을 값을 보기 전에 적고 고치지 않는 규칙은 W3가 정한 부분이다.
- **재개:** `--skip-build`와 W2 읽기 검증(Docker 응답, 세 이미지 id 일치)으로 한다. 이미지가 없거나 id가 다르면 재개하지 않고 보고한다. 재개 때 이미지를 다시 빌드하지 않는다.

### 미재개 (조건 6, 지웅 확정)

마지막 인프라 줄이 `infrastructure-stop`이면 GO 칸은 "미산출"이다. W3는 GO를 적용하지 않고 EXP-2를 시작하지 않는다. 지웅이 재개를 승인하지 않아 그대로 끝나면 EXP-3 미완이고, 세 판 문서의 판 다다.

### 표 7-B2

r(GO 입력), r_wall(참고, GO 입력 아님), 정지 횟수, 누적 공백 시간을 낸다. 원인은 `docs/LOG.md`의 W2 기록을 가리킨다.

### 바뀌지 않는 것

GO 식, 76, E ≥ 1, train abort ≤ .45와 그 분모(D041), 운영 중단 규칙, 재개 승인 절차(D042), oracle 정의. NO-GO면 규칙을 바꿔 다시 적용하지 않는다. D040 본문은 고치지 않고 이 기록이 대체한다.

### 등록 반영

`experiments/preregistration/exp3-v1.md` §5, 11/18 동결 전. 코드는 #298 `T-EXP3-2`.

## D044 — 2호스트 동시 실행 벤치마크 설계 v3

**상태:** 적용 (2026-11-11, ORCH 결정, 지웅 승인 = #331 squash `dfccedc`). 측정 전 기록이다.

**근거.** [설계 v3](../experiments/configs/concurrency-scaling-v3.md), [설계 v2](../experiments/configs/concurrency-scaling-v2.md) §6, [D041](#d041--동시-실행-벤치마크-단계-a-승인과-파일럿-seed-재사용). 지웅 운영 목표(2026-11-11): H1 수정, 병렬 실행, EXP-3 실행 제어를 하나의 본실험 후보로 통합 → 안전성 게이트 → 2호스트 분산 벤치마크 → jobs 선정·동결 → 본실험.

### 결정

| 항목 | 결정 | 이유·조건 |
| --- | --- | --- |
| 배분 | **호스트별 완전 ABBA(2,4,4,2), 호스트당 48캠페인, 총 96.** 한 집합을 나눠 돌리는 안(24+24)과 블록 6셀 안은 불채택 | 나눠 돌리면 호스트마다 수준별 블록이 1개라 ρ1·ρ2·d·F(v2 §6.1·§6.4)가 정의되지 않는다. 6셀 블록은 v2 §5·§6 임계를 사실상 완화한다 |
| 판정 | v2 §6과 D041을 호스트마다 그대로 적용한다. `selected_jobs`는 호스트별이고, 합산 통계로 선정하지 않는다. 공통 jobs가 필요하면 작은 값을 쓴다 | 호스트 효과를 jobs 효과로 오인하지 않는다 |
| 추가 규칙 | V10′(monotonic·실시간 중 엄한 쪽), X1(교차 호스트 경로 일치), H2′(입력 종속은 두 호스트 합동 정지) | 모두 강화 방향. X1 오탐은 실행당 이탈 r=.05에서 .004, r=.10에서 .017(모형 정확 계산, v3 §6.3) |
| X1의 귀결 | jobs 배제가 아니다. 발동 시 본실험 확증 분석의 구조(seed 블록)는 유지하고 호스트별 민감도 표를 추가 보고한다. 호스트 제외·단일 호스트 전환은 지웅 결정이다. 미발동이어도 호스트는 기록 요인이다 | EXP-3 사전등록 문장 초안은 v3 §10 |
| 안전 중단 | v2 §5를 호스트별로 독립 적용한다. H1·H5는 그 호스트만 halted이고 다른 호스트의 선정은 유효하다 | |
| 실행기 | 벤치마크는 본실험과 같은 StartGate·공유 함수로만 셀을 시작한다. 재시도 주입값은 0이다(v2 §4 유지). 정지 정책·디스크·원장 형식은 정책 차이로 문서화한다(v3 §4.2) | 실행 경로 동일성(지웅 요구). 런처 재시도 경로는 테스트와 run_exp0 엔지니어링 smoke에서 확인한다(실 docker 재시도는 결함 주입 없이는 미검증). #335 case 단위 인프라 재실행(D046)은 셀 내부에 항상 켜져 있고 이 설정과 무관하다(2026-11-11 정정) |
| probe | 측정 전에 비등록 엔지니어링 probe를 호스트별로 둔다. seed 6200–6207, budget 1000, jobs 4, 8셀, 통과 조건 4개(cleanup UNKNOWN·잔존 리소스·러너 실패·시작 실패 0). 판정 입력이 아니다. 실행기는 벤치마크 드라이버(공유 실행 계층), 런처 셀 재시도 없음(`probe_retry_max_attempts = 1`, 2026-11-11 정정). 그 뒤 run_exp0 엔지니어링 smoke(seed 6300–6303, v3 §5.1)를 둔다 | 근본 원인 수정 효과와 부작용을 측정 전에 확인한다. 본실험 런처 경로는 별도 smoke로 확인한다 |
| 순서 | 근본 원인 수정 → 통합 head 독립 검증 → 호스트별 probe → smoke → 단계 A | 경로가 바뀌면 v3 §4.4대로 다시 한다 |
| 엔진 | `host.<id>.docker_engine`은 smoke 전 preflight에서 고정한다. 일치시킬지 기록만 할지는 **미정**이다(HOST2 재측정과 HOST1 daemon 조사 뒤 오케스트레이터가 정함). 벤치마크 시작부터 본실험 끝까지 엔진·Desktop·WSL 버전 변경을 금지한다 | 선정된 jobs는 그 호스트·그 엔진에서만 유효하다 |
| seed | 측정 seed는 D041의 4개를 두 호스트에서 재사용한다(새 노출 아님). 원장은 호스트별 행을 쓰고, 봉인은 두 호스트 raw 모두에 적용한다 | |

**바뀌지 않는 것:** v2 §6의 모든 임계값, D041의 V9 fail-closed와 H3-unmeasured, 봉인(§6.6), 벤치마크 a를 EXP-3 추정에 쓰지 않는다는 규칙, D038 안전경계, oracle 정의.

## D045 — holdout 상태 확인의 "위반"·"어댑터 호환" 정의와 train abort 분모

**상태:** 적용 (2026-11-11, ORCH 결정, 지웅 승인 = #331 squash `dfccedc`). 데이터 이전 결정이다. holdout 후보의 상태 확인은 실행하지 않았고, 7.5.2 기준 실행도 하지 않았다. D040-D4의 규칙("위반 ∧ 어댑터 호환 중 최고 버전")을 바꾸지 않고, 원문에 정의가 없던 두 낱말과 실행 순서를 정한다. **D040-D5 조건 1에 따라 이 기록이 main에 머지된 뒤에만 상태 확인을 실행한다.**

### 결정

| 항목 | 결정 | 이유·근거 |
| --- | --- | --- |
| fixture 집합 | `make regression TAR_VERSION=<v>`(`Makefile:95-102` → `scripts/regression_check.py`)의 고정 fixture 5개다. 손 하드링크 2개(`toplevel_hardlink`, `nested_hardlink`)와 symlink-write 3개(`toplevel_symlink_write`, `nested_symlink_write`, `dir_symlink_write`). 퍼징은 하지 않는다 | 기존 유지보수자 회귀 명령이다(#218). fixture 판정은 C1(외부 reference inode 공유)과 C2(reference의 ino·nlink·size·type 변화)다 |
| 어댑터 호환 | 5개 fixture가 **모두 ERROR 없이** PASS 또는 FAIL 판정을 낸다. ERROR면 1회 재실행하고 별도 원장 행으로 남긴다(D5 조건 3). 재실행도 ERROR면 부적격이다. **후보 버전에서 탐색(퍼징) 실행은 하지 않는다** | 탐색 실행은 D5-4 공개 문구("후보 버전에서 탐색 실행은 하지 않았다")를 거짓으로 만든다 |
| 위반 | **(ii) 같은 위반 계열.** 후보에서 FAIL(C1∨C2)인 fixture 중 하나 이상이 기준 집합 F_train에 속하면 위반이다. F_train은 train 타깃 7.5.2에서 FAIL인 fixture 집합이다. (i) "5개 중 1개 이상 FAIL"은 채택하지 않는다 | D040-D7의 검정력(.76~.79)은 holdout hazard가 train의 절반 이상(s ≥ .5)이라는 가정 위에 있다. train에서 hazard가 측정되지 않은 계열(예: symlink-write만 깨지는 후보)을 고르면 "I < 7 미검정"으로 끝날 위험이 크다. 변이 정책(`…-escape-hardlink-…`)도 hardlink 계열을 겨냥한다. 규칙 입력은 여전히 버전 번호와 fixture 결과뿐이라 D5-4 공개 문구가 유지된다 |
| 기준 집합 F_train | 후보보다 **먼저** 같은 명령으로 7.5.2를 1회 실행해 정한다. 그 결과의 손 하드링크 2개가 M2 기록(`experiments/repro/evidence/summary.json`, `per_release_shared["7.5.2"]` = true, toplevel·nested)과 다르면 하네스 불일치로 보고 중단한다. **F_train이 비어 있으면**(7.5.2에서 FAIL 0개) 역시 하네스 불일치로 중단·보고하고 후보를 실행하지 않는다. 7.5.2 실행은 원장에 행을 추가한다(train 타깃이라 자격에 영향 없음) | 저장소에는 7.5.2의 symlink-write 3개 결과 기록이 없다(#218 LOG: docker 미실행, `breached_fixtures` 기록 없음, 2026-11-11 확인). 고정 fixture 결과라 봉인 대상이 아니다 |
| 선정 | 위반 ∧ 호환인 후보 중 **최고 버전**. 전부 부적격이면 **D1(D)로 자동 전환**한다(holdout 포기, 탐색 등록만, exp2-v1 미실행) | D040-D4 원문 그대로 |
| 대가 공개 | (ii)는 후보를 좁히므로 D1(D) 자동 전환 확률이 (i)보다 높다. 이 점을 exp2-v1 §3에 공개한다 | 결과 전 선택의 비용을 숨기지 않는다 |
| 후보 | {7.0.1, 7.1.0, 7.2.0, 7.3.0, 7.4.4}(D040-D4), **버전 오름차순 고정, 후보당 1회** | 순서를 결과와 무관하게 고정한다 |
| allowlist | holdout 버전 허용은 D040-D2 "(a) 불변 표 1줄"로 이미 사람 승인됐다. FROZEN과 분리된 상수 1줄과 lock 해시 대조로 구현한다 | D040-D2 |
| lock·이미지 | lock 파일은 기존 7.5.x lock과 같은 절차로 생성하고, 절차와 해시는 원장 행 PR의 증거로 남긴다. **lock 생성은 선정 규칙의 입력이 아니다.** 이미지는 빌드 1회 뒤 id를 고정하고 docker save로 보관한다(D18). 운영 절차는 런북에 둔다 | D5 조건 1이 요구하는 것은 선정 규칙(위반·호환·선정·순서)이 main에 먼저 커밋되는 것이다 |
| 실행 순서 | ① D045 main 머지 → ② lock·이미지 준비 → ③ 7.5.2 기준 실행 → ④ 후보 5개(오름차순, 후보당 1회) → ⑤ 원장 행 PR(후보 5개 전부와 7.5.2, ERROR 재실행 행 포함; `exposure_kind = qualification-only`는 후보 행만) | D5 조건 1~3 |
| 역할 | 실행 W3, 실행 승인 오케스트레이터, 원장 행 PR 검증 W4 | |
| train abort 분모 | **분모 = 시도한 셀**(`start` 줄이 있는 run id). **분자 = 그중 abort + record-inconsistent + no-record.** 미시작 셀은 분모·분자 모두에서 빼고 수를 병기한다. 등록 전체 셀 기준 값도 참고 줄로 함께 내며 GO 입력은 아니다 | D040-D11·D041·D043(#303) 어디에도 분모가 없었다. 미시작 셀을 분모에 넣으면 비율이 낮아져 GO가 쉬워지므로 엄격한 쪽을 택했다. exp3-v1 §5가 이 정의를 쓰고, 구현(`cell_completeness.py:298-314` @`bce75a2`, 현재 등록 전체 셀 분모)은 W3가 맞춘다 |

**바뀌지 않는 것:** D040-D4의 후보 집합과 선정 규칙, D5 조건 4개와 공개 문구, D1(D) 자동 전환, GO 식과 .45 임계, oracle 정의(C0/C1/C2).

## D046 — 인프라 정지 대응(case 단위 재실행)과 D040-D21 재개 판정 (초안)

**상태:** 초안 (측정 전, ORCH 결정 2026-11-11, 지웅 승인 = PR 머지). 구현은 #335(`claude/p0-335-infra-stall-case-reexecution`)다. 검증 head `49891af`는 FAIL이었다(②). 수정 head의 delta 재검증이 PASS일 때까지 통합은 HOLD다.

### 배경 사실 (HOST1 Stage A 48셀 인프라 필드 조사, 2026-11-11, 오케스트레이터 보고)

- 모든 호출이 Docker Desktop 경로다. 비정상 호출 41건 중 40건이 정확히 10초 timeout이다.
- Class S 9건: 한 컨테이너의 start가 created 상태에서 29.5~142.8초 정지했다. Class G 8건(3회): die 직후 전 캠페인이 24~57초 동시에 정지했다.
- 타깃이 0.107초에 끝났는데 attach가 반환되지 않아 10초 timeout이 난 사례가 1건 있다.
- start timeout과 created가 겹치면, 타깃이 한 번도 돌지 않았는데 TIMED_OUT으로 기록되는 경로가 있다(`container.py:424-435` → `node_tar_effect.py:243`).
- 정지가 어느 층에서 생기는지는 UNKNOWN이다.

### D040-D21 재개 판정

D21 재개 조건: "벤치마크 jobs=2에서 a > .30이거나 뒤쪽 절반 비율이 앞쪽의 2배 이상이고, `error_chain`과 broker 기록이 한 경로를 다수로 가리킬 때".

- **입력:** `~/inodefence-benchmarks/concurrency-scaling-v2/A/`의 블록별 `block.json`(일정·반환 코드)과 셀 보고서의 `aborted` 객체(`step_index`, `reason`, `error_chain`)만 읽었다. oracle 필드, steps 파일, 다른 보고서 키는 읽지 않았다. 스크립트는 W4 scratchpad의 `d21_infra.py`(2026-11-11)다.
- **a(D041 정의):**
  - jobs=2 24셀에서 8/24 = **.333**(block-1 3/12, block-4 5/12).
  - 파일럿 abort 6조합(8110의 세 arm, S-u 8102, R-restart 8103, D 8106)을 뺀 12셀에서 6/12 = **.500**.
  - 둘 다 .30을 넘는다. D041의 "전체 > .30인데 제외값 ≤ .30이면 입력 쪽을 먼저 본다"에는 해당하지 않는다.
- **뒤/앞:** 원문에 정의가 없어 두 기준을 모두 적는다.
  - abort step 위치: 앞 절반(< 1000) 4건, 뒤 절반 4건(1.0배).
  - 블록 순서: block-4/block-1 = 5/3(1.67배).
  - 둘 다 2배 미만이다. 조건은 "a > .30이거나"이므로 **a 조건으로 충족된다.**
- **한 경로 다수:** 첫 오류(`error_chain`의 가장 안쪽, 즉 마지막 원소)를 셌다.
  - 전 블록 17건: runtime inspect 14, cleanup inspect 2, 제거 확인 1.
  - jobs=2 8건: 5 / 2 / 1.
  - runtime inspect timeout이 다수다.
- **판정: D21 재개 조건 충족.** 재시도·제한 조정(#335)을 허용한다.
- **재측정:** D21의 "jobs 2·j* 각 1블록 재측정"은 v3 전체 재측정(D044, v3 §4.4: 측정 블록 뒤에 경로가 바뀌면 단계 A를 처음부터)으로 대체한다. 이쪽이 더 엄격하다.

### 규칙 (#335)

| # | 규칙 | 상태 |
| --- | --- | --- |
| ① | 첫 비정상 Docker 호출이 timeout인 시도는 폐기한다. 데몬이 180초 안에 양성 응답("No such")으로 그 시도 컨테이너의 부재를 확인한 뒤에만, 새 컨테이너·새 run root로 같은 case를 재실행한다. 예산·RNG·step은 소비하지 않는다. 확인하지 못하면 원래 예외로 abort한다 | 검증 PASS(부재 확인, fail-closed). 다만 첫 이상의 범위를 "이번 시도에서 복구되지 않은 timeout"으로 좁혀야 하고, 확인 중 BackendError가 아닌 예외가 나도 원래 예외와 기록을 보존해야 한다(검증 Medium 2건) |
| ② | **timed_out 재분류는 정지의 양성 증거가 있을 때만 하고, 그 밖은 전부 base 동작(TIMED_OUT) 그대로 둔다.** target start가 timeout된 뒤 그 컨테이너의 첫 inspect를 기준으로 판정한다. ⓐ Running이면 하네스가 kill하고 TIMED_OUT(base, 시각 비교 없음). ⓑ created(start 미완료)이면 정지로 보고 부재 확인 뒤 재실행. ⓒ 이미 스스로 exited이고 데몬 실행시간 0 ≤ FinishedAt−StartedAt ≤ 5.0초이면 정지(attach 미반환)로 보고 재실행. ⓓ exited이지만 범위 밖(음수 포함)이거나, 시각 누락·파싱 실패, 그 밖의 전부는 TIMED_OUT(base). 판정 불가는 재실행하지 않는다 | **수정 지시됨(2026-11-11), 재검증 대기.** 처음 제안("FinishedAt−StartedAt ≥ 9.0초일 때만 timed_out 인정")은 검증 FAIL이었다. 클라이언트 10초는 호스트 monotonic(HOST1에서 7~9% 빠름)으로 재고, 데몬 실행시간은 VM 벽시계(약 29초 주기로 0.1~2.5초 역행 관찰)로 재므로 서로 다른 두 시계를 섞은 비교다. 그 결과 진짜 hang이 9.0초 밑으로 측정되어 재실행 2회 뒤 새 abort가 될 수 있었다(base에서는 TIMED_OUT 결과). 새 규칙은 상태로 판정하며, 시각을 쓰는 ⓒ만 두 시각이 모두 데몬 VM 시계인 단일 시계 차다. **5.0초의 근거(ORCH):** 타깃 timeout의 절반이다. 관찰된 역행 최대 2.5초를 감안하면 정상 완주 직전 종료(≈10초)는 ≥ 7.5초로, 빠른 종료 후 attach 정지(관찰 0.107초)는 ≤ 2.6초로 측정된다. 따라서 5.0은 양쪽에서 2.4초 이상 떨어진다. 5~10초 사이에 스스로 끝나고 attach가 정지한 경우는 base대로 TIMED_OUT으로 남는다(드문 잔여 오분류, 보수 쪽). W4는 이 규칙에 동의한다. 진짜 hang은 스스로 5초 안에 exited될 수 없으므로 숨겨지지 않는다 |
| ③ | 상한: 케이스당 2회, 캠페인당 8회, 부재 확인 180초. 넘으면 abort하며 분류기는 불변이다 | "상한 소진 시 종전과 동일"이라는 주장은 실제 동작대로 다시 쓰도록 수정이 지시됐다. ②의 ⓐ·ⓓ는 재실행하지 않으므로 base와 같다. ⓑ·ⓒ에서 상한을 넘으면 abort가 되며, base에서는 TIMED_OUT 결과였던 경우다. 최종 문구는 재검증 뒤 이 칸에 적는다 |
| ④ | 기록 결과는 마지막 시도의 것이다. 폐기 시도는 arm별로 집계한다. 재실행이 있었던 캠페인을 뺀 민감도를 병행 보고하며, **arm별 제외 수를 병기하고 확증 판정에 쓰지 않는다** | 기록은 구현됐다(보고서 `infra_reexecutions`, abort 스텁 `infra_reexecution_count`·`infra_reexecutions`, stderr 1줄). 집계·민감도를 소비하는 코드는 없다(분석기 몫). 폐기 시도의 oracle 결과를 기록하지 않는다(outcome-blind)는 점을 보고서에 명시한다 |
| ⑤ | 정지 시간은 벽시계(H_rem·처리량)에 포함한다 | D043과 일치(등록 정지 공백만 뺀다) |

### cleanup inspect 재시도와 다르다 (지웅 요구)

#335의 case 재실행은 기존 cleanup inspect 재시도(`container.py`의 `_cleanup_inspect`, 1회)와 동작 의미가 다르다. 동등하다고 가정하지 않는다.

| 항목 | `_cleanup_inspect` 재시도 | #335 case 재실행 |
| --- | --- | --- |
| 대상 | cleanup의 읽기 전용 inspect timeout 1회 | 첫 이상이 timeout인 모든 op(create·inspect·start·wait·kill·rm), 확인되지 않은 TIMED_OUT |
| 단위 | 같은 컨테이너, 같은 호출 | case 전체(새 sandbox·run root·컨테이너) |
| 상한 | 1회 | 케이스당 2, 캠페인당 8, 확인 180초 |
| 결과 | 영향 없음 | 마지막 시도의 결과로 대체 |

**#335가 덮지 않는 것:**

- 셀 끝 broker·smoke 스크립트의 최종 cleanup(30초 inspect)
- 백엔드 생성(`version`, 컨트롤러 inspect)과 `bind`
- effect-demo/historical 외 모드(decompress·oras-go 등과 비대칭)
- create timeout 뒤 데몬이 늦게 만든 컨테이너. 남을 수 있으며, 볼륨 in-use로 U가 될 것으로 추론한다
- timeout이 아닌 오류(설계상 제외)

### 판정 영향 (v3 정정, 측정 전, 지웅 승인 = PR 머지)

- **V7′:** v3 판정에서 V7의 분자를 "timed_out step + case 단위 인프라 재실행(폐기 시도) 수"로 한다.
  - arm별 절대 기준(1,000 step당 1건 초과)과 ref 대비 상대 기준(V4와 같은 표)에 같은 분자를 쓴다. 임계와 표는 v2 그대로다. 재실행 수는 따로도 보고한다.
  - **근거:** #335 뒤에는 혼잡이 만들던 timed_out과 abort가 재실행 수로 옮겨 간다. 분자를 그대로 두면 같은 혼잡에서 더 높은 jobs가 통과할 수 있다. 임계를 유지한 채 분자를 줄이면 완화이므로, 재실행을 분자에 넣는 것은 강화 방향의 측정 전 변경이다.
  - V3·V4(abort)는 바꾸지 않는다. 재실행은 캠페인 손실이 아니기 때문이다.
  - 참고(판정 근거 아님): 과거 Stage A의 정지 빈도(17건/약 9.6만 step)는 V7′ 절대 기준에 한참 못 미친다.
- **V9·X1:** 보고에서 "재실행이 있었던 셀의 불일치"를 따로 표시한다. 임계는 바꾸지 않는다. 재실행은 새 run root에서 같은 case를 다시 돌기 때문에, 관찰·feedback 키에 비결정 성분이 섞이면 불일치가 늘어날 수 있다.
- **결정론 검사:** run_exp0 엔지니어링 smoke의 보고 항목으로 둔다(v3 §5.1). 판정 입력이 아니다.

### UNKNOWN

- (해소) margin 1.0초의 근거. Stage A 이벤트에서 die가 start보다 먼저 온 사례가 824건(0.56%)이고 최소 −3.1초였다. ②를 상태 기반으로 바꾸면서 이 margin은 쓰지 않는다. 남는 UNKNOWN은 ⓒ 5.0초 경계 근처의 실제 분포다. Stage A에서 관찰된 사례는 0.107초 1건뿐이다.
- 재실행 결과가 원 실행과 같다는 전제. 합성 producer로만 검증했고 실제 경로 비교 테스트는 없다.
- 정지와 arm의 상관. step당 처리 시간이 arm마다 다르다(파일럿 평균 entry: R-restart 2.1, D 2.9, S-u 4.2).
- Docker Desktop의 실제 StartedAt/FinishedAt 형식. Go RFC3339Nano는 처리된다(검증 probe).

**바뀌지 않는 것:** v2 §6의 임계(V7은 분자 정의만 강화), D041 abort 정의와 V3·V4, 분류기(`abort_classification.py`), oracle 정의(C0/C1/C2), D042·D043.
