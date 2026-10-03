# 자동 검증

## 이 폴더는 무엇인가

현재 코드의 동작을 검증하는 테스트를 둔다.

## 입력

구현된 Python 모듈과 명시적인 test fixture.

## 출력

pytest 결과.

## 책임

현재는 패키지 import와 Python 3.12를 확인한다.

## 하지 않는 것

테스트 통과를 fuzzing 효과나 계약 탐지 성능의 증명으로 취급하기.

## 다른 모듈과의 연결

[src](../src/inodefence/README.md)의 구현을 검증한다. filesystem 환경 확인은 [scripts](../scripts/README.md), 연구 성능 평가는 [experiments](../experiments/README.md) 책임이다.

## 현재 상태

test_smoke.py의 두 테스트만 있다. 모델·pipeline·oracle 테스트는 아직 없다.

## 파일 배치 규칙

대상 책임을 식별할 test_*.py 파일을 둔다. 향후 filesystem 테스트는 Linux runtime의 disposable sandbox를 사용한다.
