# Validation log — 2026-10-23 follow-up

이번 세션의 모든 명령은 별도 표기가 없으면 로컬 통합 후보
`8979f248ee77fb69259292adb9c32fda371ea4e9`에서 실행했다. Historical target, Docker, N05,
native qualification과 Track A pilot은 실행하지 않았다.

## Repository와 PR 확인

- Primary: `/workspaces/InodeFence`, clean `main`, HEAD/origin-main
  `8d29982c26cebfcce7a413b3ba9177fcd28078de`.
- 기존 worktree: `/tmp/inodefence-pr114-binding`, 기존 report directory 보존.
- 후속 worktree: `/tmp/inodefence-gyumin-runtime-20261023`, branch
  `codex/gyumin-runtime-followup-20261023`.
- Remote pull heads를 다시 fetch했고 GitHub PR page embedded metadata로 state/base/head를 확인했다.
- #120에 #115가 ancestor가 아니며 `verify_authorized_runtime_files`가 없음을 확인했다.
- #120 위에 #115를 cherry-pick해 `8979f24` 생성; conflict 없음; diff 7 files, `+277/-23`.
- `git diff --check origin/pr/120..HEAD`: exit 0.

## N01 local static evidence

시각: 2026-10-23 09:47 KST 전후.

Command: ignored static root에서 `sha256sum -c checksums.sha256`.

Result: 모든 43개 listed artifact `OK`, exit 0.

직접 rehash/cmp 결과:

```text
22d8b674a68754ea909d03aa13958a7d2fd5e78af8a8f0cde6455babef7aaf1a  tar-7.5.2.tgz
9d95d0cf786786360f97c1e414caea8a14452dc337fda17ba256ae7762c2ec66  tar-7.5.3.tgz
6d99259843eebfd4ad305c991b03579d1e616fbd8372e2775026858e78e9cafa  7.5.2 unpack.js member
b4d7c53d87c34910775dca2aa5349735486ae592a17fc84a0b50c06da9360ec0  7.5.3 unpack.js member
```

두 tar member는 보존된 `tar-*-dist-commonjs-unpack.js`와 각각 `cmp` exit 0이었다.

Candidate lock/worker direct rehash:

```text
31792107e9442ab18b04661d10ca0a0053db1fb7c58ca3aa702f1abb9908e243  node-tar-7.5.2.package-lock.json
a63d02f09d9a9fb2def77da84d5145984ff260fcedd19839ba96ec858fdfae24  node-tar-7.5.3.package-lock.json
feb13d7be5f5718769bebd4b0e375ea3f535abffd45223494dd518263593498b  _node_worker.cjs
```

Current source N01 input reconstruction:

```text
child_case_id=55b8b7eda4bf26ec1e877866a099dd49195754e00e1e6f20dd82b0bb09288a87
tar_sha256=2af6de238713e83a630ad8c95f9385f2cf2e6127a9025bd71d7a2377a7e47ba6
frozen_input_tar_sha256=2af6de238713e83a630ad8c95f9385f2cf2e6127a9025bd71d7a2377a7e47ba6
match=True
```

이는 target-free reconstruction이다. Historical raw records를 다시 읽은 결과가 아니다.

## Environment

Canonical `make check`의 environment 단계가 직접 출력한 값:

```text
OS: Linux 6.18.33.2-microsoft-standard-WSL2
Architecture: x86_64
Python: 3.12.3
Interpreter: /opt/venv/bin/python
Runtime root: /var/lib/inodefence
Hardlink semantics: PASS
Symlink semantics: PASS
Shared-object effect: PASS
Environment check: PASS
```

`command -v docker`는 빈 결과였다. 이 environment는 macOS/OrbStack arm64 N05 host가 아니다.

## Focused target-free regression

시작: `2026-10-23T01:01:45Z`. 종료: `2026-10-23T01:07:10Z`.

Command:

```bash
python -m pytest -q \
  tests/evaluation/test_n01_qualification.py \
  tests/evaluation/test_n01_candidate_match.py \
  tests/evaluation/test_n05_preflight.py \
  tests/evaluation/test_n04_host_ledger.py \
  tests/test_container_backend.py \
  tests/evaluation/test_track_a_admission.py \
  tests/evaluation/test_track_a_exploratory.py \
  tests/evaluation/test_track_a_host_ledger.py
```

Result: `277 passed in 296.76s`, exit 0.

이 tests는 mock/controlled backend와 synthetic evidence를 사용한다. Historical node-tar image,
Docker daemon, N05 path 또는 real Track A target을 호출하지 않는다.

## Canonical validation

시작: `2026-10-23T01:07:14Z`. 종료: `2026-10-23T01:17:46Z`.

Command: `make check`.

Result, exit 0:

```text
Ruff lint: PASS
Ruff format: 375 files already formatted
Pyright: 0 errors, 0 warnings, 0 informations
Pytest: 1,757 passed in 554.10s
Environment check: PASS
Docs check: PASS (135 Markdown files; canonical documents present)
```

이 명령은 Makefile상 lint/format/typecheck/pytest/env/docs만 실행한다. Docker/N05 entrypoint,
attempt ledger 생성, target extraction을 실행하지 않는다.

보고서 작성 후 `python scripts/check_docs.py`를 별도로 실행해 140 Markdown files PASS, exit 0을
확인했다. `git diff --check`도 exit 0이었다. 이 post-write 문서 검사 때문에 전체 `make check`를
이유 없이 반복하지 않았다.

## 과거 검사와 이번 검사 구분

기존 2026-10-22 보고서의 focused 57/14 tests와 `make check` 1,634 tests는 과거 결과로 보존한다.
이번 결과는 위 시각의 후보 HEAD에서 수행한 277/1,757 tests다. GitHub CI 성공, 이번 local tests,
사람 review, 실행 승인, 실제 experiment result는 서로 다른 상태다.

## 명시적 미실행

| 작업 | 상태 | 이유 |
| --- | --- | --- |
| N01 retained raw rehash/offline reader | 미실행 | N02/N04 roots 부재 |
| N01 historical target replay | 미실행 | prompt는 실행 승인 아님 |
| N05 attempt 001 | 미실행 | authorization/source/controller/Mac gates 미충족 |
| N04 retry | 미실행 | consumed/no-retry |
| Docker image/container admission | 미실행 | Docker CLI/daemon 없음, wrong host |
| Track A prepare/run-cell/pilot | 미실행 | N05 PASS, pilot approval, Unit 4 없음 |
| Native qualification/fuzzing | 미실행 | 규민 범위 밖/별도 gate |
| 영상 제작·재생 | 제외 | 사용자 지정 |
