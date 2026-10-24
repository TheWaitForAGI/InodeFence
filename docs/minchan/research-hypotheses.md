# 중간 관찰의 증거 인정 조건과 비교 가설

2026-10-23 KST 보완. 기존 문서 base `3c2487b659a24d2f4b7bc38b5ca9928ffb959723`,
engine base `8d29982c26cebfcce7a413b3ba9177fcd28078de`.
이 문서는 검토용 프로토콜이다. native 실행 승인·정책 ID 동결·비교실험 결과가 아니다.

**10/24 보완:** 현재 분석 HEAD는 `9e36e12`다. MIDTERM_GOALS의 우선순위 **P0-1~P0-5/P1**과
여기서 비교하는 연구 정책 **P0/P1/P2**는 별개다. H10/H21은 후자를 뜻한다. 팀의 native v2 demo
실행 보고가 추가됐지만, 그것은 qualified v3 producer나 H10/H21의 비교실험을 대신하지 않는다.

## 관찰 수준의 정의

P0는 BEFORE/terminal AFTER의 final signature/violation을 admission에 사용한다.
P1은 검증된 intermediate transition key로 admission을 바꾸며 parent/operator는 uniform이다.
P2는 P1과 같은 관찰·admission을 사용하고 operator weight만 transition reward로 적응시킨다.
공통 평가를 위해 P0에도 같은 trace를 수집할 수 있다. 수집 가능 정보와 정책 사용 정보는 다르다.
기준은 [v1 정책 계약](../research/design/transition-feedback-v1.md)이다. v2 effect와 v3 composite를
이 비교에 사용하려면 별도 정책 버전·qualification을 동결해야 한다. 기존 P1을 임의로 v3로 부르지 않는다.

“실제 중간 상태 관측 검증”은 아래 조건을 충족한 **실제 target run의 한정된 path/object 관측**을 뜻한다.
v2/v3 operation 전후 observation은 capture interval을 가진 국소 증거다. 서로 다른 callback의
object 관측을 합쳐 특정 한 시점의 전체 filesystem 상태라고 인정하지 않는다. 전체 tree의 원자성,
모든 작업의 관찰, archive-prefix snapshot은 현재 event model만으로 입증할 수 없다.

## 증거 인정표

“현재 확보”에서 합성은 native 증거가 아니다. 과거 수치는 원본 미확보인 보존 요약의 주장(R)이다.

| 조건 | 필요한 증거 | 현재 확보 여부 | 근거 위치 | 부족한 부분 | 검증 방법 |
| --- | --- | --- | --- | --- | --- |
| 실제 target invocation | pinned target 실행 원본·exit/termination | 과거 v2 기록 R; 이번 없음 | 기존 experiment-results / #89 | 이번 native raw | 별도 승인된 contained run와 fresh reader |
| 입력 고정 | TAR bytes/hash, ordered ArchiveCase, options | 과거 요약 R·모델 확인 | builder/model, qualification summary | 과거 raw bytes | regenerate/hash와 retained case 대조 |
| entry 식별 | ordinal+raw path+type+link target | 코드 확인·합성 검증 | `_node_effect_producer.cjs` onReadEntry, #79/#89 | native v3 mapping | duplicate path·동일 path 다른 ordinal fixture |
| 작업 식별 | unique correlation, operation, path role, fd generation/owner | v2 코드·prototype 합성 | producer fdOwners / prototype begin | 모든 API 경로 지원 여부 | callback·handle 충돌 및 unsupported API 음성 검사 |
| 시작 | API 호출 전 observer sequence와 before evidence interval | v2 코드·합성 | operation_start / prototype begin | 실제 fs 실행 시작 시점과 차이 | wrapper 경계와 호출 site 대조; kernel 시작이라고 부르지 않음 |
| 완료 | API callback의 success/error와 after evidence | v2 기록 R·합성 | operation_completion / complete | v3 native capture | 원 callback 반환값·오류 보존, throw·double callback 검사 |
| 실패·entry settled | fs error, target error, entry lifecycle, exit 각각 | v2 코드·합성 | onError/checkFs2; terminal tests | 실패가 숨은 API에서 발생하는 경우 | partial rejection·throw·timeout fixture |
| file close | 정확한 fd의 close callback | v2 코드; 이번 native 없음 | producer close wrapper | 원 run의 descriptor 생애 | open completion→handle origin→close 연결 |
| 외부 가시성 | lstat/read의 실제 값과 capture interval | 과거 v2 R; 합성 객체 | EffectObjectObservation | 실제 v3 stable capture | 전후 stat 재확인·capture 오류 보존; 단일 시점 주장 금지 |
| 영속화 | fsync/fdatasync와 저장장치 모델 | **미확보·범위 밖** | 기존 계약에 보장 없음 | durability 계측·모델 전부 | 이 연구의 완료 정의에서 제외 |
| 상태와 작업 연결 | 동일 correlation·entry·path role의 start/complete evidence | 코드·합성 검증 | v2 reader, v3 endpoint cross-check | native token의 branch truth | 독립 endpoint 재구성·다른 path/entry 주입 거부 |
| 인과 dependency | 실제 removal callback continuation에서 발급한 token | generic/합성만 | v3 reader; prototype explicit token | **native hook 미구현** | pinned bundled 분기 계측, 단 한 번 consume, 음성 대조 |
| 누락·중복 | global sequence/count/digest/flush·start/complete pairing | v2 reader·합성 | 기존 producer tests·새 ledger tests | 호출 자체가 통째로 관측 밖인 경우 | transport 누락 주입과 API coverage 감사; 없다고 추정 금지 |
| 종료·미완료 | pending IDs·target terminal·overflow/invalid 상태 | prototype 합성 검증 | CaptureTerminal | process crash의 durable prefix 보존 | kill/timeout native qualification; 이번 미실행 |
| explicit absence | removal 후 absent·creation 전 absent | generic/합성 | rebinding predicates | 실제 v3 local observations | absent와 observation failure를 분리, ENOENT와 오류 구분 |
| gap conflict | 관측된 같은 경로 binding interval 중첩 없음 | generic/합성 | feedback/rebinding.py | 미관측 작업 배제 불가 | complete supported channel 검증·unsupported 범위 명시 |
| 전체 중간 snapshot | 같은 시점·원자성·대상 전체의 completeness | **미확보** | v1 blocked decision | 현 모델로 보장하지 않음 | 별도 coherent snapshot 계약 없이는 주장 금지 |
| 재현·신뢰 경계 | source/dirty patch·image/lock/producer digest·OS/Node/FS·limits·input·raw·manifest | 과거 identity R·이번 source/log | evidence-index / experiment-results | native v3 image·external manifest | 외부 기대 hash부터 independent reader 실행 |
| 관찰 교란 | stock/minimal/v2-full/v3-full outcome·state·order·timing | 과거 profile 차이 R; 이번 없음 | #87/#88/#89, N05 draft | 새 instrumentation의 동작 중립성 | 사전 동결 기준으로 qualification; 분포 같아도 일반적 무교란 증명 아님 |

콜백 기록 순서는 observer order다. operation interval은 호출 경계→callback 경계이며 kernel effect의
정확한 발생 순간이 아니다. close는 fsync가 아니다. absence observation은 gap 전체의 부재 증명이 아니다.
“gap conflict 없음”은 complete하다고 검증한 지원 event channel에 한정한다.

### 10/24 증거 상태 변경과 추가 조건

위 인정표는 10/23 당시 확보 상태다. 현재의 변경분은 다음과 같으며 나머지 부족한 증거는 유지된다.

| 조건 | 필요한 증거 | 현재 확보 여부 | 근거 위치 | 부족한 부분 | 검증 방법 |
| --- | --- | --- | --- | --- | --- |
| v2 demo local observation | schema2 native JSON·source/image·per-step integrity | #133/LOG의 실행 보고; code 직접 확인 | effect_demo.py, run_effect_demo.py | 원본 JSON 로컬 미확보 | raw와 source/image identity를 받아 independent reconstruction |
| 실패 entry의 관찰 | rejected termination·start만 남은 작업·관찰 오류 | 팀 보고 event0/conflict; native code 확인 | LOG 10/24, native_demo_report | 원본·callback 종료 경로 직접 검증 | rejected case는 incomplete/invalid로 남기고 effect 부재로 해석하지 않음 |
| 보고 배열의 순서 | 실제 start/completion sequence | schema2 코드 확인 | effect_demo._trace_report | 출력은 entry/start 정렬이며 completion 정렬 아님 | 명시 sequence를 대조, 시간/배열 인접성으로 causal edge 만들지 않음 |
| report completeness | total/truncated와 raw 연결 | report cap64·잘림 표시 코드 확인 | effect_demo.py | lifecycle/frontier·원본 hash/reference 전체 없음 | 보고서를 원본 bundle 대신 사용하지 않음 |
| local ledger와 v2 event 집합 대응 | correlation 집합 exact equality | 이번 회귀 검사·수정 | SyntheticRebindingCapture.envelope | v2에도 통째로 빠진 작업은 검출 불가 | empty/partial capture 주입; 별도 API completeness qualification |
| branch token one-shot | predecessor/token 재소비 금지 | 합성 prototype에서 보강 | SyntheticRebindingCapture.begin | native branch hook 없음 | 같은 predecessor·같은 token을 각각 재사용해 invalid 확인 |

local terminal의 `complete`만으로 native나 전체 transport가 complete하다고 쓰지 않는다.
한정된 observed endpoint, 전체 raw integrity, native qualification, 탐색 효과는 독립 층위다.

## P1−P0: transition retention의 가치

연구 질문은 같은 관찰·mutation 능력과 budget에서 **admission 변경**이 보안 관련 탐색을 개선하는가다.
관찰 자체의 추가 표현 능력은 별도 H-REP로 분리한다.

| 항목 | 사전 검토용 정의 |
| --- | --- |
| H-REP 표현 가설 | 같은 final key인 실행이라도 검증된 transition key가 다른 사례를 표현할 수 있다. generic 합성 테스트는 지지하지만 native 실현 여부는 미검증 |
| H10 탐색 가설 | final key 대신 transition key로 보존하면 동일 실행 budget에서 독립 평가한 security-relevant behavior class 도달 수가 증가한다 |
| 바뀌는 요소 | admission의 final-key 채널→transition-key 채널만; violation admission 공통 |
| 고정 조건 | 같은 qualified producer/profile·target/image·sentinel·input seeds·mutation/operator vocabulary·uniform parent/operator 구현·timeout·execution budget·resource class·oracle·evaluator |
| primary 지표 | 사전에 동결한 독립 behavior-class evaluator의 run별 unique class 수. reward key를 그대로 세는 값과 분리; evaluator/분류표 미정이면 실행 전 STOP |
| secondary 지표 | 공통 offline final/transition coverage, corpus size, raw/invalid/timeout율, replay-validated violation candidate rate, first candidate까지의 실행 수·전체 wall time |
| 지지 결과 | paired 반복에서 primary difference가 사전 최소 의미 효과를 넘고 불확실성 구간이 0보다 높음; native invalid/관찰 교란 차이로 설명되지 않음 |
| 지지하지 않음 | 키 수만 증가하고 독립 behavior class나 candidate 개선 없음; 결과 구간이 넓어 0 포함이면 불충분/미결정 |
| 반박 가능 결과 | 충분한 정밀도에서 사전 최소 의미 효과를 배제하거나 P1의 primary가 감소. 표현 가능성을 반박하는 것과 retention 이득을 반박하는 것을 구분 |
| 한계 | admission이 corpus와 이후 RNG 소비 경로를 바꿔 같은 RNG seed여도 같은 입력열이 아님. 이는 정책 효과 일부지만 완전 paired-input 비교가 아님. 새 상태가 자동으로 위험하지 않음 |

H-REP의 native 검증은 고정 case의 P0/P1 offline projection으로 먼저 한다. 그 뒤 closed-loop 정책 비교를
따로 해야 한다. 로그가 더 많다는 결과만으로 H10이나 취약점 성능 향상을 지지하지 않는다.

## P2−P1: operator adaptation의 가치

| 항목 | 사전 검토용 정의 |
| --- | --- |
| H21 탐색 가설 | 같은 P1 admission에서 binary new-transition 보상으로 operator를 선택하면 uniform보다 독립 behavior-class coverage가 높다 |
| 바뀌는 요소 | operator selection만 uniform→bounded weighted; weights 초기1/상한8, violation reward 없음 |
| 고정 조건 | H10의 조건 + 동일 transition schema/key·admission·초기 weights·parent uniform·operator no-op 규칙·reward 계산 및 적용 시점 |
| primary 지표 | H10과 같은 외부 behavior-class evaluator. evaluator version을 양 arm에 동일 적용 |
| secondary 지표 | operator별 attempt/no-op/reward·weight saturation, transition-key gain, replay-validated candidate rate, censored time-to-first, total step latency |
| 지지 결과 | 사전 frozen 반복에서 primary paired gain과 의미 효과를 충족하고 reward replay가 일치 |
| 지지하지 않음 | 높은 reward·높은 key 수만 있고 독립 behavior/candidate 이득 없음, seed별 방향 불일치 또는 넓은 구간 |
| 반박 가능 결과 | 충분한 정밀도에서 의미 효과 배제·성능 악화·특정 operator 편중으로 탐색 감소. reward replay 불일치는 효과 반박보다 infrastructure-invalid |
| 한계 | bounded weight도 exploration guarantee나 최적성을 뜻하지 않음. transition key 설계가 reward hacking/쉬운 상태 반복을 유도할 수 있음. 관찰 능력은 P1과 같음 |

## 실행 전 동결해야 할 공정 비교 프로토콜

1. Native observation qualification, 별도 policy-version 계약과 실행 승인이 먼저다. 이 문서로 실행하지 않는다.
2. target·지원 범위·independent behavior-class 분류표·primary metric·최소 의미 효과·confidence 방법·반복 수·budget을 결과 보기 전에 확정한다. 현재 이 수치들은 **미동결**이며 10월 26일 결과에 실험 효율을 넣지 않는다.
3. seed-inclusive execution budget을 primary로, 전체 wall-clock budget을 별도 sensitivity로 보고한다. target duration으로 controller·observer 비용을 대신하지 않는다.
4. paired RNG seeds와 counterbalanced arm 순서, fresh sandbox/process, 동일 instrumentation을 사용한다. 한 arm만 trace를 끄면 관찰 비용과 선택 효과가 섞인다.
5. started/invalid/timeout/rejected/failed/completed 모든 denominator를 보존한다. 중단 slot을 성공한 retry로 대체하지 않는다. infrastructure-invalid 자료는 원인별로 보존하고 invalid 차이 자체도 보고한다.
6. 공통 evaluator가 모든 raw를 독립 재계산한다. 과거 원본에 없는 v3 token을 만들어 승격하지 않는다. 관측이 없는 것을 negative로 넣지 않는다.
7. 탐색 단위 효과는 paired difference와 불확실성으로 보고한다. no-hit는 censored 관측이며 safety/동등성 증거가 아니다. 다중 secondary metric과 exploratory 분석은 명시한다.
8. 취약점 탐지 개선은 별도 동일 oracle·replay·root-cause adjudication이 뒷받침할 때만 주장한다. N05나 B0/B1/B3의 성공을 H10/H21 증거로 대체하지 않는다.

현재 상태: 프로토콜 문서 **완료**, 구체적 실행 freeze **미착수**, H10/H21 **미검증 가설**,
native comparison **미실행**. [결과 확정표](result-freeze-checklist.md)를 따른다.
