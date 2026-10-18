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
