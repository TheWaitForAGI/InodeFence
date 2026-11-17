# 현재 프로젝트 상태

2026-11-03 이전 결과 기록(중간발표 P0 표, 2026-10-24 한눈에 보기, Ledger·마일스톤의 옛 M3·M4 캠페인 서술)은 [pre-20261103-results](archive/pre-20261103-results.md)로 옮겼다.

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
| 퍼저가 경계위반을 찾는가(H-A, R/D/S-u) | 본실험 결과 자리(봉인 해제 뒤 기입) | 초기 비교는 arm 간 어휘가 달라 폐기했고, 어휘를 맞춘 R/D/S-u 설계로 다시 실험했다. 이전 기록은 [archive](archive/pre-20261103-results.md) |
| entry-transition native 관찰 | DESIGNED / NOT_IMPLEMENTABLE (honest negative) | native completion boundary 미확보 → NOT_IMPLEMENTED. **ordered-transition 경계접근 gradient**(none<external_namespace<cross_boundary_identity, Region·ChangeField만·answer-agnostic=protected/sentinel 근접 미보상)를 설계했으나, 그 rung이 요구하는 ordered·entry-correlated 경계가 **fundamental하게 관찰 불가**(node-tar: public/OS/private snapshot·causal 전부 QUALIFIED FAIL; decompress: 엔트리 동시·재정렬 기록·컨텍스트 미전파 = 동류; oras-go 더 어려움 — generality-m4 feasibility, observed 2026-10-30). → 구현 코드(`feedback/transition_gradient.py`·`TransitionBoundaryProximity`)는 **dead로 제거**(소비자 0, EN-008); **설계+negative 발견은 transition-feedback-v1.md에 보존**. 2번째 extractor로 실제 일반화되는 건 generality lane canonical `feedback/boundary_attempt_frame.py`(`inodefence-boundary-attempt-v1` frame→M3.1 키 emit+normalize, main M3.1+주언 metrics 소비), 이 transition 경로 아님. transition **모델**(checkpoint/transition/novelty/retention)은 불변. 상세 jiwoong/m3-transition-gradient-signal, transition-feedback-v1.md |
| cross-implementation(2번째 extractor에 generic oracle 적용) | 일부 TESTED(oracle 수준) | **Python stdlib tarfile 통제 차분**: C1 하드링크 fixture를 Python tarfile로 돌려 fully_trusted(영향)=외부 sentinel inode 공유로 production oracle이 C1+C2 발화, data(PEP 706 완화)=거부·위반 0. oracle 코드 불변, target-agnostic 확인. `tests/test_python_tarfile_generality.py` 4 passed. **단 node-tar 결과·fuzzer 자력 발견 아님**(oracle·adapter 수준 일반성 증거). **oras-go(Go)·decompress(JS) adapter 구현 완료**(#176·#177): 동일 generic oracle로 affected/fixed digest-pinned 통제 reference 차분 + container-integration generality 체크 통과 → python-tarfile 포함 **3개 독립 extractor**에서 adapter 수준 일반성 확인(target 로직은 adapter/worker/recipe에 격리, generic 모듈 불변). Ledger M4 |
| 실험 campaign 병렬/클라우드 팬아웃(단일 호스트 직렬화 해소) | IMPLEMENTED/TESTED | **단일 호스트**: `scripts/run_parallel_native.py`(version×arm×seed, `--jobs` 세마포어, RUN_ID 격리)를 라이브 검증 — demo 2셀 각 ~24.7s 병렬·evidence 생성·격리 OK(observed). **클라우드**: GHA ubuntu-24.04 러너가 잠긴 하너스를 그대로 돈다(observed — CI `container-integration`이 매 실행 이미지 3개 빌드 + trusted 컨트롤러 + effect-demo) → `workflow_dispatch` `.github/workflows/experiment-fanout.yml`가 러너 플릿으로 캠페인 팬아웃(plan=`run_parallel_native --emit-github-matrix`로 셀 매트릭스 → fanout=셀별 독립 러너가 CI와 동일 경로로 1캠페인+evidence artifact; historical effect 이미지는 committed 레시피 `tools/node-tar/effect/Dockerfile`로 러너 빌드, 외부 publish 0). Claude 클라우드 에이전트 env는 devcontainer에 docker-in-docker 미포함 → 하너스 실행 불가(inferred, Dev Container와 동일). 격리·**클라우드 GHA fanout의 budget 상한 100(하드캡; native controller의 `MAX_NATIVE_BUDGET=2000`과 별개 — 상한 값 자체는 불변)**·trusted 컨트롤러·완화 플래그 0 모두 불변. **처리량 infra이며 effectiveness·발견 주장 아님.** host-broker는 여전히 non-build(지휘관 C+ 유지). |
| 사용자 명령 `inodefence`(제품, 0.2.0 릴리스 후보; 범위와 릴리스 조건은 [D049](DECISIONS.md)) | IMPLEMENTED(네 대상 `verify`·`explore`·`replay`) / 일부 TESTED | 단위 테스트는 Docker를 mock한다(`tests/test_cli.py`·`test_run_target*.py`·`test_replay_four_targets.py` 등). 호환 약속(종료 코드, `result.json` v1)은 `tests/test_result_contract.py`로 고정. 실제 extractor 실행은 WSL2 한 대의 수동 demo run뿐이다([USAGE 지원 환경과 확인 수준](USAGE.md#지원-환경과-확인-수준)). **아직 없는 것**: oras-go 2.6.2 외 버전에서의 탐색 추출 확인(2.6.2는 demo run 1회에서 11/20 추출, P-3), 실제 위반 케이스의 `replay` 실행, 두 번째 호스트 확인. `main`에 없고 태그·릴리스도 없다(Draft 스택). 남은 일은 [BACKLOG PRODUCT 절](BACKLOG.md). 연구 주장과 무관하며 제품 실행은 demo run이다 |

### 마일스톤 (날짜 아님 — 증거가 모이면 찍는다)

- **M1 — 루프가 실제 node-tar에서 돈다.** 상태: **완료**(위 Ledger 1~6행).
- **M2 — 실제 경계위반 통제 재현 + 버전 구분 (2-CVE 차분).** 상태: **실증됨 + 박제 완료**. 재현 스크립트+raw 증거 2쌍(`experiments/repro/`)이 **동일한 generic identity oracle**(추출객체가 외부 참조파일 inode 공유)로 서로 다른 root-cause 2개를 관통한다: ① 최상위 하드링크 7.5.2 공유→7.5.3 거부 = **CVE-2026-23745**(linkpath sanitation 누락; catalog N01·R1), ② 중첩 하드링크 7.5.6 공유→7.5.7 거부 = **CVE-2026-24842**(검증 base ≠ 생성 base의 check/use mismatch, CVE-2026-23745 수정이 **도입한** 회귀; catalog N02·R2, GHSA-34x7-hfp2-rc4v). 관찰된 공유 분포는 **비단조**(중첩: 7.5.2 O·7.5.3 X·7.5.6 O·7.5.7/7.5.8 X)로 7.5.3이 고친 것을 7.5.6이 되돌렸음을 보인다. advisory 범위(24842 `<7.5.7`)와 이 특정 fixture의 observed 거동은 다를 수 있어 exact 하한은 미검증(observed/inferred 구분). 핵심: **outcome 기반 oracle 하나가 R1·R2 두 root-cause를 릴리스 id/정답경로 하드코딩 없이 모두 포착.** 재발견(자력 발견, M3)과는 구분. **M2.2(박제 완료, claude/m2-2-oracle-path-7d09f3)**: 손 probe 판정 == production Observer+Oracle 판정 일치를 additive 테스트로 고정 — CI는 run_case로 7.5.2 공유 post-state를 재현해 generic C1+C2 일치 + M2.1 증거 바인딩, native closure는 container_integration의 `run_node_tar_effect_case` 체크(호스트 docker+이미지, make check 미수집). observed(실제 node-tar=M2.1 증거) vs reproduced(통제 extractor post-state) 구분, oracle/fixture/N01 불변.
- **M3 — 퍼저가 자력으로 그 위반을 찾는다.** 초기 비교는 arm 간 어휘가 달라 폐기했고, 어휘를 맞춘 R/D/S-u 설계로 다시 실험했다. 상태: 본실험 결과 자리(봉인 해제 뒤 기입). 이전 기록은 [archive](archive/pre-20261103-results.md).
- **M4 — 일반성.** 태스크: 2번째 extractor 동일 모델 적용. 상태: **완료(지웅 판정 2026-11-17: oracle·adapter 수준 일반성으로 완료로 본다. 자력 발견은 M4의 완료 조건이 아니며 후속 연구로 둔다).** **oracle+adapter 수준 일반성 3 extractor 확보**(python-tarfile·oras-go·decompress). 동일 generic C0/C1/C2 oracle(코드 불변)이 **Python stdlib tarfile**에서도 경계위반을 포착함을 통제 reference 차분으로 보임(fully_trusted=영향 → C1+C2, data=PEP 706 완화 → 거부; `tests/test_python_tarfile_generality.py` 4 passed). 이는 oracle의 target-agnostic성 증거이며 **fuzzer 자력 발견·effectiveness 주장 아님**. **oras-go·decompress adapter 구현 완료**(#176·#177): 동일 generic oracle이 python-tarfile·oras-go·decompress 3개 독립 extractor에서 adapter로 경계위반을 포착(affected/fixed 통제 reference 차분 + container-integration 체크 통과).

특정 날짜를 문서에 박제하지 않는다. 기한은 팀 일정으로 관리하고 이 문서는 능력만 추적한다.

---
---

## 지금 상태와 다음 할 일

- **기준.** 계획은 Claude Doc 「InodeFence 독립 연구 감사 및 실험 설계 재정립」
  (https://claude.ai/artifact/JJtsK3VowEGuBFN3YXZDFq), 작업 큐는 [BACKLOG](BACKLOG.md), 실험 실행은 Git에 동결된
  사전등록(`experiments/preregistration/`, 태그 `prereg-exp3-exp2-freeze-20261113`), 증거는 raw + SHA-256 목록
  (`experiments/summaries/raw-manifest-*.sha256`, 기준선 태그 `audit-baseline-20261103`)이다. 결정은
  [DECISIONS](DECISIONS.md), 실행 기록은 [LOG](LOG.md)에 있다.
- **본실험(M3).** EXP-3 train과 GO 판정, EXP-2 holdout 실행이 끝났고 봉인 해제 기록이 병합됐다(#485,
  `experiments/summaries/exp2-holdout-unseal-record.json`). 결과 값과 판정 문장은 결과 PR과 주장 목록
  (`paper/sections/claims-evidence-status-v1.md`)에서 채운다. 이 문서의 "본실험 결과 자리"는 그때 갱신한다.
- **제품 0.2.0.** `main`에 올리는 길은 착지 PR 하나다(D049). 릴리스 조건 6개 가운데 실제 위반 `replay` 기록(4),
  두 번째 호스트 확인(6)이 남았다. 남은 일은 [BACKLOG PRODUCT 절](BACKLOG.md).
- **제출물.** 결과보고서와 소개 영상의 일정과 상태는 [BACKLOG](BACKLOG.md), 초안은 `paper/deliverables/`에 있다.
- **이전 상세.** 2026-11-17 이전의 단계별 판정, evidence 경계, 수술 기준·실험 순서·게이트 표, 문서 모순 목록은
  [archive/status-detail-20261117](archive/status-detail-20261117.md)로 옮겼다. 새 작업의 게이트가 아니다.
