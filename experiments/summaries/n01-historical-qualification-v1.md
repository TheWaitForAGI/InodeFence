# N01 Historical Qualification: independent feasibility review

평가일: **2026-10-14 UTC**. 판정: **BLOCKED**. Historical execution,
affected/fixed replay, rediscovery, effectiveness는 모두 **NOT_RUN**이다.
현재 근거는 source review와 환경 진단이다. 취약점 재발견 또는 안전성 증명이 아니다.

## Task Contract와 revision

사용자가 직접 확정한 독립 Research Validation Engineer 작업 명세를 따른다.
목표는 N01 `tar 7.5.2 / 7.5.3`의 admission/실행 가능성 검토다. 이번 변경 범위는
이 조사 보고서와 provenance/evidence 기록이다. Generic Mutation, Observer, Oracle,
Feedback, native effect stack, main 및 기존 PR의 구현은 변경하지 않는다.
추가 구현은 아래 별도 **PROPOSED Task Contract** 대상으로 남긴다.

| 대상 | 확인한 revision / 상태 | 해석 |
| --- | --- | --- |
| GitHub main 및 clean checkout | `57f751992f60a534c5b07506e72124abe5d6b07d` | `git ls-remote`와 local HEAD 일치 |
| G0 capability baseline | `8ad07b8e5f23f789d57ea50ba52c7acfcee951ea` | 현재 main SHA가 아닌 과거 문서 기준 |
| [PR #88](https://github.com/TheWaitForAGI/InodeFence/pull/88) | head `dd8dd15b2b4a8ce697e3ef38567883f2602cfb15`; merge `58e69ae70953bf4e7b696abeea02d9dfe987d9b5` | 2026-10-14 04:25:48Z 병합 |
| [PR #89](https://github.com/TheWaitForAGI/InodeFence/pull/89) | head `0eb527f88aa8a4015544d2f6b0eabfebe079bf18`; merge `ccc061bece3f3525ecf0b734777a6b39bac06b07` | 2026-10-14 04:28:33Z 병합 |

요청에서 두 PR을 미병합으로 표현했지만 조회 시점에는 둘 다 병합됐다.
두 merge commit이 현재 main의 ancestor임을 독립적으로 확인했다. 원래 base
`931899209bc1de29f249d9e2f3d451438ddf1d22`와 각 head의 diff에서 N01 관련
`mutator/`, `observer/`, `oracle/`, `pipeline.py`, `node_tar.py`, `_node_worker.cjs`는
변경되지 않았다. #88의 clean 실행 revision `72bccfafe5f9f7e8ff06d850fb62a43fa6ed75d8`
및 #89의 `36ff7fdb0e31db72b3e581fd1c089b712b4a7b4e`는 main 또는 N01 실행
revision으로 재사용하지 않는다. 두 PR의 retained native qualification 실패는 N01의
final-state C1 qualification을 금지하지도 통과시키지도 않는다. 해당 raw matrix를
이번 작업에서 재실행하거나 독립 재검증했다고 주장하지 않는다.

읽은 기준: [START_HERE](../../docs/START_HERE.md), [STATUS](../../docs/STATUS.md),
[AGENTS](../../AGENTS.md), [Benchmark Set](../../docs/research/benchmarks/benchmark-set-v1.md),
[Evaluation Protocol](../../docs/research/benchmarks/evaluation-protocol-v1.md),
[Security Contracts](../../docs/research/design/security-contracts.md), 관련 scoped AGENTS,
artifact qualification 및 현재 adapter/runtime 코드. GitHub N01/historical issue 검색에서
관련 Issue가 반환되지 않아 사용자 명세를 Task Contract 출처로 유지한다.

## N01 candidate admission G1–G8

이 표는 benchmark admission gate이며 프로젝트 G0–G7이나 native v2 gate가 아니다.
부분 증거는 전체 PASS로 승격하지 않는다. READY에는 여덟 gate의 complete evidence가 필요하다.

| Gate | 독립 판정 | 입증한 것 | 아직 필요한 것 |
| --- | --- | --- | --- |
| G1 Source trust | **PASS (documentary)** | Maintainer advisory와 production patch가 같은 GHSA를 명시하며 7.5.3 fix를 연결한다 | 실제 effect qualification은 G7에서 별도로 검증 |
| G2 Exact pin | **STATIC BYTES VERIFIED / BLOCKED runtime** | Exact commits, 두 release와 5개 공통 production artifact의 SHA-512 integrity, 동일 production closure 확인 | Candidate wrapper locks, built image IDs, 실제 image의 Node/package/worker/lock identity |
| G3 Semantics | **SOURCE-SUPPORTED / NOT_RUN** | Relative hardlink의 CWD resolution과 fixed linkpath parent-component reject를 production patch에서 확인 | Linux에서 strict=true, preservePaths=false의 affected/fixed 실제 동작 및 상태 분류 |
| G4 Reachability | **BLOCKED default setup** | USTAR hardlink와 M1 generic composition은 존재 | 현재 grammar가 `outside/sentinel.txt`에 도달하지 못한다; reviewed address/setup binding과 constructive generation evidence |
| G5 Execution | **BLOCKED** | Enforced contained adapter/backend는 현재 main에 존재 | 이 세션의 검증된 host broker, candidate images, full-path binding 및 boundary qualification 부재 |
| G6 Observation | **IMPLEMENTED / historical NOT_RUN** | Persistent C1 dev+inode와 C2 sentinel metadata를 보존하는 일반 detector 존재 | 해당 pair에 대한 lifecycle-valid BEFORE/AFTER raw evidence와 reader 검증 |
| G7 Expected outcome | **NOT_RUN** | 패치로부터 상대 hardlink alias 유무 차이를 예상할 근거 | 동일 TAR의 fresh affected 3/3 및 fixed 0/3 matching C1, 실패도 포함한 raw record, root-cause review |
| G8 Explicit setup | **PROPOSED / NOT_FROZEN** | Disposable owned same-device sentinel과 empty extract 구성 가능 | 실제 mount/CWD/ownership/limits/image 및 generable controlled profile의 실행 전 freeze |

## 공식 근거와 pair의 의미

Maintainer [GHSA-8qq5-rm4j-mr97](https://github.com/isaacs/node-tar/security/advisories/GHSA-8qq5-rm4j-mr97)
및 [official CVE record](https://www.cve.org/CVERecord?id=CVE-2026-23745)가
affected `<=7.5.2`, first patched `7.5.3`를 명시한다.
Production [fix 340eb285](https://github.com/isaacs/node-tar/commit/340eb285b6d986e91969a1170d7fe9b0face405e)는
기존 member-path sanitation을 `path`/`linkpath` 공통 검사로 바꾼다. Parent component
`..`를 포함한 linkpath를 거부하고 absolute root를 strip한다. preservePaths가 true이면
검사를 우회하므로 benchmark에서 false를 유지해야 한다.

Exact affected source는 `d9ea73a9b3fc0a2f9734fda65279f48c7cc99f28`, fixed source는
`03138441b238f48070fb22824b2529c445bc70c7`다. Official GitHub compare에는 fix를
포함한 네 commit이 있다. Dependency-update commit도 포함되므로 pair를 단일 patch-only
실험으로 표현하지 않는다. Production dependency closure를 공통 exact versions로 고정하고
각 upstream lock과 실제 wrapper lock을 구분해야 한다.

공식 registry/source를 이번 세션에서 다시 내려받아 다음 바이트를 검증했다.
SRI와 SHA-1은 registry/lock의 값과 일치한다. Registry signature 자체는 검증하지 않았다.
Metadata, package bytes, named package.json 및 CommonJS unpack.js만 읽었으며 npm install,
package load, extractor 실행 또는 target image build는 하지 않았다.

| Artifact | SHA-256 of downloaded bytes | 상태 |
| --- | --- | --- |
| [tar 7.5.2](https://registry.npmjs.org/tar/7.5.2) npm tarball | `22d8b674a68754ea909d03aa13958a7d2fd5e78af8a8f0cde6455babef7aaf1a` | Registry SHA-512 SRI 및 SHA-1 일치 |
| [tar 7.5.3](https://registry.npmjs.org/tar/7.5.3) npm tarball | `9d95d0cf786786360f97c1e414caea8a14452dc337fda17ba256ae7762c2ec66` | Registry SHA-512 SRI 및 SHA-1 일치 |
| [7.5.2 upstream lock](https://github.com/isaacs/node-tar/blob/d9ea73a9b3fc0a2f9734fda65279f48c7cc99f28/package-lock.json) | `7d88a2eee8bcfee0285e2d48f8e3a7ae3d03842c55db56ff42ea3b817d9bc744` | Source development lock; wrapper lock 아님 |
| [7.5.3 upstream lock](https://github.com/isaacs/node-tar/blob/03138441b238f48070fb22824b2529c445bc70c7/package-lock.json) | `f8c16ee22830cd8384a542df56646e20dbc2b6b03ce8b1526c87443e989e6b85` | Source development lock; wrapper lock 아님 |

두 upstream lock의 production closure는 version/resolved/integrity/engines/dependencies까지
동일하다: `@isaacs/fs-minipass 4.0.1`, `chownr 3.0.0`, `minipass 7.1.2`, `minizlib 3.1.0`,
`yallist 5.0.0`. 다섯 artifact도 실제 다운로드한 bytes가 lock SRI와 일치한다.
각 identity와 원본 URL은 [machine evidence](n01-historical-qualification-v1.json)에 있다.

배포된 CommonJS unpack.js에서도 7.5.2에는 linkpath sanitizer 호출이 없고 7.5.3에는
있음을 확인했다. 두 배포의 hardlink CWD resolution은 유지돼 있어 상대 arm의 수정
차이를 설명한다. 7.5.2 exports에는 `source` condition이 있고 7.5.3에서는 없어졌으므로
기존 plain CommonJS worker를 그대로 쓰고 custom conditions/NODE_OPTIONS를 추가하지 않는다.

| 동일 relative-arm control에서 검증할 항목 | 7.5.2 예상 | 7.5.3 예상 | 실제 관찰 |
| --- | --- | --- | --- |
| Persistent extraction↔sentinel identity | 공유; C1 candidate | linkpath 검사로 공유 없음 | 양쪽 NOT_RUN |
| Sentinel nlink/ctime | Alias 생성으로 변화 가능; C2 corroboration | 동일 control의 변화 없음 | 양쪽 NOT_RUN |
| Sentinel content digest | 변화 불필요 | 변화 없음 | 양쪽 NOT_RUN |
| Process outcome | 정상 hardlink 생성이면 SUCCESS | strict warning/error이면 REJECTED, TAR_ENTRY_ERROR 예상 | 양쪽 NOT_RUN |

Process outcome은 selected effect의 대체물이 아니다. 이 table은 source 기반 예상이며
actual 3+3 동일-input replay 결과와 구분한다.

선택한 relative arm은 source에서 도출한 **추론**이다. Published absolute-arm PoC의
독립 실행 결과가 아니다. Public PoC는 seed로 사용하지 않았고 역사적 extractor는
설치·load·실행하지 않았다. Post-extraction application write도 수행하지 않았다.
Persistent cross-boundary C1 alias가 qualification의 selected effect이며 content overwrite는
필수 조건이 아니다. Dangling external symlink 또는 rejection status만으로 N01 성공을
판정하지 않는다. Fixed release가 다른 class에 대해 안전하다고 주장하지 않는다.

## 정확한 재현 환경: 관찰과 요구사항

관찰된 controller: Ubuntu 24.04.3 LTS, glibc 2.39, Python 3.12.3, x86_64,
kernel `6.18.33.2-microsoft-standard-WSL2`, uid/gid `1000:1000`,
`fs.protected_hardlinks=1`, runtime root `/var/lib/inodefence`.
Source bind mount device `2128`, runtime device `2096`으로 분리돼 있다.
`check_dev_env.py`가 disposable runtime 내 hardlink/symlink/shared-object checks를 통과했다.
이는 filesystem 기능 검사이며 OS isolation certificate가 아니다.
Runtime filesystem은 ext4 `rw,relatime`, 관찰한 controller umask는 `0022`다.
CPU는 AMD Ryzen 7 250, logical CPU 16개, MemTotal 7,706,272 KiB다. Controller의
cpu/memory/pids cgroup 값은 `max`다. 이 값은 historical target의 resource allocation이 아니다.

현재 Docker/Podman/nerdctl/bwrap CLI, Docker/Podman socket, DOCKER_HOST 및 이 세션에
전달된 trusted broker가 없다. 고정 `unshare ... true` 진단의 여덟 namespace probe는
모두 `Operation not permitted`로 실패했다. Read-only cgroup mount도 관찰됐다.
기존 WSL host broker가 과거 #89를 실행했다는 기록은 현재 세션 연결의 증거가 아니다.
직접 Node subprocess, controller의 npm install, 임의 namespace fallback을 사용하지 않는다.

기존 exact-lock packaging은 Node **22.22.0**을 공통으로 요구한다. 두 tar release의
declared engines `>=18`은 이 버전을 허용하지만 실제 호환성 검증은 아니다.
고정 build base는 `node:22.22.0-bookworm-slim@sha256:dd9d21971ec4395903fa6143c2b9267d048ae01ca6d3ea96f16cb30df6187d94`,
runtime base는 `gcr.io/distroless/cc-debian12:nonroot@sha256:9dac0a79194e45a7da0158a9c6da57b217585af0786db3845d1f0ec1a0dd182f`다.
이 값은 recipe pin이며 이번 작업에서 조회·build·실행한 image digest가 아니다.
`prepare_node_release`/`build_node_release`가 이미 존재하므로 새 adapter나 packaging
engine을 구현할 이유는 발견하지 못했다. Candidate-specific supplied lock은 별도 필요하다.

## 정상 초기 상태와 isolation 조건

다음은 **다음 실행의 요구사항**이며 이번 작업에서 frozen executed config가 아니다.

1. 새 `core-run-*`의 extract는 비어 있고 초기 internal link는 없다. archive/input.tar,
   outside directory와 sentinel 생성·mode 설정 및 target 준비를 BEFORE 이전에 마친다.
2. Sentinel은 실제 secret이 아닌 owned writable regular file, initial nlink=1이며
   extract와 같은 device다. Existing default는 `outside/sentinel.txt`,
   content `inodefence protected sentinel\n`, mode `0600`이다. uid/gid와 umask를 기록한다.
3. Controller와 target에서 동일한 per-run absolute mount를 사용한다. Actual target
   CWD와 tar.x cwd는 `<run>/extract`, archive는 `<run>/archive/input.tar`다.
4. Target은 기존 immutable-image `IsolatedTarget`만 사용한다. Network none, read-only
   image, cap-drop ALL, no-new-privileges, non-root 동일 uid/gid, private IPC/cgroup,
   bounded pids/memory/tmpfs/output/file-size와 전체 descendant stop/cleanup을 검증한다.
   기존 backend에 없는 CPU/quota나 total filesystem quota가 enforced됐다고 기록하지 않는다.
   현재 ResourcePolicy 기본값은 memory 536,870,912 bytes, pids 64, open files 1,024,
   per-file size 67,108,864 bytes, tmpfs 33,554,432 bytes다. IsolationPolicy는 shm
   16,777,216 bytes와 stream별 output 1,048,576 bytes를 선언한다. 다음 실행에서 이 값과
   실제 enforcement를 freeze·검증해야 하며 이번 세션의 executed target 설정은 아니다.
5. Pair는 동일 Node/closure/worker/options/setup/limits를 사용하고 tar version만 바뀐다.
   Proposed timeout은 각 5초다. Image build와 benign readiness는 측정 budget 밖이다.
6. BEFORE와 AFTER 사이 harness namespace bookkeeping을 하지 않는다. Target 종료 및
   descendants 정지 후 AFTER, 그 후 cleanup한다. Rejection/timeout도 snapshot을 보존하며
   observation/cleanup/identity 오류는 infrastructure-invalid로 기록한다.

## 코드 수준 reachability와 observation

[M1](../../src/inodefence/mutator/m1.py)의 component vocabulary는
`a,b,dir,file,item,.,..`이고 depth 1–4, prefix와 separator 변형, 기존 raw name reuse,
link-target affix를 지원한다. [Benign seeds](../../src/inodefence/generator/minimal.py)는
`a.txt`, `b.txt`, `dir/`, `dir/a.txt`를 쓴다. 어느 operator도 `outside`나 `sentinel.txt`를
새로 합성하지 않는다. Inductively, reusable names와 affix도 이 두 component를 추가하지
않으므로 current default sentinel의 direct addressing은 불가능하다. 단순 no-hit pilot에서
이를 추정한 것이 아니다. `SentinelSpec(name='file')`만으로도 `outside/file`의 directory
component가 여전히 불가능하므로 G4를 통과하지 못한다.

USTAR builder는 hardlink type와 raw link target를 표현하므로 필요한 format 확장이 없다.
Generable owned external directory/name이 별도 승인된 setup에 존재하면 M1의 hardlink 추가,
link-target mutation 등으로 parent-relative target를 만드는 경로는 source상 구성 가능하다.
이는 아직 constructive generated-case proof나 measured rediscovery 확률이 아니다.

[Observer](../../src/inodefence/observer/snapshot.py)는 no-follow traversal, regular-file digest,
dev+inode 및 nlink/ctime/mode 등을 보존한다. [Oracle](../../src/inodefence/oracle/contracts.py)는
post-state extraction object와 protected sentinel의 identity equality로 C1을 판정하며
sentinel 전후 변화로 C2를 판정한다. Version/CVE/payload/exit-code를 truth로 쓰지 않는다.
N01이 persistent alias만 만든다면 C1=true, C2의 nlink/ctime 변화가 기대된다. Content
digest 변화는 필요하지 않고 C0=false일 수 있다. 모두 **예상**이며 실제 pair 결과가 아니다.

[Pipeline](../../src/inodefence/pipeline.py)은 setup/prepare → BEFORE → contained execute
→ AFTER → cleanup을 유지한다. Snapshot은 transient access, sandbox 밖 효과,
symlink referent, inode reuse 또는 check/use causal 관계를 증명하지 못한다.
완전한 nonviolation도 safety proof가 아니며 C3/C4/native effect producer는 N01의
persistent C1 qualification을 위해 필요하지 않다.

## 최소 후속 작업과 PROPOSED Task Contract

**단계 A: 독립 contained pair qualification.** 기존 host/controller broker를 준비하고
정확한 production wrapper locks와 두 images를 build·verify한다. 수정 가능 영역은 새
N01 configuration/evidence, `tools/benchmarks/node-tar/`의 supplied locks 및 필요한
qualification-only orchestration이다. 기존 adapter, generic mutator/observer/oracle/feedback,
native v1/v2 구현과 옵션/acceptance rules는 금지 영역이다. 새 runner가 필요하면 입력/출력과
실행 budget을 별도 확정한 뒤 구현한다. 이 조사에서 runner를 추가하지 않았다.

완료 조건: runtime boundary 및 두 release의 benign readiness, immutable provenance,
별도로 식별된 harmless controlled positive-control TAR의 fresh 3+3 동일-input replay,
각 raw snapshot/returned outcome/exception/cleanup 기록, reader 재검증과 root-cause review.
Positive control은 initial corpus와 별도 보존하고 rediscovery로 계산하지 않는다.
No-hit fuzz pilot은 fixed-proof를 대신하지 못한다. 이 단계는 G4 addressing 구현 없이도
기존 builder/run_case로 수행 가능하다.

**단계 B: generic reachability/setup contract.** Candidate를 fuzz-ready로 만들기 전에
public controlled addressing을 확정해야 한다. 최소 대안은 (a) 기존 outside layout을 유지하고
명시적 generic address vocabulary를 versioned config로 공급하거나 (b) generable external
directory/name을 허용하는 runtime setup profile이다. 하나를 선택해 별도 Task Contract와
관련 design/provenance/config impact를 검토한다. 이번 작업에서 어느 의미도 변경하지 않는다.
단순 name 변경, PoC-derived seed 또는 target-specific recipe 삽입은 해결책이 아니다.

완료 조건: unchanged four benign seeds에서 deterministic generic mutation lineage와 case/TAR
hash를 보존한 constructive proof, 동일 setup/vocabulary를 모든 comparison arm에 적용,
zero seed-phase C1/C2 anomaly, run_case의 실제 protected set/config binding 및 benign gate.
그 후에만 separate pilot와 formal experiment freeze로 진행한다. Full-step timing과
interrupted-run orchestration/known-class adjudication은 formal comparison 전 별도 필요하며
최초 C1 pair qualification의 신규 oracle 기능은 아니다.

## 독립 연구 리스크와 판정

| 리스크 | 영향과 최소 통제 |
| --- | --- |
| 환경 blocker를 target failure/no-hit로 혼동 | 현재 historical invocation은 0회다; BLOCKED로 보존하고 denominator에 no-hit를 추가하지 않는다 |
| Addressing 불가능성을 낮은 hit probability로 오해 | G4 constructive proof와 setup freeze 전 random pilot 금지 |
| Advisory absolute PoC와 relative arm을 동일 실행 근거로 표현 | Linux/default-options relative-arm same-input replay와 patch correspondence 필요 |
| Pair dependency 또는 runtime drift | Source locks와 wrapper locks 구분, 동일 closure/worker/Node, observed immutable image identity |
| C2 metadata 또는 dangling symlink를 N01 rediscovery로 승격 | Surviving C1와 human known-class matching 필요; content overwrite를 강제하지 않는다 |
| Native qualification 결과의 범위 확대 | #88/#89 negative evidence는 해당 target/mechanism 한정; final-state N01 gate와 분리 |
| 과거 raw 위치/checksum만으로 independent validation 주장 | 이번 작업에서 접근·검증한 artifacts와 이전 summary 인용을 구분 |
| 단일 positive control에서 feedback 연구 가설 도출 | Controlled replay는 detector/pair qualification만 지지; effectiveness에는 benign-origin paired campaigns 필요 |

**다음 실험 진행 여부: BLOCKED.** 현재 실행 transport/binding이 없고 G4도 미충족이다.
이는 N01의 Linux 재현 불가능성 또는 연구 가설 반증을 뜻하는 NO-GO가 아니다.
공식 fix와 persistent C1 detector의 의미적 정합성은 지지되지만 actual effect,
generic generation, qualified historical pair와 feedback effectiveness는 아직 입증되지 않았다.

## 실행 증거와 validation 기록

Local raw investigation directory:
`experiments/raw/n01-historical-qualification-20261014/` (ignored).
`environment.json`, `isolation-support.json`, `dev-environment-check.json`, `remote-refs.json`,
`pr-88.json`, `pr-89.json`, `pr-revision-review.json` 및 official static acquisition을 보존한다.
이는 experiment RunResult bundle이 아니다. Historical target invocations **0**,
campaign RNG/budget **N/A**, generated attack archives **0**.

- `python scripts/check_dev_env.py`: PASS, disposable runtime filesystem checks.
- `python scripts/check_linux_isolation_support.py`: exit 1, 8/8 namespace probes denied;
  expected infrastructure blocker이며 target verdict가 아니다.
- Official static acquisition 첫 attempt: network read timeout으로 incomplete;
  원본 파일을 유지하고 retry 결과와 구분했다. Retry의 21개 download record는 complete이고
  두 release와 공통 의존성 다섯 개의 artifact integrity가 일치한다.
- `make check`: **PASS** at clean `3e40af4039034c97409640128afaaf73a8de7908`;
  Ruff, format, Pyright, **1,437 tests**, environment와 docs checks 통과.
- Final documentation/evidence update 후 `make docs-check`와 `git diff --check`: **PASS**.
- Fresh Python process에서 45개 retained file, archive와 summary의 SHA-256 재검증:
  **PASS**. Archive member는 extractfile로 읽었고 filesystem에 extraction하지 않았다.
- N01 historical extraction / contained integration / affected-fixed replay: **NOT_RUN**.

[작은 machine evidence](n01-historical-qualification-v1.json)는 원본에서 생성한 derived
investigation record다. Current-session 환경 진단, official download URLs/hashes, production
closure, shipped-source 검토, PR revisions와 actual validation 결과를 보존한다. JSON SHA-256:
`49ed52c5ae5d23911a07aff707b9398e1806da320b9aab2050f67700f2f90411`.
Raw bundle은 `experiments/raw/n01-historical-qualification-20261014.tar.gz`, SHA-256
`be9657409b48f11223fb5b5fd0544e716f7a2dd1fec95558183a2cf39dc015ed`다. Bundle의
45개 원본/조사 artifact 및 별도 checksum manifest는 local workspace에 보존했고 Git에는
작은 보고서와 JSON만 올렸다. Ignored raw bundle은 PR로 배포된 artifact가 아니다.
Derivation은 retained `derive_evidence.py`를 사용하며 기존 output을 overwrite하지 않는다.
Fresh-reader 검증은 checksum/content integrity 범위이며 historical snapshot reader 또는
actual extractor replay 검증이 아니다. 후속 변경은 documentation/evidence만 추가하므로
위 canonical test 결과는 실행한 clean revision에 한정해 기록하고 final docs를 재검사했다.

Skill evidence 분류: historical finding에 대해 **RAW ONLY / no execution evidence**.
Source review/diagnostic evidence를 REPRODUCIBLE finding 또는 PAPER-READY로 승격하지 않는다.
