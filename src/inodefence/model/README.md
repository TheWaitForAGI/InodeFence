# 공통 데이터 모델

## 이 폴더는 무엇인가

모듈이 주고받을 case와 결과의 표현을 위한 위치다.

## 입력

entry 내용·관계·순서, 실행 기록과 관찰 자료(계획).

## 출력

ArchiveEntry, ArchiveCase부터 정의할 공통 표현(계획).

## 책임

예: notes.txt 파일 entry의 경로와 내용을 실행 없이 표현한다.

## 하지 않는 것

TAR 생성 정책, extractor 실행, mutation, 보안 판정.

## 다른 모듈과의 연결

[architecture의 데이터 흐름](../../../docs/research/design/architecture.md)에서 각 모델의 소비자를 본다.

## 현재 상태

이번 작업에서 README만 추가했다. Python 패키지와 모델은 미구현이다. 첫 구현 대상은 [STATUS](../../../docs/STATUS.md)의 ArchiveEntry와 ArchiveCase다.

## 파일 배치 규칙

모델 구현 시 필드 의미와 제약을 docstring과 관련 design 문서에 남긴다. target별 실행 옵션은 넣지 않는다.
