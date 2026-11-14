# 표 L — Capability Ledger 요약 (M1·M2·M4)

§5.5의 요약표다. 능력·증거 수준의 **단일 기준은 Capability Ledger**([`../../docs/STATUS.md`](../../docs/STATUS.md))이며,
이 표는 그 행을 **가리키는 요약**이지 새 판정이 아니다. 증거 수준 어휘는 DESIGNED / IMPLEMENTED /
TESTED / VALIDATED다.

| 마일스톤 | 능력(요지) | 증거 수준 | 증거 포인터(§) |
| --- | --- | --- | --- |
| M1 | 실제 node-tar 루프(입력→실행→entry별 관찰→C0/C1/C2→feedback→다음 mutation) | **TESTED** | §5.1; `make demo` 호스트, budget 20/100 |
| M2 | 하나의 generic identity oracle이 두 root-cause(CVE-2026-23745·CVE-2026-24842)를 릴리스 id·정답 경로 하드코딩 없이 통제 차분으로 포착 | **TESTED** (방어 가능, observed) | §5.2; [표 M2](m2-cross-release-evidence.md), [cross-release 요약](../../experiments/summaries/cross-release-identity-repro-v1.md) |
| M4 | 동일 generic C0/C1/C2 oracle(코드 불변)이 3개 독립 extractor(python-tarfile·oras-go·decompress)에 adapter 수준 적용 | **일부 TESTED** (oracle/adapter 수준) | §5.4.1; [`../../tests/test_python_tarfile_generality.py`](../../tests/test_python_tarfile_generality.py) |

증거 수준 어휘(DESIGNED/IMPLEMENTED/TESTED/VALIDATED)의 정확한 정의와 전체 증거 포인터는 [`../../docs/STATUS.md`](../../docs/STATUS.md)를 따른다.
