# 실행 로그

append-only. 실행 시도 1건 = 1줄. 실패해도 기록한다.

형식: `YYYY-MM-DD | 누가 | 무엇을 실행 | 결과 | 산출물 경로`

- 2026-10-23 | 지웅 | 레포 리셋: AI 규칙(AGENTS/CLAUDE), P0 현황표, PR 템플릿 | 적용 | jiwoong/p0-0-ai-rules
- 2026-10-23 15:38 | 지웅 | CI container-integration 절차 수동 재현, 로컬 이름 (context=orbstack, Docker 29.8.2 — 버전은 10/23 이후 조회값) | validate·validate-node-image·validate-node-target 통과, benign-node-smoke 1 passed, validate-node-effect-producer 10 passed | ~/inodefence-evidence/inodefence-node-smoke-20261023-153848
- 2026-10-23 15:47 | 지웅 (Claude Code) | make node-tar-smoke 1/3 (context=orbstack, Docker 29.8.2) | 통과: validate 6, node-image 2, node-target 10, benign-node-smoke 1 passed, controller·volume 정리됨 | ~/inodefence-evidence/inodefence-node-smoke-20261023-154700
- 2026-10-23 15:47 | 지웅 (Claude Code) | make node-tar-smoke 2/3 (context=orbstack, Docker 29.8.2) | 통과: validate 6, node-image 2, node-target 10, benign-node-smoke 1 passed, controller·volume 정리됨 | ~/inodefence-evidence/inodefence-node-smoke-20261023-154736
- 2026-10-23 15:48 | 지웅 (Claude Code) | make node-tar-smoke 3/3 (context=orbstack, Docker 29.8.2) | 통과: validate 6, node-image 2, node-target 10, benign-node-smoke 1 passed, controller·volume 정리됨 | ~/inodefence-evidence/inodefence-node-smoke-20261023-154807
- 2026-10-23 15:48 | 지웅 (Claude Code) | make node-tar-effect-check (context=orbstack, Docker 29.8.2) | 통과: validate-node-effect-producer 10 passed, controller·volume 정리됨 | 없음 (validation 모드)
- 2026-10-23 15:49 | 지웅 (Claude Code) | 의도적 실패 주입: PYTHON=false로 local_node_tar_smoke.sh 실행 (target 미실행) | 예상대로 실패: "FAILED at step: validate", controller·volume 정리 확인 | 없음
- 2026-10-23 | 지웅 (Claude Code) | make demo (synthetic producer, P2, seed 123, budget 20) 2회 | 통과: 두 JSON 바이트 동일, 20 steps, unique_effect_keys 14, C0/C1/C2 위반 0 (synthetic fixture — native 증거 아님); --producer native는 exit 2로 차단 | $INODEFENCE_RUNTIME_ROOT/demo/effect-demo-synthetic.json
