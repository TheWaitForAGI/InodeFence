# 고정 node-tar 버전 컨텍스트 (effect 이미지 빌드용)

이 디렉터리는 historical effect 이미지(`inodefence-node-tar-effect:<version>`)를 **재현 가능하게**
빌드하기 위한 버전별 `package.json` + `package-lock.json`이다. 빌드 레시피는
[`../effect/Dockerfile`](../effect/Dockerfile)이며 `--build-arg TAR_VERSION=<version>`으로 각 버전을 만든다:

```bash
docker build -f tools/node-tar/effect/Dockerfile --build-arg TAR_VERSION=7.5.6 \
  -t inodefence-node-tar-effect:7.5.6 .
```

## 범위

여기 들어간 버전은 **2026년 node-tar CVE 벤치마크**가 다루는 것들이다
([catalog](../../../experiments/benchmarks/catalog-v1.json)):

| 버전 | 역할 | CVE |
| --- | --- | --- |
| 7.5.2 / 7.5.3 | node-link-sanitize (취약/수정) | CVE-2026-23745 |
| 7.5.6 / 7.5.7 | node-hardlink-base (취약/수정) | CVE-2026-24842 |
| 7.5.7 / 7.5.8 | node-link-compose (취약/수정) | CVE-2026-26960 |

## lock 일관성

각 버전의 `package-lock.json`은 frozen lock 레지스트리
[`../../../experiments/benchmarks/locks/`](../../../experiments/benchmarks/locks/)의
`node-tar-<version>.package-lock.json`과 **바이트 동일**해야 한다. 7.5.2/7.5.3은 기존 frozen lock을
그대로 쓰고, 7.5.6/7.5.7/7.5.8은 같은 lock을 두 위치에 함께 추가했다.

이 디렉터리는 **빌드 입력일 뿐**이다. 어떤 버전을 실제 historical 데모에서 돌릴 수 있는지는 별도
allowlist가 정하며, native 실행은 승인된 안전 범위(고정 버전, disposable sandbox + sentinel)에서만 한다.

## 여기 없는 버전: 레지스트리 준비(exploratory)

이 디렉터리에 lock이 없는 node-tar 버전은 `make target-run TARGET=node-tar TARGET_VERSIONS=<X.Y.Z>
AUTO_PREPARE=1 ALLOW_REGISTRY_PREPARE=1`로만 돌릴 수 있다(`scripts/node_tar_registry_prepare.py`).
실행 시점에 공개 npm 레지스트리로 임시 lock을 만들어 검사한 뒤 같은 Dockerfile로
`inodefence-node-tar-registry:<X.Y.Z>`를 빌드하고, 결과는 `exploratory demo run`으로 표시된다.

한계: integrity 대조는 "생성한 lock이 같은 실행에서 레지스트리가 공표한 값과 일치한다"까지만
보인다. 레지스트리 자체가 바뀌었거나 오염된 경우는 막지 못한다. 그래서 exploratory이고, 재현
근거는 출력 폴더에 저장된 lock 파일과 그 SHA-256뿐이다. 받은 패키지의 안전성도 보증하지 않는다.
이 경로는 이 디렉터리에 아무것도 쓰지 않는다. 버전을 verified로 올리려면 위 절차대로 lock을
커밋하고 검토한다(자동 승격 없음).
