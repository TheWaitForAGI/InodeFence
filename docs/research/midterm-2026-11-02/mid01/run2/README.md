# MID-01 Run #2 — 연구 서사 수정안

작성일: **2026-10-22 KST**. 상태: **DRAFT FOR HUMAN REVIEW**. 발표일: 2026-11-02.
Task Contract는 [Run #2 계약](../run2-inputs/MID01_Run2_Codex_Task_Contract.md), 검토 입력은
[INDEPENDENT_REVIEW](../run2-inputs/INDEPENDENT_REVIEW.md)다. 기존 MID01 7개 문서는
10월 21일 감사 스냅샷으로 보존한다. 이 디렉터리는 그 내용을 덮어쓰는 대신 수정 논리와 최신 차이를 제공한다.

발표의 중심은 **RQ1: 알려진 TAR 문제에서 identity/effect를 관찰·판정할 수 있는가**,
**RQ2: 같은 실행 예산에서 B0/B1/B3 정책이 어떤 탐색 차이를 만드는가**다.
RQ6 native intermediate feedback은 보조·확장 연구다. N01은 fixed-input automated replay이며
fuzzer rediscovery가 아니다. Pilot은 **NOT_AUTHORIZED / NOT_RUN**, 기본 발표 경로는 **Path B**다.

| 신규 파일 | 역할 |
| --- | --- |
| [00-independent-review-response.md](00-independent-review-response.md) | A–H 대응, RQ 용어 대응, 1차 문헌 비교, Run #2 Claim Register |
| [01-cve-and-evidence-boundaries.md](01-cve-and-evidence-boundaries.md) | 두 CVE 구분, N01 관측과 해석 경계, raw 검증 한계 |
| [02-github-pr-delta-20261022.md](02-github-pr-delta-20261022.md) | 최신 main 및 8개 PR 상태·의존성·구현/실행 구분; 기술 부록 |
| [03-contrast-identifiability.md](03-contrast-identifiability.md) | B/A/P 비교의 식별 대상·잔존 정보·해석 한계 |
| [04-slide-outline-v2.md](04-slide-outline-v2.md) | 교수 대상 12장, 발표 문장과 데이터 부족 시 대체 문장 |
| [05-reviewer-qa-addendum.md](05-reviewer-qa-addendum.md) | CVE 및 인과성 필수 질문을 포함한 추가 Q&A |
| [06-team-evidence-template.md](06-team-evidence-template.md) | 규민·주언·민찬 공통 제출 양식과 담당별 검토 항목 |

## 감사 경계와 근거 수준

읽기 전용 GitHub 확인 시점은 **2026-10-22 09:03 UTC / 18:03 KST**다. Remote main (`M`)은
`8d29982c26cebfcce7a413b3ba9177fcd28078de`로 기존 감사와 같다. 상세 head는 [02](02-github-pr-delta-20261022.md)에 고정한다.
로컬 HEAD도 같은 revision이며 작업 branch는 `docs/mid01-research-audit-20261021`이다.
기존 untracked MID01 자료와 `mid01-review.zip`은 입력 상태로 유지한다.

공식 node-tar 권고문과 ZIPDiff/Wormholes/LinkZard 원문을 이번에 직접 읽었다.
N01/native v2 수치는 저장소의 보존 보고서에 근거한다. 이번 감사는 off-worktree raw root를 열거나
historical reader를 실행·재계산하지 않았다. 과거 independent verification과 이번 문서 감사를 구분한다.
PR 본문의 테스트 수는 **기여자가 보고한 engineering evidence**로만 인용한다.

[실험 검증 스킬](../../../../../.codex/skills/inodefence-experiment-validation/SKILL.md)의
observed fact → derived result → interpretation → paper claim 구분을 적용했다.
새 raw를 검증하거나 evidence 등급을 승격하지 않았다. 스킬의 path-only 비교 예시는
이 프로젝트의 비교군을 추가하지 않는다. Canonical B0/B1/B3 정의를 따른다.

실제 extractor, Docker, N05, historical target, fuzzing campaign은 실행하지 않았다.
Production code/test/config와 canonical 문서는 수정하지 않았다. Git commit/push/merge 및
외부 메시지 전송도 하지 않았다. `make check`와 pytest는 이 계약의 문서 정적 검증 범위에 포함하지 않았다.
이후 실험을 허가하는 문서는 아니다.

## 해결되지 않은 의사결정 5개

| ID | 결정할 내용 | 필요한 근거 / 기본 처리 | 책임 제안 |
| --- | --- | --- | --- |
| D1 | N01 exact input과 CVE-2026-23745의 root-cause correspondence를 accept/reject/unresolved 중 무엇으로 기록할 것인가? | 원본 보존 범위·metadata-only C2·package bytes 누락을 포함한 실제 human disposition; 그 전 pending | Research Lead + 규민 |
| D2 | #115 source-origin 수정 및 #118 이후 consumer 연결을 포함한 최종 source/controller를 어디서 동결할 것인가? | 최종 clean SHA, exact N05 applicability, 독립 검토. 기존 exact-SHA 규칙의 암묵적 호환 예외 금지 | Maintainer + 규민·주언 |
| D3 | 최종 consumer/host ledger의 승인 신뢰 경로·보존 위치·실패 시 attempt 소비 규칙을 어떻게 확정할 것인가? | #117 Units 2–4 설계와 실제 연결 증거; reader 존재만으로 해결됐다고 하지 않음 | Maintainer + 주언 |
| D4 | 향후 pilot을 qualified historical route로 할지, 별도 exploratory feasibility route로 할지, 발표 전 보류할지? | route별 실제 승인·N05 근거·자원·claim 범위. 4,000회는 제안 총량이며 승인되지 않음 | Research Lead |
| D5 | 10월 30일 발표 동결 시 Path B 유지 및 native RQ6 후속 범위를 어떻게 정할 것인가? | 10월 27일 검토 packet을 기준으로 Path A 증거가 없으면 B; v3 native qualification/effectiveness는 별도 계약 | Research Lead + 민찬 |

## Research Lead 검토 체크리스트

- [ ] 발표용 RQ1을 canonical rediscovery RQ1의 관찰·판정 선행 질문으로 명시한 데 동의한다.
- [ ] 두 CVE의 버전 경계와 N01 root-cause pending 문장을 승인한다.
- [ ] N01 표를 고정 입력 반복 관측으로 읽고 metadata-only C2 및 raw 재검증 부재를 확인한다.
- [ ] B1 full state-key와 B3/B0의 정책 전체 효과, A1/A2/A3의 좁은 범위를 확인한다.
- [ ] 선행연구 중복을 인정하고 최초성·외부 도구 대비 우월성 표현을 제외한다.
- [ ] #118 Unit 1과 실행 진입점 연결을 구분하고 N05/pilot NOT_RUN을 유지한다.
- [ ] 12장 각 Claim ID·근거·분모·대체 문장을 점검하고 Path A/B를 명시적으로 선택한다.
- [ ] 팀 제출에 raw URI/hash·independent verification·실패/누락·금지 결론을 포함한다.
- [ ] D1–D5 결정과 발표 승인 시각을 기록한다. 발표 승인과 실행 승인은 별개다.

## 정적 검증 기록

검증 대상은 이 디렉터리의 신규 Markdown 8개다. UTF-8/LF/마지막 newline, 링크·anchor,
표 열 수, Claim ID 참조, 12장 필드, 공통 제출 필드, whitespace 및 변경 범위를 정적으로 확인한다.
정적 검증은 **PASS**다: 신규 8개 파일, local Markdown links 123개, Run #2 Claim ID 20개,
12장 각각의 필수 내용, 공통 제출 14개 필드를 확인했다. UTF-8/LF/newline, fenced blocks,
표 열 수 및 `git diff --no-index --check`도 통과했다. 이는 문서 검사이며 project test 결과가 아니다.

작업 전후 Git-visible 기존 426개 파일의 SHA-256이 모두 동일하며, 신규 파일은 이 디렉터리의
지정된 8개뿐이다. 보존한 MID01 7개 문서의 전후 동일 SHA-256은 다음과 같다.

| 보존 문서 | SHA-256 (작업 전 = 작업 후) |
| --- | --- |
| 00-status-audit.md | `21153e341778412ec259c0bff44354bca6a335d784a392f9720541ce354c2f6e` |
| 01-claim-register.md | `cc649a41cc688e5dcde2f9c87f44dc3e65a2217e2917786f29c3ad27067c7833` |
| 02-research-narrative.md | `4a23ed66b5622b58dd108c78da8e7f61ea15d7536df5d6d12767a60ec72a19e7` |
| 03-slide-outline.md | `77562a8c620208098b4a745dab08fc89ba565205238e673e8aab5cdf40e7f327` |
| 04-team-evidence-requests.md | `181b912a1d0563627eaa74f88a2bcd918d5d12e2d9f925121c8a270a42ee8ae5` |
| 05-reviewer-qa.md | `5d7bd9d5c4a96bf905f81669b5f7f32bf1b35b23b13555187d4f513ec479887b` |
| README.md | `39756c1f2085d36431f49ea10c558d5ea90e42844ecd0f456e3ea65a5f15688d` |

완료 후 human review를 기다리며 중단한다. 자동 후속 실행이나 PR 게시 작업은 포함하지 않는다.
