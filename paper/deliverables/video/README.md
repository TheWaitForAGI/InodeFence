# 소개 영상 파이프라인

녹음 대본 블록(s01…s10) 하나가 영상 한 구간이다. 순서는 구성안 v2(장면 1~10)를 따르고, 끝에 지원 문구 카드(4초)를 붙인다. 지원 문구는 `--end-note`로 넘긴다(공개 저장소에 두지 않는다). EXP-0 장면은 없다.

## 실행

```text
nice -n 19 python3 paper/deliverables/video/build_video.py \
  --script ~/capstone-work/video-handoff/recording-script-v1.1.md \
  --values <W3 값 파일> --d12 ~/capstone-work/paper-w4/d12-conclusions.md \
  --out <출력 폴더> [--incoming <녹음 폴더>] [--asr-python ~/capstone-work/tools/asr-venv/bin/python] \
  [--freeze ga|na] [--s10-before-freeze] [--takes takes.json] [--end-note "<지원 문구>"]
```

출력: `video.mp4`(1920×1080, 30 fps, H.264 + AAC 48 kHz), `video.srt`, `video.ass`(구워 넣은 자막), `build.json`(블록별 길이, 테이크 이름·SHA-256, 앞뒤 무음 자른 구간, 음성 인식 일치도, 경고). 이어서 `paper/deliverables/check_submission.py --mp4 … --srt … --values …`로 검사한다.

## 블록 처리

- **테이크:** `--incoming`에서 `<블록>-t<n>.<확장자>`를 찾고, n이 가장 큰 것을 쓴다. `--takes`로 고정할 수 있다. 얼굴 블록(s01, s07a, s10)은 카메라 영상(mp4/mov/m4v)을 받는다. 목소리 블록은 오디오(wav/m4a/mp3/flac)를 받아 슬라이드나 터미널 재생 위에 얹는다. 앞뒤 무음은 ffmpeg `silencedetect`로 자른다.
- **테이크가 없는 블록:** 대본의 목표 길이로 무음으로 만든다. 자막은 문장 길이 비례로 깔고, 오른쪽 위에 "무음 초안"을 표시한다. 11/17 초안이 이 경로다.
- **자막:**
  - 글자는 항상 대본 문장이다. 읽는 법 괄호는 빼고, 씨제로·씨원·씨투·아이노드는 C0·C1·C2·inode로 바꾼다.
  - 시간은 녹음이 있으면 `asr_align.py`에서 받는다. 이 도구는 로컬 faster-whisper(CPU, 별도 venv)로 돌리며, 외부로 보내지 않는다.
  - 일치도가 `--min-similarity`(기본 0.9)보다 낮거나 위치를 못 잡은 문장이 있으면 `build.json` 경고에 남는다. 이때는 들어 보고 재녹음을 판단한다. 자막을 인식 결과로 고치지 않는다.
- **장면 7 (s07c):** 기본값 `--freeze na`는 「고정하도록 계획했습니다」 블록과 그에 맞는 슬라이드 문구를 쓴다. 동결 기록이 올라간 뒤에만 `--freeze ga`(「고정했습니다」)로 빌드한다.
- **장면 9:**
  - 값 파일 상태가 `미해제`면 `s09-대기` 블록과 d12 「실행 중」 문장을 쓴다. 대본 문장이 d12와 다르면 멈춘다.
  - 그 밖의 상태면 `s09-결과` 블록에 d12 낭독 판(값 괄호 없음)을 쓰고, 슬라이드에 값을 채운 문어 판과 출처를 보인다.
  - `synthetic`이면 슬라이드에 SYNTHETIC 도장을 찍는다.
- **장면 8:** `scene8_slides.py`는 W1이 원본 기록과 대조한 문자열을 그대로 조판한다. 문자열을 바꾸면 W1이 다시 대조해야 하고, 그 전에는 빌드가 멈춘다.
- **터미널 재생:** 2026-11-07 `script` 기록(`~/inodefence-evidence/demo-recordings-20261107`)을 바이트 그대로 재생한다. 블록에 들어가지 않으면 배속을 올리고 머리말에 배속을 표시한다.

## 지키는 것

- 봉인된 실험 출력은 열지 않는다. 값은 W3 값 파일에서만 받는다.
- 녹음과 영상 파일은 저장소 밖에 둔다.
- 실험 호스트에서는 `nice -n 19`, ffmpeg 2스레드로 돌린다.
