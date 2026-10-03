# 위협 모델

## 공격자 능력

공격자는 victim 또는 service가 압축 해제할 악성 TAR archive를 제공할 수 있다고 가정한다.

공격자는 archive entry의 다음 속성을 제어할 수 있다.

- entry type
- path
- link target
- entry order
- duplicate entry
- 특정 entry 처리 시점에 참조 target이 존재하는지 여부

초기 entry type:

- regular file
- directory
- hardlink
- 필요한 범위의 symbolic link

## Victim 동작

Target extractor는 공격자가 제공한 TAR를 지정된 extraction directory에 해제한다.

보안 기대사항은 archive 처리 때문에 extraction boundary 밖의 보호된 filesystem object가 의도하지 않게 영향을 받지 않는 것이다.

## 초기 보안 경계

각 test run은 disposable sandbox를 사용한다.

```text
run-UUID/
├── outside/
│   └── protected sentinels
└── extract/
    └── extraction destination
```

`outside` directory는 보호된 외부 상태를 의미한다.

## 초기 모델에서 공격자가 할 수 없다고 가정하는 것

첫 버전에서는 공격자가 다음을 수행할 수 있다고 가정하지 않는다.

- extraction 실행 중 filesystem을 외부 process로 동시에 변경
- 외부 process를 이용한 validation/use race
- kernel/filesystem implementation bug 악용
- sandbox 외부 host에 대한 임의 접근

LinkZard의 OpLock과 같은 runtime 외부 조작 모델은 초기 범위에서 제외한다.

## Security Failure 후보

다음과 같은 경우 보안 관련 상태로 본다.

- 생성/사용된 path가 의도한 extraction boundary를 직접 벗어남
- 내부 path가 외부 sentinel과 의도하지 않게 동일 identity를 공유
- 외부 sentinel content/metadata 변경
- 보호된 외부 object가 의도하지 않게 생성/교체/삭제/link
- extraction root가 redirect되어 confinement boundary의 실제 의미가 변경

## 안전 요구사항

- 실제 민감 파일을 sentinel로 사용하지 않는다.
- 개발자 home directory를 실험 target으로 사용하지 않는다.
- 전용 runtime root만 사용한다.
- disposable run directory를 정리한다.
- intentionally saved finding/experiment data만 지속 보관한다.
