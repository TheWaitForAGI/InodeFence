# 정오표: `input-structure-class-v1-freeze-1`

대상: [`input-structure-class-v1.md`](input-structure-class-v1.md)(`input-structure-class-v1-freeze-1`, sha256 `15a83db6b9bc0e8574274c251dd8c26f3fd6ca42ea58ecb3a4c185d280cd34fa`).
그 파일의 바이트는 바꾸지 않는다(서명된 Drive 초안 2의 정의 부분과 글자 그대로 같아야 하기 때문).

1. **부록의 기준 줄 수치를 구현 기준으로 정정한다.**
   - 기준 줄: P16, R-chain m4, 등록 mutator, seed 31–35, W3 공유 생성기.
   - 보정 당시 보고: 캠페인당 서로 다른 분류 수 중앙값 **42**, 합친 탈출 분류 **66**, 최빈 비율 최대 **0.47**.
   - 구현(`src/inodefence/structure_class.py`)으로 다시 계산한 값: 중앙값 **43**(캠페인별 42, 43, 49, 39, 43), 합친 탈출 분류 **68**, 최빈 비율 최대 **0.47**.
   - 문서 안의 "42"(사유 문구의 "캠페인당 42개", "같은 분류기에서 20 → 42" 등)는 구현 기준으로 43으로 읽는다. 다른 줄(민감도 행)은 보정 스크립트 값 그대로이며, 같은 원인으로 1 안팎 차이가 날 수 있다.
2. **원인.**
   - 보정 스크립트는 절대 경로·대상(맨 앞 `/`)의 reach를 맨 앞 `/` 뒤의 `..` 조각을 따라 걸어 계산했다.
   - 이는 서명 문서의 글자 "reach = 그 문자열의 `reach(0, N(·))`(absolute면 0)"(정의 §4 A2 행)과 어긋난다.
   - 구현은 글자를 따른다(절대 문자열의 reach = 0).
   - W3 생성기 입력 9,980개 중 96개가 달랐고, 모두 `/..`로 시작하는 절대 경로 또는 절대 대상이다.
   - 절대 경로·대상은 reach가 0이어도 절대 형태만으로 탈출 관련 집합 E에 들어간다(정의 §3 규칙 1·2의 `abs(·)`). 분류가 `none`으로 떨어지지 않는다. `tests/test_structure_class.py`의 `test_absolute_forms_are_escape_relevant_with_reach_zero`가 이를 고정한다.
3. **영향.**
   - 두 하한(합친 탈출 분류 ≥ 5, 최빈 비율 ≤ 0.8)은 여전히 지켜진다(68, 0.47).
   - 상한 판정(20 초과 → 사유를 적고 동결)과 사다리 L4 선택은 바뀌지 않는다.
   - 계열 구분 확인(정의 §11.3과 서명 뒤 확인)은 절대 형태의 `/..` 입력을 쓰지 않았으므로 결과가 같다.
- 재계산 자료는 저장소 밖 보정 자료(Drive 02-엔진 `20261118-HOST4-isc-보정/`의 `isc_impl_reference_row.py`, `impl-reference-row.log`, `isc_impl_vs_calibration.py`, `impl-vs-calibration.log`, SHA256SUMS)에 있다.

정의는 바뀌지 않는다. 다음 id에서 본문 부록에 반영한다. (IF-W4-METHOD 판정 2026-11-18)
