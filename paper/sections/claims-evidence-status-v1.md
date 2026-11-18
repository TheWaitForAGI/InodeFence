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
3. **본실험 결과 자리.** 봉인은 2026-11-17 23:49:27 KST 해제 기록 PR #485 머지로 풀렸다. EXP-3 train과
   EXP-2 holdout 결과는 아래 "본실험 결과 자리"의 S-TRAIN·S-HOLDOUT 문장만 쓴다. 숫자는 #487의 표와 값 파일에서만 가져온다.
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
| C-M1 | 실제 node-tar에서 입력 생성 → 실행 → entry별 중간 상태 관찰 → C0/C1/C2 판정 → feedback → 다음 변이 선택의 루프가 한 명령(`make demo`)으로 반복 실행된다. 현재 main(`ff83fbe`)에서 `make demo`의 기본 입력(seed 123, 실행 20)으로 돌린 데모는 node-tar 7.5.22에서 20 step(성공 18, 거부 2)을 실행했고 위반 0, 고유 effect 키 25, 보상 step 3회(데모가 찍는 번호로 step 6·13·20), 코퍼스 4 → 7이었다 | TESTED · observed (엔지니어링 능력, `demo run`) | Ledger M1 행과 마일스톤 M1([STATUS](../../docs/STATUS.md)); GHA 실행 43565892214(`.github/workflows/experiment-fanout.yml` mode=demo, main `ff83fbe`, 2026-11-14, 아티팩트 `campaign-native-make-demo-s123`, 리포트 sha256 `e2cbc8c8…6936`); CI 실행 43565082671(main `d954387`)의 container-integration 작업(같은 경로, 실행 6); `docs/LOG.md` 2026-11-06 "시연 대본 명령 실행 검증" 줄(main `23e5c66`); `paper/figures/make-demo-screen.png`(2026-11-07 기록 재생); 재생 검증 `make replay`(`scripts/replay_report.py`) | 루프가 돈다는 것까지다. 탐색 효과의 근거가 아니다. 위반 0은 이 데모 예산에서 관찰되지 않았다는 뜻이다. node-tar 7.5.22가 안전하다는 근거가 아니다. 고유 effect 키, 보상 step, 코퍼스 크기는 비교 arm이 없는 seed 1개 데모의 값이므로 탐색 성능이나 arm 비교의 수치로 쓰지 않는다. 2026-11-06 기록과 같다고 말할 수 있는 것은 step 수 20과 위반 0뿐이다(나머지 값은 그때 기록이 없다). 2026-11-07 화면 기록(`paper/figures/make-demo-screen.png`)과는 성공 18·거부 2, 위반 0, 고유 effect 키 25, 보상 step 6·13·20, 코퍼스 4 → 7이 같다. step 번호는 데모가 찍는 번호(1부터)로 쓴다. 리포트 JSON의 `index`는 0부터 센다. feedback이 다음 변이(연산자) 선택에 쓰이는 것은 `make demo`의 기본 정책(`effect-feedback-v2-or-violation-v1-adaptive-mutation-v1`, 적응형 연산자 선택)이다. `explore` 경로와 등록 실험의 세 arm은 연산자 선택이 uniform이고, 등록 S-u의 피드백은 입력 보존(retention)에만 쓰인다 |
| C-M2 | 릴리스 번호나 정답 경로를 판정 조건에 넣지 않은 identity 오라클 하나가, node-tar 5개 릴리스(7.5.2·7.5.3·7.5.6·7.5.7·7.5.8)와 고정 입력 2개의 통제 차분에서 서로 다른 두 결함(CVE-2026-23745, CVE-2026-24842)을 구분한다. 통제 재현이며 퍼저의 탐색 결과가 아니다 | TESTED · 판정 결과는 observed, 릴리스별 원인 서술은 inferred | raw [`summary.json`](../../experiments/repro/evidence/summary.json) → [M2 요약](../../experiments/summaries/cross-release-identity-repro-v1.md) → `paper/tables/m2-cross-release-evidence.md`; 실행 `experiments/repro/cross_release_identity.py`; `tests/test_cross_release_oracle_agreement.py`; Ledger M2 행. raw는 2026-10-25에 만들어졌고(`86a4585`, 감사 전) 같은 스크립트로 다시 실행할 수 있다(docker 필요). 2026-11-06에 main `23e5c66`에서 다시 실행한 결과가 커밋된 raw와 차이 0이었다(`docs/LOG.md` 2026-11-06 "시연 대본 명령 실행 검증" 줄). CI 실행 43565082671(main `d954387`)의 check 작업이 `tests/test_cross_release_oracle_agreement.py`를 통과했다. GHA 실행 43571057146(`.github/workflows/repro-evidence.yml`, main `1e43eae`, 2026-11-14, 통제 재현)에서 같은 스크립트를 다시 실행한 결과의 `summary.json`이 커밋된 raw와 바이트 단위로 같았다(입력별 파일은 raw dev·inode 번호와 디렉터리 메타데이터만 다르고 판정 값은 같다) | 사람이 만든 고정 입력이다. "퍼저가 찾았다", "새 취약점"을 쓰지 않는다 |
| C-ORACLE | 경계 검사 없이 entry를 그대로 따르는 통제용 테스트 추출기(in-process, 일회용 샌드박스 안)에 고정 입력 4개를 넣어 오라클을 대조했다. 정상 입력은 위반 없음, 추출 루트를 벗어나는 경로의 파일은 C0, sentinel을 가리키는 하드링크는 C1과 C2, symlink를 만든 뒤 그 경로에 쓰는 입력은 C2로 판정된다. 오라클 검증이며 node-tar 결과가 아니다 | TESTED · observed | `scripts/oracle_fixture_check.py`; `tests/test_oracle_fixtures.py`; CI 실행 43565082671(main `d954387`)의 check 작업; GHA 실행 43571057146(`.github/workflows/repro-evidence.yml`, main `1e43eae`, 2026-11-14, 통제 재현)의 `oracle_fixture_check` 출력(4개 모두 기대대로); `docs/LOG.md` 2026-11-06 "시연 대본 명령 실행 검증" 줄("oracle fixture 4종 모두 expected") | "node-tar에서 확인했다"로 쓰지 않는다. 고정 입력 4개에 대한 대조이며 탐색 성능의 근거가 아니다. 다른 대조의 수(교차 호스트 12/12 등)를 이 대조의 값으로 쓰지 않는다 |
| C-REG | `make regression TAR_VERSION=<x>` 한 명령으로, 알려진 경계 고정 입력이 그 릴리스에서 아직 C1/C2를 내는지 확인할 수 있다 | TESTED · 도구 자체는 단위테스트와 dry-run(2026-11-04, docker 미실행), 실제 실행은 observed(2026-11-11 holdout 상태 확인에서 같은 명령을 수정 없이 실행) | `Makefile`의 `regression` 목표; `scripts/regression_check.py`; `tests/test_regression_check.py`; STATUS 감사 산출물 ⑫ 행(#218); `docs/LOG.md` 2026-11-04 "유지보수자용 회귀 명령" 줄(dry-run·단위테스트)과 2026-11-11 "D4 holdout 상태 확인 실행" 줄(실제 실행); GHA 실행 43571057146(`.github/workflows/repro-evidence.yml`, main `1e43eae`, 2026-11-14, 통제 재현)에서 같은 스크립트를 7.5.2에 실행해 하드링크 고정 입력 2개는 위반, symlink 쓰기 입력 3개는 비위반, 오류 0이었다(판정 줄 `REGRESSION FAIL node-tar=7.5.2 c1_or_c2=2/5`; 이 명령에서 FAIL은 알려진 입력이 아직 위반을 낸다는 뜻이다) | 고정 입력 회귀 확인이다. 탐색 성능의 근거가 아니다 |
| C-HOSEL | holdout 릴리스를 정하려고 후보 5개(7.0.1·7.1.0·7.2.0·7.3.0·7.4.4)에 고정 입력 5개를 한 번씩 실행해 상태를 확인했고, 규칙에 따라 7.4.4를 골랐다. 다섯 후보 모두 하드링크 입력 2개는 위반, symlink 입력 3개는 통과, 오류 0이다 | TESTED(qualification-only, 퍼징·캠페인 아님) · observed | `experiments/preregistration/exposure-ledger.md`의 7.0.1–7.4.4 `qualification-only` 행; `docs/DECISIONS.md` D045; `docs/LOG.md` 2026-11-11 "D4 holdout 상태 확인 실행" 줄; `experiments/summaries/raw-manifest-host1-d4-holdout-20261111.sha256`; `experiments/preregistration/exp2-v1.md` §3 | 오라클·측정 사슬의 근거로만 쓴다. 탐색 성능의 근거가 아니다. 이 고정 입력 5개로는 7.0–7.4 후보를 서로 구분할 수 없고, 7.4.4는 가장 높은 버전을 고르는 규칙으로 정해졌다. "7.4.4에서 발견", "holdout이 새 결함 계열", "train과 독립적인 일반성 시험"을 쓰지 않는다 |
| C-PC | 측정 사슬의 양성·음성 대조를 했다. (가) 등록 실행과 같은 캠페인 경로로 7.5.2에서 S-u 1셀(seed 8002, 실행 2000)을 돌려 HOST1에서 위반 사건을 기록했다(첫 사건 step 685, 계약 C2). HOST2도 같은 값이다. (나) 등록 실행 경로 밖에서 돌린 고정 입력 1개가 7.5.2와 7.4.4에서 C1·C2 위반으로, 수정 릴리스 7.5.3에서는 거부·비위반으로 판정됐다 | TESTED(비등록 `demo run`, 공개 범위는 사전에 고정한 키) · observed | `experiments/preregistration/exposure-ledger.md`의 양성 대조 행; `docs/LOG.md` 2026-11-12 "양성 대조 결과" 줄과 "양성 대조 E′ 7.4.4" 줄, 2026-11-13 HOST2 적격성·양성 대조 줄. HOST2의 값은 LOG에 없고 `experiments/summaries/host2-qualification-20261111/REPORT.md`의 양성 대조 절과 사전에 고정한 공개 키 파일 `pc-a-keys-HOST2.txt`(저장소 밖, sha256 `780016a2…`, 원장 HOST2 양성 대조 행의 해시)에 있다 | 오라클·측정 사슬(경로 민감도)의 근거로만 쓴다. 탐색 성능의 근거가 아니다. (가)의 첫 사건은 C2뿐이라 "탐색이 C1에 도달한다"의 근거가 아니다. (나)는 실행 SHA에 진입 배선만 더한 E′(`2567b843`, main 미머지)에서 `run_exp0`과 시작 게이트를 거치지 않고 sentinel 1개로 돌린 판정이다 |
| C-M4a | 같은 오라클을 코드 변경 없이 다른 추출기 3개(python-tarfile, oras-go, decompress)에 어댑터로 적용했고, 각 통제 차분에서 영향 쪽은 위반, 대조 쪽은 비위반으로 판정했다. python-tarfile은 같은 라이브러리의 추출 필터 설정(`fully_trusted` 대 `data`) 토글 비교다. oras-go(v2.6.1 대 v2.6.2)와 decompress(4.2.1 대 유지보수 포크 11.1.4)는 릴리스 비교다. 이 둘은 실제 추출기의 동작을 프로브로 관찰한 기록이 있고, 저장소 테스트의 오라클 판정은 그 사후 상태를 일회용 샌드박스에서 재현한 것에 내린 판정이다 | TESTED(오라클·어댑터 수준) · 실제 추출기 동작은 프로브 기록으로 observed, 오라클 판정은 재현한 사후 상태에 대해 observed | `tests/test_python_tarfile_generality.py`; `tests/test_oras_go_generality.py`, `experiments/repro/oras_go_cwd_hardlink.py`와 그 기록 `experiments/repro/evidence/oras_go_cwd_hardlink.json`; `tests/test_decompress_generality.py`, `experiments/repro/decompress_hardlink.py`와 그 기록 `experiments/repro/evidence/decompress_hardlink.json`; Ledger M4 행 가운데 오라클·어댑터 부분만. 테스트와 프로브 기록은 2026-10-27~30에 만들어졌고(감사 전) 다시 실행할 수 있다. CI 실행 43565082671(main `d954387`)의 check 작업이 세 일반성 테스트를 통과했다. GHA 실행 43571057146(`.github/workflows/repro-evidence.yml`, main `1e43eae`, 2026-11-14, 통제 재현)에서 oras-go와 decompress 프로브를 다시 실행했고 판정 값(영향 버전은 identity 공유, 수정 버전은 거부)이 커밋된 기록과 같았다 | 오라클·어댑터 수준의 주장이다. 퍼저 탐색의 일반성이나 효과에 대한 주장이 아니다. "모든 추출기"를 쓰지 않는다 |
| C-RUST | 같은 방식의 고정 입력 프로브를 Rust `tar` 0.4.35와 0.4.36에도 적용했다 | TESTED(고정 입력 프로브, 캠페인 아님) · observed | `experiments/repro/evidence/rust_tar_fixture_probe.json`; `experiments/preregistration/exposure-ledger.md`의 rust-tar 행; `docs/LOG.md` 2026-11-07 "Rust tar 고정 fixture 프로브 증거 수록" 줄 | "적용된다"까지만 쓴다. 프로브 결과의 해석이나 일반성은 쓰지 않는다. 사전에 결과를 알았으므로 등록 실험에서 뺐다. 생성 스크립트가 미머지 PR #261에 있어 main만으로는 다시 실행할 수 없다(감사 이후 기록으로만 쓴다) |
| C-EXP0 | 등록 실행 EXP-0(인프라 측정)은 15셀(R·D·S-u × seed 9001–9005, 캠페인당 실행 200)이 모두 유효했고 abort 0, 경계위반 사건 0이었다. 가설을 판정하지 않는다 | TESTED(등록 실행, 인프라 측정) · observed | `experiments/summaries/exp0-20261105-report.md`와 같은 이름의 `.json`; `paper/tables/exp0-summary.md`; `experiments/preregistration/exp0-pilot-v2.1.md` | 사건 0은 "위반이 없다"가 아니라 그 예산에서 관찰되지 않았다는 뜻이다. arm 비교의 근거가 아니다 |
| C-PILOT | 비등록 위험도 파일럿(7.5.2, 40 캠페인, 캠페인당 실행 2000)에서 네 arm 모두 첫 C1∨C2 사건이 있었고, 신뢰구간이 크게 겹쳐 arm의 순서를 말할 수 없다(R-walk 1/10, R-restart 4/10, D 4/10, S-u 6/10). abort는 11/40이다. 이 값은 표본 수 산정, R 변형 선택(D6), 사전등록 예측의 개정에 썼다 | 탐색(비등록) · observed | `experiments/summaries/exp3-hazard-pilot-v1-result.md` §1–§2; `experiments/summaries/raw-manifest-exp3-hazard-pilot-v1.sha256`; `docs/DECISIONS.md` D040 | arm의 우열이나 효과의 근거로 쓰지 않는다 |
| C-GO | EXP-3 train이 끝난 뒤 등록 규칙을 기계적으로 적용해 GO를 냈다(2026-11-13 23:37:16 KST). 세 arm을 합친 첫 C1∨C2 캠페인 수 31(기준 1 이상), 처리 용량 554(기준 76 이상), 인프라 실패 비율 .033(기준 .45 이하)이다 | 등록 규칙 적용과 독립 확인 · 합산값 observed | `paper/tables/exp3-go-inputs.md`; `experiments/summaries/exp3-train-go-decision.json`; `docs/LOG.md` 2026-11-13 "EXP-3 GO 판정" 줄(PR #368) | 합산값만 쓴다. GO는 합산값만 썼다; arm별 train 값은 S-TRAIN(탐색). 31에 분모를 붙이지 않는다. 효과의 근거가 아니다. 독립 확인은 순서·용량·할당 재생성까지이고, 31은 GO 당시 봉인 자료가 필요해 다시 계산하지 않았다 |
| C-DESIGN | 세 arm(R 무작위, D 구조 커버리지, S-u 상태 피드백)이 같은 어휘와 같은 예산을 쓰도록 설계했다. 가설·arm·표본 수·분석·판정표를 결과를 보기 전에 Git에 동결했다(2026-11-13, 동결 커밋 `72de299`). train(7.5.2, 탐색)과 holdout(7.4.4, 확증)을 나눴고, 결과는 해제 기록 PR #485 머지(2026-11-17 23:49:27 KST)까지 가렸다. 동결 전에 등록을 고친 내용(예측 문장, 판정표의 비기각 행, N 결정 규칙, 범위 문구, 동결일 정의)은 등록 실행을 시작하기 전의 개정이며 사전등록 변경 이력에 공개돼 있다. 사전등록에는 예측도 고정돼 있다: 문법 몬테카를로로 미리 계산한 상한 U_sim ≈ HR 1.1~1.3, 그래서 기대하는 결말은 비기각과 HR 2 배제다. 이것은 등록한 예측이며 결과가 아니다. S-u의 피드백은 corpus 입회(보존)에만 작용했고 연산 선택은 세 arm 모두 균등이었다(등록 설계) | DESIGNED·IMPLEMENTED(설계와 절차); 어휘 동일은 TESTED · observed | `experiments/preregistration/exp3-v1.md`; `experiments/preregistration/exp2-v1.md`; `experiments/preregistration/exp2-v1.md` §8(변경 이력); `docs/LOG.md` 2026-11-13 "EXP-3/EXP-2 사전등록 동결 기록" 줄; STATUS 감사 산출물 ⑤ 행(어휘 동등 단위테스트, EXP-0 어휘 동일); `docs/research/design/research-questions.md`; `src/inodefence/feedback/effect.py`(normalized_effect_signature)·`src/inodefence/feedback/effect_search.py`(입회 규칙, E `bed077a`) | "결과를 보지 않고는 어떤 결정도 없었다"를 쓰지 않는다(파일럿을 보고 표본 수를 정한 것은 공개된 사실이다). S-u를 설명할 때 exp2-v1 §6의 범위 문구를 지킨다: S-u의 boundary 키는 특정 패턴이나 경로를 담지 않지만 결함 계열 수준의 사전 지식이다. D는 구조 커버리지 유도 퍼징의 대리이며 코드 커버리지 기준선이 아니다. 등록 예측은 방법·설계를 설명하는 자리에서만 "사전등록 예측(결과 아님)"이라고 밝혀 쓰고, 값은 exp2-v1 §1의 것만 쓴다. 결과 자리 옆에는 두지 않는다. S-u의 effect 키에는 영향 경로가 보호 대상이며 추출 루트 밖인지를 나타내는 플래그가 들어간다(경로 이름은 넣지 않는다). 이 키는 모든 arm의 관찰에서 계산·기록되지만 보존 판단에는 S-u만 쓴다. S-u는 위반 지문(oracle 출력; 관찰된 경로를 담으며 보호 객체 경로가 들어갈 수 있다)으로도 보존한다. 위반 지문은 위반이 관찰된 뒤에만 생기고 패턴·CVE를 담지 않는다 |
| C-INFRA | 재현성 인프라를 갖췄다. raw 출력의 SHA-256 매니페스트, 요약이 raw까지 닿는지 검사하는 증거 사슬 점검(`make check`에 연결), 표 생성기와 커밋된 표의 바이트 대조, 호스트 적격성 검증(호스트별 12 캠페인, 두 호스트 통과)과 교차 호스트 비교(공통 셀 12개 중 12개 일치)다 | TESTED(도구); 적격성과 교차 비교는 그 조건에서의 observed | `experiments/summaries/`의 `raw-manifest-*.sha256`와 `scripts/make_raw_manifest.py`; `scripts/check_evidence_chain.py`; `scripts/regenerate_paper_artifacts.py`·`scripts/gen_table_m2.py`·`scripts/gen_exp3_tables.py`; `experiments/configs/host-qualification-v1.md`와 `scripts/qualify_host.py`; `docs/LOG.md` 2026-11-12 "HOST1 호스트 적격성 실행 결과" 줄, 2026-11-13 HOST2 적격성 줄과 "TBD-FREEZE 채움" 줄(교차 호스트 12/12) | 적격성은 "그 호스트, 실행 SHA `bed077a`, jobs 2, 실행 2000, 12 캠페인 조건에서 기준 충족"까지다. "장기 안정성", "환경 독립"을 쓰지 않는다. 12/12는 교차 호스트 비교의 값이다 |
| C-LIM1 | 한계: 현재 변이 문법에서 경계위반 입력은 seed에서 변이 1회 거리에 있다 | 사전등록에 기록된 설계 사실 · inferred(외부 검토와 문법 몬테카를로) | `experiments/preregistration/exp2-v1.md` §6(노출 공개와 한계)과 §8(변경 이력의 외부 검토 F1) | 이 한계를 빼고 탐색 난이도를 말하지 않는다 |
| C-LIM2 | 한계: 확증 범위는 node-tar 한 계보(train 7.5.2, holdout 7.4.4)와 하드링크 identity 공유 계열이다. holdout 7.4.4는 고정 입력에서 train과 같은 계열의 위반을 내는 릴리스다 | 설계 사실 · observed(C-HOSEL) | `experiments/preregistration/exp2-v1.md` §3; `docs/DECISIONS.md` D045; C-HOSEL의 근거 | 다른 추출기나 다른 결함 계열로 넓혀 쓰지 않는다 |
| C-LIM3 | 한계: 오라클은 추출 전후 두 스냅숏을 비교하는 탐지기다. 위반 없음(`violated=False`)은 관찰 범위 안에서 위반 증거가 없다는 뜻일 뿐이며, 두 시점 사이에 생겼다 사라진 변화, inode 번호 재사용, 샌드박스 밖 접근은 판정하지 못한다. entry 사이의 중간 상태 전이는 feedback 근거로만 쓰고 C0/C1/C2 판정으로 올리지 않는다 | DESIGNED·IMPLEMENTED(오라클의 정의에서 나오는 한계) · 설계 사실 | `docs/research/design/security-contracts.md`의 "무엇을 판정하지 못하는가 (한계)" 절; `docs/research/design/entry-effect-feedback-v2.md`("failure is not a nonviolation") | "안전하다", "위반이 없다"로 쓰지 않는다. 시험으로 확인한 성질이 아니라 설계상 한계로 쓴다 |
| C-OPS | 공개하는 운영 사실(주장이 아니다): EXP-3 train 중 HOST2 인프라 정지 1회(2026-11-13, 원인 기록 #366 뒤 재개, 정지에 걸린 2셀은 재실행하지 않음). EXP-2 holdout 중 HOST1 정지 2회·재개 2회, HOST2 정지 5회·재개 성공 5회(재개 시도 거부 1회). 정지마다 원인 기록 PR 머지 뒤 재개했다. 확인된 직접 원인은 Docker Desktop 무응답·backend 사망 등 인프라 층이며 근본 원인은 확인하지 못했다 | observed(인프라 기록) | `docs/LOG.md` 2026-11-17 "EXP-2 holdout 끝 기록" 줄(#369, 정지 횟수의 단일 기준)과 2026-11-15~17 원인 기록 줄; `paper/tables/exp3-go-inputs.md` | 원인이 생긴 층을 단정하지 않는다. 메모리 관찰의 인과는 추론이다 |
| C-HA | 같은 어휘·같은 예산 아래 상태 피드백(S-u)이 R·D보다 첫 경계위반까지의 실행 수를 줄이는가(H-A)를 등록 holdout(7.4.4)에서 확증 검정했고, 두 대비 모두 차이를 확인하지 못했다(분리 실패). 위험률 비 2배 이상의 가속은 구간으로 배제됐다 | **판정 완료: 비기각(분리 실패, HR 2 배제)** · observed(등록 검정) | `paper/tables/exp2-holdout-contrasts.md`(#487); `experiments/summaries/exp2-holdout-report.json`(#487); `experiments/preregistration/exp2-v1.md` §5 | "효과 없음", "반증", "상태 피드백은 쓸모없다"를 쓰지 않는다. 결과는 결함이 seed에서 변이 1회 거리인 이 벤치마크에 한정한다. U_viol(S-u가 더 많음)을 H-A의 근거로 쓰지 않는다(S-u만 위반 입력을 보존해 방향이 구조적으로 정해진다). 이 판정은 retention 피드백에 대한 것이다. 연산 선택(스케줄링) 피드백은 시험하지 않았다 |
| C-AUDIT | 해제 전 결과 가림의 열람 감사: 열람 감사(HOST1 세션 기록, 머지 전)에서 홀드아웃 셀 로그를 필터 없이 읽은 명령은 W1의 운영 진단 5건이었다. 판정 상태가 출력된 것은 이미 공개한 편차 2(S-u s9058 step 1329·1330 두 줄)뿐이고, 나머지는 인프라 줄이었다. HOST2 세션 기록은 W2가 자체 점검했고 W4가 추출본으로 다시 점검해 상태 줄 0건이었다 | observed(세션 기록 정규식 점검 + 수동 확인) | #487 본문 §5와 `docs/LOG.md` 2026-11-18 결과 줄 | HOST2 열람 감사는 W2 자체 점검을 W4가 추출본으로 재점검한 것이다. 정규식 점검이며 전수 판독이 아니다. "아무도 결과를 보지 않았다"를 쓰지 않는다. 공개 산출물에서는 세션 이름 대신 운영 진단·그 호스트 담당·별도 검토자로 쓴다 |
| C-DEV1 | 봉인 기간 중(2026-11-15) 다른 작업 레인이 확증 대상 밖 릴리스 node-tar 7.5.1에서 비등록 탐색 6건(등록 S-u 설정 3건, 데모 설정 3건)과 재실행 1건을 했다. 그중 1건은 출력이 삭제돼 결과 파일 해시를 복구할 수 없다. 등록 seed·등록 실행 경로가 아니며, 1건의 위반 수가 약 38분 동안 공개 PR 본문에 있었다. 분석 규칙·분류기·판정표는 그 전에 동결돼 있었다. 7.5.1 실행 값과 탐색 레인의 결과는 쓰지 않았다 | observed(공개 편차) | #485 본문 §4; `docs/LOG.md` 2026-11-17 해제 기록 줄 | 사전등록 밖의 편차로만 쓴다. 7.5.1 실행 값을 어디에도 인용하지 않는다 |
| C-DEV2 | 봉인 기간 중(2026-11-16 00:44) HOST1 Docker 정지 대응에서 S-u s9058 attempt 1 로그 끝을 출력해 step 2개(1329·1330)의 판정 상태 두 줄이 보였다. 같은 명령은 R s9057 로그 끝도 출력했으나 인프라 줄뿐이었다. 스스로 보고됐다. 분석 규칙·분류기·판정표는 그 전에 동결돼 있었다. 그 두 줄은 어떤 결정에도 쓰지 않았고, attempt 1의 분류는 E 출력으로 정했다 | observed(공개 편차) | `docs/LOG.md` 2026-11-17 "EXP-2 holdout 끝 기록" 줄(#369)과 2026-11-18 결과 줄(편차 2 보완) | 한 방식·한 seed의 두 step이라 방식 간 대비 정보가 없다는 점을 함께 쓴다; 두 줄의 값은 인용하지 않는다 |
| C-REPRO | holdout·train 결과 표는 저장소에 넣은 analyze_exp0 리포트에서 `make paper-artifacts`로 바이트 단위로 다시 만들어진다. train 리포트는 고정 manifest로 검증한 raw에서 GO 때와 같은 명령으로 다시 만들어 바이트가 같았다(088c9027) | TESTED(바이트 일치) · observed | #487 본문 §3·§6; `scripts/regenerate_paper_artifacts.py` | 첫 hit 출처 표·첫 hit 분할·접은 U_viol(보고 전용)은 미산출이다. 고정 스크립트가 26 GB 호스트에서 끝나지 않았으며, 이 값들이 있다고 쓰지 않는다 |
| C-V2BENCH | 후속 설계(v2)에서 피드백 이득이 날 여지가 있는 깊이 ≥ 2 벤치마크를 사전 규칙으로 찾았다. 고정 문법(`b-grammar-v2-freeze-3`)과 등록 seed 코퍼스에서 깊이 2 이상 계열은 L2-chain(심볼릭 링크 사슬) 하나였고(d* = 2), 피드백 없는 깊이 도달 무작위 기준(R 사슬, 실행당 연산 1~4개)의 캠페인당 도달 확률은 .047(95% 구간 .042~.054, 9.4M step 중 228회)로 사전 고정한 입회 하한 .05 아래였다(구간은 .05를 포함한다. 판정은 계산 전에 고정한 규칙 — 모든 실행을 합친 점추정이 .05 이상이면 입회 — 에 따른 것이다). 그래서 사전 규칙에 따라 확증 벤치마크를 만들지 않았다 | exploratory · 설계 단계 계산(대상 실행 없음) · observed | #509 RUN.md(Drive 01-분석·설계), depth-definition §2.3, `docs/LOG.md` 레인 A 줄 | 상태 피드백의 효과에 대한 주장이 아니다. "깊이 ≥ 2 결함이 없다"가 아니라 "이 문법·seed에서 입회 조건을 만족하는 계열이 없었다"로만 쓴다. 등록 seed s1이 O1·typeswap 계열을 깊이 1로 만든다는 사실을 함께 쓴다. v2.1 결과가 나오면 함께 보고한다. 구간이 하한을 포함하므로 '도달 확률이 .05보다 낮다'고 단정하지 않는다. 하한을 낮추거나 예산을 늘려 다시 판정하지 않았다 |
| C-V21BENCH | v2가 입회 실패한 뒤 사전 규칙을 정한 재설계 1회(v2.1: 디렉터리·링크 없는 최소 seed 코퍼스)에서, 고정 문법으로 깊이 2 계열 셋(L2-chain·L2-typeswap·O1-order)을 얻었다. 입회 조건(무작위 사슬 R 도달 확률 .05~.70, 예측 가속 상한 U_sim ≥ 2)을 만족한 것은 L2-chain 하나였다(p_R .072 [.065, .080], U_sim 3.41 [2.67, 4.13]). 대응 결함으로 확인한 버전은 현재 실행 환경으로 돌릴 수 없는 node-tar 6.1.1 이하였다. 7.5.7 이하의 합성 링크 결함(CVE-2026-26960)이 같은 계열인지는 확인하지 않았다(보유 버전 분석의 누락, 결과를 본 뒤 확인). 가용 호스트 21일 실행으로는 위험률 비 2에서 검정력이 .63(정지 공백 7.15% 반영; 공백 0%에서도 .67)이라, 사전 정한 정지 규칙에 따라 확증 시험을 하지 않았다. 이 결정은 검정력(.63 < .80)만으로 같다 | exploratory · 설계 단계 계산(대상 실행 없음) · observed | `20261118-HOST1-509-v2-v21-요약.md`(Drive 01-분석·설계), depth-definition §2.4·§2.5, power-result-l2chain.json, carrier-advisory/ | 상태 피드백이 깊은 결함에서 돕는지에 대한 주장이 아니다. "우리 자원 안에서 검정력이 부족했다"이지 "불가능하다"가 아니다. O1-order의 입회는 U_sim 정의에 따라 달라졌다(고정한 정의로 미입회). L2-chain의 U_sim은 표집된 near-miss 52개(생성이 드물고 토큰이 다양해 엔진의 near-miss 공간은 더 큼)에서 냈고 코퍼스 20 민감도는 1.84(<2; 입회는 고정 코퍼스 10 기준). 고정한 조건 "200개 이상 또는 존재하는 전부"는 어느 쪽도 충족되지 않았다(52 < 200이고 52개는 표본이다)(결과는 안 바뀐다 — NO-GO는 검정력에서). 정지 공백 7.15%는 #369 raw에서 D043 규칙으로 계산했다(명시값 아님). v2.1 코퍼스는 v2 결과를 본 뒤 정했다. 보유 버전 분석은 CVE-2026-26960(GHSA-83g3-92jg-28cx, ≤7.5.7)을 빠뜨렸다. 실행 가능한 7.x에서 이 계열의 증인 입력을 시험하는 길은 택하지 않았다(순수 2-symlink 증인이 그 결함과 구조가 맞는지는 확인하지 않았다). C-V2BENCH와 함께 쓴다 |

## 제품 주장 표 (`inodefence` 명령, 0.2.0)

2026-11-17 지웅 지시로 더한 행이다. 사용자 명령 `inodefence`(제품 계층)에 대한 주장이며 연구 가설(H-A)과는 별개다.
따로 적지 않은 행은 Windows + WSL2(Ubuntu 24.04) + Docker Desktop(Engine 29.9.3) 호스트 한 대의 `demo run`(engineering smoke)이고
등록 실험이 아니다. 0.2.0의 릴리스 조건(D049) 6개는 2026-11-18에 `main`에서 기록으로 충족됐고, 0.2.0은 태그 `v0.2.0`(커밋 `ba6fa6f`, 2026-11-18)과 GitHub Release로 릴리스됐다. 제품 코드와 근거 문서는 2026-11-18에
`main`에 병합됐고(#484; 행에 적힌 `f108e36`·`6a2031f`·`aa4cda3`·`b4eb150`은 측정한 시점의 커밋이다), 실행 기록 원본은 저장소 밖의 비공개 Drive 보관소에 있다(`InodeFence/Archive/Local-Records-20261118/`와 `InodeFence/Release-0.2.0/`; 2026-11-18에 HOST4의 로컬 사본은 해시 대조 뒤 지웠다). 위 "쓰는 규칙"을
그대로 지킨다. 값은 적힌 그대로 쓰고 올림하거나 다른 버전으로 넓히지 않는다.

| ID | 쓸 수 있는 말 | 증거 수준 · 관찰 구분 | 근거 경로 | 용도 제한 · 쓰면 안 되는 말 |
| --- | --- | --- | --- | --- |
| C-PCLI | 사용자 명령 `inodefence`가 `doctor`(환경 점검) → `targets`(대상 목록) → `verify`(고정 입력 회귀 검사) → `explore`(피드백 탐색) → `status`·`summary`(확인과 요약) → `replay`(케이스 재실행)의 흐름으로 돈다. 커밋 `f108e36`의 깨끗한 클론과 새 venv에서 `doctor`는 종료 0(UNKNOWN 1: WSL 메모리), `targets`는 대상 4개를 보였다. `verify`는 네 대상 모두 정상 입력 대조군이 ok였고 고정 공격 입력의 위반은 0/5(oras-go 0/6)였다 | TESTED · observed(`demo run`, 호스트 한 대, 2026-11-17) | `docs/USAGE.md` "지원 환경과 확인 수준" 절; `docs/LOG.md` 2026-11-17 "PR-B 통합 head의 깨끗한 클론 E2E" 줄; `README.md` 빠른 시작; 실행 기록은 저장소 밖 | 이 행의 측정은 WSL2 호스트 한 대의 값이다(두 번째 환경은 C-PLIM). `verify`의 고정 입력은 모두 공격 형태이고 최신 버전이 전부 거부했다. "모든 환경에서 동작"을 쓰지 않는다. 릴리스 사실은 C-PLIM에 적힌 대로만 쓴다 |
| C-PEXP | `explore`는 실제 추출기를 격리 컨테이너에서 돌리며 입력을 변이하고 C0/C1/C2로 판정한다. node-tar 7.5.23, seed 20261117, budget 300 실행(커밋 `6a2031f`)은 300/300을 약 10분에 완주했고(0.518 runs/s) success 200 · rejected 99 · failed 1, 미판정 1, 위반 0, 남긴 corpus 17이었다. step 기록마다 입력 해시, 부모, 변이, 선택, 관찰 trace, 오라클 판정, 피드백이 연결돼 있다. 이 실행들에서 퍼저는 위반을 찾지 못했다(대상은 최신 버전이다) | TESTED · observed(`demo run`, seed 1개, 비교 arm 없음) | `docs/USAGE.md` "지원 환경과 확인 수준" 절의 "node-tar 더 긴 탐색" 항목; `docs/LOG.md` 2026-11-17 "PR-B 통합 head의 깨끗한 클론 E2E" 줄; 실행 기록은 저장소 밖(`manifest-6a2031f.sha256`) | 위반 0은 이 예산에서 관찰되지 않았다는 뜻이다. node-tar 7.5.23이 안전하다는 근거가 아니다. 탐색 성능이나 arm 비교의 수치로 쓰지 않는다. "퍼저가 찾았다", "발견"을 쓰지 않는다. 통제 재현(C-M2)은 사람이 만든 고정 입력의 판정이고, 이 행은 퍼저의 자력 탐색 실행이다. 둘을 섞어 쓰지 않는다 |
| C-PTGT | 네 추출기의 지원 범위(커밋 `f108e36` 깨끗한 클론, `explore` budget 20, seed 123): node-tar 7.5.23 success 17 · rejected 3, python-tarfile 3.12.16 `data` 필터 success 12 · failed 5 · rejected 3, decompress(`@xhmikosr/decompress@11.1.4`) success 11 · rejected 9, oras-go 2.6.2 success 0 · rejected 20과 "추출 성공 0건" 경고. 네 대상 모두 위반 0, 미판정 0이다. oras-go의 0건은 `f108e36` 시점의 값이다. 그 뒤 제품 탐색 입력을 아티팩트 디렉터리 `d/` 아래로 보내는 수정(D049 조건 1, #484)이 들어가, `b4eb150`의 화면 기록(C-PREC)과 arm64 VM(C-PLIM)에서는 같은 seed·예산에서 success 11 · rejected 9이고 경고가 없다. oras-go 탐색은 실험적이며 유의미한 보안 커버리지를 주장하지 않는다 | TESTED · observed(`demo run`, 호스트 한 대, 2026-11-17) | `docs/USAGE.md` "지원 환경과 확인 수준" 절의 대상별 표; `docs/LOG.md` 2026-11-17 "PR-B 통합 head의 깨끗한 클론 E2E" 줄 | 버전과 설정은 적힌 것만이다. python-tarfile은 `data` 필터만 탐색한다(`fully_trusted` 탐색은 설계상 거부). "네 추출기가 안전하다", "여러 추출기에 일반화된다"를 쓰지 않는다. oras-go의 지금 동작을 쓸 때는 0건이 아니라 success 11 · rejected 9를 쓰고, 추출이 일어난다는 것이 "실험적" 표시를 바꾸지 않는다(이 탐색의 변이가 oras-go의 알려진 하드링크 결함 형태에 닿지 않는다고 보는데, 이것은 코드를 읽고 한 추론이며 실행으로 확인하지 않았다, 이슈 #499). 오라클·어댑터 수준의 통제 차분(C-M4a)과는 다른 근거다 |
| C-PREPLAY | `replay`는 네 대상 모두를 받는다. 위반이 없는 케이스를 3회씩 다시 돌려 네 대상 모두 원래 판정(위반 없음)과 3/3 일치했다. 이 케이스들은 탐색의 0번째 입력으로 조립한 통제 케이스 폴더다. 이 행의 2026-11-17 측정에서는 실제 위반 케이스의 native 재실행을 하지 않았다(탐색에서 위반이 없었다). 그 측정에서 위반이 재현되는 경로는 통제·합성 단위 테스트로만 확인했다. 탐색 결과 폴더는 위반 step의 입력만 저장하므로, 위반이 없는 결과 폴더에 대한 `replay`는 실행 전에 거부된다(종료 2) | TESTED · 비위반 재실행은 observed(`demo run`), 위반 재현 경로는 합성 단위 테스트(native 아님) | `docs/USAGE.md` "지원 환경과 확인 수준" 절의 replay 항목과 "위반 후보 재실행(재현 확인)" 절; `docs/LOG.md` 2026-11-17 "PR-B REPLAY 레인" 줄; 거부 화면은 2026-11-18 화면 기록(C-PREC) | "위반을 재현했다"를 쓰지 않는다. 합성 단위 테스트 결과를 native 증거로 쓰지 않는다. 조건 4 기록(decompress@4.2.1 C0 위반 케이스 `replay` 3/3 재현)의 한계: 같은 케이스를 같은 입력·이미지·설정으로 2026-11-18에 모두 60회 실행했다(위 3회 포함, 서로 겹치지 않는 실행). 51회는 같은 C0 위반(추출기 정상 종료), 9회는 추출기가 거부해 위반 없음이었다(관찰). 이 추출기 버전에서 이 케이스의 재현은 실행마다 달라질 수 있고, 3/3은 그 가운데 세 번이 연속으로 재현된 관찰이다. 이 추출기 버전은 entry를 동시에 처리하며(코드 관찰: `Promise.all`로 모든 entry를 함께 처리), 경로 검사와 쓰기 사이의 순서가 실행마다 달라질 수 있다고 본다(추론, 타이밍은 측정하지 않음). |
| C-PFAST | `explore --profile fast`는 실행 시작부터 컨트롤러 준비까지의 구간을 실행당 2.78 s에서 1.33 s로 줄인다(node-tar 7.5.23, seed 123, budget 20, 번갈아 5회씩). 케이스당 시간과 처리량은 그대로다(1.96 s 대 1.92 s). 5쌍에서 step 입력과 판정이 같았다 | TESTED · observed(`demo run`, 호스트 한 대, 성능 측정 아님) | `docs/USAGE.md` "한계와 주의" 절의 실행 프로필 항목; `docs/LOG.md` 2026-11-17 "PR-B FAST 레인" 줄 | 퍼징이 빨라진다고 쓰지 않는다. 기본은 STRICT이고 `replay`는 항상 STRICT다 |
| C-PLIM | 제품 한계: 확인한 환경은 둘이다. Windows + WSL2(x86_64) + Docker Desktop 호스트 한 대와, 맥북 위 가상머신인 Ubuntu 24.04 arm64 VM(Multipass, WSL 아님) + Docker Engine 한 대다. arm64 VM에서는 2026-11-18에 커밋 `8620d54`의 깨끗한 클론을 USAGE 그대로 설치해 네 대상의 `verify`·`explore`(seed 123, 실행 20)·`status`·`summary`가 모두 종료 0이었고, 유효 추출 수가 x86_64와 같았다(17·12·11·11, `demo run`). x86_64 네이티브 Linux와 macOS는 확인하지 않았다. 0.2.0은 릴리스 조건(D049) 6개가 `main`에서 충족된 뒤 태그 `v0.2.0`(커밋 `ba6fa6f`, 2026-11-18)과 GitHub Release로 릴리스됐다. PyPI 같은 패키지 저장소에는 게시하지 않았고, 설치 방식은 `docs/USAGE.md`의 설치 표대로다. 실행 중 수치 표시는 node-tar만 되고 나머지 세 대상은 실행 중 `?`로 표시된다. 멈춘 탐색을 이어 하는 기능(resume)은 이 스택에 없다(보류된 브랜치에 구현돼 있고 병합되지 않았다). 오라클은 실행 전후 상태를 비교하므로 위반 없음은 안전 증명이 아니다(C-LIM3) | 설계·운영 사실 · observed | `docs/USAGE.md` "지원 환경과 확인 수준" 절과 "한계와 주의" 절; `CHANGELOG.md` 0.2.0 머리말; `docs/LOG.md` 2026-11-17 "PR-B 통합 head의 깨끗한 클론 E2E" 줄(RESUME 레인 보류); `docs/LOG.md` 2026-11-18 "D049 조건 6" 줄(두 번째 환경) | resume을 제품 기능으로 쓰지 않는다. 릴리스는 "0.2.0을 태그 `v0.2.0`(2026-11-18)으로 릴리스했다"까지만 쓴다. "안정 버전", "정식 출시", "패키지로 배포"를 쓰지 않는다. "설치만 하면 어디서나 된다"를 쓰지 않는다. "두 환경"은 arm64 VM 한 대를 포함한 수이고, 다른 행의 측정값(300회 탐색, `verify` 수치 등)은 x86_64 한 대의 값으로만 쓴다 |
| C-PREC | 소개 영상의 CLI 화면에 쓰는 실행 기록은 2026-11-18(UTC 2026-11-17 17:35~17:43)에 `b4eb150`의 깨끗한 클론과 새 venv에서 `script`로 남긴 실제 실행 기록이다. 기록한 셸은 중립 경로(`/var/tmp/inodefence-demo-b4eb150`, HOME과 USER를 그 아래로 설정)에서 돌았고, 화면은 사후에 고치지 않았다. 그 기록에서 `doctor`는 종료 0(UNKNOWN 1), node-tar 7.5.23 `verify`는 정상 입력 대조군 ok와 위반 0/5였고, `explore` seed 123 budget 40은 40/40(success 28 · rejected 12, 미판정 0, 위반 0, 0.293 runs/s, 약 3분)이었다. 나머지 세 대상의 `explore` budget 20 seed 123은 python-tarfile 3.12.16 `data` 필터 success 12 · failed 5 · rejected 3, decompress(`@xhmikosr/decompress@11.1.4`) success 11 · rejected 9, oras-go 2.6.2 success 11 · rejected 9였고, 네 대상 모두 위반 0, 미판정 0이다. 위반이 없는 결과 폴더에 대한 `replay` 두 건은 실행 전에 거부됐다(종료 2). 2026-11-17에 `aa4cda3`에서 남긴 이전 기록은 oras-go 수정 전의 것(success 0 · rejected 20)이라 이 기록으로 바꿨다 | TESTED · observed(`demo run`, 기록 6개, 호스트 한 대) | 비공개 Drive `교내 경연대회/영상/05-CLI 실행 기록(b4eb150)/`의 `rec01`–`rec06`(`.typescript`·`.timing`·`.cmd.sh`·`.stdout.log`·`.meta.json`)과 `SHA256SUMS`(30개; 그 파일의 sha256 `be46dafe5cf30e40297b8eb0318b7635caafeaa2379c49f816eecef7f0dd7dc6`); 이전 기록은 같은 위치의 `05-CLI 실행 기록(aa4cda3)/`(`SHA256SUMS`의 sha256 `a4b4696f50d93880f264bc03912d4b8858a7654dc69b6172830f2d3a21597c32`); 재생 도구 `paper/deliverables/video/build_video.py`의 `SEQUENCES` | 화면 기록이며 등록 실험이 아니다. 배속 재생은 화면 머리말에 배속을 표시한다. budget 40 값은 이 기록의 값으로만 쓴다. runs/s와 걸린 시간은 실행 시점의 호스트 부하에 따라 달라지며(이전 기록은 같은 명령에서 0.598 runs/s, 86 s) 성능 수치로 쓰지 않는다. 영상과 보고서가 이 기록을 실제로 쓰는지는 `paper/deliverables`의 상태를 따른다(2026-11-18 현재 영상 도구는 이전 기록의 날짜와 수치를 적고 있다) |
| C-PQA | `main`의 깨끗한 클론에서 검사 묶음 `make check`(lint·format·타입 검사·테스트·환경·문서 링크·증거 사슬)가 통과한다: 2026-11-17 커밋 `7ee495b`, 테스트 5970 passed · 8 skipped. CI에는 설치된 `inodefence`를 네 대상의 실제 추출기에 돌리는 `product-e2e` job이 있고, `main` `043fc31`의 실행(run 44129454056, 2026-11-17)에서 이 job을 포함해 모두 통과했다 | TESTED · observed(자동 검사) | `docs/LOG.md` 2026-11-17 "깨끗한 클론 확인" 줄; `.github/workflows/ci.yml`; `scripts/dev/product_e2e.py` | "테스트 약 6천 개"는 위 수(5970)를 반올림한 말이다. 단위 테스트는 Docker를 mock한다. 검사 통과는 도구가 돈다는 뜻이고 대상 추출기가 안전하다는 뜻이 아니다. 연구 가설의 근거로 쓰지 않는다 |
| C-PRUN | python-tarfile·decompress·oras-go의 호스트 런처는 탐색 본체와 로컬 CLI 조회를 뺀 모든 Docker 데몬 호출에 시간 제한을 두고(조회 30초, 생성 60초, 정리 60초, 빌드 1800초 등), 정리 실패·시간 초과·제거 미확인이면 성공이던 실행을 런처 종료 125(제품 종료 2, 결과 미발행)로 바꾼다. 정리 명령을 75초 늦추거나 실패시킨 시험에서 런처는 125로 끝났고, 다른 소유 표시의 볼륨은 쓰지도 지우지도 않았다 | TESTED · observed(가짜 Docker 단위 테스트 48개; 실제 Docker 시험은 `demo run`, 호스트 한 대, 2026-11-18, 커밋 `0f37cfc`) | `CHANGELOG.md` "변경된 동작과 호환성"; `docs/LOG.md` 2026-11-18 "D049 조건 3" 줄; `tests/test_target_launchers_bounded.py`; `scripts/launcher_bounded.sh` | 탐색 본체에는 시간 상한이 없다. node-tar 런처는 기존 방식 그대로다. 컨테이너 격리 인자는 소유 표시 label 하나 외에 변경 전후가 같다. 등록 실험과 무관하다(등록 실행이 끝난 뒤의 변경). 실제 Docker 시험 뒤에 바뀐 증거 게시 폴백은 단위 테스트로만 확인했다. "멈추지 않는다", "실험의 정지를 고쳤다"를 쓰지 않는다 |

## 본실험 결과 자리

| 자리 | 들어갈 내용 | 상태 | 쓰는 문장 |
| --- | --- | --- | --- |
| S-TRAIN | EXP-3 train(7.5.2)의 탐색 대비. 탐색이며 효과의 근거가 아니다 | 채움(2026-11-18, #487) | 짧은 판: 「EXP-3 train(7.5.2) 탐색 대비: S-u 대 R p .54, S-u 대 D p .43(탐색적, 판정 없음).」 긴 판: 「EXP-3 train(node-tar 7.5.2, 등록 seed 블록 20, k 5, 예산 2000)의 탐색 대비(exp3-v1 §6)는 S-u 대 R 19블록·사건 21·탐색 p .5367, S-u 대 D 19블록·사건 22·탐색 p .4268이었고, 세 abort 정책에서 같았다. 이 대비는 탐색적이며 판정이 없다. 7.5.2는 사전 노출된 버전이고, 이 결과로 holdout 가설·arm·표본 수·분석 기준을 바꾸지 않았다. 확증 판정은 EXP-2 holdout(7.4.4)만이다.」 |
| S-HOLDOUT | EXP-2 holdout(7.4.4)의 확증 판정(H-A). 사전등록 판정표의 문장만 쓴다 | 채움(2026-11-18, #487, D12 칸 「분리 실패, HR 2 배제」, W3·W4 서명) | 「두 대비 모두 차이를 확인하지 못했다(Holm 보정 p .9306, .9048). Peto 위험률 비는 1.015 [.735, 1.425], .887 [.658, 1.219](seed 블록 부트스트랩 95% 구간)로, 두 대비 모두 구간 상한이 2보다 작아 '상태 피드백이 첫 위반까지의 위험률을 2배 이상 높인다'는 크기의 효과는 배제된다. 두 구간 모두 U_sim(≈ 1.1~1.3)과 겹쳐, 등록된 읽기로는 문법 수준 기대와 일치한다. 결과는 결함이 seed에서 변이 1회 거리인 이 벤치마크에 한정되며, 상태 피드백 일반의 효과에 대한 결론이 아니다.」 요약: 「S-u는 R·D 어느 쪽과도 구분되지 않았고, 위험률 비 2 이상의 가속은 구간으로 배제됐다(결함 깊이 1 벤치마크).」 |

영상은 장면 6 자리와 결론 장면을 S-HOLDOUT 자리로 비워 둔다.

결과 자리에는 위 문장만 쓴다. 순열 p는 몬테카를로 10만 회 값이다. U_viol은 보고 전용 문단에 등록 단서(S-u만 위반 입력을 보존해 방향이 구조적으로 정해지며 H-A의 근거가 아니다)와 함께만 쓴다.

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

## 탐색 기록 — 알려진-버전 위반 도달 (X-; arm 아님, 능력 주장 아님)

아래는 **탐색 기록 행**이다. **능력(claim) 주장이 아니다** — "알려진 결함 버전에서 관찰된 위반 도달
(탐색 기록)"이며 위 주장 표의 어떤 C-ID paper-ready 판정도 바꾸지 않는다. 셀은 **서로 arm으로 비교하지
않는다**(같은 호스트, 버전·정책만 다름). generic oracle은 위반을 CVE에 귀속하지 못한다. "재발견/발견"
금지. 가드(W4): "v1·v2 셀은 같은 엔진(e1098d6)에서 변이 정책만 다르다. 등록 arm이 아니고 비교 설계가 아니므로(사전등록 없음, 검정 없음) 비교하지 않는다. 같은 표에서 서로 다른 블록에 두고, 둘 사이의 차이·비율·우열 문장을 쓰지 않는다."

동결: `experiments/preregistration/exp517-host3-cells-v1.md`. 승인 W4 c1562032·ORCH D-235.

| 행 | 셀 (engine e1098d6) | seed 블록 | 상태 | 도달 k/6 · replay · 포화/candidate |
| --- | --- | --- | --- | --- |
| X-Q1 | 7.5.23 v1 (Q1, engine 5cc002b) | 51600번대 9 seed | 채움 대기(HOST3 종료표) | 누적 85 distinct(개별 35), 외부변화 0, 포화 발동 [0,0,0]; number-check PASS |
| X-517-7.5.7-v2 | 7.5.7 v2 | 56601–56610 | 대기(실행 전) | — |
| X-517-7.5.7-v1 | 7.5.7 v1 | 56611–56620 | 대기(실행 전) | — |
| X-517-7.5.8-v2 | 7.5.8 v2 | 56621–56630 | 대기(실행 전) | — |
| X-517-7.5.8-v1 | 7.5.8 v1 | 56631–56640 | 대기(실행 전) | — |
| X-517-7.5.2-v2 | 7.5.2 v2 | 56641–56650 | 대기(실행 전) | — |
| X-517-7.5.2-v1 | 7.5.2 v1 | 56651–56660 | 대기(실행 전) | — |
| X-517-7.5.3-v2 | 7.5.3 v2 | 56661–56670 | 대기(실행 전) | — |
| X-517-7.5.3-v1 | 7.5.3 v1 | 56671–56680 | 대기(실행 전) | — |
| X-517-7.5.6-v2 | 7.5.6 v2 | 56681–56690 | 대기(실행 전) | — |
| X-517-7.5.6-v1 | 7.5.6 v1 | 56691–56700 | 대기(실행 전) | — |
| X-517-7.5.11-v2 | 7.5.11 v2 (깨끗 통제) | 56701–56710 | 대기(실행 전) | 위양성 0 기대 |
| X-517-7.5.11-v1 | 7.5.11 v1 (깨끗 통제) | 56711–56720 | 대기(실행 전) | 위양성 0 기대 |

이 표의 어떤 행도 novelty·effectiveness·일반성 주장으로 승격하지 않는다.

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
하드코딩 없이 관통한다. retention 피드백의 효과(C-HA)는 등록 실험에서 판정됐다: 비기각(분리 실패, HR 2 배제).
