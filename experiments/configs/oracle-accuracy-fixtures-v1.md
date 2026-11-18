# Oracle 정확도 fixture v1 — 손 라벨 (#514, exploratory)

**이 파일은 실행 전에 커밋한다.** 아래 "손 라벨"은 fixture의 구성과 `docs/research/design/security-contracts.md`의 C0·C1·C2 정의만 보고 적었다. oracle을 돌려 본 뒤 고치지 않는다. 등록 실험(EXP-3 train, EXP-2 holdout)과 섞지 않는 `exploratory` 측정이다. oracle의 판정 의미는 바꾸지 않는다.

## 재는 방법

- **세 가지를 나란히 적는다:** 손 라벨, 파일시스템 비교로 정한 정답, oracle 판정.
  - **파일시스템 비교**는 oracle과 독립된 작은 모듈로 한다(`os.walk`·`lstat`·내용 해시·`(st_dev, st_ino)`). observer·oracle·feedback 모듈을 import하지 않는다.
  - 손 라벨과 파일시스템 정답이 다르면 fixture나 라벨 쪽 문제다. 표에 그대로 남기고 고친 이유를 적는다.
- **추출기는 두 가지다.** 모두 일회용 샌드박스 안에서 프로세스 안으로 돌린다.
  - **통제(무검사):** `scripts/oracle_fixture_check.py`의 `UncheckedControlledExtractor`. entry를 그대로 따르고, 기존 파일에는 제자리에 쓴다. 모드·소유는 적용하지 않는다.
  - **python-tarfile `data` 필터:** 공격 형태 entry를 거부하는 쪽이다. 거부되면 세 계약 모두 `n`이 기대값이다.
- **결과 표:** fixture별 혼동표(손 라벨 / 파일시스템 정답 / oracle, 계약마다)와 미판정 원인만 적는다. 이 fixture 밖으로 일반화한 "정확도 %"는 쓰지 않는다.
- **샌드박스 밖으로 나가는 구성은 여기서 돌리지 않는다:** 절대 경로 이름, 두 단계 넘는 `..`. 이런 구성과 실제 추출기 버전 쌍은 Docker 격리 실행(HOST3·HOST4)으로 넘기고 이 표에는 "격리 실행 몫"으로 둔다.
- **C3 Extraction Root Integrity·C4 Check/Use Coherence**는 계약 정의가 `security-contracts.md`에 들어가기 전에는 "정의 전"으로만 둔다.

## fixture와 손 라벨 (통제 추출기 기준, C0 · C1 · C2)

| ID | 구성 | C0 | C1 | C2 | 손 라벨 근거(계약 정의) |
| --- | --- | --- | --- | --- | --- |
| F01 | 일반 파일 세 개(추출 루트 안) | n | n | n | 루트 밖 변화 없음 |
| F02 | 깊은 디렉터리(10단계) 안의 파일 | n | n | n | 루트 안 |
| F03 | 루트 안 하드링크 `b -> a` | n | n | n | 둘 다 루트 안, sentinel과 무관(기존 `normal`) |
| F04 | 루트 안 상대 symlink `l -> a` | n | n | n | 루트 안, C1은 symlink 객체만 본다 |
| F05 | 같은 이름 entry 두 번(루트 안 덮어쓰기) | n | n | n | 제자리 쓰기, 루트 안 |
| F06 | 일반 파일 `../escape.txt` | y | n | n | 루트 밖 새 이름 생성(기존 `c0`) |
| F07 | 일반 파일 `../outside/new.txt`(sentinel 옆 새 파일) | y | n | n | 루트 밖 새 이름, sentinel은 그대로 |
| F08 | 일반 파일 `../outside/sentinel.txt`(sentinel 덮어쓰기) | n | n | y | 통제 추출기는 제자리에 쓴다: 이름·identity 그대로, 내용·크기·mtime 변경. 라벨은 제자리 쓰기에 달려 있다: 지우고 새로 만드는 추출기라면 identity가 바뀌어 C0도 y |
| F09 | 하드링크 `alias -> ../outside/sentinel.txt` | n | y | y | inode 공유 + sentinel nlink·ctime 변경(기존 `c1`) |
| F10 | F09 뒤 `alias`에 일반 파일 쓰기 | n | y | y | F09 + 내용 변경 |
| F11 | symlink `link -> ../outside/sentinel.txt`만 | n | n | n | symlink 객체는 루트 안, sentinel 변화 없음 |
| F12 | F11 뒤 일반 파일 `link` 쓰기 | n | n | y | symlink를 따라 sentinel 내용 변경(기존 `c2`) |
| F13 | symlink `d -> ../outside` 뒤 `d/new.txt` 쓰기 | y | n | n | symlink 디렉터리를 거쳐 루트 밖 새 이름 생성 |
| F14 | symlink 사슬 `a -> b`, `b -> ..` 뒤 `a/escape2.txt` | y | n | n | 사슬을 거쳐 루트 밖 새 이름 생성 |
| F15 | 절대 경로 이름 `/…`, 두 단계 넘는 `../..` | — | — | — | 격리 실행 몫(샌드박스 밖) |
| F16 | 추출 루트 자체의 교체·권한 변경 | 정의 전 | | | C3 계약 정의 뒤 |
| F17 | 검사 시점과 사용 시점의 경로 해석 차이 | 정의 전 | | | C4 계약 정의 뒤 |

## python-tarfile `data` 필터의 기대값

F06–F14의 공격 형태는 `data` 필터에서 거부되거나(예외) 루트 안으로 바뀌어야 한다. 기대값은 C0·C1·C2 모두 `n`이고, 거부된 경우에는 "거부"로 적는다. F01–F05는 통제 추출기와 같다.
