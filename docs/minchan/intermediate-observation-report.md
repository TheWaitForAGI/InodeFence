# 민찬 — 중간 파일시스템 상태 관찰 연구 보고서

> **최신 확인: 2026-10-24 KST, HEAD `9e36e1208b163308f744a7208fbfa56c4584b5c9`.**
> 10/22·10/23 본문은 당시 기록이다. 현재 상태는 끝의 “10월 24일 재검토”와
> [결과 확정표](result-freeze-checklist.md)를 먼저 읽는다. v2 native 데모의 팀 실행 보고가
> 추가됐지만 v3 native dependency/qualification과 정책 효과 비교는 여전히 미검증이다.

> 2026-10-23 보완: 아래 기존 본문은 10월 22일 조사 기록으로 보존했다. 새 결과는 문서 끝의
> “10월 23일 후속 결과”와 [가설/증거 조건](research-hypotheses.md),
> [비판 검토](novelty-and-threats.md), [26일 확정표](result-freeze-checklist.md)를 따른다.

작성일: 2026-10-22 KST. 전달 대상: 지웅. 연구·구현 확정 10월 26일, 발표 제출 10월 27일.
분석 checkout: `8d29982c26cebfcce7a413b3ba9177fcd28078de` (PR #111 merge).
작업 branch: `docs/minchan-intermediate-observation`. 시작 시 tracked/untracked 변경 없음.
사용자의 이번 명세를 문서 조사·제한 검증 Task Contract로 사용했다. 기존 core와 실험 판정은 변경하지 않았다.

## 핵심 결론

1. P0/P1/P2는 관찰 장비 세 종류가 아니라 **corpus admission과 mutation 선택을 비교하는 정책**이다. P0는 최종 상태, P1은 transition novelty, P2는 P1에 transition 보상 기반 operator 선택을 더한다.
2. node-tar 7.5.22의 entry stream 소비 완료와 filesystem 작업 완료는 다르다. 독립 경로 작업은 겹칠 수 있어 archive ordinal과 callback 완료 순서는 다를 수 있다. 완료 callback에서 tree 전체를 읽어도 archive prefix snapshot이 되지 않는다.
3. native v1은 요구한 ordered checkpoint를 충족하지 못해 `BLOCKED_NATIVE_OBSERVATION`이다. v2는 partial order와 operation별 evidence를 구현했지만 필수 replacement coverage가 없어 `V2_NATIVE_EFFECT_OBSERVATION_NOT_QUALIFIED`다.
4. v3는 하나의 operation replacement를 느슨하게 바꾸지 않는다. removal과 creation/link 사이의 **명시적 부재와 producer dependency**를 별도 composite로 표현한다. generic 모델·reader·feedback은 구현됐으나 native dependency producer와 qualification은 미완성이다.
5. 이번 직접 검증은 기존 합성 테스트 재실행이다. 실제 node-tar v3 연결 성공, 탐색 효율 향상, 재발견 성과는 **미검증**이다. [실험 결과](experiment-results.md), [근거 색인](evidence-index.md), [편집 가능한 그림](diagrams.md)을 함께 읽는다.

## 자료 확인 범위와 용어

GitHub 연결 도구로 [저장소](https://github.com/TheWaitForAGI/InodeFence)를 확인했다. 요청한 15개 PR의 본문·head/base/merge SHA·diff와 discussion endpoint를 가져왔다. discussion 반환은 모두 빈 배열이었다. 이는 이번 API 반환 범위의 사실이며 삭제된 대화나 별도 CI 로그까지 없다는 증거는 아니다. Diff 전체를 정밀 감사했다는 주장은 하지 않는다. 아래 연구 흐름에 관련된 변경 내용과 현재 코드·테스트를 대조했다. PR별 원문은 [수집 snapshot](evidence/pr-snapshots.json)에 보존했다.

`v1/v2/v3`에는 두 번호 체계가 있다. `node-transition-observation-qualification-v2`, `internal-completion-qualification-v3`, `causal-effect-qualification-v4`는 **옛 v1 checkpoint 계약을 평가한 실험 revision**이다. `entry-effect v2`, `namespace-rebinding v3`는 **관찰 데이터 모델 세대**다. 옛 실험 v3를 최신 native v3 구현으로 부르면 안 된다.

근거 표시는 F=이번 직접 확인, R=PR/보존 보고서의 기록, I=코드 기반 해석, U=미검증이다. 과거 raw는 이 checkout에 없으므로 과거 수치를 F로 승격하지 않았다.

## PR 연구 이력

각 PR의 정확한 head/merge SHA·본문은 snapshot에 있다. 아래 SHA는 PR head 축약값이며 실행 revision은 별도로 표시했다. 후속 PR이 stacked diff를 포함할 수 있어 diff 양을 독립 기여량으로 세지 않는다.

| PR / head | 목적·모델·구현 범위 | PR의 검증/결과 기록(R) | 현재 코드 대조·한계·후속 관계 |
| --- | --- | --- | --- |
| [#79](https://github.com/TheWaitForAGI/InodeFence/pull/79) `b2b936e` | immutable checkpoint/transition/ordered trace/signature | 합성 file→hardlink→replacement, 1,312 tests | model/transition.py 존재; native producer 아님. #81의 기반 |
| [#80](https://github.com/TheWaitForAGI/InodeFence/pull/80) `7d61a63` | 공개 entry/end timing 조사 | timing probe, 1,312 tests; completion 부적합 | entry-timing-probe.cjs 존재. #84의 controlled 조사로 확장 |
| [#81](https://github.com/TheWaitForAGI/InodeFence/pull/81) `59f5fc3` | P0/P1 admission, uniform parent, caller-owned producer | 1,319 tests; effectiveness NOT_RUN | transition_search.py/campaign 존재. #82 scheduler 추가 |
| [#82](https://github.com/TheWaitForAGI/InodeFence/pull/82) `e07d7bc` | P2 안정 operator ID와 1–8 bounded weights | 1,329 tests, transition-only reward | mutation_scheduler.py 존재. violation은 reward 아님 |
| [#83](https://github.com/TheWaitForAGI/InodeFence/pull/83) `0935ccf` | config/export/reader/RNG replay/arm metrics | 1,336 tests; native NOT_RUN | evaluation/transition_evidence.py 존재. 합성 correctness와 효율 분리 |
| [#84](https://github.com/TheWaitForAGI/InodeFence/pull/84) `e2284ef` | 공개 async/sync, inotify, strace, prefix 및 libarchive 경계 평가 | node 201+Python 4회, libarchive 80회; QUALIFIED FAIL | 보고서·probe 존재. 실행 SHA node `06ace942…`, libarchive `99828fa4…`; raw 미확보 |
| [#85](https://github.com/TheWaitForAGI/InodeFence/pull/85) | upload-artifact 4.6.2→7.0.2 | 의존성 변경 | 관찰 모델/연구 결과 없음; 연속 연구 단계로 취급하지 않음 |
| [#86](https://github.com/TheWaitForAGI/InodeFence/pull/86) `1ca7cce` | setup-node 4.4.0→7.1.0 | 의존성 변경 | 관찰 모델/연구 결과 없음 |
| [#87](https://github.com/TheWaitForAGI/InodeFence/pull/87) `104c6d7` | bundled private checkFs2 완료 marker/snapshot | 180 process, 440 exact association, snapshot consistency failure 1건 | ordered snapshot FAIL. 실행 `9ea306f7…`; #88이 callback snapshot 대신 causal effect 검토 |
| [#88](https://github.com/TheWaitForAGI/InodeFence/pull/88) | async-context filesystem completion attribution | 480 process, 1,020 operation exact association, independent 20/20 역순 완료 | v1 feasibility FAIL; causal-effect probe 존재. v2 모델과 구분 |
| [#89](https://github.com/TheWaitForAGI/InodeFence/pull/89) `0eb527f` | v2 contained producer의 input-open attribution/provenance 수정, 고정 matrix | 480회, 420 success+60 expected rejection, 13/14 | `_node_effect_producer.cjs`·adapter 존재. 실행 `36ff7fd…`; coverage FAIL 유지 |
| [#90](https://github.com/TheWaitForAGI/InodeFence/pull/90) `c46f372` | stat bool/float coercion과 association mismatch 거부 | 1,434 tests, 기존 320+160 reader 재검증 | malformed evidence 방어; synthetic transport positive는 native qualification 아님 |
| [#91](https://github.com/TheWaitForAGI/InodeFence/pull/91) `0fa8bda` | truncation 대 removal→creation 진단 | 90 native 진단 실행, 18 complete bundle 검증, v2 replacement 0 | 실행 `2e31ea9`; multi-operation rebinding이 v2 single-operation 조건과 다름. #100 근거 |
| [#100](https://github.com/TheWaitForAGI/InodeFence/pull/100) `3e0ef26` | 별도 v3 rebinding semantics 제안 | PROPOSED/NOT_IMPLEMENTED 당시 상태, 1,504 tests | 당시에는 문서뿐. 현재 #111 구현과 구분 |
| [#111](https://github.com/TheWaitForAGI/InodeFence/pull/111) `44e115b` | v3 dependency/composite/strict reader/additive finite feedback | 22 synthetic checks, 1,584 tests; external manifest digest 보강 | 현재 merge SHA가 분석 기준. native producer NOT_IMPLEMENTED, qualification NOT_RUN |

PR #111 본문은 이전 head `5acd9a0`의 self-consistent token forgery 발견과 `44e115b`의 manifest digest 보강을 기록한다(R). 이번 discussion API는 빈 배열이므로 독립 리뷰 원문·최종 인간 승인 여부는 확인되지 않았다. 현재 reader가 외부 expected digest를 먼저 요구하는 것은 직접 확인했다(F).

## P0·P1·P2: 정확한 비교

기준은 [transition-feedback-v1](../research/design/transition-feedback-v1.md)과 [scheduler 계약](../research/design/transition-mutation-scheduler-v1.md)이다. P0도 공통 evaluation에서 transition 진단을 기록할 수 있다. 차이는 무엇을 **retention/reward에 사용하느냐**다.

| 항목 | P0 | P1 | P2 |
| --- | --- | --- | --- |
| 정책 관찰 단위 | 한 extraction의 normalized final StateSignature v3 + violation fingerprint | entry boundary 간 FilesystemTransition의 bounded key + violation fingerprint | P1과 동일 |
| 시점 | BEFORE/target 종료 뒤 AFTER | BEFORE + 각 검증된 entry completion checkpoint; 별도 AFTER reconciliation | P1과 동일 |
| corpus admission | 새 final key OR 새 violation | 새 transition key OR 새 violation | P1과 동일 |
| parent 선택 | retained corpus에서 uniform | uniform | uniform 유지 |
| operator 선택 | 기존 uniform mutation | 같은 uniform mutation | 초기 weight 1, 새 transition이 하나라도 있으면 해당 operator +1, 상한 8 |
| 반복 | parent→mutation→execute→final novelty→retain | parent→mutation→trace→transition novelty→retain | P1 loop + binary transition reward→다음 weighted draw |
| 추가로 구분 가능한 차이 | 최종 persistent 차이 | 최종 상태가 같아도 중간 identity/namespace/external effect 차이 | 관찰 능력은 같고 입력 분포만 적응 |
| 한계 | 사라진 일시 상태를 놓침 | 유효한 경계가 없으면 해석 불가; checkpoint 사이 모든 syscall을 보는 것은 아님 | bounded reward가 성능 향상을 보장하지 않음 |

예: 내부 경로가 잠시 외부 sentinel과 identity를 공유했다가 끊어진 두 실행이 동일 AFTER를 만들면 P0 final key만으로 구분하기 어렵다. 해당 순간이 유효한 checkpoint에 잡히면 P1은 구분 가능하다(I, 개념 예). 실제 node-tar에서 이 탐지 성공을 검증한 결과는 없다(U). C0/C1/C2 최종 oracle 의미는 P1/P2로 자동 확장되지 않는다. 별도 v2 effect 정책은 incomplete/invalid/rejected trace의 admission/reward를 거부하며 v1 ID나 결과를 조용히 재사용하지 않는다.

## node-tar 순서 문제

분석 버전은 Node 22.22.0 / node-tar 7.5.22다. upstream `v7.5.22`의 [parse.ts](https://github.com/isaacs/node-tar/blob/v7.5.22/src/parse.ts), [unpack.ts](https://github.com/isaacs/node-tar/blob/v7.5.22/src/unpack.ts), [path-reservations.ts](https://github.com/isaacs/node-tar/blob/v7.5.22/src/path-reservations.ts)를 확인했다. upstream tag의 commit SHA는 이번 수집에서 해석하지 않았으므로 SHA 고정 근거로 사용하지 않는다. 실제 package의 compiled source hash는 [기존 qualification 계약](../research/design/entry-transition-observation-v1.md)에 있다.

흐름은 `Parser entry/body consumption → Unpack ONENTRY → CHECKFS/PEND → path reservation → CHECKFS2 → MAKEFS → FILE/DIRECTORY/HARDLINK/SYMLINK → callback/UNPEND/reservation release → MAYBECLOSE`다. Parser의 entry `end`는 body 소비 경계다. fs callback이 끝나기를 모두 기다려 다음 header를 파싱하는 전역 직렬 loop가 아니다. backpressure도 stream 흐름을 제어할 뿐 entry별 모든 filesystem 부수 효과의 직렬 완료를 증명하지 않는다.

CHECKFS는 destination과 linkpath를 reservation에 넣는다. 같은 경로/관련 의존 경로의 충돌은 예약으로 제한되지만, 독립 경로는 겹칠 수 있다. 따라서 “파일 A가 먼저 archive에 있으므로 모든 A 작업이 B보다 먼저 끝난다”는 성립하지 않는다. 정확한 dependency는 reservation/실제 callback continuation/handle provenance로 확인해야 한다. ordinal이나 timestamp만으로 추가 edge를 만들면 안 된다.

구분할 경계는 다음과 같다.

| 경계 | 의미 | 보장하지 않는 것 |
| --- | --- | --- |
| `onReadEntry` | entry 전달·identity 부착 후보 | 파일 생성·쓰기 완료 |
| entry `end` | 입력 body 소비 | output stream finish, metadata, close |
| fs operation callback | 해당 API의 성공/오류 통지 | 다른 작업의 완료, callback 간 물리 효과 전체 순서 |
| private `checkFs2`의 `fullyDone` | 해당 entry 분기 작업 settled/예약 반환 경로 | archive prefix snapshot, 성공 여부를 오류 채널 없이 판정 |
| `tar.x` resolve/reject | invocation의 terminal outcome | 디스크 영속화, 모든 숨은 API가 계측됐다는 증명 |

regular stream finish 후 metadata·close 등 여러 callback이 남을 수 있다. directory/link도 각각 별도 완료 경로를 가진다. close callback은 파일 descriptor 닫힘이며 fsync/fdatasync 완료나 전원 손실에 견디는 영속화가 아니다. 외부 lstat/read가 보는 상태는 callback 전달보다 앞서 존재할 수 있고 tree walk는 원자 snapshot이 아니다.

**과거 관측 기록(R):** #87 mixed snapshot은 `1,0,2,3,4`가 20/20, independent-files는 `0,1,3,2`가 18/20이었다. 첫 snapshot에 뒤 entry 경로가 이미 보였다. #88 effects에서는 independent-files `0,1,3,2`가 20/20, earlier completion 전 later operation 162개가 기록됐다. 이번에 raw를 재현한 값이 아니다. [타임라인](diagrams.md)은 이 기록과 가상 설명을 분리한다.

## Native Observation v1 → v2 → v3

### v1: ordered complete checkpoint 요구와 실패

목표는 정확한 entry reference를 가진 complete checkpoint를 archive 순서대로 얻어 consecutive state delta를 만드는 것이다. 공개 read/end는 이르며, inotify receipt/tree walk는 뒤 effect를 포함하거나 capture consistency가 실패했다. strace는 syscall과 entry의 완전한 대응 및 중립성을 자동 제공하지 않는다. prefix replay는 원 실행의 중간 시점이 아니라 별도 반사실 실행이다. private hook은 association에는 성공했지만 ordered prefix와 coherent snapshot을 보장하지 못했다.

실패는 node-tar 취약점이나 transition feedback 무효의 증거가 아니다. **이 버전·fixture·관찰 방식이 고정된 v1 계약을 충족하지 못했다**는 bounded negative result다. 최종 상태가 같았다고 중간 scheduling 중립성이 증명되지 않는다. #87의 snapshot/stock target-time 비율 1.336–1.660, #88 effects/stock 1.152–1.308은 보존 보고서의 기술 통계이며 이번 성능 측정이 아니다.

### v2: operation event와 partial order, 14개 mandatory criteria

정의의 실제 판정 위치는 `scripts/qualify_node_effect_observation.py::_summarize`다. 모두 참일 때만 qualification이다. 표의 결과는 #89 및 보존 요약(R)이며 이번 raw 재계산은 불가능했다.

| 조건 ID | 코드가 요구하는 판정 기준 | 기록 결과 |
| --- | --- | --- |
| complete_fixed_matrix | 8 fixtures × 3 profiles × repetitions, repetitions ≥20 | 통과: 480 |
| clean_source_revision | 실행 source clean | 통과 |
| expected_target_outcomes | rejection fixture 외 success, rejection은 rejected | 통과: 420/60 |
| transport_and_association_integrity | non-stock trace integrity valid | 통과 |
| semantic_state_equality | fixture/repetition별 profile final semantic digest 동일 | 통과 |
| required_effect_coverage | fixture별 required realized effect + required operation 종류 모두 충족 | **실패** |
| rejection_failure_operation_observed | full rejection에서 실패 operation 보존 | 통과 |
| normalized_key_stability | fixture/profile 반복 간 key digest 안정 | 통과 |
| rejected_prefix_feedback_ineligible | rejected prefix의 key 없음 | 통과 |
| failure_injections_detected | injection 결과 비어 있지 않고 모두 검출 | 통과 |
| timeout_preserved_incomplete | forced timeout을 incomplete로 보존 | 통과 |
| overflow_preserved_invalid | overflow를 invalid로 보존 | 통과 |
| backend_failure_distinct | backend 오류와 target/trace 판정 분리 | 통과 |
| overhead_and_completion_order_reported | 보고 항목; 현재 구현은 상수 True | 통과로 집계됨; overhead 중립성 threshold 아님 |

실패 cell은 duplicate-path의 `namespace_replacement`다. 기대는 v2 정의의 single-operation realized replacement coverage, 실제 기록은 same `(st_dev, st_ino)` truncation 20/20, replacement 0/20이다. upstream ISREUSABLE는 regular file·unlink 비활성·nlink≤1·비Windows이면 기존 객체를 재사용한다. 이 분기는 보고된 결과와 일치하는 코드 설명(F/I)이다. 이번 원본 trace를 읽지 않았으므로 개별 run의 실제 분기 실행을 새로 확정하지 않는다. 추가 검증은 archived qualification/raw checksum 확보→independent reader 재계산→duplicate open 전후 evidence 대조다.

#91의 별도 진단은 unlink→create/mkdir/link/symlink로 binding이 바뀌어도 v2 reader가 removal+creation/link로 유지한다고 기록한다. 이를 기존 v2 replacement 성공으로 재분류하지 않는다. separated inode 값이 같다는 사실만으로 연속 identity도 증명할 수 없다(재활용 가능).

### v3: 명시적인 namespace rebinding composite

현재 `NamespaceRebindingSequence`는 같은 entry·같은 destination의 성공 removal→creation/link를 묶는다. removal 전 present/후 absent와 creation 전 absent/후 present가 필요하다. removal completion→creation start의 직접 `producer_branch_continuation` dependency, 정확한 correlation/sequence, gap 중 같은 경로의 conflicting binding 부재를 요구한다. 타 경로 operation은 남아도 된다. symlink는 destination, hardlink는 destination과 source 역할을 구분한다.

reader는 complete/valid/successful v2 trace와 externally frozen expected v3 raw SHA-256를 먼저 확인한다. endpoint evidence를 v2 event와 cross-check하고 composite를 재구성한다. 내부 digest만 다시 맞춘 token 위조는 외부 manifest digest와 불일치해 거부된다. 이는 native branch token의 진실성을 자동 증명하지 않는다. native producer가 실제 continuation에서 token을 내보냈는지는 다음 qualification 과제다.

v3 normalized key는 type/ordinal bucket/region/creation kind 등 유한한 특징만 추가한다. exact path/inode/token/time은 evidence에만 남는다. v2 keys가 같은 “A removal→B creation”과 “A removal→A creation” 중 후자만 composite가 되는 합성 nonredundancy가 확인됐다. 이는 representation의 추가 구분 능력이며 더 빠른 fuzzing 결과가 아니다.

| 수준 | 현재 상태 |
| --- | --- |
| 설계 의도 | multi-operation same-path dependency와 explicit absence 보존 |
| 구현 | model/rebinding.py, feedback/rebinding.py, evaluation/rebinding_evidence.py |
| 직접 검증 | 이번 focused suite와 기존 v3 합성 positive/negative/tamper 테스트 재실행 |
| 미완성 | native dependency token producer, manifest publication 연결, native v3 qualification, 캠페인 effectiveness |

## 실제 node-tar 연결: 기존 코드와 누락 부분

**이미 있는 연결:** `_node_effect_producer.cjs`가 fs API wrapper를 설치한 후 package를 load하고, `onReadEntry`의 ordinal/path/type/link-target를 WeakMap에 보존한다. private `checkFs2`는 AsyncLocalStorage entry context와 work-start/settled를 만든다. open의 fd owner를 저장해 write/close를 연결하며 context/handle conflict를 기록한다. operation start/completion은 correlation ID·record sequence·path·관찰 interval·before/after object evidence·오류를 가진다. `node_tar_effect.py` adapter와 `effect_pipeline.py`, `native_effect_evidence.py`가 target→flush→AFTER→검증/보존을 담당한다. 이는 **v2 producer가 실제로 존재한다**는 뜻이며 v3 연결 완료가 아니다.

**제안 연결(미구현):** node-tar CHECKFS2의 성공 unlink/rmdir callback에서 동일 entry의 MAKEFS continuation을 시작하는 정확한 분기를 계측한다. removal completion correlation과 다음 실제 creation operation start correlation을 branch token으로 연결하고 v3 dependency envelope를 별도 export한다. 단지 동일 async context 안에 있다는 이유만으로 이 edge를 만들지 않는다. creation 종류별 FILE/DIRECTORY/HARDLINK/SYMLINK 진입과 callback을 확인해야 한다. existing fs wrapper의 event를 재사용하고 generic observer에 node-tar 분기 지식을 넣지 않는다.

이 연구의 “작업 완료”는 **명명한 fs API callback에서 성공/오류를 기록한 경계**와 **entry 분기의 settled 경계**를 따로 뜻한다. synchronous throw도 실패로 보존한다. disk durability는 범위 밖이다. callback에서 직접 얻은 API error/entry association과 그 전후 lstat evidence는 관찰이며, realized class/composite는 고정 규칙에 의한 파생 결과다. recording sequence는 observer의 순서다. causal edge는 callback continuation/handle provenance 같은 별도 증거가 필요하다.

필수 다음 구현 항목:

- 현재 package entrypoint/unpack/producer hash와 정확한 source revision을 고정하고 실제 bundled class에 계측한다.
- removal callback→creation scheduling 분기에 producer-issued token을 발급한다. branch가 없거나 대응이 불명확하면 emit하지 않고 fail closed한다.
- dependency raw와 v2 raw digest·endpoint·external manifest를 원자적으로 binding하고 no-overwrite로 보존한다.
- reader에 누락·중복·unknown endpoint·token 바꿈·source mismatch·오류/timeout/overflow를 주입한다.
- stock/minimal/full, archive-only fixtures, 반복≥20, final equality·dependency truth·observer perturbation 기준을 실행 전 고정한다.

계측은 lstat/hash·JS wrapper·AsyncLocalStorage·메모리 buffer·flush 비용으로 event-loop와 I/O scheduling을 바꿀 수 있다. 현재 wrapper가 다루지 않는 sync/Promise/native-addon 경로, event bound 초과, callback 이전 process 종료, path evidence 수집 경쟁은 누락 원인이다. 지원 API 목록 밖을 “모두 관찰”했다고 쓰면 안 된다. source guard는 버전 오류를 줄이지만 완전성 증명은 아니다.

## 기존 연구 비교

원문을 확인한 자료는 아래 표 링크와 같다. 논문 수치는 저자의 보고이며 이번 재현 결과가 아니다. 공통 budget으로 비교 실행하지 않았다.

| 연구 | 목적/대상·입력 선택 | 관찰 시점·단위/중간 상태 | 순서·링크·identity | 근거·한계 |
| --- | --- | --- | --- | --- |
| [ZIPDiff, You et al., USENIX 2025](https://www.usenix.org/system/files/usenixsecurity25-you.pdf), [공식 코드](https://github.com/ouuan/ZipDiff) | ZIP parser semantic gap; grammar/byte mutation, output feedback와 UCB 선택 | extraction output 비교; transient native completion stream은 확인되지 않음 | path/metadata 차이; inode/async causal 모델 확인되지 않음 | §4, §7.3: 50 parsers/19 languages; disk output이 internal result와 다를 수 있다는 한계 |
| [Wormholes, Liu et al., USENIX 2026](https://www.usenix.org/system/files/usenixsecurity26-liu-yongheng.pdf) | symlink API 오해·validation bypass; 분석한 bypass/write 전략 | path resolution과 extraction effect; feedback corpus loop는 확인되지 않음 | composition/creation order/hardlink를 다룸; node-tar callback partial-order 모델 확인되지 않음 | §4–5: 85 projects 평가, 16 arbitrary-write 보고. §5.6 ZIPDiff 비교는 저자 측 특정 20-tool 평가 |
| [LinkZard, Xiang et al., USENIX 2025](https://lfysec.github.io/paper/linkzard-security25.pdf) | Windows link-following; query-guided file-state mutation, operation type/count feedback | 실행 중 state query/API operation와 primitive graph | operation sequence·hardlink 정보·link count 포함; Linux inode 연속 identity 모델 확인되지 않음 | §4–5/Appendix C: state constraints/sink graph. TAR corpus와 Linux 대상이 아님 |
| InodeFence 현재 | Linux TAR generic mutation + security-state novelty 가설 | final snapshot; v1 synthetic checkpoints; v2 operation effects; v3 synthetic rebinding | raw identity/namespace/effect와 검증된 dependency 분리 | v1 blocked, v2 not qualified, v3 native 미구현. superiority/일반화 미검증 |

차별점 후보는 **TAR를 evolving input으로 유지하면서 target operation evidence에서 검증된 same-path rebinding과 object/external-effect 특징을 유한 feedback으로 연결**하는 조합이다. “기존 연구가 상태·링크·순서를 보지 않았다”는 주장은 근거와 맞지 않는다. v3 native 완전성과 동일 budget 효과 비교 전에는 최초·우월·더 많은 취약점 탐지라고 발표하지 않는다.

## 구현·검증 범위와 10월 26일 마감 기준

이번에는 기존 최소 v2 collector와 v3 synthetic reader가 이미 있어 이를 중복 구현하지 않았다. native v3는 실제 branch token 의미와 qualification 기준을 새로 고정해야 하므로 연결 분석까지 제공하고 합성 검증을 재실행했다. 기존 negative gate를 pass로 바꾸는 수정·matrix 재실행·campaign은 수행하지 않았다. 이는 문서 산출물을 완성하는 데 필요한 조건이 아니다.

10월 26일까지: (1) 지웅과 v1/v2/v3 명칭 및 발표 claim을 확정, (2) 과거 raw archive·checksums를 확보해 14조건 reader를 fresh process에서 재계산, (3) native v3를 추진하면 source-guarded branch token Task Contract와 stock/minimal/full 허용 기준을 먼저 확정, (4) 미완료면 발표에는 연결 제안·합성 결과·negative qualification만 남긴다. 10월 27일은 [6장 발표 구성](presentation-outline.md)을 사용한다. 이 일정은 사용자가 지정한 중간 발표 일정이며 STATUS의 별도 11월 연구 일정과 혼동하지 않는다.

## 10월 23일 후속 결과

시작 HEAD는 기존 문서 커밋 `3c2487b659a24d2f4b7bc38b5ca9928ffb959723`다.
`docs/minchan-intermediate-observation`과 `minchan/intermediate-observation`은 모두 같은 SHA로
tree/commit 차이가 0이었다. clean tree에서 docs branch로 이동했다. 다른 branch를 삭제·reset·merge하지
않았다. engine은 여전히 `8d29982c…`이며 새 변경은 로컬 dirty diff다. 커밋/push/외부 게시 없음.

### 기존 산출물 점검과 이번 추가

| 영역 | 시작 시 완료/부족 | 이번 결과 |
| --- | --- | --- |
| PR 이력·P0/P1/P2·node-tar 순서 | 설명/표 완료 | #81/#82/#89/#90/#100/#111 metadata 재확인; head/merge SHA 유지 |
| PR 리뷰 상태 | 수집 snapshot의 빈 discussion | #111 discussion 재조회도 빈 배열. 최종 adversarial review 원문·인간 승인 미확인 |
| 76 focused / 1,584 canonical | 10월22일 로그 보존 | 이번 로그는 별도 날짜 파일; 과거 결과를 재사용한 pass 아님 |
| 중간 관찰 인정 조건 | 항목별 인정표 부족 | research-hypotheses 증거표 완료 |
| 비교 가설 | 정책 차이는 있으나 반박·지표 부족 | H-REP/H10/H21, 비교 프로토콜·반박·미동결 항목 명시 |
| v3 native | generic만 구현, native branch token 없음 | target-free bounded capture prototype 추가; native 미구현 유지 |
| 신규성·교란·oracle | 비교표 존재 | 예상 반박 14항목, 남은 약점/추가 검증 정리 |
| 결과 확정/인계 | 22일 시점 | 23일 증거 기준 26일 사용 가능한 상태표 추가 |

### 제한 구현의 Task Contract

현재 Layer는 target observation의 engineering prototype다. 목표는 interleaved operation bookkeeping과
기존 v3 reader wire compatibility를 합성 입력으로 점검하는 것이다. 수정 영역은
`scripts/minchan_rebinding_capture.py`, `tests/test_minchan_rebinding_capture.py`, `docs/minchan/`이다.
generic core·C0/C1/C2·기존 policy/reader·target worker·N05/Track A 구현은 수정하지 않는다.
입력은 typed v2 event와 caller가 명시한 synthetic continuation token이고 출력은 terminal 상태와
검증된 v3 형식 bytes다. 보안 oracle을 추가하지 않는다. 완료 조건은 실패/누락/중복/종료/역순에 대한
합성 검사, existing reader 호환과 canonical validation, native 미검증 표시다.

prototype은 unique correlation과 entry/start sequence를 묶고 완료 event를 대조한다. 실패 error code,
pending IDs, overflow invalid를 남긴다. operation 수는 1..256으로 제한한다. caller 소유 string/object가
있으므로 constant-byte-memory producer는 아니며 export에 기존 reader의 1MiB cap을 적용한다.
same entry/path/time만 보고 dependency를 만들지 않는다. explicit predecessor+token은 성공 완료 뒤
다음 begin에만 허용한다. envelope는 unchanged v3 reader로 재검증한다. 외부 manifest를 발행하거나
token의 native 진실성을 보증하지 않는다. 실제 node-tar에 이 Python prototype을 연결하지 않았다.

### bounded native producer 타당성 판정

| 항목 | 근거/후보 | 판정·남은 한계 |
| --- | --- | --- |
| entry association | onReadEntry WeakMap + checkFs2 ALS + fdOwners | 구현 가능한 기존 v2 경로; unsupported/sync/native API는 별도 감사 |
| start/complete/error | producer line 315 operation_start, 342 completion, 369 callback, 396 onError | 직접 API callback 경계 관측 가능; kernel effect 시각·durability 아님 |
| 실제 branch hook | CHECKFS2의 unlink callback→MAKEFS; producer wrapper completion 후 original callback 호출 직전 | source별로 특정 가능한 후보. 같은 context의 첫 matching operation만으로 true branch라 단정 금지 |
| nested/concurrent work | entry/operation IDs, callback별 context, one-shot branch token | 순서 역전 보존 가능. context 오염·token 이중 소비·source branch drift 음성 검사 필요 |
| 상태 evidence | v2 before/after lstat·hash와 path role | 국소 interval 관측. 원자 전체 snapshot·완전 gap 부재 보장 불가 |
| bounded/termination | event/byte bounds, terminal flush, pending/fault | overflow/kill/drop은 incomplete/invalid. 이번 prototype에 durable prefix/실제 flush 없음 |
| perturbation | 동기 probe/ALS/token/serialization 추가 비용 | native profile 비교 전 중립성 미검증; 기존 profile scheduling 변화는 위험 근거 |
| 실제 실행 | pinned image/source/worker/lock·Linux runtime volume·trusted broker·한정 fixtures·명시 승인 | 현재 task는 실행 승인 없이 가능한 합성 작업만 허용. native 미실행 |

구체적인 차단은 (1) 실제 branch token hook 미구현, (2) v3 source/image/protocol 및 acceptance 계약의
독립 검토·실행 승인 미확보, (3) 과거 raw 미확보다. 단순히 Docker가 동작하는지 시험하거나 consumed
preflight를 재시도하지 않았다. host namespace 문제를 우회한 shell 실행은 target isolation 승인과 다르다.

### 실행 게이트와 다른 담당의 의존성

현재 checkout의 STATUS와 N04 synthetic v3 Task Contract는 native 실행을 허용하지 않는다.
추가로 remote ref `origin/docs/n05-native-qualification-critical-path`의 `00356e4` 보고서와 draft를
읽었다. 이는 source-only read이며 checkout에 merge하지 않았다. 그 보고서는 native v3 branch hook과
별도 600-slot qualification **제안**을 설명하지만 승인이 아니다. 해당 문서가 기록한 source tarball
hash·compiled line 번호는 그 보고서의 자료 주장(R)으로만 취급한다.

2026-10-23 GitHub #115 head `e83349ed…`는 closed이고 본문상 N05 NOT_AUTHORIZED/NOT_RUN이다.
#122 head `20f190b0373db851e1c5b0ea343eb889dddaa451`은 open engineering candidate이며 N05/pilot
NOT_RUN, source/mount 계약과 clean integrated SHA가 남았다고 명시한다. merge/CI만으로 승인하지 않는다.
이것이 규민·주언의 개인 작업 전체 상태를 증명하지는 않는다. 접근 가능한 PR 자료 범위의 의존성 확인이다.
N05 실행과 B0/B1/B3는 이번 범위 밖이며 native v3 또는 H10/H21의 증거로 대체할 수 없다.

### 대안과 후속 최소 조건

| 대안 | 장점 | 단점/인정 경계 |
| --- | --- | --- |
| source-guarded callback continuation 계측 | 기존 v2 reuse, native scheduling 유지 시도 | private/bundled source 취약, 교란/branch truth qualification 필요 |
| target source에 명시적 hook patch | branch 지점이 명확하고 검토 쉬움 | 수정 target임을 명시해야 함, stock equivalence와 patch 관리 비용 |
| syscall/inotify corroboration | 별도 관찰 채널로 효과 순서 점검 | entry/branch dependency를 직접 제공하지 않음, v3 대체 producer 아님 |
| target-free prototype + generic v3 확정 | 지금 재현 가능하고 과장 없는 engineering 산출물 | 실제 관찰·성능·native feasibility 확정 못 함 |

다음 최소 조건은 frozen exact bundled source와 branch specification, pinned contained image·독립 검토,
explicit bounded 실행 승인, raw/manifest publication trust, stock/minimal/v2-full/v3-full qualification,
failure injection과 fresh-process reader다. 이 조건이 없으면 26일 결과는 generic/synthetic 및 negative
qualification 분석으로 확정한다. [확정표](result-freeze-checklist.md)에 상태를 분리했다.

## 10월 24일 재검토: 현재 코드·팀 데모·연구 판정 분리

작업 시작 HEAD `9e36e1208b163308f744a7208fbfa56c4584b5c9`는 기존 작업
`f90f342`와 main의 #133까지 포함한 merge다. 다른 minchan branch는 여전히 `3c2487b`다.
따라서 두 branch가 같다는 10/23 기록은 과거 사실이며 현재에는 해당하지 않는다.
시작 tree는 clean이었다. 현재 docs branch에서 이어갔으며 branch 삭제/강제 이동/merge/commit/push를
하지 않았다. engine 전체가 `8d29982c` 그대로라는 과거 표현도 현재에는 적용하지 않는다.
단, native v2 worker와 v3 strict reader는 그 SHA와 diff가 없음을 확인했다.

| 항목 | 재검토 결과 | 근거 수준/남은 부분 |
| --- | --- | --- |
| 인정 조건·H10/H21·반박 표 | 기존 완성본 유지, 최신 scope 보완 | 코드·자료 확인; 효과는 미검증 가설 |
| v2 native 데모 | #133 본문/STATUS/LOG에 실제 실행 보고 추가 | 팀의 실제 관측 보고; 이번 원본 미확보·독립 미검증 |
| v3 generic 모델/reader | 기존 구현 유지 | 합성 검증; native dependency hook 없음 |
| bounded prototype | operation coverage와 token one-shot 검증 보완 | 합성 회귀 검증; native producer 아님 |
| 승인 게이트 | 기존 qualified research gate와 새 bounded demo 경로 분리 | 팀 데모 경로 존재가 v3 실행/qualification 승인 아님 |
| 과거 qualification raw | 로컬 primary/mirror 없음 | 독립 재계산 차단 |

### 최신 데모에서 주장할 수 있는 범위

[PR #133](https://github.com/TheWaitForAGI/InodeFence/pull/133)은 report schema 2에 entry별
operation·association·before/after status·present일 때 dev/ino/nlink/size, observation failures,
64-event 잘림 표시와 selection을 추가했다. `src/inodefence/effect_demo.py`를 직접 읽었다.
이 출력은 entry/start 순으로 정렬하므로 출력 배열을 실제 completion 순서로 해석하지 않는다.
원본의 completion_sequence가 별도로 존재한다. report는 모든 lifecycle/frontier를 복제하지 않고
hash·전체 operation별 raw reference도 담지 않으므로 qualification raw bundle을 대체하지 않는다.

PR 본문과 LOG의 사람 실행 보고는 2회 native 데모, 20 steps, link의 nlink 2, step 8/18의 event 0 및
operation_correlation_conflict를 기록한다. 이 원본 JSON은 현재 checkout에서 찾지 못했다.
따라서 이번에 20-step 결과를 재계산하거나 직접 node-tar를 관찰했다고 쓰지 않는다.
또한 LOG는 step18 stderr를 관측값, strict INFO→rejection 설명을 사람 해석으로 나누므로 그대로 구분한다.

`scripts/run_effect_demo.py::native_demo_report`는 성공 target의 invalid trace에서는 중단하지만,
rejected target은 invalid trace를 남기고 loop를 계속할 수 있다. 이는 데모 처리이며 해당 prefix의
완전한 중간 관찰 성공은 아니다. event 0을 filesystem effect 부재로 해석하지 않는다.
이 bounded demo와 v2 negative qualification, native v3 미구현은 함께 성립한다.

### 이번 최소 수정과 검증 경계

이번 Task Contract는 P0-2 관찰 evidence bookkeeping 검증이다. `scripts/minchan_rebinding_capture.py`,
그 테스트와 기존 docs/minchan을 보완한다. production producer/reader·oracle·scheduler·N05·B0/B1/B3를
수정하지 않는다. 새 실행 게이트를 만들지 않으며 native demo도 이번에는 실행하지 않는다.

먼저 4개 회귀 case를 추가해 모두 실패함을 재현했다. 첫 결함은 empty/partial capture가 완전한 v2
trace를 전달받고도 operation 누락을 거부하지 않는 것이었다. 이제 export에서 correlation 집합을
정확히 대조한다. 둘째는 predecessor/token 재사용이었다. 이제 capture 안에서 둘 다 one-shot이다.
이는 prototype의 보수적인 지원 범위이며 generic v3 계약을 바꾸지 않는다. 실제 native continuation
발급과 token 진실성은 구현하지 않았다.

`CaptureTerminal.complete`는 알려진 start들의 local settlement만 뜻한다. export 시 v2 전체 event와
대조해야 한다. v2와 capture 양쪽에 모두 빠진 작업, 지원 밖 API, fsync/durability, atomic tree snapshot은
여전히 보장하지 않는다. 신규/기존 합성·보고 테스트와 canonical 결과는
[이번 실행 기록](experiment-results.md)의 10/24 절을 따른다.

### 26일 확정 기준

데모 출력 기능, synthetic bookkeeping/reader 호환, 기존 negative qualification 분석은 설명할 수 있다.
팀 native 데모 수치는 “PR/LOG의 실행 보고, 원본 독립 검증 전”으로 인용한다.
native v3 성공·전체 snapshot·H10/H21 효과 향상은 주장하지 않는다. 남은 최소 의존성은 데모 원본과
그 source/image identity, native v3 branch hook·계약·명시 승인·qualification, 별도 공정 비교 동결이다.
