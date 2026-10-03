# 상태 정규화와 후속 corpus

## 현재 입력과 출력

`state_signature(before, after) -> StateSignature`

[초기 signature](signature.py)는 Oracle과 독립적으로 snapshot을 정규화한다. **StateSnapshot = full raw observation/evidence**, **StateSignature = normalized security-state representation for future feedback/corpus**다. Observer는 sandbox 전체를 기록하며 archive digest/harness metadata를 raw evidence에서 제거하지 않는다.

Schema version 2는 공통 Region에서 EXTRACTION/EXTERNAL object만 선택한다. `.`과 `archive/**` HARNESS object/metadata는 제외하며 **ArchiveCase identity와 TAR artifact identity를 직접 포함하지 않는다.** EXTERNAL은 `outside/**`와 root-level `escape.txt` 등 모든 unreserved extraction 밖 경로를 포함한다. Sorted path/type/mode, regular nlink/size/content digest, textual symlink target, scoped same-object groups, external change field labels 및 protected_paths를 담는다. Identity group도 선택한 object scope로 projection하고 singleton을 제거하여 harness path가 dangling relation을 만들지 않는다. 삭제된 sentinel의 보호 설정과 내부↔sentinel relation은 유지한다.

Raw st_dev/st_ino는 같은 run 안의 group 관계를 계산할 때만 사용한다. Signature에는 숫자 identity, timestamp/uid/gid 원값과 nonregular size가 없다. `SignatureObject.st_nlink`는 regular만 정수, directory/symlink/other는 None이다. Directory link count의 filesystem 차이를 key에 넣지 않지만 raw nlink/C2 metadata 비교와 external nlink-change labels는 보존한다. 이는 모든 filesystem의 effect pattern이 같다는 보장은 아니다. Absolute symlink text의 literal run prefix는 $RUN으로 바꾸며, 그 외 path spelling은 유지한다. Extraction symlink의 harness target text도 유지하며 referent digest를 추가하지 않는다. 이는 path resolution이나 symlink referent identity 추론이 아니다.

정렬된 tuple과 [canonical JSON](../model/README.md)으로 cross-run key를 만들 수 있다. Envelope schema v1/case encoding과 signature 내부 v2는 별개다. 이전 signature와 key 호환성을 주장하지 않는다. [실제 E2E regression](../../../tests/test_pipeline.py)은 독립 regular entry의 순서를 바꿔 case ID/TAR SHA-256이 달라도 동일 semantic state의 signature/canonical JSON은 같음을 검증한다. 다른 inode allocation/PYTHONHASHSEED의 기존 테스트도 유지한다. 초기 representation은 검증된 최종 feedback policy가 아니며 Layer 5의 baseline/ablation 전에 schema를 고정해야 한다.

## 후속 책임

Interestingness, corpus persistence/scheduler와 mutation loop는 아직 미구현이다. [observer](../observer/README.md)의 facts와 [oracle](../oracle/README.md)의 verdict를 각각 활용하되 새 상태를 취약점으로 간주하지 않는다. 계약 정의는 Oracle/canonical contract 문서에 둔다.
