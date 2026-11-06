# 그림 사양 — M3 어휘 제거 대조 (사양 + 렌더됨)

**렌더됨:** 이 사양으로 실제 그림을 렌더했다 — PNG [`m3-blind-ablation.png`](m3-blind-ablation.png),
생성 소스 [`render_m3_blind_ablation.py`](render_m3_blind_ablation.py). 결과 그림은 Results
[§5.3](../sections/06-results.md)에 삽입돼 있다. 아래는 그 그림의 사양·데이터 근거다(observed 수치 그대로).

이 파일의 데이터는 전부 [표 M3](../tables/m3-blind-ablation.md)·
[자력발견 요약](../../experiments/summaries/node-self-discovery-mechanism-v1.md)의 observed 수치이며,
그림을 그릴 때 이 수치 그대로 써야 한다(figures 규칙: Figure → analysis input → experiment result →
experiment config → commit 추적 가능).

## 의도한 그림

node-tar 7.5.2, budget 1500에서 세 비교 셀의 **자율 C1 hit 수**를 나타내는 막대그래프. 외부 객체 이름을 어휘에 넣은
A3full에서만 관찰됐다는 **이름 획득 조건 대조**를 보인다. 판정은 **이름 획득 조건의 관찰(피드백 인과 미입증)**이다.
*(구: "발견이 관찰(feedback)이 있을 때만 일어난다는 인과", 2026-11-03 정정)*
(2026-11-03 정정: 이 어휘 제거 대조는 피드백이 아니라 **어휘**를 통제한 실험이다. 관찰된 것은 외부 객체 이름을 어휘에 넣은 조건에서 자율 C1이 나왔고 그 조건 밖에서는 관찰되지 않았다는 것이다(구조적 불가로 단정하지 않는다). 이는 (st_dev, st_ino) retention·스케줄링 피드백의 기여를 보인 것이 아니며, 그 기여는 어휘를 맞춘 R/D/S-u 비교(research-questions v2 H-A)로 미분리다. 수치·서술은 보존한다. 상세: §5.3.2 정정.)
수치는 그대로 두고, 2026-11-06에 PNG와 렌더 스크립트의 제목·캡션·x축 라벨을 이 정정에 맞췄다.

## 데이터 (observed, 그대로 사용)

| 막대(arm·seed) | 기록 step 수 | 자율 C1 hit |
| --- | --- | --- |
| A3full s11 (외부 이름 어휘 포함) | 416 (abort 전) | 21 |
| A3blind s11 (외부 이름 제외) | 1475 | 0 |
| A1 token-clean 어휘 (표 M3의 "A1 random floor", seed 1–35 합산, 이름 철자 불가) | 33,005 | 0 |

## 인코딩 지침

- y축 = 자율 C1 hit 수(0–25 권장). x축 = 세 막대.
- 각 막대 아래/위에 기록 step 수를 주석으로 병기(0 hit가 "실행을 적게 해서"가 아님을 보이기 위해:
  A3blind 1475 step·A1 33,005 step에도 0).
- 캡션에 반드시 포함: (1) 이는 **이름 획득 조건의 관찰(피드백 인과 미입증)**이고, 어휘를 맞추지 않아 retention·effect
  피드백 기여는 R/D/S-u로 미분리이며, **rate 우위가 아니다**, (2) 21 hit는 한 seed의 1 lineage이고 막대마다 분모가 다르다,
  (3) 자율 트리거는 **seed-rare**(65 seed 중 s11 하나), (4) **blind 발견이 아니다**.
  *(구: (1) "이는 인과(없으면 도달 불가)", 2026-11-03 정정)*
- 그림 안 문구는 영문이다(렌더 환경에 한글 폰트가 없다). 한글 Ledger 문구는 표 M3와 §5.3 본문 캡션에 둔다.
- 색/스타일은 저장소 정식 figure 생성 단계에서 정하되 위 수치·캡션 요건은 불변.

## 렌더 메모

정식 figure는 experiment 결과에서 재생성 가능한 방식(예: matplotlib 스크립트)으로 만들고, 입력은
위 표/요약의 observed 수치로 고정한다. raw step 로그는 저장소 밖(`~/inodefence-evidence/`,
git-ignore)에 있으므로, 그림 생성 스크립트는 요약의 재집계 수치를 입력으로 받는다.
