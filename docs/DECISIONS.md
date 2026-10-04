# 프로젝트 결정 기록

이 문서는 팀이 이미 합의한 **큰 결정만** 기록한다.

코딩 에이전트가 임의로 이 결정을 바꾸지 않도록 하는 것이 목적이다.

결정을 바꾸려면 PR에서 이유를 설명하고 이 문서도 함께 수정한다.

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
