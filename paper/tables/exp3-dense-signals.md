# EXP-3 train dense 지표 (탐색, effectiveness 아님)

대상 node-tar 7.5.2, k=5, budget 2000. 등록 seed 블록 20, 분석 블록 20, 미완주 제외 0(없음).

| arm | 셀별 새 키 평균(온전한 trace 기준) | 셀별 새 키 중앙값(온전한 trace 기준) | arm 안 고유 키(온전한 trace 기준) | rejected 비율 | 관찰 실패 종류별 step 수(1000 step당, 합계 아님) | feedback_eligible=false 비율 |
| --- | --- | --- | --- | --- | --- | --- |
| R | 4.37 | 4 | 6 | .362 | malformed_identity 59(1.55/1000); operation_correlation_conflict 291(7.66/1000) | .013 |
| D | 4.05 | 4 | 8 | .503 | malformed_identity 54(1.35/1000); operation_correlation_conflict 200(5.00/1000) | .009 |
| S-u | 4.58 | 5 | 6 | .358 | malformed_identity 44(1.16/1000); operation_correlation_conflict 206(5.42/1000) | .009 |
