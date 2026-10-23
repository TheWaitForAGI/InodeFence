# N05 + Track A 통합 후보 Linux 검증 인수인계 — 2026-10-23

Task Contract: 지웅이 직접 제공한 **Integration Candidate Linux Validation**.
범위는 지정 후보 보존, 기존 Linux 개발환경의 공학 검증, 실패 분석 및 후속 개발 진입 판단이다.
이 문서는 실행 승인, N05 PASS, qualification token, pilot 결과 또는 병합 결정이 아니다.

## 1. 판정

**종합: CONDITIONALLY_READY. 다음 개발 단계 GO, 실제 N05 / Track A 실행 STOP.**

정확한 코드 SHA `7861a7c5e0f9ca288eb36fae40b926ed60a4ca20`에서 Linux canonical
`make check`가 **1,757 PASS / 0 FAIL / 0 SKIP**로 완료됐다. N05 및 Track A Units 1–3
관련 별도 회귀는 **211 PASS**, 기존 경로·unknown-count probe는 **4 PASS**다.
중복 suite의 수치는 합산하지 않는다. macOS의 과거 117 PASS도 이 수치에 합산하지 않았다.

최초 Linux 실행은 검증자가 설정한 중첩 runtime root에서 **1,747 PASS / 10 FAIL**이었다.
모두 `FakeDocker`의 basename-only volume-subpath fixture와 관련된다. 표준 runtime 설정으로
backend 83개와 전체 suite를 재검증했다. Production, 테스트 fixture, isolation guard 및 evidence
schema는 수정하지 않았다. 중첩 runtime 설정의 suite 호환성은 여전히 제한 사항이다.

Host↔Controller의 양방향 evidence 경로, working-directory 충돌, Unit 4의 final Host binding은
남아 있다. 따라서 이 결과는 **공학 회귀 통과**이며 실제 실행 readiness는 **BLOCKED**다.
N05와 Track A pilot은 모두 **NOT_AUTHORIZED / NOT_RUN**을 유지한다.

## 2. 정확한 source 및 환경 identity

| 항목 | 확인값 |
| --- | --- |
| Repository | `TheWaitForAGI/InodeFence` |
| 실제 Linux 검증 source | `7861a7c5e0f9ca288eb36fae40b926ed60a4ca20` |
| 검증 source tree | `e0be20c2b03aea57d52731590c2d9ce581a581e8` |
| 첫 부모 / #120 | `02072c95537d76d1b213b9c858d96c97fff653cc` |
| 둘째 부모 / #115 | `e83349ed1592d536e3ec0fce3c7cb204cb5c6ec9` |
| 기존 보고서 commit | `c914da00e74556c3598c477a9325d02a7732e56a` — 부모는 위 검증 SHA |
| 기존 보고서 tree | `edca7e88c34636008c4dd5cf28ba43aee6f07fc0` |
| 기존 보고서 SHA-256 | `7e46ed08f7a43ebd69f47c45324188a9cc54b2de38b21a7bc72956c35a43d81b` |
| 실제 Linux source 경로 | `/home/vscode/inodefence-integration-linux-20261023/source` |
| 기존 Dev Container ID | `d3daf9a52d2e2567420ab02708c13c925141da2b198abaa56cd98a8aa9f909b0` |
| Dev Container image ID | `sha256:470e82d0541507e58ad8daf4f4371a44a99f7e8cafa2001138cbb41c00b44a1a` |
| OS / architecture | Ubuntu 24.04.3 LTS / Linux aarch64, Docker linux/arm64 |
| Kernel | `7.2.9-orbstack-00391-g2b298d05fbd4` |
| OrbStack | `2.2.4 (2020400)`, commit `1c4c8267f3256f8df9e4d80a2e50ac8f1136956c` |
| Docker context / client / server | `orbstack` / `29.8.2` / `29.8.2` |
| 실제 실행 user | `docker exec --user vscode`, UID/GID `1000:1000` |
| Python | `/opt/venv/bin/python`, CPython `3.12.3` |
| 검사 도구 | Ruff `0.17.0`, Pyright `1.1.414`, pytest `9.1.1`, pluggy `1.6.0` |
| 설치 package 목록 SHA-256 | `bab3f3285aa082b9b9194fca7dd74033005c401eab013c504b4b8e69abf1564c` |
| 환경 summary identity SHA-256 | `55e40e142465b4716f8057448933cec72408d4f35ca03e0907f8660cad21b66b` |
| 최종 canonical runtime | `/var/lib/inodefence`, 기존 `inodefence-runtime` volume |
| 검증 전용 tmp / pytest / cache | `/var/lib/inodefence/integration-validation-20261023/` 아래 서로 다른 basename |

환경에는 별도 Git SHA가 없다. 위 image ID, container ID, version/package 목록과
[environment-summary.json](../../../artifacts/linux-integration-validation-20261023/environment-summary.json)의
canonical summary hash로 식별한다. Summary hash는 자기 hash field를 제외한 sorted compact JSON의 hash다.
Container 기본 `Config.User`는 `root`지만 모든 검증 exec는 실제 non-root `vscode`로 수행했다.
이 Dev Container는 N05가 동결한 Controller가 아니며 N05 attestation을 받은 환경으로 주장하지 않는다.

## 3. Phase 0–2: 계보, 보존, 기존 환경 재사용

먼저 `START_HERE → STATUS → AGENTS` 순서 및 상위 instruction 파일 존재 여부를 확인하고,
연구 문서·엔진·실험 scoped AGENTS와 `CONTRIBUTING.md`를 읽었다. 관련 #115/#120 PR의 body,
head, base, 상태를 read-only 재조회했다. 두 head는 위 full SHA와 일치했다.
기존 보고서와 MID-03 consumer 설계의 필요한 부분만 추가로 검토했다.

새 안정 worktree:

```text
/Users/choijiwng/Projects/InodeFence-integration-linux-validation-20261023
branch: validation/n05-track-a-linux-20261023
initial HEAD: c914da00e74556c3598c477a9325d02a7732e56a
```

충돌하지 않는 새 디렉터리에 `git worktree add -b`로 생성했다. 기존 integration branch와
`/private/tmp/inodefence-overnight-20261023-goy0npqw/candidate`는 이동·삭제·switch하지 않았다.
기존 `revision-index.json`을 복사하고 report bytes/hash, artifact index의 **38개** file/hash/size,
#115와 #120의 핵심 **10개** 파일을 해당 부모와 독립 비교했다. 모두 일치했다.
보고서 commit의 변경은 handoff 문서·artifact뿐이며 `src`, `scripts`, `tests`, `.devcontainer`,
`Makefile`, `pyproject.toml`은 코드 SHA와 동일하다.

[lineage-and-preservation.json](../../../artifacts/linux-integration-validation-20261023/lineage-and-preservation.json),
[prior-revision-index.json](../../../artifacts/linux-integration-validation-20261023/prior-revision-index.json),
검증된 complete-history [source bundle](../../../artifacts/linux-integration-validation-20261023/preserved-source.bundle)을
보존한다. Bundle ref는 기존 integration branch의 `c914da0…`이며 두 commit을 모두 포함한다.

기본 checkout은 `main@919d723b7eb3bf13b060d3ae34b083499590b4fc`이고 기존 변경은
`.devcontainer/devcontainer.json` 하나다. 그 SHA-256
`af1b308868338c81cc727094c1bfab5dce679b546ef4eb79c97915c8cdf233c9`와 diff를 기록했다.
기존 worktree의 stale/prunable 표시는 정리하지 않았다.

기존 Dev Container의 `/workspaces/InodeFence`는 이 기본 checkout의 **RW bind mount**다.
여기서 테스트하지 않았다. Bundle만 기존 container의 새 전용 디렉터리에 복사해 local clone하고
정확한 코드 SHA를 detached checkout했다. Host worktree의 `.git` 절대경로를 Linux에서 재사용하지 않았다.
새 container/image/volume, build, package 다운로드·설치, 환경 재설치는 **0회**다.
기존 editable install은 기본 checkout을 가리키므로 명시적 `PYTHONPATH=<검증 clone>/src:<검증 clone>`을
사용했다. 주요 Host/N05/ledger 모듈의 실제 `__file__`이 검증 clone 안인지 전후 확인했다.
Source와 runtime volume은 별개이며 기존 mount의 장치번호도 각각 `37`, `42`였다.

## 4. Phase 3: 명령과 결과

전체 argv, exec user, cwd, 환경, UTC 시작·종료, exit code 및 stdout/stderr hash는
[command-index.json](../../../artifacts/linux-integration-validation-20261023/command-index.json)에 연결했다.
통합 코드의 실행 검증은 `/home/vscode/inodefence-integration-linux-20261023/source`에서 수행했다.
추가한 보고서의 게시 전 링크·Git 검사는 안정 Host worktree에서 별도로 수행했다.
`PYTHONDONTWRITEBYTECODE=1`, 외부 pytest plugin autoload 비활성화, 전용 `TMPDIR`와 각 실행별
새 `--basetemp`/JUnit 경로를 사용했다. 기존 basetemp 및 최초 실패 로그를 재사용하지 않았다.

| 명령 | 결과 | 범위 / 증거 |
| --- | --- | --- |
| `make --dry-run check` | PASS | lint → format → typecheck → pytest → env → docs; install/target-tools 없음 |
| `python -m ruff check .` | PASS | 정확한 코드 SHA, 별도 명령 |
| `python -m ruff format --check .` | PASS | 375 files, 별도 명령 |
| `python -m pyright` | PASS | 0 errors / warnings, 별도 명령 |
| `make check`, 중첩 runtime 설정 | **FAIL** | 1,747 PASS / 10 FAIL, pytest exit 1 / make exit 2; env/docs는 이후 target이라 NOT_RUN |
| `python -m pytest tests/test_container_backend.py -q`, 기본 runtime | PASS | 83/83; 원인 대조 |
| `make check`, 기본 runtime | **PASS** | Ruff/format/Pyright, **1,757 pytest**, environment, docs 모두 완료 |
| N04/N05 + Units 1–3 명시적 pytest | **PASS** | 211/211, 64.85s |
| 기존 `test_path_accounting_contracts.py` 4개 | PASS | 4/4, preserved bytes를 별도 probe 경로에서 실행 |
| `git diff --check`, `git diff --exit-code HEAD`, `git status --porcelain=v1 --untracked-files=all` | PASS | 검증 Linux clone의 tracked diff 및 nonignored untracked 없음 |
| `git bundle verify <preserved-source.bundle>` | PASS | complete history, ref=`c914da0…` |
| 실제 N05, N04 consumed attempt, historical node-tar, Track A pilot | **NOT_RUN** | 승인/실행·real PASS·qualification token 생성 없음 |
| 별도 benign target container integration | **NOT_RUN** | 이번에 새로운 Docker target 구동을 허용하지 않음 |

명시적 회귀의 전체 명령은 다음과 같다. Prefix/env는 위 command index의
`n05-track-a-synthetic.json`에 있다.

```bash
python -m pytest \
  tests/evaluation/test_n04_preflight.py \
  tests/evaluation/test_n04_host_ledger.py \
  tests/evaluation/test_n05_preflight.py \
  tests/evaluation/test_track_a_admission.py \
  tests/evaluation/test_track_a_exploratory.py \
  tests/evaluation/test_track_a_host_ledger.py -q
```

| 파일 | PASS |
| --- | ---: |
| `test_n04_preflight.py` | 31 |
| `test_n04_host_ledger.py` | 10 |
| `test_n05_preflight.py` | 47 |
| `test_track_a_admission.py` | 34 |
| `test_track_a_exploratory.py` | 38 |
| `test_track_a_host_ledger.py` | 51 |

Canonical pytest는 safe Python reference 실행, controlled Node-shaped adapter, synthetic backend,
파일 publication/변조·실패 주입 및 bounded process lifecycle 검사를 포함한다. 실제 Node/historical
package 실행으로 해석하지 않는다. `tests/container_integration/check_*.py`는 자동 collection 대상이 아니다.
Container 내부에는 Docker CLI 및 Docker socket도 없었다. 기존 테스트 double은 그대로 사용했고,
이번 검증 실패를 우회하기 위한 새 mock이나 guard override를 추가하지 않았다.

## 5. Phase 4: 최초 실패 10건의 원인과 최소 조치

최초 관찰 SHA는 전부 `7861a7c5e0f9ca288eb36fae40b926ed60a4ca20`다. 과거 revision까지
bisect한 최초 도입 SHA를 뜻하지 않는다. 정확한 command는 `canonical-make-check.json`, 원본
traceback은 [최초 stdout](../../../artifacts/linux-integration-validation-20261023/canonical-make-check.stdout.log.gz),
[최초 XML](../../../artifacts/linux-integration-validation-20261023/canonical-initial.xml.gz), 각 건의
예상/실제/코드 위치/최소 조치는 [failure-analysis.json](../../../artifacts/linux-integration-validation-20261023/failure-analysis.json)에 있다.

아래 node ID는 모두 `tests/test_container_backend.py::` 뒤의 이름이다.

| 실패 node ID | 동일한 실패 지점 |
| --- | --- |
| `test_cr002_environment_order_does_not_change_the_policy` | `container.py:284` |
| `test_final_cr002_cleared_cmd_accepts_only_documented_empty_forms[None]` | 같은 policy 검증 |
| `test_final_cr002_cleared_cmd_accepts_only_documented_empty_forms[empty_cmd1]` | 같은 policy 검증 |
| `test_ex003_timed_out_cli_with_exited_zero_primary_is_not_success` | 같은 policy 검증 |
| `test_policy_has_no_host_exposure_or_inherited_environment` | 같은 policy 검증 |
| `test_only_empty_runtime_default_volume_driver_is_accepted[driver0-True]` | 같은 policy 검증 |
| `test_timeout_stops_context_before_return` | 같은 policy 검증 |
| `test_timeout_exit_race_only_accepts_confirmed_stopped_context[container is not running-True]` | 같은 policy 검증 |
| `test_timeout_exit_race_only_accepts_confirmed_stopped_context[permission denied-False]` | 같은 policy 검증 |
| `test_start_deadline_before_launch_destroys_context_before_return` | 같은 policy 검증 |

예상은 valid request의 create-command와 FakeDocker inspect mount가 일치해 각 테스트 본문까지
진행하는 것이다. 실제로 fixture `tests/test_container_backend.py:99`는
`Subpath=Path(root).name`만 반환한다. 최초 설정에서는 `core-run-…`만 반환하는 반면 production의
`create_command`(`src/inodefence/execution/container.py:153`)와 검증(`:278`)은
`integration-validation-20261023/core-run-…`를 요구한다. `:284`의 거부는 올바른 fail-closed 동작이다.

분류는 **테스트 fixture + 비기본 runtime 실행 설정의 불일치**다. Architecture 차이나 Linux guard
미구성으로 분류하지 않는다. 이 로그에서 production defect는 확인되지 않았다.
최소 실행 조치는 기본 `INODEFENCE_RUNTIME_ROOT=/var/lib/inodefence` 복원이다. 이 한 설정과
충돌 방지용 출력 경로만 바꾸고 같은 source에서 83/83 → 전체 1,757/1,757을 확인했다.
별도 fixture 개선이 필요하면 `Path(root).relative_to(RUNTIME_BASE).as_posix()`로 inspect double을
맞추는 작은 후속 test-only 작업이 가능하다. 이번에는 그 수정을 하지 않았다.

기존 macOS 실패였던 `test_missing_backend_fails_before_runtime`와
`test_missing_evidence_stays_explicitly_unavailable`는 Linux에서 모두 PASS다.
`container.py:86`의 non-root Linux guard와 `evaluation/storage.py:32`의 Linux publication guard는
그대로다. 별도의 production 수정, contract/schema/isolation 변경 필요 상황은 발생하지 않았다.

신규 로그 수집 helper의 별도 lint에서는 UTC alias, subprocess 출력 수집 및 명시적 `check=False`
관련 4개 지적이 나왔다. 검증 source 밖의 이 helper만 정리하고 lint/format을 다시 통과했다.
변경 전 helper와 최초 lint 원본은
[tooling-adjustments.json](../../../artifacts/linux-integration-validation-20261023/tooling-adjustments.json)에
연결했다. 이는 통합 코드의 테스트 실패와 구분하며 기존 실행 로그를 재작성하지 않았다.

## 6. Phase 5: 통합 guard와 consumer 유지 여부

| 질문 | 확인 결과 / 한계 |
| --- | --- |
| #115 source-origin guard | **유지 / PASS**. Host entry와 loaded module origin·canonical nonsymlink·authorized bytes를 검사한다. `n05_preflight.py:337`, `container_host.py:1120`의 검사가 ledger/Docker보다 먼저다. Positive 1개 + mismatch 5종 회귀가 Linux에서 PASS. |
| #120 Host ledger | **유지 / PASS**. durable start 후 Host ID를 Controller 및 policy claim에 동일하게 결속한다. Terminal/manifest/stderr/cleanup, start-only replay 거부, watchdog/spawn/관찰 실패의 unknown 보존을 51개 회귀로 확인했다. |
| Units 1/2 consumer | **유지 / PASS**. 34 admission + 38 exploratory 회귀. Original pilot/N05/protocol 재개방, retained integrity와 process-local live admission의 구분, digest-only/admissionless entry 거부 유지. |
| N04 consumed guard | **유지 / PASS**. Production `ATTEMPT_CONSUMED=True`를 최종 확인. 실제 attempt 재실행 없음. |
| Host↔Controller 절대 경로 | **여전히 BLOCKER**. 실제 N05 namespace 실패 재현으로 주장하지 않으며 코드 및 declared-mount model로 확인. |
| working-directory 계약 | **충돌 유지**. N05는 `/workspaces/InodeFence`; Track A `_arguments`는 같은 경로에서 실행을 거부한다. |
| Unit 4 final graph | **미구현 범위 유지**. 현재 final COMPLETE는 campaign 완료 수만으로 정해지며 외부 Host ledger 20개를 결합하지 않는다. |

## 7. Host↔Controller 경로와 B안 검토

코드 근거는 `n05_preflight.py:61–106, 616–638`, `container_host.py:684, 732, 1180`,
`track_a_admission.py:836–855`, `track_a_host_ledger.py:492, 804, 826`,
`track_a_exploratory.py:592`, `track_a_container_host.py:156`,
`track_a_container_controller.py:41`이다. 이는 위 코드 SHA의 위치다.

| 필요한 원본 / view | 현재 차단 조건 |
| --- | --- |
| Host N05 ledger, original pilot, Track A Host ledger/start → Controller | Reader가 기록된 `/Users/...` 절대경로를 실제로 연다. N05의 허용 mount 두 개는 source RO `/workspaces/InodeFence`, runtime RW `/var/lib/inodefence`뿐이다. |
| Linux N05 raw/final, Track A execution/repetitions → Host | Host consumer도 `/var/lib/inodefence/...` 원본 graph를 다시 열어야 한다. Host가 Docker volume을 같은 절대경로로 볼 수 있다는 검증이 없다. |
| N05 Controller와 Track A Controller | Admission은 ID/image/daemon/volume equality를 요구한다. 별도 container로 분리하는 것은 현재 계약의 해결책이 아니다. |
| source cwd | N05의 유일 source destination과 Track A primary-worktree 금지가 함께 남는다. `.git`도 접근 가능한 clean execution clone이 필요하다. |

기존 보고서의 **B: 명시적 evidence view + 제한된 bytes transport**를 우선 권고한다.
아직 **PROPOSED DESIGN**이며 이번에 구현·채택·승인하지 않았다.
검토할 interface는 `EvidenceView(logical_namespace, logical_root, physical_root,
inventory_reference, expected_origin_manifest_sha256)`다.

원본 authorization/path/manifest bytes와 digest를 유지하고, logical origin과 physical view를
별도 versioned manifest로 결속해야 한다. Host→Controller뿐 아니라 Controller→Host도 필요하다.
고정 allowlist의 complete bytes를 제한된 크기로 전달한 뒤 기존 typed reader가 전체 digest graph를
재검증해야 한다. `VerifiedTrackAAdmission`이나 private seal을 직렬화해서는 안 된다.
동적 `started.json`은 새 발행 직후 exact digest로 결속하고 stale start를 거부해야 한다.
임의 prefix 치환, symlink alias, `/Users` 추가 mount, Docker socket, arbitrary path RPC,
source-origin 검사 생략, digest-only fallback은 이번 작업의 해결책으로 승인하지 않았다.

Missing/extra/traversal/symlink/stale/wrong-origin/oversize view와 start swap을 start/claim 전에 거부하고,
target에는 evidence view가 노출되지 않음을 후속 Linux 배치 검증으로 확인해야 한다.
Working-directory/source policy도 함께 명시적으로 결정해야 한다. 이 변경은 새로운 source SHA를
만드므로 최종 구현·review 이후 source/image freeze와 별도 N05 승인을 다시 결속해야 한다.

## 8. 규민에게 넘길 Runtime 작업

입력은 위 통합 SHA, 보존된 Linux 회귀, B안 설계 질문 및 현재 N05 source/containment guard다.
현재 Dev Container를 N05 Controller로 재명명하거나 기존 N04 attempt/volume을 재사용하지 않는다.

1. 지웅·주언과 evidence authority, 양방향 view, bounded transport 및 source cwd 계약을 먼저 확정한다.
2. 최종 구현 완료 뒤 정확한 clean execution clone/source SHA, authorized executable bytes,
   package/build-context digest, Controller image/ID, daemon, dedicated volume 및 UID/GID를 동결한다.
3. 기존 source RO/runtime RW 경계, no network/privilege/capabilities, target one-run subpath isolation을
   유지한다. Freshness 및 다른 volume consumer 부재를 실제 환경에서 확인한다.
4. 승인 전에 target-free namespace read-positive/read-negative, tamper/stale mapping,
   target evidence 비노출과 양방향 origin/hash 검증을 수행한다. 설치/build가 필요하면 이유·범위를 먼저 보고한다.
5. 별도 사람 승인 후에만 새 N05 attempt를 실행하고 Host cleanup까지 independent reader로 검증한다.
   N05 PASS는 Track A pilot 승인을 대신하지 않는다.

이번에 관찰한 Dev Container와 runtime은 **개발 회귀 환경**이다. N05의 exact image/freshness/
dedicated-volume 및 실행 승인 선행 조건을 충족했다고 넘기지 않는다.

## 9. 주언에게 넘길 Unit 4 작업

선행 조건인 #115+#120 통합과 Units 1–3 Linux 회귀는 확보했다. **Host publication authority의
사람 결정은 아직 필요**하다. Same-namespace synthetic 구현·검증과 실제 배치 gate를 구분한다.
기존 보고서 E의 U4.1–U4.5를 재사용하며 이 작업에서 Unit 4나 Native producer는 구현하지 않았다.

| 작업 | 재사용할 interface / 인수 조건 |
| --- | --- |
| U4.1 authority / external reference | `ArtifactReference`, `read_track_a_host_attempt`, `read_track_a_host_ledger`; 원본 Host authority를 execution/source/plan/admission anchor에 결속 |
| U4.2 incomplete inspection | strict 성공 reader는 유지. absent / started-only / partial-terminal / verified / invalid를 read-only 진단. terminal 합성·수정·재시도 없음 |
| U4.3 final graph | `finalize_track_a_execution` / final manifest를 versioned 확장. 고정 20-slot Host refs와 campaign graph 결합, no-overwrite |
| U4.4 independent final reader | `read_track_a_execution` → 원본 authority → 각 start/terminal/manifest/stderr/cleanup → 동일 ID policy claim/journal 재검증 |
| U4.5 analysis | Host 상태, publication completeness, campaign 상태, target 상태를 분리. 실패·미시작·unknown도 scheduled 20 / arm별 5 분모에 보존 |

권고 model 초안은 `TrackAHostLedgerReference`와 `TrackAHostSlotEvidence`이며 아직 확정 interface가 아니다.
완료 판정에는 **20 valid Host COMPLETE + 20 campaign COMPLETED + 200 verified records/cell**이
필요하다. Index/run/arm/seed/config/attempt/execution/plan/admission이 모두 연결돼야 한다.
삭제·변조·중복·gap·cross-run swap·cleanup 실패·changed N05를 COMPLETE로 검증하면 안 된다.

현재 `track_a_exploratory.py:856–940`는 campaign 수와 local `_inventory(root)`만 검증하므로
그 final COMPLETE를 pilot 전체 성공으로 사용해서는 안 된다. 이는 알려진 Unit 4 누락 범위이며
이번에 실제 잘못된 pilot 산출물을 관찰한 것은 아니다.

**4,000은 20×200 planned seed-inclusive budget**이다. Cell당 seed 4 + mutation 196이다.
`target_executions`/journal completed records는 관찰 완료 수이며 interrupted actual starts의 정확한
수가 아닐 수 있다. `planned_executions`, `verified_completed_executions`, `actual_target_starts`
(모르면 null), `count_completeness`를 구분한다. Unknown을 0/no-hit으로 바꾸지 않는다.
정확한 launch count용 begin/end durability instrumentation은 별도 계약 판단 사항이다.

## 10. 지웅이 결정할 사항과 실행 금지 범위

1. 이 exact 통합 후보를 후속 개발 기준으로 채택할지, PR/merge를 어떤 순서로 진행할지 결정한다.
   이번 작업은 push, 기존 PR 수정 또는 병합을 수행하지 않았다.
2. B안의 Host authority, view schema, 허용 transport/size/retention 및 trusted mapping anchor를 동결한다.
3. N05와 Track A가 함께 만족할 clean source clone/cwd 정책을 확정한다. 기존 guard를 끄는 결정으로
   대체하지 않는다. Controller 분리안은 별도 applicability/identity 계약 변경이 필요하다.
4. Unit 4 completeness 및 실행 수 의미를 확정하고, exact starts 계측의 필요 여부를 따로 판단한다.
5. 구현·Linux 회귀·독립 review 후 최종 SHA/image/path를 freeze하고 N05 승인과 pilot 승인을 별도로 한다.

Unit 4와 경로 해결 전에는 실제 Track A prepare/run-cell/pilot, final COMPLETE를 이용한 전체
pilot 성공 판정, 4,000 actual executions 또는 효과 우위 주장을 하면 안 된다. 현재 Task Contract에서는
실제 N05도 승인되지 않았다. N04 consumed attempt 재실행, historical target 실행, real approval/PASS/
qualification token 생성은 수행하지 않았다. Native Observation 및 새 fuzzing 기능도 추가하지 않았다.

## 11. STOP/GO, 변경과 영구 증거

**GO:** 후보를 보존된 개발 기준으로 검토하고 Runtime 경로 계약 및 Unit 4 개발 명세를 확정한다.
Canonical Linux 공학 검증과 Units 1–3 회귀는 이 exact 코드 SHA에서 통과했다.

**STOP:** 실제 N05/Track A. 양방향 path/cwd 계약, Unit 4 final binding, 최종 source/image freeze,
각각의 사람 승인이 충족될 때까지 실행하지 않는다. 11월 2일 발표에서는 구현·공학 검사와
실험 NOT_RUN을 분리하고, 11월 30일 연구 결과로 이번 PASS를 승격하지 않는다.

이번 변경은 새 보고서·검증 기록·작은 artifact 안내뿐이다. Production, tests, Security Contract,
N05 authorization, source-origin guard, isolation, evidence schema는 그대로다.
기본 checkout과 기존 integration worktree는 최종 HEAD/status/hash를 재대조했다.
기존 runtime의 다른 top-level 항목 inode/mtime/mode도 같았다. 이는 기존 runtime raw 전체를 재귀 hash한
검증은 아니며, 테스트는 disposable sentinel/새 tmp만 사용했다.

영구 보고서는 이 파일이고 로그·명령·XML·bundle은
`/Users/choijiwng/Projects/InodeFence-integration-linux-validation-20261023/artifacts/linux-integration-validation-20261023/`
아래에 보존한다. 주요 증거는 다음과 같다.

- [최종 make check 원본 stdout gzip](../../../artifacts/linux-integration-validation-20261023/canonical-make-check-default-runtime.stdout.log.gz)
- [최종 JUnit gzip](../../../artifacts/linux-integration-validation-20261023/canonical-default.xml.gz)
- [집계 및 파일별 회귀](../../../artifacts/linux-integration-validation-20261023/test-summary.json)
- [최초 실패별 원인·traceback](../../../artifacts/linux-integration-validation-20261023/failure-analysis.json)
- [실행 전후 보존 확인](../../../artifacts/linux-integration-validation-20261023/preservation-final.json)
- [전체 명령 index](../../../artifacts/linux-integration-validation-20261023/command-index.json)
- [파일/hash/원본 gzip 대응](../../../artifacts/linux-integration-validation-20261023/artifact-index.json)

원본 `.log`/`.xml` bytes는 수정하지 않았다. 같은 디렉터리의 원본 파일과 무손실 gzip 사본을 보존하며
Git에는 gzip을 포함해 traceback trailing whitespace와 원본 보존을 함께 만족시킨다.
Gzip 변환은 압축뿐이며 원본 hash를 inventory에 기록한다. 이번 문서 commit은 검증 코드 SHA와
다르다. 정확한 최종 commit과 이 보고서 hash는 종료 응답 및 안정적인 외부 index
`/Users/choijiwng/Projects/InodeFence-integration-linux-validation-20261023.revision-index.json`에 기록한다.

증거의 수준은 **engineering validation**이다. 연구 finding 또는 paper-ready 실험 run은 없으며,
새 취약점·재발견·정책 효과·native qualification 결과를 주장하지 않는다.
