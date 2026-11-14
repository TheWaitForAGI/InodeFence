# 주장 목록 ↔ 증거 사슬 현황 v1

이 문서는 결과보고서·소개 영상·논문 **세 산출물이 함께 쓰는 단일 주장 목록**이다(2026-11-14 지웅
지시, 정리 단계 B). 세 산출물은 아래 표의 "쓸 수 있는 말" 범위 안에서만 쓰고, 표에 없는 주장은 쓰지
않는다. 표를 바꿔야 하면 산출물에서 직접 고치지 않고 오케스트레이터에 올린다. [paper 규칙](../README.md)의
"각 주장·수치는 출처와 실험 설정에 추적 가능해야 한다"를 충족하는 provenance 지도다.

근거로 쓸 수 있는 것은 **2026-11-03 독립 감사 이후의 자료**와 **다시 실행해 확인할 수 있는 것**뿐이다.
감사 이전 설계의 실험 결과는 근거로 쓰지 않는다.

능력의 **단일 기준은 Capability Ledger**([`../../docs/STATUS.md`](../../docs/STATUS.md))이며, 이
문서는 거기 행을 **가리키기만** 한다(능력 판정을 여기서 새로 하지 않는다). 증거 수준 어휘
(DESIGNED/IMPLEMENTED/TESTED/VALIDATED)와 M1–M4 마일스톤은 Ledger 정의를 그대로 쓴다. observed는
실행 출력으로 확인한 것, inferred는 관찰에서 끌어낸 해석이다.

## 증거 사슬 규약

```text
raw experiment output → validated summary → finding → 이 매핑 → Capability Ledger 행
```

주장이 "paper-ready"이려면 이 사슬이 **raw까지 끊김 없이** 닿아야 한다. 사슬이 안 닿거나 열려
있으면 **완료 아님**으로 표시하고 논문 본문의 확정 주장으로 쓰지 않는다.

## 쓰는 규칙

1. 문장을 쓸 때 그 행의 증거 수준과 용도 제한을 함께 지킨다. "쓸 수 있는 말"보다 강한 표현으로 바꾸지 않는다.
2. **용도 제한.** 양성 대조(C-PC)와 holdout 버전 선정 점검(C-HOSEL)은 오라클과 측정 사슬의 근거로만 쓰고
   탐색 성능의 근거로 쓰지 않는다. Rust tar(C-RUST)는 "적용된다"까지만 쓴다. python-tarfile은 릴리스
   비교가 아니라 설정 토글 비교임을 밝힌다.
3. **본실험 결과 자리.** EXP-3 train의 arm별 결과와 EXP-2 holdout 결과가 들어갈 곳은 세 산출물 모두
   `본실험 결과 자리(봉인 해제 뒤 기입)`라는 같은 문구의 빈 칸으로 둔다. 봉인 값은 어떤 칸에도 넣지 않는다.
4. **쓰지 않는 말.** "퍼저가 찾았다", "발견", "재발견", "우위", "효과가 있다", "여러 추출기에 일반화된다",
   "새 취약점", "최초". 통제 재현은 "통제 재현이며 퍼저의 탐색 결과가 아니다"로, 추출기 적용은
   "퍼저 탐색의 일반성이나 효과에 대한 주장이 아니다"로 한정한다.
5. **근거 시점.** 근거 경로의 날짜와 SHA는 그 기록이 만들어진 시점의 것이다. 정리 단계 D에서 현재 main으로
   다시 뽑은 뒤에는 새 기록을 가리키도록 이 표를 먼저 고친다.

## 주장 표

| ID | 쓸 수 있는 말 | 증거 수준 · 관찰 구분 | 근거 경로 | 용도 제한 · 쓰면 안 되는 말 |
| --- | --- | --- | --- | --- |
| C-M1 | 실제 node-tar에서 입력 생성 → 실행 → entry별 중간 상태 관찰 → C0/C1/C2 판정 → feedback → 다음 변이 선택의 루프가 한 명령(`make demo`)으로 반복 실행된다 | TESTED · observed (엔지니어링 능력, `demo run`) | Ledger M1 행과 마일스톤 M1([STATUS](../../docs/STATUS.md)); `docs/LOG.md` 2026-11-06 "시연 대본 명령 실행 검증" 줄(main `23e5c66`); `paper/figures/make-demo-screen.png`(2026-11-07 기록 재생); 재생 검증 `make replay`(`scripts/replay_report.py`) | 루프가 돈다는 것까지다. 탐색 효과의 근거가 아니다 |
| C-M2 | 릴리스 번호나 정답 경로를 판정 조건에 넣지 않은 identity 오라클 하나가, node-tar 5개 릴리스(7.5.2·7.5.3·7.5.6·7.5.7·7.5.8)와 고정 입력 2개의 통제 차분에서 서로 다른 두 결함(CVE-2026-23745, CVE-2026-24842)을 구분한다. 통제 재현이며 퍼저의 탐색 결과가 아니다 | TESTED · 판정 결과는 observed, 릴리스별 원인 서술은 inferred | raw [`summary.json`](../../experiments/repro/evidence/summary.json) → [M2 요약](../../experiments/summaries/cross-release-identity-repro-v1.md) → `paper/tables/m2-cross-release-evidence.md`; 실행 `experiments/repro/cross_release_identity.py`; `tests/test_cross_release_oracle_agreement.py`; Ledger M2 행 | 사람이 만든 고정 입력이다. "퍼저가 찾았다", "새 취약점"을 쓰지 않는다 |
| C-REG | `make regression TAR_VERSION=<x>` 한 명령으로, 알려진 경계 고정 입력이 그 릴리스에서 아직 C1/C2를 내는지 확인할 수 있다 | TESTED(고정 입력, dry-run 테스트 포함) · observed | `Makefile`의 `regression` 목표; `scripts/regression_check.py`; `tests/test_regression_check.py`; STATUS 감사 산출물 ⑫ 행(#218); `docs/LOG.md` 2026-11-04 "유지보수자용 회귀 명령" 줄 | 고정 입력 회귀 확인이다. 탐색 성능의 근거가 아니다 |
| C-HOSEL | holdout 릴리스를 정하려고 후보 5개(7.0.1·7.1.0·7.2.0·7.3.0·7.4.4)에 고정 입력 5개를 한 번씩 실행해 상태를 확인했고, 규칙에 따라 7.4.4를 골랐다. 다섯 후보 모두 하드링크 입력 2개는 위반, symlink 입력 3개는 통과, 오류 0이다 | TESTED(qualification-only, 퍼징·캠페인 아님) · observed | `experiments/preregistration/exposure-ledger.md`의 7.0.1–7.4.4 `qualification-only` 행; `docs/DECISIONS.md` D045; `docs/LOG.md` 2026-11-11 "D4 holdout 상태 확인 실행" 줄; `experiments/summaries/raw-manifest-host1-d4-holdout-20261111.sha256`; `experiments/preregistration/exp2-v1.md` §3 | 오라클·측정 사슬의 근거로만 쓴다. 탐색 성능의 근거가 아니다. "7.4.4에서 발견", "holdout이 새 결함 계열", "train과 독립적인 일반성 시험"을 쓰지 않는다 |
| C-PC | 측정 사슬의 양성·음성 대조를 했다. (가) 등록 실행과 같은 캠페인 경로로 7.5.2에서 S-u 1셀(seed 8002, 실행 2000)을 돌려 두 호스트 모두 위반 사건을 기록했다(첫 사건 step 685, 계약 C2). (나) 고정 입력 1개가 7.5.2와 7.4.4에서 C1·C2 위반으로, 수정 릴리스 7.5.3에서는 거부·비위반으로 판정됐다 | TESTED(비등록 `demo run`, 공개 범위는 사전에 고정한 키) · observed | `experiments/preregistration/exposure-ledger.md`의 양성 대조 행; `docs/LOG.md` 2026-11-12 "양성 대조 결과" 줄과 "양성 대조 E′ 7.4.4" 줄, 2026-11-13 HOST2 적격성·양성 대조 줄 | 오라클·측정 사슬(경로 민감도)의 근거로만 쓴다. 탐색 성능의 근거가 아니다. (가)의 첫 사건은 C2뿐이라 "탐색이 C1에 도달한다"의 근거가 아니다 |
| C-M4a | 같은 오라클을 코드 변경 없이 다른 추출기 3개(python-tarfile, oras-go, decompress)에 어댑터로 적용했고, 각 통제 차분에서 영향 쪽은 위반, 대조 쪽은 비위반으로 판정했다. python-tarfile은 같은 라이브러리의 추출 필터 설정(`fully_trusted` 대 `data`) 토글 비교다. oras-go(v2.6.1 대 v2.6.2)와 decompress(4.2.1 대 유지보수 포크 11.1.4)는 릴리스 비교다 | TESTED(오라클·어댑터 수준) · observed | `tests/test_python_tarfile_generality.py`; `tests/test_oras_go_generality.py`와 `experiments/repro/evidence/oras_go_cwd_hardlink.json`; `tests/test_decompress_generality.py`와 `experiments/repro/evidence/decompress_hardlink.json`; Ledger M4 행 | 오라클·어댑터 수준의 주장이다. 퍼저 탐색의 일반성이나 효과에 대한 주장이 아니다. "모든 추출기"를 쓰지 않는다 |
| C-RUST | 같은 방식의 고정 입력 프로브를 Rust `tar` 0.4.35와 0.4.36에도 적용했다 | TESTED(고정 입력 프로브, 캠페인 아님) · observed | `experiments/repro/evidence/rust_tar_fixture_probe.json`; `experiments/preregistration/exposure-ledger.md`의 rust-tar 행; `docs/LOG.md` 2026-11-07 "Rust tar 고정 fixture 프로브 증거 수록" 줄 | "적용된다"까지만 쓴다. 프로브 결과의 해석이나 일반성은 쓰지 않는다. 사전에 결과를 알았으므로 등록 실험에서 뺐다 |
| C-EXP0 | 등록 실행 EXP-0(인프라 측정)은 15셀(R·D·S-u × seed 9001–9005, 캠페인당 실행 200)이 모두 유효했고 abort 0, 경계위반 사건 0이었다. 가설을 판정하지 않는다 | TESTED(등록 실행, 인프라 측정) · observed | `experiments/summaries/exp0-20261105-report.md`와 같은 이름의 `.json`; `paper/tables/exp0-summary.md`; `experiments/preregistration/exp0-pilot-v2.1.md` | 사건 0은 "위반이 없다"가 아니라 그 예산에서 관찰되지 않았다는 뜻이다. arm 비교의 근거가 아니다 |
| C-PILOT | 비등록 위험도 파일럿(7.5.2, 40 캠페인, 캠페인당 실행 2000)에서 네 arm 모두 첫 C1∨C2 사건이 있었다(S-u 6/10, R-restart 4/10, D 4/10, R-walk 1/10). abort는 11/40이다. 신뢰구간이 크게 겹쳐 arm의 순서를 말할 수 없고, 이 값은 표본 수 산정에만 썼다 | 탐색(비등록) · observed | `experiments/summaries/exp3-hazard-pilot-v1-result.md` §1–§2; `experiments/summaries/raw-manifest-exp3-hazard-pilot-v1.sha256`; `docs/DECISIONS.md` D040 | arm의 우열이나 효과의 근거로 쓰지 않는다 |
| C-GO | EXP-3 train이 끝난 뒤 등록 규칙을 기계적으로 적용해 GO를 냈다(2026-11-13 23:37:16 KST). 세 arm을 합친 첫 C1∨C2 캠페인 수 31(기준 1 이상), 처리 용량 554(기준 76 이상), 인프라 실패 비율 .033(기준 .45 이하)이다 | 등록 규칙 적용과 독립 확인 · 합산값 observed | `paper/tables/exp3-go-inputs.md`; `experiments/summaries/exp3-train-go-decision.json`; `docs/LOG.md` 2026-11-13 "EXP-3 GO 판정" 줄(PR #368) | 합산값만 쓴다. arm별 값은 봉인이다. 31에 분모를 붙이지 않는다. 효과의 근거가 아니다. 독립 확인은 순서·용량·할당 재생성까지이고, 31은 봉인 자료가 필요해 다시 계산하지 않았다 |
| C-DESIGN | 세 arm(R 무작위, D 구조 커버리지, S-u 상태 피드백)이 같은 어휘와 같은 예산을 쓰도록 설계했다. 가설·arm·표본 수·분석·판정표를 결과를 보기 전에 Git에 동결했다(2026-11-13, 동결 커밋 `72de299`). train(7.5.2, 탐색)과 holdout(7.4.4, 확증)을 나눴고, 결과는 해제 기록 전까지 가린다 | DESIGNED·IMPLEMENTED(설계와 절차); 어휘 동일은 TESTED · observed | `experiments/preregistration/exp3-v1.md`; `experiments/preregistration/exp2-v1.md`; `docs/LOG.md` 2026-11-13 "EXP-3/EXP-2 사전등록 동결 기록" 줄; STATUS 감사 산출물 ⑤ 행(어휘 동등 단위테스트, EXP-0 어휘 동일); `docs/research/design/research-questions.md` | "결과를 보지 않고는 어떤 결정도 없었다"를 쓰지 않는다(파일럿을 보고 표본 수를 정한 것은 공개된 사실이다) |
| C-INFRA | 재현성 인프라를 갖췄다. raw 출력의 SHA-256 매니페스트, 요약이 raw까지 닿는지 검사하는 증거 사슬 점검(`make check`에 연결), 표 생성기와 커밋된 표의 바이트 대조, 호스트 적격성 검증(호스트별 12 캠페인, 두 호스트 통과)과 교차 호스트 비교(공통 셀 12개 중 12개 일치)다 | TESTED(도구); 적격성과 교차 비교는 그 조건에서의 observed | `experiments/summaries/`의 `raw-manifest-*.sha256`와 `scripts/make_raw_manifest.py`; `scripts/check_evidence_chain.py`; `scripts/regenerate_paper_artifacts.py`·`scripts/gen_table_m2.py`·`scripts/gen_exp3_tables.py`; `experiments/configs/host-qualification-v1.md`와 `scripts/qualify_host.py`; `docs/LOG.md` 2026-11-12 "HOST1 호스트 적격성 실행 결과" 줄, 2026-11-13 HOST2 적격성 줄과 "TBD-FREEZE 채움" 줄(교차 호스트 12/12) | 적격성은 "그 호스트, 실행 SHA `bed077a`, jobs 2, 실행 2000, 12 캠페인 조건에서 기준 충족"까지다. "장기 안정성", "환경 독립"을 쓰지 않는다. 12/12는 교차 호스트 비교의 값이다 |
| C-LIM1 | 한계: 현재 변이 문법에서 경계위반 입력은 seed에서 변이 1회 거리에 있다 | 사전등록에 기록된 설계 사실 · inferred(외부 검토와 문법 몬테카를로) | `experiments/preregistration/exp2-v1.md` §6(노출 공개와 한계)과 §8(변경 이력의 외부 검토 F1) | 이 한계를 빼고 탐색 난이도를 말하지 않는다 |
| C-LIM2 | 한계: 확증 범위는 node-tar 한 계보(train 7.5.2, holdout 7.4.4)와 하드링크 identity 공유 계열이다. holdout 7.4.4는 train과 같은 계열의 위반을 내는 릴리스다 | 설계 사실 · observed(C-HOSEL) | `experiments/preregistration/exp2-v1.md` §3; `docs/DECISIONS.md` D045; C-HOSEL의 근거 | 다른 추출기나 다른 결함 계열로 넓혀 쓰지 않는다 |
| C-OPS | 공개하는 운영 사실(주장이 아니다): EXP-3 train 중 HOST2 인프라 정지 1회(2026-11-13, 원인 기록 #366 뒤 재개, 정지에 걸린 2셀은 재실행하지 않음), EXP-2 holdout 중 HOST2 인프라 정지 1회(2026-11-14, 원인 기록 #370 뒤 재개). 확인된 직접 원인은 Docker Desktop API 무응답이고 근본 원인은 확인하지 못했다 | observed(인프라 기록) | `docs/LOG.md` 2026-11-13 "EXP-3 train HOST2 인프라 정지 1회" 줄과 "EXP-3 train 종료 기록" 줄, 2026-11-14 "EXP-2 holdout HOST2 인프라" 줄; `paper/tables/exp3-go-inputs.md`(정지 1회, 공백 0.3 h) | 원인이 생긴 층을 단정하지 않는다. holdout이 끝나면 종료 기록에 맞춰 이 행을 고친다 |
| C-HA | 같은 어휘 아래 상태 피드백(S-u)이 R·D보다 첫 경계위반까지의 실행 수를 줄이는가(H-A)는 등록 실험으로 판정한다 | **미검증**(실행 중, 봉인) | [research-questions v2](../../docs/research/design/research-questions.md) H-A; `experiments/preregistration/exp2-v1.md` §5 | 결과 문장은 아래 "본실험 결과 자리"로만 둔다. 해제 전에 방향이나 크기를 쓰지 않는다 |

## 본실험 결과 자리

| 자리 | 들어갈 내용 | 채우는 시점 | 지금 두는 문구 |
| --- | --- | --- | --- |
| S-TRAIN | EXP-3 train(7.5.2)의 arm별 결과. 탐색이며 효과의 근거가 아니다 | 해제 기록 PR 머지 뒤 | `본실험 결과 자리(봉인 해제 뒤 기입)` |
| S-HOLDOUT | EXP-2 holdout(7.4.4)의 확증 판정(H-A). 사전등록 판정표의 문장만 쓴다 | 해제 기록 PR 머지 뒤 | `본실험 결과 자리(봉인 해제 뒤 기입)` |

영상은 장면 6 자리와 결론 장면을 S-HOLDOUT 자리로 비워 둔다.

각 요약의 raw 포인터가 매니페스트나 저장소에 닿는지는 `scripts/check_evidence_chain.py`로 점검한다.

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
