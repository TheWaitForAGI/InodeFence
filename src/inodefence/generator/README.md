# 초기 case 생성

## 이 폴더는 무엇인가

작고 정상적인 초기 archive case를 만드는 책임을 둔다.

## 입력

초기 case 구성과 재현 가능한 생성 설정(계획).

## 출력

ArchiveCase(계획).

## 책임

예: notes/ 디렉터리와 notes/readme.txt 파일이 있는 이해하기 쉬운 입력을 만든다.

## 하지 않는 것

기존 case 변형, extractor 실행, CVE-specific payload 생성.

## 다른 모듈과의 연결

case는 [model](../model/README.md)로 표현하고 [mutator](../mutator/README.md)에 전달한다. TAR Builder는 별도 직렬화 책임이며 배치 위치는 [architecture](../../../docs/research/design/architecture.md)에서 미확정으로 표시한다.

## 현재 상태

빈 __init__.py만 있고 생성기와 TAR Builder는 미구현이다.

## 파일 배치 규칙

초기 생성 정책을 둔다. 직렬화와 mutation 정책을 섞지 않고 Builder의 실제 파일 배치는 구현 단계에서 합의한다.
