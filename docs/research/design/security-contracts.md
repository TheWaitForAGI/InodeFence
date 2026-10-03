# Security Contract

Security Contract는 안전한 archive extraction이 지켜야 할 일반화된 보안 규칙이다.

특정 CVE 식별자와 독립적으로 정의한다.

## 한눈에 보기

| ID | Contract | 역할 | 초기 우선순위 |
| --- | --- | --- | --- |
| C0 | Path Boundary Confinement | 기본 path 경계 sanity / baseline | 높음 |
| C1 | Object Identity Confinement | 내부↔외부 object identity 연결 탐지 | 높음 |
| C2 | External Effect Noninterference | 외부 sentinel 변경 탐지 | 높음 |
| C3 | Extraction Root Integrity | extraction root redirect/교체 탐지 | 중간 |
| C4 | Check/Use Coherence | validation과 실제 operation 의미 불일치 분석 | 후순위 |

C0는 중요한 보안 규칙이지만 **InodeFence의 신규 기여로 주장하지 않는다.**

---

## Contract C0 — Path Boundary Confinement

### 규칙

Archive extraction으로 생성되거나 직접 사용되는 path가 의도한 extraction boundary를 벗어나면 안 된다.

가장 단순한 예:

```text
../../outside.txt
```

### 왜 필요한가?

InodeFence의 핵심은 object identity/effect지만, 가장 기본적인 path traversal을 먼저 잡지 못하면 observer/oracle 구현 자체를 신뢰하기 어렵다.

또한 RQ2의 path-only feedback/baseline을 설명하는 기준점이 된다.

### 주의

문자열에 `../`가 있는지만 검사하는 것은 충분하지 않다.

Path normalization, symlink resolution, 실제 filesystem object 관계는 서로 다를 수 있다.

따라서 C0는 C1/C2를 대체하지 않는다.

### 초기 우선순위

높음. sanity/baseline contract로 구현한다.

---

## Contract C1 — Object Identity Confinement

### 규칙

Extraction 영역 내부에 생성된 object가 보호된 외부 sentinel과 의도하지 않게 동일한 filesystem identity를 공유하면 안 된다.

### 초기 관찰 방법

같은 filesystem에서 다음을 비교한다.

```text
(st_dev, st_ino)
```

내부 object와 보호된 외부 sentinel이 의도하지 않게 같은 object identity를 공유하면 violation 후보로 본다.

### 왜 중요한가?

서로 다른 path가 같은 underlying object를 가리킬 수 있다.

따라서 path-only observer는 보안 관련 관계를 놓칠 수 있다.

### 초기 우선순위

높음. Minimal implementation에 포함한다.

---

## Contract C2 — External Effect Noninterference

### 규칙

Untrusted archive 처리 때문에 보호된 외부 sentinel object가 의도하지 않게 변경되면 안 된다.

### 후보 관찰 정보

- existence
- content hash
- file size
- mode
- 선택 timestamp
- 이후 필요 시 ownership

### 예

Extraction 결과를 생성/수정했는데 보호된 외부 sentinel의 content가 바뀌었다면 external side effect가 발생한 것이다.

### 초기 우선순위

높음. Minimal implementation에 포함한다.

---

## Contract C3 — Extraction Root Integrity

### 규칙

Extraction root의 실제 object/redirect 의미가 공격자 entry에 의해 바뀌어 이후 extraction이 의도한 boundary 밖으로 향하면 안 된다.

### 메모

Destination manipulation 계열 패턴을 다루는 데 중요하지만 초기 C0/C1/C2 구현을 막지 않도록 후순위로 둔다.

### 초기 우선순위

중간.

---

## Contract C4 — Check/Use Coherence

### 규칙

Target이 어떤 path/object를 검증한 뒤 filesystem operation을 수행한다면, 검증한 대상과 실제 사용한 대상의 의미가 일관되어야 한다.

### 메모

Target-specific instrumentation이나 operation tracing이 필요할 수 있다.

Validation/use mismatch의 root-cause 분석에 유용하지만 첫 end-to-end fuzzer의 필수요건은 아니다.

### 초기 우선순위

후순위.

---

## Oracle 설계 원칙

Oracle은 다음 조건을 만족해야 한다.

- 일반화된 보안 속성을 표현할 것
- `if target_version == vulnerable_version` 같은 조건을 피할 것
- Known PoC byte sequence를 직접 매칭하지 않을 것
- finding 재현에 충분한 증거를 남길 것
- 필요할 경우 suspicious state와 confirmed violation을 구분할 것
- 각 violation이 어떤 Contract ID(C0~C4)에 해당하는지 기록 가능할 것

## Sentinel 정책

실제 host의 민감 파일을 target으로 사용하지 않는다.

각 run은 전용 runtime sandbox 안에 controlled sentinel을 생성한다.

예:

```text
run-UUID/
├── outside/
│   ├── sentinel-a
│   └── sentinel-b
└── extract/
```

Observer는 extraction 전후 sentinel state를 기록한다.
