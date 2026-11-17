# build-invalid step과 demo 보고서 스키마 5 (v2 U2, #512)

> **상태:** IMPLEMENTED·TESTED(합성만). exploratory(등록 밖). 방법 검토 W4 판정(2026-11-18):
> **탐색 동작 변경 없음 / 기록 형식 변경 있음(보고서 스키마 4→5).**
> 등록 설정(R/D/S-u × `OBSERVED_NAMES`, `build_invalid = abort`)의 탐색 궤적은 bed077a와 바이트 동일하다.
> 근거 테스트: `tests/test_registered_arms_golden.py`, `tests/test_registered_arms_golden_variable.py`.

## 1. 무엇이 바뀌나

빌더(`builder.build_tar`)가 표현할 수 없는 변이 자식은 지금까지 생산자 안에서 `ValueError`를 냈다.
그 결과 캠페인 전체가 abort했다(`aborted.reason`에 "cannot be represented in USTAR", 분류 `other`).
v2는 이것을 기록된 step으로 바꿀 수 있다.

| 설정 `EffectCampaignConfig.build_invalid` | 동작 |
| --- | --- |
| `abort` (기본값, 모든 기존·등록 설정) | 바뀌지 않는다. 루프는 빌더를 미리 부르지 않는다 |
| `record` (v2 전용) | 변이 자식마다 생산 전에 `build_tar`를 시도한다. `ValueError`면 `BuildInvalidStep`으로 기록한다 |

`BuildInvalidStep`(직렬화 스키마 1)은 다음과 같다.
- 예산 1단위를 쓴다. 생산자·oracle·feedback에 닿지 않는다.
- 스케줄러에는 새 key 없이 결과를 알려 보상이 0이다. corpus에 들어가지 않는다.
- seed는 build-invalid가 될 수 없다.
- 한 설정이 세 arm에 같은 값을 준다.
- R walk의 작업 부모는 바뀌지 않는다(관찰된 자식이 없으므로).

`EffectCampaignStep`의 직렬화 스키마는 2 그대로다. step의 canonical JSON과 그 digest는 바뀌지 않는다.
새 기록 키는 보고서용 레코드(`effect_demo`)에만 있다.

## 2. 보고서 스키마 5 (`effect_demo.DEMO_REPORT_SCHEMA`)

모든 변경은 추가다.
- step 레코드: `step_record_schema`(2), `archive_format`(실행 step: `RunResult.archive_format`), `outcome`(`executed` | `build-invalid`).
- 보고서 `config`: `build_invalid`, `builder_format`.
  - `effect_campaign_report`가 쓰는 보고서에만 있다.
  - 공유 경로 런처가 직접 만드는 보고서의 `config`에는 이 두 키가 없다. 그 파일은 바꾸지 않는다.
- build-invalid 레코드
  - `outcome: "build-invalid"`, `build_invalid_reason`(빌더 메시지), `validity: "invalid"`, `invalid_reason: "build_invalid"`
  - `oracle {}`, `oracle_fingerprints []`, `trace {}`
  - `feedback`: 새 key 없음, `retained: false`
  - `name_segments {"before": [], "observed": []}`
  - `mutation_attempt`·`scheduler_evidence`·`selection`은 실행 step과 같은 형식이다.

## 3. 판독기

- **`evaluation/rds_report.py`(사전등록이 가리키는 구현, bed077a와 같은 blob, 바꾸지 않음)**: 스키마 5를 그대로 읽는다.
  - build-invalid 레코드는 "실행 1회, 위반 없음"으로 센다(`t_first` 분모에 들어간다).
  - 어휘 풀은 그 레코드가 없을 때와 같다.
  - `name_segments` 키가 없으면 풀이 빈 값이 되므로 빈 목록을 넣는다.
  - 회귀 테스트: `tests/test_build_invalid_v2.py`.
- **`evaluation/rds_report_v2.py`(새)**: 같은 요약에 build-invalid를 **독립 범주**(`build_invalid_steps`)로 더한다.
  - 실행 step이 기록한 형식 집합도 낸다.
  - 스키마 4 레코드(`outcome` 없음)는 실행 step으로 읽는다. `archive_format`이 없으면 형식 집합은 확인 불가(`None`)이고, 값을 가정하지 않는다.
  - `check_report_config_v2`는 v2 키를 확인한다.
- 스키마 4 보고서와 스키마 5 보고서는 서로 비교하지 않는다(`_require_comparable`가 거부한다). 의도된 동작이다.

## 4. abort 분류

`abort_classification.InvalidReason`에는 값을 더하지 않는다. `scripts/analyze_exp0.py`(사전등록이 가리키는 파일)의 대체 목록이 enum의 모든 값을 나열해야 하고, 그 파일이 enum에서 어휘를 읽기 때문이다.
v2 분류는 `evaluation/abort_classification_v2.py`가 한다.
- 빌더의 두 문구("cannot be represented in USTAR", "USTAR name/prefix split would change the raw path") → `build_invalid`
- 나머지는 기존 분류기에 맡긴다
- 등록 경로에서는 이런 abort가 여전히 `other`다

## 5. 스키마 5에 자리만 잡아 둔 필드 (U3에서 채움)

스키마를 두 번 올리지 않으려고 같은 스키마 5에 자리를 둔다. U2는 쓰지 않는다. 키가 없으면 "미기록"으로 읽는다(`rds_report_v2`).

| 필드 | 위치 | 나타나는 때 | 키가 없을 때 |
| --- | --- | --- | --- |
| `chain_length`(int m), `operator_chain`(m개 `{operator_id, applied, selected_weight}`, 적용 순서) | step 레코드 `mutation_attempt` 안 | v2 무작위 사슬 R 정책일 때만 | 연산 1회(모든 기존·등록 정책). `mutation_chain_length`는 1(seed는 `None`)이다 |
| `input_structure`(객체 하나, 판정과 분리) | step 레코드 최상위 | 분류기(W4 서명 뒤)가 생긴 뒤 모든 step | 미기록(`input_structure`는 `None`이다). "구조 없음"이 아니다 |

- 사슬 정책에서 `operator_id`는 마지막 연산이고, `applied`는 "최종 자식이 부모와 다름"이다. `scheduler_evidence`는 마지막 연산의 것이다.
- 사슬 모델은 `MutationAttempt`를 그대로 두고 별도 타입(RES1 설계 §12 `MutationChainAttempt`)으로 둔다. 그래서 등록 설정에서 step의 canonical JSON은 바뀌지 않는다.

## 6. D가 깊이에 닿을 수 있음 (구성상 확인, 대상 실행 없음)

`tests/test_registered_arms_golden_variable.py::test_d_admits_non_seed_non_violating_inputs_and_reaches_depth_two`는 bed077a에 고정한 시험용 가변 생산자로 다음을 단언한다(seed 5·777·4242, budget 64).
- D의 corpus에 seed가 아니고 위반도 없는 변이 입력이 들어간다.
- 그 입력을 부모로 한 자식이 계보 깊이 2 이상에 생긴다.

계보 깊이는 실행 기록의 `origin`(seed = 0), `parent_case_id`, `mutation_attempt.applied`에서 계산한다. `applied=False`는 깊이에 세지 않는다.
bed077a 코드에서도 같은 단언이 성립한다(최대 깊이 3~4).
D와 S-u의 셀 설정은 `search_policy`(입회 규칙)만 다르다. 문법·어휘·seed corpus·부모 선택·연산 분포·예산은 같고, 이것도 테스트가 확인한다.
이것은 등록 논리의 성질이고 대상에서 잰 값이 아니다.

## 7. 하지 않은 것

- 빌더 형식은 `ustar-utf8-v1` 하나다. PAX·GNU 형식은 `b-grammar-v2-freeze-3`의 "v2 엔진 미구현"이다.
- `RdsCellSummary`와 등록 셀 설정은 바꾸지 않는다.
- 공유 경로 파일 16개와 사전등록이 가리키는 파일은 바이트 동일하다.
