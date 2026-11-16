# 실험 영역 에이전트 규칙

root [AGENTS.md](../AGENTS.md)와 함께 따른다.

- 등록 실험의 실행 기준은 Git에 동결된 사전등록 파일(`preregistration/`)이고, 증거 기준은 raw + SHA-256 목록
  (`summaries/raw-manifest-*.sha256`)이다. 동결된 사전등록·등록 실험 설정·본실험 실행 SHA의 변경과 승인된 범위를 넘는
  실행·예산은 사람(지웅) 결정이다. 결과를 본 뒤 방법·지표·예산을 바꾸지 않는다.
- 실행 전에 experiment config, random seed, target 및 정확한 target version을 기록한다.
- InodeFence commit, execution budget(실행 수·시간·timeout 등), OS/architecture 및 주요 의존성 버전을 기록한다.
- 실패와 timeout도 데이터로 취급한다. 성공 결과만 선택해서 남기지 않는다.
- raw 결과를 수동 수정하지 않는다. 수정이 필요하면 원본을 보존하고 변환 과정과 이유를 기록한다.
- raw result는 paper conclusion이 아니다. 검증된 요약과 논문 해석을 구분한다.
- 서로 다른 host 결과를 무분별하게 하나의 formal dataset으로 혼합하지 않는다.
  환경 차이를 기록하고, 비교 가능성을 검증한 후 집계한다.
- 작은 요약의 provenance는 [summaries 규칙](summaries/README.md)을 따른다.
