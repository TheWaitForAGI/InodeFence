# Security Contract 판정

## 이 폴더는 무엇인가

관찰 결과에 일반화된 보안 계약을 적용한다.

## 입력

StateSnapshot과 보호 대상·계약 설정(계획).

## 출력

ViolationResult와 판정 근거(계획).

## 책임

예: 내부 파일과 보호 sentinel의 의도하지 않은 identity 공유를 C1 위반 후보로 판정한다.

## 하지 않는 것

filesystem을 직접 실행하거나 mutation하기, CVE/버전으로 취약 판정하기.

## 다른 모듈과의 연결

[observer](../observer/README.md)의 사실을 받아 [feedback](../feedback/README.md)에 판정을 제공한다. 정의는 [security-contracts](../../../docs/research/design/security-contracts.md)에만 둔다.

## 현재 상태

빈 __init__.py만 있다. C0/C1/C2 우선이며 C3/C4는 후속 계획이다.

## 파일 배치 규칙

계약별 generic 판정 로직을 둔다. 수집은 Observer, 실행 차이는 Target Adapter에 둔다.
