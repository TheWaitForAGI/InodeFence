# 변이 어휘 목록 v1 (#512)

> **상태:** 동결 `b-grammar-v2-freeze-3`(문서만). 엔진 동작은 바꾸지 않는다. 표시: exploratory(등록 밖) 설계 메모.
> 이슈 [#512](https://github.com/TheWaitForAGI/InodeFence/issues/512)(변이 문법 확장)와
> [#499](https://github.com/TheWaitForAGI/InodeFence/issues/499)(작업 폴더 기준 하드링크)의 첫 단계다.
> 계열 목록은 #510에서 v2 holdout을 정하기 전에 동결한다(방법 검토 W4, 2026-11-18). 깊이 정의는 #509(레인 A)에서 받아 채운다.

## 동결: `b-grammar-v2-freeze-3` (2026-11-18, 재발행)

**문법 id: `b-grammar-v2-freeze-3`.** 동결 날짜 2026-11-18.
- 서명: IF-W4-METHOD(방법 검토). freeze-1 서명(42fbbf7의 계열 목록과 세는 규칙 기준), freeze-2 판정(정정 발행 승인),
  freeze-3 판정(2026-11-18, v2 엔진 범위 확정에 따른 재발행).
- 이력: `b-grammar-draft-0`(커밋 `35afa67`·`d02615e`) → `b-grammar-draft-1`(`7e1b667`·`42fbbf7`)
  → `b-grammar-v2-freeze-1`(`9edbf87`) → `b-grammar-v2-freeze-2`(`074284d`, 정오표 `b-grammar-v2-freeze-2.erratum.md`) → 이 재발행.
  이전 판의 바이트는 각 커밋에 남는다(W3는 SHA로 인용한다).
- **변경 메모(freeze-2 → freeze-3)**:
  1. **v2 엔진에서 구현하지 않는 항목**(freeze 목록에는 남기고 "범위 밖, 다음 실험"으로 표시). W4 판정 근거:
     v2 엔진은 원시 헤더 빌더를 만들지 않는다(모든 입력을 쓰는 구성 요소에 큰 새 표면을 더하는 위험).
     #509의 깊이 2 이상 후보(L2 사슬, O1 순서)는 이 계열을 필요로 하지 않는다.
     연산을 빼면 d*는 올라가기만 하고 내려가지 않는다. W3가 공식 d*를 아직 돌리지 않았다.
     - H1 owner(논리 모델에 uid/gid가 없음)
     - H1 size 불일치·링크 entry의 content 불일치
     - H1 PAX/USTAR 필드 불일치(PAX·GNU long 헤더)
     - P1의 새 변형 토큰(긴 경로·유니코드 정규화·대소문자 변형, 길이 상한 위치 포함)
  2. **v2 엔진에서 구현하는 항목(유지):** L1(탈출 하드링크 depth 0..3), L2, O1, H1 mode와 일반 파일 content.
  3. **freeze-2 정오표 두 항목을 본문에 반영:** 아래 1항의 대조 대상 id(freeze-2 본문 22행 "freeze-1과 대조" → 이 판에서는 freeze-3),
     freeze-2 변경 메모의 100바이트 검사 위치 네 곳(m1.py 32행 `_raw_path`의 기존 경로 재사용 후보, 72행 `add_hardlink`의 대상 선택(M1 표에만 있음),
     98행 탈출 하드링크 대상, 128행 `mutate_link_target`의 새 대상; §1.1 행에도 있음).
  4. **G1 관문의 위치 문구:** 아래 2항의 G1 관문 검사 위치를 `scripts/run_g1_smoke.py`가 아니라 v2 전용 새 검사 파일로 고쳤다
     (W4의 G1 판정 2026-11-18: SHARED_PATH_FILES 16개는 바이트 동일하게 둔다). 관문의 내용(검사할 것)은 같다.
- **세는 규칙과 남은 계열의 연산 수·대응표는 freeze-2와 같다.** 현재 엔진 동작은 바꾸지 않는다(문서만).

1. **이 동결이 v2 문법을 정의한다.** v2 엔진은 이 목록과 세는 법을 그대로 구현해야 한다. 단 아래 "v2 한계"의 계열은 구현하지 않는다.
   v2 동결 전에 IF-H4-QA가 구현을 freeze-3과 대조한다. 어긋남은 새 id와 W4 검토로만 처리하며 조용히 고치지 않는다.
2. **v2 전 필수 관문.** §3에 적은 것을 관문으로 명시한다: G1 어휘 동등성 검사에 셀 간 `mutation_policy` id 동일과
   빌더 형식 id 동일 확인을 추가한다. 이 검사는 SHARED_PATH_FILES를 건드리지 않는 **v2 전용 새 검사 파일**에 둔다
   (`scripts/run_g1_smoke.py`는 바꾸지 않는다).
3. **범위 밖** (목록이 말하지 않은 것을 포함으로 읽지 않는다):
   - P1·H1이 적은 부분집합 밖의 device/FIFO/sparse 타입
   - Windows 경로 의미
   - L2의 check/use 겹침을 뺀 root integrity(C3) 구조
4. **이후 변경**은 새 id와 W4 검토가 필요하다.

### v2 한계: 이 계열들은 v2 엔진에서 구현하지 않는다

freeze 목록(아래 §1~§3)에는 남기지만 v2 엔진에는 넣지 않는다. 표의 해당 행에 `[v2 엔진 미구현]`을 붙였다.
v2 실험의 결과는 이 계열이 없는 문법에서 나온 것으로 읽는다.
- H1 owner
- H1 size 불일치·링크 content 불일치
- H1 PAX/USTAR 필드 불일치(PAX·GNU long 헤더)
- P1의 새 변형 토큰(긴 경로·정규화·대소문자, 길이 상한 위치 포함)

아래 "후보 계열", "draft" 같은 표현은 동결 전 작성 이력을 남긴 것이다. 동결 뒤에는 이 목록이 v2 문법의 정의다.
- 레인 A(#509)의 결함 깊이 d*(이 문법에서 등록 seed corpus로부터 위반 입력에 닿는 데 필요한 최소 원시 연산 적용 횟수)는 이 id와 아래 규칙으로 센다.

### 세는 규칙 (draft-1, 어떤 d* 계산보다 먼저 고정)

> 원시 연산 1회 = TAR entry 하나에 대한 구조 편집 하나다: entry 하나 삽입, entry 하나 삭제, entry 하나의 필드 하나 변경(type,
> linkname, mode/owner, size/content), entry 하나의 위치 이동. 경로·대상·종류·깊이 같은 값의 선택은 그 연산의 매개변수이며 연산 수를
> 늘리지 않는다. 매개변수의 정의역은 그 필드가 TAR에서 가질 수 있는 일반 범위로 정하고, 특정 대상의 결함을 보고 넓히거나 좁히지 않는다.
> 아카이브 전체 형식(ustar/PAX/GNU)은 연산이 아니라 셀마다 기록하는 빌더 형식 id다.

이 규칙은 대상과 무관하게 기계적으로 적용한다. 아래 표는 모두 이 규칙을 적용한 결과다.
- 해석 메모: 괄호 안 필드 목록은 예시이며 전부가 아니다. path(이름)도 entry 필드다(W4 확인 2026-11-18).
  지금 코드의 경로 교체(SET path)는 "필드 하나 변경" 1회로 센다.
- 위치 이동의 원시 연산은 **MOVE(entry, 목표 위치) = 1**이다. 엔진의 swap(`reorder_entries`)은 복합이다:
  인접한 두 entry의 swap은 MOVE 1회, 인접하지 않은 두 entry의 swap은 MOVE 2회와 같다.

#### 엔진 연산 → 원시 연산 수 대응표

d*(#509)는 문법의 **원시 연산**을 센다. #507의 경험적 계보 거리 d와 v2의 d_R은 **엔진의 연산 적용 횟수**를 센다.
엔진 연산이 복합이거나 no-op인 곳에서는 두 측도가 달라지므로, #509가 d*와 d_R을 비교할 때 이 표를 거친다.

| 엔진 연산 (슬롯, 코드) | 적용 1회의 원시 연산 수 | 비고 |
| --- | --- | --- |
| `add_entry` (LEGACY `operators.add_entry`, M1 `m1.add_entry`) | 1 | INSERT. LEGACY는 끝에, M1은 임의 위치에 |
| `remove_entry` | 1 | DELETE |
| `duplicate_entry` | 1 | INSERT(기존 entry의 사본) |
| `reorder_entries` | **위치 의존: 인접 1, 비인접 2** | swap = MOVE 1 또는 2. entry가 2개 미만이거나 서로 다른 값의 entry가 없으면 no-op(0) |
| `mutate_path` (LEGACY affix, M1 `_raw_path` 교체) | 1 | SET(path) |
| `add_hardlink` (LEGACY, M1) | 1 | INSERT(hardlink) |
| `add_escaping_hardlink` (등록 arm 표의 슬롯 5) | 1 | INSERT(hardlink). depth는 매개변수 |
| `add_symlink` | 1 | INSERT(symlink) |
| `mutate_link_target` | 1 | SET(linkname) |
| 결과가 원본과 같은 적용 (모든 슬롯: 적용 불가, 길이 상한 초과, 같은 값으로 바꾼 경우 등) | 0 | 엔진은 적용 1회로 센다. `MutationAttempt.applied = False`는 child == case인 모든 경우다. 문법의 원시 연산은 없다 |
| no-reorder 정책(`*-no-reorder-v1`)의 reorder 슬롯 | 0 | 엔진은 슬롯을 실행하고 결과를 버린다(RNG 소비는 같음) |

지금 엔진에는 "삽입 두 번을 한 슬롯으로 묶은 연산"이 없다. 그런 연산을 새로 넣으면 이 표에 원시 수 2로 적는다.

이 문서는 (1) 지금 문법이 실제로 내는 entry 종류와 변이 연산을 코드에서 읽어 정리하고, (2) 지금 못 만들거나 드물게만
만드는 구조를 계열별로 적는다. 새 변이의 구현은 이 문서의 범위가 아니다.

## 1. 지금 문법이 내는 것 (코드 기준, main `5cc002b`)

### 1.1 논리 모델과 인코딩

| 층 | 코드 | 내용 |
| --- | --- | --- |
| entry 종류 | `src/inodefence/model/archive.py` `EntryType` | `regular`, `directory`, `hardlink`, `symlink` 네 가지뿐이다. FIFO·장치·연속 파일·sparse 같은 다른 TAR 타입은 없다 |
| entry 값 | `ArchiveEntry(path, entry_type, content, link_target, mode)` | 경로·링크 대상은 정규화하지 않은 원문 텍스트(NUL 금지, UTF-8). `mode`는 0..0o7777. 순서와 중복이 의미를 가진다 |
| 인코딩 | `src/inodefence/builder.py` `build_tar`(`BUILDER_FORMAT = "ustar-utf8-v1"`) | USTAR만 쓴다. uid·gid·mtime 0, uname·gname 빈 문자열, size는 content 길이. PAX·GNU long name/link로 넘어가지 않고 표현 불가면 실패한다. USTAR name/prefix 분할이 원문을 바꾸면 거부한다 |
| 길이 상한 | `src/inodefence/mutator/m1.py` `MAX_TEXT_BYTES = 100` | UTF-8 100바이트 검사는 **네 곳에만** 있다: 32행 `_raw_path`의 기존 경로 재사용 선택(넘는 경로는 재사용 후보에서 뺌), 72행 `add_hardlink`의 대상 선택(M1 표, 등록 표에는 이 슬롯이 없음), 98행 `add_escaping_hardlink`의 대상(넘으면 no-op), 128행 `mutate_link_target`의 새 대상(넘으면 no-op). `_raw_path`가 **새로 만드는** 경로(add_entry·mutate_path·add_hardlink·add_escaping_hardlink·add_symlink의 entry 경로와 add_symlink의 대상)는 검사하지 않는다. 기본 풀(`m1.COMPONENTS`)로는 최대 25바이트(접두 3 + 토큰 4×4 + 구분자 2×3)라 넘지 않는다. 등록 arm의 풀(기본 풀 + step 0 관찰 이름)은 이름 길이를 거르지 않으므로 긴 관찰 이름이 있으면 넘을 수 있다. 넘을 때 빌드 동작(`builder.build_tar`): entry 경로는 USTAR name/prefix 분할이 원문을 그대로 재구성하면 빌드되고 아니면 실패한다. 링크 대상(linkname 100바이트 필드)이 넘으면 빌드 실패(`ValueError`)다 |
| seed | `src/inodefence/generator/minimal.py` `minimal_seed_corpus` | 네 seed: 파일 1개 / 디렉터리+그 안 파일 / 파일+그 파일로의 하드링크 / 파일+그 파일로의 symlink. 모두 아카이브 안쪽을 가리킨다 |

### 1.2 변이 정책과 슬롯

모든 정책은 같은 8슬롯 순서(`src/inodefence/mutator/dispatch.py` `MutationOperatorId`, `OPERATOR_ORDER`)를 균등하게 뽑는다.
적용할 수 없으면 한 번의 no-op이고 재시도하지 않는다.

| 슬롯 | `operators.py`(LEGACY `uniform-generic-v1`) | `m1.py`(M1) | `m1_addressing.GENERIC_ESCAPE_OPERATORS`(등록 arm이 쓰는 표) |
| --- | --- | --- | --- |
| 0 add_entry | 끝에 regular 추가(`_PATH_PREFIXES`+`_PATH_STEMS`) | 임의 위치에 regular 또는 directory 추가, 이름은 `_raw_path` | m1 add_entry(어휘 = 아래 풀) |
| 1 remove_entry | entry 하나 제거 | 같음 | 같음 |
| 2 duplicate_entry | entry 하나를 임의 위치에 그대로 복제 | 같음 | 같음 |
| 3 reorder_entries | 서로 다른 두 entry 자리 바꿈 | 같음 | 같음 |
| 4 mutate_path | 한 entry 경로에 affix(`../`, `./`, `/`, `/..`, `x`) | 한 entry 경로를 `_raw_path`로 바꿈 | m1 mutate_path |
| 5 add_hardlink | 기존 경로를 가리키는 하드링크를 끝에 | 기존 경로(링크 포함)를 가리키는 하드링크를 임의 위치에 | **`m1.add_escaping_hardlink`**: 대상이 항상 `..`(1~3번)로 시작하고 1~3개 토큰이 뒤따름. 기존 경로를 가리키는 하드링크는 이 표에서 만들지 않는다 |
| 6 add_symlink | 기존 경로 또는 짧은 원문을 가리키는 symlink | 대상·경로 모두 `_raw_path`(기존 이름 재사용 포함) | m1 add_symlink |
| 7 mutate_link_target | 링크 대상에 affix | 절반은 affix(`../`, `./`, `/`, `/..`, `/`), 절반은 `_raw_path`로 교체 | m1 mutate_link_target |

`_raw_path`(m1.py): 경로가 있으면 절반은 기존 entry 경로(링크·중복 포함)를 재사용한다. 나머지는 접두(`""`, `./`, `../`, `/`)
+ 깊이 1~4 + 구분자(`/` 또는 `//`) + 토큰이다. 토큰 기본 풀은 `m1.COMPONENTS = (a, b, dir, file, item, ., ..)`다.

등록 arm(R, D, S-u)의 어휘는 하나다(`src/inodefence/evaluation/rds.py` `VocabularyMode.OBSERVED_NAMES` →
`MutationPolicy.M1_STATE_AWARE_ESCAPE_HARDLINK_FIXED_BASELINE`). 토큰 풀은 `m1.COMPONENTS` + **step 0의 추출 전 스냅숏에서
관찰한 이름**(외부 영역 이름 포함)이다. 캠페인 시작 때 한 번 정하고 늘리지 않는다(`effect_campaign.py`, `rds.vocabulary_pools`).
세 arm은 같은 표, 같은 균등 가중치(슬롯 가중치 1), 같은 seed·예산을 쓰고 보존(admission) 정책만 다르다
(`src/inodefence/feedback/effect_search.py` `RDS_POLICIES`).
G1 어휘 동등성 검사는 `scripts/run_g1_smoke.py` `vocabulary_equality`가 셀별 최종 토큰 풀을 seed마다 arm 사이에서 비교한다.

### 1.3 원시 연산과 매개변수 (d* 계산 단위)

위 세는 규칙의 원시 연산을 INSERT(삽입), DELETE(삭제), SET(필드 하나 변경), MOVE(위치 이동)로 적는다. **복합(composite) 연산**은
원시 연산 여러 번을 한 슬롯으로 묶은 것이며, 분해를 함께 적는다. d*는 원시 연산 횟수로 센다. 슬롯 안에서 무작위로 정하는 값(경로,
대상, 위치, 타입)은 그 연산의 **매개변수**다. 지금 코드의 8슬롯 중 `reorder_entries`만 복합이다.

| 지금 슬롯 (코드) | 원시/복합 | 원시 연산 | 매개변수와 그 범위 (지금 코드) |
| --- | --- | --- | --- |
| add_entry (`m1.add_entry`) | 원시 | INSERT(entry) | 위치 0..n, 타입 {regular, directory}, 경로 = `_raw_path`, content 0~16바이트 무작위, mode 0o644 고정 |
| remove_entry | 원시 | DELETE(i) | 위치 i |
| duplicate_entry | 원시 | INSERT(기존 entry의 사본) | 고를 entry, 위치 |
| reorder_entries | **복합** (draft-0에서는 원시로 셌음) | MOVE 최대 2회(두 entry를 서로의 자리로). 인접한 두 entry면 MOVE 1회와 같다 | 서로 다른 값의 두 위치 |
| mutate_path (`m1.mutate_path`) | 원시 | SET(i.path) (이름 필드 하나 변경) | 새 경로 = `_raw_path` |
| add_hardlink (`m1.add_hardlink`, M1 표) | 원시 | INSERT(hardlink) | 대상 = 기존 entry 경로 중 하나, 경로 = `_raw_path`, 위치 |
| add_escaping_hardlink (`m1.add_escaping_hardlink`, 등록 arm 표의 슬롯 5) | **원시** | INSERT(hardlink) | 대상 = `"../" × depth + 토큰 1~3개`. **현재 구현 depth 1..3, v2 문법 정의 0..3(미구현)**. 경로·위치. add_hardlink와 같은 원시 연산이고 대상 생성 규칙(매개변수 분포)만 다르다 |
| add_symlink (`m1.add_symlink`) | 원시 | INSERT(symlink) | 대상·경로 = `_raw_path`, mode 0o777, 위치 |
| mutate_link_target (`m1.mutate_link_target`) | 원시 | SET(i.link_target) | 절반은 기존 대상에 affix, 절반은 `_raw_path`로 교체 |
| LEGACY 슬롯들 (`operators.py`) | 원시 | 위와 같은 종류(삽입은 끝에만) | 경로·affix 목록이 더 좁다 |

**이름 어휘와 링크 대상 기준은 연산이 아니라 매개변수다(지금 코드 기준).**
- 토큰 풀(`m1.COMPONENTS`, 등록 표가 쓰지 않는 옛 구성 요소 목록(`m1_addressing.COMPONENTS`)이 더하는 상수 두 개, 등록 arm의 step 0 관찰 이름)은 연산 함수의 `components=` 인자다.
  `_raw_path`와 escape 대상 생성의 **매개변수 공간**을 정할 뿐이고 새 연산을 만들지 않는다.
  같은 연산이라도 풀에 어떤 이름이 있느냐에 따라 한 번에 닿는 입력이 달라지므로 d*는 풀에 의존한다.
  등록 arm의 풀은 step 0의 추출 전 스냅숏에서 정해지므로, d*는 "그 풀을 고정한 문법" 기준으로 센다.
  피해 경로 이름은 연산이나 고정 토큰이 아니고, 관찰 이름으로 풀에 들어갈 때만 매개변수 값이 된다.
- 링크 대상 기준(추출 루트 / 작업 폴더 / entry 위치)은 코드에 **명시적인 개념으로 없다.**
  대상은 원문 문자열이고, 어느 기준으로 풀릴지는 추출기가 정한다.
  문법 쪽에서 기준을 정하는 것은 사실상 대상 문자열의 앞 `..` 개수(escape 슬롯의 `depth`)와 접두(`/`, `""`)다.
- #499는 이 **매개변수 정의역의 문제**다. 세는 규칙상 매개변수 정의역은 그 필드가 TAR에서 가질 수 있는 일반 범위이고, 상대 링크
  대상의 일반 정의역에는 `..` 0개(평범한 상대 대상)가 들어간다. 그래서 **v2 문법(draft-1)의 탈출 하드링크 depth 정의역은 0..3**이고,
  #499의 경로(작업 폴더 기준으로 형제를 가리키는 하드링크)는 INSERT(hardlink) **원시 1회**다.
  **현재 구현은 1..3 그대로다.** 지금 엔진에서는 그 하드링크에 INSERT(hardlink) + SET(link_target)의 원시 2회가 필요하다.
  add_escaping_hardlink의 동작, 등록 arm이 쓰는 연산 표, 실행 커밋 E(`bed077a`)의 재현은 바꾸지 않는다.
  0..3은 나중에 새 문법 버전·설정으로 분리해 구현한다.
- **예외(d* 규약, W3와 맞춤):** 어떤 기준이나 이름을 쓰려면 그것을 만드는 **별도 entry**(디렉터리나 symlink 등)가 아카이브 안에
  있어야 하는 경우, 그 entry를 넣는 것은 매개변수 선택이 아니라 **독립된 원시 연산 적용(INSERT)**이다.
  예: entry 위치 기준으로 바깥을 가리키려고 디렉터리 symlink를 먼저 두는 경우 → INSERT(symlink) 1회 + 그 뒤 연산.
- 연산이 아닌 것: 아카이브 전체 형식(ustar/PAX/GNU)은 빌더 형식 id이며 연산 수에 들지 않는다(세는 규칙).

## 2. 지금 못 만들거나 드물게만 만드는 구조

"만듦" 칸은 코드로 본 가능성이다. 실행 빈도는 측정하지 않았다(가능 = 확률이 0이 아님, 드묾 = 여러 조건이 같은 변이 열에서 맞아야 함).

| 계열 | 구조 | 지금 만드는가 (근거) |
| --- | --- | --- |
| **L1 링크 대상 기준** | 하드링크 대상이 추출 루트 기준으로 풀리는 경우 | 만듦: 등록 표의 슬롯 5가 `..`로 시작하는 대상을 만든다 |
| | 하드링크 대상이 **작업 폴더 기준**으로 풀리는 추출기에서 그 폴더의 형제 객체를 가리키는 경우(`..` 없이 시작하는 상대 대상, #499) | 드묾: 슬롯 5는 항상 `..`로 시작한다. 슬롯 7(`mutate_link_target`)의 `_raw_path` 교체는 접두 `""`와 관찰된 이름으로 만들 수 있다. 다만 등록 표에는 기존 경로를 가리키는 하드링크 슬롯이 없어, 바꿀 하드링크는 seed의 하드링크와 슬롯 5의 결과뿐이다 |
| | 링크 대상이 **entry 위치 기준**(링크 entry가 있는 디렉터리 기준)으로 풀리는 경우(symlink의 표준 의미) | 만듦: 슬롯 6·7이 상대 대상을 만들고, 추출기가 entry 위치 기준으로 푼다. 다만 "링크가 놓인 깊이에 맞춘 `..` 수"를 고르는 장치는 없어 우연에 맡긴다 |
| | 절대 경로 대상 | 만듦: `_raw_path` 접두 `/` |
| **L2 symlink 사슬·type 교체** | symlink → symlink 사슬(2단 이상) | 가능: `_raw_path`가 기존 symlink 경로를 대상으로 재사용할 수 있다. 3단 이상은 드묾 |
| | 같은 경로를 디렉터리 → symlink로 바꿔 쓰기(그리고 그 반대) | 가능: add_entry(directory)·add_symlink가 기존 경로를 재사용하고 임의 위치에 삽입한다 |
| | 같은 경로를 regular ↔ hardlink ↔ symlink로 바꿔 쓰기 | 가능(같은 이유). 등록 표에서는 하드링크 쪽이 슬롯 5(탈출 대상)뿐이라 "기존 파일 자리에 안쪽 하드링크"는 seed 하드링크의 복제·이동으로만 생긴다 |
| **O1 순서 의존** | 선행 entry가 만든 객체(디렉터리 symlink)를 후행 entry가 경로로 통과(`d → ..` 뒤에 `d/x`) | 드묾: 후행 경로가 선행 symlink 이름을 첫 조각으로 가져야 한다. `_raw_path`의 재사용은 경로 전체 단위라 "기존 이름 + 하위 조각"을 일부러 만들지 않는다 |
| | 같은 경로 중복 | 만듦: 슬롯 2(duplicate), 이름 재사용 |
| | 부모 디렉터리보다 먼저 오는 자식 | 가능: 삽입 위치가 임의고 슬롯 3이 순서를 바꾼다. 부모·자식 관계를 의식해 고르지는 않는다 |
| | 하드링크가 자기보다 뒤에 오는 대상을 가리킴(앞 참조) | 가능(M1 문서가 허용함) |
| **P1 경로 표현** | `..` 조각, `./`, 중복 구분자(`//`), 끝 구분자 | 만듦: 접두·구분자·affix |
| | 긴 경로(100바이트 초과, USTAR prefix 사용, PAX path) **[v2 엔진 미구현 — freeze 목록에 있으나 범위 밖, 다음 실험]** | **기본 풀에서는 못 만듦; 관찰 이름 풀에서는 이름 길이에 달림.** 기본 풀의 생성 경로는 최대 25바이트다. 관찰 이름이 길면 `_raw_path`의 새 경로가 100바이트를 넘을 수 있다(검사하는 곳은 §1.1의 네 곳뿐). 그 경우 entry 경로는 USTAR prefix 분할이 원문을 보존할 때만 빌드되고, symlink 대상은 빌드 실패다. 빌더는 PAX로 넘어가지 않는다 |
| | 대소문자 차이, 유니코드 정규화 차이(NFC/NFD), 비ASCII **[v2 엔진 미구현 — freeze 목록에 있으나 범위 밖, 다음 실험]** | **못 만듦**: 토큰이 ASCII 고정 목록이다. 관찰된 이름이 비ASCII면 그대로 쓸 수 있으나 정규화 변형을 만들지 않는다 |
| | 백슬래시·드라이브 문자 같은 다른 OS 구분자 | **못 만듦**(범위 밖: Windows 의미는 초기 범위에서 제외, AGENTS) |
| **H1 헤더 변형 (보안 경계에 닿는 것만)** | PAX 확장 헤더의 path·linkpath가 USTAR 필드와 다른 경우 **[v2 엔진 미구현 — freeze 목록에 있으나 범위 밖, 다음 실험]** | **못 만듦**: USTAR만 쓴다 |
| | GNU long name/long link **[v2 엔진 미구현 — freeze 목록에 있으나 범위 밖, 다음 실험]** | **못 만듦** |
| | mode의 setuid·setgid·sticky와 경계 값 | 모델은 허용(0..0o7777)하지만 **변이가 mode를 바꾸지 않는다**(add_entry 0o644 기본, symlink 0o777) |
| | 하드링크·symlink entry에 size·content가 붙은 경우, size와 실제 길이 불일치 **[v2 엔진 미구현 — freeze 목록에 있으나 범위 밖, 다음 실험]** | **못 만듦**: 모델이 링크의 content를 금지하고 빌더가 size를 content 길이로 둔다 |
| | 다른 type flag(장치, FIFO, 연속 파일, GNU sparse), uid·gid·mtime 변형 | **못 만듦**: `EntryType` 네 가지, 메타데이터 0 고정 |

### 2.1 후보 계열의 연산 수 (draft-1, 세는 규칙 적용)

draft-0에서 "원시로 넣을지 복합으로 넣을지"가 미정이던 항목은 세는 규칙으로 정했다(W4 판정 2026-11-18).

| 후보 | 원시/복합 | 분해 또는 매개변수 |
| --- | --- | --- |
| L1 하드링크 대상 기준 (#499) | 원시 1 | INSERT(hardlink). depth는 매개변수, v2 정의역 0..3(현재 구현 1..3, 미변경). 새 연산 없음 |
| L2 symlink 사슬 k단 | 원시 k | INSERT(symlink) × k (각 대상 = 직전 symlink 경로, 대상 선택은 매개변수) |
| L2 같은 경로 타입 교체 (directory → symlink) | 원시 1 (앞 entry가 이미 있을 때) / 원시 2 (앞 entry도 넣어야 할 때) | 기존 이름에서 경로를 뽑는 INSERT(symlink, p) 1회. 새 SET(type) 연산은 필요 없다. 기존 entry의 type 필드를 바꾸는 것도 "필드 하나 변경" = 1로 같은 수다 |
| O1 선행 객체를 통과하는 후행 경로 | 원시 1 (선행 객체가 이미 있을 때) | INSERT(entry). 경로 = 기존 이름 + 접미(매개변수). 선행 symlink도 넣어야 하면 +1 |
| O1 부모보다 먼저 오는 자식 | 원시 1 | INSERT의 위치 매개변수, 또는 MOVE 1회 |
| P1 긴 경로·정규화·대소문자 | 원시 1 **[v2 엔진 미구현 — freeze 목록에 있으나 범위 밖, 다음 실험]** | SET(path) 또는 INSERT. 값은 매개변수(정의역 = TAR 이름 필드의 일반 범위). 100바이트 초과는 빌더 형식 id(PAX 등)에 달림 |
| H1 mode·owner 경계 | 원시 1 | SET(i.mode) 또는 SET(i.owner) — 세는 규칙의 "필드 하나 변경". 지금 엔진에는 이 연산이 없다. v2 엔진은 SET(i.mode)만 구현한다; SET(i.owner)는 **[v2 엔진 미구현 — freeze 목록에 있으나 범위 밖, 다음 실험]**(논리 모델에 uid/gid 없음) |
| H1 PAX·GNU long 헤더 | 연산 아님 **[v2 엔진 미구현 — freeze 목록에 있으나 범위 밖, 다음 실험]** | 빌더 형식 id(셀마다 기록). 연산 수 밖. G1에서 arm 간 같은 형식 id인지 확인한다 |
| H1 size 불일치·링크 content 필드 | 원시 1 **[v2 엔진 미구현 — freeze 목록에 있으나 범위 밖, 다음 실험]** (일반 파일 content 변경 SET(i.content)는 v2에 남는다) | SET(i.size) 또는 SET(i.content) — "필드 하나 변경" |

## 3. 계열별 판단 칸

공통 확인: 아래 어느 계열을 넣더라도 **새 연산은 `MutationPolicy` 하나의 슬롯 표에 들어간다.** 등록 arm 셋은 `VocabularyMode` →
`MutationPolicy` 대응 하나로 같은 표·같은 균등 가중치를 쓰게 되어 있다(`rds.py` 148행대, `RdsCellConfig.mutation_policy`).
arm 전용 연산은 만들지 않는다. 새 표는 **새 `MutationPolicy` id**로만 추가한다. 등록 실행 E(`bed077a`)의
`M1_STATE_AWARE_ESCAPE_HARDLINK_FIXED_BASELINE`는 그대로 둔다.

| 계열 | 일반 구조로서의 근거 | 특정 공개 권고 지식이 동기였는가 (솔직하게) | 세 arm 동등 (같은 어휘·같은 가중치) | G1 어휘 동등성 검사에 미치는 영향 | 깊이 (#509) |
| --- | --- | --- | --- | --- | --- |
| L1 링크 대상 기준 | TAR의 링크 대상은 상대 경로이고, 무엇을 기준으로 푸는지(추출 루트·작업 폴더·entry 위치)는 추출기 구현의 선택이다. 기준이 다르면 같은 바이트가 다른 객체를 가리킨다 | **예.** 작업 폴더 기준 변형은 decompress@4.2.1·oras-go 2.6.1의 통제 재현(#499, 2026-11-18 조건 4)에서 탐색이 하드링크 계열 위반을 내지 못한 것을 보고 고른 계열이다. 두 버전의 공개 권고를 알고 있었다. 탈출 하드링크 슬롯 자체도 node-tar 통제 재현(M2)을 알고 만든 것이다 | 예: 대상 기준을 슬롯 하나의 대상 생성 규칙으로 표현한다(예: 접두 `..` 수 0..3을 같은 분포로). 추출기별 분기는 넣지 않는다(대상별 로직 금지) | 토큰 풀은 바뀌지 않는다(같은 토큰 조합). 연산 표가 바뀌므로 G1에 "셀들의 `mutation_policy` id가 같다" 비교를 더해야 한다(지금은 구성상 같아서 검사하지 않음) | (비움) |
| L2 symlink 사슬·type 교체 | 링크를 따라가는 경로 해석과 같은 경로의 타입 교체는 추출기가 경로를 검사한 뒤 실제로 쓰는 사이의 일관성(Check/Use)과 닿는 일반 구조다 | **예, 일부.** node-tar 6.x 계열의 공개 권고(symlink·디렉터리 캐시)는 v2 예약 범위에 있다. 이 계열을 목록에 올린 데 그 지식이 작용했다. 어휘 계열은 v2 holdout을 정하기 전에 동결하고, 이 사실을 v2 한계로 밝힌다 | 예: 사슬 길이·교체 순서를 슬롯 안의 균등 선택으로 둔다 | 토큰 풀 불변. 연산 표 변경 → 위와 같음 | (비움) |
| O1 순서 의존 | TAR는 순서가 있는 연산 열이고, 선행 entry가 만든 객체를 후행 entry가 통과하는 구성은 아카이브 형식 자체의 성질이다 | 부분: 일반 형식 성질로 고른 계열이다. 다만 위 symlink 권고들이 순서 의존을 포함한다는 것을 알고 있다 | 예: "기존 이름 + 하위 조각" 경로 생성을 `_raw_path` 재사용 분기의 변형으로 넣으면 모든 arm에 같다 | 토큰 풀 불변(기존 이름 재사용). 연산 표 변경 → 위와 같음 | (비움) |
| P1 경로 표현 **[v2 엔진 미구현: 새 변형 토큰 전부]** | 경로 정규화 차이(긴 경로, 정규화 형식, 대소문자)는 검사 경로와 사용 경로가 갈리는 일반 원인이다 | 아니오(특정 권고를 보고 고르지 않음). 긴 경로는 빌더 형식(PAX) 확장과 묶인다 | 예: 토큰·길이 분포를 셀 공통으로 둔다 | **토큰 풀이 바뀐다**(예: 비ASCII·대소문자 변형 토큰). 풀이 셀 공통 상수면 G1 비교는 그대로 통과하고, 검사 기준(풀 목록)이 새 정책 id와 함께 기록돼야 한다 | (비움) |
| H1 헤더 변형 **[v2 엔진 미구현: owner·size 불일치·링크 content·PAX/USTAR 불일치; 구현: mode, 일반 파일 content]** | 헤더 필드 사이의 불일치(PAX 대 USTAR, size 대 실제 길이, mode 경계)는 파서가 서로 다른 값을 믿게 만드는 일반 구조다. 보안 경계에 닿는 것만 둔다 | 아니오(특정 권고에서 오지 않음). 범위는 "파서 모호성 전체가 아니라 경계에 닿는 것"으로 좁힌다(AGENTS 초기 범위) | 예: 헤더 형식(ustar/PAX/GNU)은 연산이 아니라 셀마다 기록하는 빌더 형식 id(`ustar-utf8-v1` 옆의 새 id)이고 모든 arm이 같은 형식을 쓴다. mode·owner·size 같은 필드 변경은 "필드 하나 변경" 원시 1 | 토큰 풀 불변일 수 있음. 빌더 형식 id는 연산 수 밖이며, G1에서 arm 간 같은 형식 id인지 확인해야 한다(같은 논리 입력이라도 형식이 다르면 TAR 바이트가 다름) | (비움) |

**세는 규칙과 알려진 결함 (출처 칸에 더함).** 세는 규칙(문서 머리)은 어떤 d* 계산보다 먼저 고정했다(draft-1, W4 판정 2026-11-18).
d*를 본 뒤 규칙을 바꾸지 않는다. 이 규칙이 알려진 결함 계열에 주는 수는 다음과 같다. 공개 권고를 아는 계열이라 결과를 미리 적어 둔다.
- **L2 같은 경로 타입 교체**(node-tar 6.x 계열 공개 권고와 닿음): 앞 entry가 이미 있으면 원시 1, 앞 entry도 넣어야 하면 2.
  draft-0의 "복합 2" 안보다 1 작아질 수 있다.
- **O1 선행 symlink를 통과하는 후행 경로**: 선행 symlink가 이미 있으면 원시 1, 없으면 2.
  "기존 이름 + 접미"를 매개변수로 보기 때문이다.
- **#499 작업 폴더 기준 하드링크**(decompress·oras-go 통제 재현): v2 문법 정의(depth 0..3)에서 원시 1.
  현재 구현(1..3)에서는 원시 2(INSERT + SET link_target)다. #509는 이 경로를 깊이 2 이상 후보에서 뺀다.
- 이 수는 규칙의 기계적 적용 결과다. 어느 결함이 "얕다"는 판단은 #509의 d* 계산과 W4 서명을 거쳐야 한다.

## 4. 지키는 것

- 특정 CVE의 PoC를 변이로 옮기지 않는다. 위 계열은 구조로만 표현하고, 대상 경로·sentinel 이름·버전을 변이에 넣지 않는다.
- 등록 arm 정의, 실행 커밋 E(`bed077a`), 동결 태그 기준 재현, 사전등록 파일은 바꾸지 않는다. 새 변이는 새 정책 id로만 추가한다.
- 새 비교 실행은 사전등록하거나 exploratory로 표시한다. node-tar v2 예약 버전(7.0.0–7.4.3, 6.0.0–6.2.1, 4.4.0–5.0.x)은 어떤 실행도 하지 않는다.
- 이 목록은 "무엇을 아직 못 만드는가"의 기록이다. 어느 계열이 위반을 더 낸다는 주장이 아니다.
