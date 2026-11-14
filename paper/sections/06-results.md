# 5. Results (드래프트 v1)

이 절의 모든 수치는 증거 사슬(raw → validated summary → finding)로 추적 가능하며, 능력 판정의
단일 기준은 Capability Ledger([`../../docs/STATUS.md`](../../docs/STATUS.md))다. 주장↔증거 매핑은
[`claims-evidence-status-v1.md`](claims-evidence-status-v1.md)를 본다. observed(실행 출력으로 확인)와
inferred(추론)를 소절마다 구분한다.

## 5.1 M1 — 루프가 실제 node-tar에서 돈다 (TESTED)

`make demo`(호스트, 실제 node-tar 7.5.22)는 입력 생성 → 실행 → entry별 중간 상태 관찰 →
C0/C1/C2 oracle → feedback → 다음 mutation 루프를 한 바퀴 20 step 돌린다. 반복 실행해도 같은
루프이고(SAME_LOOP), macOS/OrbStack과 WSL2 x86_64 두 플랫폼에서 동일 루프가 재현됐다(observed).

- 결과 JSON의 step마다 `trace`(entry별 중간 상태, observed/derived 구분), `oracle`(C0/C1/C2),
  `selection`(corpus 편입 여부 · operator 가중치 변화)이 남는다(observed).
- 정상 입력 20개에서 **위반 0건**이며, 이 소절은 취약점 발견·재발견을 주장하지 않는다.
- 중단 내성(끝난 step이 보존됨)과 producer 견고성(조용한 exit 0 → failed 프레임/lifecycle 기록)은
  별도로 TESTED다(Ledger 1–6행).

증거 수준은 **TESTED**(지정된 한계 안의 engineering 증거)이며 research effectiveness를 뜻하지 않는다.

## 5.2 M2 — 실제 경계위반 통제 재현 + 2-CVE 차분 (observed)

손으로 만든 결정론적 하드링크 fixture(외부 참조파일 대상, 추출 디렉터리를 벗어나는 동일 상대
경로)를 **5개 고정 node-tar 릴리스**(7.5.2 / 7.5.3 / 7.5.6 / 7.5.7 / 7.5.8)에 돌려, "추출된 객체가
외부 참조파일의 `(st_dev, st_ino)`를 공유하는가"라는 **generic C1 관찰**로 판정했다. 릴리스 id나
정답 경로를 판정 조건에 넣지 않았다. 전체 표는 [M2 cross-release 증거표](../tables/m2-cross-release-evidence.md),
raw는 [`../../experiments/repro/evidence/summary.json`](../../experiments/repro/evidence/summary.json),
검증 요약은 [cross-release-identity-repro-v1](../../experiments/summaries/cross-release-identity-repro-v1.md)다.

![node-tar 릴리스별 하드링크 identity verdict 그리드: top-level와 nested fixture × 7.5.2–7.5.8, 비단조 분포와 R1·R2 고정 쌍](../figures/m2-cross-release-evidence.png)

*그림 1 — 릴리스별 verdict(observed). 데이터 [표 M2](../tables/m2-cross-release-evidence.md),
생성 소스 [`../figures/render_m2_cross_release.py`](../figures/render_m2_cross_release.py).*

**Finding (observed).** 하나의 generic identity oracle(추출 객체↔외부 참조파일 inode 공유 = C1,
참조파일 전후 metadata 변화 = C2)이 서로 다른 **두 root-cause**를 포착한다.

- **R1 = CVE-2026-23745** (catalog N01): linkpath sanitation 누락. 최상위 하드링크가 7.5.2에서
  공유(nlink 1→2)되고 7.5.3에서 거부되는 전환으로 재현.
- **R2 = CVE-2026-24842** (catalog N02, GHSA-34x7-hfp2-rc4v): 검증 base ≠ 생성 base의 check/use
  mismatch 회귀이며, R1 수정이 도입한 것으로 **추론**한다(아래 inferred). 중첩 하드링크가 7.5.6에서 공유되고 7.5.7에서 거부되는
  전환으로 재현.

관찰된 공유 분포는 **비단조**(중첩: 7.5.2 공유 · 7.5.3 거부 · 7.5.6 공유 · 7.5.7/7.5.8 거부)로,
7.5.3에서 거부된 입력이 7.5.6에서 다시 공유되고 7.5.7에서 다시 거부됨을 보인다.

- **observed:** 5×2 verdict 표, nlink 전이, 거부 메시지, 비단조 분포.
- **inferred:** 특정 CVE↔fixture 대응과 "7.5.6 회귀가 R1 수정이 도입한 것"이라는 인과 서술.
  advisory 범위(24842 `<7.5.7`)와 이 **특정** fixture의 observed 거동은 다를 수 있어 **exact 하한은
  미검증**이다.
- **production-path 일치(M2.2):** 손 probe 판정 == production Observer+Oracle 판정 일치를 additive
  테스트로 고정했다([`../../tests/test_cross_release_oracle_agreement.py`](../../tests/test_cross_release_oracle_agreement.py),
  native closure는 [`../../tests/container_integration/check_cross_release_oracle_agreement.py`](../../tests/container_integration/check_cross_release_oracle_agreement.py)).

**정직 경계:** 이것은 **통제 재현이며 퍼저의 탐색 결과가 아니다**. fixture는
손으로 만든 generic 하드링크 엔트리이고, 하드링크·링크 상태 관찰·버전 차분 자체는 선행연구
(§3)가 다루므로 신규 기여로 표현하지 않는다.

## 5.4 M4 — 일반성 (oracle/adapter 수준)

### 5.4.1 동일 generic oracle의 3-extractor 적용 (일부 TESTED)

**동일 generic C0/C1/C2 oracle(코드 불변)**이 adapter 수준에서 3개 독립 extractor에 target-agnostic
하게 적용됨을 통제 reference 차분(affected/fixed digest-pinned)과 container-integration 체크로 보였다.
target 로직은 adapter/worker/recipe에 격리되고 generic 모듈은 불변이다.

- **python-tarfile (JS 아님, stdlib):** C1 하드링크 fixture를 Python tarfile로 돌려 `fully_trusted`
  (영향) = 외부 sentinel inode 공유로 production oracle이 C1+C2 발화, `data`(PEP 706 완화) = 거부·
  위반 0([`../../tests/test_python_tarfile_generality.py`](../../tests/test_python_tarfile_generality.py) 4 passed).
- **oras-go (Go) · decompress (JS):** 동일 generic oracle로 affected/fixed 통제 reference 차분 +
  container-integration generality 체크 통과(#176 · #177).

이는 oracle의 **target-agnostic성 증거**이며 **퍼저 탐색의 일반성이나 효과에 대한 주장이 아니다.**

## 5.5 Capability Ledger 요약

M1–M4의 능력과 증거 수준을 한눈에 보는 요약은 [Capability Ledger 요약표](../tables/capability-ledger-summary.md)에
두며, 단일 기준은 [`../../docs/STATUS.md`](../../docs/STATUS.md)다.


## 5.6 EXP-0 결과와 EXP-3·EXP-2 결과 자리

이 소절은 §4.6 실험 설계의 실행 결과 자리다. EXP-0 등록 실행은 완료됐고 핵심 수치를 아래에 적는다. EXP-3·EXP-2 표·그림은
**본실험 결과 자리(봉인 해제 뒤 기입)**다.

**EXP-0 등록 실행 (registered run · 인프라 측정 · 가설 검정 아님).** 2026-11-05에 사전등록 v2.1로 등록한 실행이다. 대상은
node-tar 7.5.2, 설계는 seed 9001–9005 × {R, D, S-u}, budget 200, sentinel k=3(생성기 seed 고정 무작위 이름, 전 arm·seed 공통)이다(15셀,
3000 실행). H-A 검정도 효과 주장도 아니며, 이 숫자로 arm을 비교하지 않는다. 값의 기준과 재현 명령은 공식 리포트 [exp0-20261105-report](../../experiments/summaries/exp0-20261105-report.md)(#268)다.

- **완주.** 15/15, abort 0, invalid 셀 0. 셀 판정과 별개로 trace가 invalid인 step 11개와 failed step 10개가 있다(리포트 편차 2).
- **위반 hit.** C1/C2 전 arm 0(C0 관측도 0, arm마다 5/5 우측중도절단 @200). hit 0은 hazard 0이 아니다. 캠페인 단위 rule-of-three 참고 상한은 .6(n=5)이고 판정 입력이 아니다.
- **p95 full-step.** 기록값 1.549 s, 실시간 환산 1.419 s.[^exp0-clock]
- **처리량.** 호스트 집계 약 4760 exec/h(jobs 2, 실제 경과에서 직접 계산).[^exp0-clock]
- **편차.** 사전등록 대비 편차 11건은 리포트 §3에 공개했다. 측정 4(per-case 대 워커 풀 처리량 비교)는 미충족이다(편차 3).

- **표.** EXP-0 인프라·dense 신호 요약 — `analyze_exp0` report.json **item1~7 전부**(전부 분모 병기):
  item1 abort(사유 × arm) · item2 p95 full-step · item3 처리량(exec/h) · item4 per-case vs 워커풀 parity ·
  item5 첫 C0/C1/C2 · T_first(우측중도절단; abort 민감도 **3정책** `item5.sensitivity` — exclude · censor-at-budget, #243) ·
  item6 dense 신호 · item7 hazard proxy. **item2·item3·item4·item7은 '참고값' 라벨**(effectiveness·판정 입력 아님).
  arm×abort 독립성(꼭지 13 validity, 레인 3 optional)은 번호 없는 `arm_abort_independence` 키(#242)로 보고 —
  사전등록 **측정 item8 = raw SHA-256 체크섬 목록**과 번호 충돌을 피한다(체크섬은 report.json 밖 manifest).
  생성 경로: `scripts/analyze_exp0.py` → `report.json` →
  `paper/figures/render_exp0_survival.py` → `paper/tables/exp0-summary.md`. — **EXP-0 값의 기준은 위 공식 리포트다.**
- **그림.** arm별 결합 T_first(C1 ∨ C2) Kaplan–Meier 생존곡선(중도절단 tick). 생성 경로:
  `scripts/analyze_exp0.py` → `report.json` → `paper/figures/render_exp0_survival.py` → `exp0-survival.png`.
  — **EXP-0은 전 arm 사건 0(공식 리포트 측정 5)이다.**

**EXP-0 seed 사전 노출 공개 (결과 아님 — 도구 검증).** EXP-0 사전등록 seed 중 9001–9004는 동결 전 비등록 실행에 이미
노출됐다. 이 호스트 raw 기준으로 seed 9001은 10런(G1 smoke 3, G1 completion 3, parity 확인 `s3wp` 3, 타이밍 대조 1)이고
9002–9004는 G1 smoke 각 3런이다. v2.1 사전 노출 절은 seed 9001의 4런만 공개해 6런이 빠졌고, 노출 원장은 7런을 기록해
`s3wp` 3런이 빠졌다(공식 리포트 편차 9). 이 실행들의 출력은 **결과가 아니며 논문 표·결론에 쓰지 않는다**.
이 중 G1 smoke는 통합 브랜치 `4b072a5`(image `sha256:22c8734f…`, node-tar 7.5.2), seed 9001–9004 × budget 50에서
**12/12 완주(abort 0, arm 간 어휘 동등 true)**했고, 그중 **D arm s9002의 exec 42에서 generic oracle C2 이벤트
1건**(u_viol 1; hardlink `a.txt` → `../outside/sentinel.txt` 뒤 regular `a.txt`)이 관찰됐다 — 출처 PR #223
(`claude/s3-exp0-launcher`) LOG + 호스트 `~/inodefence-evidence/g1-20261104/smoke/summaries/index.json`
(sha256 `26235b44…`, [raw-manifest-win-20261104-1421](../../experiments/summaries/raw-manifest-win-20261104-1421.sha256) 71행). 이는 사전등록 판정이 아니라 도구 검증 관측이므로
**해석하지 않는다**. smoke는 sentinel 설정과 budget이 등록 실행과 달라 등록 결과와 비교하지 않는다. 사전 노출된 seed로 얻은 EXP-0/EXP-3 결과의 독립성 해석상 한계는 §6.7에 둔다.

[^exp0-clock]: evidence: `experiments/summaries/exp0-20261105-report.md` 편차 1. 기록값은 monotonic clock 기준이고, EXP-0 당시 이 호스트의 monotonic clock은 실시간보다 1.091배 빠르게 갔다(합산 1.0914, 셀별 1.0855~1.0964; EXP-0 전용 배율). 다른 실행에서는 이 배율이 1.00~1.10으로 변했다([파일럿 결과 메모](../../experiments/summaries/exp3-hazard-pilot-v1-result.md) §5). p95 환산값 1.419 s는 셀 안에서 배율이 일정하다고 가정한다. 셀 안 변동은 측정하지 않았고, EXP-0 셀은 짧고 셀별 범위가 좁아 영향은 작을 것으로 본다(추론). 환산값은 실시간 기준이며 실시간 시계의 장기 편차는 검증 중이다. 호스트 집계 처리량은 배율 환산이 아니라 실제 경과에서 직접 계산했다(셀 구간 4763, 해시 고정 타임스탬프 4758 exec/h). T_first와 hazard proxy는 실행 수로 세므로 시계와 무관하다.
