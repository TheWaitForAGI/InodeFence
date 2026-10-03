# 용어집

이 문서는 InodeFence에서 자주 쓰는 단어를 **프로젝트 기준으로 쉽게 설명**한다.

## Archive / TAR

여러 파일과 metadata를 하나로 묶은 입력 파일.

InodeFence의 1차 연구 대상은 TAR다.

## TAR Entry

TAR 안에 들어 있는 하나의 항목.

예:

- regular file
- directory
- symlink
- hardlink

TAR는 entry를 순서대로 처리하기 때문에 **entry order도 filesystem 결과에 영향을 줄 수 있다.**

## Regular File

일반적인 파일.

예: `hello.txt`

## Symlink

다른 **path**를 가리키는 특수 파일.

예:

```text
link -> ../target
```

핵심은 "다른 inode를 가진 링크 파일이 경로를 가리킨다"는 것이다.

## Hardlink

서로 다른 파일 이름이 **같은 filesystem object**를 가리키는 관계.

```text
a.txt ─┐
       ├── inode 123
b.txt ─┘
```

## inode

Linux filesystem에서 file object를 식별하는 핵심 번호.

InodeFence에서는 보통 inode 번호만 보지 않고:

```text
(st_dev, st_ino)
```

를 object identity 비교에 사용한다.

## st_dev

어느 filesystem/device의 object인지 나타내는 값.

## st_ino

해당 filesystem 안에서 object를 식별하는 inode 번호.

## st_nlink

같은 inode를 가리키는 hardlink 개수.

## Extraction Root

압축을 풀기로 한 기준 directory.

예:

```text
/extract
```

정상적인 extractor라면 의도하지 않은 방식으로 이 경계 밖을 건드리지 않아야 한다.

## Sentinel

실험에서 "외부 보호 파일" 역할을 하는 가짜 파일.

실제 `/etc/passwd` 같은 파일을 사용하지 않고 다음처럼 안전한 파일을 만든다.

```text
run-123/
├── outside/
│   └── sentinel.txt
└── extract/
```

## Mutation

기존 test case를 조금 바꾸는 것.

예:

- entry type 변경
- path 변경
- link target 변경
- entry order 변경
- entry 추가/삭제/복제

## Seed

Mutation을 시작할 때 사용하는 입력.

## Corpus

퍼저가 다음 mutation에 다시 사용할 가치가 있다고 판단해 보관한 seed 집합.

## Feedback

"이 입력을 보관할 가치가 있는가?"를 결정할 때 사용하는 실행 결과.

InodeFence에서는 filesystem security state가 핵심 feedback 후보다.

## State Snapshot

특정 시점의 filesystem 상태를 기록한 것.

예:

- path
- type
- inode
- link count
- size
- symlink target
- content hash

## State Signature

Snapshot 전체를 그대로 비교하지 않고, fuzzing feedback에 필요한 특징을 정규화한 표현.

"이전에 본 상태인지 아닌지" 판단하는 데 사용한다.

## Security Contract

Extractor가 지켜야 하는 일반화된 보안 규칙.

특정 CVE 이름과 독립적으로 정의한다.

## Oracle

이번 실행이 Security Contract를 위반했는지 판정하는 코드.

## Object Identity Confinement

Extraction 내부 object가 보호된 외부 object와 의도하지 않게 같은 identity를 공유하면 안 된다는 contract.

## External Effect Noninterference

Archive extraction 때문에 보호된 외부 object의 content/metadata가 의도하지 않게 바뀌면 안 된다는 contract.

## Path Boundary Confinement

생성/해석된 path가 의도한 extraction boundary를 직접 벗어나면 안 된다는 가장 기본적인 contract.

이 contract는 중요하지만 **InodeFence의 novelty는 아니다.**

## Target

퍼저가 실제로 실행할 archive extractor.

예:

- node-tar
- oras-go
- GNU tar

## Target Adapter

각 extractor의 실행 방법 차이를 공통 interface 뒤로 숨기는 모듈.

## Baseline

제안 방법이 실제로 나은지 비교하기 위한 기준 방법.

예:

- Random Mutation
- Path-State Feedback
- Fixed Strategy

## Ablation

제안 방법의 일부 요소를 빼고 다시 실험하여 **어떤 요소가 효과에 기여하는지** 확인하는 방법.

예:

```text
Path only
Path + Type
Path + Identity
Path + Identity + Effect
```

## PoC

Proof of Concept.

특정 취약점이 실제로 재현된다는 것을 보여주는 최소 입력/코드.

Known CVE PoC는 benchmark 분석에는 사용할 수 있지만 proposed fuzzer의 기본 seed로 직접 넣지 않는다.
