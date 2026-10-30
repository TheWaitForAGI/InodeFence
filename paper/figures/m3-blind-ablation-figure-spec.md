# 그림 사양 — M3 blind-ablation 대조 (렌더 전 사양)

이 파일은 **렌더된 이미지가 아니라 그림 사양**이다. 아래 데이터는 전부 [표 M3](../tables/m3-blind-ablation.md)·
[자력발견 요약](../../experiments/summaries/node-self-discovery-mechanism-v1.md)의 observed 수치이며,
그림을 그릴 때 이 수치 그대로 써야 한다(figures 규칙: Figure → analysis input → experiment result →
experiment config → commit 추적 가능).

## 의도한 그림

node-tar 7.5.2, budget 1500에서 세 비교 셀의 **자율 C1 hit 수**를 나타내는 막대그래프. 발견이
**관찰(feedback)이 있을 때만** 일어난다는 인과를 한눈에 보인다.

## 데이터 (observed, 그대로 사용)

| 막대(arm·seed) | 기록 step 수 | 자율 C1 hit |
| --- | --- | --- |
| A3full s11 (identity 관찰 O) | 416 (abort 전) | 21 |
| A3blind s11 (identity 관찰 X) | 1475 | 0 |
| A1 random floor (seed 1–35 합산) | 33,005 | 0 |

## 인코딩 지침

- y축 = 자율 C1 hit 수(0–25 권장). x축 = 세 막대.
- 각 막대 아래/위에 기록 step 수를 주석으로 병기(0 hit가 "실행을 적게 해서"가 아님을 보이기 위해:
  A3blind 1475 step·A1 33,005 step에도 0).
- 캡션에 반드시 포함: (1) 이는 **인과**(없으면 도달 불가)이지 **rate 우위가 아니다**, (2) 자율
  트리거는 **seed-rare**(65 seed 중 s11 하나), (3) **blind 발견이 아니다**.
- 색/스타일은 저장소 정식 figure 생성 단계에서 정하되 위 수치·캡션 요건은 불변.

## 렌더 메모

정식 figure는 experiment 결과에서 재생성 가능한 방식(예: matplotlib 스크립트)으로 만들고, 입력은
위 표/요약의 observed 수치로 고정한다. raw step 로그는 저장소 밖(`~/inodefence-evidence/`,
git-ignore)에 있으므로, 그림 생성 스크립트는 요약의 재집계 수치를 입력으로 받는다.
