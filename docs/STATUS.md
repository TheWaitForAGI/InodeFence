# 현재 프로젝트 상태

## 중간발표 P0 현황 (M1 세부 이력 — 현재 단일 기준은 아래 Capability Ledger)

기준: 현재 능력은 아래 **Capability Ledger**가 단일 기준이다. 이 P0 표는 M1(루프 동작)의 세부
이력이며 날짜·게이트를 현재 제약으로 읽지 않는다. 배경 [MIDTERM_GOALS](MIDTERM_GOALS.md) · 실행 기록: [LOG](LOG.md)

| P0 | 담당 | 상태 (10/23) | 다음 할 일 |
| --- | --- | --- | --- |
| P0-1 실제 node-tar 실행 | 규민 | 통과: make node-tar-smoke (macOS/OrbStack, 10/23). 10/24: budget 100에서 producer가 '조용한 exit 0'(tar.x 미settle, checkPath 드롭)을 내 demo가 중단되던 결함 원인 확인(LOG 18:00) → `jiwoong/p0-1-producer-settle-skip`에서 failed 프레임/lifecycle 기록으로 수정, 호스트 budget 100 100/100 확인(LOG 18:21), 수정 PR #144 머지됨. 10/27: WSL2 x86_64 host(Docker Desktop 29.7.2)에서 make node-tar-smoke 1회 + make demo 3회 통과, SAME_LOOP_x3·macOS 기록과 동일 = 두 플랫폼 재현(LOG 10/27 18:35) | 이미지 ID 재현성(BuildKit attestation, macOS·WSL 공통) 처리 |
| P0-2 중간 상태 관찰 | 민찬 | 동작: v2 producer 필수 기준 14개 중 13개 통과, replacement coverage 1개 미달. `effect_demo.render_effect_trace`로 entry별 trace 출력(archive/observed/not_observed/derived 라벨, synthetic이면 라벨에 ·SYNTHETIC; synthetic으로만 확인). demo report(schema 2) step마다 같은 정보를 `trace`로 출력(entry·operation·association, 작업 전후 status와 present일 때 dev:ino·nlink·size, observation_failures, step당 event 64개 상한). native 확인: `make demo-native` 2회(10/24, demo run) 20/20 step trace 출력, link 작업에서 extract/a.txt·b.txt st_nlink 2 관찰, step 8·18은 event 0 + operation_correlation_conflict | 한계 표현 결정(거부 입력의 operation_correlation_conflict 포함) |
| P0-3 Oracle 검증 | 민찬 | C0/C1/C2 fixture TESTED. 데모 fixture 4종(정상·C0·C1+C2·C2) 판정 일치: `python -m scripts.oracle_fixture_check` (controlled oracle check, node-tar 아님) | — |
| P0-4 Feedback 기반 Mutation | 주언 | `run_effect_campaign` 구현, `make demo`(별칭 `make demo-native`)로 실제 node-tar 루프 실행. demo report step마다 선택 근거 `selection` 출력(채널 ① corpus_admission: 선택 전 corpus 크기·편입 여부, ② operator_weights: weights_before·reward·weights_after). native 확인: `make demo-native` 2회(10/24, demo run) 같은 선택, reward 1·편입 step 5·12·19(새 key 각 2개, 선택 전 corpus 4·5·6), step 5 add_entry 가중치 1→2 | — |
| P0-5 End-to-end 데모 | 지웅 | `make demo` = 실제 node-tar 루프(호스트, 별칭 `make demo-native`), synthetic은 `make demo-synthetic`(JSON `label`: `SYNTHETIC (not node-tar)`). 동작: `make demo-native` (실제 node-tar 7.5.22, FULL profile, P2·M1·seed 123·budget 20) 2회 동일 루프, demo run(10/24). `make demo` 1회 (호스트, 10/24 14:42, demo run): label `demo run`, producer native, node-tar 7.5.22, 20 steps, SYNTHETIC 0건 | 거부 중 미완료 operation trace 한계 표현, 이미지 ID 재현성(provenance attestation) |

### 한눈에 보기 (2026-10-24)

- `make demo`(호스트) = 실제 node-tar 7.5.22 루프, 20 step, 반복 실행해도 같은 루프(SAME_LOOP_x4). 결과 JSON은 `~/inodefence-evidence/`.
- 결과 JSON의 step마다 `trace`(entry별 중간 상태, observed/derived 구분), `oracle`(C0/C1/C2), `selection`(corpus 편입 여부·operator 가중치 변화)이 있다.
- 정상 입력 20개에서 위반 0건. 취약점 발견·재발견 주장 없음.
- 남은 P0 과제: 거부 입력에서 중간 상태 event가 0개인 한계의 표현 방식. 이미지 ID 재현성은 처리됨(10/27):
  원인은 BuildKit 기본 provenance/SBOM attestation(빌드 시각 포함)이라 캐시된 재빌드도 매번 새 image ID가 됐고,
  `local_node_tar_smoke.sh`가 `BUILDX_NO_DEFAULT_ATTESTATIONS=1`로 빌드해 같은 체크아웃·같은 호스트에서는 같은 ID가 나온다
  (same-host 결정론, 플랫폼 간 bit-for-bit 주장 아님; LOG 10/27).
- 주의(10/24): budget 20은 반복 성공했지만 budget 100에서는 9회 중 5회가 producer 결함으로 중단됐다(LOG 18:16).
  수정 브랜치(`jiwoong/p0-1-producer-settle-skip`)가 머지되기 전까지 큰 budget 데모는 중단될 수 있다.
- A/B/C(정책 간) rate 비교 결론은 없다(LOG 18:44). 단 자율 경계위반은 **state-identity 관찰이 인과적으로 가능케 함**이 blind 대조로 입증됐다(A3 21건 vs A1·blind 0, 아래 Ledger M3).

## Capability Ledger (살아있는 증거 원장)

이 표가 **현재 능력의 단일 기준**이다. 각 줄은 "능력 → 증거 수준 → 증거 포인터"이고,
현실이 바뀌면 바로 갱신한다(죽은 커밋에 고정하지 않는다). 증거 수준은
[Research Contract](research/design/research-contract-v1.md)의 어휘를 그대로 쓴다:
**DESIGNED**(정의/가설만) · **IMPLEMENTED**(실행 경로 존재) · **TESTED**(명시된 한계 안에서 테스트/검증) ·
**VALIDATED**(고정 조건·반복·raw 증거로 연구 주장 뒷받침). observed(실행 출력로 확인)와
inferred(추론)를 구분하고, synthetic은 native 증거로 승격하지 않는다.

| 능력 | 수준 | 증거 포인터 |
| --- | --- | --- |
| 실제 node-tar 루프(입력→실행→entry별 관찰→C0/C1/C2→feedback→다음 mutation) | TESTED | `make demo` 호스트, LOG 2026-10-24; budget 20/100 완주 |
| entry별 중간 FS 상태 관찰(trace, observed/derived 구분) | TESTED | demo report schema 2 `trace`; native 20/20 step |
| C0/C1/C2 oracle 판정이 fixture와 일치 | TESTED | `scripts.oracle_fixture_check` 4/4 |
| feedback→mutation 연결(corpus admission + operator 가중치) | TESTED | demo `selection`; `test_effect_feedback_sensitivity` |
| 중단 내성(끝난 step이 `.steps.jsonl`에 보존) | TESTED | PR #143; 강제 중단 테스트 |
| producer 견고성(조용한 exit 0 → failed 프레임/lifecycle 기록) | TESTED | PR #144; 호스트 budget 100 100/100 |
| **실제 경계위반을 통제 재현 + affected/fixed 구분**(node-tar 하드링크→외부 참조파일 = C1 identity 공유 + nlink 증가, 이후 릴리스 거부) | TESTED | 재현 스크립트+raw 증거 `experiments/repro/`(5 릴리스 sweep): 최상위 하드링크 7.5.2 공유(nlink 1→2)·7.5.3 거부 = CVE-2026-23745(catalog N01·R1), 중첩 하드링크 7.5.6 공유·7.5.7 거부(7.5.8도 거부) = CVE-2026-24842(CVE-2026-23745 수정이 도입한 check/use 회귀; catalog N02·R2). 동일 outcome oracle이 두 root-cause(R1·R2)를 포착, 릴리스 id/정답경로 하드코딩 없음. **퍼징 자력 발견은 아님**. **M2.2 박제**: 같은 외부-sentinel 하드링크를 production Observer+Oracle로 판정해 손 probe 판정과 일치함을 additive 테스트로 고정 — CI는 7.5.2 공유 post-state를 재현해 generic C1+C2 일치 검증(`tests/test_cross_release_oracle_agreement.py`, run_case 경로 + M2.1 증거 바인딩), native effect-pipeline(`run_node_tar_effect_case`) closure는 container_integration 체크(`tests/container_integration/check_cross_release_oracle_agreement.py`, 호스트 docker+이미지). oracle/fixture/N01 불변, 릴리스 문자열은 증거 키일 뿐 판정 조건 아님 |
| 퍼저가 **자력으로** 경계위반을 발견 | 입증(인과): state-identity 관찰 구동 자율 C1 (A3 21 vs A1 0 vs identity-blind 0) | ① **어휘판 자율 C1 관찰**: native 7.5.2 budget 100에서 퍼저 생성 `../outside/sentinel.txt` 하드링크가 extract 객체↔외부 sentinel 동일 inode(C1+C2; P1 s789 2케이스, LOG 01:40). **단 변이 어휘에 대상 토큰(outside/sentinel.txt)이 들어 있어 blind 아님.** ② **de-contaminated(토큰 제거 + 관찰-이름 조합, LOG 11:00)**: A1(토큰 없음) 대상 segment 조합 0/6=도달 바닥, A2/A3는 관찰 이름으로 대상 segment 도달(5/6·6/6, target-agnostic·이름-독립성 단위테스트 증명), 그러나 **정확 대상=exact C1은 전 arm 0/6**(budget 100 우측센서). ③ **gradient 기작 측정됨**: 외부 접근 시도 A3 3.83 vs A2 1.67, escape operator 가중·거부-trace 키 편입↑. ④ **큰 seed study(결판, LOG 15:02)**: A1/A3 × seed 1~60 × budget 100(7.5.2, +7.5.3 대조)에서 clean exact C1 **A1 0/57·A3 0/59·대조 0/3**(C0/C2도 0; A3 접근시도 3.27>A1 2.30이나 exact 미전환; 4건 native abort). → budget 100·~60 seed에서 **H1(상태-인지 피드백 > 무작위) C1-rate 우위 미입증(정직한 negative)**. 도달은 target-agnostic 입증, gradient는 접근 시도 증가 측정됨. ⑤ **실제 규모 + blind 대조(결판, LOG 10-26)**: budget 1500에서 A3(identity 관찰 O) seed 11이 `../outside/sentinel.txt` 하드링크로 C1+C2 **21건 자율 트리거**, random floor A1=0(33k 실행), **identity-blind 대조 A3blind=0**(관찰 이름에서 EXTERNAL region 제외; blind-s11은 1475 실행에도 0). → 발견의 **인과적 원인 = filesystem-state의 object-identity 관찰**(가설이 명시한 feedback)임을 blind 대조로 확정. 단 **blind 발견은 아님**(기존 외부 객체 하드링크엔 그 이름이 필요, 퍼저는 관찰로 얻음; 어휘·oracle에 대상 경로/식별자/정답 seed/근접 보상 하드코딩 없음, EXTERNAL 필터는 region 기준 target-agnostic). 의미: **'피드백(identity 관찰)이 발견을 가능케 함 — 없으면 도달 불가'**(rate 우위 주장 아님). ⑥ **재현성(LOG 10-26)**: A3full을 새 seed 36~65(30개)에 budget 1500로 재실행 → **0/30 hit**. 기존 1~35과 합쳐 **65 seed 중 자율 C1은 s11 1개뿐**. s11은 동일 seed에서 결정론적으로 재현(21건)되고 관찰-이름 경유이나, **교차-seed로는 seed-rare**(이 예산에서 다른 seed로 일반화 안 됨). Ledger M3 |
| feedback effectiveness(B0/B1/B3, A1/A2/A3) | IMPLEMENTED, 미VALIDATED | 정책 매트릭스 9/9 완주하나 비교 결론 없음(LOG 18:44). 다음(BACKLOG): M3.4 pilot로 검정력 확보·budget right-size, M3.5 coverage baseline D로 '피드백 일반'과 'identity 특정'을 분리. **단일경로 A/B/C/D 비교 하너스+공통지표 readout** IMPLEMENTED/synthetic-TESTED(claude/m3-2-eval-d81a84 `evaluation/arm_comparison.py`): A=B0/legacy·B=B0/M1·C=B3/M1·D=D/M1을 한 `run_search_campaign` 경로로 돌리고 "Exact metrics"(executions-to-first-violation right-censored·유효입력비·unique states 등)를 evaluation.summary 산술 재사용으로 읽음. 안전 reference extractor(python-tarfile-data, PEP 706) 단일경로 실행 완료(seed×3·budget 50): 전 arm first-violation **right-censored >N**(data 필터가 escape 차단 = 구조적, 안전/effectiveness 주장 아님), retention arm(C/D) valid-input↑·corpus 성장 — 기작 차이이지 효과 아님, **effectiveness 랭킹 없음**(~/inodefence-evidence/abcd-reference-20261030-005915). **node-tar affected-mode terminal-C1 통합 native run은 NOT_RUN**(설계결정 C+ 2026-10-30: host-broker 미구축 — feasible budget에선 right-censored null이고 node-tar H1 인과 증거는 이미 effect-path에 있음). **중간상태 gradient 차분 지표 소비경로 준비**(additive, `evaluation/intermediate_metrics.py`): arm별 dense 중간상태 key-set 시퀀스를 non-right-censored 차분(unique keys·novelty rate·cumulative trajectory·directed boundary-attempt milestone)으로 측정하고 main의 effect/transition 신호 adapter로 소비(core는 추상 key-set+milestone 술어 → #174 미머지·2nd extractor 비의존). 민찬 monotone proximity-rank(trace_proximity의 none<external_namespace<cross_boundary_identity rungs) 소비 형태도 제공(executions-to-rung·running-max 궤적, non-right-censored; 추상 int rank 입력이라 미머지 모듈 비의존). **M3.3 right-censored roll-up 도구**(evaluation/right_censored.py: Wilson 95% CI+censoring+complete/incomplete 분리+단일arm 정직 프레이밍) IMPLEMENTED/TESTED — **M3.3 A1 random control 배치 1+2 통합 소비(observed, budget 2000, seeds 11/66/67/68/69/70 + 71~76, 규민 commit 103e245·6417b75 #178)**: clean exact C1 **0/7 complete**(완주 s67/69/70/71/72/73/76, Wilson 95% CI [0, 0.354] — 배치1 [0,0.561]보다 좁아짐) + 5 fail-closed abort(s11/66/68/74/75, infra-incomplete=denominator 제외, 각 abort 전 0 observed), 전체 **0 clean C1 / 12 seed / ~20,163 exec**. **인과 대조(rate 아님, CI 아직 넓어 underpowered)**: random floor=**0/12**(s11 포함) vs identity-feedback effect-path s11=21@budget1500 → '피드백이 발견을 가능케 함, random은 더 큰 예산(2000)에도 clean C1 미도달'. 프로토콜대로 abort≠no-hit censoring(규민 'right_censored_abort' 라벨과 구분). roll-up evidence ~/inodefence-evidence/m3-3-control-budget-b2-20261030/m3-3-rollup-combined.json. **정직 프레이밍**: 단일경로 A/B/C/D 하너스 demonstrated; node-tar H1 인과=effect-path(s11+blind); terminal-C1 rate 차분은 gradient 지표 또는 사람-게이트 대예산 필요; effectiveness 랭킹 주장 없음(EN-008: 중간상태 탐색은 search behavior). B0/B1/B3 의미 불변 |
| entry-transition native 관찰 | DESIGNED / SYNTHETIC TESTED | native completion boundary 미확보 → NOT_IMPLEMENTED |
| cross-implementation(2번째 extractor에 generic oracle 적용) | 일부 TESTED(oracle 수준) | **Python stdlib tarfile 통제 차분**: C1 하드링크 fixture를 Python tarfile로 돌려 fully_trusted(영향)=외부 sentinel inode 공유로 production oracle이 C1+C2 발화, data(PEP 706 완화)=거부·위반 0. oracle 코드 불변, target-agnostic 확인. `tests/test_python_tarfile_generality.py` 4 passed. **단 node-tar 결과·fuzzer 발견 아님**; oras-go adapter·2번째 extractor 자력 발견은 미구현. Ledger M4 |

### 마일스톤 (날짜 아님 — 증거가 모이면 찍는다)

- **M1 — 루프가 실제 node-tar에서 돈다.** 상태: **완료**(위 Ledger 1~6행).
- **M2 — 실제 경계위반 통제 재현 + 버전 구분 (2-CVE 차분).** 상태: **실증됨 + 박제 완료**. 재현 스크립트+raw 증거 2쌍(`experiments/repro/`)이 **동일한 generic identity oracle**(추출객체가 외부 참조파일 inode 공유)로 서로 다른 root-cause 2개를 관통한다: ① 최상위 하드링크 7.5.2 공유→7.5.3 거부 = **CVE-2026-23745**(linkpath sanitation 누락; catalog N01·R1), ② 중첩 하드링크 7.5.6 공유→7.5.7 거부 = **CVE-2026-24842**(검증 base ≠ 생성 base의 check/use mismatch, CVE-2026-23745 수정이 **도입한** 회귀; catalog N02·R2, GHSA-34x7-hfp2-rc4v). 관찰된 공유 분포는 **비단조**(중첩: 7.5.2 O·7.5.3 X·7.5.6 O·7.5.7/7.5.8 X)로 7.5.3이 고친 것을 7.5.6이 되돌렸음을 보인다. advisory 범위(24842 `<7.5.7`)와 이 특정 fixture의 observed 거동은 다를 수 있어 exact 하한은 미검증(observed/inferred 구분). 핵심: **outcome 기반 oracle 하나가 R1·R2 두 root-cause를 릴리스 id/정답경로 하드코딩 없이 모두 포착.** 재발견(자력 발견, M3)과는 구분. **M2.2(박제 완료, claude/m2-2-oracle-path-7d09f3)**: 손 probe 판정 == production Observer+Oracle 판정 일치를 additive 테스트로 고정 — CI는 run_case로 7.5.2 공유 post-state를 재현해 generic C1+C2 일치 + M2.1 증거 바인딩, native closure는 container_integration의 `run_node_tar_effect_case` 체크(호스트 docker+이미지, make check 미수집). observed(실제 node-tar=M2.1 증거) vs reproduced(통제 extractor post-state) 구분, oracle/fixture/N01 불변.
- **M3 — 퍼저가 자력으로 그 위반을 찾는다.** 상태: **입증(인과적) — 메커니즘·실제규모·blind 대조 완료(PR #151)**. **state-aware 퍼징(filesystem-state의 object-identity를 feedback으로 사용)이 영향 릴리스 7.5.2에서 경계위반을 자율 트리거**: A3(identity 관찰 O) seed 11이 budget 1500에서 `../outside/sentinel.txt` 하드링크로 C1+C2 21건. random floor **A1=0**(33k 실행), **identity-blind 대조 A3blind=0**(관찰에서 EXTERNAL region 이름 제외; blind-s11은 1475 실행에도 0) → **관찰이 인과적 원인**임을 blind 대조로 확정. 메커니즘: 거부된 외부-하드링크 시도를 valid trace로 관찰(producer abort-drain) + boundary-attempt gradient + 어휘 대상 토큰 제거·state-aware 관찰이름 조합 + external-resolve rung + 재현 study 하너스. **정직 경계(필수 명시)**: 이는 blind 발견이 아니다 — 기존 외부 객체에 하드링크하려면 그 이름이 필요하고 퍼저는 그것을 **관찰**로 얻는다(가설이 명시한 object-identity feedback). 어휘·oracle에 대상 경로/식별자/정답 seed/근접 보상 하드코딩 없음(EXTERNAL-이름 필터는 region 기준 target-agnostic). 가설 입증 형태는 '상태-인지 피드백이 무작위보다 빠르다(rate)'가 아니라 **'피드백(identity 관찰)이 발견을 가능케 한다 — 없으면 도달 불가'**. (이전 budget 100·~60 seed study는 clean exact 0였고, 실제 규모 budget 1500에서 자율 트리거가 관찰됨 — s11.) **재현성 주석(정직)**: 새 seed 36~65(30개) 재실행 = 0/30 → budget 1500·65 seed 중 자율 트리거는 **s11 1개(seed-rare)**. s11은 동일 seed에서 결정론적으로 재현되고 관찰-이름 경유임이 확실하나(인과·메커니즘 입증), 이 예산에서 교차-seed 일반화는 미입증. 상태: **입증(인과·메커니즘; 자율 트리거는 seed-rare), PR 사람 머지 대기**.
- **M4 — 일반성.** 태스크: 2번째 extractor 동일 모델 적용. 상태: **1차 증거(oracle 수준) 확보**. 동일 generic C0/C1/C2 oracle(코드 불변)이 **Python stdlib tarfile**에서도 경계위반을 포착함을 통제 reference 차분으로 보임(fully_trusted=영향 → C1+C2, data=PEP 706 완화 → 거부; `tests/test_python_tarfile_generality.py` 4 passed). 이는 oracle의 target-agnostic성 증거이며 **fuzzer 자력 발견·effectiveness 주장 아님**. oras-go adapter와 2번째 extractor에서의 자력 발견은 미구현(설계).

중간발표는 이 척추에서 **지금 와 있는 지점을 증거 수준과 함께 정직하게** 보여주는 것이다.
특정 날짜를 문서에 박제하지 않는다. 기한은 팀 일정으로 관리하고 이 문서는 능력만 추적한다.

---

### 역사적 기록 (현재 제약 아님 — provenance용)

아래부터는 **과거 특정 리비전의 기록**이다. 현재 능력은 위 Capability Ledger가 기준이고,
아래는 "왜 이렇게 됐는가"를 찾을 때만 본다. 이 절과 `docs/audits/`, `docs/research/diagnostics/`,
`docs/research/benchmarks/`의 감사·자격·task-proposal 문서는
[archive 안내](archive/README.md)가 정리한 **동결 기록**이며, 새 작업의 게이트가 아니다.
G0 capability baseline SHA `8ad07b8…`도 그 동결 리뷰가 본 리비전일 뿐 최신 main이 아니다.

특히 아래 문장들은 **Ledger/BACKLOG로 대체됐다. 문구 그대로 현재 범위·게이트로 읽지 않는다**:
"현재 다음 독립 gate는 N01 historical qualification", 11월 2일·11월 9일·11월 30일 날짜,
"이 G0 freeze는 ORAS·C3/C4·새 mutation operators·discovery를 추가하지 않는다 … 별도 Task Contract 필요".
현재 작업은 BACKLOG의 M2(통제 재현 박제)·M3(generic security-state gradient = 새 feedback 신호,
자력 발견)·M4(oras-go 일반성)이며, 이는 승인된 안전경계·연구 불변식 안에서 자율로 진행한다.

상태 갱신일: **2026-10-18**. G0 capability baseline은 main
**`8ad07b8e5f23f789d57ea50ba52c7acfcee951ea`**다. 이 SHA는 G0 문서 동결이
검토한 구현 revision이며 최신 main을 뜻하지 않는다. #77–#84 연구 stack은 main에
통합됐다. Internal completion qualification v3의 clean harness revision은 `9ea306f7`이고,
causal filesystem-effect qualification v4의 clean harness revision은 `72bccfa`다.

## 현재 단계와 연구 판정

Layer 2–5 core와 Layer 6 evaluation infrastructure가 구현돼 있다. Layer 6 전체나
paper/effectiveness 검증이 완료된 것은 아니다. [Research Contract
v1](research/design/research-contract-v1.md)의 G0 문서 동결과 transition synthetic stack은
통합됐지만, G1 이후 historical qualification/experiment readiness는 별개다.
과거 Phase-4 global-closeout 대기 문구는 현재 구현 상태로 사용하지 않는다.
[역사적 감사](research/benchmarks/engine-contract-audit.md)와
[handoff](research/benchmarks/post-audit-backlog.md)는 해당 revision의 기록이다.

**N01 historical automated replay는 exact 7.5.2/7.5.3 image에서 8건 readiness와
10건 pair를 완료했고 independent reader가 PASS했다. 최종 상태는
`AWAITING_HUMAN_CORRESPONDENCE_REVIEW`다. Rediscovery와 formal comparison은 NOT_RUN이며,
재발견한 역사적 취약점이나 현재 취약점을 주장하지 않는다.**
상세 identity와 claim boundary는
[N02 qualification report](research/diagnostics/n02-autonomous-integration-and-qualification.md)를 따른다.
N03의 별도 [machine correspondence audit](research/diagnostics/n03-n01-machine-correspondence-audit.md)는
retained evidence와 automated token의 consistency를 PASS로 재확인했지만 human review를 대체하지 않는다.
[N04 독립 retained-evidence 감사](research/diagnostics/n04-n01-independent-evidence-audit.md)는
원본 checksum을 다시 확인하고 별도 Linux 사본에서 current-main reader를 재실행해 같은 automated
PASS를 재구성했다. 단, 원 N02 root에는 npm tarball bytes가 없어 선언된 package digest의 직접
재해시는 **NOT_VERIFIABLE**이다. 이 결과도 machine evidence이며 human qualification token을
발급하지 않는다.
[B0/B1/B3 pilot proposal](research/benchmarks/n03-b0-b1-b3-pilot-task-proposal.md)은 exact candidate
schedule과 5초/10초 mismatch를 기록하며 **PROPOSED / NOT_AUTHORIZED / NOT_RUN**이다.

N04의 별도 [5초 preflight Task Contract](research/benchmarks/n04-five-second-preflight-task-contract-v1.md)는
사용자가 직접 승인한 최대 8건의 benign readiness 범위였다. 2026-10-18 KST 단일 attempt는
target 실행 전 host-only Docker metadata 요청이 transport allowlist에서 거부되어
**PREFLIGHT_INCONCLUSIVE / ATTEMPT CONSUMED**로 종료됐다. target extraction과 oracle control은
각각 0건이며 5초 readiness는 **NOT_EVALUATED**이다. 원본 host ledger와 판정은
[N04 preflight result](research/diagnostics/n04-five-second-preflight-result.md)에 고정했다.
후속 transport 수정은 구현·synthetic 검증 대상일 뿐 재실행 승인이 아니다. 4,000회 B0/B1/B3
pilot과 native P0/P1/P2 campaign은 계속 **NOT_AUTHORIZED / NOT_RUN**이다.

## DESIGNED / IMPLEMENTED / TESTED / EXPERIMENTALLY VALIDATED

[Evidence 용어](research/design/research-contract-v1.md)는 각 수준을 독립적으로 기록한다.
아래 TESTED는 지정된 범위의 engineering evidence이며 research effectiveness를 뜻하지 않는다.

| 영역 | DESIGNED | IMPLEMENTED in current source | TESTED evidence / 범위 | EXPERIMENTALLY VALIDATED research claim |
| --- | --- | --- | --- | --- |
| C0/C1/C2 | [계약](research/design/security-contracts.md) | persistent BEFORE/AFTER namespace, identity, sentinel effects | [oracle tests](../tests/test_state_semantics.py), [observer](../tests/test_observer.py), [real pipeline](../tests/test_pipeline.py) | N01 exact pair에서 7.5.2 C1/C2 5/5, 7.5.3 0/5; final human disposition pending |
| Linux execution | fresh runtime + container-required third-party boundary | backend / prepared invocation / verified artifact admission; N01 exact wrapper locks and bounded pair orchestration | [container integration](../tests/README.md); pinned Node benign smoke; N01 8+10 real historical runs와 independent reader PASS | N01 automated replay complete; final qualification pending |
| Mutation | legacy / M1 / protected-component / A3 contracts | eight slots; M1 nested/reused names/dependencies; versioned default-sentinel component policy; no-reorder versions | [mutator tests](../tests/test_mutator.py), [constructive addressing](../tests/test_mutator_addressing.py), [search composition](../tests/test_campaign_search.py) | logical address generation만 TESTED; historical effect 미검증 |
| Search / feedback | B0/B1/B3 and A1/A2 | `SearchState`, `run_search_campaign`, explicit policy config | [policy checks](../tests/test_feedback_search_contracts.py), [trusted reference integration](../tests/test_campaign_search_integration.py) | 비교 효과 미검증 |
| Entry transitions | P0 final-state, P1 transition retention, P2 transition-adaptive mutation; separately versioned v3 rebinding composite | v1 model/search/evaluation; v2 event model/feedback, bounded node-tar producer/raw export, independent reader and qualification runner; additive v3 composite model/strict reader/finite feedback | synthetic tests plus node-tar/libarchive controlled qualification; v2 producer 10 checks PASS and 480-run matrix independently verified at `36ff7fd`; v3 22 synthetic checks and canonical 1,584-test suite PASS | v1 `BLOCKED_NATIVE_OBSERVATION`; v2 `V2_NATIVE_EFFECT_OBSERVATION_NOT_QUALIFIED` (replacement coverage); v3 native producer NOT_IMPLEMENTED and qualification/effectiveness NOT_RUN |
| Minimization | bounded deterministic generic/USTAR reduction | core and exact-fingerprint evidence binding | [minimizer tests](../tests/test_minimizer.py), [USTAR checks](../tests/test_minimizer_ustar.py) | historical/unknown candidate 없음 |
| Evaluation / reproduction | explicit provenance, immutable raw → verified derivation | reader, pair records, failure ledger/legacy journal, policy journal/timing/repetition/controller HWM, candidate 3+3 raw replay, N01 machine matcher, qualification/matrix, benign replay, completed policy export/config/dataset/statistics | [evaluation tests](../tests/evaluation/), [benign replay tests](../tests/replay/) | HWM/matcher는 controlled TESTED; historical pilot memory/candidate assessment / human known-class judgment / formal dataset 없음 |
| C3/C4 / generality | 후속 contracts / RQ4 | C3/C4와 ORAS adapter 없음; GNU route는 benign allowlist만 | broader scope의 실행 증거 없음 | 미검증 |

## 기준 main의 검증 근거

[main CI run 37248955432](https://github.com/TheWaitForAGI/InodeFence/actions/runs/37248955432)
은 `8ad07b8`에서 check와 container-integration을 통과했다. 해당 baseline의 canonical
`make check`는 **1,304 tests PASS**, Ruff/Pyright/environment/docs 검사를 포함한다.
이는 고정 revision의 검증 기록이지 이후 checkout에 적용되는 live test count가 아니다.
Contained **node-tar 7.5.22 benign smoke PASS**는 실제 extractor를 실행한 engineering
증거다. Historical 7.5.2/7.5.3 execution이나 rediscovery 증거로 승격하지 않는다.
과거 [pre-audit](../experiments/summaries/pre-audit-readiness-v1.md) 및
[benign Node 요약](../experiments/summaries/benign-node-container-smoke-v1.md)은 각자의
revision/config/checksum을 유지한다. 그 수치를 현재 실험 결과로 옮기지 않는다.

## 실제 실행 및 evidence 경계

`pipeline.run_case`는 TAR/layout/sentinel과 target 준비 뒤 BEFORE를 찍고, target 종료 뒤
bookkeeping/cleanup 전에 AFTER를 찍는다. 양쪽 cleanup이 끝나야 결과가 반환된다.
Disposable directory는 OS sandbox가 아니다. Third-party target은 검증된 `IsolatedTarget`이
필수이며 Linux runtime volume `/var/lib/inodefence`를 source bind mount와 분리한다.

[Security Contract](research/design/security-contracts.md)의 C0는 HARNESS까지 포함한
sandbox 내 extraction 밖 persistent namespace 변화다. C1은 post-state lstat identity,
C2는 지정 sentinel의 전후 content/metadata 변화다. Transient effect, sandbox 밖 접근,
symlink referent, inode reuse, direct-use/tracing은 판정하지 못한다. 관찰 실패는 오류이며
nonviolation을 만들지 않는다. `violated=False`는 safety proof가 아니다.

`run_search_campaign` / `SearchCampaignConfig`는 **B0/B1/B3 × FULL/A1/A2 ×
legacy/M1/protected-component/A3**를 명시적으로 실행한다. B0는 unretained walk, B1은 key novelty admission,
B3는 key OR violation novelty admission이다. A1/A2는 feedback key만 투영한다.
A3는 reorder draw를 유지한 no-op이며 insertion/duplicate의 order variation은 남는다.
[정확한 비교 범위](research/benchmarks/baseline-and-ablation-v1.md)를 따른다.
Path-only와 fixed-recipe baseline은 없으며 RQ2/RQ3의 비교로 주장하지 않는다.

The generic entry-transition model preserves exact archive ordinal/path/type/link-target
association, complete raw checkpoints, derived filesystem deltas and normalized transition
keys without changing `RunResult` or final C0/C1/C2 semantics. Its current evidence is a
deterministic synthetic file → hardlink → replacement sequence. The separate P0/P1
campaign core keeps uniform parent/mutation behavior constant while replacing P0 final-state
admission with P1 transition-key admission; full-state, transition, violation and incomplete
trace diagnostics remain independent. P2 keeps P1 retention and uniform parent selection,
then adapts explicit operator weights from 1 through 8 using only binary new-transition-key
reward. Violations remain diagnostic and do not receive scheduler reward. A native extractor
completion producer and transition effectiveness are still not implemented results.
[The exact contract](research/design/transition-feedback-v1.md) keeps synthetic model/search
correctness separate from native observation qualification.

`TransitionEvaluationConfig` binds the policy IDs and frozen provenance to a separate
checksummed result bundle. Its reader replays parent/operator/mutation/admission/scheduler
decisions before summaries or P0/P1/P2 arm statistics are accepted. This is TESTED with a
deterministic synthetic producer; it does not make native target effectiveness a result.

Pinned node-tar 7.5.22 public async/sync events, Linux inotify, strace and fresh-process
prefix replay were tested with benign regular/directory/hardlink/symlink/duplicate-path
fixtures. Public events precede common write/close/metadata completion; event receipt
snapshots can include later effects or fail coherent capture; syscall completion order is
not archive order; prefix replay is a separate counterfactual execution. A separate
libarchive 3.7.2 public write-disk qualification associated all ordinal/path markers but
applied directory metadata only during final writer close.

A third source-guarded qualification wrapped node-tar's actual bundled private `checkFs2`
callback. All 440 marker/snapshot callbacks had exact entry association, but mixed snapshot
completion was out of archive order in 20/20 runs, independent-files was out of order in
18/20, callback snapshots included later-entry effects, and one of 220 snapshot callbacks
recorded a consistency failure. Snapshot median target time was 1.336×–1.660× stock in the
three benign cases and marker/snapshot scheduling distributions differed. Final semantic
states remained equal, which is insufficient to establish intermediate neutrality. All
three controlled candidate sets are **QUALIFIED FAIL** for the current complete
ordered-checkpoint contract. No native producer is implemented, and P0/P1/P2 target
effectiveness remains **NOT_RUN**. See the
[qualification decision](research/design/entry-transition-observation-v1.md) and retained
[node-tar](../experiments/summaries/node-transition-observation-qualification-v2.md) /
[libarchive](../experiments/summaries/libarchive-entry-boundary-qualification-v1.md) /
[internal completion](../experiments/summaries/node-internal-completion-qualification-v3.md)
summaries.

A fourth source-guarded candidate propagated entry identity through Node async resources
and recorded callback-based filesystem operation completions instead of treating a callback
snapshot as a checkpoint. Its clean 480-process run preserved all expected outcomes and
final semantic states. All 1,020 operation events had exact entry association and there were
no observation failures. Independent-files nevertheless completed `0,1,3,2` in 20/20
effects runs and recorded 162 successful later-ordinal operations before earlier entry
completion. The context-only and effects scheduling distributions differed, and effects
median target duration was 1.152×–1.308× stock across fixtures. Partial rejection was
preserved after ordinal 0 completion in 20/20 effects runs. The fixed rule therefore gives
**QUALIFIED FAIL** and the native v1 gate is **BLOCKED_NATIVE_OBSERVATION**. No producer or
target P0/P1/P2 run exists. The [v4 summary](../experiments/summaries/node-causal-effect-qualification-v4.md)
retains exact evidence. The separate
[partial-order/effect-event v2 observation contract](research/design/entry-effect-observation-v2.md),
[architecture](research/design/entry-effect-architecture-v2.md),
[normalized feedback contract](research/design/entry-effect-feedback-v2.md) and
[design review](research/design/entry-effect-design-review-v2.md) now pass Design Gate 1.
The immutable generic lifecycle/effect/identity/causal trace model, separate
`EffectRunResult`, finite normalized keys, fail-closed P0-v2/P1-v2/P2-v2 search, bounded
scheduler and caller-owned closed loop are IMPLEMENTED and TESTED synthetically. Synthetic
Gate 2 is PASS. Gate 3 now has a source-guarded bounded worker, contained adapter, controller
flush verification before AFTER, class-specific evidence conversion and no-overwrite raw
export. The WSL recovery task retained the Gate 4 base `5575169` and fixed two target-side
integration defects on a separate branch. At clean revision `36ff7fd`, the contained Gate 3
suite passed 10/10 checks and canonical `make check` passed 1,387 tests. Gate 4 completed all
480 runs: 420 success and 60 expected rejection. Fresh controller and host readers each
verified all 320 native bundles and 160 stock records. Thirteen of fourteen mandatory
criteria passed; replacement coverage failed because duplicate-path reused the same inode
and truncated it in 20/20 full runs. The exact decision is
`V2_NATIVE_EFFECT_OBSERVATION_NOT_QUALIFIED`. Immutable raw evidence, checksums and audit
reports are retained in the [v2 summary](../experiments/summaries/node-native-effect-observation-qualification-v2.md).
Target campaign remains blocked and NOT_RUN.

후속 node-tar 진단은 exercised archive-only/precreated cases의 실제 namespace rebinding이
단일 operation이 아니라 `unlink -> create/link/symlink`로 구성됨을 확인했다. 18/18 complete
native diagnostic bundle에서 v2 `namespace_replacement`는 0건이었으며, 이는 reader가 frozen
계약을 잘못 분류했다는 근거가 아니다. v2 판정은 그대로다. 별도
[v3 rebinding semantics 제안](research/design/entry-effect-rebinding-v3-proposal.md)은 composite
dependency/evidence 조건에 대해 기술 검토됐고, 별도
[Task Contract](research/benchmarks/n04-namespace-rebinding-sequence-v3-task-contract.md)에 따라
generic model, strict independent reader와 additive finite feedback이 **IMPLEMENTED / SYNTHETIC
TESTED**됐다. Same-path/explicit-absence/conflict-free dependency gap이 v2 normalized keys에 없는
구분을 추가함을 synthetic nonredundancy fixture로 확인했다. Native dependency producer는
**NOT_IMPLEMENTED**, qualification/effectiveness는 **NOT_RUN**이며 어떤 native campaign도
허가하지 않는다. 상세 결과는 [N04 v3 synthetic verification](research/diagnostics/n04-namespace-rebinding-sequence-v3-synthetic-verification.md)에 고정한다.

Legacy `ExperimentConfig` v1/v2는 여전히 B3/legacy mutation만 허용한다. 별도
`PolicyEvaluationConfig`와 completed policy export/reader/config/dataset/statistics가 구현됐다.
Reader는 raw derivations와 admission/parent binding을 검증하되 실제 RNG/mutation 실행을
재구성하지 않는다. 별도 policy journal은 exact RNG parent/operator/mutation/feedback을 replay하고
중단 prefix/failure를 보존한다. Policy repetition schedule은 exact config slot을 claim하고
complete/failed terminal digest를 결합하며 STARTED slot을 retry하지 않는다. Full result는
O(budget) memory다. Legacy runner에는 completed-step callback이 없다.
Final-state policy runner의 `policy-full-step-monotonic-v1` evidence/reader는 동기 journal
publication까지 포함한 step offsets를 보존한다. Existing result/policy schema와 target duration은
변경하지 않는다. Final publication timing, timed dataset pooling과 known-class adjudication은
완성된 자동 pipeline이 아니다. Target duration으로 전체 latency나 throughput을 대신하지 않는다.
별도 `linux-proc-self-vmhwm-v1`은 terminal slot에 controller process-lifetime peak RSS를 결합하고
측정 slot 사이 process identity 재사용을 거부한다. 이는 campaign delta나 target-container memory가
아니며 historical pilot 측정값은 아직 없다.
[Candidate pair replay](research/design/candidate-pair-replay-v1.md)는 verified policy evidence의
exact case를 counterbalanced affected/fixed 3+3 raw execution에 binding하고 complete/failed/interrupted
prefix를 보존한다. 이는 N01 class match나 human root-cause 판정이 아니다.
[실험 안내](../experiments/README.md)를 따른다.

## 다음 연구 gate

Native entry-transition work cannot proceed to v1 Phase B/C/D. Reopening it requires the
separate v2 qualification Task Contract; v1 policy IDs and evidence cannot be silently reused.
This blocker does not promote or invalidate the independent final-state historical plan.

The v2 contained qualification has completed with a retained negative decision. Replacement
coverage must be established under a separate frozen Task Contract before another matrix.
Native campaign integration remains blocked until the exact
`V2_NATIVE_EFFECT_OBSERVATION_QUALIFIED` decision is retained. The initial v2 policy rejects
incomplete/invalid streams and target-rejection prefixes for admission/reward.
The runtime diagnosis selected the multi-operation branch for the exercised node-tar cases.
The separately versioned v3 generic representation passed its synthetic engineering gate.
The next v3 step is not an implicit campaign: a native dependency producer and qualification
matrix require a new frozen contract and explicit authorization. Alternatively, v2 can only
reopen with a genuine one-operation positive under its own contract.

N03 independent closeout은 [structured report](research/diagnostics/n03-autonomous-research-advancement.md)에
기록한다. Final-state journal/timing/repetition infrastructure는 IMPLEMENTED / TESTED지만 pilot과
known-class adjudication은 완료되지 않았다. Generic v3 rebinding은 synthetic engineering
검증만 완료했으며 v2 negative decision이나 P0-v2/P1-v2/P2-v2 gate를 변경하지 않는다.

**첫 historical qualification인 N01 node-tar 7.5.2 / 7.5.3 hardlink arm은 automated
replay를 완료했고 final human correspondence review를 기다린다.**
두 exact [wrapper locks](../experiments/benchmarks/locks/README.md)는 공통 historical production
closure로 준비하고 portable validator를 통과했으며, N02 attempt에서 image build/runtime/
options/setup admission도 통과했다. M1은 composition을 지원하지만 기존 finite vocabulary가 default
`outside/sentinel.txt`를 생성하지 못한다. 별도 versioned
[protected-component policy](research/design/mutation-protected-components-v1.md)는 original benign
seed에서 해당 상대 주소까지의 deterministic logical reachability를 TESTED했다. 이는 target-visible
setup, historical affected/fixed behavior 또는 rediscovery를 검증하지 않으므로 contained setup과
pair qualification 전 unknown-vulnerability campaign으로 넘어가지 않는다.
[2026-10-15 execution progress](research/diagnostics/n01-historical-execution-progress-2026-10-15.md)는
두 변경의 tested integration revision, N01 contract technical review와 후속 implementation gate를
기록한다. Human authorization은 2026-10-15에 기록됐다. N01 전용 구현은
normal `7.5.22` validator와 분리된 metadata admission, 정확히 8건의 readiness,
counterbalanced 10-run pair, result-first publication과 fresh-process independent reader를 포함한다.
이 구현의 controlled-adapter tests와 별개로 clean `e987c855` source와 trusted
macOS/OrbStack controller에서 두 historical image를 immutable ID로 admission했고, 8건
readiness와 10건 pair를 한 번 실행했다. Independent reader는
`N01_PAIR_AUTOMATED_REPLAY_COMPLETE`를 재계산했다. 7.5.2는 C1/C2 5/5, 7.5.3은
C1/C2 0/5와 strict rejection 5/5였다. Frozen contract의 human correspondence disposition이
남아 final token은 없으며 pilot과 B0/B1/B3는 **NOT_RUN**이다. 전체 evidence는
[N02 report](research/diagnostics/n02-autonomous-integration-and-qualification.md)에 기록한다.
[Benchmark Set](research/benchmarks/benchmark-set-v1.md)과
[catalog](../experiments/benchmarks/README.md)의 15개 G0 planning record는 여전히 정적
`NOT_RUN` 값이며 READY는 없다. 이 값은 별도 N01 qualification evidence의 live 상태를 대신하지 않는다.

순서를 유지한다: G0 정의 → oracle → harness → fuzzer correctness → synthetic →
historical qualification → pilot → experiment freeze → main experiments → candidate triage →
analysis → paper → independent reproduction. 현재 다음 독립 gate는 N01 historical
qualification이다.

[Evaluation protocol](research/benchmarks/evaluation-protocol-v1.md)의 budgets/subsets는
pilot 이전의 제안이며 main-experiment freeze가 아니다. Negative result, qualification failure,
rejection/timeout와 infrastructure-invalid attempts를 모두 보존한다. Raw data는 수동 수정하지 않는다.
11월 2일 발표는 working implementation과 검증된 pilot 범위를 구분해야 하며, 11월 9일
experiment freeze와 11월 30일 최종 artifact는 별도 승인/증거가 필요하다.

## 변경 범위와 문서 우선순위

현재 범위는 Linux TAR/USTAR, C0/C1/C2, fresh extract와 controlled sentinels다.
이 G0 freeze는 ORAS, C3/C4, PAX/GNU encoding, 새 mutation operators 또는 discovery를 추가하지 않는다.
새 기능이나 methodology 변경에는 별도 Task Contract와 영향 문서 검토가 필요하다.

현재 상태는 이 문서, G0 정의는 [Research Contract](research/design/research-contract-v1.md),
C0/C1/C2 의미는 [Security Contracts](research/design/security-contracts.md), 비교/측정 정의는
[연구 질문](research/design/research-questions.md)과 [프로토콜](research/benchmarks/evaluation-protocol-v1.md)을
따른다. Historical audit/summary는 자체 날짜와 SHA의 기록으로만 읽는다.

## Phase 2 조사 기록

- **P2-a C1 일반화 영향 조사 (2026-10-23, `jiwoong/p2-a-c1-impact`) — 판정: 안전(additive).**
  C1을 "extraction object ↔ 지정 sentinel" 대신 "extraction object ↔ EXTERNAL object 전체"와
  비교하도록 일반화하는 변경안을 **임시 패치(미커밋, 되돌림)**로 Dev Container에서 실행해 영향만 확인했다.
  기존 C0/C1/C2 판정·oracle fixture 4/4·N01 경로·전체 pytest가 모두 불변이고(전체 1722 passed,
  1 failed는 C1과 무관한 기존 container-backend 환경 실패), extraction↔비-sentinel EXTERNAL identity
  공유 탐지만 **추가**된다. `archive/input.tar`(HARNESS)는 일반화 후에도 C1이 되지 않으며(의도),
  HARNESS까지 포함하는 확장은 `IdentityEvidence`의 EXTERNAL 제약 때문에 additive가 아니다(별도 모델
  변경 필요, P2-b 범위). 코드 판정은 바꾸지 않았다(소스 변경 0). 상세는 [LOG](LOG.md)와
  [BACKLOG](BACKLOG.md) P2-a.

아래는 2026-10-18 기준 상세 기록이다.

상태 갱신일: **2026-10-18**. G0 capability baseline은 main
**`8ad07b8e5f23f789d57ea50ba52c7acfcee951ea`**다. 이 SHA는 G0 문서 동결이
검토한 구현 revision이며 최신 main을 뜻하지 않는다. #77–#84 연구 stack은 main에
통합됐다. Internal completion qualification v3의 clean harness revision은 `9ea306f7`이고,
causal filesystem-effect qualification v4의 clean harness revision은 `72bccfa`다.
