# 자동 검증

Container transport/policy unit tests는 `make check`에 포함한다. 실제 namespace/resource/
descendant 검증은 별도 `tests/container_integration/check_boundary.py`를 host broker로 실행한다.
[실행 명령과 policy](../src/inodefence/execution/README.md)를 따른다. Runtime이 없으면
integration command는 실패하며 PASS/skip으로 보고하지 않는다. CI는 별도 job에서 실행한다.

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

`test_execution_duration.py`는 finite/nonnegative duration validation, 모든 status의 monotonic elapsed 측정과 timeout budget 구분, JSON 보존과 signature/case identity isolation을 검증한다. 실제 E2E의 success/rejected/failed/timed_out에서도 finite/0 이상인 duration을 확인한다.

`test_mutator.py`는 8개 독립 operator와 uniform baseline의 원본 불변성, caller-owned RNG 재현성, raw spelling/순서/중복, 적용 불가 시 no-op와 canonical model invariant를 검증한다. `test_mutator_builder.py`는 별도 integration 경계에서 빈/regular/mixed case를 변형한 뒤 constructor 재검증과 deterministic USTAR의 raw path/link, type/mode/content/order 보존을 확인한다. USTAR 길이를 넘는 변형은 logical model에 남고 builder가 명시적으로 거부해야 한다. 이 검사는 mutator 구현에 builder 의존성을 추가하지 않으며 corpus scheduling, fuzzing 효과나 benchmark campaign의 검증이 아니다.

`test_pipeline_c0_harness_transitions_are_independent_of_signature`는 실제 run_case/Python reference extraction에 controlled execution effect를 추가한다. Archive namespace 생성, input.tar 삭제·inode/type 교체는 C0이며 content/mode-only effect는 C0가 아니다. Raw evidence는 보존되고 HARNESS signature exclusion은 유지되어 verdict와 novelty가 독립적임을 검증한다. Region.HARNESS는 security trust boundary가 아니다. 기존 서로 다른 case/TAR SHA-256의 semantic-equivalence, identity-group projection, directory nlink, live inode/PYTHONHASHSEED stability 및 C1/C2 regression을 유지한다.

`test_harness_artifact_changes_remain_raw_evidence_without_state_novelty`의 이전 AFTER bookkeeping 생성 + 모든 verdict nonviolation 가정은 snapshot에 actor provenance가 있다고 가정한 오류였다. 정상 setup은 BEFORE 전에 완료하도록 test lifecycle을 정리하고 nonviolation assertion을 유지한다. 같은 setup을 잘못된 baseline으로 관찰 구간에 포함하면 C0 evidence가 생긴다는 assertion도 추가한다. C1/C2 test의 harness alias는 baseline에 만들며 root replacement test의 retained inode는 extraction 안에 두어 기존 assertion을 유지한다. Test 삭제/skip/xfail이나 보안 판정 assertion 약화로 통과시키지 않는다.

Snapshot-only 관찰은 transient operation/direct path use/sandbox 밖 access와 actor attribution을 완전히 증명하지 못한다. Phase label은 provenance가 아니며 runner/adapter가 관찰 구간 내 harness namespace write 금지 계약을 지켜야 한다.

`test_feedback_corpus.py`는 C0/C1/C2 stable fingerprints의 contract/path/field 구분과
raw dev/inode/timestamp/value/prose exclusion, evidence/result ordering과 dedup을 검증한다.
Corpus의 state/violation 독립 novelty, 같은 case_id의 단일 보존, interesting observation과
새 entry 구분, 이미 보존한 case의 새 outcome에 대한 seen-index 갱신, 최초 admission
metadata 보존, 정확한 stats와 immutable exposed records를 검사한다. Uniform parent 선택은
insertion order와 caller RNG state로 재현되며 empty selection과 global random isolation도
검증한다.

`test_feedback_corpus_integration.py`의 필수 C0/HARNESS regression은 실제 `run_case()`를
사용한다. 서로 다른 case/TAR를 controlled no-effect target으로 실행한 A/B는 같은 signature이고
B는 보존하지 않는다. C는 TargetAdapter.run 관찰 구간에서 `archive/escaped.txt`를 생성하므로
같은 signature라도 새 C0 fingerprint로 보존한다. CVE PoC나 unsafe extractor를 사용하지 않는다.
다른 case/TAR/input digest, HARNESS mode, 네 execution status/duration과 relabeled raw
inode/device/timestamp가 novelty로 유출되지 않음을 추가로 검증한다. Caller 수준의 parent
선택 → `mutate` → child 한 번 실행 → consider 조합은 모듈 결합이나 fuzzing loop를 추가하지 않는다.

이 테스트들은 Layer 5 state retention contract를 검증하며 effectiveness, benchmark
rediscovery 또는 paper 결과를 증명하지 않는다.

4종 baseline TAR는 fixtures/tar/에 두며 [실행과 관찰 방법](../docs/examples/tar-baseline.md)을 따른다. Canonical validation은 Dev Container의 `make check`다. Filesystem test는 `/var/lib/inodefence` 내 disposable sandbox만 사용한다. 서로 다른 run의 inode normalization 검사는 두 sandbox를 동시에 유지해 inode 재사용을 피한다.

## 파일 배치 규칙

대상 책임을 식별할 test_*.py 파일을 둔다. 향후 filesystem 테스트는 Linux runtime의 disposable sandbox를 사용한다.

`test_campaign.py`는 정확한 seed-inclusive budget, 선언 순서, 중복/빈 seed/config 거부, RNG
호출 순서와 global isolation, no-op 실행, 네 status, 예외 전달, index/parent, stats와 불변성을
검증한다. `test_campaign_integration.py`는 Linux disposable runtime와 Python reference로 같은
config를 두 번 실행하고 semantic case lineage/feedback/admission order를 비교한다. Raw inode,
timestamp와 duration equality를 요구하지 않으며 연구 효과를 주장하지 않는다.

`test_generator.py`는 minimal seeds의 고정 순서/내용/의존 관계, unique case IDs, 반복 canonical
표현, 불변성과 filesystem/RNG independence를 검증한다. `test_generator_integration.py`는
기존 fixture bytes와의 동일성 및 explicit seed-only Python reference campaign에서 정상
hardlink/symlink 의미론을 검증한다. 기존 fixture regression은 그대로 유지한다.

`test_campaign_export.py`는 같은 완료 result의 deterministic LF bytes, manifest provenance와
JSONL checksum, canonical step encoding, 모든 status/raw allocation/time/bytes/text, C2 evidence와
feedback 보존, context ordering, 기존 output 거부와 IO 예외 전달을 검증한다.
`test_campaign_export_integration.py`는 Linux safe reference 결과가 runtime cleanup 후에도
완전히 export되는지 검사한다. Reader/deserializer API는 추가하지 않는다.

`test_provenance.py`와 campaign/export regression은 immutable 설정, 실행 전 capture, 같은 stored
값 보존, supplied config/adapter/result drift 거부와 exporter의 사후 재구성 방지를 검증한다.
`test_experiment_config.py`는 strict parsing, canonical config ID, critical-value binding, CLI config
보존과 unchanged isolation requirement를 검사한다. Actual runtime/source/results는 config identity와
분리한다.

`test_node_tar.py` covers portable invocation/binding/classification and campaign
rejection. The seven original real Node fixture cases moved to the explicit
container suite: `scripts.container_host ... validate-node-target` runs them plus
AFTER-error cleanup (8 cases). No real extractor runs outside its target container;
CI invokes this suite and unavailable runtime is an error, not a skipped PASS.

`test_linux_isolation_support.py`는 namespace prerequisite 진단의 denied/missing/timeout/error/
unsupported-platform 처리를 검사한다. Tool 설치만으로 지원을 주장하지 않으며 성공도 containment
증명이 아니다. `test_node_tar.py`의 실제 adapter 기반 regression은 두 campaign entry에서
provenance freeze/runtime/첫 archive execution 이전 거부를 확인한다. Gate 생략과 거짓 positive
진단을 주입한 local review에서 regression이 실패하는 것도 확인했다. Production isolation은 아직 없다.
