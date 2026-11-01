# 5. Results (드래프트 v1)

이 절의 모든 수치는 증거 사슬(raw → validated summary → finding)로 추적 가능하며, 능력 판정의
단일 기준은 Capability Ledger([`../../docs/STATUS.md`](../../docs/STATUS.md))다. 주장↔증거 매핑은
[`claims-evidence-status-v1.md`](claims-evidence-status-v1.md)를 본다. observed(실행 출력으로 확인)와
inferred(추론)를 소절마다 구분한다.

## 5.1 M1 — 루프가 실제 node-tar에서 돈다 (TESTED)

`make demo`(호스트, 실제 node-tar 7.5.22)는 입력 생성 → 실행 → entry별 중간 상태 관찰 →
C0/C1/C2 oracle → feedback → 다음 mutation 루프를 한 바퀴 20 step 돌린다. 반복 실행해도 같은
루프이고(SAME_LOOP), macOS/OrbStack과 WSL2 x86_64 두 플랫폼에서 동일 루프가 재현됐다(observed).

- 결과 JSON의 step마다 `trace`(entry별 중간 상태, observed/derived 구분), `oracle`(C0/C1/C2),
  `selection`(corpus 편입 여부 · operator 가중치 변화)이 남는다(observed).
- 정상 입력 20개에서 **위반 0건**이며, 이 소절은 취약점 발견·재발견을 주장하지 않는다.
- 중단 내성(끝난 step이 보존됨)과 producer 견고성(조용한 exit 0 → failed 프레임/lifecycle 기록)은
  별도로 TESTED다(Ledger 1–6행).

증거 수준은 **TESTED**(지정된 한계 안의 engineering 증거)이며 research effectiveness를 뜻하지 않는다.

## 5.2 M2 — 실제 경계위반 통제 재현 + 2-CVE 차분 (observed)

손으로 만든 결정론적 하드링크 fixture(외부 참조파일 대상, 추출 디렉터리를 벗어나는 동일 상대
경로)를 **5개 고정 node-tar 릴리스**(7.5.2 / 7.5.3 / 7.5.6 / 7.5.7 / 7.5.8)에 돌려, "추출된 객체가
외부 참조파일의 `(st_dev, st_ino)`를 공유하는가"라는 **generic C1 관찰**로 판정했다. 릴리스 id나
정답 경로를 판정 조건에 넣지 않았다. 전체 표는 [M2 cross-release 증거표](../tables/m2-cross-release-evidence.md),
raw는 [`../../experiments/repro/evidence/summary.json`](../../experiments/repro/evidence/summary.json),
검증 요약은 [cross-release-identity-repro-v1](../../experiments/summaries/cross-release-identity-repro-v1.md)다.

![node-tar 릴리스별 하드링크 identity verdict 그리드: top-level와 nested fixture × 7.5.2–7.5.8, 비단조 분포와 R1·R2 고정 쌍](../figures/m2-cross-release-evidence.png)

*그림 1 — 릴리스별 verdict(observed). 데이터 [표 M2](../tables/m2-cross-release-evidence.md),
생성 소스 [`../figures/render_m2_cross_release.py`](../figures/render_m2_cross_release.py).*

**Finding (observed).** 하나의 generic identity oracle(추출 객체↔외부 참조파일 inode 공유 = C1,
참조파일 전후 metadata 변화 = C2)이 서로 다른 **두 root-cause**를 포착한다.

- **R1 = CVE-2026-23745** (catalog N01): linkpath sanitation 누락. 최상위 하드링크가 7.5.2에서
  공유(nlink 1→2)되고 7.5.3에서 거부되는 전환으로 재현.
- **R2 = CVE-2026-24842** (catalog N02, GHSA-34x7-hfp2-rc4v): 검증 base ≠ 생성 base의 check/use
  mismatch 회귀로, **R1 수정이 도입**했다. 중첩 하드링크가 7.5.6에서 공유되고 7.5.7에서 거부되는
  전환으로 재현.

관찰된 공유 분포는 **비단조**(중첩: 7.5.2 공유 · 7.5.3 거부 · 7.5.6 공유 · 7.5.7/7.5.8 거부)로,
7.5.3이 닫은 경로를 7.5.6이 되돌렸고 7.5.7이 다시 닫았음을 보인다.

- **observed:** 5×2 verdict 표, nlink 전이, 거부 메시지, 비단조 분포.
- **inferred:** 특정 CVE↔fixture 대응과 "7.5.6 회귀가 R1 수정이 도입한 것"이라는 인과 서술.
  advisory 범위(24842 `<7.5.7`)와 이 **특정** fixture의 observed 거동은 다를 수 있어 **exact 하한은
  미검증**이다.
- **production-path 일치(M2.2):** 손 probe 판정 == production Observer+Oracle 판정 일치를 additive
  테스트로 고정했다([`../../tests/test_cross_release_oracle_agreement.py`](../../tests/test_cross_release_oracle_agreement.py),
  native closure는 [`../../tests/container_integration/check_cross_release_oracle_agreement.py`](../../tests/container_integration/check_cross_release_oracle_agreement.py)).

**정직 경계:** 이것은 **통제 재현**이지 **퍼저 자력 발견이 아니다**(자력 발견은 §5.3). fixture는
손으로 만든 generic 하드링크 엔트리이고, 하드링크·링크 상태 관찰·버전 차분 자체는 선행연구
(§3)가 다루므로 신규 기여로 표현하지 않는다.

## 5.3 M3 — 퍼저가 자력으로 위반을 찾는다: 메커니즘 인과 입증

영향 릴리스 node-tar 7.5.2(budget 1500)에서 **object-identity 관찰을 feedback으로 쓰는 state-aware
퍼징이 경계위반을 자율 트리거**한다. 전체 대조표는 [M3 blind-ablation 표](../tables/m3-blind-ablation.md),
그림 사양은 [m3-blind-ablation-figure-spec](../figures/m3-blind-ablation-figure-spec.md), 검증 요약은
[node-self-discovery-mechanism-v1](../../experiments/summaries/node-self-discovery-mechanism-v1.md)다
(Ledger M3 / PR #151, merge d44d903).

![M3 blind-ablation 막대그래프: A3full s11 21 hits vs A3blind s11 0 vs A1 random floor 0, identity 관찰 on/off 인과 대조](../figures/m3-blind-ablation.png)

*그림 2 — blind-ablation 대조(observed; 인과이지 rate 아님). 데이터 [표 M3](../tables/m3-blind-ablation.md),
생성 소스 [`../figures/render_m3_blind_ablation.py`](../figures/render_m3_blind_ablation.py).*

### 5.3.1 관찰된 수치 (observed, raw step 로그 재집계)

hit의 정의는 **step에서 `oracle.C1` AND `feedback.contract_violated`가 모두 참**이다.

| 셀 | seeds | 기록 step 수 | 자율 C1 hit |
| --- | --- | --- | --- |
| A3full s11 (state-aware) | 11 | 416 (abort 전) | **21** (모두 C1·C2·contract_violated 동시) |
| A3blind s11 (identity-blind 대조) | 11 | 1475 | **0** |
| A1 random floor | 1–35 (35개) | 33,005 | **0** |
| A3full scale study | 1–35 (35개) | 41,494 | **s11만 21** (그 외 전 seed 0) |
| A3full 재현 | 36–65 (30개) | 34,585 | **0/30** |

s11 run은 step 416에서 evidence-integrity 검사로 abort(returncode 1)하지만, 21건의 hit는 **abort
이전**에 기록된 step이다(producer abort-drain이 거부된 외부-하드링크 시도를 valid trace로 관찰).
따라서 process returncode 1을 "발견 없음"으로 읽지 않는다.

### 5.3.2 인과 해석과 정직 경계

**인과(주 주장, observed):** 발견의 원인은 **object-identity 관찰**이다 — blind 대조(관찰 이름에서
EXTERNAL region 제외)의 A3blind s11은 1475 step에도 0, 무작위 바닥 A1은 33,005 step에도 0,
state-aware A3full s11만 21. 즉 **"feedback(identity 관찰)이 발견을 가능케 한다 — 없으면 도달
불가."** 이것은 가설이 명시한 feedback이 실제로 발견을 구동함을 blind 대조로 확정한 것이다.

**정직 경계(엄수, inferred/열린 항목):**

- **blind 발견이 아니다.** 기존 외부 객체에 하드링크하려면 그 이름이 필요하고 퍼저는 그것을
  **관찰**로 얻는다. 어휘·oracle에 대상 경로·식별자·정답 seed·근접 보상을 하드코딩하지 않았고
  EXTERNAL 필터는 region 기준 target-agnostic이다. 다만 state-aware mutation 어휘 계열이
  `outside`/`sentinel.txt` 토큰을 포함할 수 있으므로, 어떤 rediscovery 프레이밍에서도 "blind 아님"을
  명시한다.
- **seed-rare.** s11은 동일 seed에서 결정론적으로 재현(21건)되지만, budget 1500·65 seed 중 자율
  C1을 내는 seed는 s11 하나뿐이다(재현 0/30). 이 예산에서 다른 seed로 일반화되지 않는다.
- **rate 우위가 아니다.** 이 소절의 주장은 **인과**("feedback이 발견을 가능케 함")이지 "상태-인지
  feedback이 무작위보다 빠르다/많이 찾는다"가 아니다(§5.3.3).

### 5.3.3 rate 우위 판정 — 사전등록 판정: CI 미분리(검정력 부족)

동일 budget·신규 disjoint seed 매칭 대조로 **rate 우위**(상태-인지 feedback이 무작위보다 더
빨리/많이 C1을 찾는가)를 사전등록 후 판정했다([powered verdict](../../experiments/summaries/m3-powered-matched-verdict-v1.md)).

- **설정(사전등록, 실행 전 고정):** A1 random floor vs A3full state-aware, node-tar 7.5.2 frozen
  overlay, **동일 budget 2000**, 기존 전부와 disjoint한 seed {100..119}(20개). hit = 한 step에서
  `oracle.C1 && feedback.contract_violated`(clean exact C1). rate 주장은 Wilson 95% CI 분리를
  요구한다(점추정 차이는 rate 아님, EN-008).
- **결과(observed):** A3full은 완주 10 campaign 중 **1 complete hit** — 신규 disjoint seed **s101**에서
  clean exact C1(1-based 실행 1720/2000) + s118이 abort 전 65건 관찰(observed-trigger, complete hit
  아님). A1은 완주 12 campaign 중 **0 complete hit**. 매칭 대조 Wilson 95% CI: A3full 1/10
  **[0.018, 0.404]** vs A1 0/12 **[0, 0.242]** → **겹침**(`complete_hit_wilson_intervals_separate=False`).
- **판정:** 완주 clean-C1 rate 점추정은 identity feedback 쪽(0.10 vs 0.00)이나 **매칭 Wilson 구간이
  겹쳐 rate 우위는 CI로 분리되지 않는다** — ~0.1 효과에 대해 이 예산·seed 수로는 검정력이 부족하다.
  rate 우위는 여전히 **미입증**이며 이 논문의 주 주장이 아니다.
- **단, 메커니즘은 멀티-seed로 강화된다(§5.3.2 보강).** §5.3.2의 자율 트리거는 budget 1500·seed
  1–65에서 s11 하나였으나, 이 powered 런은 **기존과 disjoint한 새 seed s101**(완주 C1)과 s118
  (observed-trigger)에서 identity feedback 경유 자율 C1을 재현했다. 즉 "object-identity 관찰이 발견을
  가능케 한다"는 인과 명제는 단일 seed 아티팩트가 아니라 **여러 disjoint seed에서 성립**한다. CI
  분리된 rate 주장은 사람-게이트 대예산 pilot(M3.4: N01 qualification 토큰·timeout 동결 선행)이
  필요하다.

### 5.3.4 (보조·탐색적) item-3 단일경로 A/B/C/D 중간상태 거동

effect-path에서 A/B/C/D 4 arm(§4.4)의 **중간상태 boundary-attempt 거동**을 측정했다(AFFECTED
node-tar 7.5.2, budget 1000; de-censored PASS 2). **gradient(C/D) > random(A) > structure(B)**가
3개 짝 seed에서 일관되고, **identity-state(C) ≡ coverage(D)**가 4/4 짝 seed에서 operationally
identical(동일 case_id 시퀀스·operator weights·boundary-attempt step)이었다. terminal C1은 **0/21**
(Wilson 95% CI [0, 0.155]).

- 이것은 **search behavior**(탐색 거동)이지 **effectiveness 랭킹이 아니다**(EN-008). 중간상태 키 수를
  effectiveness 결론으로 옮기지 않는다.
- C≡D는 **범위 한정 negative**다: escape-hardlink 문법에서는 external LINK=hardlink escape라
  external-resolve rung이 boundary-attempt와 중복되어 C의 추가 rung이 scheduling을 바꾸지 못한다.
  이 타깃·문법의 중복이지 identity-state 일반 무의미가 아니다(다른 문법에선 갈릴 수 있음).

## 5.4 M4 — 일반성 (oracle/adapter 수준)

### 5.4.1 동일 generic oracle의 3-extractor 적용 (일부 TESTED)

**동일 generic C0/C1/C2 oracle(코드 불변)**이 adapter 수준에서 3개 독립 extractor에 target-agnostic
하게 적용됨을 통제 reference 차분(affected/fixed digest-pinned)과 container-integration 체크로 보였다.
target 로직은 adapter/worker/recipe에 격리되고 generic 모듈은 불변이다.

- **python-tarfile (JS 아님, stdlib):** C1 하드링크 fixture를 Python tarfile로 돌려 `fully_trusted`
  (영향) = 외부 sentinel inode 공유로 production oracle이 C1+C2 발화, `data`(PEP 706 완화) = 거부·
  위반 0([`../../tests/test_python_tarfile_generality.py`](../../tests/test_python_tarfile_generality.py) 4 passed).
- **oras-go (Go) · decompress (JS):** 동일 generic oracle로 affected/fixed 통제 reference 차분 +
  container-integration generality 체크 통과(#176 · #177).

이는 oracle의 **target-agnostic성 증거**이며 **node-tar 결과·fuzzer 자력 발견·effectiveness 주장이
아니다.**

### 5.4.2 2번째 extractor 자력발견 native run — right-censored 음성 (observed)

decompress를 effect 캠페인 퍼즈 타깃으로 연결하는 루프를 구현(sanctioned
`inodefence-boundary-attempt-v1` frame #179 + generic C0/C1/C2 oracle 불변)하고 native run을
실행했다(사전등록 ef585f7). decompress의 ordered per-op trace는 격리경계 내 infeasible로 확정돼
feasible set-based frame 채널을 쓴다(node-tar의 ordered per-op보다 좁음; #179 observed).

- **실행 설정(observed):** 실제 decompress 4.2.1 AFFECTED, production backend(컨트롤러 내 non-root
  Linux, 격리계약·완화 플래그 0), budget 200 × seed 11 × 2 arm(A3 state-aware + A1 random).
- **결과(observed):** **양 arm 0 C1/C2 (right-censored 음성).** 루프는 2번째 extractor에서 기능
  작동한다(실제 decompress frame 관찰, boundary-attempt 키 A3 11 / A1 8, rejected 141 vs 103,
  feedback 조향) 그러나 exact 경계위반에 미도달.
- **inferred:** exact 자력발견은 budget/seed-rare(node-tar M3와 정합 — budget 100=0, 자율 트리거는
  budget 1500+특정 seed). arm 차분(A3 11 > A1 8)은 1-seed라 검정력이 없다(EN-008, rate/effectiveness
  아님) → autoloop 7.1상 당시 **미판정**이었고, §5.4.3의 powered 통합 반복에서 검정력 있게 판정한다.

### 5.4.3 decompress powered 판정 — 검정력 있는 정직 음성

M4.4의 검정력 없는 음성을 더 큰 사전고정 예산·복수 seed로 독립 반복해 판정했다. 맥(arm64)과
윈도우(x86_64) 두 아키텍처에서 각각 실행한 결과를 right-censored로 합산한
[통합 verdict](../../experiments/summaries/m4-5-decompress-selfdiscover-unified-v1.md)다.

- **설정(사전등록):** 실제 decompress 4.2.1 AFFECTED, production backend(격리계약·완화 플래그 0),
  A1 random vs A3 state-aware. 윈도우 seed {500..509}, 맥 seed {11,85,163,211,307,401}(교집합 ∅).
- **결과(observed):** 양 arm **C1/C2 0/14**(Wilson 95% CI [0, 0.215]), 맥+윈도우 pooled
  **0/28 (Wilson 95% CI ≤ 0.121) = 검정력 있는 정직 음성**. C0(path-boundary)는 **12/14** 자력도달
  하나 arm 우위는 없다(C0은 identity 관찰 불요). 교차-arch 바이트동일은 주장하지 않는다.
- **판정:** 2번째 extractor에서 자력발견 루프는 **기능 작동**하고 path-boundary(C0)를 자력도달하나,
  identity/effect 경계위반(C1/C2)은 이 예산에서 미도달이다(node-tar M3 seed-rare와 정합). 이는
  **generality(oracle/adapter)≠self-discovery(루프 작동)≠effectiveness(발견)**의 구분을 지킨 음성
  결과이며 effectiveness 주장이 아니다.

### 5.4.4 3번째 extractor (oras-go) 자력발견 native run — right-censored 음성 (observed)

oras-go(Go, compiled 3rd-party)를 effect 캠페인 퍼즈 타깃으로 연결해 native run을 실행했다
([M4.7 요약](../../experiments/summaries/m4-7-oras-go-selfdiscover-v1.md)). compiled 바이너리라
link call interpose가 불가해 post-extraction 상태 SET 채널에서 `inodefence-boundary-attempt-v1`
frame을 파생한다(decompress의 fs-wrap보다 좁다).

- **설정(사전등록):** 실제 oras-go v2.6.1 AFFECTED, production backend(격리 완화 0), budget 200 ×
  seed 11 × 2 arm(A3/A1).
- **결과(observed):** 양 arm **C0/C1/C2 0/1**(Wilson 95% CI [0, 0.793]) = right-censored 음성.
  compiled 채널이라 attempt-key가 양 arm 0이고 arm 우위도 없다. budget 200·1 seed라 **검정력이
  약한** 음성이다(과대주장 없음).
- **판정:** 3번째 독립 extractor에서도 자력발견 effectiveness는 음성이다. generality=oracle/adapter
  수준(§5.4.1)이며 self-discovery 루프는 작동하나 발견은 미도달.

## 5.5 Capability Ledger 요약

M1–M4의 능력과 증거 수준을 한눈에 보는 요약은 [Capability Ledger 요약표](../tables/capability-ledger-summary.md)에
두며, 단일 기준은 [`../../docs/STATUS.md`](../../docs/STATUS.md)다.
