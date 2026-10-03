# 프로젝트 범위

## 한 문장 정의

InodeFence는 TAR entry를 반복적으로 변형하고 실제 extractor를 실행한 뒤, filesystem object identity와 external effect를 관찰하여 새로운 보안 관련 상태를 다음 mutation에 활용하는 state-guided TAR extraction fuzzer를 목표로 한다.

## 문제 정의

기존 archive extraction 보안 검사는 주로 path confinement를 본다.

> archive path가 extraction root 밖으로 나가는가?

InodeFence는 더 넓은 질문을 한다.

> extraction 이후 또는 과정에서 만들어진 filesystem object 관계가 의도한 보안 경계를 위반했는가?

경로는 내부에 있는 것처럼 보여도 실제로는 외부 object를 참조하거나 영향을 줄 수 있다.

## 핵심 아이디어

TAR archive를 filesystem을 변화시키는 entry sequence로 본다.

```text
Entry 1 -> State S1
Entry 2 -> State S2
Entry 3 -> State S3
```

Crash, code coverage, output path만 feedback으로 쓰는 대신 다음과 같은 보안 관련 state를 탐색한다.

- object type
- `st_dev`, `st_ino`
- link count
- hardlink relation
- symlink target
- internal ↔ external identity relation
- external content/metadata effect

## 신규 기여라고 주장하지 않는 것

다음 아이디어 자체를 연구 기여라고 표현하지 않는다.

- TAR fuzzing
- hardlink 사용
- symlink 사용
- archive entry order 변경
- filesystem state 관찰
- outside-root write 탐지
- feedback-guided fuzzing 일반

선행연구가 이미 서로 다른 형태로 이 요소들을 다룬다.

## 현재 Research Gap 가설

현재 가설은 archive extraction에 다음 feedback loop가 의미가 있는지 검증하는 것이다.

1. generic archive-entry mutation 수행
2. 실제 extractor 실행
3. filesystem security state 관찰
4. 처음 보는 security-relevant state를 만든 입력 보존
5. 해당 입력을 다시 mutation

이 접근법이 적절한 baseline보다 탐색 효율을 높이는지 실험으로 확인해야 실제 기여가 성립한다.

## 초기 범위

- Format: TAR
- Platform semantics: Linux
- 주요 object: regular file, directory, hardlink, 필요한 symlink subset
- 초기 target: node-tar, oras-go
- 선택 target: GNU tar
- 초기 관찰 방식: extraction 전/후 filesystem snapshot
- 핵심 보안 축: object identity, external effect

## 명시적인 Non-Goal

첫 버전에서는 다음을 해결하지 않는다.

- 모든 archive format
- 모든 filesystem
- Windows-specific NTFS semantics
- 일반적인 race-condition discovery
- kernel filesystem vulnerability discovery
- 모든 symlink semantics
- 전체 parser differential testing
- symbolic execution

## Zero-Day가 없어도 연구는 성공할 수 있음

다음 결과로도 충분히 프로젝트의 연구성을 평가할 수 있다.

- known vulnerable behavior의 안정적인 rediscovery
- baseline 대비 측정 가능한 개선
- 여러 extractor에 동일한 모델 적용
- 재현 가능한 실험 결과

새로운 vulnerability 발견은 추가 성과이며 필수 성공 조건이 아니다.
