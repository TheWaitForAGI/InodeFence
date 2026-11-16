# 소개 영상 파이프라인

녹음 대본 블록 하나가 영상 한 구간이다. 블록 순서·목표 길이·화면은 콘티 [`../demo-video-script.md`](../demo-video-script.md)(제품 시연 판, 2026-11-17)와 `build_video.py`의 `PLAN`·`SEQUENCES`·`SLIDES`가 같다. 콘티 파일이 그대로 녹음 대본이다(`--script`에 준다). 끝에 지원 문구 카드(4초)를 붙인다. 지원 문구는 공개 저장소에 두지 않고, 저장소 밖 파일에서 `--end-note`로 넘긴다.

## 실행

```text
nice -n 19 python3 paper/deliverables/video/build_video.py \
  --script paper/deliverables/demo-video-script.md \
  --recordings <2026-11-17 실행 기록 폴더> \
  [--values <W3 값 파일> --d12 ~/capstone-work/paper-w4/d12-conclusions.md] \
  --out <출력 폴더> [--incoming <녹음 폴더>] [--asr-python ~/capstone-work/tools/asr-venv/bin/python] \
  [--s09-running] [--takes takes.json] [--end-note "<지원 문구>"]
```

`--values`를 빼면 봉인 상태의 초안으로 만든다(장면 6·9는 결과 자리, `build.json`에 경고). 제출용 빌드에는 W3 값 파일을 반드시 준다. Pillow와 ffmpeg(libx264, libass)·ffprobe가 필요하다.

출력: `video.mp4`(1920×1080, 30 fps, H.264 + AAC 48 kHz), `video.srt`, `video.ass`(구워 넣은 자막), `build.json`(블록별 길이, 테이크 이름·SHA-256, 앞뒤 무음 자른 구간, 음성 인식 일치도, 경고). 이어서 `paper/deliverables/check_submission.py --mp4 … --srt … --values …`로 검사한다.

## 블록 처리

- **테이크:** `--incoming`에서 `<블록>-t<n>.<확장자>`를 찾고, n이 가장 큰 것을 쓴다. `--takes`로 고정할 수 있다. 얼굴 블록(s01, s07a, s10)은 카메라 영상(mp4/mov/m4v)을 받는다. 목소리 블록은 오디오(wav/m4a/mp3/flac)를 받아 슬라이드나 터미널 재생 위에 얹는다. 앞뒤 무음은 ffmpeg `silencedetect`로 자른다.
- **테이크가 없는 블록:** 대본의 목표 길이로 무음으로 만든다. 자막은 문장 길이 비례로 깔고, 오른쪽 위에 "무음 초안"을 표시한다. 11/17 초안이 이 경로다.
- **자막:**
  - 글자는 항상 대본 문장이다. 읽는 법 괄호는 빼고, 씨제로·씨원·씨투·아이노드는 C0·C1·C2·inode로 바꾼다.
  - 시간은 녹음이 있으면 `asr_align.py`에서 받는다. 이 도구는 로컬 faster-whisper(CPU, 별도 venv)로 돌리며, 외부로 보내지 않는다.
  - 일치도가 `--min-similarity`(기본 0.9)보다 낮거나 위치를 못 잡은 문장이 있으면 `build.json` 경고에 남는다. 이때는 들어 보고 재녹음을 판단한다. 자막을 인식 결과로 고치지 않는다.
- **장면 7 (s07c):** 블록 하나다(「고정했습니다」). 동결(2026-11-13) 뒤라 다른 판은 없다.
- **결과 자리 (s06, s09):** 화면에는 `본실험 결과 자리(봉인 해제 뒤 기입)`만 두고, 그 옆에 예상·방향·진행 상황 문장을 두지 않는다. s06은 녹음이 없는 카드다. s09는 값 파일 상태가 `미해제`면 s06과 같은 카드다(결과 자리 문구, 낭독 없음). 봉인 해제 전에 제출하기로 ORCH가 정하면 `--s09-running`으로 `s09-대기` 블록(d12 「실행 중」 문장)을 쓴다. 그 밖의 상태면 `s09-결과` 블록에 d12 낭독 판(값 괄호 없음)을 쓴다. 해제 뒤 화면 문장은 주장 목록 S-HOLDOUT 행에 따라 따로 넣는다.
- **슬라이드 장면 (s07d, s08, s04 끝의 budget 300 결과, s05b 뒤의 검증 수준 표):** `SLIDES`의 글자를 그대로 조판한다. 글자는 콘티의 화면 메모에서 가져왔고, 값은 주장 목록에 있는 것만 쓴다.
- **터미널 재생 (s03, s04, s04b, s04c, s05b):**
  - 사용자 명령 `inodefence`의 2026-11-17 `script` 기록(`rec01`–`rec06`, `<이름>.typescript`와 `<이름>.timing`)을 바이트 그대로 재생한다. 어느 블록이 어느 기록을 쓰는지는 `SEQUENCES`에 있고, 기록별 명령과 SHA-256은 콘티의 "실행 기록" 절에 있다.
  - 기록은 저장소 밖(`~/inodefence-rc-e2e-20261117/pr-c/recordings/`)에 두고 `--recordings`로 준다. 기록마다 `.meta.json`(inodefence 버전, 엔진 SHA, 호스트, Docker 버전, UTC 시각, 명령)이 있고 폴더의 `SHA256SUMS`가 전체 목록이다. `build.json`은 블록마다 쓴 기록의 SHA-256과 화면에 표시한 배속을 남긴다.
  - 블록에 들어가지 않으면 배속을 올리고 머리말에 배속을 표시한다. 글자를 손으로 쓰거나 고치지 않는다.
  - 재생기는 CR·LF·SGR 색만 해석한다. CR 뒤의 글자는 같은 줄을 제자리에서 덮어쓴다(`explore` 진행 줄).
  - 기록을 새로 남길 때는 깨끗한 클론과 새 venv에서 `script -q -e -T <이름>.timing -c "<명령을 담은 셸>" <이름>.typescript`로 남기고, 터미널 폭은 140칸(`COLUMNS=140`)으로 맞춘다. 2026-11-07 기록(`make demo`, 통제 재현 출력)은 이 판에서 쓰지 않는다.

## 지키는 것

- 봉인된 실험 출력은 열지 않는다. 값은 W3 값 파일에서만 받는다.
- 녹음과 영상 파일은 저장소 밖에 둔다.
- 실험 호스트에서는 `nice -n 19`, ffmpeg 2스레드로 돌린다.
