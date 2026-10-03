# filesystem 사실 관찰

## 입력과 출력

`capture_state(sandbox_root, phase, protected_paths) -> StateSnapshot`

`compare_states(before, after) -> tuple[StateChange, ...]`

[Snapshot 구현](snapshot.py)은 sandbox 전체의 reachable tree를 관찰한다. extract/는 extraction 영역이고 나머지는 external 영역이다. outside sentinel뿐 아니라 external namespace 생성·삭제도 기록한다. 비교는 같은 root/보호 대상의 BEFORE/AFTER에만 허용한다.

## 수집 의미

경로마다 lstat type, st_dev/st_ino/st_nlink, mode, size, uid/gid, mtime/ctime nanoseconds, symlink text와 regular SHA-256을 보존한다. Digest는 stream으로 계산하고 content 전체는 저장하지 않는다. atime은 관찰 자체의 read effect를 피하려고 제외한다.

Directory descriptor와 O_NOFOLLOW를 사용한다. Symlink를 따라 stat/hash하거나 directory로 내려가지 않는다. FIFO 같은 special object는 열지 않는다. IO/permission 오류는 ObservationError이며 missing sentinel과 구분한다. 동시 filesystem 변경은 초기 threat model 밖이고, digest 중 불일치가 감지되면 오류로 올린다.

부재는 snapshot path 없음으로 표현하되 protected_paths를 유지한다. [모델](../model/README.md)에 순서/identity 의미가 있다. Compare는 생성·삭제·type·identity·content·metadata 변화를 사실로 반환한다.

## 하지 않는 것

취약점·interestingness 판정, target 실행, CVE/target 정책. 결과는 [oracle](../oracle/README.md)과 [signature](../feedback/README.md)에서 별도로 소비한다. Transient operation이나 symlink referent identity는 snapshot에 없다.
