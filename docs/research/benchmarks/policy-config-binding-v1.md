# Explicit policy evaluation binding v1

`PolicyEvaluationConfig` is an evaluation-owned declaration around the existing
public `SearchCampaignConfig`. It records all policy IDs, integer seed/budget,
ordered initial case IDs, exact frozen ExecutionProvenance and explicit stable
seed/environment/sentinel/protocol profile identifiers. Its `config_id` is the
SHA-256 of its canonical schema-v1 model encoding. This is a separate namespace
from legacy ExperimentConfig; no legacy ID, parser or execution path changes.

Callers can construct this declaration before executing their own campaigns.
`export_bound_policy_result(result, config, directory)` is passive and requires
the config, initial cases and entire source/runtime/target/artifact/isolation/
sentinel provenance to match the completed result. It does not invoke policy
dispatch, mutation or targets. Use the existing public core interface under the
caller's applicable execution authorization; this module is an evidence sink.

The no-overwrite bundle contains `evaluation-config.json`, a complete distinct
policy evidence bundle under `campaign/`, and `binding.json` published last.
Checksummed canonical schema-v1 `PolicyEvaluationBinding` links both config bytes
and the raw campaign manifest and records the config ID. Missing binding markers
leave incomplete evidence; they never become normal completed input by inference.
Linux atomic publication and trusted parents/single writer are required.

`verify_bound_policy_evidence(directory, expected_binding_sha256=...)` freshly
verifies every linked artifact, config identifier, policy/raw result and exact
declaration binding before returning any evidence. Corruption, unbound config
changes, symlinks, missing or extra files fail closed. Existing raw outputs are
never overwritten, including those from interrupted publication.

An externally trusted binding digest can anchor integrity. Checksums do not
authenticate operator claims or establish qualification. Profile names record
explicit declarations, not proof that a protocol/environment was followed.
Unknown/dirty source may be preserved as raw engineering evidence; comparison
validators must reject it rather than silently pool it. This format invents no
timing, ExperimentConfig compatibility or paper-readiness claim. Dataset analysis
and incremental integration are separate work; Core has no completed-step hook.
