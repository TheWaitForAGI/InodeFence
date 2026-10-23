# 10월 26일 연구·구현 결과 확정표

**2026-10-23 KST 현재 확정 가능한 상태**다. 미래 10월 26일에 실행/승인된 것처럼 쓰지 않는다.
예약·백그라운드 연구·자동 재실행은 설정하지 않았다. 후속 증거가 없으면 아래 범위 그대로 26일에 사용한다.

| 항목 | 작업 상태 | 테스트 결과 | 근거 수준 | 확정/남은 조건 |
| --- | --- | --- | --- | --- |
| 두 branch·3c2487b·기존 문서 보존 | 완료 | 해당 없음 | 코드·자료 확인 | 두 branch 시작 SHA 같음; docs branch만 로컬 수정 |
| 실제 중간 증거 인정 조건 | 완료 | 해당 없음 | 코드·자료 확인 | research-hypotheses의 증거표; full snapshot 보장 없음 |
| H10/H21와 반박·공정 비교 프로토콜 | 완료 | 미실행 | 미검증 가설 | 구체적 evaluator/효과크기·반복/budget 미동결 |
| bounded synthetic 수집 prototype | 완료 | 신규18·focused94 통과 | 합성 검증 | native producer 아님 |
| native source-hook 타당성 분석 | 부분 완료 | 미실행 | 코드·자료 확인 | callback wrapper 후보 있음; 실제 bundled 분기 token 검증 필요 |
| native v3 producer | 차단 | 미실행 | 미검증 | hook·source/image 계약·독립 검토·명시 실행 승인 없음 |
| native v3 qualification | 차단 | 미실행 | 미검증 | native producer 완성 + 별도 frozen matrix·승인 필요 |
| 기존 v1 native 판정 | 완료(기록 정리) | 과거 실패 | 코드·자료 확인 | BLOCKED 유지; 이번 원본 재검산 아님 |
| 기존 v2 native 판정 | 완료(기록 정리) | 과거 실패(13/14) | 코드·자료 확인 | NOT_QUALIFIED 유지 |
| 과거 raw independent 재계산 | 차단 | 미실행 | 미검증 | primary/mirror raw 미확보 |
| 실제 P1−P0/P2−P1 효과 비교 | 미착수 | 미실행 | 미검증 가설 | producer qualification과 정책 freeze 뒤 별도 승인 |
| 비판 검토·발표 claim·인계 자료 | 완료 | 문서 검사 대상 | 코드·자료 확인 | novelty-and-threats와 handoff |
| canonical engineering validation | 완료 | 1,602 tests 및 Ruff/format/Pyright/environment/docs 통과 | 합성/기존 engineering 검증 | 실제 native v3 관측 증거 아님 |
| 규민 N05 실행 | 범위 밖 의존성 | 이번 미실행 | PR 자료 확인 | 구현 통과가 실행 승인 아님; 담당 결과만 이후 인용 |
| 주언 B0/B1/B3 | 범위 밖 의존성 | 이번 미실행 | PR 자료 확인 | final-state 비교가 transition 효과 증거 아님 |

## 26일 최종 제출 전 확인

- [x] 현재 결과와 기존 10월 22일 결과를 분리한다.
- [x] source/base SHA·branch·dirty 변경과 코드/문서 위치를 남긴다.
- [x] synthetic token은 synthetic이라고 표시하고 native provenance로 사용하지 않는다.
- [x] v1/v2 negative decision·기존 policy/oracle/reader를 변경하지 않는다.
- [x] 실제 native 관찰과 H10/H21 효과는 미검증으로 남긴다.
- [ ] 과거 raw archive 확보와 independent 재계산: 미확보면 차단으로 확정한다.
- [ ] native hook·manifest trust·image/source·fixtures·limits·failure injection을 독립 검토하고 별도 승인한다. 미완료면 native 미검증으로 확정한다.
- [ ] 지웅의 발표 claim 문구 확인: 이 문서는 전달 준비이며 메시지 발송/수신 확인이 아니다.

최종 실행 수·통과 수와 실패 기록은 [experiment-results](experiment-results.md), 코드 경로와
추가 근거는 [evidence-index](evidence-index.md), 전달 문구는 [handoff](handoff-to-jiwoong.md)를 따른다.
