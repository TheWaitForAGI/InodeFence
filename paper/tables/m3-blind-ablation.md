# 표 M3 — 자력 발견 어휘 제거 대조표

> 렌더된 그림: [m3-blind-ablation.png](../figures/m3-blind-ablation.png) (생성 소스 [`render_m3_blind_ablation.py`](../figures/render_m3_blind_ablation.py))

M3(§5.3)의 근거표다. hit = **step에서 `oracle.C1` AND `feedback.contract_violated`가 모두 참.**
모든 수치는 raw step 로그(`*.steps.jsonl`)를 재현 가능한 변환으로 다시 세어 얻은 것이다(수동으로
지어내지 않음).

## Provenance

| 항목 | 값 |
| --- | --- |
| target | node-tar 7.5.2 (image `inodefence-node-tar-effect:7.5.2`) — 영향(affected) 릴리스 |
| mode / jobs | `demo-historical`, jobs 3 |
| budget | 1500 (campaign당) |
| raw 위치 | `~/inodefence-evidence/{m3-scale-full, m3-ablation, m3-repro}/` (저장소 밖, git-ignore; 각 `matrix.json`에 provenance) |
| validated summary | [node-self-discovery-mechanism-v1](../../experiments/summaries/node-self-discovery-mechanism-v1.md) |
| 관련 PR | #151 (메커니즘·실제규모·어휘 제거 대조, main 머지 `d44d903`) |

arm 정의: `A3full` = `uniform-generic-m1-state-aware-escape-hardlink-v1`; `A3blind` =
`...-state-aware-escape-hardlink-blind-v1`(관찰 이름에서 EXTERNAL region 제외); `A1` = 무작위 바닥
(token-clean, state-aware 외부 주소지정 없음). search = `effect-feedback-v2-or-violation-v1-boundary-attempt-v1-adaptive-mutation-v1`.

## 대조표 (observed, raw step 로그 재집계)

| 셀 | seeds | 기록 step 수 | 자율 C1 hit (C1 ∧ contract_violated) |
| --- | --- | --- | --- |
| **A3full s11** (state-aware; scale-full·ablation 동일·결정론) | 11 | 416 (abort 전) | **21** (21건 모두 C1·C2·contract_violated 동시) |
| **A3blind s11** (어휘 제거 대조) | 11 | 1475 | **0** |
| **A1 random floor** | 1–35 (35개) | 33,005 | **0** |
| A3full scale study | 1–35 (35개) | 41,494 | **s11만 21** (그 외 전 seed 0) |
| A3full 재현 | 36–65 (30개) | 34,585 | **0/30** |

합산: budget 1500·7.5.2에서 A3full 65 seed(1–65) 중 자율 C1을 내는 seed는 **정확히 s11 하나**다.
s11 run은 step 416에서 evidence-integrity 검사로 abort(returncode 1)하지만 21건의 hit는 **abort
이전**에 기록된 step이다(producer abort-drain). process returncode 1을 "발견 없음"으로 읽지 않는다.

## 읽는 법 (이름 획득 조건의 대조; 피드백 인과·rate 아님)

판정은 **이름 획득 조건의 관찰(피드백 인과 미입증)**이다. 세 셀은 외부 객체 이름이 mutation 어휘에 있느냐가 다르다.
A3full s11 = 21은 이름을 어휘에 넣은 조건의 관찰이고, 이름을 뺀 A3blind s11 = 0과 이름을 철자할 수 없는 A1 = 0은 그 조건
밖의 미관찰이다. "A1 random floor"는 기존 셀 이름이다. A1도 feedback retention 탐색을 쓰므로 탐색 자체가 무작위라는 뜻은
아니다([verdict v2](../../experiments/summaries/m3-powered-matched-verdict-v2.md) Arms). 어휘 미통제라 retention·effect 피드백 인과는
미입증이며, 그 기여는 어휘를 맞춘 R/D/S-u 비교로 아직 분리되지 않았다. 이는 **rate 우위도 아니다**(§5.3.3 powered 판정: 매칭
Wilson CI 미분리). 21 hit는 한 seed의 1 lineage이고 셀마다 분모(step 수)가 다르다(§5.3.1). 자율 트리거는 이 그림의 budget
1500·seed 1–65에선 s11 하나(seed-rare)이고 powered 런의 신규 disjoint seed s101에서도 관찰됐지만, 동일 어휘 통제가 없으므로
피드백 인과의 강화는 아니다. **blind 발견이 아니다**(퍼저는 외부 객체 이름을 관찰로 얻는다; oracle·feedback에 대상 경로·정답 seed 없음, §5.3.2) *(구: "하드코딩 없음", 2026-11-06 범위 정정)*.

*(구: "object-identity 관찰(feedback)이 없으면 도달 불가, 있으면 도달"이라는 인과, 2026-11-03 정정을 2026-11-06 본문에 반영.)*

(2026-11-03 정정: 이 어휘 제거 대조는 피드백이 아니라 **어휘**를 통제한 실험이다. 관찰된 것은 외부 객체 이름을 어휘에 넣은 조건에서 자율 C1이 나왔고 그 조건 밖에서는 관찰되지 않았다는 것이다(구조적 불가로 단정하지 않는다). 이는 (st_dev, st_ino) retention·스케줄링 피드백의 기여를 보인 것이 아니며, 그 기여는 어휘를 맞춘 R/D/S-u 비교(research-questions v2 H-A)로 미분리다. 수치·서술은 보존한다. 상세: §5.3.2 정정.) 이 표의 세 셀은 어휘(이름 포함 여부)가 다른 셀이므로, 읽는 법은 "이름 획득 조건의 대조"다.
