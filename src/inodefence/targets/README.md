# extractor 실행 경계

## 입력과 출력

[TargetAdapter](base.py)의 `run(archive_path: Path, extraction_root: Path) -> ExecutionResult`는 target이 멈춘 뒤 반환한다. Adapter가 command/version/options와 success/rejection/failure/timeout 분류를 소유한다. Observer·Oracle·Feedback은 target command를 알지 않는다.

CampaignTarget은 기존 단일 실행 Protocol에 `provenance: TargetProvenance` property를 추가한다.
Campaign은 실행 전 target ID/version/timeout을 고정하며 result drift를 거부한다. Reference는
같은 property의 ID/version과 configured timeout을 사용해 ExecutionResult를 반환한다.

## Reference target

[PythonTarfileTarget](python_tarfile.py)은 별도 interpreter에서 [_python_worker](_python_worker.py)를 실행한다. Worker는 uncompressed TAR와 명시적인 `filter="data"`, `errorlevel=2`를 사용한다. FilterError는 REJECTED, parser/IO 오류는 FAILED로 반환한다. Timeout은 subprocess.run이 worker를 종료·회수한 뒤 반환한다. Unexpected harness 실패는 exception으로 올린다.

Command, Python patch version, configured `timeout_seconds`, actual `duration_seconds`와 stdout/stderr를 모든 반환 status에 기록한다. Duration은 `perf_counter()`로 subprocess.run 직전부터 완료 또는 timeout kill/wait 후까지 측정하며 process startup과 timeout cleanup/wait overhead를 포함한다. Path validation과 pipeline의 setup/snapshot/판정/cleanup은 제외하고 timeout 설정값을 복사하지 않는다. Raw execution evidence이며 security verdict, StateSignature나 case identity로 사용하지 않는다. Output은 UTF-8/surrogateescape로 decode하여 undecodable bytes도 JSON evidence에서 복원할 수 있다. Data filter가 archive mode를 제한하거나 일부 입력을 변형할 수 있으므로 builder의 mode 보존과 reference의 extraction policy를 구분한다. 실패 후 부분 state도 runner가 관찰한다. 동작 기준은 [Python tarfile 문서](https://docs.python.org/3.12/library/tarfile.html#extraction-filters)다.

이 target은 **architecture 검증·integration·reference baseline용**이며 node-tar 대체 benchmark가 아니다. 최종 adapter 우선순위 node-tar → oras-go → 선택 GNU tar는 유지한다.

## 실행 경계

Reference는 동일 run의 archive/input.tar와 extract/ 경로를 검증하고 runtime symlink component를 거부한다. Directory layout은 cleanup 경계이고 OS 권한 격리가 아니다. Unsafe benchmark adapter는 추가 process/filesystem isolation을 제공하고 timeout 후 자식 process까지 멈춘 상태를 보장해야 한다. [architecture](../../../docs/research/design/architecture.md)와 [observer](../observer/README.md)를 따른다.

`run`은 BEFORE/AFTER 관찰 구간 안에서 호출된다. Harness setup/log/bookkeeping의 namespace write는 이 구간 밖에서 해야 한다. Diagnostics는 현재 reference처럼 ExecutionResult로 반환한다. Region.HARNESS는 target mutation의 면제 영역이 아니므로 adapter bookkeeping을 archive 아래에 기록해도 C0에서 자동 제외되지 않는다. Snapshot은 actor provenance가 없어 계약을 어긴 harness write를 target effect와 구분하지 못한다. 향후 adapter가 이 lifecycle을 지킬 수 없으면 별도 provenance/관찰 설계가 필요하다.
