# src

이 폴더는 InodeFence의 설치 가능한 Python source 영역이다.

현재 실제 패키지는 [inodefence/](inodefence/README.md)다.

```text
src/
└── inodefence/
    ├── model/
    ├── generator/
    ├── mutator/
    ├── targets/
    ├── observer/
    ├── oracle/
    └── feedback/
```

모듈별 책임은 `inodefence/README.md`, 전체 시스템 설계는 `../docs/research/design/architecture.md`를 기준으로 한다.

연구 문서, raw experiment result, 논문 자료는 이 폴더에 두지 않는다.
