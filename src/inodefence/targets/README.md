# extractor 실행 경계

## 이 폴더는 무엇인가

실제 extractor의 실행 차이를 adapter로 격리한다.

## 입력

빌드된 TAR, 실행 sandbox와 target 설정(계획).

## 출력

ExecutionResult와 실행 후 관찰할 sandbox 상태(계획).

## 책임

예: target마다 다른 명령·옵션을 공통 실행 경계 안에서 처리한다.

## 하지 않는 것

generic mutation, 계약 판정, corpus 선택.

## 다른 모듈과의 연결

[observer](../observer/README.md)가 실행 전후 상태를 기록한다. 공통 표현은 [model](../model/README.md), target 순서는 [architecture](../../../docs/research/design/architecture.md)를 따른다.

## 현재 상태

빈 __init__.py만 있다. node-tar, oras-go, 일정이 허용하면 GNU tar 순서가 계획이다.

## 파일 배치 규칙

target별 명령·버전·실행 옵션과 필요한 instrumentation은 여기 둔다. 특정 target 처리를 generic 모듈에 넣지 않는다.
