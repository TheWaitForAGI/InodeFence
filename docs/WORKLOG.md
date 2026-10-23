# 자율 작업 목록 (WORKLOG)

자율 루프가 끝낸 작업을 누적한다. 사람이 이 표를 보고 브랜치를 main과 비교해 머지 여부를 정한다.
한 작업 = 한 행. 작업 브랜치의 커밋에 함께 넣는다. 실행 상세는 [LOG](LOG.md), 할 일은 [BACKLOG](BACKLOG.md).

상태: `검토대기`(검증 통과, 사람 비교 대기) / `BREAKING`(기존 테스트·판정을 깸, 머지 대기, 후속 진행 금지) / `막힘`(진행 불가, 필요한 것을 요약에 적음)

비교 명령: `git diff main...<브랜치> --stat`

| 날짜 | 브랜치명 | P0/Phase | 한 줄 요약 | main 대비 핵심 변경 | 상태 |
| --- | --- | --- | --- | --- | --- |
| 2026-10-23 | jiwoong/autonomous-setup | 도구 세팅(P0 아님) | 자율 루프용 PreToolUse 가드 훅(R1–R8), 역할 4종(전부 claude-opus-4-8), autoloop 규칙, BACKLOG/WORKLOG | `.claude/settings.json`, `.claude/hooks/guard.py`, `.claude/agents/{orchestrator,builder,runtime,verifier}.md`, `.claude/skills/autoloop/SKILL.md`, `docs/BACKLOG.md`, `docs/WORKLOG.md`, `tests/test_claude_guard.py` | 검토대기 |
| 2026-10-23 | jiwoong/p2-a-c1-impact | P2-a | C1 일반화(EXTERNAL object 전체 비교) 영향 조사 — 임시 패치로 Dev Container 실행·되돌림, 판정 안전(additive) | docs만: `docs/LOG.md`, `docs/WORKLOG.md`, `docs/STATUS.md` (소스 변경 0, 패치 미커밋) | 검토대기 |
