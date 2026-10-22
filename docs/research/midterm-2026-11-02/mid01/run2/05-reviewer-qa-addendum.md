# Reviewer Q&A 추가 — Run #2

기존 [28개 Q&A](../05-reviewer-qa.md)는 Oct 21 기록으로 유지한다. 아래는 10월 22일 수정안이다.
Claim ID는 [00](00-independent-review-response.md)를 따른다. 모든 답변은 현재 근거 범위다.

## Q1. CVE-2026-23745와 CVE-2026-24842는 어떻게 다르며 7.5.3의 의미는 무엇인가?

첫 권고는 linkpath 정제 부족이며 ≤7.5.2, fixed 7.5.3입니다. 두 번째는 hardlink를 검사할 때와
생성할 때의 경로 기준점 차이이며 ≤7.5.6, fixed 7.5.7입니다. 따라서 7.5.3은 첫 문제의 수정
경계이고 모든 hardlink 문제의 수정 완료를 뜻하지 않습니다. N01 버전 경계는 첫 권고와
일치하지만 exact input의 root-cause correspondence는 사람 검토 전 확정하지 않습니다.

근거: [01 구분표](01-cve-and-evidence-boundaries.md),
[공식 23745 권고](https://github.com/isaacs/node-tar/security/advisories/GHSA-8qq5-rm4j-mr97),
[공식 24842 권고](https://github.com/isaacs/node-tar/security/advisories/GHSA-34x7-hfp2-rc4v).
R2-C02/R2-C03/R2-C17. 후속 필요: exact patch/input/runtime에 대한 human disposition.

## Q2. B0/B1/B3 비교만으로 filesystem identity/effect 피드백의 인과적 가치를 입증할 수 있는가?

그 신호만의 기여는 분리하지 못합니다. B3−B0는 retention과 parent 분포를 함께 바꾸는 정책
전체의 효과를 묻습니다. B3−B1은 full state-key 위에 violation novelty admission을 더한 효과를
묻습니다. B1에도 identity/effect 정보가 있습니다. A1/A2도 일부 field만 빼고 nlink, sentinel data,
C1/C2 fingerprints 등의 정보가 남습니다. 실제 비교도 미실행이므로 현재 효과를 주장할 수 없습니다.

근거: [03 contrast 표](03-contrast-identifiability.md),
[canonical baselines](../../../benchmarks/baseline-and-ablation-v1.md). R2-C08/R2-C09/R2-C10/R2-C16.
후속 필요: 승인된 반복 비교. Pure signal contribution은 별도 설계 과제이며 현재 비교군에 추가하지 않습니다.

## Q3. RQ1을 관찰 문제로 바꿔서 rediscovery 실패를 숨기는 것 아닌가?

Canonical RQ1은 benign-seed known-class rediscovery로 그대로 두었습니다. 발표용 RQ1은
이번 Task Contract가 요구한 관찰·판정 선행 질문이라고 표시했습니다. N01의 제한된 긍정 근거는
이 선행 질문에만 연결하며, 전체 rediscovery와 정책 효과는 NOT_RUN / NOT_EVALUATED로 남깁니다.

근거: [00 용어 대응](00-independent-review-response.md), [canonical RQs](../../../design/research-questions.md).
R2-C01/R2-C04/R2-C15. 후속 필요: 실제 search-origin 입력·lineage·3+3 replay·human class 판정.

## Q4. C1/C2가 5/5면 외부 파일 손상과 발견률 100%를 보인 것 아닌가?

동일한 고정 TAR를 affected에서 반복한 관측입니다. Search 성공률이 아닙니다. C1은 동일
dev+ino 관계, C2는 nlink 1→2와 ctime 변화이며 content digest와 size는 유지됐습니다.
Identity 공유와 metadata effect는 말할 수 있으나 내용 overwrite나 fuzzer 발견률은 말할 수 없습니다.

근거: [N04 exact-input audit](../../../diagnostics/n04-n01-independent-evidence-audit.md),
[01](01-cve-and-evidence-boundaries.md). R2-C04/R2-C05/R2-C15.
후속 필요: field별 human 검토. 관측을 늘리기 위한 post-extraction write는 추가하지 않습니다.

## Q5. #118이 admission을 검증하니 이제 N05와 pilot 연결은 끝난 것 아닌가?

#118은 target-free typed reader Unit 1 후보입니다. 실제 기록을 읽는 validator와 synthetic
regressions를 보고하지만, `freeze_track_a_execution`/reader가 이를 소비하고 원본을 보존하는
Unit 2 연결, host attempt ledger와 final accounting은 후속입니다. 실제 N05 PASS와 별도 pilot
승인도 없습니다. 따라서 기존 digest-only 실행 경로 해결이나 end-to-end 실행 가능성을 선언할 수 없습니다.

근거: [02 selected source/Unit 표](02-github-pr-delta-20261022.md),
[#118](https://github.com/TheWaitForAGI/InodeFence/pull/118). R2-C06/R2-C07/R2-C11/R2-C18.
후속 필요: 최종 통합 SHA와 실제 연결 검토; 다른 source의 PASS 암묵 재사용 금지.

## Q6. 선행연구와 조합만 다르면 신규성으로 충분한가?

충분하다고 주장하지 않습니다. 세 원문은 archive feedback, 자동 link/order 공격 workflow,
file-state/link-state 탐색의 중복을 보여줍니다. 우리는 Linux TAR corpus에서 persistent
identity/effect와 generic contract 기반 보존의 구성을 제시하지만, 그 독립 기여와 실용적 가치는
별도 문헌 검토와 실험의 대상입니다. 외부 도구와 matched comparison을 수행하지 않았습니다.

근거: [00 1차 문헌 비교](00-independent-review-response.md),
[포지셔닝](../../../design/related-work-positioning.md). R2-C13/R2-C19.
후속 필요: 문헌 범위 확장과 실제 효용 검증. ‘최초’와 외부 도구 대비 우월성은 제외합니다.

## Q7. A1/A2가 효과 없으면 identity/effect가 쓸모없다고 결론낼 수 있나?

그렇게 일반화할 수 없습니다. 현재 target ablation 결과는 없고, 향후 null result가 생겨도
A1의 identity_groups 또는 A2의 effect labels가 다른 잔존 신호 위에 추가 가치를 보이지
않았다는 좁은 해석만 가능합니다. Projected key가 실제로 달랐는지와 중복 신호의 영향을 확인해야 합니다.
A3도 reorder slot만 제거하며 insertion/duplicate의 order variation은 남습니다.

근거: [03 잔존 정보](03-contrast-identifiability.md). R2-C10/R2-C16.
후속 필요: actual key divergence, 전체 raw 및 공통 full-state 분석; 결과를 본 뒤 임의 arm 변경 금지.

## Q8. Native v2의 480회를 v3 성공 근거로 쓸 수 있나?

V2는 mandatory replacement coverage 실패로 NOT_QUALIFIED입니다. V3는 multi-operation
rebinding을 별도로 표현하고 strict reader/feedback을 합성 검증한 것입니다. Native dependency
producer는 NOT_IMPLEMENTED이며 qualification/effectiveness는 NOT_RUN입니다. V2 raw를
v3 성공으로 재분류하거나 synthetic 결과를 P-policy 효과로 바꾸지 않습니다.

근거: [v2 summary](../../../../../experiments/summaries/node-native-effect-observation-qualification-v2.md),
[v3 report](../../../diagnostics/n04-namespace-rebinding-sequence-v3-synthetic-verification.md). R2-C10/R2-C12/R2-C18.
후속 필요: 별도 versioned native producer·qualification 계약과 실제 증거.

## Q9. 4,000회 결과가 없으면 발표에 무엇을 결론으로 남기나?

현재는 구현·공학 검증, N01의 limited fixed-input 관측, native observation의 retained negative
qualification을 보고합니다. 탐색 효과는 미검증이라고 말하고 Path B에서 readiness/consumer/승인·증거
게이트와 후속 비교를 제시합니다. 미실행은 zero-hit도, 방법의 무효성도, 성공의 예상치도 아닙니다.

근거: [04 Path B](04-slide-outline-v2.md), [02](02-github-pr-delta-20261022.md).
R2-C11/R2-C12/R2-C14/R2-C20. 후속 필요: Research Lead의 scope/path 결정과 accepted packet.

## Q10. 독립 검증했다면 원본 raw와 package bytes도 직접 확인했나?

이번 Run #2는 문서·selected source·공식 권고·논문을 확인한 감사입니다. N01/native raw reader를
새로 실행하지 않았습니다. 이전 N04는 retained raw를 재검증했지만 원 npm tarball bytes의
누락을 명시했습니다. 그 earlier machine verification과 이번 감사를 합쳐 새로운 raw 독립 재현이라고
부르지 않습니다. Human correspondence도 별도입니다.

근거: [01 기술 부록](01-cve-and-evidence-boundaries.md), [README 감사 경계](README.md).
R2-C03/R2-C04/R2-C15. 후속 필요: 원본 보존 범위를 명시한 사람 검토; hash는 진위·효과의 증명이 아닙니다.
