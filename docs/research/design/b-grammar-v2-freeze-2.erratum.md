# 정오표: `b-grammar-v2-freeze-2`

대상: [`mutation-vocabulary-inventory-v1.md`](mutation-vocabulary-inventory-v1.md)(`b-grammar-v2-freeze-2`, 커밋 `074284d`).
그 파일의 바이트는 바꾸지 않는다(W3가 이 SHA를 공식 d* 실행에 고정함).

1. 22행(머리말 1항)의 "구현을 freeze-1과 대조한다"는 "구현을 freeze-2와 대조한다"로 읽는다.
   검토 메시지는 이 위치를 15행으로 적었으나 실제 위치는 22행이다. 20행의 "v2 정의 … 는 freeze-1과 같다"는 맞는 문장이다.
2. 변경 메모 1항의 100바이트 검사 위치는 네 곳이다: `src/inodefence/mutator/m1.py`
   - 32행(`_raw_path`의 기존 경로 재사용 후보)
   - 72행(`add_hardlink`의 대상 선택, M1 표에만 있음)
   - 98행(탈출 하드링크 대상)
   - 128행(`mutate_link_target`의 새 대상)

정의는 바뀌지 않는다. 다음 id에서 본문에 반영한다. (IF-W4-METHOD 판정 2026-11-18)

위 두 항목은 `b-grammar-v2-freeze-3`에서 본문에 반영됐다.
