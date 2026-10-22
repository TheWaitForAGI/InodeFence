# 비교실험으로 식별할 수 있는 것

결과 상태: **B/A historical comparisons 및 native P-policy effectiveness는 NOT_RUN**.
아래 ‘식별’은 필요한 조건이 충족된 미래 실험의 해석 범위다. 효과의 존재·방향·크기를
추정한 결과가 아니다. Claim: R2-C08/R2-C09/R2-C10/R2-C16/R2-C20.
기준은 [baseline-and-ablation-v1](../../../benchmarks/baseline-and-ablation-v1.md),
[evaluation-protocol-v1](../../../benchmarks/evaluation-protocol-v1.md),
[research-questions](../../../design/research-questions.md)다.

## 정책 정의

| 정책 | Parent / retention | 진단과 탐색의 관계 |
| --- | --- | --- |
| B0 = unretained multi-step random walk | 초기 benign seed 하나를 선택한 뒤 직전 실행 child를 다음 parent로 사용; growing corpus 없음 | 상태/위반 진단은 기록하되 다음 선택에 쓰지 않음. Rejected/failed child도 다음 parent가 됨 |
| B1 = full state-key-only admission | 새 full v3 state key를 만든 case를 보존; retained parents에서 균등 선택 | violation novelty는 진단용. Full key에 identity/effect 정보가 이미 있음 |
| B3 = state-or-violation novelty admission | 새 full state key **또는** 새 violation fingerprint를 만든 case를 보존; retained parents에서 균등 선택 | state/fingerprint novelty가 admission에 영향을 줌 |

B0는 seed에서 한 번만 변형하는 baseline이 아니다. 여러 mutation을 누적할 수 있다.
B1은 path-only baseline이 아니다. B1/B3의 선택 **규칙**은 균등 선택으로 같지만,
admission 결과가 다르면 parent pool 및 실제 선택 분포는 달라진다.
Parent 분포 변화는 정책 개입으로 유도되는 탐색 과정의 일부다.

## Contrast별 식별 대상과 한계

| Contrast | 의도적으로 바꾸는 것 | 적절히 통제한 실험에서 물을 수 있는 것 | 잔존 정보 / 식별할 수 없는 것 | 현재 상태 |
| --- | --- | --- | --- | --- |
| B3 vs B0 | novelty retention과 retained-parent 선택을 직전-child walk로 대체 | 동일 조건에서 **정책 전체**가 state/contract 탐색·비용에 미치는 차이 | retention, parent distribution, RNG 소비·진화 경로가 함께 달라짐. Pure object-identity 또는 external-effect 신호 하나의 인과 효과는 분리 못 함 | 구현·engineering TESTED; 실제 비교 NOT_RUN |
| B3 vs B1 | violation fingerprint novelty admission의 추가 여부 | full state-key admission 위에 violation novelty를 더한 정책의 marginal effect | B1도 identity/effect full key를 사용. 효과가 있더라도 특정 C1/C2 신호만의 기여가 아님. 추가 admission 이후 pool 변화는 개입의 매개 과정 | 구현·engineering TESTED; 실제 비교 NOT_RUN |
| B3 FULL vs A1 | feedback key의 `identity_groups`만 제거 | explicit identity-group key field의 제한된 marginal contribution | regular nlink, object 정보, external effects, **C1 fingerprints와 B3 OR 경로가 남음**. 모든 identity 정보 제거가 아님 | 구현·projection tests; target 효과 NOT_RUN |
| B3 FULL vs A2 | key의 `external_effects` label만 제거 | changed-field label의 제한된 marginal contribution | sentinel object/content digest, identity groups, **C2 fingerprints와 OR 경로가 남음**. 모든 effect 정보 제거가 아님 | 구현·projection tests; target 효과 NOT_RUN |
| B3 정상 mutation vs A3 | reorder slot을 동일 operator-internal RNG draw를 소비하는 executed no-op로 대체 | 정해진 grammar에서 explicit reorder/swap slot을 사용할 수 있는 정책의 marginal contribution | insertion/duplicate가 만드는 order variation은 남음. No-op도 실행 예산에 포함. 모든 entry-order 효과 제거가 아님 | 구현·no-reorder tests; target 효과 NOT_RUN |
| P1 vs P0 | 같은 uniform mutation에서 final-state retention을 transition-key retention으로 대체; violation OR는 양쪽 유지 | **qualified native observation/version** 조건에서 transition retention 정책의 추가 탐색 가치 | 표현/key 공간·parent pool이 달라짐. Transition 수 증가 자체는 보안 효과 아님. Observation 신뢰성·perturbation 검증을 대체하지 못 함 | generic synthetic TESTED; native effectiveness NOT_RUN / gate blocked |
| P2 vs P1 | 동일 transition retention·uniform parent에서 uniform operator를 bounded adaptive scheduler로 대체 | 같은 retention 아래 operator adaptation 정책의 marginal effect | reward는 binary new-transition key, violation reward 아님. Scheduler가 raw transition/key 증가를 선호해도 취약점 증가로 해석 불가 | generic synthetic TESTED; native effectiveness NOT_RUN / gate blocked |

P0/P1/P2는 B0/B1/B3의 다른 이름이 아니다. 위 P 대비는 canonical v1 의미를 요약한다.
Native v1은 `BLOCKED_NATIVE_OBSERVATION`, v2는
`V2_NATIVE_EFFECT_OBSERVATION_NOT_QUALIFIED`다. V3 synthetic composite는 이 판정이나 P-policy ID를
대체하지 않는다. Native 비교를 제안하려면 observation/feedback/policy version을 별도로 고정해야 한다.
[STATUS](../../../../STATUS.md), [transition feedback](../../../design/transition-feedback-v1.md),
[scheduler](../../../design/transition-mutation-scheduler-v1.md).

## 조건을 같게 유지한다는 뜻

비교 블록은 source revision, exact target/version/image/options, Linux filesystem/runtime,
sentinel layout/content/mode, benign initial corpus IDs/order, finite mutation grammar와
protected-component vocabulary, timeout/resource limits, oracle, seed-inclusive all-status execution budget을
공유해야 한다. Arm이 다르게 사용하는 admission key는 달라도 분석은 **같은 full state/fingerprint**로 한다.
Target version 차이는 정책 효과 비교와 별도로 stratify하며 candidate affected/fixed 확인은 같은 입력 replay다.

같은 RNG seed는 paired trial의 재현 조건이지 같은 parent·mutation·TAR를 보장하지 않는다.
Policy에 따라 pool과 RNG 소비가 달라진다. 실제 parent/operator/input lineage를 보존하고 schedule RNG는
campaign RNG와 분리해야 한다. 한 arm의 발견 입력을 다른 arm의 seed로 넣지 않는다.
Seed-phase hit는 benchmark/setup anomaly이며 mutation-origin rediscovery로 세지 않는다.
[Canonical 통제 및 randomness](../../../benchmarks/baseline-and-ablation-v1.md).

## 보고할 지표와 분모

| 보고 항목 | 필요한 정의 | 금지되는 대체 |
| --- | --- | --- |
| 실행 회계 | scheduled/started/complete/failed/invalid/STARTED/missing, 실제 step 수와 모든 target status | NOT_RUN 또는 유실 prefix를 정상 zero-hit로 입력 |
| 탐색 범위 | 모든 arm에서 같은 full v3 signature와 generic fingerprint 수; budget/complete 분모 병기 | arm마다 다른 projected key count를 우열의 공통 척도로 사용 |
| 첫 contract 관측 | 원 campaign의 1-based index; generic observation임을 표시 | first confirmed rediscovery와 동일시 |
| confirmed known-class rediscovery | benign-seed mutation lineage + generic raw evidence + exact affected 3/3 / fixed 0/3 + human root cause | 고정 positive-control 5/5나 자동 token을 발견률로 사용 |
| no-hit / pending | valid complete no-hit만 budget에서 right-censored; unresolved class는 pending, infra invalid 별도 | no-hit에 budget-end 가상 hit를 주거나 성공 run만 median 계산 |
| 시간·메모리·보존 비용 | full-step timing 정의 및 제외 구간, actual raw bytes, fresh controller process-lifetime VmHWM | target duration을 전체 throughput으로, memory limit을 측정값으로, controller HWM을 target memory로 표기 |

모든 정책 결과가 미실행이므로 현재 그래프·효과 크기·유의성·예상 승자를 작성하지 않는다.
향후 5개 seed exploratory pilot이 있어도 실제 per-seed 분포와 실패를 기술하는 범위이며
formal superiority나 일반적 인과 법칙을 자동 입증하지 않는다.
[평가 지표와 censoring 정의](../../../benchmarks/evaluation-protocol-v1.md).

## 인과 주장에 대한 답

**B0/B1/B3만으로 pure filesystem identity/effect feedback의 인과적 가치를 입증할 수 없다.**
B3−B0는 whole-policy 개입이고 B3−B1은 violation novelty admission 개입이다.
A1/A2도 일부 field만 제거하므로 남은 신호가 효과를 대체할 수 있다. Null result는 해당 field의
추가 가치가 보이지 않았다는 한정 결과일 수 있으며 identity/effect 전체의 무용성을 뜻하지 않는다.

더 좁은 정보 기여를 묻는 추가 비교는 encoding과 중복 신호, oracle/진단/feedback의 경계를 먼저
정의하는 **새 설계 과제**다. 이번 계약은 path-only arm이나 새 ablation을 추가·구현·승인하지 않는다.
그 비교가 없어도 B0/B1/B3 정책 효과라는 RQ2는 유효한 질문으로 유지된다.
