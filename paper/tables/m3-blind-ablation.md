# 표 M3 — 자력 발견 blind-ablation 대조표

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
| 관련 PR | #151 (메커니즘·실제규모·blind 대조, main 머지 `d44d903`) |

arm 정의: `A3full` = `uniform-generic-m1-state-aware-escape-hardlink-v1`; `A3blind` =
`...-state-aware-escape-hardlink-blind-v1`(관찰 이름에서 EXTERNAL region 제외); `A1` = 무작위 바닥
(token-clean, state-aware 외부 주소지정 없음). search = `effect-feedback-v2-or-violation-v1-boundary-attempt-v1-adaptive-mutation-v1`.

## 대조표 (observed, raw step 로그 재집계)

| 셀 | seeds | 기록 step 수 | 자율 C1 hit (C1 ∧ contract_violated) |
| --- | --- | --- | --- |
| **A3full s11** (state-aware; scale-full·ablation 동일·결정론) | 11 | 416 (abort 전) | **21** (21건 모두 C1·C2·contract_violated 동시) |
| **A3blind s11** (identity-blind 대조) | 11 | 1475 | **0** |
| **A1 random floor** | 1–35 (35개) | 33,005 | **0** |
| A3full scale study | 1–35 (35개) | 41,494 | **s11만 21** (그 외 전 seed 0) |
| A3full 재현 | 36–65 (30개) | 34,585 | **0/30** |

합산: budget 1500·7.5.2에서 A3full 65 seed(1–65) 중 자율 C1을 내는 seed는 **정확히 s11 하나**다.
s11 run은 step 416에서 evidence-integrity 검사로 abort(returncode 1)하지만 21건의 hit는 **abort
이전**에 기록된 step이다(producer abort-drain). process returncode 1을 "발견 없음"으로 읽지 않는다.

## 읽는 법 (인과, rate 아님)

세 바닥(A3blind s11 = 0 · A1 random floor = 0) 대비 A3full s11 = 21이 보이는 것은 **"object-identity
관찰(feedback)이 없으면 도달 불가, 있으면 도달"**이라는 **인과**다. 이는 **rate 우위가 아니다**
(§5.3.3은 PENDING). 자율 트리거는 seed-rare이고 **blind 발견이 아니다**(퍼저는 외부 객체 이름을
관찰로 얻는다; 하드코딩 없음, §5.3.2).
