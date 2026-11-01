# M4.7 oras-go native 자력발견 캠페인 (arm64) — validated summary v1

M4(일반성) 밀스톤의 **3번째 extractor(oras-go) 자력발견 native run**의 검증된 작은 요약이다.
[summaries 규칙](README.md)의 체인을 명시한다:

```text
raw: ~/inodefence-evidence/inodefence-oras-go-selfdiscover-m4sd-oras-{sa,a1}-s11.json (호스트 로컬, Git ignore)
  → machine-readable roll-up: m4-7-oras-go-selfdiscover-v1.json (이 폴더, evaluation.right_censored 재사용)
  → validated summary: 이 문서
  → finding: 아래 "## Finding"
  → 능력 원장(단일 기준): ../../docs/STATUS.md (Capability Ledger M4 행 / 마일스톤 M4), ../../docs/BACKLOG.md M4.7
```

이 요약은 raw JSON을 **재현 가능한 변환**(아래 재생성 명령)으로 읽은 것이며 raw 없이 숫자를 지어내지
않았다. observed(실행 출력)와 inferred(추론)를 구분한다. raw per-arm JSON은 이 호스트 로컬이고
저장소에 반입하지 않는다(대량 raw는 Git ignore, summaries 규칙).

## 실험 설정 (provenance)

| 항목 | 값 |
| --- | --- |
| 사전등록 | docs/LOG.md 2026-10-30 (M4.7 oras-go native 자력발견), commit `8d0d1bd` (M4.6 PR #193). **실행 전 고정·사후 변경 금지.** 이번 세션이 그 고정값(seed 11·budget 200·2 arm)을 그대로 실행 |
| InodeFence branch | claude/oras-go-m47-native-09c127 (M4.6 코드 = main `8d0d1bd` 기반) |
| target | oras-go v2.6.1 AFFECTED (ROLE=affected, image `inodefence-oras-go-selfdiscover:affected` id `sha256:06a29cb837ceb1db582251f890b3abe1b3a4a752f003fefc945e418424d53aae`), go1.25.14 |
| producer | `native-oras-go[oras-go=v2.6.1;go=go1.25.14]` (실제 oras-go, synthetic 아님) |
| 실행 경로 | production ContainerExecutionBackend (컨트롤러 내 non-root Linux, 격리계약·완화 플래그 0, disposable sandbox+sentinel) via `scripts/local_oras_go_selfdiscover.sh` + container_controller `oras-go-effect-campaign` 모드 |
| 관찰 채널 | oras-go는 compiled 3rd-party → link call interpose 불가, **post-extraction state SET frame**(`inodefence-boundary-attempt-v1`). decompress의 fs-wrap set·node-tar의 ordered per-op 채널보다 **좁음** — cleanly refused attempt 미관찰 (disclose) |
| arms | A3 state-aware identity = `uniform-generic-m1-state-aware-escape-hardlink-v1` (관찰 snapshot 이름[outside·sentinel.txt] 조합 → **blind 아님, disclose**); A1 random = `uniform-generic-v1` (관찰·토큰 없는 random floor) |
| seeds | {11} × {A3,A1} = 2 campaign. 각 campaign random_seed=11, execution_budget=200, adaptive scheduler |
| hit 기준 | 등록 hit = `discovered_violation` = any step `contract_violated` (generic oracle C0/C1/C2 on before/after, **oracle 로직 불변**). **사전등록 HIT = generic C1/C2.** 분석은 arm별 by_contract(C0/C1/C2 각각)로 분리 |
| 동시성 | jobs 2 (A3+A1 동시, RUN_ID 격리 m4sd-oras-sa-s11 / m4sd-oras-a1-s11), 형제 레인 docker 양보. 호스트 load 저부하 |
| OS/arch | macOS arm64 (이 맥 네이티브 docker 호스트), OrbStack docker 29.8.2 |

## Result (observed)

재생성: `PYTHONPATH=src python scripts/analyze_m4_7_oras_go_selfdiscover.py ~/inodefence-evidence/inodefence-oras-go-selfdiscover-m4sd-oras-*-s11.json`

| arm | complete | C0 path (baseline) | C1 identity (novelty) | C2 effect (novelty) | right-censored | fail-closed abort |
| --- | --- | --- | --- | --- | --- | --- |
| A1 random | 1 | 0/1 · Wilson95 [0, 0.793] | 0/1 · [0, 0.793] | 0/1 · [0, 0.793] | 1 | 0 |
| A3 state-aware | 1 | 0/1 · Wilson95 [0, 0.793] | 0/1 · [0, 0.793] | 0/1 · [0, 0.793] | 1 | 0 |

- 양 arm 완주(200/200 observations, eligible 200, abort 0). 실제 oras-go v2.6.1 실행(frames_observed 200/200 per arm).
- 기작 집계(rate 아님, EN-008): **양 arm 모두 unique_attempt_keys 0·violation_fingerprints 0·retained 1/200.** terminations A3 rejected 170/success 30, A1 rejected 169/success 31. → 좁은 post-state 채널이 **양 arm 공히 boundary-attempt 키 0** → state-aware arm(A3)이 받을 차등 gradient 없음, A3≈A1.
- 통합: node-tar seed·decompress M4.4{11}·M4.5 seed와 arm/extractor가 달라 교차 합산 대상 아님. oras-go 단독 3번째 extractor 데이터포인트.

## Finding

**observed:** 실제 oras-go v2.6.1 AFFECTED에서 generic effect-campaign 루프가 **3번째 extractor에서 기능적으로 작동**한다 — 양 arm 200/200 frames observed, 실제 oras-go 실행(producer native-oras-go, synthetic 아님), mutation→실행→generic oracle→feedback→next 루프 완주. **그러나 C0·C1·C2 전부 0 (양 arm) — right-censored 음성**(Wilson95 [0, 0.793]). 사전등록 HIT(generic C1/C2) 미도달.

**inferred:** oras-go는 compiled 3rd-party라 link call interpose가 불가능해 관찰 채널이 **post-extraction state SET frame** 하나뿐이고(refused attempt 미관찰), 이번 실행에서 양 arm 모두 boundary-attempt 키 0을 파생했다. 그래서 state-aware arm(A3)이 관찰 이름으로 밀 차등 gradient를 받지 못해 A3가 random(A1)과 사실상 동일(terminations·keys 동률) = **arm 우위 없음**. C1/C2(외부 객체와 inode 공유/효과)는 그 대상을 관찰로 조합해야 하는데 좁은 채널이 이를 공급하지 못하고, AFFECTED 표면(CVE-2026-50163 = 하드링크 Linkname의 process-CWD 해석)은 node-tar s11처럼 seed-rare다 → budget 200·1 seed에서 미도달. node-tar M3(65 seed 중 s11만 C1, budget 100=0)·decompress M4.4(right-censored 음성)와 정합.

**범위:** 이는 **자력발견 루프의 일반성**(3번째 extractor oras-go에서 루프가 기능 작동)과 **novelty(C1/C2)의 정직한 경계 획정**(가용 예산·좁은 채널 내 미도달)이다. generality(oracle/adapter — 이미 3 extractor 확보) ≠ self-discovery(이 루프가 3번째 extractor에서 작동) ≠ effectiveness(rate 미주장). 1 seed/arm = 검정력 없음 → autoloop 7.1상 미판정; 더 큰 사전고정 예산·복수 seed 독립반복이 다음(node-tar M3/decompress M4.5 패턴). oras-go v2.6.1은 기존 취약(CVE-2026-50163)이고 이 음성은 **좁은 관찰 채널 + 작은 예산의 함수**이지 extractor 안전성 주장이 아니다. 변이 어휘·oracle에 CVE/대상경로/sentinel 하드코딩 없음(region 기반, D005/D006); A3는 관찰 이름 조합이라 blind 아님(disclose). 정직한 음성 = H1의 정당한 결과.
