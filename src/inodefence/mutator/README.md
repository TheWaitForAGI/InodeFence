# case 구조 변경

## 이 폴더는 무엇인가

기존 archive case의 entry 구조를 바꾸는 책임을 둔다.

## 입력

기존 ArchiveCase와 재현 가능한 mutation 설정(계획).

## 출력

변형된 ArchiveCase(계획).

## 책임

예: 두 entry 순서를 바꾸거나 파일 경로를 변경한다. type, link target, 추가·삭제·복제와 dependency도 설계 범위다.

## 하지 않는 것

초기 seed 생성, extractor 실행, 특정 CVE recipe 하드코딩.

## 다른 모듈과의 연결

[generator](../generator/README.md)의 초기 case 또는 [feedback](../feedback/README.md)의 corpus 선택을 입력으로 받고 이후 TAR Builder에 전달한다.

## 현재 상태

빈 __init__.py만 있다. Mutation은 개발 Layer 4 계획이다.

## 파일 배치 규칙

generic operator를 작은 단위로 둔다. target/CVE별 실행·재현 로직을 넣지 않는다.
