# 신규성·관찰 교란·오라클에 대한 비판 검토

> 10/24 재검토: 아래 10/23 비교·반박은 유지한다. 현재 HEAD `9e36e12`의 native v2 demo 보고는
> v3 qualification이나 효율 증거로 승격하지 않는다. 최신 변경과 추가 반박은 끝에 있다.

2026-10-23 KST. 기존 [선행연구 비교표](intermediate-observation-report.md)의 범위를 유지하며
아래 1차 문헌의 관련 구간을 재확인했다. 성능을 직접 비교하거나 artifact를 실행하지 않았다.

| 자료 | 재확인 구간·차이 | 확인되지 않은 항목 |
| --- | --- | --- |
| [ZIPDiff 원문](https://www.usenix.org/system/files/usenixsecurity25-you.pdf) | §4.3/4.4 output 기반 corpus/softmax-UCB operator 선택. adaptation 자체는 신규성 아님 | native callback dependency·Linux inode-continuity feedback은 확인되지 않음 |
| [Wormholes 원문](https://www.usenix.org/system/files/usenixsecurity26-liu-yongheng.pdf) | §4–5/§5.6 symlink composition·creation order·path validation. 순서 연구 자체는 신규성 아님 | InodeFence 같은 finite rebinding key closed-loop 효과 실험은 확인되지 않음 |
| [LinkZard 저자 원문](https://lfysec.github.io/paper/linkzard-security25.pdf) | §4와 Appendix C: runtime state query·API graph·hardlink/link count. 중간 정보·파일 상태 연구 자체는 신규성 아님 | Linux TAR input corpus와 node-tar completion qualification은 확인되지 않음 |

ZIPDiff [공식 저장소](https://github.com/ouuan/ZipDiff)는 이전 조사에서 확인됐지만 이번 web fetch는
timeout이었다. `main/README.md` 경로도 404여서 branch를 추측해 코드 내용을 인용하지 않았다.
이번 새로운 source-code 비교 주장은 추가하지 않는다. Wormholes/LinkZard 공식 코드 checkout은
이번 확보하지 않았다. 따라서 “없다”가 아니라 “확인되지 않음”으로 유지한다.

## 예상 반박과 현재 답변

| 질문 | 현재 답변 | 근거 | 남은 약점 | 추가 검증 방법 |
| --- | --- | --- | --- | --- |
| 기존 연구도 중간 상태·순서를 다루지 않나? | 그렇다. LinkZard는 runtime query/API sequence, Wormholes는 creation order를 다룬다 | 위 원문 구간 | 전체 문헌을 exhaustive 검토하지 않음 | 후속 systematic review; 표현/feedback/target의 차이를 별도 비교 |
| InodeFence의 차이는 무엇인가? | Linux TAR input mutation에 object/external effect의 finite feedback을 연결하고, v3에서는 same-path absence와 explicit dependency를 composite로 표현하는 조합이 후보 | v2/v3 canonical design와 #111 | 조합의 신규성·유용성은 아직 입증 안 됨 | native qualification 후 독립 behavior evaluator와 ablation |
| 그냥 로깅 추가 아닌가? | 로깅은 instrumentation infrastructure다. representation의 nonredundancy는 합성에서 확인되지만 연구 효과는 별도 | v3 equal-v2-key synthetic test | 추가 key가 탐색에 도움이 되는지 모름 | H10/H21, composite 사용/미사용의 versioned 비교 |
| P2가 적응형이면 새로운가? | 아니다. ZIPDiff도 adaptive operator 선택을 한다. 차이는 reward representation과 bounded 정책의 검증 가능성에 한정 | ZIPDiff §4.4, mutation_scheduler.py | 현재 integer reward의 이점 없음 | same admission P2−P1, saturation/독립 성과 분석 |
| 계측이 원래 실행을 바꾸지 않나? | wrapper·ALS·동기 lstat/hash·buffer allocation이 callback/event-loop 지연과 I/O 경쟁을 바꿀 수 있다 | #87/#88/#89의 profile 차이; producer source | final equality와 deterministic tests로 무교란을 입증할 수 없음 | stock/minimal/v2-full/v3-full의 counterbalanced native qualification, frozen schedule criteria |
| 관측 누락을 부재라고 오인하지 않나? | absence는 성공한 명시적 path observation만 인정한다. missing event/failed observation은 absent가 아니다 | EffectObservationStatus·strict reader | 지원하지 않는 API나 통째로 빠진 start+completion은 ledger만으로 검출 불가 | API surface 감사·native fault injection·외부 trace를 제한적 corroboration으로 사용 |
| 기록 sequence가 causal order인가? | 아니다. callback 관측 순서다. dependency는 실제 continuation/handle 증거가 필요 | v3 direct token 조건 | token은 producer가 거짓 발급하면 hash가 맞아도 틀릴 수 있음 | source-guarded branch token qualification·wrong-branch 음성 대조 |
| external manifest hash면 충분한가? | bytes가 frozen 기대값과 같다는 integrity만 보장한다. 실제 branch truth·인간 승인·completeness를 보장하지 않는다 | #111 forgery 수정, reconstruct_rebinding_evidence | 같은 주체가 잘못 만든 raw와 manifest를 동결할 수 있음 | 독립 source review·trusted external publication·native endpoint cross-check |
| 오라클 오탐은? | C0는 harness가 observation 구간에 bookkeeping을 쓰면 target effect로 오인할 수 있다. C2 metadata는 benign extraction에서도 바뀔 수 있다 | security-contracts.md attribution/limitations | contract candidate가 exploitability와 다름 | controlled sentinel/benign negative controls, actor 경계 감사, replay/root-cause 판정 |
| 오라클 미탐은? | final C0/C1/C2는 transient effect·direct use·sandbox 밖 접근·symlink referent를 일반적으로 증명하지 못한다 | security-contracts.md persistent scope | intermediate event가 있어도 최종 verdict를 자동 확장하지 않음 | 별도 intermediate oracle 계약 없이는 “관찰 사실”로만 보고 |
| inode equality면 계속 같은 객체인가? | 분리된 시점의 같은 dev/inode는 inode recycling 때문에 연속 identity 증명이 아니다 | #91 진단·v3 design | 관측 gap이 남음 | explicit present→absent→present와 anchored old inode 대조; 원자 교체라고 표현 금지 |
| 합성 테스트는 실제 동작을 얼마나 보장하나? | 입력한 frame/호출 schedule에서 bookkeeping·strict reconstruction이 계약대로 동작함을 보장한다 | 새 prototype와 기존 reader tests | target hook coverage·native token truth·overhead·OS races·crash durability는 미검증 | qualified contained execution과 독립 raw reader |
| 실제 비교 없이 무엇을 말할 수 있나? | 기존 negative qualification의 근거와 generic representation·합성 호환성, 남은 native gate를 설명할 수 있다 | report/evidence-index | “효과 향상/최초/실제 관찰 성공”은 방어 불가 | 해당 주장은 축소해 미검증 가설로 유지 |

## 해석을 줄인 주장

- “중간 전체 상태를 관찰했다” 대신 “지원한 operation의 전후 path/object evidence를 모델링했다.”
- “causal graph를 복원했다” 대신 “증거가 있는 제한된 dependency만 표현한다.”
- “v3 producer 구현 완료” 대신 “target-free bounded bookkeeping/serialization prototype 합성 검증, native hook 미구현.”
- “보안 탐지 향상” 대신 “representation nonredundancy 합성 검증; 효과는 H10/H21로 남김.”
- “계측이 동작을 바꾸지 않음” 대신 “교란 가능성이 있고 native qualification으로 범위를 제한해야 함.”

재현 지연·자원 비용은 instrumented profile별 측정 대상이다. v2 historical ratio를 새 prototype의
overhead로 옮기지 않는다. 조건을 통과하지 못한 실행을 버리고 성공 run만 골라 발표하지 않는다.

## 10/24 추가 검토

ZIPDiff 원문의 §4.4 UCB/softmax와 LinkZard Appendix C의 hardlink/query 정보를 재확인했다.
Wormholes PDF 재조회는 timeout이었고 공식 발표 페이지의 연구 설명만 이번 확인됐다.
따라서 창작한 코드 비교나 “선행연구에 기능이 없다”는 주장을 추가하지 않는다. 이전 원문 검토와
이번 접근 실패를 구분하며 기존 비교표의 미확인 표기를 유지한다.

| 추가 질문 | 현재 답변 | 근거 | 남은 약점 | 추가 검증 |
| --- | --- | --- | --- | --- |
| 팀 native demo가 있으니 중간 관찰은 모두 완료 아닌가? | v2 local endpoint 출력의 팀 실행 보고는 존재한다. 모든 entry의 complete trace·원자 전체 상태·v3 dependency 검증은 별개다 | #133/LOG·native_demo_report | 원본 JSON 미확보, 거부 step event0/conflict | 원본/worker/image/source 대조, 오류 prefix 보존 |
| event0이면 effect가 없나? | 아니다. 미완료 operation이 event로 구성되지 않았을 수 있다 | LOG의 start-only open 보고, current worker 종료 코드 | 이번 실제 callback 동작 재현 없음 | pending 원본·terminal·stderr 검토; no-effect로 판정 금지 |
| 데모의 배열 순서가 실제 작업 순서인가? | 아니다. 보고서는 entry/start 순 정렬이다 | effect_demo._trace_report | ordered 그림이 총순서를 암시할 수 있음 | completion_sequence 명시, 표에 정렬 기준 표기 |
| prototype complete가 coverage 증거인가? | local settlement만 확인한다. 이번에는 제공된 v2 전체 event 집합과 export 대조를 보강했다 | 4개 red→green 회귀 | 두 채널 공통 누락은 여전히 모름 | token hook/지원 API별 native qualification |
| 같은 token을 두 번 쓰면? | 이번 synthetic prototype은 predecessor/token을 한 번만 소비하도록 제한한다 | begin 회귀 검사 | 실제 source branch token 발급 없음 | source-bound one-shot native callback 음성 검사 |

관찰 자료를 보고용으로 복사하는 기능과 피드백이 **효율을 높이는 연구 기여**는 다르다.
팀 데모가 연결 동작을 보여줬다는 기록과 H10/H21 미검증은 동시에 성립한다.
