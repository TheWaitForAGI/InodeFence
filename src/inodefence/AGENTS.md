# 엔진 영역 에이전트 규칙

root [AGENTS.md](../../AGENTS.md)와 이 규칙을 함께 따른다. 책임과 데이터 흐름은
[architecture](../../docs/research/design/architecture.md)가 기준이다.

- Issue에 지정된 현재 Layer보다 앞선 구현을 임의로 하지 않는다.
- Observer는 filesystem 사실만 기록한다. 보안 취약 여부를 판정하지 않는다.
- Oracle은 Security Contract를 판정한다. filesystem 실행 또는 mutation을 하지 않는다.
- Mutator는 generic archive transformation만 수행한다. CVE-specific recipe를 넣지 않는다.
- Targets에 target-specific invocation logic을 격리한다.
- Feedback에서 interesting state를 vulnerability와 동일시하지 않는다.
- 공통 interface 변경 시 관련 design 문서 및 테스트를 함께 갱신한다.
- 새 기능에는 테스트가 필수다. 완료 전 Dev Container에서 `make check`를 실행한다.
