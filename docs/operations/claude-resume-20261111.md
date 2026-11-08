# InodeFence — 2026-11-11 Claude 재개 / EXP-3·EXP-2 실행 전 인계

> 상태: 2026-11-08 기준 **실행 전 준비 메모**. 이 문서를 병합하거나 읽었다고 해서 실험·동결·머지 승인이 생성되지 않는다.
> 이 문서는 사람/Claude/Codex 공통 인계서다. 수치 출처를 분리하며, 최신 브랜치와 GitHub PR 상태는 재개 시 재조회한다.
> **절대 원칙:** 기존 H1 raw 및 EXP oracle 봉인 유지, 유료 Codex Plus 소모 최소화, main 직접 푸시 금지, 실행 PR을 승인 없이 머지하지 않음.

## 0. 일정과 기존 의사결정

- **11/11(수):** Claude Code 세션을 다시 열고, 아래 읽기 전용 감사를 마친 후 W1 구현 → W3 연구 검증 → W1 정합 재확인. 사전등록 dry-run·합성 E2E·CI·회귀·실행 환경을 준비한다.
- **11/18:** D040-D1에 따라 `exp3-v1` (train 20 seed)와 `exp2-v1` (조건부 holdout ≤120 seed)를 함께 **동결**, EXP-3 train 시작. 이 날짜를 앞으로 당기는 것은 별도의 사람 결정과 기록이 필요하다.
- **11/25 12:00 KST:** 사전 고정 실행 마감. D040/D041의 마감 후 seed 제외·운영 중단 규칙을 그대로 적용.
- **11/26:** 결과보고서 및 소개영상 제출 목표. 11/30 최종 발표.
- D040: train seed 9006–9025; holdout 9026–9145; budget=2000; sentinel k=5; arm R-restart / D / S-u; 두 등록 파일 모두 `targets.<id>.*`. `engine_sha`·k·generator·budget·arm 공통.
- D040-D11: **GO = E≥1 ∧ floor(H_rem·r/(6000·e))≥76 ∧ train abort≤.45**. GO 자동 판정 금지. W3가 train 실측으로 적용 후 LOG에 기록한다. D041의 record-inconsistent 집계와 D043 PR의 r_wall 정의 검증 필요.
- Holdout D4/D5: 고정 후보 5개에 대해 규칙 커밋 후 **고정 fixture** 상태 확인, 전 후보·증거·qualification-only 원장 기록 및 독립 검토. **실험적 탐색/결과 유리한 타깃 교체 금지.**

## 1. 지금까지 확인된 사실 — 출처 수준 분리

- **main 및 PR 메타데이터 GitHub 확인(11/08):** main PR base sha `2278dffb95e2148f0cfe892322abb512f756589f`. 최초 조회 시 open PR 22개(#307 생성 전). 최신 여부는 11/11 다시 조회.
- **이전 벤치마크(사용자 제공 진단/결정):** Stage A (jobs 2,4,4,2), 총 48캠페인 중 abort 17. jobs=2 8/24=.333, jobs=4 9/24=.375. `H1 / halted / selected_jobs=null / fallback_jobs=null`. raw의 oracle은 EXP-3 동결 전 봉인.
- **호스트 증거(사용자 제공):** Docker broker 완전 기록 48/48, Docker 명령 timeout 40건, 서로 다른 캠페인 동시 지연 군집, `docker ps` 23.0초 지연 1건. 최초 예외 체인상 runtime inspect 14, cleanup inspect 2, 삭제 확인 1. `container start` timeout이 먼저 발생한 호출도 일부 존재. Docker daemon root cause는 확정되지 않음.
- **원본 백업(사용자 확인):** Windows→Google Drive→Mac 238/238 SHA-256 PASS (raw 약 1.5GB). WSL Drive G:→/mnt/g 자동 마운트 설정. 재시작 후 재마운트/실제 Cloud sync 최종 상태는 추후 확인.
- **후보 패치 검증(사용자 실행):** `codex/p0-306-h1-inspect-timeout-recovery` SHA `fa3e80f` (Windows cherry-pick `c5ee031`); 관련 178 pytest PASS, Docker smoke 19 PASS, 추출 8/8, 18/18 컨테이너 정리, 3-arm jobs=2 smoke 3/3 종료코드0·watchdog 0·잔여0. 로그 21개 Google Drive 복사 후 `desktop.ini` 제외 diff PASS. **이는 고부하 H1 해결 증거가 아님**.

## 2. H1 진단의 우선순위 (W2/연구 W3; 코드 수정 전)

- #306 기존 도구 사용: `scripts/diagnose_concurrency_h1.py`. **새 분석기 재구현 금지.** `concurrency-report.json`, `block.json`, `*.calls.jsonl`, `host/events.jsonl`, `host/samples.jsonl`만 읽는다. campaign `*.json`, `*.steps.jsonl` 및 그 내부 oracle 조회 금지.
- 분석 대상은 **abort 17개만이 아니라 정상 종료한 31개를 포함한 48개 전부의 Docker 호출**. 호출별 단계/비정상률/시간 분포(p50/p95/p99/max), 블록·jobs·arm·시각별 `start/inspect/wait/remove` 지연, timestamp 정렬과 host probe, 비정상 호출의 첫 예외/cleanup 예외 차이를 수량화한다.
- 원인 분리: ① 공통 Docker/WSL2 응답 지연 ② per-case CLI 고빈도 호출 구조 ③ runtime inspect의 10초 계약 ④ 입력 종속(동일 case/step 재발) 가능성. 단순 `EOF`/timeout 일치만으로 daemon fault 확정 금지.
- #307은 **cleanup inspect 1회 재조회 후보**일 뿐이다. 첫 예외 14/17인 runtime inspect를 해결하지 못한다. 실행 중 inspect를 무조건 재시도하면 fail-closed 회귀 3개와 충돌한 이력이 있으므로, 먼저 격리/종료/상태 검증 안전 계약과 대조한다. `start --attach`는 target 10초 제한을 포함하므로 무조건 재시도하거나 timeout을 늘리지 않는다.
- H1은 계속 **halted**. jobs=2도 안전하다고 선택된 적이 없고 H3 fallback이 아니다. 코드·retry·timeout·cleanup 순서 변경은 기존 측정과 연결할 수 없으므로 설계 §3.5/§9와 W3 판단, 사용자 승인에 맞춘 **별도 출력 경로·새 SHA** 재측정 계획을 먼저 만든다.
- 호스트와 맥/Windows 역할을 명확히 구분하고, 게임/기타 Docker 작업 등 혼입 요인을 기록한다. 의심 원인이라고 해서 사후 임계 조정 금지.

## 3. 기존 PR 활용 — 중복 작업을 만들지 말 것

| 목적 | PR | 관계·주의 |
| --- | --- | --- |
| H1 증거 분석 | [#306](https://github.com/TheWaitForAGI/InodeFence/pull/306) | 기존 host metadata 분석기, Draft. raw 증거 봉인 유지 |
| H1 수정 후보 | [#307](https://github.com/TheWaitForAGI/InodeFence/pull/307) | cleanup-only retry. Draft, root-cause 미확정. **머지 보류** |
| 상태 문서 | [#304](https://github.com/TheWaitForAGI/InodeFence/pull/304) | H1 halted, 17/48 반영. 다른 상태 문서와 충돌 확인 |
| D042/D043 문서 | [#303](https://github.com/TheWaitForAGI/InodeFence/pull/303) | 운영 정지/재개, GO 처리량 r. W3 산식·W1 코드 일치 필요 |
| 실험 셀 실행 주 스택 | [#292](https://github.com/TheWaitForAGI/InodeFence/pull/292) → [#293](https://github.com/TheWaitForAGI/InodeFence/pull/293) → [#295](https://github.com/TheWaitForAGI/InodeFence/pull/295) → [#297](https://github.com/TheWaitForAGI/InodeFence/pull/297) | 회전/qualification-only/마감/기록 완전성. W3 검증 + 전체 회귀 + EXP-0 바이트 비교 필요 |
| 분석·통계 | [#299](https://github.com/TheWaitForAGI/InodeFence/pull/299) → [#300](https://github.com/TheWaitForAGI/InodeFence/pull/300) → [#301](https://github.com/TheWaitForAGI/InodeFence/pull/301) | #297 위 스택. #301은 #298 통합 변경 포함, 겹침 제거·실제 통합 검증 필수 |
| 출력 명세와 표/그림 | [#296](https://github.com/TheWaitForAGI/InodeFence/pull/296), [#298](https://github.com/TheWaitForAGI/InodeFence/pull/298) | #298은 #297 base, #296 명세에 의존, #299 분석 키에 의존. 실제 렌더 테스트 필요 |
| 운영점검 | [#302](https://github.com/TheWaitForAGI/InodeFence/pull/302) | #297 위, 원격 smoke만으로 통과 주장 금지 |
| G1 다중타깃 수정 | [#305](https://github.com/TheWaitForAGI/InodeFence/pull/305) | 독립 수정. 단일 타깃 우선 실험 차단과 구별 |
| 구 사전등록·다른 타깃 | #239 #264 #254 #255 #261 #260 | 일부 old stack/conflict·미실행 초안. D040 현재 캠페인과 자동 병합 금지 |
| 별도 worker pool / Track A | #233 #122 | #233 superseded 예정, #122는 별도 Track A. 이번 EXP 엔진 준비와 섞지 않음 |

> 11/08 PR 메타데이터 조회상 #292~#302는 Draft였고 #239/#264/#254/#255/#261 같은 구 스택은 일부 Draft가 아닌 열린 PR도 있다. **열림·CI green ≠ 승인.** 최신 CI를 신뢰 가능하게 직접 확인하지 못한 항목은 `UNKNOWN`으로 둔다.

## 4. 11/11 시작 시 검증할 공통 게이트

1. **실험 중립 작업 환경:** Windows WSL2 및 추가 호스트의 Git 원격 main 최신 SHA, worktree 상태, Python/Docker/이미지 ID, 디스크/메모리/호스트 상태, 기존 봉인 데이터 hash, 잔여 자원 확인. 프로젝트 루트와 Drive 백업 직접 실행 금지. 절대 `docker system prune` 금지.
2. **PR 스택 차분 검증:** 각 PR의 base/head, SHA, changed files, CI, 충돌 및 중복 패치 식별. W1은 순차 통합 테스트 브랜치만 만들고 **main 머지 금지**. 특히 #298/#299/#301의 통합 충돌과 분석기 필드 동일성 확인.
3. **회귀:** 합성 E2E, 등록 2파일 파서/스키마, D040 순열 exact/MC, D041 마감·abort 기록/재실행, D042 중단·재개, D043 GO 입력 r, 결과 표 생성기의 실제 키 검사, 전체 `make check` (실행 호스트 동결 기간 외) 및 EXP-0 이전 원자료 **바이트 불변성**.
4. **W3 독립 검증:** 통계/다중검정·검정력/우측절단/holdout·qualification-only/운영 중단·H1 재측정 영향·표 레이블 검토. 코드 작성자 확인만으로 PASS 금지.
5. **실행 동결 후보:** 두 등록 파일을 동일 `engine_sha`·k/seed·budget·image id/보관본·노출 원장 SHA로 dry-run하고, GO 판정 인자와 시각 기록을 증거로 남긴다. 결과가 나온 뒤 등록 변경 금지.
6. **승인:** W1 구현 PASS → W3 연구 검증 PASS → W1 코드·사전등록 일치 재확인 → GitHub CI/host smoke PASS → 사용자 머지/동결/실행 승인. 통과하지 못하면 어떤 항목이 언제 막히는지 기록하고 조건을 완화하지 않는다.

## 5. 세션 배분 (Claude 재개 후)

- **Orchestrator:** 위 표의 의존성·최신 SHA·W1/W3 판정 원장만 관리, 임의 GO/실행 승인 금지.
- **W1(실행·통합):** #292→#293→#295→#297→#299→#300→#298→#301 및 #302의 통합 검증과 수정; 독립 브랜치/PR. 학술 결과 표 필드 계약 W4와 교차 확인.
- **W2(H1/host 증거):** 48캠페인 호출 latency 분포, 오류 체인/host 시간 정렬, 호스트별 운영 런북, H1 재측정 후보 제시. oracle 봉인.
- **W3(연구/통계):** W1과 독립 검수자, D040/D041/D042/D043 및 재측정 판정. **결과를 먼저 보지 않는다.**
- **W4(보고서/영상/논문):** #296·#298 산출물 참조해 TBD 자리만 마련. 11/26 제출물 원고·검수표를 본실험 숫자와 분리해 작성.
- **W5(증거/동결):** 원장·이미지·raw 해시·등록 SHA·실행 SHA·중단/재개 기록 검증. W5 실제 기존 역할과 겹치면 Orchestrator가 조정.
- **ChatGPT 채팅:** GitHub PR/CI 메타데이터·독립 리뷰·보고서 구조와 학술 논리 검수 등을 직접 수행하여 Codex Plus 사용량을 보존. Codex는 대량 코드 수정/로컬 Docker 검증의 병목 작업만 맡김.

## 6. 11/11 Claude 오케스트레이터 첫 지시 (복사용)

```text
InodeFence 재개. 이 문서와 D040/D041, Draft PR #292~#307(특히 #306 H1 도구, #307 cleanup 후보), main HEAD를 실제 조회하고 상태를 재구성하라.
우선순위는 (1) H1 원인 분리·사전 결정 jobs (2) 실행 스택의 W1 통합/W3 독립 검증 (3) 등록 2파일 dry-run 및 SHA·원장·이미지 고정 준비 (4) 결과보고서/영상/논문 수치 자리이다.
이전 Claude 세션의 미커밋 변경·브랜치·검증 근거를 보존하되 작업 중복을 만들지 않는다.
지금은 main 머지, EXP-3/EXP-2 본실험 실행, 사전등록 동결, raw oracle 봉인 해제, 결과 숫자 선입력을 금지한다.
PR은 Draft로만 올리고 각 항목을 VERIFIED / PENDING / BLOCKED로 표기한다.
실행 제어·통계 코드는 W1 구현 → W3 독립 연구 검증 → W1 정합 재확인, CI 및 실제 EXP-0 바이트 회귀 순서다.
11/18 동결/EXP-3 시작 및 11/25 12:00 마감은 D040에 정해진 일정이므로 사람 승인 없이 11/11로 당기지 않는다.
```

## 7. 상태 표시 규칙

- **VERIFIED:** 재현 명령·환경·SHA·출력과 독립 근거가 연결됨.
- **PENDING:** 코드 또는 Draft PR만 존재, 해당 검증 미완료.
- **BLOCKED:** 원인 미해결/H1·결정·동결·의존 조건 불충족.
- **NOT RUN:** 계획한 검증을 실행하지 않음. 오류 0이 아니다.
- PR의 Draft/CI green 자체는 연구 검증 PASS가 아니다.

이 문서는 실행 사전등록 파일이 아니며 D040/D041/D042/D043 또는 `concurrency-scaling-v2`의 임계값을 바꾸지 않는다.
