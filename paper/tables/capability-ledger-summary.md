# 표 L — Capability Ledger 요약 (M1–M4)

§5.5의 요약표다. 능력·증거 수준의 **단일 기준은 Capability Ledger**([`../../docs/STATUS.md`](../../docs/STATUS.md))이며,
이 표는 그 행을 **가리키는 요약**이지 새 판정이 아니다. 증거 수준 어휘는 DESIGNED / IMPLEMENTED /
TESTED / VALIDATED다.

| 마일스톤 | 능력(요지) | 증거 수준 | 증거 포인터(§) |
| --- | --- | --- | --- |
| M1 | 실제 node-tar 루프(입력→실행→entry별 관찰→C0/C1/C2→feedback→다음 mutation) | **TESTED** | §5.1; `make demo` 호스트, budget 20/100 |
| M2 | 하나의 generic identity oracle이 두 root-cause(CVE-2026-23745·CVE-2026-24842)를 릴리스 id·정답 경로 하드코딩 없이 통제 차분으로 포착 | **TESTED** (방어 가능, observed) | §5.2; [표 M2](m2-cross-release-evidence.md), [cross-release 요약](../../experiments/summaries/cross-release-identity-repro-v1.md) |
| M3 | 외부 객체 이름을 어휘에 획득한 조건에서만 자율 경계위반이 관찰됨 (이름 없으면 도달 불가; blind 발견 아님; 멀티-seed s11+s101) *(구: "object-identity 관찰이 발견을 인과적으로 가능케 함", 2026-11-03 정정)* | **이름 획득 조건의 관찰(피드백 인과 미입증)·멀티-seed** (rate CI 미분리; retention·effect 피드백 기여는 R/D/S-u로 미분리) *(구: "메커니즘 인과 입증·멀티-seed", 2026-11-03 정정)* | §5.3; [표 M3](m3-blind-ablation.md), [자력발견 요약](../../experiments/summaries/node-self-discovery-mechanism-v1.md), [powered verdict](../../experiments/summaries/m3-powered-matched-verdict-v1.md) |
| M3 (보조) | 상태-인지 feedback의 rate 우위(무작위보다 빠르다/많다) | **사전등록 판정: CI 미분리**(검정력 부족) | §5.3.3; powered matched A1 0/12 vs A3full 1/10(s101), Wilson [0,0.242] vs [0.018,0.404] 겹침 |
| M4 | 동일 generic C0/C1/C2 oracle(코드 불변)이 3개 독립 extractor(python-tarfile·oras-go·decompress)에 adapter 수준 적용 | **일부 TESTED** (oracle/adapter 수준) | §5.4.1; [`../../tests/test_python_tarfile_generality.py`](../../tests/test_python_tarfile_generality.py) |
| M4 (자력발견, 2번째) | 2번째 extractor(decompress) 퍼저 자력 발견 | **사후 분석 기준 음성(사전등록 판정 아님)** (통합 판정) | §5.4.3; 맥+윈도우 통합 C1/C2 0/28 Wilson≤0.121(등록 hit=C0 포함 discovered_violation, C1/C2 분리·0/28은 사후 축), C0 12/14 자력도달·arm 우위 없음 |
| M4 (자력발견, 3번째) | 3번째 extractor(oras-go) 퍼저 자력 발견 | **약한 음성** | §5.4.4; budget 200×seed 11×2 arm, 양 arm 0/1 Wilson[0,0.793] |

주: M3의 "이름 획득 조건의 관찰(피드백 인과 미입증)"은 Ledger가 쓰는 표현("이름 획득 조건의 관찰(피드백 인과 미입증); 자율 트리거는 seed-rare")을
요약한 것이다(구 표현 "입증(인과·메커니즘)"은 2026-11-03 정정). 증거 수준 어휘(DESIGNED/IMPLEMENTED/TESTED/VALIDATED)의 정확한 정의와 전체 증거
포인터는 [`../../docs/STATUS.md`](../../docs/STATUS.md)를 따른다.

(2026-11-03 정정: 이 어휘 제거 대조는 피드백이 아니라 **어휘**를 통제한 실험이다. 입증된 것은 "외부 객체 이름의 관찰(어휘 획득)이 자율 C1의 필요조건"이지 (st_dev, st_ino) retention·스케줄링 피드백의 기여가 아니며, 그 기여는 어휘를 맞춘 R/D/S-u 비교(research-questions v2 H-A)로 미분리다. 수치·서술은 보존한다. 상세: §5.3.2 정정.)
