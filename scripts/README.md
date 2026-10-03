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

환경 확인과 [TAR baseline 예제](../docs/examples/tar-baseline.md)의 fixture 생성·수동 관찰 명령이 있다. 자동 pipeline 실행 CLI는 아직 없다.

## 파일 배치 규칙

사용 목적을 알 수 있는 스크립트명과 입력 설정을 남긴다. 공통 엔진 로직은 src에 두고 raw output은 실험 기록으로 관리한다.

`python -m scripts.reference_campaign_pilot --output experiments/raw/<new-directory>`는 safe
Python reference만 사용하는 7개 작은 bounded campaign의 개발 검증이다. Explicit baseline
seeds, provenance, raw canonical results와 generated summary를 기록하며 exact repeat의 semantic
lineage/feedback, budget/cleanup을 assertion으로 검사한다. 기존 output을 덮어쓰지 않는다.
효과 평가나 일반 third-party campaign CLI는 아니다.
