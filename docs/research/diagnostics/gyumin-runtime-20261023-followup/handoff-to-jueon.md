# 주언 인계 — N05/Track A runtime 경계

기준: 2026-10-23 KST. 아래 값은 실행 승인이 아니며 실제 N05/Track A result가 아니다.

## Source

- 최신 Track A Unit 3 head: PR #120
  `02072c95537d76d1b213b9c858d96c97fff653cc`.
- N05 loaded-host-source fix: PR #115
  `e83349ed1592d536e3ec0fce3c7cb204cb5c6ec9`.
- 로컬 통합 후보: `8979f248ee77fb69259292adb9c32fda371ea4e9` at
  `/tmp/inodefence-gyumin-runtime-20261023`.
- 이 후보는 #120 + #115이고 target-free focused 277 tests와 `make check` 1,757 tests가 PASS했다.
- 후보는 review/merge/authorization된 final source가 아니다. Unit 4 이후 clean SHA를 다시 동결해야
  하고, N05는 바로 그 exact SHA로 승인·실행되어야 한다.

PR #120 단독에는 `verify_authorized_runtime_files`가 없다. 따라서 final Track A stack을 정할 때
#115를 잃지 말아야 한다. 수동 재구현보다 #115 commit/diff를 통합하고 기존 tests를 유지한다.

## Environment와 target identity

N05 required host는 Mac arm64 + OrbStack, `/usr/local/bin/docker`, context `orbstack`, fresh Linux
arm64 controller다. 현재 WSL2 x86_64에는 Docker CLI가 없으므로 실제 admission은 미완료다.

| Identity | affected | fixed |
| --- | --- | --- |
| Node / node-tar | 22.22.0 / 7.5.2 | 22.22.0 / 7.5.3 |
| Image ID | `sha256:8b44887734511dbe9462f9b82f1c3128a8b445ebab2fa9b8db3fadcbc659c520` | `sha256:ed428826dd4b561f5b23035539137f0e7fe86c03c92eb5c7cae54a684fc7880f` |
| arm64 manifest | `sha256:b5ae7f5d2f85f12fa417ecece3e9089001266cc6bf4a997724c225a40ce8b542` | `sha256:3a1bcf4dffcd21ddc4fa6645980bebd96dceda4ceee0ddfe033abd0d50dd6ee0` |
| npm tarball SHA-256 | `22d8b674a68754ea909d03aa13958a7d2fd5e78af8a8f0cde6455babef7aaf1a` | `9d95d0cf786786360f97c1e414caea8a14452dc337fda17ba256ae7762c2ec66` |
| Lock SHA-256 | `31792107e9442ab18b04661d10ca0a0053db1fb7c58ca3aa702f1abb9908e243` | `a63d02f09d9a9fb2def77da84d5145984ff260fcedd19839ba96ec858fdfae24` |
| Build record SHA-256 | `960b28e0699af5c6ac35709d2d14d7a8818ea8cfed0039f86b3b0217c68997ef` | `e6adeae1456771dce3e0d20acb3e231ceefd5e726a4c8bf554fc402f62ac8960` |

Worker SHA-256은
`feb13d7be5f5718769bebd4b0e375ea3f535abffd45223494dd518263593498b`다. Local ignored static npm
tarball bytes는 위 hash와 직접 일치하지만 N05 exact host input path는 없으므로 실제 Mac에서
read-only copy와 image/build binding을 다시 admission해야 한다.

## Evidence, checksum, reader와 cleanup

- N05 attempt는 `n05-five-second-preflight-v2-attempt-001` 하나다.
- 4 affected + 4 fixed benign extraction, 각 5초, 전체 30분, no retry다.
- source/load-origin gate 이후 host ledger가 생성되는 순간 attempt가 소비된다.
- N05 Linux independent reader와 host verifier는 구현·synthetic test됐다.
- overall PASS는 Linux raw/final/independent checksum, host ledger, bounded stderr, deadline와 cleanup이
  모두 일치해야 한다.
- 현재 N05 host/Linux evidence가 없으므로 Track A가 소비할 checksum도 없다.
- N05 status는 `NOT_RUN`; 미실행을 PASS나 zero violation으로 입력하지 않는다.

## Track A 경로 연결

Units 1–3은 다음 원본을 recorded absolute path에서 다시 여는 read-only graph를 구현한다.

1. original pilot authorization bytes;
2. authoritative N05 host ledger;
3. authoritative N05 Linux evidence;
4. Track A evidence root/local admission records;
5. Track A host attempt ledger;
6. protocol file.

합성 tests는 통과했지만 Mac host path와 Linux controller namespace 사이의 real volume/mount mapping은
검증되지 않았다. 이 경로를 맞추기 위해 digest-only fallback, 큰 evidence tree 복제 또는 기존
isolation 완화를 추가하지 않는다. 배치가 exact absolute path를 제공하지 못하면 pilot을 거부한다.

## Unit 4 의존성과 주언 할 일

Unit 4는 규민 범위에서 구현하지 않았다. 주언이 이어서 해야 할 최소 항목은 다음과 같다.

1. 어느 host-ledger copy가 publication authority인지 사람 결정을 받는다.
2. `verify_track_a_final`과 analysis admission reporting이 20개 host-attempt terminal을 모두 final
   manifest에서 inventory/reopen하게 한다.
3. admission rejected, host failed/timeout/interrupted, campaign result를 서로 다른 denominator/status로
   보존한다. 0 execution을 no-hit으로 바꾸지 않는다.
4. final clean integrated SHA에 #115 loaded-source fix가 포함됐는지 확인한다.
5. 그 exact SHA에 대한 N05 authorization/PASS와 별도 Track A pilot authorization을 순서대로 받는다.
6. 실제 controller가 위 여섯 absolute path를 read-only로 다시 열 수 있음을 launch 전 배치
   검증한다.

## 승인 경계

N05 authorization은 exact 8-run preflight만 승인하며 `pilot_authorized=false`다. N05가 PASS해도
20 campaigns/4,000 executions를 승인하지 않는다. Track A에는 exact final SHA, original N05
host/Linux digests, target/controller/daemon/environment, 20-cell schedule, budget와 output/ledger paths를
결합한 별도 canonical 사람 승인서가 필요하다. CI, AI review, 이 인계 문서로 승인서를 대체하지
않는다.
