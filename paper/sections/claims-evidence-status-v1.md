# 논문 주장 ↔ 증거 사슬 현황 v1

이 문서는 논문에 쓸 **각 주장**이 어떤 증거 사슬로 뒷받침되는지, 그리고 지금 **방어 가능한지
(paper-ready)** 아니면 **완료 아님/진행 중**인지를 한눈에 매핑한다. [paper 규칙](../README.md)의
"각 주장·수치는 출처와 실험 설정에 추적 가능해야 한다"를 충족하는 provenance 지도다.

능력의 **단일 기준은 Capability Ledger**([`../../docs/STATUS.md`](../../docs/STATUS.md))이며, 이
문서는 거기 행을 **가리키기만** 한다(능력 판정을 여기서 새로 하지 않는다). 증거 수준 어휘
(DESIGNED/IMPLEMENTED/TESTED/VALIDATED)와 M1–M4 마일스톤은 Ledger 정의를 그대로 쓴다.

## 증거 사슬 규약

```text
raw experiment output → validated summary → finding → 이 매핑 → Capability Ledger 행
```

주장이 "paper-ready"이려면 이 사슬이 **raw까지 끊김 없이** 닿아야 한다. 사슬이 안 닿거나 열려
있으면 **완료 아님**으로 표시하고 논문 본문의 확정 주장으로 쓰지 않는다.

## 주장 현황표

| # | 논문 주장(요지) | 상태 | 증거 사슬 포인터 |
| --- | --- | --- | --- |
| C-M1 | 실제 node-tar에서 입력→실행→entry별 관찰→C0/C1/C2→feedback→다음 mutation 루프가 돈다 | **paper-ready**(TESTED, 엔지니어링 능력) | Ledger M1 행 1–6 + 마일스톤 M1; `make demo`(호스트) |
| C-M2 | **generic identity oracle 하나**가 릴리스/정답경로 하드코딩 없이 두 root-cause(R1=CVE-2026-23745, R2=CVE-2026-24842)를 통제 재현으로 포착 | **paper-ready**(방어 가능) | raw [`../../experiments/repro/evidence/summary.json`](../../experiments/repro/evidence/summary.json) → [M2 validated summary](../../experiments/summaries/cross-release-identity-repro-v1.md) → Ledger M2 행/마일스톤 M2 |
| C-M3a | 영향 릴리스 7.5.2에서 **object-identity 관찰이 자율 경계위반 발견을 인과적으로 가능케 한다**(2026-11-03 정정: blind 대조는 어휘를 통제하므로 입증된 것은 '외부 객체 이름의 관찰(어휘 획득)이 필요조건'이며 retention·스케줄링 피드백 기여는 R/D/S로 미분리; A3full s11=21 vs identity-blind 0 vs random 0; **멀티-seed**: powered 매칭 런에서 신규 disjoint seed s101 완주 C1 + s118 observed-trigger로 재현, 단일 s11 아님) | **paper-ready**(인과·메커니즘; 단 "blind 발견 아님" 명시 필수) | raw `~/inodefence-evidence/{m3-scale-full,m3-ablation,m3-repro}` → [M3 validated summary](../../experiments/summaries/node-self-discovery-mechanism-v1.md) + powered 매칭 [verdict](../../experiments/summaries/m3-powered-matched-verdict-v1.md)(#196) → Ledger M3 행/마일스톤 M3(PR #151) |
| C-M3b | **상태-인지 피드백이 무작위보다 C1을 더 빨리/많이 찾는다(rate 우위, H1 effectiveness)** | **사전등록 판정: rate CI 미분리(검정력 부족)** — 주 주장 아님 | powered 매칭 런 완료(A1 vs A3full, budget 2000, disjoint seed 100–119): 완주 clean C1 A3full 1/10 vs A1 0/12, 매칭 Wilson CI 겹침(`complete_hit_wilson_intervals_separate=False`) → rate 우위 미입증(~0.1 효과 검정력 부족). raw `~/inodefence-evidence/m3-powered-matched-20261030` → [powered verdict](../../experiments/summaries/m3-powered-matched-verdict-v1.md)(#196). 논문 본문 확정 rate 주장 금지(보조·탐색적) |
| C-M4a | 동일 generic C0/C1/C2 oracle이 **3개 독립 extractor**(python-tarfile·oras-go·decompress)에서 adapter로 경계위반을 포착 | **paper-ready**(단 **oracle/adapter 수준 일반성에 한정**) | Ledger M4 행/마일스톤 M4(통제 reference 차분 + container-integration; `tests/test_python_tarfile_generality.py` 등) |
| C-M4b | 2·3번째 extractor에서 **퍼저 자력 발견** 일반성 | **완료 아님(루프 작동·실행, 발견은 음성)** | 자력발견 루프가 decompress(2번째)·oras-go(3번째)에서 실제 실행됨 — decompress 통합 C1/C2 **0/28 Wilson≤0.121(검정력 있는 음성, #198)**, oras-go **0/1 Wilson[0,0.793](약한 음성, #197)**; C0(path-boundary)는 자력도달하나 identity/effect 미도달. [M4.5 통합 verdict](../../experiments/summaries/m4-5-decompress-selfdiscover-unified-v1.md)·[M4.7 oras-go](../../experiments/summaries/m4-7-oras-go-selfdiscover-v1.md). generality(oracle/adapter=C-M4a)≠self-discovery(루프 작동)≠effectiveness(발견). 발견 effectiveness 주장 아님 |
| C-ABCD | item-3 A/B/C/D 중간상태 gradient: gradient(C/D)>random(A)>structure(B); **identity-state(C)≡coverage(D)** | **보조/탐색적만**(effectiveness 랭킹 아님) | Ledger "feedback effectiveness" 행 PASS 2. terminal C1 0/21 Wilson[0,0.155]. escape-hardlink 문법 한정 negative(C≡D 중복), 범위 밖 일반화 금지. EN-008(새 state 수 ≠ effectiveness) |

## 완료 아님 항목의 취급(명시)

- **C-M3b (rate 우위)**: powered 매칭 런으로 **사전등록 판정 완료 — rate CI 미분리(검정력 부족)**.
  논문 본문에서 effectiveness 우위를 **주 주장으로 쓰지 않는다**. 주 주장은 C-M2(통제 재현)와
  C-M3a(메커니즘 인과, 이번에 멀티-seed로 강화)다. CI 분리된 rate 주장은 사람-게이트 대예산
  pilot(M3.4: N01 토큰·timeout 동결 선행) 뒤에만 보조로 승격한다.
- **C-M4b (2·3번째 extractor 자력 발견)**: "일반성"을 말할 때 **oracle/adapter 수준**임을 반드시
  한정한다(C-M4a). 자력발견 루프는 decompress·oras-go에서 실제 실행됐으나 발견은 검정력 있는/약한
  **음성**(0/28·0/1)으로 표기 — generality≠self-discovery≠effectiveness.
- **C-ABCD**: 중간상태 탐색 거동(search behavior)으로만 서술하고 effectiveness 결론으로 옮기지 않는다.

## 선행연구 포지셔닝 (필수 준수)

[related-work-positioning](../../docs/research/design/related-work-positioning.md)을 그대로 따른다.
Jana & Shmatikov(semantic gap·TAR 공격), ZIPDiff(feedback-guided archive differential),
LinkZard(feedback-driven file-state fuzzing·hardlink/link-count 관찰),
Wormholes(archive-extraction symlink/hardlink composition·creation order)가 이미 다룬 영역이므로,
다음은 **쓰지 않는다**(positioning 문서의 "아직 하면 안 되는 주장"):

- "InodeFence가 최초의 state-guided archive fuzzer다."
- "기존 연구는 inode 정보를 사용하지 않았다 / archive link를 fuzzing하지 않았다 / entry ordering을 보지 않았다."
- "제안 방법이 fixed strategy보다 우수하다 / 여러 extractor에 일반화된다."

논문이 방어하는 것은 좁은 명제뿐이다: (C-M2) outcome 기반 identity oracle 하나가 2개 root-cause를
하드코딩 없이 관통한다, (C-M3a) object-identity 관찰이 이 자율 경계위반 발견을 가능케 한다(없으면
도달 불가; blind 발견 아님).
