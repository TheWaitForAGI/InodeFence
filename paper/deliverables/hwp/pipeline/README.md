# 결과보고서 HWP 파이프라인 (채움 → 그림 → 검사 → 렌더)

한 명령으로 학교 서식 HWP를 채우고 그림 2장을 넣는다. 이어서 검사와 독립 렌더, 근사 PDF까지 만든다. 한컴에서 그림을 넣는 사람 단계는 없어졌다.

```text
paper/deliverables/hwp/pipeline/setup_tools.sh <tooldir>        # 한 번
paper/deliverables/hwp/pipeline/build_report.sh <tooldir> <template.hwp> <sample-terms.json> <outdir>
```

- `<template.hwp>`(학교 서식)와 `<sample-terms.json>`(서식 견본의 이름·주제)은 공개 저장소에 두지 않는다. 서식의 sha256은 `../cell-map.json`이 고정한다.
- 출력:
  - `report.hwp`: 제출 입력본.
  - `report-approx.pdf`: rhwp 레이아웃과 대체 글꼴로 만든 근사본이다. 제출용이 아니다.
  - `check-form.txt`, `check-structure.txt`, `render/`(쪽 SVG·PNG), `build.log`(입력 sha256 포함).
- 같은 입력이면 `report.hwp`가 바이트 단위로 같다(2026-11-13, 두 번 실행해 sha256 일치).

## 단계

1. `fill_form.py fill`: 본문 원고(`../../capstone-report-form-body.md`)를 서식 칸에 넣는다.
2. `figures_step.py`: **■ 결과물 사진** 아래에 그림마다 행을 하나씩 만든다.
   - 표 폭 병합, 흰 배경을 넣고, 원래 캡션 행은 지운다.
   - 각 행에 그림을 글자처럼 넣고(폭 150 mm) 그 아래에 캡션을 둔다.
   - 행 높이는 그림 높이에 캡션 몫을 더해 선언한다. rhwp 0.9.0은 이렇게 하지 않으면 캡션 줄을 행 높이에서 빼고, 한컴은 셀 높이를 최소값으로만 쓴다.
3. `scrub_preview.py`: 서식의 PrvText(견본 문단)와 PrvImage(견본 쪽 축소판)를 같은 크기로 덮어쓴다. 한컴이 다시 저장하기 전에도 견본 이름이 파일에 남지 않는다.
4. 검사:
   - `fill_form.py check`: 견본 문구, 회색·기울임, 자리 표시.
   - `check_hwp.py`: olefile만 쓰는 독립 파서다. 그림 바이트 sha256이 원본과 같은지, 기존 스트림이 그대로인지, 본문 손실이 0인지 본다. 셀 수 변화는 `--cell-delta`로 허용한다.
5. `render.sh`: rhwp 0.9.0으로 쪽 SVG를 만들고, cairosvg로 근사 PDF를 만든다. 이어서 `pdffonts`·`pdfinfo`로 PDF를 검사하고, 캡션이 렌더됐는지 센다.

## 도구 (`setup_tools.sh`, 저장소 밖에 만든다)

- **claw-hwp**(MIT, <https://github.com/DoHyun468/claw-hwp>)
  - 커밋 `eadf86fb713b5f9152fdf61520c6b60363a74222`의 scripts만 받는다. `cell-patch.js`의 git blob id(`82af912a…`)를 확인한 뒤 `claw-hwp-image.patch`를 적용한다.
  - 패치 내용(오케스트레이터 세션 작성):
    - 4,096바이트 이상 그림을 일반 FAT 스트림에 저장한다. 상류는 이를 거부한다.
    - `cell.before_para`를 지원한다.
    - 그림 레코드의 테두리 사각형·자르기 상자·원본 크기를 실제 크기에 맞춘다.
  - 저작권 고지는 `NOTICE-claw-hwp.txt`에 있다. 상류 코드 전체는 저장소에 넣지 않는다.
- **@rhwp/core 0.9.0**(npm, integrity 고정): 독립 렌더러다. claw-hwp에 묶인 0.7.x는 셀 안 그림을 그리지 않는다.
- **venv**: cairosvg 2.9.1, olefile 0.47.

## 아직 사람이 하는 것

순서는 저장소 밖 `~/capstone-work/deliverables-20261112/07-hancom-human-steps.md`(약 10분)에 있다.

- 한컴에서 열리는지 확인한다.
- 한컴 기준 쪽수와 원래 글꼴을 확인한다.
- 메모 2개를 지운다.
- PDF로 저장한다.

rhwp 레이아웃은 한컴과 다를 수 있다. 근사 PDF의 쪽수(2026-11-13: 표지 포함 6쪽)는 참고값이다.
