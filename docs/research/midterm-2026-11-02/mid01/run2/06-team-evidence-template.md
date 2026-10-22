# 팀 증거 제출 공통 양식

이 문서는 Research Lead가 증거를 검토할 양식이다. 담당 제안은 **규민: N01/N05/실제 타깃**,
**주언: B0/B1/B3/Ablation**, **민찬: Native P0/P1/P2/v3**다.
팀원 수락이나 외부 전송을 기록한 것이 아니며 실행을 요청·승인하는 문서도 아니다.

항목별 packet을 복사해 작성한다. 실행되지 않은 항목은 **NOT_RUN**, 실제 승인이 없으면
**NOT_AUTHORIZED**로 적는다. 실행된 과거 N01/native v2까지 NOT_RUN으로 덮어쓰지 않는다.
순수 문서 작업에서 target/config 등이 적용되지 않으면 NOT_APPLICABLE과 이유를 적는다.
누락은 UNKNOWN/UNAVAILABLE로 표시하며 0/PASS로 채우지 않는다.

## 공통 packet — 필수 14개 필드

아래는 **빈 제출 양식**이며 실제 제출·실험 결과가 아니다.

| 필수 필드 | 작성 값 / 요구사항 |
| --- | --- |
| 담당자 | 이름, packet ID, 연락/검토 책임 범위. 제안 담당과 실제 제출자를 구분 |
| 검증 질문 | 정확한 RQ/가설/contract 및 이 packet이 답할 한 문장 |
| 정확한 source revision | full Git SHA, clean/dirty, 실행 source / reader source / 보고서 revision을 각각 구분. 미실행이면 실행 source NOT_RUN, 검토한 revision만 기입 |
| target 및 version | extractor/package/Node version, exact image/worker/lock/build identity. 적용 없으면 이유 |
| 실행 환경 | OS/kernel/architecture/controller/daemon, filesystem/mount/device/runtime root, uid/gid/limits/timeout, containment profile. Report-only 환경과 직접 확인 환경 구분 |
| 실제 실행 여부 | NOT_RUN 또는 RUN 및 실제 UTC 시작·종료. Synthetic/benign/historical/preflight/pilot/native qualification을 분리; 승인 상태 별도 기입 |
| config / budget / seed | immutable config URI/hash, seed corpus IDs/order, mutation/feedback/oracle IDs, RNG/schedule seed, planned/actual/all-status seed-inclusive budget. 미실행이면 계획과 actual NOT_RUN 명시 |
| 관찰된 결과 | raw field 수준 사실, derived contract verdict, interpretation을 분리. 미실행이면 ‘NOT_RUN — 관측값 없음’; 예상 결과나 가상 수치 금지 |
| raw evidence 및 SHA-256 | 원본 URI/path, artifact별 manifest와 SHA-256, 실제 재해시자·시각·범위. 미실행이면 ‘NOT_RUN — raw 없음’; planned config hash와 result manifest 구분 |
| independent verification 상태 | NOT_VERIFIED / earlier report only / machine reader PASS·FAIL / human disposition, exact verifier revision/output URI/hash. 미실행은 NOT_RUN, 검증 절차 설계만 있으면 DESIGNED |
| 실패, 차단, 누락 사항 | attempt/cell별 started/complete/failed/invalid/STARTED/missing/cleanup, 원인과 원본 보존 범위. 없음도 근거 필요; 미실행은 blocker 기록 |
| 주장 가능한 결론 | 정확한 발표 문장, 증거 수준, 대응 R2-Cxx, 적용 조건/분모 |
| 주장하면 안 되는 결론 | replay→rediscovery, metadata→content overwrite, synthetic→native, CI→qualification 등 해당 금지 확장 |
| 제출 시각 | ISO-8601과 timezone, 제출자, packet revision; 실제 작성 시 기록하고 예정 시각을 제출 완료로 쓰지 않음 |

## 수치·승인·근거 연결 보조 표

| 보조 필드 | 작성 방법 |
| --- | --- |
| 실행 authority | 실제 contract/approval reference와 신뢰된 전달 경로. 승인 검증 machinery나 synthetic authorized_by 문자열과 구분 |
| Evidence 층위 | DESIGNED / IMPLEMENTED / TESTED(synthetic/real 구분) / EXPERIMENTALLY VALIDATED를 각각 기록; 근거 없는 마지막 label 금지 |
| 관측·파생·해석 | `raw field → reader/analysis revision → table/figure → slide/Claim ID`의 링크 연결 |
| Schedule 회계 | planned/actual/complete/invalid/pending 분모; replay와 search budget 분리; 실패 prefix 원본 유지 |
| Provenance 한계 | 원 package bytes 또는 raw 부재, source mismatch, 환경 차이, checksum만 확인한 범위 등 명시 |
| Human disposition | accept/reject/unresolved, 검토자·시각·근거 identity. 머신이나 AI가 대리 발급하지 않음 |

SHA-256은 실제 보존한 bytes와 연결해야 한다. 화면 캡처나 요약표만으로 raw 제출을 대체하지 않는다.
원본은 수정하지 않고 분석 결과를 별도 derivative로 작성한다. 재검증이 읽기 전용을 넘어 새 출력을
생성한다면 적절한 별도 범위가 필요하며 이 양식이 실행 권한을 만들지 않는다.

## 담당별 추가 제출 포인트

| 담당 | 검토 packet | 반드시 포함할 구분 / 참조 |
| --- | --- | --- |
| 규민 | N01 source/input/images/10초 setup, 8 readiness/10 pair, C1 및 metadata-only C2, machine token과 human disposition | 두 CVE 버전 경계; raw 재검증 범위; original package bytes 누락; fixed rejection과 release safety 분리. [01](01-cve-and-evidence-boundaries.md), R2-C02–R2-C05/R2-C15 |
| 규민 | N05 actual authority/readiness 유무와 source/controller binding dossier | #115 source-origin 수정은 후보; 5초 PASS가 없으면 NOT_RUN; consumed N04와 새 attempt 분리; N05 승인과 pilot 승인 분리. [02](02-github-pr-delta-20261022.md), R2-C06/R2-C07/R2-C11 |
| 주언 | B0/B1/B3 및 A1/A2/A3 의미·version·공통 조건표 | B1 full key, B3−B0 정책 전체, B3−B1 violation admission 추가, A1/A2 잔존 정보, A3 잔존 order. [03](03-contrast-identifiability.md), R2-C08–R2-C10/R2-C16 |
| 주언 | #118 Unit 1과 실제 execution freeze/reader/host accounting 연결 상태; 실제 pilot packet 또는 미실행 packet | 20×200은 계획 총량; actual 값과 raw 없으면 NOT_RUN. 별도 approved route, full-state metrics, lineage·censoring·모든 실패 분모. [02](02-github-pr-delta-20261022.md), R2-C07/R2-C11/R2-C14/R2-C20 |
| 민찬 | version별 P0/P1/P2 및 v1/v2/v3 gate map | v1 blocked, v2 480-run NOT_QUALIFIED 유지; v3 generic synthetic와 native dependency producer 분리. P1−P0/P2−P1은 조건부 질문. [03](03-contrast-identifiability.md), R2-C10/R2-C12/R2-C18 |
| 민찬 | 1차 문헌/novelty 근거 및 발표 한계 검토 | ZIPDiff archive feedback, Wormholes 자동 workflow, LinkZard file/link-state 중복 인정; 조합 차이와 novelty·효용 분리. [00](00-independent-review-response.md), R2-C13/R2-C19 |

## Research Lead 수령·검토 기록 양식

기존 [팀 제출 일정](../04-team-evidence-requests.md)의 10월 23일/27일 18:00 KST는 제안된
handoff이며 수락·완료 여부를 새로 추정하지 않는다. 10월 30일 콘텐츠 동결의 18:00 KST도
기존 운영상 제안이다. 일정 변경·담당 수락은 사람이 기록한다.

| 검토 필드 | 빈 기록 |
| --- | --- |
| Packet ID / 담당자 / 실제 수령 시각 | 미기록 |
| Source·target·config·raw identity 검토 | 미검토 |
| 실제 실행·독립 검증·human disposition 확인 | 미검토 |
| 실패·누락·분모·claim 경계 확인 | 미검토 |
| 허용할 슬라이드/Claim ID와 정확한 문장 | 미결정 |
| Path A 허용 또는 Path B 유지 | 기본 Path B; 실제 결정 미기록 |
| 보완 요청 / 결정자 / 결정 시각 | 미기록 |

NOT_RUN packet도 올바른 상태·blocker·다음 의사결정을 담으면 제출 가능하다.
발표 검토를 통과했다고 실험 실행·Git push/merge가 승인되는 것은 아니다.
