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

`test_pipeline_c0_harness_transitions_are_independent_of_signature`는 실제 run_case/Python reference extraction에 controlled execution effect를 추가한다. Archive namespace 생성, input.tar 삭제·inode/type 교체는 C0이며 content/mode-only effect는 C0가 아니다. Raw evidence는 보존되고 HARNESS signature exclusion은 유지되어 verdict와 novelty가 독립적임을 검증한다. Region.HARNESS는 security trust boundary가 아니다. 기존 서로 다른 case/TAR SHA-256의 semantic-equivalence, identity-group projection, directory nlink, live inode/PYTHONHASHSEED stability 및 C1/C2 regression을 유지한다.

`test_harness_artifact_changes_remain_raw_evidence_without_state_novelty`의 이전 AFTER bookkeeping 생성 + 모든 verdict nonviolation 가정은 snapshot에 actor provenance가 있다고 가정한 오류였다. 정상 setup은 BEFORE 전에 완료하도록 test lifecycle을 정리하고 nonviolation assertion을 유지한다. 같은 setup을 잘못된 baseline으로 관찰 구간에 포함하면 C0 evidence가 생긴다는 assertion도 추가한다. C1/C2 test의 harness alias는 baseline에 만들며 root replacement test의 retained inode는 extraction 안에 두어 기존 assertion을 유지한다. Test 삭제/skip/xfail이나 보안 판정 assertion 약화로 통과시키지 않는다.

Snapshot-only 관찰은 transient operation/direct path use/sandbox 밖 access와 actor attribution을 완전히 증명하지 못한다. Phase label은 provenance가 아니며 runner/adapter가 관찰 구간 내 harness namespace write 금지 계약을 지켜야 한다.

4종 baseline TAR는 fixtures/tar/에 두며 [실행과 관찰 방법](../docs/examples/tar-baseline.md)을 따른다. Canonical validation은 Dev Container의 `make check`다. Filesystem test는 `/var/lib/inodefence` 내 disposable sandbox만 사용한다. 서로 다른 run의 inode normalization 검사는 두 sandbox를 동시에 유지해 inode 재사용을 피한다.

## 파일 배치 규칙

대상 책임을 식별할 test_*.py 파일을 둔다. 향후 filesystem 테스트는 Linux runtime의 disposable sandbox를 사용한다.
