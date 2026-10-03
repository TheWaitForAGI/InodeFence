# 상태 정규화와 후속 corpus

## 현재 입력과 출력

`state_signature(before, after) -> StateSignature`

[초기 signature](signature.py)는 Oracle과 독립적으로 snapshot을 정규화한다. Schema version 1은 sorted path/type/mode/link-count, regular size/content digest, textual symlink target, sorted same-object groups와 external change field labels를 포함한다.

Raw st_dev/st_ino는 같은 run 안의 group 관계를 계산할 때만 사용한다. Signature에는 숫자 identity, timestamp/uid/gid 원값과 allocation-dependent directory size가 없다. Absolute symlink text의 literal run prefix는 $RUN으로 바꾸며, 그 외 path spelling은 유지한다. 이는 path resolution이나 symlink referent identity 추론이 아니다.

정렬된 tuple과 [canonical JSON](../model/README.md)으로 cross-run key를 만들 수 있다. 초기 representation은 검증된 최종 feedback policy가 아니며 Layer 5의 baseline/ablation 전에 schema를 고정해야 한다.

## 후속 책임

Interestingness, corpus persistence/scheduler와 mutation loop는 아직 미구현이다. [observer](../observer/README.md)의 facts와 [oracle](../oracle/README.md)의 verdict를 각각 활용하되 새 상태를 취약점으로 간주하지 않는다. 계약 정의는 Oracle/canonical contract 문서에 둔다.
