---
name: autoloop
description: InodeFence 자율 작업 루프 규칙. docs/BACKLOG.md 맨 위부터 작업 1개씩 브랜치에서 진행하고, make check 통과 후 커밋·LOG·WORKLOG 기록까지 하고, PR·CI·verifier 통과 후 스스로 squash 머지한 뒤 다음 작업으로 간다. "자율로 진행", "backlog 이어서", "autoloop" 요청 시 사용.
---

# autoloop — 자율 루프 규칙서

작업 선택·구현·검증·기록·PR·**머지까지** 이 규칙대로 자율로 진행한다(D035). 사람에게 돌리는 것은
안전경계·연구 불변식에 걸리는 결정만이다: `BREAKING`(5절 4항), 가드·격리·allowlist 설정, FROZEN 변경, 외부 공개.
`AGENTS.md`, `docs/MIDTERM_GOALS.md`의 규칙이 이 문서보다 우선한다. 이 문서는 그 위에 자율 실행 절차를 더한다.

기계적 안전장치: `.claude/hooks/guard.py` (`.claude/settings.json` PreToolUse, 서브에이전트 포함).
훅이 막으면 **우회하지 않는다.** 아래 "막힘 처리"로 간다. 훅·allowlist·격리 설정 수정은 사람만 한다.

## 0. 역할 (멀티 에이전트)

| 역할 | 정의 | 모델 | 하는 일 | 가드 |
| --- | --- | --- | --- | --- |
| 지휘관 | `.claude/agents/orchestrator.md` | claude-opus-4-8 | BACKLOG에서 작업 선택, 환경 판단, 위임, 보고 수신 | R6: 메타데이터 문서·`git status/branch/log/diff --stat`만. 소스·diff·실행 출력 접근 차단, 작업자 3종 외 위임·모델 override 차단 |
| builder | `.claude/agents/builder.md` | claude-opus-4-8 | 코드 작성·수정, `make check`, 커밋, 기록, PR 생성·머지 | R1–R5 |
| runtime | `.claude/agents/runtime.md` | claude-opus-4-8 | docker 실제 실행(호스트) | R1–R5, R7: 기록 문서만 쓰기 |
| verifier | `.claude/agents/verifier.md` | claude-opus-4-8 | 브랜치 검토, PASS/ISSUES | R1–R5, R8: 읽기 전용 |

- 시작: `claude --agent orchestrator` (메인 세션이 지휘관 정의와 모델로 뜬다). 이 플래그 없이 시작한 세션은 지휘관 제한(R6)이 걸리지 않는 일반 세션이다.
- 작업자 보고는 메타데이터 형식(`orchestrator.md`의 "작업자 보고 형식")만 쓴다. 코드·diff·payload·취약점 세부는 커밋과 LOG에 남기고 보고에 넣지 않는다. 이 부분은 지시로만 지켜지고 훅으로 강제되지 않는다.
- 세션 하나는 한 환경(Dev Container 또는 호스트)에서만 돈다. 작업자도 같은 환경이다.
- 지휘관을 fable로 두지 않는 이유(observed, 2026-10-23): 이 저장소에서 `--agent orchestrator`를 fable로 띄우면 첫 요청에서 `model_refusal_fallback`(category cyber, scope session)이 나고 세션 전체가 claude-opus-4-8로 넘어갔다. 도구 호출 전이라 자동 로드되는 프로젝트 문맥이 원인으로 추정(inferred)되며, 메타데이터 제한으로는 피할 수 없다.

## 1. 루프

```text
BACKLOG 맨 위의 "대기" 항목 1개 선택
  → 분류 밝히기 (어느 마일스톤 M2~M4 / 상시 태스크인지, 아니면 해당 없음+이유)
  → 게이트 확인 (선행 항목 결과, 차단 조건)
  → main에서 새 브랜치 1개
  → 환경 선택 후 구현·실행
  → 검증 (make check 등)
  → 브랜치에 커밋 (+ 브랜치 push)
  → docs/LOG.md 한 줄 + docs/WORKLOG.md 한 행 + BACKLOG 항목 상태 갱신
  → PR 생성 → CI 통과 + verifier PASS 확인 → squash 머지 (BREAKING·가드·FROZEN·외부 공개는 사람)
  → 다음 항목
```

- **한 번에 작업 1개. 브랜치 1개 = 작업 1개.** 다른 미머지 작업 브랜치 위에 브랜치를 쌓지 않는다(스택 금지). 항상 최신 `main`에서 분기한다.
- 앞 항목의 결과가 필요한데 그 브랜치가 아직 머지되지 않았으면, 그 위에 쌓지 말고 해당 항목을 "대기(머지 필요)"로 두고 다음 항목으로 간다.
- **순서대로 진행한다.** BACKLOG 맨 위부터. 게이트가 막힌 항목은 건너뛰되 건너뛴 이유를 LOG에 남긴다.
- 진행할 수 있는 안전한 항목이 더 없으면 **대기**한다. 일을 만들어 내지 않는다(새 감사 문서, 범위 밖 refactor 금지).
- **PR을 만들고 스스로 머지한다.** 기록 커밋까지 끝난 브랜치로 `gh pr create --base main`(본문은 `--body-file`;
  첫 항목은 AGENTS.md PR 규칙의 질문에 대한 답) → CI 두 job 통과(`gh pr checks <n> --watch`) + verifier `PASS`
  → `gh pr merge <n> --squash --delete-branch`. **main 직접 push는 여전히 하지 않는다**(가드 R2).
  머지하지 않고 PR만 열어 두는 것: `BREAKING`(5절 4항), 가드·격리·allowlist 설정 변경, FROZEN 변경, 외부 공개가
  걸린 변경. 이건 WORKLOG `NEXT`/요약에 "사람 결정"으로 적고 다음 항목으로 간다.

## 2. 작업 시작 시 밝힐 것

브랜치를 만들기 전에 LOG/커밋 메시지에 남길 수 있게 다음을 정한다.

1. 분류: BACKLOG의 어느 마일스톤(M2~M4)·상시 태스크인지.
   둘 다 아니면 진행하지 않고 그 이유를 LOG에 기록한다.
2. 완료 조건: BACKLOG 항목에 적힌 것을 그대로 쓴다. 바꾸지 않는다.
3. "이 작업이 끝나면 무엇을 실제로 실행/검증할 수 있게 되는가" 한 줄.

브랜치 이름: `jiwoong/<p0-N|pN>-<요약>` (예: `jiwoong/p2-c1-impact`).

## 3. 환경 선택

| 필요한 것 | 환경 | 근거 |
| --- | --- | --- |
| docker: `make demo`(별칭 `make demo-native`), `make node-tar-smoke`, `make node-tar-effect-check`, node-tar 실제 실행, native 캠페인 | **호스트 터미널** (macOS + OrbStack) | Dev Container에는 `docker`가 없다(`DEVCONTAINER=true`, `which docker` 없음). LOG의 native 실행은 모두 `context=orbstack` |
| `make check`, `make demo-synthetic`(synthetic, node-tar 아님), `make probe`, `python -m scripts.oracle_fixture_check`, 코드 작업, pytest | **Dev Container** | 기준 환경 Ubuntu 24.04 + Python 3.12, `$INODEFENCE_RUNTIME_ROOT=/var/lib/inodefence` |

- 지금 세션이 어느 쪽인지 먼저 확인한다: `echo $DEVCONTAINER; command -v docker`.
- 필요한 환경이 아니면 실행을 흉내 내지 않는다. "호스트 실행 필요 — 미실행"으로 LOG에 남기고, 그 실행이 필요 없는 부분만 진행하거나 다음 항목으로 간다.
- native 실행은 **안전경계 안에서 자율로 한다**: 고정 node-tar 버전, 실행 예산 상한, disposable sandbox + sentinel, 격리 완화 플래그 금지. 이 경계 안의 실행(재현 probe, historical 캠페인 포함)은 따로 사람 승인을 기다리지 않는다. 결과는 `demo run`으로 라벨링하고 qualification으로 부르지 않는다. 경계를 벗어나는 일(외부 공개, 격리 완화, 민감 파일)만 멈추고 사람에게 돌린다.

## 4. 완료 처리

1. 검증: Dev Container에서 `make check` 통과. 코드 변경이 없는 작업은 적용 가능한 검사(`make docs-check` 등)를 돌리고 무엇을 돌렸는지 적는다.
   실패하면 커밋하지 않는다. 고쳐서 통과시키되, 테스트를 지우거나 약화해서 통과시키지 않는다. 못 고치면 "막힘 처리".
2. 브랜치에 커밋하고 브랜치를 push한다(`git push -u origin <branch>`). main에는 push하지 않는다.
3. `docs/LOG.md`에 한 줄 추가: `YYYY-MM-DD HH:MM | 지웅 (Claude Code, autoloop) | 무엇을 실행 | 결과 | 산출물 경로`.
4. `docs/WORKLOG.md` 표에 한 행 추가(양식은 그 파일 참고). 상태는 `검토대기` / `BREAKING` / `막힘` 중 하나.
5. `docs/BACKLOG.md`에서 해당 항목 상태를 갱신한다(`완료(브랜치명)` / `막힘` / `BREAKING`).
6. P0 현황이 바뀌었으면 `docs/STATUS.md` 표를 갱신한다.
7. PR을 만들고 머지한다(1절). CI가 실패하면 같은 브랜치에서 고쳐 다시 push한다. 테스트를 지우거나 약화해서
   통과시키지 않는다. 못 고치면 PR을 draft로 돌리고 "막힘 처리". 머지 여부의 기준은 PR 상태다
   (`gh pr view <n> --json state,mergedAt`); WORKLOG 행은 머지 뒤에 고치지 않는다(main 직접 push 금지).

LOG·WORKLOG·BACKLOG 기록은 작업 브랜치의 커밋에 함께 넣는다.

## 5. 절대 규칙 (위반하게 되면 멈추고 기록, 우회 금지)

1. **막히면 완화하지 않는다.** 격리·allowlist·빌드·테스트 실패, 훅 차단, 권한 거부가 나면 설정을 느슨하게 하거나 다른 경로로 돌아가지 않는다. 멈추고 LOG에 원인·명령·에러 첫 줄을 남기고, WORKLOG에 `막힘`으로 적고, 다음 항목으로 간다.
2. **결과를 꾸미지 않는다.** 안 된 건 안 됐다고 적는다. 일부만 됐으면 된 범위만 적는다. reconstruct한 고정 입력, synthetic producer, fixture 결과로 실제 실험(native node-tar) 결과를 대체하지 않는다. synthetic이면 synthetic이라고 쓴다.
3. **관찰과 추론을 구분한다.** 기록마다 `observed`(실행 출력·파일로 확인한 것)와 `inferred`/`derived`(그로부터 추론·재구성한 것)를 나눈다. 증거 경로가 없는 결론은 "추론"으로 명시한다.
4. **oracle 판정 로직을 바꾸는 작업**(`src/inodefence/oracle/`, C0/C1/C2 의미, Security Contract):
   - 먼저 영향 조사: N01 재현 경로, 기존 fixture(`tests/test_oracle_fixtures.py`, `scripts/oracle_fixture_check.py`), 전체 테스트가 깨지는지 실행해서 확인한다.
   - 깨뜨리면 기존 판정은 그대로 두고 **추가하는 방식**(새 contract id/새 evidence 필드/새 함수)으로만 바꾼다.
   - 그래도 기존 테스트를 깨는 변경은 WORKLOG 상태를 `BREAKING`으로 두고, 커밋 메시지와 LOG에 "BREAKING"을 명시하고, **그 위에 후속 작업을 진행하지 않는다.** 사람 판단 전까지 머지 대기다. 자동 머지 경로에 올리지 않는다.
   - 영향 조사 결과가 "깨뜨린다"이면 구현 항목으로 넘어가지 않는다. 조사 결과만 기록하고 다음 안전한 항목으로 간다.
5. **바꾸지 않는 것:** FROZEN 해시와 frozen 입력/타깃(`FROZEN_*`, 예: `src/inodefence/evaluation/n01.py`), 기존 qualification 모드와 그 계약, `docs/research/` 아래 동결된 보고서. 새 동작이 필요하면 새 모드/새 이름으로 추가한다.
6. **문서:** 새 audit/readiness/handoff/qualification/preserve 문서를 만들지 않는다. 기록은 STATUS 갱신과 LOG 한 줄로 한다.
7. **안전:** disposable sandbox와 sentinel만 사용한다. 실제 민감 파일을 대상으로 쓰지 않는다. `--privileged`, `--cap-add`, `--security-opt` 같은 격리 완화는 하지 않는다.

## 6. 막힘 처리

```text
LOG:     YYYY-MM-DD HH:MM | 지웅 (Claude Code, autoloop) | <명령/작업> | 막힘: <원인 한 줄> (<에러 첫 줄>) | <증거 경로 또는 없음>
WORKLOG: 상태 = 막힘, 요약에 무엇이 필요한지(사람 결정/호스트 실행/권한)
BACKLOG: 항목 상태 = 막힘(<날짜>, <한 줄 이유>)
```

같은 항목을 다른 방법으로 우회해서 다시 시도하지 않는다. 다음 항목으로 넘어간다.
