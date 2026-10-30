# Abstract (드래프트 v1)

InodeFence는 TAR archive extraction의 보안 경계위반 탐색에서, 고정된 CVE PoC나 공격 recipe를
하드코딩하지 않고 **filesystem-security-state**(추출 객체와 외부 객체 사이의 object identity, 보호된
외부 sentinel에 대한 external effect)를 feedback으로 사용하는 접근을 조사하는 연구 프로토타입이다.
핵심 연구 질문 H1은 "이 상태를 feedback으로 쓰면 extraction의 보안 경계위반을 더 잘 탐색할 수
있는가"이며, 참신성은 확정된 사실이 아니라 **검증 대상 가설**로 둔다.

이 드래프트가 **방어하는 주장은 좁다**:

1. 입력 생성 → 실제 node-tar 실행 → entry별 중간 filesystem 상태 관찰 → generic C0/C1/C2 oracle →
   feedback → 다음 mutation으로 이어지는 루프가 실제 extractor에서 반복 가능하게 동작한다
   (M1, 증거 수준 TESTED).
2. **하나의 generic identity oracle**(추출 객체가 외부 참조파일의 `(st_dev, st_ino)`를 공유 = C1;
   보호된 외부 sentinel의 전후 metadata 변화 = C2)이 릴리스 id나 정답 경로를 판정 조건에 넣지
   않고 서로 다른 두 root-cause(CVE-2026-23745, 그리고 그 수정이 도입한 회귀 CVE-2026-24842)를
   5개 고정 릴리스의 통제 차분으로 포착한다(M2, observed).
3. 영향 릴리스 node-tar 7.5.2에서 object-identity 관찰을 **끄면**(identity-blind 대조) 자율 경계위반
   발견이 0이고 **켜면** 특정 seed에서 결정론적으로 재현되는 자율 C1 트리거(21건)가 나타난다 —
   즉 발견의 **인과적 원인**이 가설이 지목한 바로 그 feedback임을 blind 대조로 보인다(M3).
4. 동일한 generic oracle(코드 불변)이 adapter 수준에서 3개 독립 extractor(python-tarfile · oras-go ·
   decompress)에 target-agnostic하게 적용된다(M4, **oracle/adapter 수준** 일반성).

**정직 경계를 명시한다.** (3)은 "상태-인지 feedback이 무작위보다 빠르다/많이 찾는다"는 **rate 우위가
아니라** "feedback(identity 관찰)이 발견을 가능케 한다 — 없으면 도달 불가"라는 **인과 명제**다. 자율
트리거는 이 예산(budget 1500)에서 65 seed 중 1개로 **seed-rare**이며, 이것은 **blind 발견이 아니다**
(기존 외부 객체에 하드링크하려면 그 이름이 필요하고 퍼저는 그것을 관찰로 얻는다; 어휘·oracle에
대상 경로·식별자·정답 seed·근접 보상을 하드코딩하지 않았고 EXTERNAL 필터는 region 기준
target-agnostic이다). rate 우위 판정(동일 budget powered matched A1 vs A3full)과 2번째 extractor의
powered 자력발견 판정은 **PENDING**(독립 반복 진행 중)이며, 이 드래프트는 그 수치를 추측해 적지
않는다. 관련 선행연구(Jana & Shmatikov, ZIPDiff, LinkZard, Wormholes)와의 중첩을 명시하고
"최초 / 기존연구에 없음" 류 주장은 하지 않는다.
