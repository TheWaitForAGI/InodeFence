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

generate_tar_fixtures.py는 4종 TAR baseline을 재생성한다. manual_tar_probe.py는 Linux runtime sandbox에 TAR를 풀고 lstat/readlink 결과를 출력한 뒤 sandbox를 삭제한다.

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
