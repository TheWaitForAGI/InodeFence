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
5. **설계 변경 경위.** 꼭 필요한 곳에 수치 없이 한 문장만 둔다: "초기 비교는 arm 간 어휘가 달라 폐기했고, 어휘를 맞춘 R/D/S-u 설계로 다시 실험했다." 주장 ID는 붙이지 않는다.
6. **근거 시점.** 근거 경로의 날짜와 SHA는 그 기록이 만들어진 시점의 것이다. 정리 단계 D에서 현재 main으로
   다시 뽑은 뒤에는 새 기록을 가리키도록 이 표를 먼저 고친다. 2026-11-14에 다시 뽑은 것: 20 step 데모(GHA 실행
   43565892214, main `ff83fbe`)와 CI 실행 43565082671(main `d954387`)의 6 step 데모·통제 추출기 대조·릴리스 간 오라클 일치·추출기
   일반성 테스트다. docker가 필요한 통제 재현(릴리스 간 재현 스크립트, 회귀 확인 7.5.2, oras-go·decompress 프로브, 통제 추출기 대조)은
   GHA 실행 43571057146(main `1e43eae`)으로 다시 뽑았다. 릴리스 간 재현 스크립트와 두 프로브의 판정 값은 커밋된 기록과 같았고, 회귀 확인 7.5.2와 통제 추출기 대조는 기대값대로였다. 이 재실행은 모두 `demo run` 또는
   통제 재현이며 등록 캠페인이 아니다. GitHub 러너에서 만든 이미지를 썼으므로 이미지 id는 동결된 등록 이미지와 다르다.

## 주장 표

| ID | 쓸 수 있는 말 | 증거 수준 · 관찰 구분 | 근거 경로 | 용도 제한 · 쓰면 안 되는 말 |
| --- | --- | --- | --- | --- |
| C-M1 | 실제 node-tar에서 입력 생성 → 실행 → entry별 중간 상태 관찰 → C0/C1/C2 판정 → feedback → 다음 변이 선택의 루프가 한 명령(`make demo`)으로 반복 실행된다. 현재 main(`ff83fbe`)에서 `make demo`의 기본 입력(seed 123, 실행 20)으로 돌린 데모는 node-tar 7.5.22에서 20 step(성공 18, 거부 2)을 실행했고 위반 0, 고유 effect 키 25, 보상 step 3회(데모가 찍는 번호로 step 6·13·20), 코퍼스 4 → 7이었다 | TESTED · observed (엔지니어링 능력, `demo run`) | Ledger M1 행과 마일스톤 M1([STATUS](../../docs/STATUS.md)); GHA 실행 43565892214(`.github/workflows/experiment-fanout.yml` mode=demo, main `ff83fbe`, 2026-11-14, 아티팩트 `campaign-native-make-demo-s123`, 리포트 sha256 `e2cbc8c8…6936`); CI 실행 43565082671(main `d954387`)의 container-integration 작업(같은 경로, 실행 6); `docs/LOG.md` 2026-11-06 "시연 대본 명령 실행 검증" 줄(main `23e5c66`); `paper/figures/make-demo-screen.png`(2026-11-07 기록 재생); 재생 검증 `make replay`(`scripts/replay_report.py`) | 루프가 돈다는 것까지다. 탐색 효과의 근거가 아니다. 위반 0은 이 데모 예산에서 관찰되지 않았다는 뜻이다. node-tar 7.5.22가 안전하다는 근거가 아니다. 고유 effect 키, 보상 step, 코퍼스 크기는 비교 arm이 없는 seed 1개 데모의 값이므로 탐색 성능이나 arm 비교의 수치로 쓰지 않는다. 2026-11-06 기록과 같다고 말할 수 있는 것은 step 수 20과 위반 0뿐이다(나머지 값은 그때 기록이 없다). 2026-11-07 화면 기록(`paper/figures/make-demo-screen.png`)과는 성공 18·거부 2, 위반 0, 고유 effect 키 25, 보상 step 6·13·20, 코퍼스 4 → 7이 같다. step 번호는 데모가 찍는 번호(1부터)로 쓴다. 리포트 JSON의 `index`는 0부터 센다 |
| C-M2 | 릴리스 번호나 정답 경로를 판정 조건에 넣지 않은 identity 오라클 하나가, node-tar 5개 릴리스(7.5.2·7.5.3·7.5.6·7.5.7·7.5.8)와 고정 입력 2개의 통제 차분에서 서로 다른 두 결함(CVE-2026-23745, CVE-2026-24842)을 구분한다. 통제 재현이며 퍼저의 탐색 결과가 아니다 | TESTED · 판정 결과는 observed, 릴리스별 원인 서술은 inferred | raw [`summary.json`](../../experiments/repro/evidence/summary.json) → [M2 요약](../../experiments/summaries/cross-release-identity-repro-v1.md) → `paper/tables/m2-cross-release-evidence.md`; 실행 `experiments/repro/cross_release_identity.py`; `tests/test_cross_release_oracle_agreement.py`; Ledger M2 행. raw는 2026-10-25에 만들어졌고(`86a4585`, 감사 전) 같은 스크립트로 다시 실행할 수 있다(docker 필요). 2026-11-06에 main `23e5c66`에서 다시 실행한 결과가 커밋된 raw와 차이 0이었다(`docs/LOG.md` 2026-11-06 "시연 대본 명령 실행 검증" 줄). CI 실행 43565082671(main `d954387`)의 check 작업이 `tests/test_cross_release_oracle_agreement.py`를 통과했다. GHA 실행 43571057146(`.github/workflows/repro-evidence.yml`, main `1e43eae`, 2026-11-14, 통제 재현)에서 같은 스크립트를 다시 실행한 결과의 `summary.json`이 커밋된 raw와 바이트 단위로 같았다(입력별 파일은 raw dev·inode 번호와 디렉터리 메타데이터만 다르고 판정 값은 같다) | 사람이 만든 고정 입력이다. "퍼저가 찾았다", "새 취약점"을 쓰지 않는다 |
| C-ORACLE | 경계 검사 없이 entry를 그대로 따르는 통제용 테스트 추출기(in-process, 일회용 샌드박스 안)에 고정 입력 4개를 넣어 오라클을 대조했다. 정상 입력은 위반 없음, 추출 루트를 벗어나는 경로의 파일은 C0, sentinel을 가리키는 하드링크는 C1과 C2, symlink를 만든 뒤 그 경로에 쓰는 입력은 C2로 판정된다. 오라클 검증이며 node-tar 결과가 아니다 | TESTED · observed | `scripts/oracle_fixture_check.py`; `tests/test_oracle_fixtures.py`; CI 실행 43565082671(main `d954387`)의 check 작업; GHA 실행 43571057146(`.github/workflows/repro-evidence.yml`, main `1e43eae`, 2026-11-14, 통제 재현)의 `oracle_fixture_check` 출력(4개 모두 기대대로); `docs/LOG.md` 2026-11-06 "시연 대본 명령 실행 검증" 줄("oracle fixture 4종 모두 expected") | "node-tar에서 확인했다"로 쓰지 않는다. 고정 입력 4개에 대한 대조이며 탐색 성능의 근거가 아니다. 다른 대조의 수(교차 호스트 12/12 등)를 이 대조의 값으로 쓰지 않는다 |
| C-REG | `make regression TAR_VERSION=<x>` 한 명령으로, 알려진 경계 고정 입력이 그 릴리스에서 아직 C1/C2를 내는지 확인할 수 있다 | TESTED · 도구 자체는 단위테스트와 dry-run(2026-11-04, docker 미실행), 실제 실행은 observed(2026-11-11 holdout 상태 확인에서 같은 명령을 수정 없이 실행) | `Makefile`의 `regression` 목표; `scripts/regression_check.py`; `tests/test_regression_check.py`; STATUS 감사 산출물 ⑫ 행(#218); `docs/LOG.md` 2026-11-04 "유지보수자용 회귀 명령" 줄(dry-run·단위테스트)과 2026-11-11 "D4 holdout 상태 확인 실행" 줄(실제 실행); GHA 실행 43571057146(`.github/workflows/repro-evidence.yml`, main `1e43eae`, 2026-11-14, 통제 재현)에서 같은 스크립트를 7.5.2에 실행해 하드링크 고정 입력 2개는 위반, symlink 쓰기 입력 3개는 비위반, 오류 0이었다(판정 줄 `REGRESSION FAIL node-tar=7.5.2 c1_or_c2=2/5`; 이 명령에서 FAIL은 알려진 입력이 아직 위반을 낸다는 뜻이다) | 고정 입력 회귀 확인이다. 탐색 성능의 근거가 아니다 |
| C-HOSEL | holdout 릴리스를 정하려고 후보 5개(7.0.1·7.1.0·7.2.0·7.3.0·7.4.4)에 고정 입력 5개를 한 번씩 실행해 상태를 확인했고, 규칙에 따라 7.4.4를 골랐다. 다섯 후보 모두 하드링크 입력 2개는 위반, symlink 입력 3개는 통과, 오류 0이다 | TESTED(qualification-only, 퍼징·캠페인 아님) · observed | `experiments/preregistration/exposure-ledger.md`의 7.0.1–7.4.4 `qualification-only` 행; `docs/DECISIONS.md` D045; `docs/LOG.md` 2026-11-11 "D4 holdout 상태 확인 실행" 줄; `experiments/summaries/raw-manifest-host1-d4-holdout-20261111.sha256`; `experiments/preregistration/exp2-v1.md` §3 | 오라클·측정 사슬의 근거로만 쓴다. 탐색 성능의 근거가 아니다. 이 고정 입력 5개로는 7.0–7.4 후보를 서로 구분할 수 없고, 7.4.4는 가장 높은 버전을 고르는 규칙으로 정해졌다. "7.4.4에서 발견", "holdout이 새 결함 계열", "train과 독립적인 일반성 시험"을 쓰지 않는다 |
| C-PC | 측정 사슬의 양성·음성 대조를 했다. (가) 등록 실행과 같은 캠페인 경로로 7.5.2에서 S-u 1셀(seed 8002, 실행 2000)을 돌려 HOST1에서 위반 사건을 기록했다(첫 사건 step 685, 계약 C2). HOST2도 같은 값이다. (나) 등록 실행 경로 밖에서 돌린 고정 입력 1개가 7.5.2와 7.4.4에서 C1·C2 위반으로, 수정 릴리스 7.5.3에서는 거부·비위반으로 판정됐다 | TESTED(비등록 `demo run`, 공개 범위는 사전에 고정한 키) · observed | `experiments/preregistration/exposure-ledger.md`의 양성 대조 행; `docs/LOG.md` 2026-11-12 "양성 대조 결과" 줄과 "양성 대조 E′ 7.4.4" 줄, 2026-11-13 HOST2 적격성·양성 대조 줄. HOST2의 값은 LOG에 없고 `experiments/summaries/host2-qualification-20261111/REPORT.md`의 양성 대조 절과 사전에 고정한 공개 키 파일 `pc-a-keys-HOST2.txt`(저장소 밖, sha256 `780016a2…`, 원장 HOST2 양성 대조 행의 해시)에 있다 | 오라클·측정 사슬(경로 민감도)의 근거로만 쓴다. 탐색 성능의 근거가 아니다. (가)의 첫 사건은 C2뿐이라 "탐색이 C1에 도달한다"의 근거가 아니다. (나)는 실행 SHA에 진입 배선만 더한 E′(`2567b843`, main 미머지)에서 `run_exp0`과 시작 게이트를 거치지 않고 sentinel 1개로 돌린 판정이다 |
| C-M4a | 같은 오라클을 코드 변경 없이 다른 추출기 3개(python-tarfile, oras-go, decompress)에 어댑터로 적용했고, 각 통제 차분에서 영향 쪽은 위반, 대조 쪽은 비위반으로 판정했다. python-tarfile은 같은 라이브러리의 추출 필터 설정(`fully_trusted` 대 `data`) 토글 비교다. oras-go(v2.6.1 대 v2.6.2)와 decompress(4.2.1 대 유지보수 포크 11.1.4)는 릴리스 비교다. 이 둘은 실제 추출기의 동작을 프로브로 관찰한 기록이 있고, 저장소 테스트의 오라클 판정은 그 사후 상태를 일회용 샌드박스에서 재현한 것에 내린 판정이다 | TESTED(오라클·어댑터 수준) · 실제 추출기 동작은 프로브 기록으로 observed, 오라클 판정은 재현한 사후 상태에 대해 observed | `tests/test_python_tarfile_generality.py`; `tests/test_oras_go_generality.py`, `experiments/repro/oras_go_cwd_hardlink.py`와 그 기록 `experiments/repro/evidence/oras_go_cwd_hardlink.json`; `tests/test_decompress_generality.py`, `experiments/repro/decompress_hardlink.py`와 그 기록 `experiments/repro/evidence/decompress_hardlink.json`; Ledger M4 행 가운데 오라클·어댑터 부분만. 테스트와 프로브 기록은 2026-10-27~30에 만들어졌고(감사 전) 다시 실행할 수 있다. CI 실행 43565082671(main `d954387`)의 check 작업이 세 일반성 테스트를 통과했다. GHA 실행 43571057146(`.github/workflows/repro-evidence.yml`, main `1e43eae`, 2026-11-14, 통제 재현)에서 oras-go와 decompress 프로브를 다시 실행했고 판정 값(영향 버전은 identity 공유, 수정 버전은 거부)이 커밋된 기록과 같았다 | 오라클·어댑터 수준의 주장이다. 퍼저 탐색의 일반성이나 효과에 대한 주장이 아니다. "모든 추출기"를 쓰지 않는다 |
| C-RUST | 같은 방식의 고정 입력 프로브를 Rust `tar` 0.4.35와 0.4.36에도 적용했다 | TESTED(고정 입력 프로브, 캠페인 아님) · observed | `experiments/repro/evidence/rust_tar_fixture_probe.json`; `experiments/preregistration/exposure-ledger.md`의 rust-tar 행; `docs/LOG.md` 2026-11-07 "Rust tar 고정 fixture 프로브 증거 수록" 줄 | "적용된다"까지만 쓴다. 프로브 결과의 해석이나 일반성은 쓰지 않는다. 사전에 결과를 알았으므로 등록 실험에서 뺐다. 생성 스크립트가 미머지 PR #261에 있어 main만으로는 다시 실행할 수 없다(감사 이후 기록으로만 쓴다) |
| C-EXP0 | 등록 실행 EXP-0(인프라 측정)은 15셀(R·D·S-u × seed 9001–9005, 캠페인당 실행 200)이 모두 유효했고 abort 0, 경계위반 사건 0이었다. 가설을 판정하지 않는다 | TESTED(등록 실행, 인프라 측정) · observed | `experiments/summaries/exp0-20261105-report.md`와 같은 이름의 `.json`; `paper/tables/exp0-summary.md`; `experiments/preregistration/exp0-pilot-v2.1.md` | 사건 0은 "위반이 없다"가 아니라 그 예산에서 관찰되지 않았다는 뜻이다. arm 비교의 근거가 아니다 |
| C-PILOT | 비등록 위험도 파일럿(7.5.2, 40 캠페인, 캠페인당 실행 2000)에서 네 arm 모두 첫 C1∨C2 사건이 있었고, 신뢰구간이 크게 겹쳐 arm의 순서를 말할 수 없다(R-walk 1/10, R-restart 4/10, D 4/10, S-u 6/10). abort는 11/40이다. 이 값은 표본 수 산정, R 변형 선택(D6), 사전등록 예측의 개정에 썼다 | 탐색(비등록) · observed | `experiments/summaries/exp3-hazard-pilot-v1-result.md` §1–§2; `experiments/summaries/raw-manifest-exp3-hazard-pilot-v1.sha256`; `docs/DECISIONS.md` D040 | arm의 우열이나 효과의 근거로 쓰지 않는다 |
| C-GO | EXP-3 train이 끝난 뒤 등록 규칙을 기계적으로 적용해 GO를 냈다(2026-11-13 23:37:16 KST). 세 arm을 합친 첫 C1∨C2 캠페인 수 31(기준 1 이상), 처리 용량 554(기준 76 이상), 인프라 실패 비율 .033(기준 .45 이하)이다 | 등록 규칙 적용과 독립 확인 · 합산값 observed | `paper/tables/exp3-go-inputs.md`; `experiments/summaries/exp3-train-go-decision.json`; `docs/LOG.md` 2026-11-13 "EXP-3 GO 판정" 줄(PR #368) | 합산값만 쓴다. arm별 값은 봉인이다. 31에 분모를 붙이지 않는다. 효과의 근거가 아니다. 독립 확인은 순서·용량·할당 재생성까지이고, 31은 봉인 자료가 필요해 다시 계산하지 않았다 |
| C-DESIGN | 세 arm(R 무작위, D 구조 커버리지, S-u 상태 피드백)이 같은 어휘와 같은 예산을 쓰도록 설계했다. 가설·arm·표본 수·분석·판정표를 결과를 보기 전에 Git에 동결했다(2026-11-13, 동결 커밋 `72de299`). train(7.5.2, 탐색)과 holdout(7.4.4, 확증)을 나눴고, 결과는 해제 기록 전까지 가린다. 동결 전에 등록을 고친 내용(예측 문장, 판정표의 비기각 행, N 결정 규칙, 범위 문구, 동결일 정의)은 등록 실행을 시작하기 전의 개정이며 사전등록 변경 이력에 공개돼 있다. 사전등록에는 예측도 고정돼 있다: 문법 몬테카를로로 미리 계산한 상한 U_sim ≈ HR 1.1~1.3, 그래서 기대하는 결말은 비기각과 HR 2 배제다. 이것은 등록한 예측이며 결과가 아니다 | DESIGNED·IMPLEMENTED(설계와 절차); 어휘 동일은 TESTED · observed | `experiments/preregistration/exp3-v1.md`; `experiments/preregistration/exp2-v1.md`; `experiments/preregistration/exp2-v1.md` §8(변경 이력); `docs/LOG.md` 2026-11-13 "EXP-3/EXP-2 사전등록 동결 기록" 줄; STATUS 감사 산출물 ⑤ 행(어휘 동등 단위테스트, EXP-0 어휘 동일); `docs/research/design/research-questions.md` | "결과를 보지 않고는 어떤 결정도 없었다"를 쓰지 않는다(파일럿을 보고 표본 수를 정한 것은 공개된 사실이다). S-u를 설명할 때 exp2-v1 §6의 범위 문구를 지킨다: S-u의 boundary 키는 특정 패턴이나 경로를 담지 않지만 결함 계열 수준의 사전 지식이다. D는 구조 커버리지 유도 퍼징의 대리이며 코드 커버리지 기준선이 아니다. 등록 예측은 방법·설계를 설명하는 자리에서만 "사전등록 예측(결과 아님)"이라고 밝혀 쓰고, 값은 exp2-v1 §1의 것만 쓴다. 결과 자리 옆에는 두지 않는다 |
| C-INFRA | 재현성 인프라를 갖췄다. raw 출력의 SHA-256 매니페스트, 요약이 raw까지 닿는지 검사하는 증거 사슬 점검(`make check`에 연결), 표 생성기와 커밋된 표의 바이트 대조, 호스트 적격성 검증(호스트별 12 캠페인, 두 호스트 통과)과 교차 호스트 비교(공통 셀 12개 중 12개 일치)다 | TESTED(도구); 적격성과 교차 비교는 그 조건에서의 observed | `experiments/summaries/`의 `raw-manifest-*.sha256`와 `scripts/make_raw_manifest.py`; `scripts/check_evidence_chain.py`; `scripts/regenerate_paper_artifacts.py`·`scripts/gen_table_m2.py`·`scripts/gen_exp3_tables.py`; `experiments/configs/host-qualification-v1.md`와 `scripts/qualify_host.py`; `docs/LOG.md` 2026-11-12 "HOST1 호스트 적격성 실행 결과" 줄, 2026-11-13 HOST2 적격성 줄과 "TBD-FREEZE 채움" 줄(교차 호스트 12/12) | 적격성은 "그 호스트, 실행 SHA `bed077a`, jobs 2, 실행 2000, 12 캠페인 조건에서 기준 충족"까지다. "장기 안정성", "환경 독립"을 쓰지 않는다. 12/12는 교차 호스트 비교의 값이다 |
| C-LIM1 | 한계: 현재 변이 문법에서 경계위반 입력은 seed에서 변이 1회 거리에 있다 | 사전등록에 기록된 설계 사실 · inferred(외부 검토와 문법 몬테카를로) | `experiments/preregistration/exp2-v1.md` §6(노출 공개와 한계)과 §8(변경 이력의 외부 검토 F1) | 이 한계를 빼고 탐색 난이도를 말하지 않는다 |
| C-LIM2 | 한계: 확증 범위는 node-tar 한 계보(train 7.5.2, holdout 7.4.4)와 하드링크 identity 공유 계열이다. holdout 7.4.4는 고정 입력에서 train과 같은 계열의 위반을 내는 릴리스다 | 설계 사실 · observed(C-HOSEL) | `experiments/preregistration/exp2-v1.md` §3; `docs/DECISIONS.md` D045; C-HOSEL의 근거 | 다른 추출기나 다른 결함 계열로 넓혀 쓰지 않는다 |
| C-LIM3 | 한계: 오라클은 추출 전후 두 스냅숏을 비교하는 탐지기다. 위반 없음(`violated=False`)은 관찰 범위 안에서 위반 증거가 없다는 뜻일 뿐이며, 두 시점 사이에 생겼다 사라진 변화, inode 번호 재사용, 샌드박스 밖 접근은 판정하지 못한다. entry 사이의 중간 상태 전이는 feedback 근거로만 쓰고 C0/C1/C2 판정으로 올리지 않는다 | DESIGNED·IMPLEMENTED(오라클의 정의에서 나오는 한계) · 설계 사실 | `docs/research/design/security-contracts.md`의 "무엇을 판정하지 못하는가 (한계)" 절; `docs/research/design/entry-effect-feedback-v2.md`("failure is not a nonviolation") | "안전하다", "위반이 없다"로 쓰지 않는다. 시험으로 확인한 성질이 아니라 설계상 한계로 쓴다 |
| C-OPS | 공개하는 운영 사실(주장이 아니다): EXP-3 train 중 HOST2 인프라 정지 1회(2026-11-13, 원인 기록 #366 뒤 재개, 정지에 걸린 2셀은 재실행하지 않음), EXP-2 holdout 중 HOST2 인프라 정지 1회(2026-11-14, 원인 기록 #370 머지로 재개 승인; 재개 사실은 holdout 종료 기록에 적는다). 확인된 직접 원인은 Docker Desktop API 무응답이고 근본 원인은 확인하지 못했다 | observed(인프라 기록) | `docs/LOG.md` 2026-11-13 "EXP-3 train HOST2 인프라 정지 1회" 줄과 "EXP-3 train 종료 기록" 줄, 2026-11-14 "EXP-2 holdout HOST2 인프라" 줄; `paper/tables/exp3-go-inputs.md`(정지 1회, 공백 0.3 h) | 원인이 생긴 층을 단정하지 않는다. holdout이 끝나면 종료 기록에 맞춰 이 행을 고친다 |
| C-HA | 같은 어휘 아래 상태 피드백(S-u)이 R·D보다 첫 경계위반까지의 실행 수를 줄이는가(H-A)는 등록 실험으로 판정한다 | **미검증**(실행 중, 봉인) | [research-questions v2](../../docs/research/design/research-questions.md) H-A; `experiments/preregistration/exp2-v1.md` §5 | 결과 문장은 아래 "본실험 결과 자리"로만 둔다. 해제 전에 방향이나 크기를 쓰지 않는다 |

## 본실험 결과 자리

| 자리 | 들어갈 내용 | 채우는 시점 | 지금 두는 문구 |
| --- | --- | --- | --- |
| S-TRAIN | EXP-3 train(7.5.2)의 arm별 결과. 탐색이며 효과의 근거가 아니다 | 해제 기록 PR 머지 뒤 | `본실험 결과 자리(봉인 해제 뒤 기입)` |
| S-HOLDOUT | EXP-2 holdout(7.4.4)의 확증 판정(H-A). 사전등록 판정표의 문장만 쓴다 | 해제 기록 PR 머지 뒤 | `본실험 결과 자리(봉인 해제 뒤 기입)` |

영상은 장면 6 자리와 결론 장면을 S-HOLDOUT 자리로 비워 둔다.

결과 자리에는 위 문구만 둔다. 예상, 방향, 진행 상황 문장을 덧붙이지 않는다. 제출 시점까지 봉인이 풀리지 않은 경우에 한해 사전등록 판정표(D12)의 "진행 중" 문장으로 바꾸며, 그 판단은 오케스트레이터가 한다.

각 요약의 raw 포인터가 매니페스트나 저장소에 닿는지는 `scripts/check_evidence_chain.py`로 점검한다.

## 수술 3단계 도구·증거 행 (완료 아님 / 도구 검증 / 대기)

아래는 수술 3단계에서 나온 **도구·증거 행**이다. **능력(claim) 주장이 아니다** — 도구 검증·증거 수집
상태이며, 위 주장 표의 어떤 **C-ID paper-ready 판정도 바꾸지 않는다.** 전부 "완료 아님 / 도구 검증 / 대기"로
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
