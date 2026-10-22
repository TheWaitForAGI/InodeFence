# 지웅 전달용 — 민찬 중간 관찰 연구

작성 2026-10-22 KST. 제출 자료를 저장소에 준비했으며 외부 메시지·PR·댓글은 게시하지 않았다.

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
