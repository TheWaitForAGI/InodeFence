# v2 문법의 추첨 축과 분포 (`b-grammar-v2-freeze-3`, #512)

> **상태:** IMPLEMENTED·TESTED(합성만). exploratory(등록 밖). 공식 p_R 계산 전에 고정한다.
> - 근거:
>   - W3 축 목록(depth-definition §2.2)과 그 개정 원장 줄
>   - W4 판정(2026-11-18, rng 추첨 전수 대응표에 대한 판정)
>   - 대응표 원본: 비공개 Drive `Research/02-엔진/20261118-HOST4-v2-rng추첨-전수대응표.md`
> - 정책: `MutationPolicy.V2_FREEZE3_FIXED_BASELINE` = **`uniform-b-grammar-v2-freeze-3-fixed-baseline-v1`**
>   - 이 id는 커밋 `4303075`의 임시 id `…-provisional-v1`(실행된 적 없음)을 대체한다.
> - 코드:
>   - 정의역: `src/inodefence/mutator/v2_freeze3.py`의 `GrammarParameters`/`FINAL_UNIFORM`
>   - 연산 표: `mutator/dispatch.py`의 `OPERATOR_ORDER_V2`
> - 테스트: `tests/test_v2_freeze3_grammar.py`
>   - 정의역 고정
>   - 모든 추첨이 고정 정의역에 대한 `rng.choice`이거나 위치 범위에 대한 `randrange`임
>   - 원시 연산 수

모든 arm이 같은 정책 id를 쓴다. arm 사이 차이는 입회 규칙과 부모 선택, 그리고 R의 m이다.
아래 분포는 모두 균등이다(유한 정의역에 대한 `rng.choice`, 위치는 `randrange`).
정의역을 바꾸면 새 정책 id가 필요하다.

## 1. 공유 축 (세 arm 같음)

| 축 | 정의역 | 코드 |
| --- | --- | --- |
| 연산 slot | 10개: `add_entry, remove_entry, duplicate_entry, reorder_entries, mutate_path, add_hardlink, add_symlink, mutate_link_target, set_mode, set_content` | `effect_scheduler.EffectUniformMutationScheduler.choose_operator` |
| entry 종류 | slot이 정한다(INSERT 종류를 따로 균등 추첨하지 않음). `add_entry` 안에서만 {regular, directory} | `entry_kinds` |
| INSERT 위치 | 0..n | `m1._insert`, `operators.duplicate_entry` |
| reorder 위치 | 첫 위치 0..n−1. 둘째 위치는 첫 entry와 값이 다른 entry 위치 가운데 균등(조건부) | `operators.reorder_entries` |
| 대상 entry 선택 | `mutate_path`·`set_mode`·`remove_entry`: 모든 entry. `mutate_link_target`: 링크 entry. `set_content`: regular entry. `duplicate_entry`: 모든 entry | 각 slot |
| 경로 분기 | {기존 경로 재사용, 기존 경로 확장, 새 경로}. 기존 경로(100바이트 이하)가 없으면 새 경로만 | `path_branches` |
| 새 경로 | 접두 {"", "./", "../", "/"}, 조각 수 {1,2,3,4}, 구분자 {"/", "//"} | `new_path_prefixes`, `new_path_depths`, `separators` |
| 확장 경로 | 기존 경로 + 구분자 + 토큰 {1,2,3}개 | `extend_token_counts` |
| 탈출 하드링크 | 깊이 {0,1,2,3}(`../` 개수), 꼬리 토큰 {1,2,3}개 | `hardlink_depths`, `hardlink_token_counts` |
| 링크 대상 바꾸기 | {affix, 새 경로 생성} 둘, affix 5종(`m1._AFFIXES`) | `link_target_ways`, `link_target_affixes` |
| 이름 토큰 | 풀 = `m1.COMPONENTS` 7 + 관찰 이름(등록 `OBSERVED_NAMES` 규칙: seed 기준 실행의 step 0 BEFORE 스냅숏의 경로 조각). COMPONENTS와 같은 이름과 반복된 이름은 한 번만 넣는다 | `v2_freeze3.operators` |
| H1 mode | {0o644, 0o755, 0o4755, 0o2755, 0o1777} | `modes` |
| 일반 파일 content | {빈 것, `x`×8, `x`×16}. `add_entry`의 regular와 `set_content` 둘 다 | `contents` |

이름 풀은 등록 하네스에서 16개(하네스 이름 4 + 관찰 이름 5)가 된다. 정책 id에는 **구성 규칙만** 고정된다. 관찰 이름의 값은 실행 환경(하네스 설정)에서 온다.

## 2. arm마다 다른 것 (공유 축이 아님)

| 항목 | R | D | S-u |
| --- | --- | --- | --- |
| 부모 선택 | 고정 seed corpus에서 균등 | 보존 corpus에서 균등 | 보존 corpus에서 균등 |
| 입회 규칙 | 보존 없음 | 구조 커버리지 | 상태 보존 |
| 실행 1회의 연산 수 m | 사슬 R: U{1..4}(`R_UNRETAINED_SEED_CHAIN_M4`, 주 정책) | 1 | 1 |

- `R_UNRETAINED_SEED_CHAIN_M6`(m ~ U{1..6})은 민감도 정책이다. 주 축이 아니며 따로 적는다(W4).
- 부모 선택의 기록 위치: W4는 "부모 선택 = corpus에서 균등(R은 고정 seed corpus)"을 축으로 기록하라고 판정했다. W3는 이것을 arm을 정하는 탐색 정책의 일부로 본다. 분포(균등)는 두 쪽이 같고 엔진도 같다. 목록에서 어느 칸에 적는지는 W3 원장 줄이 정한다.

## 3. 비추첨 고정값

- symlink entry mode는 0o777이다.
- `add_entry` directory의 mode는 기본값 0o644다.
- 링크 entry에는 content가 없다.
- 100바이트 USTAR 길이 검사(`m1.MAX_TEXT_BYTES`)를 넘으면 no-op이다. 확장 경로가 100바이트를 넘는 경우는 빌더가 판단하고, 표현할 수 없으면 build-invalid step이 된다(D060).

## 4. seed 코퍼스 (정책 id의 매개변수, v2.1)

v2와 v2.1은 seed 코퍼스만 다르다. 문법, 축, 분포, 사슬 R의 m, build-invalid 처리는 같다.

- 코퍼스는 정책 프로필(`mutator.policy.SEED_CORPUS`)이 정한다.
- 공유 런처는 언제나 등록 seed 4개를 넘긴다. 캠페인(`effect_campaign.bound_seed_cases`)이 그것을 정책의 코퍼스로 바꾼다.
- 그 밖의 코퍼스가 넘어오면 바꾸지 않고 거부한다.
- 세 arm이 같은 정책 id를 쓰므로 같은 코퍼스가 돈다. 사슬 R의 seed 추첨도 이 코퍼스 위에서 균등이다.

| 정책 id | 어휘 모드(사전등록 `vocabulary`) | 코퍼스 id | 내용 |
| --- | --- | --- | --- |
| `uniform-b-grammar-v2-freeze-3-fixed-baseline-v1` | `observed-names-b-grammar-v2-freeze-3` | `minimal-seed-corpus-v1` | 등록 seed 4개(bed077a와 바이트 동일) |
| `uniform-b-grammar-v2-freeze-3-fixed-baseline-minimal-empty-reg-v1` | `observed-names-b-grammar-v2-freeze-3-minimal-empty-reg-v1` | `minimal-empty-reg-v1` | 빈 아카이브, 일반 파일 `a.txt` 하나 |

- 코퍼스 id는 모든 seed entry의 논리 내용 전체를 고정한다: 이름, 종류, mode, content 바이트, 링크 대상(W4).
  - `set_content`는 이미 있는 바이트를 뽑으면 no-op이 된다. 그래서 content 바이트도 추첨에 영향을 준다.
- `minimal-empty-reg-v1`의 `a.txt` 값은 `generator/corpora.py`의 `MINIMAL_EMPTY_REG_REGULAR` 한 곳에 있다.
  - 지금은 임시값이다: 등록 `a.txt`와 같은 바이트, mode 0o644.
  - W3가 p_R 계산에 실제로 쓴 값을 보고하면 이 상수만 바꾼다.
- 빈 아카이브는 USTAR 끝 블록만 있는 10240바이트로 빌드되고, 다시 읽으면 같은 case가 된다.
- 빈 입력에서 slot별 동작:
  - `add_entry`, `add_hardlink`, `add_symlink`는 적용된다.
  - 나머지 7개 slot은 no-op이고 `applied` = False로 기록된다.
  - 사슬에서 no-op은 m에 세지만 깊이에는 더하지 않는다.
- 보고서 `config.seed_corpus`에 코퍼스 id가 기록된다(읽기 편의 라벨). **G1 v2 관문**(W4 2026-11-18, 기록만이 아니라 관문)은 셀마다 기록된 초기 case id(보고서 `initial_case_ids`, 보고서가 없으면 seed step의 `case_id` 순서)가 그 셀의 기록된 정책이 묶는 코퍼스(`mutator.policy.SEED_CORPUS` → `generator.seed_corpus`, 값은 그곳에서 import)의 case id와 같은지, 묶음의 arm 사이에 같은지 본다. 다르면 그 셀의 실패이고, 기록이 없거나 정책이 코퍼스를 묶지 않으면 확인 불가(`review_required`)다. 셀별 값은 `seed_corpus_cells`.
- 테스트:
  - `tests/test_seed_corpus_v21.py`
  - `tests/test_seed_corpus_golden_v21.py`: 회귀 golden이다. bed077a에 대응하는 코드가 없으므로 이 커밋에서 만든 값을 고정한다.
