# 실험 설정

이 폴더는 **재현 가능한 experiment configuration**을 둔다.

설정 하나만 보고 최소한 다음을 알 수 있는 형태를 목표로 한다.

- target과 version
- 시작 seed/corpus
- mutation 조건
- feedback 조건
- random seed
- execution budget
- timeout
- 필요한 environment identifier

숨은 수동 설정을 최소화한다.

같은 이름의 실험이라도 조건이 달라졌다면 결과를 덮어쓰지 말고 구분 가능한 config로 남긴다.
