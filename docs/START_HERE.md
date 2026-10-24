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

여기에 더해 "extraction이 다 끝난 뒤의 상태"뿐 아니라 **"entry 하나하나가 처리되는 동안의
중간 상태"**를 feedback으로 쓰면 같은 budget에서 더 나은 다음 입력을 고를 수 있는지도 묻는다.
이것도 **가설**이며 아직 **결과**가 아니다. 중간 상태를 어떻게 관찰하기로 했는지(v1 방식은
qualification에서 실패했고, 지금은 v2 "effect event" 방식을 쓴다)와 그 한계는
[STATUS](STATUS.md)의 상세 기록과
[entry-effect-observation-v2](research/design/entry-effect-observation-v2.md)를 따른다.

## 4. 현재 어디까지 했는가? (2026-10-24 기준)

한 줄 요약: **실제 node-tar 7.5.22를 대상으로 "입력 생성 → 실행 → entry별 중간 상태 관찰 →
C0/C1/C2 판정 → feedback → 다음 mutation 선택" 루프가 `make demo` 한 명령으로 돌아간다.**
같은 조건(seed 123, budget 20)으로 다시 돌리면 같은 루프가 나온다(호스트에서 4회 확인).

11/2 중간발표 목표(P0-1~P0-5)별 상태는 [STATUS 맨 위 표](STATUS.md)가 기준이다. 목표 정의는
[MIDTERM_GOALS](MIDTERM_GOALS.md), 할 일 순서는 [BACKLOG](BACKLOG.md), 실행 기록은 [LOG](LOG.md)다.

지금 돌아가는 것:

| 명령 | 어디서 | 무엇을 하는가 |
| --- | --- | --- |
| `make demo` | 호스트 터미널 (docker 필요) | 격리 컨테이너에서 node-tar를 실제로 실행하는 루프. 결과 JSON은 `~/inodefence-evidence/`에 남는다 |
| `make demo-synthetic` | Dev Container | node-tar 없이 synthetic producer로 같은 루프. 결과에 `SYNTHETIC (not node-tar)` 라벨이 붙는다 |
| `make node-tar-smoke` | 호스트 터미널 | node-tar 실행 환경이 되는지 확인 |
| `python -m scripts.oracle_fixture_check` | Dev Container | C0/C1/C2 판정이 의도한 fixture에서 맞게 나오는지 확인 (통제 extractor, node-tar 아님) |
| `make check` | Dev Container | lint·타입·테스트·환경·문서 링크 검사 |

아직 안 된 것, 그리고 주장하지 않는 것:

- 취약점을 찾았다거나 재발견했다는 주장은 없다. `make demo`의 정상 입력 20개에서 C0/C1/C2 위반은 0건이다.
- N01(과거 취약 버전 node-tar 7.5.2/7.5.3 재발견)은 자동 replay까지 끝났고 사람 검토를 기다린다.
  재발견 실행은 사람 승인 뒤(10/27~)에만 한다.
- A/B/C(random / structure-aware / state-aware) 비교 실험은 하지 않았다. 중간발표 이후 과제다.
- node-tar가 거부한 입력(`..` 경로, 절대 경로)에서는 중간 상태 event가 0개로 남는다.
  이 한계를 어떻게 표현할지 아직 정하지 않았다.

**DESIGNED ≠ IMPLEMENTED ≠ TESTED ≠ EXPERIMENTALLY VALIDATED.**
"구현돼서 돌아간다"와 "연구 가설이 맞다"는 다르다. 지금은 앞쪽이다.
2026-10-18 이전의 Layer별 상세 이력과 영어 용어가 많은 기록은 [STATUS](STATUS.md) 하단에 있다.

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

읽는 순서대로 4개만 본다.

1. [security-contracts.md](research/design/security-contracts.md) — C0/C1/C2가 무엇을 위반으로 보는가
2. [architecture.md](research/design/architecture.md) — 전체 pipeline과 모듈 책임
3. [entry-effect-observation-v2.md](research/design/entry-effect-observation-v2.md) — entry별 중간 상태를 어떻게 관찰하는가
4. [entry-effect-feedback-v2.md](research/design/entry-effect-feedback-v2.md) — 관찰 결과가 어떻게 다음 mutation 선택에 쓰이는가

나머지 설계 문서(연구 범위, research contract, transition v1, rebinding v3 제안 등)는
[설계 문서 목록](research/design/README.md)에서 찾는다. 설계 문서 본문은 대부분 영어다.

## 6. 파일을 어디에 만들까?

폴더별 책임은 [문서 지도](README.md)와 [엔진 모듈 지도](../src/inodefence/README.md), 상세 데이터
흐름은 [architecture.md](research/design/architecture.md)를 본다.

`make demo`가 실제로 지나가는 코드 경로는 다음이다. 루프의 부품은 이미 다 있으니 새로 만들기보다
이 경로 안에서 고친다.

```text
scripts/local_node_tar_smoke.sh demo          호스트에서 컨테이너를 띄우고 아래를 실행
  scripts/container_controller.py             컨테이너 안 진입점 (effect-demo)
    scripts/run_effect_demo.py                demo report JSON 작성 (step별 trace·selection)
      effect_campaign.run_effect_campaign     루프: parent 선택 → mutate → 실행 → 관찰 → 판정 → feedback
        effect_pipeline                       node-tar 1회 실행 + entry별 effect trace 수집
        oracle/                               C0/C1/C2 판정
        feedback/effect.py                    effect trace → feedback key → corpus 편입 여부
        effect_scheduler.py                   operator 가중치(reward) 갱신과 다음 operator 선택
        mutator/                              선택된 operator로 TAR entry 변형
```

```text
src/inodefence/model/       공통 데이터 표현과 canonical JSON
src/inodefence/builder.py   결정적 USTAR 직렬화
src/inodefence/runtime.py   disposable runtime와 sentinel
src/inodefence/pipeline.py  입력 하나의 실행·관찰·판정 연결 (최종 상태 snapshot 경로)
src/inodefence/effect_pipeline.py  입력 하나의 node-tar 실행 + entry별 중간 effect 관찰 (make demo 경로)
src/inodefence/effect_campaign.py  effect feedback 루프 (parent 선택 → mutate → 실행 → feedback)
src/inodefence/effect_scheduler.py  operator 가중치와 reward 기록 (P2 adaptive)
src/inodefence/effect_demo.py  demo report: step별 trace 라벨(archive/observed/derived)과 선택 근거
src/inodefence/effect_synthetic.py  node-tar 없이 돌리는 synthetic producer (native 증거 아님)
src/inodefence/mutation_scheduler.py  재현 가능한 operator 선택 (mutation 함수와 분리)
src/inodefence/campaign.py  최종 상태 기반 bounded campaign / parent lineage
src/inodefence/campaign_export.py  manifest.json / canonical steps.jsonl
src/inodefence/provenance.py  실행 전 source/environment/target/sentinel 설정 고정
src/inodefence/experiment_config.py  strict JSON 설정 / config ID / explicit 실행 binding
src/inodefence/generator/   명시적 minimal_seed_corpus (정상 baseline 4종)
src/inodefence/mutator/     TAR entry 변형 (8개 generic operator)
src/inodefence/targets/     공통 실행 경계 / Python reference / contained node-tar / effect producer(.cjs)
src/inodefence/observer/    filesystem 상태 관찰
src/inodefence/oracle/      security contract 판정
src/inodefence/feedback/    최종 상태 feedback(B0/B1/B3, A1/A2)와 effect feedback v2 (effect.py)
src/inodefence/minimizer.py bounded generic / USTAR / evidence-bound minimization
src/inodefence/evaluation/ completed raw validation / qualification / dataset / statistics
src/inodefence/transition_campaign.py  transition v1 P0/P1/P2 composition (현재 demo 경로 아님)
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
해당 P0 (또는 Layer):
작업 목표:
수정 가능한 모듈:
건드리면 안 되는 모듈:
완료 조건:
관련 contract:
```

예:

```text
해당 P0: P0-4
작업 목표: demo report의 selection에 parent 선택 근거 한 줄 추가
수정 가능한 모듈: scripts/run_effect_demo.py, src/inodefence/effect_demo.py
건드리면 안 되는 모듈: oracle, effect_scheduler (판정·선택 의미 변경 금지)
완료 조건: make check 통과 + synthetic report 테스트 + 호스트 make demo 1회 후 LOG 한 줄
관련 contract: 없음 (보고 형식만 바뀜)
```

작업 단위는 [BACKLOG](BACKLOG.md)에서 고르고, 끝나면 [LOG](LOG.md)에 한 줄 남긴다.
새 감사·계획 문서를 만들지 않는다(AGENTS.md 금지 사항).

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
