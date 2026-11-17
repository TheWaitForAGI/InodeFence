# EXP-2 holdout dense 지표 (탐색, effectiveness 아님)

대상 node-tar 7.4.4, k=5, budget 2000. 등록 seed 블록 160, 분석 블록 160, 미완주 제외 0(없음).

| arm | 셀별 새 키 평균(온전한 trace 기준) | 셀별 새 키 중앙값(온전한 trace 기준) | arm 안 고유 키(온전한 trace 기준) | rejected 비율 | 관찰 실패 종류별 step 수(1000 step당, 합계 아님) | feedback_eligible=false 비율 |
| --- | --- | --- | --- | --- | --- | --- |
| R | 4.49 | 4 | 8 | .358 | malformed_identity 432(1.37/1000); operation_correlation_conflict 2481(7.86/1000) | .013 |
| D | 4.22 | 4 | 8 | .506 | malformed_identity 305(0.96/1000); operation_correlation_conflict 1481(4.67/1000) | .009 |
| S-u | 4.59 | 5 | 8 | .373 | incomplete_flush 1(0.00/1000); malformed_identity 353(1.12/1000); operation_correlation_conflict 2111(6.72/1000) | .011 |
