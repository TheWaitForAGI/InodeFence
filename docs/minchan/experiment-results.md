# 검증 결과와 재현 안내

실행일 2026-10-22 KST. source `8d29982c26cebfcce7a413b3ba9177fcd28078de`, branch `docs/minchan-intermediate-observation`.
이번 변경은 문서와 검증 기록이다. generic/target 코드 수정 없음. 고정 native matrix 재실행 없음.

## 이번 환경과 판정

Linux x86_64, kernel `6.18.33.2-microsoft-standard-WSL2`, Python 3.12.3, Node v22.22.0.
node-tar package 설치/실행 버전은 이번 검증하지 않았다. 저장소의 대상 pin은 7.5.22다.
기본 shell 도구는 bwrap user namespace 생성 오류로 시작 실패했다. 승인된 저장소 read/test는 elevated execution으로 수행했다. 이를 native target isolation 검증으로 간주하지 않는다.

| 검사 | 명령/입력 | 판정 | 실제 관찰 검증 |
| --- | --- | --- | --- |
| focused synthetic | 아래 pytest, 각 1회; deterministic test fixtures | **통과: 76 tests** | native 아님 |
| canonical | `make check` | **통과: 1,584 tests**, Ruff/format/Pyright/environment/docs 모두 통과 | native v3 증거 아님 |
| delayed synthetic runtime | 인위적 sleep 기반 collector 실험 | **미실행** | 모델 frame의 순서 역전과 구분 |
| node-tar v3 native | 실제 dependency producer | **미실행: 미구현** | **미검증** |
| 과거 480회 raw reader 재검증 | archived qualification bundle | **환경 제약으로 차단: raw 미확보** | 이번 독립 검증 없음 |
| P0/P1/P2 native comparison | equal-budget campaign | **미실행** | effectiveness 미검증 |

```bash
python -m pytest tests/test_rebinding_v3.py tests/test_node_effect_producer.py \
  tests/test_transition_model.py tests/test_transition_search.py \
  tests/test_mutation_scheduler.py -v
make check
git diff --check
```

focused 로그: [focused-tests.log](evidence/focused-tests.log). canonical 로그: [make-check.log](evidence/make-check.log).
실행은 각 한 번이며 RNG/budget/timeout은 각 기존 테스트 fixture가 정의한다. fuzzing experiment seed나 campaign budget은 적용되지 않는다.
pass 기준은 pytest exit 0 및 canonical 모든 단계 exit 0이다. 오류가 있으면 로그를 그대로 남기고 pass로 쓰지 않는다.

Canonical 실행은 문서 작성과 병행돼 기존 128 Markdown 파일을 검사했다. 작성 완료 후 `python scripts/check_docs.py`를 별도로 실행해 새 문서를 포함한 **134 Markdown 파일 통과**를 확인했다. 첫 사후 docs 검사에서는 아직 복사 전인 `evidence/make-check.log` 링크가 없어 실패했다. 실제 완료 로그를 복사한 뒤 재검사해 통과했다. `git diff --check`도 통과했다. [사후 문서 검사 로그](evidence/docs-check.log)에 이 순서를 보존했다.

## 핵심 합성 조건

| 조건 | 기존 테스트 | 의미 |
| --- | --- | --- |
| 시작과 완료 순서 역전 | test_out_of_order_completions_remain_observed_without_invented_dependency | frame 순서 보존, 가상 causal edge 금지 |
| 정상 순서와 realized content | test_regular_content_effect_has_exact_entry_correlation_and_causality | exact correlation/association/evidence |
| 작업 실패 | test_complete_rejected_prefix_is_retained_with_distinct_termination | rejection prefix와 success 구분 |
| 누락·중복·overflow·unmatched | test_transport_and_association_failures_never_promote_a_trace | invalid stream 승격 금지 |
| v3 same-path composite | test_positive_raw_fixture_reconstructs_additive_sequence_and_key | endpoint/dependency로 재구성 |
| v3 부재·conflict·다른 entry/path | test_composite_requires_all_semantic_predicates | 약한 관계를 rebinding으로 오인하지 않음 |
| manifest/token/sequence 변조 | test_reader_rejects_rehashed_dependency_forgery_against_trusted_manifest 및 tamper parameterization | 내부 digest 재계산만으로 위조 통과 불가 |

위 테스트는 합성 frame/model을 사용한다. fs callback instrumentation의 timing neutrality나 실제 node-tar control-flow token을 검증하지 않는다.

## 과거 실제 실행: 보존 요약의 기록

다음은 이번 실행 결과가 아니다. 입력·명령·image/source identity·반복·limits의 authoritative 기록은 각 요약에 있다.

| 기록 | 실행 identity / 입력·반복 | 기록된 판정과 raw 위치 |
| --- | --- | --- |
| private completion #87 | clean `9ea306f7ad20b8f479126360baf21192e0e86fdb`; Node22.22.0/tar7.5.22, mixed/directory-child/independent, stock/marker/snapshot 각20 | [요약](../../experiments/summaries/node-internal-completion-qualification-v3.md): QUALIFIED FAIL; raw checksum `ecb40154…` |
| causal effects #88 | clean `72bccfa`; 8 fixtures×3 profiles×20=480 | [요약](../../experiments/summaries/node-causal-effect-qualification-v4.md): QUALIFIED FAIL; v1 blocked |
| v2 qualification #89 | clean `36ff7fdb0e31db72b3e581fd1c089b712b4a7b4e`; WSL2, Python3.12.3, Node22.22.0/tar7.5.22, 8×stock/minimal/full×20 | [요약](../../experiments/summaries/node-native-effect-observation-qualification-v2.md): 13/14, NOT_QUALIFIED |
| runtime diagnosis #91 | clean `2e31ea9`; 90 contained runs, 18 complete native bundle | PR snapshot의 실패 8/성공82와 native v2 replacement 0; native v3 qualification 아님 |

v2 deterministic fixtures는 regular-file, directory-metadata, hardlink-identity, symlink, duplicate-path, directory-child, independent-files, partial-rejection이다. complete async `tar.x(strict=true,preservePaths=false)`, timeout10초/event256, memory512MiB/PID64 등의 세부는 보존 요약을 따른다. stock=무계측, minimal=lifecycle, full=operation evidence. 420 success+60 expected rejection을 모두 보존했고 forced timeout/overflow/backend injections는 480회 밖의 별도 검사다.

v2 raw primary: `/var/lib/inodefence/node-native-effect-observation-qualification-v2-20261013-36ff7fd-AA8cvq`.
mirror: `experiments/raw/node-effect-gates-20261013-AA8cvq/qualification`.
qualification.json SHA-256 `ca2dae9150813c6df14df10e16de65b1139550a7ecd761a30122c717e4575a90`.
session tar.gz SHA-256 `6b0a5b31d52d00347259342683941692181e93515d7f82384df86d9fb1cab1e5`.
이번에는 이 파일들이 없어 checksum 재확인은 하지 못했다. 원래 실패 Gate3 bundle과 Gate4 pre-matrix provenance failure도 원 session에 보존됐다는 기록만 확인했다.

재현은 위 요약의 trusted controller/broker 명령을 사용한다. raw 재분석과 새 target 실행을 구분하며, 기존 디렉터리를 덮어쓰지 않는다. v3 실제 연결 전에는 source-guard·dependency semantics·manifest trust·실패 주입·profile 비교와 허용 기준을 고정해야 한다. 단순히 v2 duplicate-path 입력을 바꿔 과거 판정을 pass로 만들지 않는다.

## 미검증·실패의 보존

현재 문서의 과거 13/14는 PR/summary와 판정 코드의 일치 확인이다. 원본 데이터 독립 재계산은 미완료다. 이번 결과는 engineering synthetic 검증이며 research effectiveness에 대해서는 **RAW ONLY / 미평가**다. 합성 통과로 native observation qualified나 paper-ready superiority를 주장할 수 없다.
