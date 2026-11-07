# 소개 영상 렌더러 (제작 보류 중)

**코드 위치:** 렌더러 `build_video.py`와 재생 기준으로 고친 대본은 브랜치 `w5/deliverables-01`에 있고, 제작 재개 때까지 main에 넣지 않는다.

**알려진 버그:** 그 `build_video.py`는 각 장면 내레이션의 마지막 문장을 자막에서 빠뜨린다. 수정 패치는 저장소 밖 `~/capstone-work/video/build_video-caption-fix-uncommitted.patch`(SHA-256 `0b9be0dc…`)에 있고, 제작 재개 때 커밋한다.

보존본은 같은 폴더의 `draft1.mp4`(SHA-256 `ce4933a5…`, 4,815,150 B, 295 s)이고 패치를 적용한 코드로 만들었다. 이전 판 `00bea4d2…`는 자막 누락 버그판이며 보존하지 않았다.
