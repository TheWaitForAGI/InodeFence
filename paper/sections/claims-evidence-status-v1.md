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
| C-M3a-1 | 영향 릴리스 7.5.2에서 **외부 객체 이름을 mutation 어휘에 획득한 조건(A3full)에서 자율 경계위반이 관찰됐다**(s11=21 vs 이름을 뺀 A3blind 0 vs 철자 불가 A1 0; **멀티-seed**: powered 매칭 런의 신규 disjoint seed s101 완주 C1 + s118 observed-trigger로 반복) | **paper-ready**(observed; "blind 발견 아님"·"동일 어휘 통제 없음" 명시 필수) | raw `~/inodefence-evidence/{m3-scale-full,m3-ablation,m3-repro}` → [M3 validated summary](../../experiments/summaries/node-self-discovery-mechanism-v1.md) + powered 매칭 [verdict v2](../../experiments/summaries/m3-powered-matched-verdict-v2.md)(#200) → Ledger M3 행/마일스톤 M3(PR #151) |
| C-M3a-2 | **inode/effect retention 피드백 자체의 인과 기여**(동일 어휘 아래 S-u가 R·D보다 위반에 먼저·더 많이 도달) | **미검증** — 기존 blind 대조는 어휘를 통제해 분리 불가; 어휘 동등 R/D/S 비교(EXP-3, 2026-11-18 사전등록) 이후 판정 | [research-questions v2](../../docs/research/design/research-questions.md) H-A · [exp0-pilot-v2](../../experiments/preregistration/exp0-pilot-v2.md) |
| C-M3b | **상태-인지 피드백이 무작위보다 C1을 더 빨리/많이 찾는다(rate 우위, H1 effectiveness)** | **사전등록 판정: rate CI 미분리(검정력 부족)** — 주 주장 아님 | powered 매칭 런 완료(A1 vs A3full, budget 2000, disjoint seed 100–119): 완주 clean C1 A3full 1/10 vs A1 0/12, 매칭 Wilson CI 겹침(`complete_hit_wilson_intervals_separate=False`) → rate 우위 미입증(~0.1 효과 검정력 부족). raw `~/inodefence-evidence/m3-powered-matched-20261030` → [powered verdict](../../experiments/summaries/m3-powered-matched-verdict-v1.md)(#196). 논문 본문 확정 rate 주장 금지(보조·탐색적) |
| C-M4a | 동일 generic C0/C1/C2 oracle이 **3개 독립 extractor**(python-tarfile·oras-go·decompress)에서 adapter로 경계위반을 포착 | **paper-ready**(단 **oracle/adapter 수준 일반성에 한정**) | Ledger M4 행/마일스톤 M4(통제 reference 차분 + container-integration; `tests/test_python_tarfile_generality.py` 등) |
| C-M4b | 2·3번째 extractor에서 **퍼저 자력 발견** 일반성 | **완료 아님(루프 작동·실행, 발견은 음성)** | 자력발견 루프가 decompress(2번째)·oras-go(3번째)에서 실제 실행됨 — decompress 통합 C1/C2 **0/28 Wilson≤0.121(검정력 있는 음성, #198)**, oras-go **0/1 Wilson[0,0.793](약한 음성, #197)**; C0(path-boundary)는 자력도달하나 identity/effect 미도달. [M4.5 통합 verdict](../../experiments/summaries/m4-5-decompress-selfdiscover-unified-v1.md)·[M4.7 oras-go](../../experiments/summaries/m4-7-oras-go-selfdiscover-v1.md). generality(oracle/adapter=C-M4a)≠self-discovery(루프 작동)≠effectiveness(발견). 발견 effectiveness 주장 아님 |
| C-ABCD | item-3 A/B/C/D 중간상태 gradient: gradient(C/D)>random(A)>structure(B); **identity-state(C)≡coverage(D)** | **보조/탐색적만**(effectiveness 랭킹 아님) | Ledger "feedback effectiveness" 행 PASS 2. terminal C1 0/21 Wilson[0,0.155]. escape-hardlink 문법 한정 negative(C≡D 중복), 범위 밖 일반화 금지. EN-008(새 state 수 ≠ effectiveness) |

## 증거 파일 매핑 (실험 ID·raw manifest·통계 파일·결과 버전)

위 현황표의 각 C-ID를 그 증거 파일로 잇는 열 확장이다(C-ID는 위와 동일). raw manifest는 raw 바이트의
보존 체크섬 목록([보존 상태](../../experiments/summaries/README.md) 참조), 통계 파일은 수치를 만든
분석 스크립트/요약, 결과 버전은 해당 요약·verdict 버전이다. 경로는 코드 span으로 둔다.

| C-ID | 실험 ID | raw manifest 파일 | 통계 파일(분석·요약) | 결과 버전 |
| --- | --- | --- | --- | --- |
| C-M1 | M1 effect-demo-native (`make demo`) | `raw-manifest-win-20261104.sha256`(2026-11-01 demo)·`raw-manifest-mac-20261103.sha256`(demo/historical) | 엔지니어링 능력(통계 없음); 재현 검증 `scripts/replay_report.py`(`make replay`) | `make demo`/`make replay`(호스트) |
| C-M2 | M2 cross-release identity repro (R1·R2) | 해당 없음 — in-repo raw `experiments/repro/evidence/summary.json` | `cross-release-identity-repro-v1.md` | v1 |
| C-M3a-1 | M3 `m3-scale-full`·`m3-ablation`·`m3-repro`·`m3-powered-matched-20261030` | `raw-manifest-mac-20261103.sha256` | `node-self-discovery-mechanism-v1.md`·`m3-powered-matched-verdict-v2.{json,md}`; `scripts/determine_m3_powered_cells.py`·`scripts/analyze_m3_3_control.py` | self-discovery v1 + powered-matched v2 |
| C-M3a-2 | EXP-3 어휘 동등 R/D/S (사전등록 예정) | 해당 없음 — 미실행 | `experiments/preregistration/exp0-pilot-v2.md` | 미검증 |
| C-M3b | `m3-powered-matched-20261030` (A1 vs A3full, budget 2000, seed 100–119) | `raw-manifest-mac-20261103.sha256` | `m3-powered-matched-verdict-v1.md`; `scripts/determine_m3_powered_cells.py`·`scripts/analyze_m3_3_control.py` | v1 (rate CI 미분리) |
| C-M4a | M4 adapter generality (python-tarfile·oras-go·decompress) | 해당 없음 — 테스트 기반 | `tests/test_python_tarfile_generality.py` 등 generality 테스트 | 해당 없음(TESTED) |
| C-M4b | M4.5 decompress selfdiscover (win `{500..509}`·mac `{11,85,163,211,307,401}`); M4.7 oras-go (seed 11) | `raw-manifest-win-20261104.sha256`(win decompress)·`raw-manifest-mac-20261103.sha256`(mac decompress·oras-go) | `scripts/analyze_m4_5_unified.py`→`m4-5-decompress-selfdiscover-unified-v1.md`; `scripts/analyze_m4_7_oras_go_selfdiscover.py`→`m4-7-oras-go-selfdiscover-v1.md`; win 단독 `scripts/analyze_m4_5_selfdiscover.py`→`m4-5-decompress-selfdiscover-win-v1.md` | unified v1(음성)·oras-go v1(음성) |
| C-ABCD | `m3-item3-abcd-20261030` | `raw-manifest-mac-20261103.sha256` | `scripts/analyze_m3_item3.py` | 보조·탐색적(버전 미할당) |

raw manifest가 "해당 없음"인 행은 raw가 저장소 안(C-M2)이거나 테스트/사전등록(C-M4a·C-M3a-2)이라 host-local
raw manifest 대상이 아니다. win manifest의 생성·검증은 `scripts/make_raw_manifest.py`, 각 요약의 raw
포인터가 manifest/저장소에 닿는지는 `scripts/check_evidence_chain.py`로 점검한다.

## 완료 아님 항목의 취급(명시)

- **C-M3b (rate 우위)**: powered 매칭 런으로 **사전등록 판정 완료 — rate CI 미분리(검정력 부족)**.
  논문 본문에서 effectiveness 우위를 **주 주장으로 쓰지 않는다**. 주 주장은 C-M2(통제 재현)와
  C-M3a-1(이름 획득 조건 관찰, 멀티-seed 반복; 피드백 인과 C-M3a-2는 미검증)다. CI 분리된 rate 주장은 사람-게이트 대예산
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
하드코딩 없이 관통한다, (C-M3a-1) 기존 실험은 외부 객체 이름을 mutation 어휘에 획득한 조건에서 경계위반이
관찰되었음을 보여준다 — 동일 어휘로 통제하지 않았으므로 inode/effect retention 피드백 자체의 인과적 기여는
아직 입증되지 않았다(C-M3a-2 미검증; blind 발견 아님).
