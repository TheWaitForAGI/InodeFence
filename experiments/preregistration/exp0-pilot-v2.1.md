# EXP-0 파일럿 사전등록 v2.1 (초안 — 동결 전 TBD-FREEZE 토큰·사전 노출 공개)

> **상태(2026-11-04):** 이것은 **동결 전 초안**이며 PR로 main에 올린다 — 머지하면 run_exp0 게이트가 대조할
> 등록 파일이 main에 존재하게 된다(단, 동결 PR 전에는 실행 불가). [exp0-pilot-v2](exp0-pilot-v2.md) 본문은
> 바꾸지 않고 기계판독 블록만 더한다. **`engine_sha`·`image_digest`·`sentinel_generator_seed` 세 값은 빈 칸이
> 아니라 명시적 `TBD-FREEZE` 토큰**으로 둔다. 이 세 값은 **별도 동결 PR**에서 채우며, **그 동결 커밋의 SHA가
> 등록 SHA**다(동결 커밋 이전 실행은 EXP-0이 아니다). image_digest **후보**(이 호스트 빌드):
> `sha256:22c8734f141d91b333ba37c7fe6a9a7547d7abfab487fa028da2053bed6f3dbb`. 레인 5 dry-run(케이스 1~4)으로
> 확인: `TBD-FREEZE`가 하나라도 남으면 run_exp0 게이트가 **포맷 오류로 거부**한다(40-hex `engine_sha` /
> `sha256:` `image_digest`가 아님) — 자리만 잡은 파일은 코드로 보장되는 비실행본이다. 아래 "## v2 본문
> (불변 복제)"는 v2와 글자 그대로 같다.

## 기계판독 등록 블록

아래 펜스 블록이 실행기 파서의 입력이다(레인 5 `src/inodefence/evaluation/rds_preregistration.py`,
브랜치 `claude/s3-rds-runner`). 파서는 **첫 번째** ```preregistration``` 블록만 읽고 블록 밖 산문은 무시하며,
`key = value` 한 줄씩, `#` 주석·빈 줄 허용, 중복 키 금지다. 실행 시 HEAD가 `engine_sha`와 같고 clean,
image digest·seed·budget·arm 일치가 아니면 실행을 거부한다(아무것도 돌지 않음).

```preregistration
# EXP-0 파일럿 v2.1 (초안). G1 동결 시 TBD-FREEZE을 채우고 실행 전에 커밋한다.
# 레인 5 확정 포맷 키: engine_sha image_digest seeds budget vocabulary arm.* sentinel_*
engine_sha = TBD-FREEZE
image_digest = TBD-FREEZE
seeds = 9001, 9002, 9003, 9004, 9005
budget = 200
# observed-names = step 0 BEFORE 스냅샷에서 풀 1회 고정(baseline mutation policy
#   uniform-generic-m1-state-aware-escape-hardlink-fixed-baseline-v1). 세 arm 동일 적용.
vocabulary = observed-names
arm.R = unretained-walk-v1-uniform-mutation-v1
arm.D = structure-coverage-v1-uniform-mutation-v1
arm.S-u = effect-feedback-v2-or-violation-v1-boundary-attempt-v1-uniform-mutation-v1
# 선택: 탐색적 ablation(주 비교 아님; 호스트 시간 남을 때만)
arm.S-a = effect-feedback-v2-or-violation-v1-boundary-attempt-v1-adaptive-mutation-v1
# sentinel: 레인 7 #205 describe() 스키마. generator_id는 #205 확정값과 일치해야 함.
sentinel_generator_id = sentinel-names/seed-random-v1
sentinel_generator_seed = TBD-FREEZE
sentinel_count = 3
# --- 아래 키는 #223(scripts/run_exp0.py + rds_preregistration KNOWN_KEYS)에서 게이트가 대조한다.
#     rule 5키(hit_definition·c0_counts_as_hit·denominator·abort_reporting·rule_of_three_unit)는
#     "제공 시 대조"(optional), observer_integrity_policy는 stop|invalid-continue만 허용하고
#     선언 시 실행 request에도 공급돼야 한다. 미지의 키는 KNOWN_KEYS로 추적된다. ---
# observer_integrity_policy: 레인 2 #207, 지웅 확인 조건
observer_integrity_policy = invalid-continue
# hit = post-state oracle C1 ∨ C2 이고 contract_violated인 step. C0만은 hit 아님(baseline 별도 집계).
hit_definition = c1-or-c2-and-contract-violated
c0_counts_as_hit = false
# 분모 = 모든 셀(abort 포함). abort는 우측중도절단으로 보고, 분모에서 제외 금지.
denominator = all-cells-including-abort
abort_reporting = right-censored
# zero-hit rule-of-three 상한의 독립성 단위(실행 단위 상한은 탐색적 병기).
rule_of_three_unit = campaign
# --- #230 선택 키(제공 시 대조; 열거/범위 위반은 포맷 오류). execution_mode는 G1 조건 1–3 통과
#     경로와 동일한 '검증된 경로'다. worker-pool 선택은 레인4 #224 모듈 + smoke.sh
#     DEMO_EXECUTION_MODE 배선이 main에 있어야 live 실행된다. ---
experiment_id = exp0
execution_mode = per-case-container
jobs_max = 2
campaign_watchdog_seconds = 7200
disk_pause_fraction = 0.9
interim_analysis = forbidden
```

**초안 메모(G1 전 확정 필요):**

- `engine_sha`는 실행 시점 `main` HEAD(clean). `image_digest`는 `inodefence-node-tar-effect:7.5.2`의 전체
  `sha256:` id(v2 대상표 prefix `sha256:21d8a0e3a5c5`). 둘 다 G1 후 확정.
- `sentinel_generator_id`/`sentinel_generator_seed`/`sentinel_count`는 런타임이 넘기는 sentinel_set의
  generator_id/seed/count와 **일치해야** 실행된다(불일치 시 거부). id는 레인 7 #205 `describe()` 확정값으로 고정.
- `observer_integrity_policy`·`hit_definition`·`c0_counts_as_hit`·`denominator`·`abort_reporting`·
  `rule_of_three_unit`은 v2 본문 규칙을 기계판독으로 옮긴 것이다. #223에서 이 5키는 `KNOWN_KEYS`에 포함되어
  **"제공 시 대조"(optional)**로 게이트가 검증하며, 이 초안의 값은 #223 기본값과 일치한다
  (`c1-or-c2-and-contract-violated`/`false`/`all-cells-including-abort`/`right-censored`/`campaign`).
  `observer_integrity_policy`는 `stop`|`invalid-continue`만 허용되고(초안=invalid-continue), 선언 시 실행
  request에도 공급돼야 한다. 필수 키는 engine_sha/image_digest/seeds/budget/vocabulary/arm.*이고 sentinel_*는
  optional이다. 2026-11-04 #223 대조: rule/observer 키는 KNOWN_KEYS에 속하고 값이 기본값과 일치, 빈 칸은
  engine_sha·image_digest·sentinel_generator_seed 3개뿐이다.
- **#230 선택 키(2026-11-04 추가):** `experiment_id=exp0`, `execution_mode=per-case-container`,
  `jobs_max=2`, `campaign_watchdog_seconds=7200`, `disk_pause_fraction=0.9`, `interim_analysis=forbidden`.
  #230에서 런처가 "제공 시 대조"하며 `execution_mode`/`interim_analysis`는 열거값만, `jobs_max≥1`,
  `watchdog>0`, `disk_pause∈(0,1]`. `execution_mode`는 G1 조건 1–3을 통과한 **검증된 경로**다. 이 6키는
  전부 선택이라 동결 시 빼도 되며, 빼면 런처는 자신의 CLI 값을 쓴다.
- **측정 4(per-case vs 워커풀 parity) 주석:** 워커풀 parity(G1 조건 4)는 **EXP-0의 전제가 아니라
  워커풀 사용의 전제**다. EXP-0 본 측정은 `execution_mode=per-case-container`(검증된 경로)로 수행한다.
  **2026-11-04 parity PASS 확인**(레인 4; a1 vs b 4차원 agree·재시도 0·self-determinism PASS)이므로 측정 4는
  워커풀 셀을 **추가로 측정 가능**(`available:true` 예정)하며 per-case와 처리량을 나란히 보고한다. (parity가
  PASS하지 못했다면 `available:false`로 보고했을 것이다. parity 결과와 무관하게 EXP-0 본 측정은 막히지 않는다.)
- **U_viol 지표 명시(새 정의 아님, 현 상태):** `U_viol`은 EXP-0의 **비등록 탐색 지표**다
  ([research-questions v2](../../docs/research/design/research-questions.md) L50 정의). formal 추정(EXP-3 hazard/효과)에
  **사용하지 않는다**. 1차 endpoint는 v2 본문대로 생존형 T_first이며 U_viol·rule-of-three 상한은 참고값이다.
- **C2 sentinel(선택지 B):** Security Contract의 **기본값은 변경하지 않는다**(D038 사람 승인 사항). 이 실험만
  `sentinel_count=3`, `sentinel_generator_id`는 레인 7 #205 확정 문자열(`sentinel-names/seed-random-v1`),
  `sentinel_generator_seed`는 `TBD-FREEZE`(레인 7 권장 seed 수신 후 동결 PR에서 채움).

## sentinel 집합 (동결 확정값 — 레인 7 #205/#214, 2026-11-04)

Security Contract 기본값은 불변(선택지 B). 이 실험의 sentinel은 아래로 **사전등록 동결**한다. 기계판독
블록의 `sentinel_generator_seed`는 여전히 `TBD-FREEZE`이며, **동결 PR이 이 값(20261104)으로 채운다** —
그 전엔 게이트가 비실행본으로 거부한다.

**선정 규칙(필수 명시):** `sentinel_generator_seed`는 **고정 상수**여야 하고 **캠페인 seed에서 파생 금지**다.
`generate_sentinel_set(seed, count=3)`이 seed로 이름을 결정하므로, 캠페인 seed 파생 시 seed마다 집합이 달라져
세 arm(R/D/S-u)·전 campaign seed의 "동일 sentinel 집합·동일 타깃" 전제를 위반한다(T_first/U_viol 교락).
고정 상수면 단일 집합이 모든 arm·모든 seed에 공통이다. 권장값 `20261104`는 사전등록일 기반(투명·비 p-hacking).

동결 시 `sentinel_set`은 다음 `describe()`(seed 20261104, count 3; mode 384 = 0o600)와 **바이트 동일**해야
하며, 실행 report의 `sentinel_set`에 그대로 재현된다(주입: 셀 env `DEMO_SENTINEL_COUNT=3
DEMO_SENTINEL_SEED=20261104` → `run_parallel_native.cell_env` → `local_node_tar_smoke.sh --sentinel-count 3
--sentinel-seed 20261104` → `run_effect_demo`):

```json
{
  "generator_id": "sentinel-names/seed-random-v1",
  "generator_seed": 20261104,
  "count": 3,
  "names": ["nux5boya8e3y.dat", "b2k94phssnhu.dat", "96575y82ul0n.dat"],
  "protected_paths": ["outside/96575y82ul0n.dat", "outside/b2k94phssnhu.dat", "outside/nux5boya8e3y.dat"],
  "sentinels": [
    {"name": "96575y82ul0n.dat", "content_sha256": "ed13f98527a83c9cf0467b0f42de558a2a57981a29bb72946a6ad2fb87a43686", "mode": 384},
    {"name": "b2k94phssnhu.dat", "content_sha256": "c21de362e397bde6444d0d079407449d97bdecc124208784c2180ac04ac39f36", "mode": 384},
    {"name": "nux5boya8e3y.dat", "content_sha256": "986430e9d3319331649b7832f9f1e8d96b0c9ead7c9c81d5f419a37da5c5e69b", "mode": 384}
  ]
}
```

k(=sentinel 수)-vs-reach 설계 입력(공식 실험 아님)은 `sentinel-k-reach-20261104/`(다음 manifest) 참조:
in-process reach k=3 ~2.0×·k=5 ~2.6×(k=1 대비) 포화. v2.1엔 count=3만 반영하고 k=5·파일럿은 사람 승인 항목이다.

## 실행 전제 (의존성; 머지 전 실행 불가)

EXP-0 실행은 다음이 **main에 머지된 뒤에만** 유효하다. 가장 핵심 의존성은 **#208의
`scripts/make_raw_manifest.py`** — run_exp0 완료 조건 8(실행 후 raw 체크섬 목록 생성)이 이 스크립트를
호출한다(이 등록 파일이 머지되는 시점엔 #208도 머지돼 경로가 생긴다). 그 외: #206→#212→#223→#230(사전등록 파서·게이트·선택 키),
#207(observer-integrity), #205→#214(sentinel 생성기), #235(`uv.lock`). 이 중 하나라도 미머지면 EXP-0을
"실행했다"고 적지 않는다.

## 동결 규칙 (게이트 그대로 유지)

`TBD-FREEZE`가 **하나라도** 남아 있으면 run_exp0 게이트가 **포맷 오류로 거부**한다(`engine_sha` 40-hex /
`image_digest` `sha256:<64hex>` 아님). 레인 5 dry-run 케이스 1~4로 확인됐다. 즉 이 등록 파일은 동결 PR이
세 값을 채우기 전까지 **코드로 보장되는 비실행본**이며, 게이트 로직은 이 PR로 바뀌지 않는다.

## 실행 체크아웃 규칙

- `engine_sha` = **머지 완료 main HEAD**. 등록(동결) 커밋은 그 HEAD **위**에 올린다.
- 실행은 **전용 worktree의 detached HEAD**에서, 입력·출력 **파일 절대경로**로 수행한다(공유 트리 오염 금지).
- LOG에 **engine_sha · 등록 커밋 SHA · 등록 파일 sha256** 세 값을 기록한다(실행 증거의 3-튜플).

## 사전 노출(pre-exposure) 공개 (2026-11-04)

정직성 공개다. EXP-0 사전등록 seed `{9001, 9002, 9003, 9004}`가 **사전등록 동결 이전에 미등록(unregistered)
실행으로 이미 한 번 노출됐다.** G1 통합 smoke가 그 seed를 실제로 돌렸다.

- **무엇이 돌았나:** unregistered G1 smoke. arm R/D/S-u × seed `{9001..9004}` = 12런, **budget 50**(사전등록
  budget 200 아님), node-tar 7.5.2 overlay, 코드 통합 브랜치 `claude/s3-g1-integration` `4b072a5`,
  image `sha256:22c8734f…`. raw: `~/inodefence-evidence/g1-20261104/smoke/` (라벨 demo run; EXP-0 raw 아님).
- **결과:** 12런 완주 12/12·abort 0. smoke `7.5.2-D-s9002`의 1-based step 42에서 **C2 사건 1건**
  (raw 재확인: `oracle.C2=true` + `feedback.contract_violated=true`; 12런 통틀어 유일한 contract_violated step).
  나머지 11런은 contract_violated 0.
- **왜 공개하나 / 영향:** v2는 seed를 동결했으므로 **v2.1에서 seed를 바꾸지 않는다**(동결 규칙 유지). EXP-0은
  가설(H-A) 검정이 아니라 **인프라 측정**이므로(위 "목적") 이 사전 노출은 EXP-0의 측정 타당성에 영향이 없다.
  다만 본실험(EXP-3, 11/18 사전등록)에서 hazard/효과를 **추정**할 때는 이 seed들이 pre-exposed라는 사실을
  기록하고, EXP-3 seed 선택 시 노출 이력을 고려한다(새 disjoint seed 사용 또는 노출 영향 명시). 이 C2 사건은
  unregistered·budget 50 조건의 관찰이며 등록 결과로 집계하지 않는다.

---

## v2 본문 (불변 복제)

**등록일:** 2026-11-03 · **단계:** 수술 4a(BACKLOG) · **기준:** [research-questions v2](../../docs/research/design/research-questions.md) · [D038](../../docs/DECISIONS.md) · **대체:** [exp0-pilot-v1](exp0-pilot-v1.md)(보존)

## 변경 사유 (v1 → v2)

1. **S 스케줄러 통제.** v1의 S는 adaptive 스케줄러라 retention 효과와 스케줄러 효과가 섞였다. 주 비교의 S를
   **S-u(identity/effect/boundary-attempt retention + uniform)**로 바꿔 D와 operator 정책을 동일하게 통제하고,
   adaptive를 얹은 **S-a는 탐색적 ablation(선택)**으로 분리한다.
2. **zero-hit 방침.** 5 seed × 200 × 3 arm = 3,000 실행이고 현 hazard 추정이 ~2e-5이면 기대 hit ≈ 0.06이라
   zero-hit이 기본 결과다. EXP-0이 hit로 무엇을 하지 않는지(아래 절)를 명시한다.
3. **백업 상태.** 원본 백업은 **미완료**다: 맥 raw는 체크섬 목록(`experiments/summaries/raw-manifest-mac-20261103.sha256`)만
   저장소에 있고 raw 자체는 호스트 로컬, 윈도우 raw 미반입, 외부/공유 저장소 백업 없음. EXP-0 raw도 같은 상태로
   시작하므로 실행 후 체크섬 목록을 저장소에 커밋하는 것을 완료 조건에 넣는다.
4. **rule-of-three 독립성 단위.** zero-hit 상한의 분모를 실행 수가 아니라 캠페인 수로 한다(실행 step은 캠페인 내
   비독립); 실행 단위 상한은 탐색적으로만 병기하고, 단위·계산 방식은 11/18 사전등록 전에 확정한다.

> **구속력.** 이 v2는 엔진 SHA·이미지 digest·policy ID가 비어 있는 **설계 등록**이다. G1(구현 수리) 동결 시 그 값을
> 채운 **v2.1을 실행 전에 커밋**해야 실행이 유효하다. **v2.1 커밋 이전의 실행은 EXP-0이 아니다.** v2.1은 아래 내용을
> 바꾸지 않고 빈 칸만 채운다.

## 목적

**인프라 측정**이다. 가설(H-A) 검증이 아니며, 파일럿 데이터는 **formal 추정(EXP-3)에 합산하지 않는다.** 목적은
EXP-3 규모와 EXP-2 GO/NO-GO 규칙의 숫자(x·n)를 실측으로 정하는 것이다.

## 대상

| 항목 | 값 | v2.1에서 채움 |
| --- | --- | --- |
| node-tar | 7.5.2 AFFECTED, frozen overlay `inodefence-node-tar-effect:7.5.2` (image_id prefix `sha256:21d8a0e3a5c5`) | 전체 image digest |
| Python tarfile | 3.12 `fully_trusted` (in-process) | 인터프리터 버전 문자열 |
| 엔진 | InodeFence main | 엔진 commit SHA |
| 컨트롤러 이미지 | 기존 production backend(격리계약·완화 플래그 0) | 컨트롤러 image digest |

## arm (R/D/S-u — research-questions v2 H-A와 동일)

| arm | retention | operator 선택 | 역할 | policy ID (v2.1에서 채움) |
| --- | --- | --- | --- | --- |
| R | 없음 | uniform | 무작위 바닥 | — |
| D | 구조 커버리지(`SearchPolicy.D`) | uniform | 커버리지 대조 | — |
| **S-u** | identity/effect/boundary-attempt | **uniform** | 주 비교 | — |
| S-a (선택) | S-u와 동일 | adaptive | 탐색적 ablation, 주 비교 아님; 호스트 시간이 남을 때만 | — |

세 주 arm은 **동일 어휘**(관찰 이름 포함 여부를 세 arm에 동일 적용)·seed·예산·이미지·oracle·operator 선택(uniform).
policy ID는 Evaluation 세션이 어휘 동등 R/D/S 러너를 구현한 뒤 v2.1에 기록한다.

## 설계

- **seed:** 9001, 9002, 9003, 9004, 9005 (5개; 기존 전 실험과 disjoint).
- **budget:** 200 / cell. 셀 = seed × arm × 타깃. 주 비교 3 arm = 3,000 실행(타깃당).
- **sentinel:** ≥ 3개. 이름은 **seed 고정 무작위 생성기**로 생성하고 생성기 seed를 결과에 기록한다(손으로 정한 이름 없음).
- **hit 정의:** post-state oracle **C1 ∨ C2**이고 `contract_violated`인 step. C0만은 hit가 아니다(baseline으로 별도 집계).
- **분모:** 모든 셀(abort 포함). abort는 우측중도절단으로 보고하고 분모에서 몰래 빼지 않는다.

## zero-hit 방침 (v2 추가)

3,000 실행 × hazard ~2e-5 → 기대 hit ≈ 0.06. **zero-hit이 기본 결과**이며 다음을 미리 정한다.

- **(a)** EXP-0은 C1/C2 hit으로 hazard를 **추정하지 않는다**. zero-hit이면 rule-of-three 상한만 보고하되, 실행 step은
  같은 캠페인 안에서 독립이 아니므로(corpus 계보·retention) 분모는 실행 수가 아니라 **캠페인 수**(3/n, n = 캠페인 수)로
  계산한다. 실행 단위 3/n(n = 실행 수)은 **탐색적 상한**으로만 병기한다. 독립성 단위(캠페인 vs 실행)와 상한 계산
  방식은 11/18 본실험 사전등록 전에 확정한다.
- **(b)** EXP-3 설계 입력은 **dense 신호**로 정한다: boundary-attempt 키 수, C0 도달(인덱스·비율), rejected 비율,
  처리량(exec/h), abort 사유별 수.
- **(c)** EXP-2 GO/NO-GO는 EXP-0이 아니라 **EXP-3 결과**에 11/18 사전등록된 규칙을 적용해 결정한다.
- **(d)** zero-hit은 NO-GO 사유가 **아니다**. "검정력 산정 불가 → EXP-3 hazard 상향 설계(다수 sentinel·budget 2000)
  진행"으로 처리한다.

## 측정 (전부 기록)

1. abort 수 — 사유별(observer evidence-integrity / docker broker / container cleanup / 기타)과 arm별 비율.
2. p95 full-step 시간(셀별·합산).
3. exec/h — 셀별·합산.
4. **per-case 컨테이너 vs 워커 풀** 처리량을 나란히(parity 확인; G1 조건).
5. arm별 첫 C0 / C1 / C2 인덱스(우측중도절단; 무hit=200, abort=abort 시점).
6. dense 신호 — boundary-attempt 키 수, rejected 비율(arm별).
7. hazard proxy = (C1 ∨ C2 step 수) / (실행 수) — zero면 캠페인 단위 rule-of-three 상한만 보고하고 실행 단위는 탐색적 상한으로 병기(위 (a)).
8. EXP-0 raw의 SHA-256 체크섬 목록(실행 후 저장소 커밋; 완료 조건).

## 파생 결정 (4a에서 작성)

EXP-2 GO/NO-GO 규칙 템플릿(EXP-3 결과에 적용):

> **EXP-3 R/D/S-u 합산 hazard ≥ x** 이고 **남은 호스트 시간으로 arm당 ≥ n 캠페인이 가능**하면 GO, 아니면 NO-GO.

**n**은 EXP-0 처리량·abort율 실측에서, **x**는 EXP-2 검정력 요구(목표 효과·n)에서 역산해 **11/14 확정**하고
**11/18 사전등록**(EXP-3 + EXP-2 규칙)에 넣는다. EXP-0의 hit 수는 x 산정에 쓰지 않는다((a)). 11/20에 EXP-3 결과에
규칙을 **기계적으로** 적용한다.

## 바뀌지 않는 것

안전경계(disposable sandbox + sentinel, 격리 완화 0), oracle 정의(C0/C1/C2 불변), CVE/대상경로/정답 seed/근접 보상
하드코딩 없음(D005/D006). 어휘에 피해 경로 이름을 넣는 것은 위협 모델(research-questions v2)의 일부이며 세 arm에
동일하게 적용된다.
