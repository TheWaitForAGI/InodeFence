# Abstract (드래프트 v1)

InodeFence는 TAR archive extraction의 보안 경계위반 탐색에서, CVE 식별자·PoC·고정 공격 패턴·대상 경로·sentinel 이름을
oracle과 feedback에 넣지 않고 **filesystem-security-state**(추출 객체와 외부 객체 사이의 object identity, 보호된
외부 sentinel에 대한 external effect)를 feedback으로 사용하는 접근을 조사하는 연구 프로토타입이다.
핵심 연구 질문은 "피해 경로 이름을 아는 동일 어휘·동일 예산 아래서, 이 상태를 retention·스케줄링 피드백으로 쓰는 탐색이 무작위 탐색과
구조 커버리지 탐색보다 첫 경계위반까지의 실행 수를 줄이고 고유 위반 입력을 더 많이 찾는가"이고(research-questions v2; blind 발견 비주장), 참신성은 확정된 사실이 아니라 **검증 대상 가설**로 둔다.

이 드래프트가 **방어하는 주장은 좁다**:

1. 입력 생성 → 실제 node-tar 실행 → entry별 중간 filesystem 상태 관찰 → generic C0/C1/C2 oracle →
   feedback → 다음 mutation으로 이어지는 루프가 실제 extractor에서 반복 가능하게 동작한다
   (M1, 증거 수준 TESTED).
2. **하나의 generic identity oracle**(추출 객체가 외부 참조파일의 `(st_dev, st_ino)`를 공유 = C1;
   보호된 외부 sentinel의 전후 metadata 변화 = C2)이 릴리스 id나 정답 경로를 판정 조건에 넣지
   않고 서로 다른 두 root-cause(CVE-2026-23745와 CVE-2026-24842; CVE 대응과 회귀 원인은 추론)를
   5개 고정 릴리스의 통제 차분으로 포착한다(M2, observed).
3. 동일한 generic oracle(코드 불변)이 adapter 수준에서 3개 독립 extractor(python-tarfile · oras-go ·
   decompress)에 target-agnostic하게 적용된다(M4, **oracle/adapter 수준** 일반성).

관련 선행연구(Jana & Shmatikov, ZIPDiff, LinkZard, Wormholes)와의 중첩을 명시하고
"최초 / 기존연구에 없음" 류 주장은 하지 않는다.
