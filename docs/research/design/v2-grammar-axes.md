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
