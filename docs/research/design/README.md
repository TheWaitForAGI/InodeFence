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

Layer 2 공통 데이터 모델, Layer 3 최소 pipeline, Layer 4 Generic Mutation v1과
[protected-component addressing v1](mutation-protected-components-v1.md),
Layer 5 Feedback / Corpus 및 bounded campaign이 구현됐다. Contained Node의 tiny benign
configured campaign도 검증했다. Snapshot 관찰 범위와 runtime/kernel trust 한계는 유지하며,
Layer 6 benchmark/security evaluation과 연구 효과 검증은 아직 수행하지 않았다.
Native v2 replacement 실패 이후 확인된 multi-operation namespace rebinding은
[별도 v3 제안](entry-effect-rebinding-v3-proposal.md)에만 정의돼 있으며
**BLOCKED_FOR_REVIEW / NOT_IMPLEMENTED**다. 이는 현재 합의된 v2 계약이 아니다.

## 파일 배치 규칙

기존 주제 문서를 갱신한다. 큰 설계 결정은 [DECISIONS](../../DECISIONS.md)에 기록하고 긴 정의를 README로 복사하지 않는다.
