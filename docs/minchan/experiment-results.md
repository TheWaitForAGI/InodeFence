# 검증 결과와 재현 안내

> 기존 본문은 2026-10-22 실행 기록이다. 10월 23일의 새 코드·검증은 아래 별도 절에 기록한다.

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

## 2026-10-23 보완 실행

문서 base `3c2487b659a24d2f4b7bc38b5ca9928ffb959723`, core `8d29982c…`, 새 코드/테스트는
uncommitted local diff다. source hash/OS/Node/Python/UID/branch/dirty 상태는
[provenance](evidence/provenance-20261023.json)에 있다. 기존 evidence 파일은 덮어쓰지 않았다.

추가 구현은 `scripts/minchan_rebinding_capture.py`의 **synthetic-only** bounded ledger다.
네이티브 fs API·node-tar를 import/execute하지 않는다. caller가 v2 typed events와 synthetic token을
제공한다. 18개 새 tests는 deterministic call schedule로 정상·역순 completion, interleaved entry,
오류 코드, unmatched/duplicate, pending exit, overflow, token 없는 경우, reader 호환과 trace drift를 검사한다.
인위적 sleep은 넣지 않았다. 이 순서 역전은 실제 node-tar 로그가 아니다.

| 이번 검사 | 결과/근거 | native v3 관측 여부 |
| --- | --- | --- |
| 초기 prototype pytest | **실패: 3 failed, 10 passed**; initial-prototype-20261023.log | 없음 |
| 수정 후 초기 13개 suite | **통과: 13**; prototype-tests-20261023.log | 없음 |
| 최종 focused suite | **통과: 94** (기존76 + 신규18), focused-tests-20261023.log | 없음 |
| canonical make check | **통과: 1,602**; Ruff/format/Pyright/environment/docs 통과, make-check-20261023.log | actual node-tar v3 연결 아님 |
| 문서·diff/LF 검사 | validation-20261023.log | 해당 없음 |
| 실제 node-tar v3 run / qualification | **미실행**; hook·frozen source/image·별도 승인 없음 | **미검증** |
| P1−P0/P2−P1 비교 | **미실행** | 미검증 가설 |
| 과거 raw 재검산 | **미실행**; primary/mirror 경로 부재 | 원본 독립 확인 없음 |

초기 실패는 (1) canonical event JSON의 `value` wrapper를 빠뜨린 wire projection,
(2) 존재하지 않는 `OperationOutcome.FAILED`를 사용한 테스트 두 개였다. explicit projection에서
`value`를 사용하고 실제 enum `ACCESS_DENIED`로 바꿨다. 이어 import/format 검사와 Pyright의
token optional narrowing 오류가 나와 formatter 적용 및 `_reject`의 `NoReturn` typing을 수정했다.
기존 reader·enum·계약을 완화하지 않았다. 초기 실패 로그를 보존했다.

```bash
python -m pytest tests/test_minchan_rebinding_capture.py tests/test_rebinding_v3.py \
  tests/test_node_effect_producer.py tests/test_transition_model.py \
  tests/test_transition_search.py tests/test_mutation_scheduler.py -v
make check
python scripts/check_docs.py
git diff --check
```

최종 focused와 보강 후 canonical을 각각 1회 실행하고, 앞선 prototype·보강 전 실행은 별도 기록했다. pytest exit 0과
canonical 모든 단계 exit 0이 통과 기준이다. canonical에는 기존 안전한 reference/runtime 검사도
포함되므로 전체를 “어떤 filesystem 실행도 없는 검사”라고 부르지 않는다. third-party native v3
target 실행은 없다. source bind mount를 보안 filesystem 실험 공간으로 사용하지 않았다.

**검증 한계:** operation-only ledger의 sequence gap은 lifecycle record 때문인지 누락 때문인지
구분할 수 없어 허용한다. 시작·완료 쌍이 통째로 관측 밖이면 검출할 수 없다. 이를 명시적으로 검사했다.
v2 global reader가 transport/count/digest/flush를 검증해야 하며 그것도 계측 밖 API의 완전성을
증명하지 않는다. 모든 callback이 끝나도 target termination 실패면 export 불가다. 실패/pending은
terminal에 남지만 이 prototype은 native crash의 durable prefix writer를 제공하지 않는다.
18개 합성 통과는 native branch truth·overhead·capture coherence를 보증하지 않는다.
prototype 호출은 단일 observer에서 직렬 호출하는 schedule만 지원하며 Python thread safety나
실제 Node async-resource propagation을 구현하지 않는다. 같은 entry의 nested operation도 correlation으로
분리하는 합성 schedule을 검사했지만 실제 callback stack 중첩을 계측한 결과는 아니다.

합성 raw 예시는 [envelope](evidence/synthetic-v3-envelope-20261023.jsonl)와
[검증 record](evidence/synthetic-v3-verification-20261023.json)에 보존했다. raw SHA-256은
`d1c57ef6e8af1f8b3c03a73520e2d4759050ffa94a9a9b2ea4311c6215d1497d`이고 기존 reader는
composite 1개를 재구성했다. source와 v2 trace도 synthetic fixture다. 이 hash record는 production
external manifest나 native qualification token이 아니다. 보존 bytes를 재검증하는 명령은 다음과 같다.

```bash
PYTHONPATH=src:tests python - <<'PY'
import json
from pathlib import Path
from test_rebinding_v3 import _trace, V3_SOURCE
from inodefence.evaluation.rebinding_evidence import reconstruct_rebinding_evidence
root = Path('docs/minchan/evidence')
record = json.loads((root / 'synthetic-v3-verification-20261023.json').read_text())
assert record['synthetic_only'] is True
raw = (root / 'synthetic-v3-envelope-20261023.jsonl').read_bytes()
result = reconstruct_rebinding_evidence(raw, record['raw_sha256'], _trace(), V3_SOURCE)
assert len(result.sequences) == 1
PY
```

최종 nested-case 보강 전 canonical도 1,600개 통과했다. 그 로그는
`make-check-20261023-before-nested-cases.log`에 별도로 남겼다. 최종 canonical 결과와 사후 docs/diff 검사는
최종 완료 기록을 따른다.

### 최종 완료 기록

- 최종 focused: **94 passed** (0.30초). 신규18은 모두 합성이다.
- 최종 canonical: **1,602 passed** (84.22초), Ruff/format/Pyright/environment/docs 모두 통과.
- 사후 보완 문서·diff·LF·source hash·보존 synthetic raw 검증: [validation-20261023.log](evidence/validation-20261023.log).
- 현재 실제 native v3 연결/관측/qualification: **미실행 / 미검증**.
- H10/H21: **미검증 가설**. 과거 raw 재검산: **raw 미확보로 차단 / 미실행**.
