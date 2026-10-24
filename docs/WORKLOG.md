# 자율 작업 목록 (WORKLOG)

자율 루프가 끝낸 작업을 누적한다. 사람이 이 표를 보고 브랜치를 main과 비교해 머지 여부를 정한다.
한 작업 = 한 행. 작업 브랜치의 커밋에 함께 넣는다. 실행 상세는 [LOG](LOG.md), 할 일은 [BACKLOG](BACKLOG.md).

상태: `검토대기`(검증 통과, 사람 비교 대기) / `BREAKING`(기존 테스트·판정을 깸, 머지 대기, 후속 진행 금지) / `막힘`(진행 불가, 필요한 것을 요약에 적음)

비교 명령: `git diff main...<브랜치> --stat`

| 날짜 | 브랜치명 | P0/Phase | 한 줄 요약 | main 대비 핵심 변경 | 상태 |
| --- | --- | --- | --- | --- | --- |
| 2026-10-23 | jiwoong/p0-0-autoloop-setup | 도구 세팅(P0 아님) | 자율 루프용 PreToolUse 가드 훅(R1–R8), 역할 4종(전부 claude-opus-4-8), autoloop 규칙, BACKLOG/WORKLOG; 10-24 BACKLOG를 11/2 P0 큐(1–4)로 재정렬, N01·P3는 사람 일정·승인으로 막음 | `.claude/settings.json`, `.claude/hooks/guard.py`, `.claude/agents/{orchestrator,builder,runtime,verifier}.md`, `.claude/skills/autoloop/SKILL.md`, `docs/BACKLOG.md`, `docs/WORKLOG.md`, `tests/test_claude_guard.py` | 검토대기 |
| 2026-10-24 | jiwoong/p0-1-producer-settle-skip | P0-1 (BACKLOG 4 후속 수정) | native producer의 '조용한 exit 0' 두 형태(tar.x 미settle, checkPath 드롭)를 failed 프레임/lifecycle 기록으로 바꿔 demo abort를 결과로 전환; 호스트 make demo budget 100에서 abort 0 확인 | `src/inodefence/targets/_node_effect_producer.cjs`, `tests/test_node_effect_producer_local.py`, LOG/WORKLOG/BACKLOG/STATUS | 검토대기 |
| 2026-10-24 | (PR #129·#130 브랜치에 머지 커밋 push) | BACKLOG 5 | #129/#130을 main과 머지(충돌 8/10파일 해소: main의 demo=native 유지), 머지 트리 make check 통과, GitHub MERGEABLE·CI SUCCESS. 남은 것: 사람이 #129 → #130 순으로 머지 | 코드 변경 없음(머지 커밋만) | 검토대기 |
| 2026-10-24 | (코드 변경 없음, 실행만) | BACKLOG 7 1차 | 7.5.22 P0/P1/P2 × 3 seed × budget 100 매트릭스: 1차 9회 중 5회 producer 결함 중단(.steps.jsonl로 부분 보존), 수정 producer 2차 9/9 완료·위반 0·정책 간 일관된 차이 없음(LOG 18:44). 정식 비교는 A/B/C 정의·지표 확정 후 | ~/inodefence-evidence/p3-policy-matrix-7522{,-v2}/ | 검토대기 |
