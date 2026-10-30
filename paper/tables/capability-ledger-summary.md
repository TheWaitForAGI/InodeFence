# 표 L — Capability Ledger 요약 (M1–M4)

§5.5의 요약표다. 능력·증거 수준의 **단일 기준은 Capability Ledger**([`../../docs/STATUS.md`](../../docs/STATUS.md))이며,
이 표는 그 행을 **가리키는 요약**이지 새 판정이 아니다. 증거 수준 어휘는 DESIGNED / IMPLEMENTED /
TESTED / VALIDATED다.

| 마일스톤 | 능력(요지) | 증거 수준 | 증거 포인터(§) |
| --- | --- | --- | --- |
| M1 | 실제 node-tar 루프(입력→실행→entry별 관찰→C0/C1/C2→feedback→다음 mutation) | **TESTED** | §5.1; `make demo` 호스트, budget 20/100 |
| M2 | 하나의 generic identity oracle이 두 root-cause(CVE-2026-23745·CVE-2026-24842)를 릴리스 id·정답 경로 하드코딩 없이 통제 차분으로 포착 | **TESTED** (방어 가능, observed) | §5.2; [표 M2](m2-cross-release-evidence.md), [cross-release 요약](../../experiments/summaries/cross-release-identity-repro-v1.md) |
| M3 | object-identity 관찰이 자율 경계위반 발견을 인과적으로 가능케 함 (없으면 도달 불가; blind 발견 아님·seed-rare) | **메커니즘 인과 입증** (rate 우위 미판정) | §5.3; [표 M3](m3-blind-ablation.md), [자력발견 요약](../../experiments/summaries/node-self-discovery-mechanism-v1.md) |
| M3 (보조) | 상태-인지 feedback의 rate 우위(무작위보다 빠르다/많다) | **미판정 / PENDING** | §5.3.3; powered matched A1 vs A3full 진행 중 |
| M4 | 동일 generic C0/C1/C2 oracle(코드 불변)이 3개 독립 extractor(python-tarfile·oras-go·decompress)에 adapter 수준 적용 | **일부 TESTED** (oracle/adapter 수준) | §5.4.1; [`../../tests/test_python_tarfile_generality.py`](../../tests/test_python_tarfile_generality.py) |
| M4 (자력발견) | 2번째 extractor(decompress) 퍼저 자력 발견 | **right-censored 음성** (미판정) | §5.4.2; budget 200×seed 11×2 arm, 양 arm 0 C1/C2 |
| M4 (보조) | decompress 자력발견 powered 판정 | **PENDING** | §5.4.3; 대예산 독립 반복 진행 중 |

주: M3의 "메커니즘 인과 입증"은 Ledger가 쓰는 표현("입증(인과·메커니즘; 자율 트리거는 seed-rare)")을
요약한 것이다. 증거 수준 어휘(DESIGNED/IMPLEMENTED/TESTED/VALIDATED)의 정확한 정의와 전체 증거
포인터는 [`../../docs/STATUS.md`](../../docs/STATUS.md)를 따른다.
