# Infrastructure readiness v1

이 기록은 execution provenance, safety gate, benign node-tar adapter와 explicit configuration
도입 이후의 engineering audit다. 전체 준비 상태는 **ENGINEERING FOUNDATION**이다.
Evidence 분류는 **REPRODUCIBLE (development semantic checks only)**이며 benchmark/evaluation,
vulnerability finding 또는 paper-ready evidence가 아니다.

## 실제 검증 기준점

Engine audit와 raw reference runs의 source는 clean main
`de8427e5be92ab905f898b72e07e800b9e593987`이다. 이후 PR #32의
`52add4e5e7735ab70ebf9232fe8c00f6c8776f8e`는 process 검사 테스트만 고치며 engine은 동일하다.
이 문서 PR도 runtime code를 바꾸지 않는다. 이전
[engineering audit](final-engineering-audit-v1.md)은 이전 revision의 역사적 기록으로 유지한다.

Supported Linux Dev Container에서 수행했다:

- Ubuntu 24.04, Python 3.12.3, Linux aarch64
- Kernel `7.0.14-orbstack-00380-ga7e0a2dc9535`; runtime `/var/lib/inodefence`
- Reference `python-tarfile-data`, version `3.12.3`, timeout 5 seconds
- Node adapter setup identity `node-tar-strict`, `node=22.22.0;tar=7.5.22`
- [Explicit config](../configs/reference-smoke-v1.json): seed 11, budget 8, minimal-generic-v1,
  uniform-generic-v1, state-v2-or-violation-v1-uniform-parent-v1, linux-development-v1
- Sentinel `sentinel.txt`, mode `0o600`, configured content SHA-256
  `caed2ac112733b3f5e3f56d9372f7ce6ba88dfafd57eb58807bb29f16548e36b`

Config ID는 `5a24679b4a55f55fa20272e8817c9fd8f7d97fc994495c964d2b37f0967863a0`이다.
Environment profile은 operator label이고 actual environment는 frozen provenance다. Source dirty는
두 run 모두 false로 기록됐다. Native macOS filesystem evidence를 사용하지 않았다.

## 실행 사실

| 실행 | Budget / 실제 실행 수 | Status | Interesting / retained / unique states | Violated contracts / fingerprints |
| --- | --- | --- | --- | --- |
| reference-1 | 8 / 8 | 8 SUCCESS | 5 / 5 / 5 | 0 / 0 |
| reference-2 | 8 / 8 | 8 SUCCESS | 5 / 5 / 5 | 0 / 0 |
| Node campaign entry check | 4 / 0 | 실행 전 거부 | 해당 없음 | 해당 없음 |

Reference 두 run의 index/origin/parent, logical case/TAR hash, feedback/signature/verdict,
initial/admission order와 stats가 일치했다. Raw inode/timestamp/duration/command runtime prefix는
비교 key가 아니며 export에 그대로 남는다. 각 JSONL의 checksum, stored config ID, budget/index와
삭제된 runtime root를 원본에서 검증했다. Config JSON은 두 run에서 동일 bytes이고 raw JSONL은
volatile evidence를 보존하므로 서로 다른 bytes다.

Node campaign은 `requires execution isolation; no validated boundary is available`로 거부됐다.
실제 Node adapter의 ordinary version discovery만 수행했고 provenance capture와 run_case가 호출되지
않도록 assertion을 걸었다. Runtime directory listing은 그대로였고 Node archive execution은 0회다.
Requirement를 낮추거나 low-level API로 campaign gate를 우회하지 않았다. Node의 ordinary 네 fixture,
invalid format/controlled timeout integration은 별도의 자동 테스트 범위다.

## 원본과 재검증

[기계 생성 요약](infrastructure-readiness-v1.json)은 source/config/environment, 실제 counts와 각
experiment.json/manifest.json/steps.jsonl checksum을 연결한다. 원본은 이 workspace의 Git-ignored
`experiments/raw/session-f-audit/`에 로컬 보관하고 공유 upload는 하지 않았다. 원본을 수정하지 않았다.

동일 Python/version/tooling의 supported Linux checkout에서 새 output으로 재실행한다:

```bash
python -m scripts.run_configured_reference experiments/configs/reference-smoke-v1.json --output experiments/raw/readiness-repeat-1
python -m scripts.run_configured_reference experiments/configs/reference-smoke-v1.json --output experiments/raw/readiness-repeat-2
```

Python patch가 다르면 exact config를 명시적으로 갱신하고 다른 config ID/environment로 기록한다.
이전 run의 raw checksums와 재실행 bytes가 같아야 한다고 요구하지 않는다. 아래 원본 projection으로
의미적 반복과 writer checksum/budget/cleanup을 확인한다:

```python
import json
from hashlib import sha256
from pathlib import Path

from inodefence.experiment_config import ExperimentConfig


def semantic(directory):
    config = ExperimentConfig.from_json((directory / "experiment.json").read_text())
    manifest = json.loads((directory / "manifest.json").read_bytes())
    raw = (directory / "steps.jsonl").read_bytes()
    assert sha256(raw).hexdigest() == manifest["steps_sha256"]
    assert config.config_id == manifest["experiment_config_id"]
    steps = [json.loads(line)["value"] for line in raw.splitlines()]
    assert len(steps) == manifest["number_of_steps"] == config.campaign.execution_budget
    assert [step["index"] for step in steps] == list(range(len(steps)))
    assert all(not Path(step["result"]["after"]["sandbox_root"]).exists() for step in steps)
    assert not any(v["violated"] for step in steps for v in step["result"]["violations"])
    projected = [
        (
            step["index"],
            step["origin"],
            step["parent_case_id"],
            step["feedback"],
            {
                key: step["result"][key]
                for key in ("case", "archive_format", "archive_sha256", "signature", "violations")
            },
            step["result"]["execution"]["status"],
        )
        for step in steps
    ]
    return (
        projected,
        manifest["initial_case_ids"],
        manifest["final_corpus_stats"],
        manifest["retained_case_ids"],
    )


root = Path("experiments/raw")
assert semantic(root / "readiness-repeat-1") == semantic(root / "readiness-repeat-2")
```

이 검사는 completed-result 검증이며 campaign stop policy는 아니다. Unexpected evidence가 나오면
추가 campaign을 시작하지 않고 원본을 보존해 사람의 review로 넘긴다. Node campaign smoke는 실행하지 않았다.

## Audit와 validation

Model, builder, runtime, generator, mutator, pipeline, campaign, feedback, observer, oracle, targets,
provenance, export, experiment config, tests와 canonical docs를 읽었다. 34 core Python modules / 73
static internal import edges에서 cycle은 없었다. Static graph는 dynamic/plugin imports까지 증명하지 않는다.

| 경계 | 확인한 구현 |
| --- | --- |
| Configuration / evidence | source/env/target/sentinel은 첫 실행 전 freeze; result/export는 stored 값; observed/exporter contexts는 별도 |
| Portable identity | config는 canonical JSON hash; result/source/kernel/inode/time은 config ID에 없고 signature/fingerprint도 raw identity 제외 |
| Search / execution | explicit unique seeds, seed-inclusive budget, 한 campaign RNG, no retry, 모든 status 보존, run_case는 한 execution |
| Module responsibilities | generic mutation/observer/oracle/feedback에 Node logic 없음; target은 invocation/version/status/streams 소유 |
| Filesystem / lifecycle | Linux runtime의 controlled sentinel, no-follow observation, BEFORE/AFTER 밖의 bookkeeping, symlink-resistant cleanup |
| Safety | runtime/Dev Container는 OS sandbox가 아님; Node는 ISOLATION_REQUIRED로 campaign fail-closed |

Engine base의 focused checks는 116 passed, local make check는 459 passed였다. Main CI는 이후
reaped child의 /proc read에서 ESRCH를 반환한 test race로 458 passed / 1 failed였다.
[PR #32](https://github.com/TheWaitForAGI/InodeFence/pull/32)에서 deterministic red regression을 실행하고
ENOENT/ESRCH만 absence로 처리했다. Readable live child와 PermissionError는 여전히 실패한다.
Focused Node/process는 19 passed, Dev Container make check는 462 passed,
[최종PR CI](https://github.com/TheWaitForAGI/InodeFence/actions/runs/37167092056)도 SUCCESS였다.
Ruff/format/Pyright/environment/docs와 git diff --check는 PASS. Fixtures 재생성과 4 probes도 PASS이며
기존 TAR bytes는 불변이다. Test 삭제/skip이나 contract assertion 약화는 없다.

## 남은 준비 조건

Reference engine은 ENGINE READY이고 전체는 ENGINEERING FOUNDATION이다. Benchmark-ready에는
별도로 validated OS process/filesystem/credential/network/resource boundary, 전체 child shutdown
검증과 tiny benign Node campaign smoke가 필요하다. Process-group kill/direct-child wait로 대신하지 않는다.
Same-version dependency content의 runtime attestation, source dirty patch 보존과 완전한 environment
locking은 미제공이다. Snapshot은 transient operation/sandbox 밖 effects/actor attribution을 증명하지 않는다.
Adaptive/resume/ablation policy와 비교 평가도 미구현/미실행이다.

다음 engineering PR은 execution isolation boundary이고, 다음 사람이 review할 연구 task는 그 격리와
benchmark 설정·controls/metrics/반복 계획 승인이다. Known-vulnerability reproduction, security campaign,
finding minimization이나 exploit 생성은 별도의 명시적 Task Contract까지 진행하지 않는다.
