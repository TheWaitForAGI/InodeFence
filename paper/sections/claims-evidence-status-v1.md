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
| C-HA | **inode/effect retention 피드백 자체의 인과 기여**(동일 어휘 아래 S-u가 R·D보다 위반에 먼저·더 많이 도달) | **미검증** — 어휘 동등 R/D/S-u 등록 실험(EXP-3 train·EXP-2 holdout, 2026-11-13 동결)의 봉인 해제 뒤 판정 | [research-questions v2](../../docs/research/design/research-questions.md) H-A · [exp0-pilot-v2](../../experiments/preregistration/exp0-pilot-v2.md) |
| C-M4a | 동일 generic C0/C1/C2 oracle이 **3개 독립 extractor**(python-tarfile·oras-go·decompress)에서 adapter로 경계위반을 포착 | **paper-ready**(단 **oracle/adapter 수준 일반성에 한정**) | Ledger M4 행/마일스톤 M4(통제 reference 차분 + container-integration; `tests/test_python_tarfile_generality.py` 등) |

## 증거 파일 매핑 (실험 ID·raw manifest·통계 파일·결과 버전)

위 현황표의 각 C-ID를 그 증거 파일로 잇는 열 확장이다(C-ID는 위와 동일). raw manifest는 raw 바이트의
보존 체크섬 목록([보존 상태](../../experiments/summaries/README.md) 참조), 통계 파일은 수치를 만든
분석 스크립트/요약, 결과 버전은 해당 요약·verdict 버전이다. 경로는 코드 span으로 둔다.

| C-ID | 실험 ID | raw manifest 파일 | 통계 파일(분석·요약) | 결과 버전 |
| --- | --- | --- | --- | --- |
| C-M1 | M1 effect-demo-native (`make demo`) | `raw-manifest-win-20261104.sha256`(2026-11-01 demo)·`raw-manifest-mac-20261103.sha256`(demo/historical) | 엔지니어링 능력(통계 없음); 재현 검증 `scripts/replay_report.py`(`make replay`) | `make demo`/`make replay`(호스트) |
| C-M2 | M2 cross-release identity repro (R1·R2) | 해당 없음 — in-repo raw `experiments/repro/evidence/summary.json` | `cross-release-identity-repro-v1.md` | v1 |
| C-HA | EXP-3 train·EXP-2 holdout 어휘 동등 R/D/S-u (등록, 2026-11-13 동결) | 봉인 해제 뒤 기입 | `experiments/preregistration/exp3-v1.md`·`exp2-v1.md` | 미검증 |
| C-M4a | M4 adapter generality (python-tarfile·oras-go·decompress) | 해당 없음 — 테스트 기반 | `tests/test_python_tarfile_generality.py` 등 generality 테스트 | 해당 없음(TESTED) |

raw manifest가 "해당 없음"인 행은 raw가 저장소 안(C-M2)이거나 테스트(C-M4a)라 host-local
raw manifest 대상이 아니다. win manifest의 생성·검증은 `scripts/make_raw_manifest.py`, 각 요약의 raw
포인터가 manifest/저장소에 닿는지는 `scripts/check_evidence_chain.py`로 점검한다.

## 수술 3단계 도구·증거 행 (완료 아님 / 도구 검증 / 대기)

아래는 수술 3단계에서 나온 **도구·증거 행**이다. **능력(claim) 주장이 아니다** — 도구 검증·증거 수집
상태이며, 위 현황표의 어떤 **C-ID paper-ready 판정도 바꾸지 않는다.** 전부 "완료 아님 / 도구 검증 / 대기"로
표기하고, 관찰 사실과 다른 레인의 보고를 구분한다(provenance는 이 호스트에서 재확인한 값만 "재확인"으로 표시).

| 항목 | 상태 | provenance / 증거 |
| --- | --- | --- |
| G1 조건 1–3 (unregistered) | 도구 검증 (레인 5 보고; EXP-0 사전등록 아님) | 통합 브랜치 `4b072a5`, image `sha256:22c8734f…`, completion index `sha256 fc748d68…`·smoke index `sha256 26235b44…` (둘 다 이 호스트 디스크 재확인), raw `g1-20261104/` (manifest `raw-manifest-win-20261104-1421.sha256`) |
| 네이티브 observer 13런 | 도구 검증 (레인 2 보고; 해시 무결성만 독립 재확인) | `s3-observer-20261104/` 26파일 SHA-256 26/26 독립 재해시 일치; 레인 2 보고 = abort 0, budget ≤100에서 `malformed_identity` 미발생·분기 아티팩트 없음(이 세션에서 재현 안 함) |
| 워커풀 parity | **PASS (도구 검증, unregistered)** | a1 vs b 4차원 agree · 재시도 0 · self-determinism PASS; 결과 SHA `a700c06c…`/`fb1a21b0…`; 처리량 동등(speedup 1.002, 50-step 1셀 값). 워커풀의 값은 처리량이 아니라 **리셋 검증 + 인프라 재시도 견고성**이다. 능력 주장 아님(G1 조건 4). **EXP-0 측정 항목 4는 미충족**이다: 등록 실행은 per-case뿐이고 이 비등록 결과가 등록 측정을 대신하지 않는다(`experiments/summaries/exp0-20261105-report.md` 편차 3) |
| 증거 보존·검증 도구 | 도구 검증 (구현·테스트 통과; 외부 백업 미완) | `make_raw_manifest.py`(`--verify`/`--exclude-suffix`), `check_evidence_chain.py`(`make check` 연결), `make replay`, `make_evidence_bundle.py`(로컬 번들만, 업로드 0). PR #208·#211·#215·#226 |
| EXP-0 seed 사전 노출(pre-exposure) | 공개 사실 (완료 아님 범주) | 동결 전 비등록 실행이 EXP-0 seed `{9001..9004}`를 budget 50으로 선행 실행: seed 9001은 10런(G1 smoke 3, G1 completion 3, parity `s3wp` 3, 타이밍 대조 1), 9002–9004는 G1 smoke 각 3런. v2.1 미공개 6런, 노출 원장 누락 `s3wp` 3런(`experiments/summaries/exp0-20261105-report.md` 편차 9). smoke `7.5.2-D-s9002` step 42 C2 1건(raw 재확인). `experiments/preregistration/exp0-pilot-v2.1`(`23e5c66` 동결)·[보존 상태표](../../experiments/summaries/README.md) 기록 |

이 표의 어떤 행도 novelty·effectiveness·일반성 주장으로 승격하지 않는다. G1·observer·parity는 **인프라/도구
검증**이고, 사전 노출은 **정직성 공개**다. EXP-0은 인프라 측정이라 가설을 판정하지 않는다. H-A 판정은 EXP-3 사전등록(동결 후)과
그 결과에만 근거한다.

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
하드코딩 없이 관통한다. retention 피드백의 효과(C-HA)는 등록 실험의 봉인 해제 전까지 미검증이다.
