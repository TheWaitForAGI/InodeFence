# 프로젝트 문서 입구

## 이 폴더는 무엇인가

처음 읽을 안내, 현재 상태, 용어, 결정 기록과 연구 문서를 연결한다.

## 입력

프로젝트의 합의된 범위와 작업 상태.

## 출력

작업에 필요한 문서로 가는 탐색 경로.

## 책임

[START_HERE](START_HERE.md) → [STATUS](STATUS.md) → [AGENTS](../AGENTS.md) 순서로 읽도록 안내한다.

## 하지 않는 것

하위 설계의 긴 설명 복사나 raw 결과 저장.

## 다른 모듈과의 연결

[research](research/README.md)는 연구 문서, [소스 안내](../src/inodefence/README.md)는 모듈 지도다. [TAR baseline 예제](examples/tar-baseline.md)는 작은 archive의 생성·extraction·filesystem 관찰 방법을 설명한다.

## 현재 상태

입구 문서와 연구 설계가 있다. 구현 단계는 STATUS를 기준으로 한다.

## 파일 배치 규칙

빠른 이해는 START_HERE, 진행 상태는 STATUS, 용어는 [GLOSSARY](GLOSSARY.md), 큰 결정은 [DECISIONS](DECISIONS.md)에 둔다.

중간발표 기간의 작업 기록은 세 파일로 나눈다. 새 감사·계획·handoff 문서는 만들지 않는다.

| 파일 | 무엇을 적는가 |
| --- | --- |
| [MIDTERM_GOALS](MIDTERM_GOALS.md) | 11/2 목표(P0-1~P0-5)와 완료 판정 기준. 자주 바뀌지 않는다 |
| [BACKLOG](BACKLOG.md) | 할 일 순서와 상태(대기/진행/완료/막힘). 맨 위부터 집는다 |
| [LOG](LOG.md) | 실제로 무엇을 언제 돌려 어떤 결과였는지 한 줄씩. 관찰과 추론을 구분한다 |
| [WORKLOG](WORKLOG.md) | 자율 루프가 끝낸 브랜치 목록. 사람이 머지 여부를 정한다 |
