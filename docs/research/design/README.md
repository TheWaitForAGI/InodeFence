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
변이 문법이 지금 내는 것과 못 내는 것은 [변이 어휘 목록 v1](mutation-vocabulary-inventory-v1.md)(#512, 동결 `b-grammar-v2-freeze-3`, exploratory)에 있다. 정오표: [b-grammar-v2-freeze-2.erratum](b-grammar-v2-freeze-2.erratum.md).

변이 자식을 빌더가 표현할 수 없을 때의 기록(`build-invalid` step)과 demo 보고서 스키마 5는 [build-invalid와 보고서 스키마 5](build-invalid-and-report-schema-v5.md)(#512 v2 U2, exploratory)에 있다.

v2 문법이 하는 모든 추첨의 축과 분포(공식 p_R 전에 고정, 최종 정책 id)는 [v2 문법 추첨 축](v2-grammar-axes.md)에 있다.

step마다 기록하는 입력 구조 분류의 정의는 [입력 구조 분류기 v1](input-structure-class-v1.md)(`input-structure-class-v1-freeze-1`, W4 서명, 구현은 v2 U3)에 있다. 정오표: [input-structure-class-v1-freeze-1.erratum](input-structure-class-v1-freeze-1.erratum.md).

## 현재 상태

Layer 2 공통 데이터 모델, Layer 3 최소 pipeline, Layer 4 Generic Mutation v1과
[protected-component addressing v1](mutation-protected-components-v1.md),
Layer 5 Feedback / Corpus 및 bounded campaign이 구현됐다. Contained Node의 tiny benign
configured campaign도 검증했다. Snapshot 관찰 범위와 runtime/kernel trust 한계는 유지하며,
EXP-0 등록 실행과 hazard 파일럿은 수행했다. EXP-3 train과 EXP-2 holdout도 끝났고, H-A 확증 판정은 비기각(분리 실패, HR 2 배제)이다(#487): S-u는 R·D 어느 쪽과도 구분되지 않았고, 위험률 비 2 이상의 가속은 구간으로 배제됐다(결함 깊이 1 벤치마크). 판정 문장은 [주장 목록](../../../paper/sections/claims-evidence-status-v1.md) C-HA·S-HOLDOUT 행이 기준이다.
Native v2 replacement 실패 이후 확인된 multi-operation namespace rebinding은
[별도 v3 제안](entry-effect-rebinding-v3-proposal.md)에만 정의돼 있으며
**BLOCKED_FOR_REVIEW / NOT_IMPLEMENTED**다. 이는 현재 합의된 v2 계약이 아니다.

## 파일 배치 규칙

기존 주제 문서를 갱신한다. 큰 설계 결정은 [DECISIONS](../../DECISIONS.md)에 기록하고 긴 정의를 README로 복사하지 않는다.
