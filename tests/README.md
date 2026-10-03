# 자동 검증

## 이 폴더는 무엇인가

현재 코드의 동작을 검증하는 테스트를 둔다.

## 입력

구현된 Python 모듈과 명시적인 test fixture.

## 출력

pytest 결과.

## 책임

모델 invariant와 raw path 의미, 결정적 USTAR encoding, 실제 Linux lstat/hardlink/symlink/digest, snapshot 변화, portable signature, C0/C1/C2 evidence와 reference E2E를 검증한다. 기존 baseline 재생성·extraction·probe regression도 유지한다.

## 하지 않는 것

테스트 통과를 fuzzing 효과나 계약 탐지 성능의 증명으로 취급하기.

## 다른 모듈과의 연결

[src](../src/inodefence/README.md)의 구현을 검증한다. filesystem 환경 확인은 [scripts](../scripts/README.md), 연구 성능 평가는 [experiments](../experiments/README.md) 책임이다.

## 현재 상태

`test_core_model.py`, `test_builder.py`, `test_observer.py`, `test_state_semantics.py`, `test_runtime.py`, `test_pipeline.py`가 core semantics를 검증한다. Oracle positive case는 synthetic 또는 직접 제어한 disposable sentinel state이며, vulnerable extractor나 CVE PoC를 재현하지 않는다. E2E는 실제 Python subprocess로 정상 entry, reject 후 부분 추출, parser 실패와 timeout을 확인한다. IO 오류/cleanup의 단위 검사는 오류를 주입하며 실제 실행 검사를 대체하지 않는다.

4종 baseline TAR는 fixtures/tar/에 두며 [실행과 관찰 방법](../docs/examples/tar-baseline.md)을 따른다. Canonical validation은 Dev Container의 `make check`다. Filesystem test는 `/var/lib/inodefence` 내 disposable sandbox만 사용한다. 서로 다른 run의 inode normalization 검사는 두 sandbox를 동시에 유지해 inode 재사용을 피한다.

## 파일 배치 규칙

대상 책임을 식별할 test_*.py 파일을 둔다. 향후 filesystem 테스트는 Linux runtime의 disposable sandbox를 사용한다.
