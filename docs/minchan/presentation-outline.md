# 10월 27일 발표용 6장 구성

> 10/24 갱신: 분석 HEAD `9e36e12`. 기존 6장 구성은 유지하고 아래 보완 사항을 적용한다.

담당 민찬, 전달 지웅. 연구 확정 기준일 10월 26일. 각 슬라이드에 source SHA `8d29982c`와 synthetic/native 구분을 유지한다.

| 장 | 핵심 메시지 | 사용할 그림·표 | 근거 | 발표 메모 |
| --- | --- | --- | --- | --- |
| 1. 왜 중간 상태인가 | 같은 최종 상태가 다른 중간 관계를 숨길 수 있다 | 보고서의 sentinel identity 개념 예 + 전체 구조도 | #79, transition model 계약 | 개념 예이며 실제 공격 발견이라고 소개하지 않음 |
| 2. P0/P1/P2에서 무엇이 달라지나 | retention과 operator 선택을 분리해서 비교한다 | 보고서 P0/P1/P2 표, diagrams 정책 그림 | #81/#82, scheduler code | P2는 관찰 능력 추가가 아니라 입력 분포 적응. 효율 향상은 미검증 |
| 3. node-tar에서 순서가 어려운 이유 | entry/body end와 fs 완료가 다르다 | 가상 sequence diagram + 과거 관측 0,1,3,2 표 | #80/#84/#87/#88, upstream v7.5.22 | 가상 timeline과 과거 실제 로그 요약을 별도 표기. timestamp≠causality |
| 4. v1/v2가 남긴 negative result | v1 ordered prefix 실패; v2 14조건 중 coverage 실패 | 14조건 축약표, duplicate-path 기대/실제 표 | #89/#90/#91, qualification `_summarize` | 13/14는 전체 PASS 아님. reader 오류와 contract coverage 부족을 구분 |
| 5. v3의 접근과 구현 경계 | removal→absence→creation + explicit dependency | v1→v2→v3 그림, composite 조건 | #100 당시 proposal, #111 현재 synthetic 구현 | v2 replacement를 재정의하지 않음. native producer 미구현 문구를 눈에 띄게 표시 |
| 6. 검증·선행연구·남은 과제 | engineering 검증과 연구 효과 주장을 분리한다 | ZIPDiff/Wormholes/LinkZard 비교 4행 + 완료/미검증 | evidence-index, focused 76 tests, experiment-results | 기존 연구도 feedback/link/order를 다룸. raw 확보·native token qualification·동일 budget 효과 비교가 후속 |

발표 수치는 [실험 결과](experiment-results.md)의 최종 실행 기록만 사용한다. 과거 PR의 테스트 수를 현재 통과 수로 쓰지 않는다. canonical 검증의 환경 차단이 있으면 숨기지 않는다. native 성과가 10월 26일까지 확보되지 않아도 구조·실패 분석·합성 검증을 결과로 제출할 수 있다.

10월 23일 보완: 2장에는 [H10/H21와 반박 조건](research-hypotheses.md)을 넣고, 5장은
“generic v3 + target-free capture prototype / native hook 없음”으로 업데이트한다. 6장에는
[예상 반박](novelty-and-threats.md)의 계측 교란·누락·오라클 한계와 [26일 확정표](result-freeze-checklist.md)를
사용한다. 76/1,584는 22일 기록이며 23일 검증 수치는 experiment-results의 별도 절로 교체한다.

10/24 보완: 3·5장에 현재 schema2 출력의 entry/start 정렬·cap64·거부 step의 관찰 오류를 설명한다.
팀 native demo 보고와 이번 합성 검증을 분리한다. 팀 수치는 #133/LOG 인용이며 원본 독립 검증 전이다.
P0-2(발표 우선순위)와 P0/P1/P2(연구 정책)를 구분한다. H10/H21은 여전히 미검증이다.
이번 수정은 v2 trace 대조 시 누락 operation 거부와 prototype token one-shot 검증이며 native hook이 아니다.
