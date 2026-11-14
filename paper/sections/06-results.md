# 5. Results (드래프트 v2)

이 절의 모든 문장은 주장 목록([`claims-evidence-status-v1.md`](claims-evidence-status-v1.md))의 한 행을 근거로 하며,
문장이나 문단 끝의 `[C-…]`가 그 행이다. 능력 판정의 단일 기준은 Capability Ledger([`../../docs/STATUS.md`](../../docs/STATUS.md))다.
observed(실행 출력으로 확인)와 inferred(추론)를 소절마다 구분한다.

## 5.1 M1 — 루프가 실제 node-tar에서 돈다 (TESTED)

실제 node-tar에서 입력 생성 → 실행 → entry별 중간 상태 관찰 → C0/C1/C2 판정 → feedback → 다음 변이 선택의 루프가
한 명령(`make demo`)으로 반복 실행된다. 실행 기록은 `demo run`으로 라벨링하며, 끝 화면은
[`make-demo-screen.png`](../figures/make-demo-screen.png)(2026-11-07 기록 재생)이고 결과 재생 검증은 `make replay`다 [C-M1].
현재 main(`ff83fbe`)에서 `make demo`의 기본 입력(seed 123, 실행 20)으로 돌린 데모는 node-tar 7.5.22에서 20 step(성공 18,
거부 2)을 실행했고 위반 0, 고유 effect 키 25, 보상 step 3회(데모가 찍는 번호로 step 6·13·20), 코퍼스 4 → 7이었다(GHA 실행 43565892214,
아티팩트 `campaign-native-make-demo-s123`) [C-M1]. 위반 0은 이 데모 예산에서 관찰되지 않았다는 뜻이며 node-tar 7.5.22가
안전하다는 근거가 아니다. 고유 effect 키, 보상 step, 코퍼스 크기는 비교 arm이 없는 seed 1개 데모의 값이므로 탐색 성능이나
arm 비교의 수치가 아니다. 2026-11-06 기록과 같다고 말할 수 있는 것은 step 수 20과 위반 0뿐이고, 2026-11-07 화면 기록(위 끝 화면)과는 성공 18·거부 2,
위반 0, 고유 effect 키 25, 보상 step 6·13·20, 코퍼스 4 → 7이 같다. step 번호는 데모가 찍는 번호(1부터)이며 리포트 JSON의
`index`는 0부터 센다 [C-M1].
이것은 루프가 돈다는 엔지니어링 증거이며 탐색 효과의 근거가 아니다 [C-M1].

## 5.2 오라클 대조와 M2 통제 차분 (TESTED, observed)

**오라클 대조(통제용 테스트 추출기).** 경계 검사 없이 entry를 그대로 따르는 통제용 테스트 추출기(in-process, 일회용
샌드박스 안)에 고정 입력 4개를 넣어 오라클을 대조했다. 정상 입력은 위반 없음, 추출 루트를 벗어나는 경로의 파일은 C0,
sentinel을 가리키는 하드링크는 C1과 C2, symlink를 만든 뒤 그 경로에 쓰는 입력은 C2로 판정된다(`scripts/oracle_fixture_check.py`,
`tests/test_oracle_fixtures.py`; CI 실행 43565082671, main `d954387`의 check 작업). 오라클 검증이며 node-tar 결과가 아니고,
고정 입력 4개에 대한 대조라 탐색 성능의 근거가 아니다 [C-ORACLE].

**node-tar 통제 차분.** 손으로 만든 결정론적 하드링크 고정 입력 2개(외부 참조파일 대상, 추출 디렉터리를 벗어나는 같은 상대 경로; 최상위와
중첩)를 node-tar 5개 릴리스(7.5.2 / 7.5.3 / 7.5.6 / 7.5.7 / 7.5.8)에 돌려, "추출된 객체가 외부 참조파일의
`(st_dev, st_ino)`를 공유하는가"라는 C1 관찰로 판정했다. 릴리스 번호나 정답 경로를 판정 조건에 넣지 않았다 [C-M2].
전체 표는 [M2 증거표](../tables/m2-cross-release-evidence.md), raw는
[`../../experiments/repro/evidence/summary.json`](../../experiments/repro/evidence/summary.json), 검증 요약은
[cross-release-identity-repro-v1](../../experiments/summaries/cross-release-identity-repro-v1.md)다. raw는 2026-10-25(`86a4585`)에
만들어졌고 같은 스크립트로 다시 실행할 수 있다(docker 필요). 2026-11-06 main `23e5c66`에서 다시 실행한 결과가 커밋된 raw와
차이 0이었고, CI 실행 43565082671(main `d954387`)의 check 작업이 판정 일치 테스트를 통과했다 [C-M2].

![node-tar 릴리스별 하드링크 identity verdict 그리드: top-level와 nested fixture × 7.5.2–7.5.8](../figures/m2-cross-release-evidence.png)

*그림 1 — 릴리스별 verdict(observed). 데이터 [표 M2](../tables/m2-cross-release-evidence.md),
생성 소스 [`../figures/render_m2_cross_release.py`](../figures/render_m2_cross_release.py).*

- **observed.** 최상위 입력은 7.5.2에서 외부 참조파일과 identity를 공유(nlink 1→2)하고 7.5.3부터 거부된다. 중첩 입력은
  7.5.2에서 공유, 7.5.3에서 거부, 7.5.6에서 다시 공유, 7.5.7·7.5.8에서 거부된다. 같은 오라클 하나가 두 전환을 서로 다른
  결함으로 구분한다 [C-M2].
- **inferred.** 최상위 쌍(7.5.2 → 7.5.3)을 CVE-2026-23745에, 중첩 쌍(7.5.6 → 7.5.7)을 CVE-2026-24842에 대응시키는 것과
  7.5.6의 공유가 앞선 수정이 도입한 회귀라는 원인 서술은 추론이다 [C-M2].
- **production 경로 일치.** 손 probe 판정과 production Observer+Oracle 판정의 일치를 테스트로 고정했다
  ([`../../tests/test_cross_release_oracle_agreement.py`](../../tests/test_cross_release_oracle_agreement.py)) [C-M2].

이것은 **통제 재현이며 퍼저의 탐색 결과가 아니다**. 고정 입력은 사람이 만든 것이고, 하드링크·링크 상태 관찰·버전
차분 자체는 선행연구(§3)가 다루므로 신규 기여로 표현하지 않는다 [C-M2].

## 5.3 고정 입력 회귀 명령과 holdout 릴리스 선정 점검

- **회귀 명령.** `make regression TAR_VERSION=<x>` 한 명령으로, 알려진 경계 고정 입력이 그 릴리스에서 아직 C1/C2를 내는지
  확인할 수 있다(`scripts/regression_check.py`, `tests/test_regression_check.py`). 고정 입력 회귀 확인이며 탐색 성능의
  근거가 아니다 [C-REG].
- **holdout 선정 점검.** holdout 릴리스를 정하려고 후보 5개(7.0.1·7.1.0·7.2.0·7.3.0·7.4.4)에 고정 입력 5개를 한 번씩
  실행했다. 다섯 후보 모두 하드링크 입력 2개는 위반, symlink 입력 3개는 통과, 오류 0이었다. 이 입력들로는 7.0–7.4를
  구분할 수 없어, 7.4.4는 최고 버전 규칙으로 골랐다 [C-HOSEL]. 이 점검은 qualification-only이며 퍼징 캠페인이 아니고,
  오라클·측정 사슬의 근거로만 쓴다 [C-HOSEL].

## 5.4 측정 사슬의 양성·음성 대조

- **(가) 캠페인 경로 양성 대조.** 등록 실행과 같은 캠페인 경로로 node-tar 7.5.2에서 S-u 1셀(seed 8002, 실행 2000)을
  돌렸다. HOST1은 위반 사건을 기록했고 첫 사건은 step 685, 계약 C2였다. HOST2도 같은 값이었다 [C-PC].
- **(나) 고정 입력 대조.** 등록 실행 경로 밖에서 돌린 고정 입력 1개(sentinel 1개)가 7.5.2와 7.4.4에서 C1·C2 위반으로,
  수정 릴리스 7.5.3에서는 거부·비위반으로 판정됐다 [C-PC].

두 대조는 측정 사슬(경로 민감도)의 근거이며 탐색 성능의 근거가 아니다. (가)의 첫 사건은 C2뿐이므로 "탐색이 C1에
도달한다"의 근거도 아니다 [C-PC].

## 5.5 M4 — 다른 추출기에 대한 오라클·어댑터 수준 적용 (TESTED)

같은 C0/C1/C2 오라클을 코드 변경 없이 다른 추출기 3개에 어댑터로 적용했고, 각 통제 차분에서 영향 쪽은 위반, 대조 쪽은
비위반으로 판정했다 [C-M4a].

- **python-tarfile.** 같은 라이브러리의 추출 필터 설정 토글 비교다: `fully_trusted`는 위반, `data`는 거부·비위반
  ([`../../tests/test_python_tarfile_generality.py`](../../tests/test_python_tarfile_generality.py)) [C-M4a].
- **oras-go(v2.6.1 대 v2.6.2)와 decompress(4.2.1 대 유지보수 포크 11.1.4).** 릴리스 비교다. 이 둘은 실제 추출기의 동작을 프로브로 관찰한 기록이 있고(`experiments/repro/evidence/`의 증거 JSON),
  저장소 테스트(`tests/test_oras_go_generality.py`, `tests/test_decompress_generality.py`)의 오라클 판정은 그 사후 상태를
  일회용 샌드박스에서 재현한 것에 내린 판정이다 [C-M4a].
- **Rust `tar`.** 같은 방식의 고정 입력 프로브를 0.4.35와 0.4.36에도 적용했다(`experiments/repro/evidence/rust_tar_fixture_probe.json`).
  이 프로브는 main만으로는 다시 실행할 수 없어 감사 이후 기록으로만 쓴다 [C-RUST].

테스트와 프로브 기록은 2026-10-27~30에 만들어졌고 다시 실행할 수 있으며, CI 실행 43565082671(main `d954387`)의 check 작업이
세 일반성 테스트를 통과했다 [C-M4a].

이는 오라클·어댑터 수준의 주장이며 **퍼저 탐색의 일반성이나 효과에 대한 주장이 아니다** [C-M4a].

## 5.6 등록 실행 EXP-0 (인프라 측정)

EXP-0은 사전등록 v2.1로 등록한 인프라 측정 실행이다. node-tar 7.5.2, R·D·S-u × seed 9001–9005, 캠페인당 실행 200의
15셀이 모두 유효했고 abort 0, 경계위반 사건 0이었다. 가설을 판정하지 않는다 [C-EXP0]. 사건 0은 위반이 없다는 뜻이 아니라
그 예산에서 관찰되지 않았다는 뜻이며, arm 비교의 근거가 아니다 [C-EXP0]. 값의 기준은 공식 리포트
[exp0-20261105-report](../../experiments/summaries/exp0-20261105-report.md)와 [표 EXP-0](../tables/exp0-summary.md)이다.

- **처리 시간.** step p95는 기록값 1.549 s, 실시간 환산 1.419 s이고, 호스트 집계 처리량은 약 4760 exec/h(jobs 2)다 [C-EXP0].[^exp0-clock]
- **그림.** arm별 결합 T_first Kaplan–Meier 곡선([`exp0-survival.png`](../figures/exp0-survival.png))은 전 arm 사건 0이라
  세 곡선이 겹친다. arm 비교가 아니다 [C-EXP0].

[^exp0-clock]: evidence: `experiments/summaries/exp0-20261105-report.md` 편차 1. 기록값은 monotonic clock 기준이고, EXP-0 당시 이 호스트의 monotonic clock은 실시간보다 1.091배 빠르게 갔다(EXP-0 전용 배율). 호스트 집계 처리량은 배율 환산이 아니라 실제 경과에서 직접 계산했다. T_first는 실행 수로 세므로 시계와 무관하다.

## 5.7 비등록 위험도 파일럿

비등록 위험도 파일럿(node-tar 7.5.2, 40 캠페인, 캠페인당 실행 2000)에서 네 arm 모두 첫 C1∨C2 사건이 있었고, 신뢰구간이 크게 겹쳐
arm의 순서를 말할 수 없다(R-walk 1/10, R-restart 4/10, D 4/10, S-u 6/10). abort는 11/40이다. 이 값은 표본 수 산정, R 변형 선택(D6), 사전등록 예측의 개정에 썼다 [C-PILOT]. 근거는
[파일럿 결과 메모](../../experiments/summaries/exp3-hazard-pilot-v1-result.md) §1–§2이며, arm의 우열이나 효과의 근거로
쓰지 않는다 [C-PILOT].

## 5.8 EXP-3 GO 판정

EXP-3 train이 끝난 뒤 등록 규칙(§4.6.3)을 기계적으로 적용해 GO를 냈다(2026-11-13 23:37:16 KST). 세 arm을 합친 첫 C1∨C2
캠페인 수 31(기준 1 이상), 처리 용량 554(기준 76 이상), 인프라 실패 비율 .033(기준 .45 이하)이다 [C-GO]. 입력 전체는
[표 GO 입력](../tables/exp3-go-inputs.md)에 있다. 합산값만 쓰며 arm별 값은 봉인이고, 이 값은 효과의 근거가 아니다. 독립
확인은 판정 순서·용량·할당 재생성까지이고, 31은 봉인 자료가 필요해 다시 계산하지 않았다 [C-GO].

**운영 사실 공개.** EXP-3 train 중 HOST2 인프라 정지가 1회 있었고(2026-11-13, 원인 기록 #366 뒤 재개, 정지에 걸린 2셀은
재실행하지 않음), EXP-2 holdout 중에도 HOST2 인프라 정지가 1회 있었다(2026-11-14, 원인 기록 #370 머지로 재개 승인; 재개 사실은 holdout 종료 기록에 적는다). 확인된 직접
원인은 Docker Desktop API 무응답이고 근본 원인은 확인하지 못했다 [C-OPS].

## 5.9 본실험 결과

- **EXP-3 train(7.5.2)의 arm별 결과(탐색).** 본실험 결과 자리(봉인 해제 뒤 기입) [S-TRAIN]
- **EXP-2 holdout(7.4.4)의 확증 판정(H-A).** 본실험 결과 자리(봉인 해제 뒤 기입) [S-HOLDOUT]

결과 문장은 사전등록 판정표(§4.6.4, §7.2)의 문장만 쓴다 [C-HA].

## 5.10 Capability Ledger 요약

M1·M2·M4의 능력과 증거 수준 요약은 [Capability Ledger 요약표](../tables/capability-ledger-summary.md)에 두며, 단일 기준은
[`../../docs/STATUS.md`](../../docs/STATUS.md)다.
