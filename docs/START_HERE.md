# InodeFence — 여기서 시작

이 문서는 **처음 프로젝트를 보는 사람과 코딩 에이전트가 가장 먼저 읽는 문서**다.

모든 문서를 처음부터 읽을 필요는 없다.

## 1. 이 프로젝트가 뭔가?

InodeFence는 TAR 압축 해제 프로그램을 대상으로 하는 보안 퍼저 연구다.

핵심 아이디어는 간단하다.

```text
TAR를 조금 바꾼다
    ↓
실제 extractor에 풀어본다
    ↓
파일시스템 상태를 본다
    ↓
처음 보는 위험한 상태면 그 TAR를 남긴다
    ↓
그 TAR를 다시 바꾼다
```

우리가 특히 보는 상태는 다음이다.

- 어떤 path가 생겼는가
- file type이 무엇인가
- 두 path가 같은 filesystem object를 가리키는가
- hardlink 관계가 생겼는가
- 외부 sentinel이 바뀌었는가

## 2. 왜 하는가?

단순히 path 문자열이 안전해 보여도 실제 filesystem object 관계는 위험할 수 있다.

예:

```text
/extract/result.txt ─┐
                     ├── 같은 inode
/outside/sentinel ───┘
```

이 상태라면 extraction 내부 파일을 수정했는데 외부 sentinel도 같이 바뀔 수 있다.

InodeFence는 이런 **object identity와 external effect를 fuzzing feedback으로 사용할 가치가 있는지** 실험한다.

## 3. 무엇이 새롭다고 주장하는가?

아직 확정하지 않는다.

다음은 이미 선행연구에 존재하므로 이것 자체를 novelty라고 말하면 안 된다.

- TAR fuzzing
- hardlink
- symlink
- entry order
- filesystem-state fuzzing
- feedback-guided fuzzing
- outside-root write

현재 검증할 가설은 다음이다.

> 고정된 공격 recipe 없이 generic TAR mutation을 수행하면서 filesystem security state를 feedback으로 쓰면 보안 경계 위반을 더 잘 탐색할 수 있는가?

Entry-transition 확장은 extraction 전체가 끝난 뒤의 state뿐 아니라 검증된 entry completion
경계 사이의 state transition이 같은 budget에서 추가 탐색 이득을 주는지 묻는다. 이는
**HYPOTHESIS**이며 아직 **RESULT**가 아니다. Pinned node-tar 7.5.22의 공개 async/sync event,
Linux filesystem event, syscall trace와 prefix replay 후보는 controlled qualification에서
공통 native completion boundary 조건을 충족하지 못했다. 현재 결정은 **QUALIFIED FAIL**이며
native mode는 **NOT_IMPLEMENTED**다. 별도 libarchive 3.7.2 public write-disk 후보도 directory
metadata가 final close까지 지연되어 공통 completion boundary에 **QUALIFIED FAIL**했다.
Source-guarded node-tar private completion marker는 entry association에 성공했지만 mixed/
independent 작업이 archive order 밖에서 완료되고 callback snapshot에 후속 effect가 포함됐으며
한 consistency failure와 scheduling 변화가 관찰돼 역시 **QUALIFIED FAIL**했다.
별도 async-context causal-effect qualification은 1,020개 filesystem operation을 정확한 entry에
귀속했지만 independent-files 20/20에서 completion `0,1,3,2`와 earlier completion 전 162개
later-ordinal operation을 기록해 **QUALIFIED FAIL**했다. 현재 native v1 판정은
**BLOCKED_NATIVE_OBSERVATION**이다. Partial-order/effect-event v2는 Gate 1 설계와 Gate 2
generic model/normalization/search/scheduler closed-loop synthetic tests를 통과했다. Gate 3
bounded native producer는 WSL의 기존 trusted broker에서 contained fixture 검증 10개를
통과했다. Clean revision `36ff7fd`에서 480-run matrix를 완료했고 independent reader가
320개 native bundle과 160개 stock record를 재검증했다. Duplicate-path가 동일 inode를
truncate해 필수 replacement coverage를 충족하지 못했으므로 정확한 판정은
**`V2_NATIVE_EFFECT_OBSERVATION_NOT_QUALIFIED`**다. Native campaign은 계속 NOT_RUN이다.

## 4. 현재 어디까지 했는가?

G0 documentation freeze의 capability baseline은 main
**`8ad07b8e5f23f789d57ea50ba52c7acfcee951ea`**다. 최신 상태는 [STATUS](STATUS.md),
연구 정의와 claim boundary는 [Research Contract v1](research/design/research-contract-v1.md)를 따른다.

- Layer 2–3: immutable models, USTAR, Linux runtime, actual reference worker와 snapshot C0/C1/C2.
- Layer 4–5: legacy/M1 mutation, versioned protected-component addressing,
  B0/B1/B3 search, A1/A2 feedback keys와 A3 no-reorder, deterministic seed-inclusive
  bounded campaign. Default sentinel까지의 logical generation은 TESTED지만 historical
  target/setup qualification은 NOT_RUN.
- Layer 6 infrastructure: generic/USTAR minimization, readers, pair/benign replay,
  passive ledger/journal, qualification/matrix와 completed policy binding/dataset/statistics.
  N01 `7.5.2/7.5.3` exact images는 clean `e987c855` source와 trusted macOS/OrbStack
  controller에서 admission됐다. 8건 readiness와 10건 pair가 실행됐고 fresh-process reader는
  automated replay PASS를 재계산했다. Final human correspondence review는 pending이다.
- Entry-transition infrastructure: target-independent evidence model, P0/P1 retention,
  P2 bounded scheduler and checksummed evaluation/replay APIs are TESTED synthetically;
  native v1은 qualification에서 BLOCKED이고 producer/effectiveness는 NOT_IMPLEMENTED / NOT_RUN.
- Contained node-tar **7.5.22 benign smoke TESTED**. Helper/mock tests와 real extractor
  checks는 구분하며 어느 쪽도 historical qualification이나 effectiveness 결과가 아니다.

**DESIGNED ≠ IMPLEMENTED ≠ TESTED ≠ EXPERIMENTALLY VALIDATED.**
N01 historical automated replay는 완료됐지만 final qualification은
**`AWAITING_HUMAN_CORRESPONDENCE_REVIEW`**다. Rediscovery / formal comparison은 NOT_RUN이며
현재 취약점을 주장하지 않는다. 상세 결과와 identity는
[N02 qualification report](research/diagnostics/n02-autonomous-integration-and-qualification.md)를 따른다.
Snapshot은 persistent effect만 판정하며 transient/direct-use/symlink referent와 sandbox 밖 접근을
증명하지 못한다. Alternative policy 실행 API와 completed export가 있어도 automatic journal attachment,
failure-prefix 보존과 known-class adjudication은 별도 검증 과제다. Final-state policy의 별도
full-step monotonic timing evidence/reader는 TESTED engineering infrastructure이지만 formal timing
결과나 publication/failure timing은 아니다. G0 문서 동결은 후속 gate의 PASS가 아니다.

## 5. 코딩하기 전에 딱 이것만 읽기

### 모든 작업 공통

1. 이 문서
2. [STATUS.md](STATUS.md)
3. [../AGENTS.md](../AGENTS.md)

### 용어가 헷갈리면

- [GLOSSARY.md](GLOSSARY.md)

### 왜 이렇게 설계했는지 궁금하면

- [DECISIONS.md](DECISIONS.md)

### 연구 내용을 깊게 볼 때만

- [research/design/project-scope.md](research/design/project-scope.md)
- [research/design/architecture.md](research/design/architecture.md)
- [research/design/security-contracts.md](research/design/security-contracts.md)
- [research/design/research-contract-v1.md](research/design/research-contract-v1.md)
- [research/design/entry-transition-observation-v1.md](research/design/entry-transition-observation-v1.md)
- [research/design/entry-effect-observation-v2.md](research/design/entry-effect-observation-v2.md)
- [research/design/entry-effect-architecture-v2.md](research/design/entry-effect-architecture-v2.md)
- [research/design/entry-effect-feedback-v2.md](research/design/entry-effect-feedback-v2.md)
- [research/design/entry-effect-design-review-v2.md](research/design/entry-effect-design-review-v2.md)
- [research/design/transition-feedback-v1.md](research/design/transition-feedback-v1.md)
- [research/design/transition-mutation-scheduler-v1.md](research/design/transition-mutation-scheduler-v1.md)
- [research/design/research-questions.md](research/design/research-questions.md)
- [research/design/related-work-positioning.md](research/design/related-work-positioning.md)

## 6. 파일을 어디에 만들까?

폴더별 책임과 파일 배치 규칙은 [문서 지도](README.md)와 [엔진 모듈 지도](../src/inodefence/README.md)를 본다. 상세 pipeline과 데이터 흐름은 [architecture.md](research/design/architecture.md)가 기준이다. `pipeline.run_case`는 입력 하나를 실제 실행·관찰·판정한다. Generic Mutation v1은 별도 ArchiveCase 변형 API다. Feedback / Corpus v1은 독립 state/violation novelty로 parent를 보존하고 caller RNG로 균등 선택한다. Bounded campaign v1은 명시적 seed와 budget을 받아 API를 조합한다. Node-tar의 contained adapter와 tiny benign configured campaign을 검증했다. SearchCampaignConfig가 B0/B1/B3와 A1/A2/A3를 연결하고 evaluation APIs가 완료된 raw evidence를 검증한다. Transition P0/P1/P2 core와 verified evidence APIs는 synthetic producer로 테스트됐고 node-tar v1 native observation은 qualification failure로 blocked다. V2 Gate 2는 archive order, observed operation order와 evidence-supported causality를 분리하는 generic model, normalized feedback, fail-closed corpus와 bounded scheduler를 synthetic producer로 검증했다. Gate 3 contained fixture suite는 10/10 PASS다. Gate 4는 480회를 완료하고 independent reader로 재검증했지만 replacement coverage가 실패해 NOT_QUALIFIED다. Campaign과 효과 검증은 exact qualified token까지 blocked다. Automatic interrupted-run persistence와 full-step timing도 별도 과제다.

```text
src/inodefence/model/       공통 데이터 표현과 canonical JSON
src/inodefence/builder.py   결정적 USTAR 직렬화
src/inodefence/runtime.py   disposable runtime와 sentinel
src/inodefence/pipeline.py  입력 하나의 실행·관찰·판정 연결
src/inodefence/campaign.py  bounded campaign / parent lineage / full run evidence
src/inodefence/campaign_export.py  manifest.json / canonical steps.jsonl
src/inodefence/provenance.py  실행 전 source/environment/target/sentinel 설정 고정
src/inodefence/experiment_config.py  strict JSON 설정 / config ID / explicit 실행 binding
src/inodefence/generator/   명시적 minimal_seed_corpus (정상 baseline 4종)
src/inodefence/mutator/     TAR entry 변형
src/inodefence/targets/     공통 실행 경계 / Python reference / contained node-tar
src/inodefence/observer/    filesystem 상태 관찰
src/inodefence/oracle/      security contract 판정
src/inodefence/feedback/    signature v3 / fingerprints / B0/B1/B3 / A1/A2
src/inodefence/minimizer.py bounded generic / USTAR / evidence-bound minimization
src/inodefence/evaluation/ completed raw validation / qualification / dataset / statistics
src/inodefence/transition_campaign.py  P0/P1/P2 in-memory composition
src/inodefence/replay/     allowlisted benign clean replay

tests/                      코드 테스트
scripts/                    개발/실험 보조 명령
docs/research/              연구 근거와 설계
experiments/                실험 설정과 결과
findings/                   재현 가능한 finding
artifacts/                  의도적으로 보존할 생성물 (실행 sandbox 아님)
paper/                      논문에 실제로 사용할 자료
```

## 7. AI에게 작업시킬 때 기본 요청 형식

복잡한 프롬프트가 필요하지 않다. 최소한 다음 정보를 준다.

```text
현재 Layer:
작업 목표:
수정 가능한 모듈:
건드리면 안 되는 모듈:
완료 조건:
관련 contract:
```

예:

```text
현재 Layer: 2
작업 목표: ArchiveEntry data model 초안
수정 가능한 모듈: src/inodefence/model/
건드리면 안 되는 모듈: mutator, oracle
완료 조건: pytest 통과 + 타입 필드 설명 문서화
관련 contract: 아직 직접 적용 없음
```

## 8. 한 작업의 완료 조건

코드가 "돌아간다"만으로 끝내지 않는다.

최소한:

- 현재 architecture를 깨지 않았는가
- target-specific hack이 generic module에 들어가지 않았는가
- 새 동작을 테스트했는가
- 필요한 문서를 같이 고쳤는가
- Ruff/pytest가 통과하는가
- 팀원이 PR 설명만 보고 왜 바꿨는지 알 수 있는가

## 9. 가장 중요한 원칙

> **AI가 코드를 많이 만드는 것보다, 팀원이 그 코드가 프로젝트의 어느 Layer에 있고 왜 필요한지 설명할 수 있는 상태를 유지한다.**

이 프로젝트에서는 문서도 구현의 일부다.
