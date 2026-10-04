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

현재 CampaignConfig는 seed/budget이고 ExecutionProvenance는 실행 전 source/environment,
target/version/timeout과 sorted sentinel name/content SHA-256/mode다. Campaign이 자동 freeze하거나
caller가 frozen 값을 제공하며 target/sentinel 불일치는 실행 전에 거부한다. 결과에서 설정을
재구성하지 않는다. ExperimentConfig v1은 strict JSON parser와 deterministic config_id를 제공한다.

같은 이름의 실험이라도 조건이 달라졌다면 결과를 덮어쓰지 말고 구분 가능한 config로 남긴다.


## ExperimentConfig v1

모든 필수 field를 명시한다: target ID/exact version/timeout/execution_safety, seed_profile와 ordered
initial_case_ids, campaign seed/budget, mutation_policy, feedback_policy, sentinel name/content_base64/
mode, environment_profile. Missing/unknown/duplicate fields, bad types, nonfinite numbers와 unsupported
profile/policy는 거부한다. 현재 profile은 minimal-generic-v1, mutation은 uniform-generic-v1,
feedback은 state-v2-or-violation-v1-uniform-parent-v1이다. Seed order는 archive/campaign 의미를 보존한다.

config_id는 schema v1의 sorted-key compact ASCII JSON에 대한 SHA-256이다. Sentinel order는 name
기준으로 정규화하고 timeout의 equivalent int/float는 float로 encode한다. JSON field order/whitespace는
ID에 영향을 주지 않는다. Source commit, actual platform/kernel, runtime inode/time/result는 넣지
않는다. Environment profile은 expected setup의 stable caller label이며 OS attestation이 아니다.
같은 config ID가 서로 다른 execution environment/source revision을 같다고 주장하지 않는다.

run_configured_campaign은 명시적인 caller seeds/target을 config와 비교한 후 기존 run_campaign에
동일 CampaignConfig/sentinel/config ID를 전달한다. Target/policy/seed를 조용히 바꾸지 않는다.
Manifest의 stored experiment_config_id는 None이면 unconfigured API 실행이고, 값을 제공한
low-level caller는 config binding 정확성에 책임이 있다. Canonical CLI는 실제 binding을 검증한다.

[reference-smoke-v1.json](reference-smoke-v1.json)은 Python 3.12.3/timeout 5/seed 11/budget 8의
engineering config 예다. 다른 Python patch version이면 명시적으로 config를 갱신해야 한다.
Supported Linux에서 실행:

```bash
python -m scripts.run_configured_reference experiments/configs/reference-smoke-v1.json --output experiments/raw/configured-reference
```

CLI는 safe Python reference만 실행하고 experiment.json/manifest.json/steps.jsonl을 보존한다.
Uncontained Node-tar campaign은 계속 거부되고 contained configured execution에는 v2 policy가 필요하다. Config와 raw evidence는
비교 실험 완료, research effectiveness 또는 validated isolation을 의미하지 않는다.


## Container-bound config v2

Schema v1 and its canonical IDs remain unchanged for configurations without isolation.
Schema v2 requires the complete `isolation` object (`IsolationPolicy` schema v1), including
immutable image ID, implementation/view/environment policies, network/rootfs/namespaces,
nonzero uid/gid, cap-drop ALL/NNP, all resource limits and shared-memory/capture limits.
Unknown/missing fields and unsupported weaker policies fail. v1 cannot smuggle an
isolation object; v2 cannot omit it. Resource/image/policy changes affect config identity.

The configured runner compares the actual composed target's policy with that immutable
config before campaign setup. The campaign separately validates backend availability,
freezes actual runtime/image/artifact facts and rejects supplied provenance mismatch or
policy drift. No mutable tag, container ID/PID/temp path/timestamp enters config identity.
Uncontained Node execution remains impossible; only the approved benign engineering smoke
is authorized in this pre-audit contract. A schema v1 third-party config does not supply
containment and cannot bind to an isolated target without a v2 policy.
