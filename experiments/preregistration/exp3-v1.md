# EXP-3 본실험 사전등록 v1 (11/18 동결 전 최종 검토본 — 결정 6·7 반영)

> **상태(2026-11-05):** 지웅 **결정 6·7 반영**된 11/18 사전등록 **동결 전 최종 검토본**이다. **아직 실행
> 유효본이 아니다** — 남은 `TBD-FREEZE` 토큰(engine_sha · 각 target image_digest/lock_digest · holdout 정체 ·
> seed 수 · sentinel_generator_seed · exposure_ledger_sha256 · jobs_max · watchdog)이 있는 한 레인 5 파서
> (`rds_preregistration.py`, #244)가 포맷 위반으로 **실행을 거부**한다(코드로 보장되는 비실행본). 이 값들은 G1
> 동결 시 #245 `freeze_preregistration.py`가 **한 번에** 치환하고 실행 전에 커밋해야 유효하다. 설계·판정 규칙
> (arm · 확증 검정 · 종단점 · hold-out 규칙)은 **확정**이며 결과를 보기 전 변경하지 않는다.
>
> **기준:** [research-questions v2](../../docs/research/design/research-questions.md) · [D038](../../docs/DECISIONS.md) ·
> 공통 키는 [exp0-pilot-v2](exp0-pilot-v2.md)와 레인 5 `rds_preregistration.py`(KNOWN_KEYS, #223/#230);
> pre-exposure 공개는 레인 8 exp0-pilot-v2.1 초안(미커밋)·#225 §5.6. 상위 계획은 Claude Doc(포인터만, 복사본 없음).

## 목적

EXP-3는 H-A 본실험이다: 피해 경로 이름을 아는 **동일 어휘·동일 예산** 아래 filesystem security state
retention 피드백(S-u)이 무작위(R)·구조 커버리지(D)보다 첫 경계위반까지 실행 수(T_first)를 줄이고 고유 위반
입력(U_viol)을 더 찾는가. 1차 지표·판정 시나리오는 research-questions v2를 따른다((e)). EXP-0 파일럿은 인프라
측정이며 본실험과 분리된다(formal 추정에 파일럿 합산 금지).

---

## (a) hold-out 규칙 — 버전 쌍 분리와 노출 공개

### 버전 쌍

| 역할 | node-tar 쌍 | root-cause / CVE | fixture | 비고 |
| --- | --- | --- | --- | --- |
| 개발·훈련 (train/dev) | **7.5.2 AFFECTED / 7.5.3 fixed** | R1 = CVE-2026-23745 (linkpath sanitation 누락) | toplevel hardlink | 자력발견(M3) 타깃 = node-tar 하나 = **7.5.2** (DECISIONS.md:632) |
| 평가 (hold-out 후보) | **7.5.6 AFFECTED / 7.5.7 fixed** | R2 = CVE-2026-24842 (check/use mismatch 회귀) | nested hardlink | R1 수정이 **도입한** 회귀 |

### 훈련 노출(training exposure)의 정의

이 사전등록에서 "훈련 노출"은 **어휘(vocabulary) 구성 · mutation/search 정책 튜닝 · seed 선택에 평가 쌍의
실행 산출물을 사용**한 것으로 정의한다. 단순 실행(≠ 튜닝)과, 평가 신호(oracle)가 평가 쌍 거동에 맞춰졌는지는
**별도로** 공개한다(아래).

### 이미 노출된 사실 — 정직 공개 (file:line, 추측 없음)

**FACT ① 7.5.6은 이미 실행됐다** — M2 통제 재현(고정 손 fixture + 릴리스 차분), 퍼징 캠페인 아님:
- `experiments/repro/cross_release_identity.py:55`(`"nested_hardlink": ("7.5.6", "7.5.7")`)·`:59`(`ALL_RELEASES`에 7.5.6 포함)
- `experiments/repro/evidence/summary.json:6,13,29`·`nested_hardlink.json:14,114`·`toplevel_hardlink.json:93` (7.5.6 공유=true raw)
- `experiments/summaries/cross-release-identity-repro-v1.md:25,49,53–55` (7.5.6 공유, resolved nlink 1→2)
- `docs/LOG.md:65`(M2.1: 5릴리스 7.5.2/3/6/7/8 disposable sandbox 추출·C1 observed)·`:76`(7.5.6/7.5.7/7.5.8 이미지 빌드·`--identify` 확인)·`:141`(M2 raw 재집계)
- `docs/STATUS.md:53,63,297` · `docs/DECISIONS.md:632`(MVP 범위에 7.5.6/7.5.7 명시)
- paper: `paper/sections/06-results.md:25,42–49` · `paper/tables/m2-cross-release-evidence.md:28,33–35,41` · `paper/figures/render_m2_cross_release.py:23,69,85–86`
- 동결 자산: `experiments/benchmarks/locks/node-tar-7.5.6.package-lock.json` · `experiments/benchmarks/catalog-v1.json:150,153`(N02 affected `<=7.5.6`)

**FACT ② 평가 신호(generic oracle)가 7.5.6 공유 post-state에 일치하도록 검증됐다** (M2.2 박제):
`tests/test_cross_release_oracle_agreement.py`(STATUS.md:53), container_integration `check_cross_release_oracle_agreement.py`.

**FACT ③ 엔진 소스에 7.5.6 참조 없음** — `grep -rn '7\.5\.6' src/inodefence` = **0건**(2026-11-04). 즉
어휘·mutation/search 정책·seed 어느 것도 7.5.6에 키잉돼 있지 않다(=엄격 정의상 훈련 노출 없음).

**FACT ④ 5릴리스 sweep이 {7.5.2, 7.5.3, 7.5.6, 7.5.7, 7.5.8} 전부 실행** (`cross_release_identity.py:59`)
→ **swept 집합 안에는 '미노출' node-tar 쌍이 없다.**

**INFERENCE(표기):** 엄격 정의(어휘·정책·seed 튜닝) 기준 7.5.6 훈련 노출은 없다(FACT ③). 다만 평가 신호(oracle)가
M2.2에서 7.5.6 거동에 일치하도록 검증됐다(FACT ②) — 약한 평가신호 노출이다. oracle은 CVE/경로 하드코딩 없는
고정 불변식이라 7.5.6-특정 튜닝은 아니라고 본다(이 한 문장은 추론).

### 재분류 (지웅 결정 5 = B)

**7.5.6/7.5.7은 '기(旣)노출된 수정 검증 쌍(fix-verification pair)'으로 재분류**한다 — hold-out이 아니다. 노출
이력은 위 FACT ①②④(M2 통제재현 · M2.2 oracle 일치검증 · sweep 5릴리스; file:line)로 명시돼 있고, 이 쌍은 R2
수정이 닫혔는지 **확인**하는 용도(hit 기대 0)로만 쓰며 H-A 효과 추론에서 제외한다(분석 단위는 아래 '다중 타깃' 절).

**독립 hold-out**은 기존 sweep 밖 node-tar 릴리스 또는 다른 extractor에서 선정한다. 값(버전 · 이미지 digest ·
제외 기준)은 **`TBD-FREEZE`**(11/18 동결 전 확정)로 두되 **선정 규칙은 지금 고정**한다:
1. 후보 선정 과정에서 얻은 결과로 **유리한 대상을 사후 선택하지 않는다**.
2. **이미 노출된 타깃은 독립 hold-out으로 재사용하지 않는다** — node-tar 7.5.2/7.5.3/7.5.6/7.5.7/7.5.8 ·
   decompress 4.2.1 · oras-go v2.6.1 · Python tarfile(M4.1b 노출분).
3. 후보는 **hazard·결과를 보기 전에 등록**한다. 기노출 목록은 레인 8 `exposure-ledger.md`(#249, sha256 핀)로
   커밋하고, 레인 5 게이트가 `role=holdout` 타깃의 (extractor, version)이 그 목록에 있으면 **거부**한다(#244;
   `role=holdout ∧ exposure=pre-exposed`는 파서 레벨 포맷 오류). 선정된 holdout 정체는 **engine_sha-pinned 동결**
   (train 결과를 본 뒤 교체 불가)이다.
4. 후보의 **상태 확인(노출 여부·패치 상태)은 고정 회귀 fixture(`make regression TAR_VERSION=<x>`, 연구 규칙 3의
   ground truth)로만** 수행하고 결과를 **`exposure-ledger.md`에 status-check 항목으로 기록**한다. 후보에 대한
   **퍼징 캠페인은 금지**한다 — 캠페인 실행 자체가 노출이 되어 hold-out 자격을 잃기 때문이다. (지웅 결정 7)

---

## (b) 기계판독 등록 블록 (레인 5 파서 · #223/#230 게이트 스키마)

아래 펜스 블록이 실행기 파서 입력이다(레인 5 `rds_preregistration.py`, **#244 다중 타깃 `targets.<id>.*` 스키마**).
EXP-3 타깃(train node-tar 7.5.2 · fix-verification 7.5.6/7.5.7 · 독립 holdout · Python tarfile H-B)을
`targets.<id>.*`로 선언하고, 확증 검정 키(`confirmatory_test`·`confirmatory_family`·`multiplicity`·
`primary_endpoint`·`event_threshold`)와 기노출 원장(`exposure_ledger`·`exposure_ledger_sha256`)을 포함한다. 남은
값은 **`TBD-FREEZE` 한 종류**로 #245 `freeze_preregistration.py`가 한 번에 치환한다 — 동결·커밋 전까지 파서가
거부하는 **비실행본**이다. 단일 `image_digest`와 `targets.*` 혼용은 포맷 오류다.

```preregistration
# EXP-3 본실험 v1 (11/18 동결 전 최종 검토본). 남은 TBD-FREEZE를 #245로 채우고 커밋해야 실행 유효.
experiment_id = exp3
engine_sha = TBD-FREEZE
# seeds: EXP-0(9001-9005)·M3(100-129)·pre-exposed(9001-9004)와 disjoint. 수·값은 동결 시 확정.
seeds = TBD-FREEZE
budget = 2000
vocabulary = observed-names
arm.R = unretained-walk-v1-uniform-mutation-v1
arm.D = structure-coverage-v1-uniform-mutation-v1
arm.S-u = effect-feedback-v2-or-violation-v1-boundary-attempt-v1-uniform-mutation-v1
# 선택: 탐색적 ablation(주 비교 아님)
arm.S-a = effect-feedback-v2-or-violation-v1-boundary-attempt-v1-adaptive-mutation-v1
# --- 다중 타깃(#244 targets[] 스키마). role/exposure는 파서 열거검증; confirmatory_family 멤버십은 role∧hypothesis에서 유도. ---
targets.node-tar-7.5.2.extractor = node-tar
targets.node-tar-7.5.2.version = 7.5.2
targets.node-tar-7.5.2.image_digest = TBD-FREEZE
targets.node-tar-7.5.2.role = train
targets.node-tar-7.5.2.hypothesis = H-A
targets.node-tar-7.5.2.exposure = none
targets.node-tar-7.5.6.extractor = node-tar
targets.node-tar-7.5.6.version = 7.5.6
targets.node-tar-7.5.6.image_digest = TBD-FREEZE
targets.node-tar-7.5.6.role = fix-verification
targets.node-tar-7.5.6.hypothesis = H-A
targets.node-tar-7.5.6.exposure = pre-exposed
targets.node-tar-7.5.6.exposure_ref = experiments/summaries/cross-release-identity-repro-v1.md
targets.node-tar-7.5.7.extractor = node-tar
targets.node-tar-7.5.7.version = 7.5.7
targets.node-tar-7.5.7.image_digest = TBD-FREEZE
targets.node-tar-7.5.7.role = fix-verification
targets.node-tar-7.5.7.hypothesis = H-A
targets.node-tar-7.5.7.exposure = pre-exposed
targets.node-tar-7.5.7.exposure_ref = experiments/summaries/cross-release-identity-repro-v1.md
# 독립 holdout(결정 7): sweep 밖 node-tar(예: 7.9.x) 또는 타 extractor. 정체·버전·digest는 engine_sha-pinned 동결(train 결과 후 교체 불가).
# arms 생략 = 선언 arm 전체(R/D/S-u) → confirmatory_family S-u-vs-R·S-u-vs-D 둘 다 동결 가능.
targets.node-tar-holdout.extractor = node-tar
targets.node-tar-holdout.version = TBD-FREEZE
targets.node-tar-holdout.image_digest = TBD-FREEZE
targets.node-tar-holdout.role = holdout
targets.node-tar-holdout.hypothesis = H-A
targets.node-tar-holdout.exposure = none
# H-B 탐색적 일반성(확증 아님). 기노출(M4.1b): docs/STATUS.md:57·docs/BACKLOG.md:93·docs/STATUS.md:55. live 배선 전 dry-run 거부.
targets.py-tarfile-3.12.extractor = python-tarfile
targets.py-tarfile-3.12.lock_digest = TBD-FREEZE
targets.py-tarfile-3.12.role = train
targets.py-tarfile-3.12.hypothesis = H-B
targets.py-tarfile-3.12.exposure = pre-exposed
targets.py-tarfile-3.12.exposure_ref = docs/STATUS.md:57
# 기노출 원장(레인 8 #249) + 동결 직전 sha256sum. role=holdout∧exposure=pre-exposed·등재 버전 holdout = 포맷 오류.
exposure_ledger = experiments/preregistration/exposure-ledger.md
exposure_ledger_sha256 = TBD-FREEZE
sentinel_generator_id = sentinel-names/seed-random-v1
sentinel_generator_seed = TBD-FREEZE
sentinel_count = 3   # 지웅 결정 B: hazard 상향 입력. >=3 다수 sentinel.
# rule 5키: v2 본문 규칙(제공 시 대조). EXP-3 동일.
hit_definition = c1-or-c2-and-contract-violated
c0_counts_as_hit = false
denominator = all-cells-including-abort
abort_reporting = right-censored
rule_of_three_unit = campaign
observer_integrity_policy = invalid-continue
# --- 확증 검정(지웅 결정 6): 1차 = 모든 n 유효 seed-block exact 순열 로그랭크 + Holm(holdout 패밀리). ---
primary_endpoint = t_first
confirmatory_test = exact-logrank-permutation-v1
confirmatory_family = holdout:S-u-vs-R,S-u-vs-D
multiplicity = holm-fwer-v1
event_threshold = 5   # event<5 = underpowered 플래그(검정 교체 아님); rule-of-three 서술·비검정, 시나리오 ⑤.
# #230 런처 키(제공 시 대조; 열거/범위 위반은 포맷 오류).
execution_mode = per-case-container
jobs_max = TBD-FREEZE             # EXP-0 처리량(레인4)·레인6 규모 실측, 동결 시 채움
campaign_watchdog_seconds = TBD-FREEZE   # budget 2000: EXP-0 p95 full-step에서 상향
disk_pause_fraction = 0.9
interim_analysis = forbidden     # peeking 금지 — 사전등록 무결성
```

---

## (c) U_viol 정의 — 채택안(지웅 결정): oracle-evidence 기반 고유 위반 식별

**세 arm · 모든 보고 경로에 동일 적용**한다. 구현 세부는 레인 5 PR을 포인터로 둔다.

- **대상 사건 (hit · T_first · U_viol 공통):** post-state oracle `C1 ∨ C2` 이고 `contract_violated`인 step.
- **서명 canonicalization:** `contract_id` + **정규화 evidence**. 정규화에서 **dev/inode · 타임스탬프 ·
  before/after 값은 제외**한다(환경 비결정 성분 배제).
- **중복 제거 범위:** **캠페인 내**(한 캠페인 안에서 같은 서명은 1).
- **lineage:** fingerprint 동치로 **흡수**된다 — 서명 성분이 아니다.
- **eligibility:** feedback eligibility는 **탐색 거동 지표 `u_viol_feedback`에만** 적용한다. **U_viol 자체는
  eligibility와 무관**하다(위반이면 센다).

research-questions v2의 "정규화 서명 기준; 같은 lineage · 같은 fingerprint는 1"을 위 규칙으로 구체화한 것이다.

---

## (d) 검정력·규모 — 레인 6 보고 반영

> 출처: 레인 6 보고(#209 `src/inodefence/evaluation/power.py` 산출, a4 독립 재대조 완료). hazard 2e-5는
> 사전등록 v2 **참고 proxy**이며 검정력 입력이 아니다(민감도용, v2 (a)·(b)). **결정은 지웅.**

**지웅 결정 6: T_first를 1차 지표로 확정**(확증 검정은 '다중 타깃' 절)하되 통계적 한계를 명시하고, **EXP-0 실측으로 EXP-3
타당성을 동결(11/18) 전에 재평가**한다. 규모를 좌우하는 입력은 **둘**이다 — (1) seed 수, (2) **hazard 상향**
(sentinel count = **3**, 지웅 결정 B). 한쪽만으로 판단하지 않는다.

**구속 제약은 compute가 아니라 event 수다** — 두 사실을 **구분**해 적는다(영구 불가가 아니다):

- **(a) 20 seed 조건의 사건 상한.** T_first는 캠페인당 ≤ 1 event(first-event Poisson)이므로 20 seed × 2 arm =
  40 캠페인 = **event 상한 40**. 로그랭크 HR 0.5(=HR 2)의 Schoenfeld 필요 event ≈ **65.3**(power 0.8 · α 0.05
  양측) > 40 → 이 상한에서는 분리할 수 없다. 단 **사건 상한은 seed에 선형**이라 **33 seed/arm이면 상한 ≥ 65.3**
  (seed 지렛대로 도달 가능).
- **(b) 현 hazard에서 실제 예상 사건 수 부족.** hazard 2e-5(참고 proxy) · budget 2000에서 캠페인당 P(hit) ≈
  0.039 → **기대 event ≈ 2.3**, informative 쌍 ≈ **1.5**(검정력 ≈ 0.076). 사건 상한(a)과 **별개** 문제이며, 현
  hazard로 65 사건엔 ~**830 seed/arm**이 든다.
- **MDE(최소 탐지 효과) — 형식적 역산값일 뿐.** 전 캠페인 hit(P(hit)=1)을 전제한 **낙관적 상한**에서 MDE HR ≈
  **2.43**(d=40); **현실 예상 사건(≈2.3)**에서는 MDE HR ≈ **40**(d≈2.3). 둘 다 극소 사건 수의 형식적 역산값이며
  실제 검출 가능 효과가 아니다. **Schoenfeld/로그랭크 점근 정규근사는 event < 5(권장 ≥ 10~20)에서 무효 → 검정
  자체가 미정의**다. hazard 2e-5는 **M3.3 A3full 1/17@2000 참고 proxy**(사전등록 추정치 아님)이고 sentinel
  count = 3의 hazard는 미측정이다.
- **budget↑만으로는 부족 — 지렛대는 둘.** 캠페인당 1 event 포화라 budget↑는 사건 상한(a)을 못 올린다. 상한 ·
  기대사건을 올리는 입력은 (1) **seed↑**(선형, 느림)과 (2) **hazard↑**(sentinel count = 3, (d) hazard 상향 —
  별개 지렛대)다. **영구 불가가 아니라** 두 지렛대로 해소하며 둘 다 11/18 재평가한다.
- **compute는 1차 구속 제약이 아님(이벤트 수가 제약).** 처리량은 **host-state 경합에 민감**하다(syscall/IO
  바운드, CPU 코어 수 아님, 레인4 실측). 단일스트림 ↔ **jobs=2(레인4 Phase B, par_eff 0.87 · ×1.75)**: 전용/한산
  0.845 c/s → **1.48 c/s(≈128k/일) → 120k ≈ 0.94일**; 공유/바쁜 0.23~0.29 c/s → **0.40~0.51 c/s(≈35~44k/일) →
  120k ≈ 2.7~3.9일**. 11/18~11/28(10일) feasible, margin 회복(jobs 3~4 여지는 **미측정 · 주장 안 함**). **다중
  타깃이면 실행 수 = 타깃 수 배수**(각 타깃 120k). ~830 seed/arm은 c/s와 무관(이벤트 바운드). 증거
  `~/inodefence-evidence/wp-throughput-20261104/`(MANIFEST `9ebdc43768265b4c…`).
- **zero-hit(시나리오 ⑤)이 기본 결과.** rule-of-three 95% 상한(캠페인 단위) — arm당 n20 → 0.15, 2 arm n40 →
  0.075, 3 arm n60 → 0.05. 실행 단위(120k → 2.5e-5)는 탐색적 병기만. hazard proxy · rule-of-three는 **참고값,
  판정 입력 아님**.

**결정 6으로 확정(상세는 '다중 타깃' 절):** 1차 확증 = **seed-block paired exact 순열 로그랭크 + Holm**(holdout
패밀리) · `primary_endpoint = t_first`(U_viol 2차·비확증) · `event_threshold = 5` underpowered 플래그 ·
rule-of-three는 캠페인 단위 서술. → 레인 6 당초 제안의 ①(KM+R-o-3+MDE 병기)·③(seed 층화)·④(R-o-3 캠페인 단위)·
⑤(종단점·α·검정 등록)이 **등록됨**.

**남은 보조·탐색 분석:** paired dense-지표 보조검정(permutation/Wilcoxon)은 EN-008상 **"탐색"으로 분리 선언**
(effectiveness 아님), 검정력 수치는 `TBD-LANE6(검증 중)`(Wilcoxon 검정력은 tie_frac=중도절단 비율에 의존 →
EXP-0 분포·a4 독립 재현 전 미기재).

**남은 설계 한계(결과와 무관·불변):** powered 신호 vs 비-effectiveness 신호 모순 — zero-hit엔 U_viol도 0이고
0이 아닌 dense 신호는 EN-008상 effectiveness 척도가 아니므로 powered effectiveness 주장 경로가 부재(근본 한계).

1차 지표 T_first · 확증 검정은 **결정 6으로 확정**('다중 타깃' 절). 남은 것은 **최종 규모**(seeds 수 · arm당
캠페인 · budget)뿐으로, EXP-0 처리량 · abort · dense 신호 실측 + 결정으로 **11/18 확정**(`TBD-FREEZE`)한다.

---

## 탐색적 예비치 — M3 powered roll-up KM/로그랭크/A12 재계산 (확증 아님)

> 출처: 레인 6. `experiments/summaries/m3-powered-matched-verdict-v2.json` roll-up의 문서화 수치(A1 19완주/0
> hit, A3full 17완주/1 hit @exec 1720 = s101)를 #202 `survival.py`에 투입. 캠페인 수준 T_first, EXCLUDE 정책.
> 산출 스크립트 · sha: `~/inodefence-evidence/audit11-survival-recompute-20261104/`.

| 지표 | A1 (random floor) | A3full (identity feedback) |
| --- | --- | --- |
| 완주 캠페인 | 19 (전부 budget 2000 중도절단) | 17 (1 event @1720 + 16 중도절단) |
| KM S(t) | ≡ 1.000 | 1720 이후 0.941 |
| median T_first | 미도달 (> 2000) | 미도달 (> 2000) |
| 로그랭크 | χ² = 1.118, df = 1, **p = 0.290**(비유의); O−E는 A3full 방향(+0.528) | |
| A12 (first-faster) | — | **정의 안 됨**(A1 observed event 0) |

**해석.** 단일 event · 고중도절단 degenerate → 기존 v2 판정(Wilson CI 겹침 · underpowered · 사전등록 음성 ·
EN-008)과 일치. 점추정 방향만 identity feedback 유리, **유의성 없음, effectiveness 주장 아님.**

**라벨(레인 6 — 그대로 유지):**
① **from raw 아님** — roll-up 재구성(raw `~/inodefence-evidence/m3-powered-matched-20261030/`이 이 호스트 미반입).
② abort 중도절단 시점이 roll-up에 없어 **EXCLUDE 정책 1종만**(CENSOR_AT_ABORT/BUDGET 민감도 불가).
③ s118 pre-abort C1 @exec 65 **미포함**(abort라 raw 없이 분류 불가).
④ 단일 event의 **탐색적 예비치 — 확증 아님.** Mac raw 반입 시 3정책 민감도 · s118 · 부트스트랩 CI 포함 from-raw
완전본으로 대체 예정.

---

## (e) 판정 시나리오 ①~⑧

research-questions v2 "판정 시나리오"(①~⑧)를 **그대로 포인터로** 따른다(복사본 두지 않음):
[`../../docs/research/design/research-questions.md`](../../docs/research/design/research-questions.md). 요지 —
① S > R **그리고** S > D → 가속 주장 가능 / ② S > R이나 S ≈ D → 피드백 일반 효과만(identity 특정 미입증) /
③ 탐색 지표만 다르고 위반 동등 → 보안 이득 미입증(EN-008) / ④ 알려진 클래스만 → 정상(D007) / ⑤ 전 arm 위반 0 →
미관찰 보고·분모 명시·rule-of-three 상한(참고 상한일 뿐 판정 입력 아님) / ⑥ extractor 간 불일치 → oracle 일반성과
피드백 일반성 분리 / ⑦ 비용 과다 → 시간 정규화 지표 병기 / ⑧ **S ≤ R → 반증**.

성공·실패 판정(감사 14 꼭지)의 "**검정력 산출된 n에서 분리 실패 = 반증(연장 금지)**"는 1차 지표 **T_first의
확증 검정**(결정 6: seed-block exact 순열 로그랭크 + Holm, holdout 패밀리)에 적용하되, (d)의 통계적 한계
((a) 사건 상한 · (b) 예상 사건 부족 · event<5 underpowered 플래그)를 함께 명시한다. EXP-0 실측으로 동결 전
EXP-3 **최종 규모**를 확정하고, dense 보조 종단점 검정력은 11/18 등록한다. 가속(①) vs 반증(⑧) 구분은 양측 p
기각 + 방향 부호로 하며 '다중 타깃' 절의 `faster_arm` 규칙을 따른다(#257).

---

## 다중 타깃 분석 단위 · 층화 · 다중검정 — 지웅 결정 6 (확정)

EXP-3는 여러 타깃을 포함한다(`role`: train 7.5.2 · fix-verification 7.5.6/7.5.7 · 독립 holdout `TBD-FREEZE` ·
Python tarfile). 레인 5 targets[] 설계안과 연계한다 —
`targets.<id>.{extractor, version, image_digest|lock_digest, role, exposure, exposure_ref}`, 셀 = target × arm ×
seed(run_id = `<target_id>-<arm>-s<seed>`). 아래는 **지웅 결정 6 확정**이다:

- **1차 추론 = `role=train`(node-tar 7.5.2) 타깃의 탐색**(R/D/S-u T_first 비교). `fix-verification`(7.5.6/7.5.7)은
  수정 확인(hit 기대 0) **별도 표**(H-A 효과 추론 제외). **`holdout`(sweep 밖)이 유일한 확증(confirmatory) 검정**이다.
- **1차 확증 검정 `confirmatory_test = exact-logrank-permutation-v1`** — **seed-block paired exact 순열 로그랭크**
  (모든 n 유효; 독립 점근 로그랭크 필드 없음, `contrasts[].permutation.p_value`). **`primary_endpoint = t_first`**
  (U_viol은 2차 · `supplementary.u_viol_a12`, 비확증; 종단점 간 보정 없음).
- **다중검정 `multiplicity = holm-fwer-v1`**, 패밀리 = **`confirmatory_family = holdout:S-u-vs-R,S-u-vs-D`에 한정**
  (파서가 `role=holdout ∧ hypothesis=H-A`에서 멤버십 유도·동결). **확증은 holdout 패밀리의 `reject_at_alpha`뿐**
  (`confirmatory.confirmatory_scope`).
- **방향 · 판정 규칙 (양측 p + 부호, #257).** `exact-logrank-permutation-v1`의 순열 p는 **양측**(chi² 기반)이라
  기각만으로 가속(①)·반증(⑧)을 구분하지 못한다. `contrasts[]`의 **`observed_minus_expected`(부호) · `faster_arm` ·
  `direction_note`**로 방향을 읽는다: **확증 가속 주장 = `holm_adjusted_p` ≤ α 그리고 `faster_arm == S-u`**
  (S-u의 T_first가 더 짧음) → 시나리오 ①; **기각 ∧ `faster_arm ∈ {R, D}` → 시나리오 ⑧ 반증**; **무기각 →
  시나리오 ⑤(미검정)**.
- **`event_threshold = 5`는 유효성 플래그**다 — event<5면 로그랭크 점근이 무효이므로 **underpowered 플래그 +
  시나리오 ⑤(미검정) 보고 + `campaign_unit_rule_of_three_upper95` 서술적 상한**(확증·판정 입력 **아님**; R-o-3은
  CI 상한이지 arm 대조 검정이 아니다)으로 처리한다. **검정 교체가 아니다**(exact 순열이 모든 n에서 1차).
- **rule-of-three는 타깃별**(캠페인 단위, `campaign_unit_rule_of_three_upper95`)로 보고하고 **타깃 간 풀링 금지**.
  층화(타깃별 hazard 이질성)는 index/summaries의 `target_id` · `role` 필드로 처리.
- **holdout은 underpower임을 명시**한다((d)의 사건 상한 · 예상 사건 한계가 holdout에도 적용; 통계량 유효성 포함).
- 산출원 `report["confirmatory"]`(#248; 레인 6 #252 필드명): `{confirmatory_test, multiplicity, primary_endpoint,
  event_threshold, alpha, confirmatory_scope, contrasts:[{order, contrast, number_seed_blocks, total_events,
  permutation{p_value, observed_chi_square, exact, number_blocks}, observed_minus_expected, faster_arm,
  direction_note, holm_adjusted_p, reject_at_alpha, underpowered, campaign_unit_rule_of_three_upper95(underpowered 시)}]}`
  (방향 필드 `observed_minus_expected`·`faster_arm`·`direction_note`는 #257).
- `interim_analysis = forbidden`은 전 타깃 공통(파일 1개 = 실험 1개).

구현은 레인 5 **#244**(targets[] 스키마) · **#246**(분석 단위 · no-pooling) · **#248**(confirmatory 산출) ·
**#252**(필드명)에 있다 — 그 파서를 포함한 engine_sha로 11/18 동결한다.

## 측정 · 바뀌지 않는 것

측정 항목(abort 사유별·p95·exec/h·per-case vs 워커풀 parity·arm별 C0/C1/C2 인덱스·dense 신호·hazard proxy·raw
SHA-256 체크섬 목록)은 [exp0-pilot-v2 "측정"](exp0-pilot-v2.md)과 동일하게 기록한다(포인터). 안전경계
(disposable sandbox + sentinel, 격리 완화 0)·oracle 정의(C0/C1/C2 불변)·CVE/대상경로/정답 seed/근접 보상
하드코딩 없음(D005/D006)은 변하지 않는다. 어휘에 피해 경로 이름을 넣는 것은 위협 모델(research-questions v2)의
일부이며 세 arm에 동일 적용한다 — blind 발견을 주장하지 않는다.
