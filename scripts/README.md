# 개발 보조 명령

## 이 폴더는 무엇인가

개발환경 확인 등 저장소 작업을 보조하는 명령을 둔다.

## 입력

Python 환경과 INODEFENCE_RUNTIME_ROOT를 읽는다. manual_tar_probe.py는 작은 baseline TAR 경로를 입력받는다.

## 출력

환경 검사 결과, 재생성된 fixture TAR, 사람이 읽을 수 있는 filesystem metadata.

## 책임

check_dev_env.py는 임시 sandbox에서 hardlink identity, symlink, 공유 object write effect를 확인한다.

check_docs.py는 Git-visible Markdown의 상대경로 링크와 canonical 문서 존재를 검사한다. fenced/indented/inline code와 외부 URL, anchor-only 링크는 제외한다. 완전한 Markdown parser나 anchor 검사는 아니다.

generate_tar_fixtures.py는 4종 TAR baseline과 C0/C1/C2 oracle-check fixture 3종을 재생성한다. oracle_fixture_check.py는 정상 1·C0/C1/C2 각 1 fixture를 경계 검사 없는 통제 extractor로 실행해 실제 Observer/Oracle 판정을 출력한다(controlled oracle check, node-tar 결과 아님). manual_tar_probe.py는 Linux runtime sandbox에 TAR를 풀고 lstat/readlink 결과를 출력한 뒤 sandbox를 삭제한다.

## 하지 않는 것

퍼저 구현, 실제 host 민감 파일을 대상으로 한 실험.

## 다른 모듈과의 연결

[Dev Container](../.devcontainer/README.md) 안에서 python scripts/check_dev_env.py로 실행한다. 환경 기준은 [환경 설계](../docs/research/design/development-environment.md)를 따른다.

## 현재 상태

환경 확인과 [TAR baseline 예제](../docs/examples/tar-baseline.md)의 fixture 생성·수동 관찰 명령이 있다. Safe reference의 bounded campaign 개발 pilot과 strict config CLI가 있다. 일반 target 선택/benchmark CLI는 없다.

## 파일 배치 규칙

사용 목적을 알 수 있는 스크립트명과 입력 설정을 남긴다. 공통 엔진 로직은 src에 두고 raw output은 실험 기록으로 관리한다.

`python -m scripts.reference_campaign_pilot --output experiments/raw/<new-directory>`는 safe
Python reference만 사용하는 7개 작은 bounded campaign의 개발 검증이다. Explicit baseline
seeds, provenance, raw canonical results와 generated summary를 기록하며 exact repeat의 semantic
lineage/feedback, budget/cleanup을 assertion으로 검사한다. 기존 output을 덮어쓰지 않는다.
효과 평가나 일반 third-party campaign CLI는 아니다.

`python -m scripts.run_configured_reference <config.json> --output <new-directory>`는
[ExperimentConfig v1](../experiments/configs/README.md)을 읽고 explicit minimal seeds/actual target
binding을 실행 전에 검증한다. Safe Python reference만 지원하며 config version과 실제 Python
version이 다르면 거부한다. Stored config ID/frozen provenance와 experiment.json/manifest.json/
steps.jsonl을 보존한다. Node campaign safety gate를 우회하는 명령은 없다.

`python scripts/check_linux_isolation_support.py` (`make isolation-support`)는 Linux namespace
생성 전제 조건을 JSON schema v1로 진단한다. 고정된 `unshare`/`true` 8개 probe만 실행하며
mount operation, fork, network traffic, archive extraction이나 runtime 생성은 하지 않는다.
Mount probe는 `--propagation unchanged`로 util-linux의 자동 propagation 변경도 생략한다.
5개 user-namespace 조합이 모두 성공하면 exit 0, 그 외에는 exit 1이다. Tool 존재와 syscall
실패를 구분하고 missing tool/platform, timeout/launch error와 실제 stderr를 보존한다.
`/proc`의 capability/seccomp, cgroup mount read-only 여부와 현재 resource limits도 기록한다.
Resource limit의 -1은 unlimited이며 이 명령은 limit을 설정하지 않는다.

Exit 0도 filesystem view/network 차단/credential 제한/child cleanup을 검증하지 않는다.
결과는 campaign gate의 입력이나 execution provenance가 아니며 target 실행을 허가하지 않는다.
환경마다 재실행해야 하므로 canonical `make check`와 분리한다.
[현재 환경 blocker](../experiments/summaries/linux-isolation-support-v1.md)를 따른다.

`PYTHONPATH=src python scripts/qualify_node_transition_observation.py --output <new-file>`는
pinned Node 22.22.0/node-tar 7.5.22의 entry completion 관찰 후보를 정상 fixture에서만 비교한다.
Public async/sync event, Linux inotify, strace, fresh-process prefix replay와 Python reference의
per-member 호출을 기록하며 기존 output을 덮어쓰지 않는다. 결과는 raw qualification evidence이고
native adapter, Security Contract verdict 또는 transition-feedback 효과 결과가 아니다.

`PYTHONPATH=src python scripts/qualify_node_internal_completion.py --output <new-file>`는 같은
pinned target의 실제 package entrypoint에 포함된 private `checkFs2` completion callback을
source hash guard 아래 관찰한다. Stock, marker-only, callback-time snapshot profile을 benign
mixed/directory-child/independent-file fixture에서 비교하고 exact association, completion order,
후속 entry effect 포함, snapshot failure, final semantic equivalence와 overhead를 기록한다.
설치 package를 수정하지 않으며 결과가 current `TransitionTrace` producer qualification을
통과하기 전까지 target adapter로 사용할 수 없다.
`PYTHONPATH=src:. python scripts/analyze_node_internal_completion.py <raw.json>`은 고정 fixture
identity를 확인하고 raw run에서 mechanical summary를 다시 계산해 저장된 summary와 byte-level
동등성을 검증한다. `--output`은 기존 파일을 덮어쓰지 않는다.

`PYTHONPATH=src python scripts/qualify_node_causal_effects.py --output <new-file>`는
`AsyncLocalStorage`로 private entry identity의 비동기 문맥을 전파하고 Node `fs` callback API의
완료를 entry ordinal에 귀속한다. Stock, context-only, effect-event profile을 8개 benign fixture에서
비교하며 정상 완료뿐 아니라 첫 entry 완료 후 hardlink 실패로 거부되는 경우도 기록한다. 이
mechanism은 callback-time tree snapshot을 checkpoint로 재사용하지 않는다. 더 늦은 ordinal의
filesystem operation이 더 이른 entry completion marker 전에 완료되는지를 직접 판정하는 Phase A
feasibility probe이며, event log 자체는 완전한 `EntryCheckpoint`나 native producer가 아니다.
`PYTHONPATH=src:. python scripts/analyze_node_causal_effects.py <raw.json>`은 case/archive identity를
확인하고 저장된 mechanical summary를 독립적으로 재계산한다.

`PYTHONPATH=src:. python scripts/verify_node_effect_evidence.py <bundle>
--manifest-sha256 <sha256>`는 Gate 3 bundle의 raw frame에서 lifecycle/effect/causal trace와
normalized keys를 독립적으로 재구성한다. `scripts.container_host ...
qualify-node-effect-v2 --evidence <new-absolute-path>`는 pinned contained target에서 8 fixtures,
stock/minimal/full 각 20회, timeout/overflow/backend failure와 required invalid-stream injection을
실행한다. Output은 덮어쓰지 않으며, 모든 필수 criterion이 평가된 경우에만 정확한 Gate 4
decision token을 기록한다.

## 로컬 node-tar smoke (`make node-tar-smoke`, `make node-tar-effect-check`)

`scripts/local_node_tar_smoke.sh`는 CI `container-integration` job을 로컬 이름
(`inodefence-*:local` image, `inodefence-local-controller`, `inodefence-local-runtime`)으로 재현한다.
image 빌드 → non-root controller 준비 → `scripts.container_host`로 `validate`,
`validate-node-image`, `validate-node-target`, `benign-node-smoke`를 실행하고 evidence를
`~/inodefence-evidence/inodefence-node-smoke-<timestamp>`로 복사한다. `effect` 모드
(`make node-tar-effect-check`)는 `validate-node-effect-producer`만 실행한다. 성공·실패와 무관하게
이번 실행이 만든 controller와 volume만 제거하며, 같은 이름의 자원이 이미 있으면 지우지 않고
종료한다. Context는 `docker context show` 값이고 `INODEFENCE_DOCKER_CONTEXT`, `PYTHON`
(기본 `python3.12`), `INODEFENCE_EVIDENCE_DIR`로 바꿀 수 있다. 실패하면 `FAILED at step: <단계>`를
출력한다. 결과는 demo/engineering run이며 qualification이 아니다.

## 여러 native 캠페인 병렬 실행 (`scripts/run_parallel_native.py`)

한 호스트에서 `version × arm × seed` 매트릭스를 병렬로 돌린다. 각 셀은 `local_node_tar_smoke.sh`를
고유한 `RUN_ID`로 실행해 컨트롤러·볼륨·evidence 파일이 서로 충돌하지 않게 하고(`RUN_ID`가 비어
있으면 기존 단일 실행 이름 그대로), 동시 실행 수는 `--jobs` 세마포어로 제한한다(노트북 호스트는
3~4 권장). 공용 이미지는 `BUILD_ONLY`로 한 번만 빌드하고 각 셀은 `SKIP_BUILD`로 재사용하므로 콜드
빌드가 N번 겹치지 않는다. **격리는 그대로**다 — 모든 셀이 단일 `make demo` /
`make demo-native-historical`와 동일한 trusted non-root 컨트롤러와 contained-target 정책을 쓴다.
매트릭스가 바꾸는 것은 자원 이름과 캠페인 파라미터(seed·budget·policy arm)뿐이다. docker가 있는
호스트 터미널에서만 실행된다.

```bash
PYTHONPATH=src python3.12 -m scripts.run_parallel_native \
  --mode demo-historical --versions 7.5.2,7.5.3 --seeds 123,456,789 \
  --arm default --budget 100 --jobs 3 \
  --output ~/inodefence-evidence/<new-dir>
```

`--arm`은 `default`(스크립트 in-code 기본 정책) 또는 `LABEL=SEARCH/MUTATION`이며 SEARCH/MUTATION은
`EffectSearchPolicy`/`MutationPolicy` 멤버 이름(또는 `-`로 해당 쪽 기본 유지)이다. 반복 지정으로 여러
arm을 비교한다. 결과는 `<output>/<run-id>.json`(demo 모드는 `.steps.jsonl`도), 셀별 콘솔 로그는
`<output>/<run-id>.log`, 요약 manifest는 `<output>/matrix.json`에 남는다. 모든 셀이 성공해야 exit 0이다.
`--dry-run`은 docker 없이 계획된 매트릭스만 출력한다. 결과는 demo/engineering run이며 qualification이
아니다. (격리 완화 플래그는 추가하지 않는다 — 가드 R3/R5.)

## 클라우드 러너 플릿으로 팬아웃 (`.github/workflows/experiment-fanout.yml`)

단일 호스트의 `--jobs` 상한을 넘겨 처리량을 늘리려면 GitHub Actions 러너 플릿으로 캠페인을
팬아웃한다. `workflow_dispatch`로 수동 실행하며(`mode`·`versions`·`seeds`·`arm`·`budget` 입력),
`plan` job이 `run_parallel_native --emit-github-matrix`로 셀 매트릭스를 만들고 `fanout` job이 셀마다
**독립 러너**에서 CI `container-integration`과 동일한 경로로 한 캠페인을 돌린 뒤 evidence를 artifact로
올린다. 러너는 docker가 있는 Ubuntu 24.04라(이미 CI가 매 실행 이 하너스를 돈다) **잠긴 하너스가
그대로 돈다** — 이미지 빌드·trusted non-root 컨트롤러·contained-target 정책·budget 상한 100은 전부
단일 호스트 실행과 동일하고, 격리 완화 플래그는 없다. `demo-historical`의 affected/fixed effect
이미지는 러너에서 committed 레시피(`tools/node-tar/effect/Dockerfile` +
`tools/node-tar/versions/<버전>/`)로 빌드하며, 취약 이미지를 외부에 publish하지 않는다(러너 안에서만
쓰고 폐기한다).

셀 식별자(run_id)·evidence 파일명·arm 파라미터는 `run_parallel_native`의 `build_cells`가 단일 소스라
클라우드 팬아웃과 노트북 실행이 동일하게 이름 붙고 파라미터가 매겨진다. 디스패치는 저장소의 Actions
분(minutes)을 쓰고 실제 캠페인을 돌리므로 승인된 안전 범위(고정 버전, disposable sandbox + sentinel)
안에서만 사용한다. 결과는 demo/engineering run이며 qualification이 아니다.

참고로 Claude 클라우드 에이전트 환경은 Dev Container와 동일하게 docker-in-docker가 없어 이 하너스를
돌릴 수 없다 — 그런 환경에는 코드·분석만 보내고 docker 실험은 호스트 터미널이나 이 GHA 팬아웃으로
돌린다.

## N01 historical pair (explicit trusted-host action)

N01 is a separate bounded mode, not part of the normal `7.5.22` image/target checks. On the
trusted macOS/OrbStack host, use a clean checkout of the reviewed PR #95 head and Python 3.12.
The existing Dev Container remains the controller; do not mount its Docker socket or add
privilege. Before building, independently fetch and verify the two package tarballs outside
both the source tree and build contexts:

```bash
mkdir /private/tmp/inodefence-n01-tarballs-20261015-review1
curl --fail --location --proto '=https' --tlsv1.2 \
  https://registry.npmjs.org/tar/-/tar-7.5.2.tgz \
  --output /private/tmp/inodefence-n01-tarballs-20261015-review1/tar-7.5.2.tgz
curl --fail --location --proto '=https' --tlsv1.2 \
  https://registry.npmjs.org/tar/-/tar-7.5.3.tgz \
  --output /private/tmp/inodefence-n01-tarballs-20261015-review1/tar-7.5.3.tgz
shasum -a 256 /private/tmp/inodefence-n01-tarballs-20261015-review1/tar-7.5.2.tgz \
  /private/tmp/inodefence-n01-tarballs-20261015-review1/tar-7.5.3.tgz
```

The output must be exactly `22d8b674a68754ea909d03aa13958a7d2fd5e78af8a8f0cde6455babef7aaf1a`
for 7.5.2 and `9d95d0cf786786360f97c1e414caea8a14452dc337fda17ba256ae7762c2ec66`
for 7.5.3. A mismatch stops the attempt. Then prepare and build two new exact-lock contexts
outside the source tree; every destination below must be absent before the command:

```bash
PYTHONPATH=src python3.12 -m inodefence.evaluation.node_packaging prepare \
  experiments/benchmarks/locks/node-tar-7.5.2.package-lock.json \
  /private/tmp/inodefence-n01-7.5.2 --repository "$PWD"
PYTHONPATH=src python3.12 -m inodefence.evaluation.node_packaging prepare \
  experiments/benchmarks/locks/node-tar-7.5.3.package-lock.json \
  /private/tmp/inodefence-n01-7.5.3 --repository "$PWD"
PYTHONPATH=src python3.12 -m inodefence.evaluation.node_packaging build \
  /private/tmp/inodefence-n01-7.5.2 --docker-context orbstack
PYTHONPATH=src python3.12 -m inodefence.evaluation.node_packaging build \
  /private/tmp/inodefence-n01-7.5.3 --docker-context orbstack
```

Read the two full `sha256:...` values from their `build.json` files. With the existing trusted
controller and `inodefence-runtime` volume, resolve the controller to its full ID and print the
two build records for review:

```bash
docker --context orbstack inspect --format '{{.Id}}' <running-dev-container-name-or-id>
python3.12 -c 'import json,sys; print(json.load(open(sys.argv[1]))["image_id"])' \
  /private/tmp/inodefence-n01-7.5.2/build.json
python3.12 -c 'import json,sys; print(json.load(open(sys.argv[1]))["image_id"])' \
  /private/tmp/inodefence-n01-7.5.3/build.json
```

Use those exact three full IDs and a new evidence name in the following command. Arguments and
build contexts are in affected/fixed order:

```bash
PYTHONPATH=src python3.12 -m scripts.container_host \
  --context orbstack --controller <full-controller-id> \
  --volume inodefence-runtime \
  --image <affected-full-image-id> --image <fixed-full-image-id> \
  --build-context /private/tmp/inodefence-n01-7.5.2 \
  --build-context /private/tmp/inodefence-n01-7.5.3 \
  --evidence /var/lib/inodefence/evidence/<new-n01-attempt> \
  qualify-node-n01
```

The host validates both completed build contexts before starting the controller. The
controller repeats metadata-only admission before any archive, executes the fixed budget and
launches the independent reader as a fresh Python process. Build context bytes, raw records,
failure records, `raw-manifest.json`, `independent-verification.json` and the last-published
`manifest.json` are stored at the new evidence path. Copy that directory out read-only for
review; do not rerun a failed attempt into the same destination and do not replace an image ID
with a mutable tag. A run that reaches the automated token still requires the contract's human
correspondence review before `N01_RELATIVE_HARDLINK_PAIR_QUALIFIED` may be recorded.

## N04 five-second preflight (explicit trusted-host action)

The v1 single attempt is **consumed** and its result is `PREFLIGHT_INCONCLUSIVE`; the command below
documents the executed invocation and must not be rerun. See the
[result record](../docs/research/diagnostics/n04-five-second-preflight-result.md). A new execution
requires a new explicit Task Contract, attempt ID and evidence destinations.

`preflight-node-n04-5s` is distinct from N01 qualification. It accepts only the frozen
7.5.2/7.5.3 image IDs and retained affected/fixed build contexts in that order, attests a
new unprivileged controller with exactly the source bind and the dedicated
`inodefence-n04-preflight-runtime-20261016T130000Z` volume,
and enforces one 30-minute broker/controller deadline. The source must be a clean reviewed
commit and the evidence path must not exist.

```bash
PYTHONPATH=src python3.12 -m scripts.container_host \
  --context orbstack --controller <full-controller-id> \
  --volume inodefence-n04-preflight-runtime-20261016T130000Z \
  --image <frozen-7.5.2-image-id> --image <frozen-7.5.3-image-id> \
  --build-context /Users/choijiwng/Projects/InodeFence-n02-evidence-20261015T122200Z/build/affected \
  --build-context /Users/choijiwng/Projects/InodeFence-n02-evidence-20261015T122200Z/build/fixed \
  --package-tarball /Users/choijiwng/Projects/InodeFence-n04-package-inputs-20261017/tar-7.5.2.tgz \
  --package-tarball /Users/choijiwng/Projects/InodeFence-n04-package-inputs-20261017/tar-7.5.3.tgz \
  --evidence /var/lib/inodefence/evidence/n04-five-second-preflight-20261016T130000Z \
  --host-ledger /Users/choijiwng/Projects/InodeFence-n04-5s-preflight-20261016T130000Z-host-ledger \
  preflight-node-n04-5s
```

The mode runs two harness-only controls and at most eight benign target extractions at an
exact five-second timeout, then launches the independent reader in a fresh process. It does
not run the 4,000-execution pilot, a known-class pair or P0/P1/P2. Follow the frozen N04 Task
Contract for the exact identities, single destination and stop conditions. The two official
npm tarball bytes are retained in the evidence root and must match the predeclared SHA-256
values; an alternate evidence or host-ledger path is rejected rather than treated as another
attempt. The exact host ledger is created before Docker inspection, so it retains early admission,
deadline and target-cleanup outcomes even when the Linux evidence root cannot be completed. The Linux
reader status remains host-cleanup-pending. After copying the Linux evidence read-only,
`verify_n04_host_ledger(HOST_LEDGER, LINUX_EVIDENCE_COPY,
expected_manifest_sha256=TRUSTED_HOST_MANIFEST_SHA256)` independently rehashes both manifests,
validates the frozen invocation fields and derives the overall status; a missing terminal summary or
failed fallback cleanup is
`PREFLIGHT_INCONCLUSIVE`, never `PREFLIGHT_PASS`.

The consumed v1 ledger remains readable as `inodefence-n04-host-ledger-v1`. The host
orchestration now also has a fail-closed `inodefence-n04-host-ledger-v2` publication path for
future separately versioned preflights: once a controller process is launched, it drains at most
the first 1 MiB of exact controller stderr bytes while continuing to drain the pipe, records the
truncation bit, and digest-binds the bytes through the terminal record and host manifest. This
engineering support does not create a new attempt ID, execution mode or authorization; the
`preflight-node-n04-5s` source gate remains consumed.

`PYTHONPATH=src python scripts/qualify_libarchive_entry_boundary.py --output <new-file>
--image-id <sha256> --base-image-id <sha256>`는 별도 libarchive public write-disk reference
target에서 `archive_write_finish_entry()`와 final writer close의 syscall 순서를 비교한다.
정상 mixed-effect/directory-child fixture만 사용하고 marker 없는 baseline과 strace run의 최종
semantic state를 함께 기록한다. [qualification tool](../tools/libarchive/README.md)의 exact
package와 isolation 조건이 필요하며 결과는 raw boundary evidence다.
