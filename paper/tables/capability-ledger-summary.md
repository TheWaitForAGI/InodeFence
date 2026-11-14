# 표 L — Capability Ledger 요약 (M1·M2·M4)

§5.10의 요약표다. 능력·증거 수준의 **단일 기준은 Capability Ledger**([`../../docs/STATUS.md`](../../docs/STATUS.md))이며,
이 표는 그 행과 주장 목록([`../sections/claims-evidence-status-v1.md`](../sections/claims-evidence-status-v1.md))을
**가리키는 요약**이지 새 판정이 아니다. 증거 수준 어휘는 DESIGNED / IMPLEMENTED / TESTED / VALIDATED다.

| 마일스톤 | 능력(요지) | 증거 수준 | 주장 ID · 증거 포인터 |
| --- | --- | --- | --- |
| M1 | 실제 node-tar 루프(입력→실행→entry별 관찰→C0/C1/C2→feedback→다음 변이 선택)가 `make demo` 한 명령으로 반복 실행된다 | **TESTED** | [C-M1] §5.1 |
| M2 | 하나의 identity 오라클이 node-tar 5개 릴리스의 통제 차분에서 두 결함(CVE-2026-23745·CVE-2026-24842)을 릴리스 번호·정답 경로 없이 구분한다. 통제 재현이며 퍼저의 탐색 결과가 아니다 | **TESTED** (판정 observed, 원인 서술 inferred) | [C-M2] §5.2; [표 M2](m2-cross-release-evidence.md), [cross-release 요약](../../experiments/summaries/cross-release-identity-repro-v1.md) |
| M4 | 같은 오라클이 코드 변경 없이 다른 추출기 3개(python-tarfile·oras-go·decompress)에 어댑터로 적용된다. 퍼저 탐색의 일반성이나 효과에 대한 주장이 아니다 | **TESTED** (오라클·어댑터 수준) | [C-M4a] §5.5; [`../../tests/test_python_tarfile_generality.py`](../../tests/test_python_tarfile_generality.py) |

증거 수준 어휘(DESIGNED/IMPLEMENTED/TESTED/VALIDATED)의 정확한 정의와 전체 증거 포인터는 [`../../docs/STATUS.md`](../../docs/STATUS.md)를 따른다.
