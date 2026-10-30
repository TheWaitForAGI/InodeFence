# M4.5 decompress 자력발견 대예산 독립 반복 (x86_64) — validated summary v1

M4(일반성) 밀스톤의 **decompress 2번째 extractor 자력발견 대예산 독립 반복**의 검증된 작은 요약이다.
[summaries 규칙](README.md)의 체인을 명시한다:

```text
raw: ~/inodefence-evidence/inodefence-decompress-selfdiscover-m45-{sa,a1}-s5{00..09}.json (호스트 로컬, Git ignore)
  → machine-readable roll-up: m4-5-decompress-selfdiscover-win-v1.json (이 폴더, evaluation.right_censored 재사용)
  → validated summary: 이 문서
  → finding: 아래 "## Finding"
  → 능력 원장(단일 기준): ../../docs/STATUS.md (Capability Ledger M4 행 / 마일스톤 M4), ../../docs/BACKLOG.md M4.5
```

이 요약은 raw JSON을 **재현 가능한 변환**(아래 재생성 명령)으로 읽은 것이며 raw 없이 숫자를 지어내지
않았다. observed(실행 출력)와 inferred(추론)를 구분한다. raw per-cell JSON은 이 윈도우 호스트 로컬이고
저장소에 반입하지 않는다(대량 raw는 Git ignore, summaries 규칙).

## 실험 설정 (provenance)

| 항목 | 값 |
| --- | --- |
| 사전등록 | docs/LOG.md 2026-10-30 18:05 (batch1 {500..519}, commit 5361c62) + 배치2 {520..529} (746adc0). **실행 전 고정·사후 변경 금지.** 이번 세션 실행분은 그 중 {500..509}; {510..529}는 처리량 한계로 **미실행(deferred)** |
| InodeFence commit | ad384e4 (branch jiwoong/p-m4-5-decompress-selfdiscover-win) |
| target | decompress 4.2.1 AFFECTED (ROLE=affected, image `inodefence-decompress-selfdiscover:affected` id `sha256:d229fdffd7dc7909e67b5c13c6e833356f1e2e92924b02a59a6362901a69b949`), node 22.23.4 |
| producer | `native-decompress[decompress=decompress@4.2.1;node=22.23.4]` (실제 decompress, synthetic 아님) |
| 실행 경로 | production ContainerExecutionBackend (컨트롤러 내 non-root Linux, 격리계약·완화 플래그 0, disposable sandbox+sentinel) via `scripts/local_decompress_selfdiscover.sh` + container_controller `decompress-effect-campaign` 모드 |
| arms | A3 state-aware identity = `uniform-generic-m1-state-aware-escape-hardlink-v1` (관찰 snapshot 이름[outside·sentinel.txt] 조합 → **blind 아님, disclose**); A1 random = `uniform-generic-v1` (관찰·토큰 없는 random floor) |
| seeds | {500..509} × {A3,A1} = 20 campaign. M4.4{11}·맥 M4.5{11,85,163,211,307,401}·node-tar seed와 disjoint (겹침 0, roll-up에서 확인) |
| random seed / budget | 각 campaign random_seed=해당 seed, execution_budget=1500, adaptive scheduler |
| timeout | 별도 wall timeout 없음; budget 1500 또는 fail-closed 관찰무결성 abort 중 먼저 |
| OS/arch | Linux WSL2 x86_64 (Windows 데스크톱 2번째 실험 호스트), Docker Desktop 29.8.0 |
| hit 기준 | 등록 hit = `discovered_violation` = any step `contract_violated` (generic oracle C0/C1/C2 on before/after, **oracle 로직 불변**). complete-campaign hit은 complete=True 필요(right_censored 계약). 분석은 arm별 by_contract(C0/C1/C2 각각)로 분리 |
| 동시성 | conc 6 (실측 throughput 천장; WSL2 step별 컨테이너 생성 직렬화로 conc 10↑ 붕괴). abort 4셀 재실행으로 등록셋 보강 |

## Result (observed)

재생성: `PYTHONPATH=src python scripts/analyze_m4_5_selfdiscover.py ~/inodefence-evidence/inodefence-decompress-selfdiscover-m45-*.json --external-seed-sets '{"mac_m4_5_reserved":[11,85,163,211,307,401]}'`

| arm | complete | C0 path (baseline) | C1 identity (novelty) | C2 effect (novelty) | right-censored | fail-closed abort |
| --- | --- | --- | --- | --- | --- | --- |
| A1 random | 10 | 8/10 · Wilson95 [0.490, 0.943] | 0/10 · [0, 0.278] | 0/10 · [0, 0.278] | 2 (s504·s505) | 0 |
| A3 state-aware | 9 | 8/9 · Wilson95 [0.565, 0.980] | 0/9 · [0, 0.299] | 0/9 · [0, 0.299] | 1 (s509) | 1 (s504, 2회 연속 infra abort) |

- 기작 집계(rate 아님, EN-008): A3 rejected 11110·attempt_keys 124 vs A1 rejected 8625·attempt_keys 112. state-aware가 경계접근 변이를 더 밀지만 C1/C2 전환 0.
- 첫 C0 도달 step(observed-only): A1 [74..786], A3 [78..724]. 전부 `mutate_link_target`·`add_symlink` 계열(symlink/link-target가 추출 루트 이탈 = C0).
- 통합 분모 체크: 윈도우{500..509} ∩ 맥{11,85,163,211,307,401} = ∅ (disjoint 확인). 통합 M4.5 verdict는 C1/C2 기준으로 맥(arm64)+윈도우(x86_64) right-censored 합산(by_contract C1/C2 split 사용). 아키텍처는 변수로 disclose(교차-arch 바이트동일 미주장).

## Finding

**observed:** 실제 decompress 4.2.1 AFFECTED에서 generic effect-campaign 루프가 **경로 경계(C0)를 자력으로 넘는다** — 양 arm 완주분에서 8/10(A1)·8/9(A3), PoC·대상경로 하드코딩 없이 symlink/link-target 변이로. **identity(C1)·effect(C2)는 양 arm 0 — 검정력 있는 right-censored 음성**(Wilson 상한 ≤0.30). C0은 양 arm 동률(8/10 vs 8/9)로 **arm 우위 없음**.

**inferred:** C0 탈출은 object-identity 관찰이 필요 없어(`../` 상대경로만으로 이탈) random도 도달 — state-aware 우위가 없는 게 당연. C1/C2(외부 객체와 inode 공유/효과)는 그 대상을 관찰로 얻어야 해 budget 1500·10 seed에서 미도달 = node-tar M3의 seed-rare(65 seed 중 s11만 C1)와 정합. abort는 observer-side 비결정 성분(EN-008); s504(A3)는 2회 연속 abort로 영구 incomplete 처리(분모 제외, 별도 보고).

**범위:** 이는 **자력발견 루프의 일반성**(2번째 extractor에서 작동·C0 자력도달)과 **novelty(C1/C2)의 정직한 경계 획정**(가용 예산 내 미일반화)이다. generality(oracle/adapter)≠self-discovery(이 루프 시도)≠effectiveness(rate 우위). 새 취약점 발견·effectiveness 주장 아님. decompress 4.2.1은 기존 취약(CWE-59 계열)이고 C0 도달은 루프 작동의 증거다. escape-oriented grammar라 C0은 blind 재발견 아님(disclose).
