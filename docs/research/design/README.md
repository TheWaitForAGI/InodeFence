# 설계 문서

## 이 폴더는 무엇인가

범위, 계약, 아키텍처와 환경의 합의된 기준을 둔다.

## 입력

연구 질문, 선행연구 비교와 팀 결정.

## 출력

구현과 평가가 따라야 할 책임 경계.

## 책임

상세 구조는 [architecture](architecture.md), 보안 규칙은 [security-contracts](security-contracts.md)를 canonical source로 유지한다.

## 하지 않는 것

설계 후보를 구현된 API로 표현하기.

## 다른 모듈과의 연결

[범위](project-scope.md), [연구 질문](research-questions.md), [위협 모델](threat-model.md), [선행연구 포지셔닝](related-work-positioning.md), [환경](development-environment.md).

## 현재 상태

Layer 1 설계가 마련되어 있다. 데이터 모델 필드와 pipeline은 아직 구현 전이다.

## 파일 배치 규칙

기존 주제 문서를 갱신한다. 큰 설계 결정은 [DECISIONS](../../DECISIONS.md)에 기록하고 긴 정의를 README로 복사하지 않는다.
