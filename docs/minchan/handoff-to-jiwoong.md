# 지웅 전달용 — 민찬 중간 관찰 연구

작성 2026-10-22 KST. 제출 자료를 저장소에 준비했으며 외부 메시지·PR·댓글은 게시하지 않았다.

> 10월 23일 보완 결과는 아래 추가 인계와 [26일 결과 확정표](result-freeze-checklist.md)를 따른다.
> 위 작성일과 아래 기존 테스트 수는 22일 이력이다.

## 핵심 결과

- P0 final admission → P1 transition admission → P2 operator adaptation이며 parent는 uniform이다.
- node-tar entry end는 filesystem completion이 아니다. 정확한 entry association도 coherent archive-prefix snapshot을 보장하지 않는다.
- v1 native blocked, v2 13/14로 NOT_QUALIFIED, v3 generic synthetic tested다. 이 세 판정을 유지한다.
- v2 coverage 실패는 duplicate-path가 same-inode truncation을 만든 데 있다. multi-operation unlink→create/link는 기존 single-operation replacement와 다르다.
- v3는 same-entry/path·explicit absence·direct producer continuation·conflict-free gap을 별도 composite로 표현한다. native token producer는 남아 있다.

## 완료·실패·미검증

| 항목 | 상태 |
| --- | --- |
| 요청 15개 PR metadata/body/diff/discussion 조회와 이력표 | 완료; discussion 반환은 모두 빈 배열 |
| P0/P1/P2, v1/v2/v3, 실제 hook 연결 분석 | 완료 |
| 보고서·색인·Mermaid·검증 기록·발표 구성 | 완료 |
| 기존 합성 focused tests / canonical | 76 통과 / 1,584 통과; Ruff·format·Pyright·환경·사후 문서 검사 통과 |
| 기존 native qualification | v1 실패, v2 실패라는 보존 자료 판정 유지 |
| 과거 raw 재검산 | raw 미확보로 차단 |
| v3 native producer/qualification/effectiveness | 미구현/미실행/미검증 |

## 발표에서 가능한 주장

“완료 순서와 archive 순서를 구분해야 한다는 기존 실험 근거를 정리했고, ordered checkpoint의 한계를 operation evidence/partial order로 모델링했다. v2 coverage의 의미 차이를 분석해 별도 v3 composite를 만들었고, 현재 generic reader/feedback은 합성 검증됐다.”

피할 주장: 실제 node-tar v3 연결 완료, 14조건 모두 통과, middle state 관찰로 취약점 발견, P2가 P1보다 우수, 최초 state-guided archive fuzzer, 기존 연구가 link/order/state를 다루지 않았다는 표현. 과거 실험 번호 v3와 현재 rebinding v3도 구분한다.

## 10월 26일까지의 후속 작업

1. 기존 raw archive/checksum을 확보해 fresh-process independent reader로 14조건을 재계산한다. 확보하지 못하면 발표에 자료 주장임을 명시한다.
2. native v3를 추가하려면 CHECKFS2의 removal callback→MAKEFS continuation을 source guard와 branch token으로 연결하는 최소 Task Contract를 확정한다. manifest publication·failure injection도 포함한다.
3. native 연결을 검증하지 못하면 미검증 상태로 결과를 확정하고 10월 27일 발표에는 negative qualification과 synthetic representation 결과를 사용한다.

연결 자료: [전체 보고서](intermediate-observation-report.md), [주장별 근거](evidence-index.md), [그림](diagrams.md), [실험 결과/로그](experiment-results.md), [6장 발표 구성](presentation-outline.md).

## 10월 23일 추가 인계

실제 중간 상태의 증거 인정표, P1−P0/P2−P1의 지지·반박 조건과 공정 비교 프로토콜,
신규성·교란·오라클에 대한 비판 검토를 추가했다. target-free bounded capture prototype은
start/complete correlation·실패·pending·overflow를 다루고 기존 v3 reader에 호환되는 envelope를
만든다. token은 합성 입력이며 실제 node-tar hook은 없다. 이번 검증 수치는 experiment-results의
23일 절을 사용한다. 과거 raw와 기존 native negative decision은 그대로다.

발표 가능한 짧은 문구:

> 중간 관찰을 인정할 증거 조건과 정책 비교 가설을 명시했고, 제한 수집 prototype과 v3 reader의
> 합성 호환성을 검증했다. 실제 node-tar v3 관측과 탐색 효과는 아직 검증하지 않았다.

금지할 문구: 전체 중간 filesystem snapshot 확보, native v3 연결 성공, causal 전체 순서 복원,
P2 우월/취약점 탐지 향상, 실제 실행 승인 확보. composite는 보안 위반 판정이 아니다.

의존성: 규민의 N05·주언의 B0/B1/B3는 별도 source/승인/실행 gate다. 접근 가능한 #115/#122의
NOT_RUN 표기를 확인했지만 개인별 작업 현황을 대신 확정하지 않았다. 해당 작업을 구현·실행하지 않았다.
민찬의 다음 native gate는 실제 branch token producer와 독립 qualification이며 N05 PASS로 대체되지 않는다.

이번 검증은 신규 합성18개 포함 focused94 통과, canonical1,602 및 Ruff/format/Pyright/환경/문서 검사
통과다. 기존 22일 76/1,584와 섞지 않는다. 초기 prototype의 3실패/10통과와 수정 이력도 보존했다.

26일에는 raw 재계산·native qualification이 미완료라면 차단/미검증으로 남긴 채 문서·합성 결과를
확정한다. 검토할 문서는 [가설](research-hypotheses.md), [반박 검토](novelty-and-threats.md),
[확정표](result-freeze-checklist.md)다. 외부 전달은 사용자가 수행하며 이번에 메시지를 보내지 않았다.
