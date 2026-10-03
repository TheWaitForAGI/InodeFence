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

완료된 bounded campaign은 `inodefence.campaign_export.export_campaign`으로 새 directory의
manifest.json/steps.jsonl에 기록할 수 있다. 기존 output은 덮어쓰지 않는다. Raw snapshots와
feedback decision은 분리된 field로 보존하며 manifest는 validated analysis가 아니다.
Exporter 환경을 실행 환경으로 해석하지 않는다. Source revision/실행 환경 provenance와
원본의 공유·보관 위치는 caller가 별도 기록해야 한다. Partial files가 있는 failed export는
완료 evidence로 취급하지 않는다.
