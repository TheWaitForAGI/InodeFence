# 자율 작업 목록 (WORKLOG)

자율 루프가 끝낸 작업을 누적한다. 사람이 이 표를 보고 브랜치를 main과 비교해 머지 여부를 정한다.
한 작업 = 한 행. 작업 브랜치의 커밋에 함께 넣는다. 실행 상세는 [LOG](LOG.md), 할 일은 [BACKLOG](BACKLOG.md).

상태: `검토대기`(검증 통과, 사람 비교 대기) / `BREAKING`(기존 테스트·판정을 깸, 머지 대기, 후속 진행 금지) / `막힘`(진행 불가, 필요한 것을 요약에 적음)

비교 명령: `git diff main...<브랜치> --stat`

| 날짜 | 브랜치명 | P0/Phase | 한 줄 요약 | main 대비 핵심 변경 | 상태 |
| --- | --- | --- | --- | --- | --- |
| 2026-10-24 | jiwoong/p0-5-jsonl-partial-ci | P0-5 (BACKLOG 3) | native demo가 중단돼도 끝난 step의 루프 기록이 `<evidence>.steps.jsonl`에 남고(최종 JSON 형식 불변), CI container job이 effect producer smoke + budget 6 effect-demo를 돌림 | `src/inodefence/effect_campaign.py`(on_step), `src/inodefence/effect_demo.py`(EffectStepReporter·render_effect_step_line), `scripts/run_effect_demo.py`(step_sink), `scripts/container_controller.py`(JSONL append+fsync), `scripts/local_node_tar_smoke.sh`(JSONL 복사), `.github/workflows/ci.yml`, `tests/test_effect_demo_steps_jsonl.py`, `docs/START_HERE.md` | 검토대기 (PR CI 결과는 LOG 참고) |
| 2026-10-24 | (코드 변경 없음) | P0-1 (BACKLOG 4) | N01 native 무결성 결함 원인을 producer 출력으로 분류(`tar.x` 미settle → exit 0·빈 프레임, PathReservations 교착 추론). 필요한 것: 재현 실험(로컬 tar 7.5.22 단일 엔트리)과 producer `beforeExit` 수정에 대한 사람 승인 | LOG 2026-10-24 18:00 두 번째 줄 | 막힘 |
| 2026-10-23 | jiwoong/p0-0-autoloop-setup | 도구 세팅(P0 아님) | 자율 루프용 PreToolUse 가드 훅(R1–R8), 역할 4종(전부 claude-opus-4-8), autoloop 규칙, BACKLOG/WORKLOG; 10-24 BACKLOG를 11/2 P0 큐(1–4)로 재정렬, N01·P3는 사람 일정·승인으로 막음 | `.claude/settings.json`, `.claude/hooks/guard.py`, `.claude/agents/{orchestrator,builder,runtime,verifier}.md`, `.claude/skills/autoloop/SKILL.md`, `docs/BACKLOG.md`, `docs/WORKLOG.md`, `tests/test_claude_guard.py` | 검토대기 |
