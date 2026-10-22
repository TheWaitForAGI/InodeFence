# 독립 검토 대응과 연구 논리 수정

기준: 2026-10-22. [독립 검토](../run2-inputs/INDEPENDENT_REVIEW.md)의 조건부 승인에 대응한다.
문서 작성 완료는 사람의 발표 승인이나 연구 가설 검증 완료를 뜻하지 않는다.

## A–H 대응표

| Task / 검토 우선순위 | 반영 내용 | 검토할 산출물 |
| --- | --- | --- |
| A / P1 연구 질문 | 관찰·판정 RQ1과 정책 비교 RQ2를 주축으로 고정; rediscovery와 분리; RQ6 보조화 | 이 문서, [04](04-slide-outline-v2.md) |
| B / P0 CVE | 공식 권고문 직접 확인; 23745/24842 및 7.5.3/7.5.7 구분; human root-cause gate 유지 | [01](01-cve-and-evidence-boundaries.md) |
| C / P1 최신 GitHub | remote main, #108/#112–#118 읽기 전용 확인; 미병합 구현·설계와 실제 evidence 분리 | [02](02-github-pr-delta-20261022.md) |
| D / 신규성 | 1차 논문의 실제 탐색 단위·관찰·자동화 범위 비교; 구성 차이와 입증된 기여 분리 | 아래 문헌 비교 |
| E / P0 인과성 | B3−B0, B3−B1, A1/A2/A3, P1−P0, P2−P1의 식별 범위 명시 | [03](03-contrast-identifiability.md) |
| F / P1 발표 | 보안 문제→선행연구→RQ→구현→N01→비교→한계의 정확히 12장; 기본 Path B | [04](04-slide-outline-v2.md) |
| G / 증거 제출 | 14개 필수 필드와 담당별 요구; NOT_RUN과 실제 실패 구분 | [06](06-team-evidence-template.md) |
| H / Q&A | CVE 차이와 identity/effect 인과성 필수 질문 추가 | [05](05-reviewer-qa-addendum.md) |

## 연구 질문의 정확한 대응

[Canonical research-questions](../../../design/research-questions.md)의 RQ1은 **benign seed에서
generic mutation으로 known persistent violation을 재발견할 수 있는가**다. 이번 Task Contract의
중간발표 RQ1은 그 선행 조건인 **알려진 TAR 문제에서 filesystem object identity와 external effect를
실제로 관찰·판정할 수 있는가**다. 발표에서는 “RQ1 — 관찰·판정 선행 검증”으로 표기한다.
Canonical RQ 번호·정의는 수정하지 않으며 관찰 RQ1의 제한된 긍정 근거를 전체 rediscovery의 답으로 대체하지 않는다.

RQ2는 같은 예산에서 B0/B1/B3의 **탐색 정책 전체 또는 특정 admission 규칙**이 만드는 차이를 묻는다.
“Identity feedback이 우수하다”라는 결론을 질문 자체에 넣지 않는다. N01은 관찰 가능성의
positive control이며 B0/B1/B3 탐색 효과의 결과가 아니다. RQ6는 native intermediate observation이
먼저 qualify되어야 하는 독립 확장이다. 이 우선순위는 [Research Contract](../../../design/research-contract-v1.md)의
검증 단계와 함께 해석한다.

| 질문 / 가설 | 현재 근거 | 아직 필요한 증거 |
| --- | --- | --- |
| 발표 RQ1: persistent identity/effect 관찰·판정 | N01 보고서의 C1 및 metadata-only C2, earlier machine readers | human correspondence; 더 넓은 case/target 범위는 별도 qualification |
| Canonical RQ1: known-class rediscovery | 논리적 constructive reachability 및 search infrastructure TESTED | 실제 benign-seed campaign lineage, exact candidate 3+3 replay, human class 판정 |
| RQ2 / H1: 고정 budget에서 정책이 탐색을 바꾸는가 | B0/B1/B3 구현·engineering tests | qualified/승인된 실제 비교, 모든 상태·분모·반복·비용; 효과 방향/크기 현재 미정 |
| RQ6 / H3·H4: transition retention 및 adaptive scheduler 이득 | generic synthetic model/search/scheduler, native negative qualification | version-bound native producer qualification과 별도 P1−P0/P2−P1 비교 |

## 선행연구: 1차 자료에 근거한 비교

확인일: 2026-10-22. 아래는 세 논문의 해당 절에 대한 범위 비교이며 포괄적 novelty search가 아니다.
‘차이’ 열은 논문과 InodeFence 설계를 대조한 **편집자의 해석**이다. 원문에서 특정 기법을
찾지 못했다는 사실을 모든 선행연구에 대한 부재 증명으로 사용하지 않는다.

| 연구 / 1차 자료 위치 | 이미 수행한 작업 | InodeFence와 비교할 단위·남은 부담 |
| --- | --- | --- |
| ZIPDiff, *My ZIP isn't your ZIP* (2025), §§4.1–4.4, Algorithms 1–3; 인쇄 pp.434–435 / PDF pp.5–6 | ZIP 구조·byte mutation, parser 추출 출력 비교, interesting corpus 보존, UCB/softmax mutation 선택 | Parser 간 해석 차이와 persistent C0/C1/C2 목적은 다르다. Archive feedback·retention·adaptive mutation 일반은 신규 기여가 아니다. [원문](https://www.usenix.org/system/files/usenixsecurity25-you.pdf) |
| Wormholes (2026), §§5.1–5.6, 특히 §5.5; 인쇄 pp.5218–5223 / PDF pp.8–13 | Symlink 해석·composition·생성 순서, link를 통한 write 전략 및 extractor 반응에 따라 전략을 선택하는 자동 archive workflow | 수동 PoC 모음으로 축소하지 않는다. Generic mutation+security-state retention의 효용은 다른 검증 질문이다. Link/order/outside-root effect 자체는 기여에서 제외한다. [원문](https://www.usenix.org/system/files/usenixsecurity26-liu-yongheng.pdf) |
| LinkZard, *Pig in a Poke* (2025), §§4.2.2–4.3.2, Appendix C Table 6; PDF pp.8–9,20 | Windows state-query feedback 기반 file-state mutation, operation graph/sequence와 sink 분석; hardlink 및 link count 정보 포함 | TAR archive corpus와 Windows operation model의 차이를 밝힌다. Filesystem-state fuzzing이나 link-state 관찰 자체의 최초성을 주장할 수 없다. [저자 공개 원문](https://lfysec.github.io/paper/linkzard-security25.pdf) |

Wormholes §5.6은 저자들이 재현한 ZIPDiff가 해당 데이터의 symlink case를 검출하지 못했다고
보고한다. 이것은 그 비교의 범위이며, ZIPDiff의 보편적 불가능성이나 InodeFence의 성공 근거가 아니다.
[Wormholes §5.6](https://www.usenix.org/system/files/usenixsecurity26-liu-yongheng.pdf)

| 구분 | 이번 발표에서 말할 내용 | 근거 / 미검증 경계 |
| --- | --- | --- |
| 이미 알려진 작업 | archive fuzzing/feedback, file-state 탐색, hardlink/symlink/order 공격 | 위 세 원문 및 [기존 포지셔닝](../../../design/related-work-positioning.md) |
| InodeFence가 구성한 방식 | Linux TAR-entry mutation → persistent identity/effect 관찰 → generic C0/C1/C2 → normalized key/fingerprint 기반 보존 | 설계상의 구성 차이. 문헌상 독창성이나 탐색 효용의 입증은 아님 |
| 구현·검증한 것 | final-state pipeline/search/oracle engineering checks; N01 fixed-input machine correspondence; v3 generic synthetic representation | [STATUS](../../../../STATUS.md), [N02](../../../diagnostics/n02-autonomous-integration-and-qualification.md), [v3](../../../diagnostics/n04-namespace-rebinding-sequence-v3-synthetic-verification.md) |
| 아직 실험으로 증명하지 못한 것 | stochastic rediscovery, B/A 정책 효과, native P-policy 효과, 다른 extractor family 일반성, 외부 도구 대비 우월성 | 실제 비교·qualification이 없는 질문. 결과를 추정하지 않음 |

## Run #2 Claim Register

기존 [C01–C39](../01-claim-register.md)는 Oct 21 스냅샷이다. 아래 R2-Cxx는 이번 발표 수정안의
별도 참조 ID다. ALLOW는 정확한 한정 문장만 허용, QUALIFY는 조건 병기, PROHIBIT는 현재 발표에서 금지다.
어느 행도 RQ1 rediscovery/RQ2/RQ6 효과를 EXPERIMENTALLY VALIDATED로 선언하지 않는다.

| Claim ID | 발표 문장 / 판정 | 증거와 범위 | 기존 ID 대응 |
| --- | --- | --- | --- |
| R2-C01 | ALLOW: 발표 RQ1은 관찰·판정의 선행 검증, RQ2는 같은 budget의 정책 비교, RQ6는 확장이다. | Run #2 계약; 위 canonical 대응표. 새 결과 선언 아님 | C15 보정 |
| R2-C02 | ALLOW: 23745는 ≤7.5.2 / 7.5.3, 24842는 ≤7.5.6 / 7.5.7의 서로 다른 공식 권고다. | [01 공식 출처](01-cve-and-evidence-boundaries.md); 권고문 정보 | C36 제한 강화 |
| R2-C03 | QUALIFY: N01 버전 경계는 23745와 일치하지만 exact root cause는 human review 대기다. | [01](01-cve-and-evidence-boundaries.md); 버전 일치와 원인 판정 구분 | C09/C16 |
| R2-C04 | ALLOW: N01 보존 보고서는 동일 TAR에서 7.5.2 C1/C2 5/5, 7.5.3 C1/C2 0/5 및 reject 5/5를 기록한다. | [N02](../../../diagnostics/n02-autonomous-integration-and-qualification.md), [N04](../../../diagnostics/n04-n01-independent-evidence-audit.md); 10초, 고정 입력, C2 metadata-only | C07/C08 |
| R2-C05 | ALLOW: C0/C1/C2는 관찰 sandbox의 persistent namespace, AFTER lstat identity, 지정 sentinel 전후 effect를 각각 판정한다. | [Security Contracts](../../../design/security-contracts.md); transient/직접 사용/전체 host 안전은 범위 밖 | C01–C03/C36 |
| R2-C06 | ALLOW: remote main은 M이며 요청 PR 8개는 이번 확인에서 모두 open/unmerged다. | [02 exact-head 표](02-github-pr-delta-20261022.md); 시점 한정 | C11/C19 갱신 |
| R2-C07 | QUALIFY: #118은 target-free typed admission reader 후보이며 synthetic TESTED를 보고한다. | [02](02-github-pr-delta-20261022.md); 실제 N05 PASS·launch 연결·pilot 결과가 아님 | C11/C29 보강 |
| R2-C08 | ALLOW: B0는 unretained multi-step random walk, B1은 full state-key-only, B3는 state-or-violation admission이다. | [03](03-contrast-identifiability.md), canonical baseline; B1 path-only 아님 | C04–C06/C30 |
| R2-C09 | ALLOW: B3−B0는 retention/parent 분포를 포함한 정책 전체 효과, B3−B1은 violation novelty admission의 추가 효과를 묻는다. | [03](03-contrast-identifiability.md); 실제 효과 값은 NOT_RUN | C04/C18 |
| R2-C10 | QUALIFY: A1/A2/A3와 P1−P0/P2−P1은 각각 좁고 version-bound한 질문이다. | [03](03-contrast-identifiability.md); 잔존 정보·native qualification 조건 병기 | C18/C20 |
| R2-C11 | ALLOW: N05와 4,000회 pilot은 검토 기록상 NOT_AUTHORIZED / NOT_RUN이다. | [02](02-github-pr-delta-20261022.md); 4,000은 제안 총량 | C10–C12/C28/C29 |
| R2-C12 | ALLOW: native v1 BLOCKED, v2 480-run NOT_QUALIFIED, v3 generic synthetic TESTED/native producer NOT_IMPLEMENTED다. | [STATUS](../../../../STATUS.md), [v2 summary](../../../../../experiments/summaries/node-native-effect-observation-qualification-v2.md), [v3 report](../../../diagnostics/n04-namespace-rebinding-sequence-v3-synthetic-verification.md) | C13/C14/C32 |
| R2-C13 | QUALIFY: generic TAR mutation과 identity/effect feedback의 결합이 유용한지는 검증할 가설이다. | 위 1차 문헌 비교 및 [Research Contract](../../../design/research-contract-v1.md); 최초성·효과 미검증 | C21/C24 |
| R2-C14 | QUALIFY: Path A는 향후 실제 승인·검증·사람 검토를 통과한 pilot에만 사용한다. | [04 경로 규칙](04-slide-outline-v2.md); 지금은 B, 빈 결과칸을 값으로 채우지 않음 | C22 |
| R2-C15 | PROHIBIT: N01은 fuzzer rediscovery, external content overwrite, 또는 final human qualification 완료다. | 고정 입력·내용 불변·human pending과 충돌 | C25–C27 |
| R2-C16 | PROHIBIT: B0/B1/B3만으로 pure identity/effect feedback의 인과적 가치·우월성을 입증했다. | 식별 불가 및 실제 비교 NOT_RUN | C30/C31 |
| R2-C17 | PROHIBIT: 7.5.3은 모든 hardlink 문제를 수정했고 no-hit는 안전을 증명한다. | 두 번째 권고 및 snapshot 한계와 충돌 | C36 |
| R2-C18 | PROHIBIT: CI/merge/synthetic PASS가 N05 PASS·pilot 완료·native effectiveness를 뜻한다. | [02](02-github-pr-delta-20261022.md); 서로 다른 evidence 층위 | C28/C29/C32/C33 |
| R2-C19 | PROHIBIT: 최초 state-guided archive fuzzer, 기존 연구는 link/state/order를 안 봄, 또는 외부 도구보다 우수함. | 1차 문헌 중복과 matched comparison 부재 | C34/C35 |
| R2-C20 | PROHIBIT: state/key/fingerprint 수는 취약점 수이며 NOT_RUN/invalid는 정상 zero-hit다. | [03 지표](03-contrast-identifiability.md), canonical evaluation | C37/C38/C39 |

발표 논리: **실제 보안 문제 → 이미 알려진 연구 → 관찰·탐색의 미검증 질문 → 구현된 측정 방법 →
N01의 제한된 관측 → 식별 가능한 비교 → 현재 차단 상태와 한계 → 후속 검증**.
기존 문서의 번호·문장 수정은 하지 않으며 [04](04-slide-outline-v2.md)를 발표용 수정안으로 검토한다.
