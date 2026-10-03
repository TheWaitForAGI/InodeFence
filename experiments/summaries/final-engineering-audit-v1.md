# 최종 engineering audit v1

대상 canonical main은 `240dbf7a0c9170dd9803ab91dace3600bf52c002`다. Audit은 engineering
correctness/reproducibility 검토이며 effectiveness, finding 또는 paper evidence가 아니다.
Evidence 분류는 **REPRODUCIBLE (development semantic checks only)**다.

Model, builder, runtime, pipeline, campaign, generator, mutator, observer, oracle, feedback,
reference target, structured export, tests와 affected docs를 읽었다. 정적 internal import graph의
28개 module에서 cycle이 없었다. Caller-owned RNG, ordered tuple/admission order, no-op/no-retry,
seed-inclusive budget, 네 status 보존, harness exception 전달, raw evidence와 portable keys의
분리, immutable return collections와 Linux runtime 경계를 확인했다. Snapshot-only 한계와
source/실행 환경 provenance 누락은 기존 문서에 명시된 제한으로 유지한다. 새 source defect를
확인하지 못했으며 README의 stale runner/CLI 설명은 PR #26에서 바로잡았다.

Final source head의 Dev Container `make check`: **377 passed**, Ruff/Pyright/environment/docs
검사 PASS. `git diff --check` 및 session 전체 diff 검사 PASS.
Main [CI](https://github.com/TheWaitForAGI/InodeFence/actions/runs/37137542368)도 SUCCESS다.
기존 regression을 변경/삭제/skip하지 않았다.

추가로 같은 `minimal_seed_corpus()`, RNG seed 71, budget 25와 Python tarfile/data reference를
별도 Python process의 `PYTHONHASHSEED=17`, `999`로 각각 실행했다. Target timeout은 10 seconds,
Python 3.12.3 / Linux aarch64 / `/var/lib/inodefence`다. 두 campaign 모두 25 steps/observations로
종료했고 모든 run sandbox가 정리됐다. 두 semantic digest가 같았다:

```text
27d8bcf4462fc0b57ec7e6445c901dd563c937f8a47f049e9c7f4d7559154dc8
```

Digest는 index/origin/parent, canonical ArchiveCase와 FeedbackDecision, final stats/retained
ordering만 비교한다. Raw inode/timestamp/duration은 제외했다. 각 완료 result는 production
exporter로 manifest.json/steps.jsonl에 보존했고 checksum을 검증했다.
[기계가 생성한 작은 요약](final-engineering-audit-v1.json)은 raw 경로, checksums와 실행 전에
확인한 source/Python/platform/config/timeout provenance를 담는다. 원본은 이 workspace의
Git-ignored experiments/raw/final-main-audit-hashseed-{17,999}/에 로컬 보관하며 공유 upload는 없다.

요약의 semantic digest는 raw JSONL의 위 field projection을 sorted-key compact JSON으로 encode한
SHA-256이며, audit stdout만 신뢰하지 않고 raw에서 다시 계산했다. 원본은 수정하지 않았다.
동일 검증을 재실행하려면 두 hash seed 각각으로 Dev Container Python에서 아래 API를 호출해
새 output에 기록하고 같은 projection을 비교한다. 기존 raw destination은 덮어쓰지 않는다.

```python
result = run_campaign(minimal_seed_corpus(), PythonTarfileTarget(), CampaignConfig(71, 25))
export_campaign(result, new_output_directory)
```

이 audit은 정적 검토와 소규모 개발 검증이며 모든 입력/환경에 대한 correctness 증명은 아니다.
다음 engineering 작업은 source revision, execution environment와 explicit sentinel/adapter
configuration을 **실행 시점**에 기록할 작은 caller-level provenance contract다. Export 시점의
환경을 과거 실행 환경으로 추정하지 않는 기존 경계를 유지한다. Third-party target 테스트,
C3/C4, coverage/adaptive/parallel fuzzing과 formal evaluation은 이번 세션 범위 밖이다.
