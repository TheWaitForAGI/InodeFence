# 상태 선택과 corpus

## 이 폴더는 무엇인가

관찰 상태가 탐색에 interesting한지 평가하고 입력을 보존·선택한다.

## 입력

ArchiveCase, StateSnapshot, ViolationResult와 기존 corpus 상태(계획).

## 출력

StateSignature, 입력 보존 여부와 다음 mutation 입력(계획).

## 책임

예: 처음 본 identity 관계를 만든 case를 남겨 다음 구조 변경에 사용한다.

## 하지 않는 것

Security Contract 자체 정의, 모든 새 상태를 취약점으로 판정하기.

## 다른 모듈과의 연결

[observer](../observer/README.md)와 [oracle](../oracle/README.md)의 서로 다른 결과를 활용해 [mutator](../mutator/README.md)에 case를 돌려준다.

## 현재 상태

빈 __init__.py만 있다. signature 정규화와 interesting 기준은 미확정이며 개발 Layer 5 계획이다.

## 파일 배치 규칙

상태 표현, corpus 보존·선택 책임을 둔다. corpus의 실제 저장 위치와 API는 이번 문서에서 확정하지 않는다.
