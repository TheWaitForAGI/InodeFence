# filesystem 사실 관찰

## 입력과 출력

`capture_state(sandbox_root, phase, protected_paths) -> StateSnapshot`

`compare_states(before, after) -> tuple[StateChange, ...]`

[Snapshot 구현](snapshot.py)은 sandbox 전체의 reachable tree를 관찰한다. `StateSnapshot = full raw observation/evidence`이므로 `archive/input.tar` SHA-256과 harness metadata도 제외하지 않는다. [공통 Region](../model/README.md)은 extract/를 EXTRACTION, `.`과 archive/를 HARNESS, 나머지를 EXTERNAL로 분류한다. Outside sentinel뿐 아니라 root-level escape와 기타 external namespace 생성·삭제도 기록한다. 비교는 같은 root/보호 대상의 BEFORE/AFTER에만 허용한다.

## 수집 의미

경로마다 lstat type, st_dev/st_ino/st_nlink, mode, size, uid/gid, mtime/ctime nanoseconds, symlink text와 regular SHA-256을 보존한다. Digest는 stream으로 계산하고 content 전체는 저장하지 않는다. atime은 관찰 자체의 read effect를 피하려고 제외한다.

Directory descriptor와 O_NOFOLLOW를 사용한다. Symlink를 따라 stat/hash하거나 directory로 내려가지 않는다. FIFO 같은 special object는 열지 않는다. IO/permission 오류는 ObservationError이며 missing sentinel과 구분한다. 동시 filesystem 변경은 초기 threat model 밖이고, digest 중 불일치가 감지되면 오류로 올린다.

부재는 snapshot path 없음으로 표현하되 protected_paths를 유지한다. [모델](../model/README.md)에 순서/identity 의미가 있다. Compare는 생성·삭제·type·identity·content·metadata 변화를 사실로 반환한다.

HARNESS 변화도 다른 region과 동일하게 관찰·비교하며 security trust를 부여하지 않는다. Region.HARNESS의 signature 제외는 Feedback normalization 정책이고, C0는 extraction root 밖의 persistent namespace transition을 별도로 검사한다. Snapshot/compare는 actor를 식별하지 않는다. 정상 setup과 실행 효과를 구분하려면 runner가 setup 완료 후 BEFORE, target 종료 후 bookkeeping/cleanup 이전 AFTER를 찍어야 한다. Phase label 검증만으로 이 lifecycle을 증명하지는 않는다.

`StateSignature = normalized security-state representation for future feedback/corpus`는 [feedback](../feedback/README.md)의 책임이다. Harness를 signature에서 제외해도 raw observation/change/identity group의 정보는 줄이지 않는다. ArchiveCase/TAR artifact identity를 feedback key로 유출하지 않는 invariant는 signature scope에서 적용한다.

## 하지 않는 것

취약점·interestingness 판정, target 실행, CVE/target 정책. 결과는 [oracle](../oracle/README.md)과 [signature](../feedback/README.md)에서 별도로 소비한다. Transient operation이나 symlink referent identity는 snapshot에 없다.
