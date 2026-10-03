# InodeFence Codex Skills

이 디렉터리는 InodeFence 저장소에서 반복되는 개발·검증 작업을 위한 repo-local Codex skill을 보관한다.

이 skill들은 `AGENTS.md`, `docs/START_HERE.md`, `docs/STATUS.md`, 관련 design 문서를 대체하지 않는다.
항상 저장소의 최신 문서와 Task Contract를 source of truth로 사용한다.

## Skill 선택

| Skill | 언제 사용하는가 |
| --- | --- |
| `inodefence-implementation` | Issue/Task Contract를 실제 코드 변경으로 구현할 때 |
| `inodefence-security-contract-review` | Observer/Oracle/StateSignature/보안 판정 로직이 C0~C4 의미를 보존하는지 검토할 때 |
| `inodefence-experiment-validation` | 실험 결과를 재현 가능하고 논문 근거로 사용할 수 있는지 검증할 때 |
| `inodefence-pr-review` | PR merge 전 architecture, research contract, tests, scope를 종합 검토할 때 |

## 공통 원칙

1. 먼저 `docs/START_HERE.md`, `docs/STATUS.md`, `AGENTS.md`를 읽는다.
2. 작업과 직접 관련된 문서만 추가로 읽는다.
3. 사용자 또는 Issue가 정한 Task Contract가 있으면 그것을 우선한다.
4. 현재 Layer를 넘어서는 기능을 임의로 추가하지 않는다.
5. CVE-specific logic을 generic core에 섞지 않는다.
6. 관찰된 사실, 추론, 가설, 논문 주장을 구분한다.
7. 완료를 주장하기 전에 가능한 범위에서 `make check`와 관련 검증을 실행하고 실제 결과를 기록한다.
