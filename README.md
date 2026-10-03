<div align="center">

# InodeFence

**압축을 푼 뒤, 파일시스템의 보안 경계는 안전할까?**

TAR 압축 해제 보안을 탐색하는 filesystem-state-guided fuzzing 연구 프로토타입

`TAR` · `Linux` · `Python 3.12` · `Research Prototype`

[시작 안내](docs/START_HERE.md) · [현재 상태](docs/STATUS.md) · [아키텍처](docs/research/design/architecture.md) · [개발 가이드](CONTRIBUTING.md)

</div>

---

## 무엇을 연구하나요?

InodeFence는 TAR 안의 파일 경로, 링크, 순서를 조금씩 바꾸고, 실제 압축 해제 프로그램이 만든 **파일시스템 상태**를 관찰하는 퍼저를 연구합니다.

핵심은 파일 이름뿐 아니라 **어떤 파일이 실제로 같은 객체를 가리키는지**, **추출 폴더 밖의 보호 파일이 바뀌었는지**까지 살펴보는 것입니다.

예를 들어 서로 다른 경로가 같은 inode를 가리키면, 내부 파일에 쓰는 작업이 외부 보호 파일에도 영향을 줄 수 있습니다.

```text
추출 폴더/result.txt ─┐
                     ├── 같은 파일 객체 (inode)
외부 보호 파일       ─┘
```

> 이런 객체 관계와 외부 변화를 다음 입력을 고르는 feedback으로 쓰면,
> 압축 해제의 보안 경계 위반을 더 잘 찾을 수 있을까요?

이것이 검증할 연구 가설입니다. 효과와 새로움은 선행연구 비교와 실험으로 확인할 예정입니다.

## 어떻게 동작하나요?

계획 중인 탐색 흐름은 다음과 같습니다.

```text
TAR 입력 생성·변형 → 압축 해제 → 상태 관찰 → 보안 계약 판정
       ↑                                      ↓
       └──────── 보존한 입력으로 다시 변형 ← 상태 기반 선택
```

| 관찰할 것 | 확인하려는 경계 |
| --- | --- |
| 생성된 파일의 경로 | 추출 폴더 밖으로 벗어났는가? |
| 내부·외부 파일의 객체 관계 | 보호 파일과 의도치 않게 같은 객체를 공유하는가? |
| 외부 보호 파일의 내용·메타데이터 | 압축 해제로 보호 파일이 바뀌었는가? |

초기 범위는 **Linux의 TAR 압축 해제**입니다. 대상 프로그램은 node-tar → oras-go → 일정이 허용하면 GNU tar 순으로 계획하고 있습니다. 자세한 판정 기준은 [Security Contract](docs/research/design/security-contracts.md)를 참고하세요.

## 지금 어디까지 왔나요?

**개발환경과 연구 설계를 마쳤고, 공통 데이터 모델 구현을 시작하기 직전입니다.** 실행 가능한 fuzzing pipeline은 아직 없습니다.

```text
✅ 개발환경 · 연구 설계
📍 다음: 공통 데이터 모델
⬜ 최소 실행 경로 → 입력 변형 → Feedback / Corpus → 실험·평가
```

최신 진행 상황과 다음 작업은 [STATUS](docs/STATUS.md)에 기록합니다.

## 둘러보기

| 목적 | 안내 |
| --- | --- |
| 프로젝트 이해하기 | [START_HERE](docs/START_HERE.md) |
| 코드와 폴더의 역할 보기 | [엔진 모듈 지도](src/inodefence/README.md) · [문서 지도](docs/README.md) |
| 연구 근거와 설계 읽기 | [연구 문서](docs/research/README.md) |
| 실험과 증거 살펴보기 | [experiments](experiments/README.md) · [findings](findings/README.md) · [paper](paper/README.md) |
| 개발에 참여하기 | [CONTRIBUTING](CONTRIBUTING.md) · [AGENTS](AGENTS.md) |

## 개발 시작하기

macOS 또는 Windows + WSL2에서 저장소를 **Dev Container**로 엽니다. 기준 환경은 Ubuntu 24.04 + Python 3.12입니다.

컨테이너 안에서 환경과 코드를 확인합니다.

```bash
make check
```

파일시스템 실험은 `/var/lib/inodefence`의 disposable sandbox와 보호용 sentinel에서 수행합니다. 환경 설정은 [개발환경 안내](.devcontainer/README.md)를 참고하세요.
