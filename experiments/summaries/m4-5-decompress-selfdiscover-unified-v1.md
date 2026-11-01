# M4.5 decompress 자력발견 대예산 독립반복 — 통합(맥 arm64 + 윈도우 x86_64) validated summary v1

M4(일반성) 밀스톤의 **decompress 2번째 extractor 자력발견 대예산 독립반복의 최종 통합 verdict**다.
두 실험 호스트가 **disjoint seed**로 같은 사전등록 프로토콜(budget 1500)을 돌렸다: 윈도우 x86_64
`{500..509}`, 맥 arm64 `{11,85,163,211,307,401}`. 이 문서는 둘을 하나의 right-censored
by_contract(C0/C1/C2) roll-up으로 합산한다(교집합 ∅ 확인 후). [summaries 규칙](README.md)의 체인:

```text
raw:
  - 윈도우: 윈도우 호스트 로컬(저장소 미반입) → published roll-up m4-5-decompress-selfdiscover-win-v1.json
  - 맥: ~/inodefence-evidence/m4-powered-20261030/inodefence-decompress-selfdiscover-m4p-{sa,a1}-s{11,85,163,211,307,401}.json
        (이 맥 호스트 로컬, Git ignore) + 동명 .log
  → unified roll-up: m4-5-decompress-selfdiscover-unified-v1.json (이 폴더, evaluation.right_censored 재사용)
  → validated summary: 이 문서
  → finding: 아래 "## Finding"
  → 능력 원장(단일 기준): ../../docs/STATUS.md (Capability Ledger M4 / 마일스톤 M4), ../../docs/BACKLOG.md M4.5
```

재생성:

```bash
PYTHONPATH=src python scripts/analyze_m4_5_unified.py \
  --mac-glob "$HOME/inodefence-evidence/m4-powered-20261030/*m4p-*.json" \
  --windows-rollup experiments/summaries/m4-5-decompress-selfdiscover-win-v1.json \
  --json-out experiments/summaries/m4-5-decompress-selfdiscover-unified-v1.json
```

observed(실행 출력)와 inferred(추론)를 구분한다. 윈도우 raw byte는 그 호스트 로컬이라 이 통합은 published
윈도우 roll-up에서 per-seed outcome을 **재구성**하고, 그 재구성이 published 숫자(complete·hit·Wilson·abort)를
그대로 재현하는지 스크립트가 **assert**한다(전사 오류 차단). 맥은 raw JSON을 재현 가능한 변환(위 재생성 명령)으로
직접 읽었다. 숫자를 지어내지 않았다.

## 실험 설정 (provenance, 양 호스트)

| 항목 | 윈도우 (x86_64) | 맥 (arm64) |
| --- | --- | --- |
| 호스트 | Docker Desktop WSL2 x86_64 | OrbStack arm64 (engine 29.8.2) |
| target | decompress 4.2.1 AFFECTED, image `sha256:d229fdff…`, node 22.23.4 | decompress 4.2.1 AFFECTED, node 22.23.4 (image id는 evidence에 미기록=SKIP_BUILD 재사용; 동일 `tools/decompress/Dockerfile` 레시피 — inferred) |
| producer | `native-decompress[decompress=decompress@4.2.1;node=22.23.4]` | 동일 (raw producer 필드 확인) |
| 실행경로 | production ContainerExecutionBackend (컨트롤러 내 non-root Linux, 격리계약·완화 플래그 0, disposable sandbox+sentinel) | 동일 |
| 사전등록 | docs/LOG.md 2026-10-30 18:05 (commit 5361c62); batch1 {500..519} 중 {500..509} 실행, {510..529} deferred | 맥 set {11,85,163,211,307,401}은 그 18:05 사전등록에서 예약; 같은 프로토콜로 실행(raw + per-seed .log 관찰) |
| arms | A3 state-aware = `uniform-generic-m1-state-aware-escape-hardlink-v1` (관찰 snapshot 이름[outside·sentinel.txt] 조합 → **blind 아님, disclose**); A1 random = `uniform-generic-v1` (관찰·토큰 없는 random floor) | 동일 (raw config `mutation_policy` 확인) |
| budget / scheduler | 1500 / adaptive | 동일 |
| seeds | {500,501,502,503,504,505,506,507,508,509} (10) | {11,85,163,211,307,401} (6) |
| hit 기준 | registered = `discovered_violation`(any step `contract_violated`); by_contract = step oracle C0/C1/C2 각각 (oracle 로직 불변) | 동일 |
| complete | `observations == eligible_observations == execution_budget`(1500); fail-closed abort = infra-incomplete → 분모 제외·별도 보고 | 동일 |

통합 분모: 윈도우{500..509} ∩ 맥{11,85,163,211,307,401} = **∅ (disjoint, combined 16 seeds)**. 두
아키텍처는 **독립 반복**으로 합산한다 — decompress 교차-arch 바이트동일은 주장하지 않는다(arch = disclosed
variable).

## Result — 통합 right-censored (observed)

per-arm, by_contract (맥 + 윈도우 합산; Wilson 95% CI; fail-closed abort = 분모 제외):

| arm | contract | 맥 arm64 | 윈도우 x86_64 | **통합** | Wilson95 |
| --- | --- | --- | --- | --- | --- |
| A1 random | C0 path (baseline) | 4/4 | 8/10 | **12/14** | [0.601, 0.960] |
| A1 random | C1 identity (novel) | 0/4 | 0/10 | **0/14** | [0, 0.215] |
| A1 random | C2 effect (novel) | 0/4 | 0/10 | **0/14** | [0, 0.215] |
| A3 state-aware | C0 path (baseline) | 4/5 | 8/9 | **12/14** | [0.601, 0.960] |
| A3 state-aware | C1 identity (novel) | 0/5 | 0/9 | **0/14** | [0, 0.215] |
| A3 state-aware | C2 effect (novel) | 0/5 | 0/9 | **0/14** | [0, 0.215] |

- fail-closed abort(관찰무결성 STOP, EN-008 observer-side 비결정; 각 abort 전 C1/C2 0 observed):
  A1 맥 {307, 401}·윈도우 {}; A3 맥 {401}·윈도우 {504}. 사유 — "container runtime cleanup inspect failed"
  외 맥 a1-s401은 "trusted Docker broker disconnected". 영구 incomplete로 분모 제외(denominator 미증가).
- **novelty 종합(양 arm pooled — 음성이라 arm 구분이 무의미해 단일 음성 headline으로만 합산)**:
  **C1 0/28 Wilson95 [0, 0.121]**, **C2 0/28 [0, 0.121]**.
- 맥 세부: A3-s11은 **C0도 미도달(censored)** — budget 내 경로경계조차 자력으로 넘지 못한 유일 완주 셀.
- 기작 집계(rate 아님, EN-008): A3 state-aware가 경계접근 변이를 더 밀지만(윈도우 rejected 11110 vs A1 8625)
  C1/C2 전환은 0. 통합에서도 C0 arm 동률(12/14 = 12/14).

## Finding

**observed (통합):** 실제 decompress 4.2.1 AFFECTED에서 generic effect-campaign 루프가 **경로경계(C0)를
양 arm·양 아키텍처에서 자력으로 넘는다** — 통합 A1 12/14·A3 12/14 (Wilson95 [0.601, 0.960]), PoC·대상경로
하드코딩 없이. **identity(C1)·effect(C2)는 양 arm·양 아키텍처 모두 0** — 통합 0/14 per arm(Wilson 상한
≤0.215), 양 arm 종합 0/28(상한 ≤0.121) = **검정력 있는 정직한 right-censored 음성**. C0은 통합에서 arm
동률(12/14 = 12/14) = **arm 우위 없음**.

**inferred:** C0 탈출은 object-identity 관찰이 필요 없어(`../` 상대경로/symlink 변이만으로 추출 루트 이탈)
random도 도달 — state-aware 우위 부재가 당연하다. C1/C2(외부 객체와 inode 공유/효과)는 그 대상을 **관찰**로
얻어야 하므로 budget 1500·16 seed·2 arch에서 미도달 = node-tar M3의 seed-rarity(65 seed 중 s11만
C1@budget1500)와 정합. 이번 음성은 "도달 불가 증명"이 아니라 "이 예산 내 미관찰"이다(right-censored).

**3-way 교차일치:** 이 통합 음성은 #4 decompress A/C/D(terminal C1/C2 0/24, C0 path 9/24 자력도달)와
윈도우-단독 M4.5(C1/C2 0, C0 8/10·8/9)와 정합 — 같은 extractor·문법에서 **C0 자력도달 + C1/C2 음성**이
세 독립 실험에서 반복된다.

**범위·claim 경계(필수 명시):**

- **generality**(generic oracle/adapter를 2번째 extractor에 적용; 이미 python-tarfile·oras-go·decompress 3
  extractor 확보) ≠ **self-discovery**(이 루프가 2번째 extractor에서 작동하고 C0를 **자력도달** = 양성) ≠
  **effectiveness**(state-aware의 rate 우위 — 주장 없음: C0 arm 동률, C1/C2 0).
- escape-oriented grammar라 C0은 **blind 재발견이 아니다**(disclose). A3는 관찰 snapshot 이름 조합이라
  **blind 아님**(disclose). 변이 어휘·oracle에 CVE/대상경로/sentinel/정답seed/근접보상 하드코딩 0.
- **교차-arch 바이트동일 미주장**(맥 arm64·윈도우 x86_64는 같은 프로토콜의 독립 반복). 윈도우 per-seed
  outcome은 published roll-up에서 재구성하며 스크립트가 재현을 assert; 윈도우 raw byte는 이 호스트에 없다
  (observed/inferred 경계).
- 새 취약점 발견·effectiveness 주장 아님. decompress 4.2.1은 기존 취약(CWE-59 계열)이고 C0 자력도달은 루프
  작동의 증거다. oracle 로직 불변.
