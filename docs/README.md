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

현재 능력의 단일 기준은 [STATUS](STATUS.md)의 **Capability Ledger**다(능력 → 증거 수준 → 증거 포인터).
할 일은 [BACKLOG](BACKLOG.md)의 마일스톤 M1~M4로 관리한다. 날짜는 문서에 박제하지 않는다.

## 파일 배치 규칙

빠른 이해는 START_HERE, 현재 능력은 STATUS의 Capability Ledger, 용어는 [GLOSSARY](GLOSSARY.md),
큰 결정은 [DECISIONS](DECISIONS.md)에 둔다. 과거 감사·자격 기록은 [archive 안내](archive/README.md)가
"동결 기록(현재 제약 아님)"으로 정리한다. 새 감사·계획·handoff 문서는 만들지 않는다.

| 파일 | 무엇을 적는가 |
| --- | --- |
| [STATUS](STATUS.md) | **Capability Ledger**(현재 능력·증거)와 마일스톤. 단일 기준 |
| [BACKLOG](BACKLOG.md) | 마일스톤 아래 할 일과 상태(대기/진행/완료/막힘). 맨 위부터 집는다 |
| [LOG](LOG.md) | 실제로 무엇을 언제 돌려 어떤 결과였는지 한 줄씩. 관찰과 추론을 구분한다 |
| [WORKLOG](WORKLOG.md) | 자율 루프가 끝낸 브랜치 목록. 머지는 PR·CI·verifier 통과 후 루프가 한다(D035) |
| [MIDTERM_GOALS](MIDTERM_GOALS.md) | 중간발표 배경 문서. 현재 기준은 STATUS Ledger |
| [archive](archive/README.md) | 과거 리비전의 감사·자격 기록이 동결 기록임을 선언 |
