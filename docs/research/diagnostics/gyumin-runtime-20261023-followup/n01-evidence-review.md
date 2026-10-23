# N01 evidence 후속 기술 검토

검토 시각: 2026-10-23 KST. 이 문서는 AI 기술 검토이며 사람의 correspondence disposition이나
`N01_RELATIVE_HARDLINK_PAIR_QUALIFIED` token이 아니다.

## 원본 접근 경계

다음 historical evidence root는 현재 환경에 없다.

- `/Users/choijiwng/Projects/InodeFence-n02-evidence-20261015T122200Z`
- `/Users/choijiwng/Projects/InodeFence-n04-n01-reader-20261016.EVle7X`
- `/var/lib/inodefence/evidence/n02-n01-qualification-20261015T122200Z`

따라서 raw per-run JSON, raw manifest와 기존 independent/final manifest bytes는 이번에 재해시하지
못했다. N04가 기록한 raw manifest `2a05b5c9…fac`, independent `5c8c5a18…2ae`, final
`0665f739…f59`는 문서 기록이며 이번 직접 원본 감사 결과가 아니다.

반면 다음 ignored local static acquisition 원본은 실제로 존재했다.

`/workspaces/InodeFence/experiments/raw/n01-historical-qualification-20261014/`

이 디렉터리는 `.gitignore:33`의 `experiments/raw/*`로 제외된 비추적 자료다. N02 evidence root의
일부로 가정하지 않았다. `checksums.sha256` 전 항목을 현재 bytes로 검사했고 모두 OK였다.

## 이번에 직접 검증한 package와 source

| Artifact | 현재 SHA-256 | 계약/N02 선언값과 일치 | 판정 |
| --- | --- | --- | --- |
| `tar-7.5.2.tgz` | `22d8b674a68754ea909d03aa13958a7d2fd5e78af8a8f0cde6455babef7aaf1a` | 예 | 직접 재해시 |
| `tar-7.5.3.tgz` | `9d95d0cf786786360f97c1e414caea8a14452dc337fda17ba256ae7762c2ec66` | 예 | 직접 재해시 |
| 7.5.2 `dist/commonjs/unpack.js` | `6d99259843eebfd4ad305c991b03579d1e616fbd8372e2775026858e78e9cafa` | local manifest와 일치 | tar member와 보존 copy byte-identical |
| 7.5.3 `dist/commonjs/unpack.js` | `b4d7c53d87c34910775dca2aa5349735486ae592a17fc84a0b50c06da9360ec0` | local manifest와 일치 | tar member와 보존 copy byte-identical |

`acquisition-retry.json`은 registry URL, file mtime, SHA-256과 SRI match를 기록하고
`target_executed=false`, `npm_signatures_verified=false`를 명시한다. 이 bytes를 새로 내려받지
않았고 기존 local bytes를 검사했다.

직접 source 비교 결과 7.5.2 `unpack.js:242-289`는 `entry.path`의 `..`와 absolute root만 검사하고
hardlink `entry.linkpath`에는 같은 sanitizer를 적용하지 않는다. 7.5.3 `unpack.js:253-313`은 공통
`STRIPABSOLUTEPATH(entry, field)`를 만들고 `path`와 `linkpath` 모두에 적용한다. 두 distribution은
hardlink CWD resolution을 유지한다. 이는 fixed stderr `linkpath contains '..'`의 source-level
기대와 일치한다.

중요한 경계는 다음과 같다.

- 현재 local tarball hash가 N02 선언 digest와 같으므로 **content-addressed bytes는 동일 digest**다.
- 그러나 N02 retained root가 이 tarball을 보존하지 않았고 local static directory와 historical
  Docker build 사이의 immutable path/reference edge를 이번에 다시 열 수 없다.
- 따라서 package source 차이는 직접 검증했지만, 이를 곧바로 historical execution provenance의
  독립 재검증 또는 사람 correspondence 완료로 승격하지 않는다.

## 동일 입력

현재 후보 source에서 target을 실행하지 않고 N01 case/TAR를 재구성했다.

| 항목 | 값 | 판정 |
| --- | --- | --- |
| Child case ID | `55b8b7eda4bf26ec1e877866a099dd49195754e00e1e6f20dd82b0bb09288a87` | 직접 재구성 |
| TAR SHA-256 | `2af6de238713e83a630ad8c95f9385f2cf2e6127a9025bd71d7a2377a7e47ba6` | frozen constant와 일치 |

N02/N04 문서상 affected/fixed 5쌍은 이 동일 child와 TAR digest를 사용했다. Historical raw run을
이번에 열 수 없으므로 각 arm record가 실제로 이 bytes를 받았다는 edge는 문서 확인이며 현재 raw
재검증은 아니다.

## C0/C1/C2 근거와 한계

| Contract | N02/N04 retained 기록 | 실제 의미 | 이번 확인 수준 |
| --- | --- | --- | --- |
| C0 Path Boundary | 7.5.2 0/5, 7.5.3 0/5 | observed sandbox의 extraction root 밖 persistent existence/identity/type transition 없음 | 문서·oracle code 검토; raw 미접근 |
| C1 Object Identity | 7.5.2 5/5, 7.5.3 0/5 | affected `extract/b.txt`와 protected sentinel의 AFTER `(st_dev, st_ino)`가 모두 같음 | 문서·reader logic 검토; raw identity 값 미재해시 |
| C2 External Effect | 7.5.2 5/5, 7.5.3 0/5 | affected sentinel `nlink 1→2`와 `ctime` 변화 | 문서·reader logic 검토; raw field 값 미재해시 |

Affected의 content digest와 30-byte size는 불변이라고 기록돼 있다. 따라서 이 N01의 C2는
**metadata-only external effect**이며 content overwrite 증거가 아니다. C1은 inode 숫자 하나가
아니라 같은 run/filesystem에서 device와 inode가 모두 같은 object-identity 근거다.

Fixed 7.5.3은 5/5 `REJECTED`, exit 2, retained stderr
`TAR_ENTRY_ERROR: linkpath contains '..'`, alias 부재, sentinel 불변, C0/C1/C2 0/5로 기록돼 있다.
Rejection process status만으로 결론 낸 것이 아니라 alias/sentinel post-state를 함께 사용한 설계다.

현재 C0/C1/C2는 persistent BEFORE/AFTER snapshot 검출기다. 다음을 증명하지 못한다.

- 생성 후 제거된 transient effect 또는 direct path-use;
- observed sandbox 밖 object 접근/변화;
- symlink referent identity 자체;
- protected로 지정하지 않은 외부 object의 content/metadata effect;
- inode reuse의 인과 또는 어느 process가 변화를 만들었는지에 대한 독립 actor attribution.

Canonical 의미는 `docs/research/design/security-contracts.md:177-187`과
`docs/research/design/oracle-security-model-review-v1.md:44-46`에 있다.

## AI 검토와 사람 판단

이번 AI 검토가 직접 확인한 것은 local static tarball checksums/source diff, current-source frozen
TAR 재구성, 코드의 C0/C1/C2 derivation과 target-free tests다. Historical target을 재실행하지
않았고 raw evidence의 inode/field bytes를 열지 못했다.

사람 reviewer가 답해야 할 질문은 다음과 같다.

1. N02 raw manifest와 representative affected/fixed records를 immutable copy에서 직접 열었는가?
2. 두 arm의 referenced TAR SHA-256이 모두 `2af6…ba6`인가?
3. affected의 internal/sentinel `(st_dev, st_ino)`가 각 run에서 실제로 동일한가?
4. C2 changed fields가 `nlink`와 `ctime`이고 content digest/size는 불변인가?
5. fixed alias absence, unchanged sentinel과 exact stderr가 같은 input binding 아래 있는가?
6. local static package bytes와 historical build의 provenance gap을 받아들일지, 추가 build input
   evidence를 요구할지?
7. 이 근거를 known-class positive-control correspondence로 승인·거부·불충분 중 무엇으로 판정할지?

최종 상태는 계속 `AWAITING_HUMAN_CORRESPONDENCE_REVIEW`다. Machine PASS, CI와 이 AI 문서는 사람
판단을 대신하지 않는다.
