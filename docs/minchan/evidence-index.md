# 주장별 근거 색인

확인일 2026-10-22 KST. F=직접 파일/API/실행 확인, R=자료의 기록, I=분석, U=미검증.
현재 코드 SHA는 모두 `8d29982c26cebfcce7a413b3ba9177fcd28078de`다. 아래 line은 이 SHA 기준이다.
PR 당시 head/base/merge SHA와 본문은 [JSON snapshot](evidence/pr-snapshots.json)의 각 `number` record를 따른다.
요청 15개 PR을 fetch했고 discussion API는 각 빈 배열을 반환했다. 리뷰 원문을 별도로 확보했다고 주장하지 않는다.

| 주장 / 종류 | 근거 | 범위·해석 제한 |
| --- | --- | --- |
| P0/P1 admission 차이 F | [계약](../research/design/transition-feedback-v1.md), [#81](https://github.com/TheWaitForAGI/InodeFence/pull/81), src/inodefence/feedback/transition_search.py | native effectiveness 아님 |
| P2 operator weights F | [scheduler](../../src/inodefence/mutation_scheduler.py), `TransitionAdaptiveScheduler` line 125, [#82](https://github.com/TheWaitForAGI/InodeFence/pull/82) | 새 transition binary reward, parent는 uniform |
| v1 checkpoint/trace F | [model](../../src/inodefence/model/transition.py), [#79](https://github.com/TheWaitForAGI/InodeFence/pull/79) head `b2b936eeee5d7db271d10c192ef30a836f7aebb2` | synthetic와 native 분리 |
| v2 14조건 F | [qualification runner](../../scripts/qualify_node_effect_observation.py), `_summarize` line 277 이후, criteria line 331 | all(criteria.values()); overhead 항목 상수 True |
| 13/14·480회·실패 cell R | [보존 요약](../../experiments/summaries/node-native-effect-observation-qualification-v2.md), #89/#90 snapshot | clean 실행 SHA `36ff7fdb0e31db72b3e581fd1c089b712b4a7b4e`; 이번 raw 부재 |
| duplicate reuse 코드 F/I | [upstream unpack](https://github.com/isaacs/node-tar/blob/v7.5.22/src/unpack.ts#L670), ISREUSABLE와 CHECKFS2 | tag source 검토. 실제 package hash는 v1 qualification 문서; upstream tag SHA 미해석 |
| entry/body와 fs 순서 분리 F/I | [parse](https://github.com/isaacs/node-tar/blob/v7.5.22/src/parse.ts), [reservations](https://github.com/isaacs/node-tar/blob/v7.5.22/src/path-reservations.ts), unpack CHECKFS line 680 | tag 기반 source reading, 현재 native run 아님 |
| private completion 역순·consistency failure R | [#87](https://github.com/TheWaitForAGI/InodeFence/pull/87), [요약](../../experiments/summaries/node-internal-completion-qualification-v3.md) | clean `9ea306f7ad20b8f479126360baf21192e0e86fdb`; raw SHA `ecb40154776e2f09883ecad6edb8f63abb57edc7becb3cd062863eb7e2a60cf0` |
| 1,020 attribution·162 overlap R | [#88](https://github.com/TheWaitForAGI/InodeFence/pull/88), [요약](../../experiments/summaries/node-causal-effect-qualification-v4.md) | clean `72bccfa`의 전체 SHA/환경은 요약 참조; 재실행 아님 |
| v2 실제 collector 구현 F | [producer](../../src/inodefence/targets/_node_effect_producer.cjs), `installEffectWrappers` line 272, operation start 315/completion 342, checkFs2 wrapper 403 | 이것을 v3 producer라고 부르지 않음 |
| multi-operation 진단 R | [#91](https://github.com/TheWaitForAGI/InodeFence/pull/91), tools/node-tar/diagnostics/ | clean `2e31ea9`; raw archive SHA `eae2eb45925c560c7821997ff8b42a6ccae9634c26ea7462d34685f4b6679355` |
| v3 당시 proposal R | [#100](https://github.com/TheWaitForAGI/InodeFence/pull/100) head `3e0ef26d89a1a1f93867a6641822c37d5b9ee5ce` | 당시 NOT_IMPLEMENTED; 현재 구현과 다름 |
| v3 composite 조건 F | [derivation](../../src/inodefence/feedback/rebinding.py), `derive_namespace_rebinding_sequences` line 93, `effect_feedback_projection_v3` line 225 | same-entry/path, explicit absence, direct dependency, no conflict |
| v3 external manifest digest F | [reader](../../src/inodefence/evaluation/rebinding_evidence.py), `reconstruct_rebinding_evidence` line 240 | external expected hash는 integrity trust root; native semantic truth 보증 아님 |
| token forgery correction R/F | [#111](https://github.com/TheWaitForAGI/InodeFence/pull/111), [test](../../tests/test_rebinding_v3.py) line 625 | 본문은 adversarial review 기록; 이번에는 regression 직접 통과 |
| 합성 역순/실패/누락·중복 F | [producer tests](../../tests/test_node_effect_producer.py) line 531/580/612/895, [실행 로그](evidence/focused-tests.log) | synthetic frames, delay/native 실행 아님 |
| v3 합성 nonredundancy F | tests/test_rebinding_v3.py line 431, focused 로그 | v2 keys 동일 fixture에 composite 차이. search 향상 미검증 |
| native v3/효과 U | [v3 canonical design](../research/design/namespace-rebinding-sequence-v3.md), STATUS | producer NOT_IMPLEMENTED, qualification/effectiveness NOT_RUN |

## 1차 문헌

| 자료 | 직접 확인한 구간 | 사용한 주장 / 미확인 |
| --- | --- | --- |
| You et al. 2025 [ZIPDiff 원문](https://www.usenix.org/system/files/usenixsecurity25-you.pdf), [코드](https://github.com/ouuan/ZipDiff) | §4 workflow, §7.3 limitations | output feedback/UCB, final disk output와 internal result 차이. inode/native completion 모델 확인되지 않음 |
| Liu et al. 2026 [Wormholes 원문](https://www.usenix.org/system/files/usenixsecurity26-liu-yongheng.pdf), [공식 발표 페이지](https://www.usenix.org/conference/usenixsecurity26/presentation/liu-yongheng) | §4–5, §5.6 | symlink composition/order, 85-project 평가와 ZIPDiff 비교는 저자의 결과. 공식 구현 저장소는 이번 확인되지 않음 |
| Xiang et al. 2025 [LinkZard 저자 원문](https://lfysec.github.io/paper/linkzard-security25.pdf) | introduction/approach, Appendix C | state-query/type/count feedback, graph, hardlink/link-count. Windows 대상; native node-tar 비교 없음. 공식 코드 checkout 미확보 |

논문 전체를 재현하거나 모든 reference를 감사하지 않았다. 문헌의 “미확인”은 부재 증명이 아니다.

## 보존 자료와 직접 검증의 경계

이번 snapshot은 GitHub metadata/본문·discussion 반환의 수집본이다. diff는 API로 가져와 관련 부분을 검토했지만 전체 diff 원문은 이 산출물에 복제하지 않았다. 과거 head의 모든 파일·CI artifact를 checkout해 실행한 것도 아니다. 과거 테스트 수치는 PR 주장(R)으로만 사용했다. 현재 코드의 테스트는 별도 로그(F)로 남긴다.

과거 raw 경로와 SHA는 [실험 결과](experiment-results.md)에 있다. 현재 `experiments/raw`에는 안내 파일만 확인됐고 해당 raw archive는 없었다. 따라서 자료 수준은 **보고된 negative qualification에 대한 근거 연결**이며 이번 독립 재현이나 PAPER-READY effectiveness evidence가 아니다.

## PR revision 전체 식별자

| PR | head SHA | merge SHA |
| --- | --- | --- |
| #79 | `b2b936eeee5d7db271d10c192ef30a836f7aebb2` | `f90a361307bbd44e8035c23774928d530902ceb9` |
| #80 | `7d61a6345db139a429eb8875c5210203360c95a0` | `de3a8ece8719ce556b9d6f4d0c8c3bfbbab758d6` |
| #81 | `59f5fc3c9ccfd37e3260ae814a01a4ff71ce6649` | `9977c5b60a9411728ad2b56cd7ca6545fb990e97` |
| #82 | `e07d7bc5f12d48324663cc625aed5479785a6ab2` | `bd94dfb050bae2a108ed348f567e35b342fb0d91` |
| #83 | `0935ccfe523dc41e61ee514fc573e7f789f57be4` | `ffb687425eec6219dcf1c6bec18593b75ee2b453` |
| #84 | `e2284ef36bf774fc346e66c1bb635862b2e7153c` | `0b856e771f8c5a20faacc9706eb1933f5ed7ec89` |
| #85 | `02b7db2eb77df44497da3b4adcbfecb6a268d00d` | `931899209bc1de29f249d9e2f3d451438ddf1d22` |
| #86 | `1ca7ccee2838e7d27afcdba93a89d5471f405f52` | `269b1e1d74609e52c222320235e8faf51864998b` |
| #87 | `104c6d73f68b12beb49756b0cd4955b84a4e9eef` | `b31470a51db93e63d4911f061ba424e59a90fa73` |
| #88 | `dd8dd15b2b4a8ce697e3ef38567883f2602cfb15` | `58e69ae70953bf4e7b696abeea02d9dfe987d9b5` |
| #89 | `0eb527f88aa8a4015544d2f6b0eabfebe079bf18` | `ccc061bece3f3525ecf0b734777a6b39bac06b07` |
| #90 | `c46f3724134d58283daa713774923e73aa9a0994` | `3db15e486957a38fcc381ef093e09c223df8faa5` |
| #91 | `0fa8bda5349de78541efb7f1622c469c6abf2d51` | `57f751992f60a534c5b07506e72124abe5d6b07d` |
| #100 | `3e0ef26d89a1a1f93867a6641822c37d5b9ee5ce` | `da42c805b391ca842543dcf0db77f6edbce96b1e` |
| #111 | `44e115b177d8b3aed7b06141c0523f567e0772c9` | `8d29982c26cebfcce7a413b3ba9177fcd28078de` |
