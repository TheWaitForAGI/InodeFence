# Raw 실험 결과

이 폴더는 실험에서 직접 나온 **가공 전 결과**의 논리적 위치다.

예:

- structured execution log
- timeout / failure 기록
- raw measurement
- campaign output

## 원칙

- raw 결과와 사람이 해석한 결론을 구분한다.
- 가능한 한 JSON/JSONL 같은 구조화 형식을 사용한다.
- 큰 자동 생성 데이터는 무조건 Git에 커밋하지 않는다.
- raw 파일을 수동 수정한 값을 논문 결과로 사용하지 않는다.

실제 Git 보존 정책은 repository ignore 정책과 experiment 문서를 함께 따른다.
