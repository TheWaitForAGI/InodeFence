# Vulnerability taxonomy, observation and mutation reachability

**Predictions derived from candidate evidence and inspected source; no hits measured.**
[Candidate matrix](candidate-matrix.md) provides adjacent advisory/patch sources;
[engine audit](engine-contract-audit.md) is the implementation basis. C0/C1/C2
retain their canonical definitions. Root causes below describe why extraction
can fail; effect labels describe what remains in the filesystem afterward.

## Semantic capability taxonomy

S IDs describe reusable archive semantics; R IDs below describe external root
causes; E IDs describe effects. They are not vulnerability IDs. This table is
source-derived analysis at the [audited revision](engine-contract-audit.md).
YES is ability within builder bounds, PARTIAL names a narrower ability, NO names
an exclusion, and N/A means an input-only property has no direct snapshot verdict.
Representation ≠ reachability ≠ observation ≠ confirmed vulnerability.

| ID / semantic class | Model represents? | Builder serializes? | Minimal seed contains? | Mutation v1 reaches? | Snapshot/oracle observes? | Current feedback use / blocking gap |
| --- | --- | --- | --- | --- | --- | --- |
| S01 Regular file | YES, arbitrary bytes/mode | YES, fixed uid/gid/mtime | YES | YES add_entry; no existing content/mode edit | Persistent bytes/digest/size/mode; protected effects C2 | State object digest/size/mode; novelty is not a bug |
| S02 Directory | YES, explicit ordered entry | YES, raw trailing spelling | YES one directory-bearing seed | PARTIAL inherit/duplicate/affix rename; no new-directory operator | Persistent lstat type/mode; namespace C0 if external | State paths/type/mode; arbitrary directory components absent |
| S03 Hardlink | YES unresolved text | YES within linkname limit | YES preceding internal source | YES add_hardlink, target affixes; external-name addressing blocked | lstat groups; persistent sentinel equality C1; link metadata C2 | Groups, regular nlink, fingerprints; symlink referents excluded |
| S04 Symlink | YES unresolved text | YES within linkname limit | YES preceding internal target | YES add_symlink/target affixes; arbitrary composition absent | Raw readlink/lstat, no referent walk; protected subsequent write C2 | Raw normalized text/type; outside link alone has no C1 verdict |
| S05 Duplicate path | YES duplicates preserved | YES ordered duplicates | NO | YES duplicate_entry; PARTIAL different-type same-name alignment | Only surviving type/effect, no overwrite event history | Final state/fingerprints; intermediate duplicates invisible |
| S06 Entry ordering | YES ordered tuple | YES exact order | YES internal links follow file | YES swap unequal values; duplicate insertion also varies order | Consequences only, not executed operation sequence | Useful only when final state/effect differs |
| S07 Parent-relative path | YES raw text | YES | NO | YES affixes/new prefixes | Persistent scoped effect C0/C2; spelling alone not violation | Observed path/effect keys; default sentinel components absent |
| S08 Dot-relative path | YES raw text | YES | NO | YES affixes/new prefixes | Canonical observed paths merge equivalent outcomes | No novelty merely for different TAR spelling |
| S09 Absolute-looking path | YES raw text | YES within USTAR fields | NO | YES slash prefixes, including repeated roots | Only actual controlled-run effects; no outside-sandbox observation | No absolute input novelty; random full run address is not generically available |
| S10 Link-target mutation | YES nonempty text for links | YES ≤100 UTF-8 bytes | PARTIAL benign internal targets | PARTIAL copy existing path on creation, then affixes; no component substitution | Link text and surviving relationship/effect | Text/groups/effects; M1 component composition proposed |
| S11 Cross-entry relationship | YES ordered related entries | YES; no dependency solving | YES simple internal link pairs | PARTIAL existing-path links/swaps; no dependency-aware proposal | Final identity groups, link text and effects | Generic groups/fingerprints; transient relationship absent |
| S12 Pre-existing filesystem objects | NO setup in ArchiveCase | N/A archive-independent | N/A | NO arbitrary tree/session setup; external sentinels already supplied by runtime | Existing protected regular sentinels YES; other setup NOT_IMPLEMENTED | Protected paths/effects already present; reused extraction trees out of v1 |
| S13 Replacement / type transition | YES distinct entries sharing path | YES | NO | PARTIAL type/path combinations through add/duplicate/rename; no conversion operator | Persistent replacement C0/C2; intermediate type history absent | Final objects/effect labels; no generic name replacement today |
| S14 External object identity / effect | PARTIAL describes operations, not runtime object identities | YES for four supported entry types | NO external relationship | NO selected default sentinel effect; required names outside output language | C1 surviving alias, C2 protected changes, C0 persistent external namespace | State relations/effects plus independent violation novelty; no transient/all-object claim |

Serializable semantic shapes remain subject to exact byte lengths and numeric
field limits; model and builder failures are infrastructure exceptions today.
The builder creates archive operations; the target decides their filesystem
meaning. The seed bank does not imply all seed structures coexist in one parent.

## Root-cause classes

| Class | Plain-language meaning / technical definition | What changes in the archive | Required filesystem state | Effect and InodeFence relevance |
| --- | --- | --- | --- | --- |
| R1 Lexical confinement failure | A text check accepts a path outside its intended root; incomplete stripping or missing link-field validation | Absolute/repeated-root member or link target, or parent components in selected members | Writable external destination; hardlink source must exist on same device | Outside namespace or sentinel alias/effect; C0/C1/C2 depending on operation. N01/N05/G02 |
| R2 Validation-base mismatch | The same relative text names different objects because checking and creation start in different directories | Hardlink destination depth and relative link target | External controlled file; O01 additionally requires process CWD outside extraction | Internal alias, C1 and C2 link metadata. Checking the archive spelling alone misses the relationship. N02/O01 |
| R3 Link-resolution composition | String cleanup ignores that earlier symlinks change how later components are resolved | Multiple dependent links; hardlink target or later regular member traverses the chain | Nested directories; external existing file for identity arm or writable directory for creation arm | Persistent alias or write. C1 captures N03; C2/C0 capture O02. Order matters because links must exist when consumed |
| R4 Stale directory-safety cache | Extractor still believes a directory is safe after it becomes a symlink | Directory/symlink collision then descendant file; N06 adds POSIX alternate spellings | Outside directory or protected file destination; cache filled earlier in same extraction | External write/creation, C2/C0. N04/N06 test state transition, not a static traversal string |
| R5 Filesystem-name equivalence mismatch | Extractor treats two spellings as different while filesystem treats them as one object | Unicode/case/short-name equivalents; directory/link replacement or concurrent reservations | Normalization/case-insensitive filesystem or Windows short-name semantics | Possible outside write; persistent effect may be seen, but equivalence/race cause cannot be inferred from snapshots. N07/N08 outside Linux v1 |
| R6 Archive-parser interpretation mismatch | Metadata changes which members a parser sees | PAX override and intervening GNU metadata headers | Two parser consumers; no special filesystem state required | Member disagreement is not itself C0/C1/C2. N09 outside USTAR and filesystem-contract scope |
| R7 Configured-root mismatch | Extractor's extra top-level directory is not also used to confine hardlink sources | Hardlink under top-level extraction option; optional subsequent write/link interaction | Existing source in working directory; pre-existing symlink for stronger effect | C1/C2 if source protected; C0 only if actual configured boundary is represented correctly. G01 needs boundary qualification |
| R8 Existing-state / input-sink assumption | Safety depends on prior tree contents or a non-TAR filename input | G03 reuses state across archives; O03 changes OCI title rather than TAR entries | Pre-existing internal symlink and external writable destination | C0/C2 can see effect given setup, but current empty-extract single-case campaign cannot express the scenario. Does not prove a default extractor defect |

E1 = persistent outside namespace change; E2 = internal/external identity sharing;
E3 = external bytes/metadata change; E4 = link referent or parser behavior without
persistent E1–E3 evidence. These are effect categories, not new oracle contracts.
Existing-object replacement and entry order are cross-cutting requirements of
R3/R4/R8, rather than separate independent vulnerability counts.

## Candidate-by-candidate observation map

Expected = follows from the specified persistent effect and controlled setup;
possible = depends on which object/operation survives; not relevant = no such
evidence for that arm. “Expected” is a hypothesis, not a guarantee of rediscovery.
For platform-excluded cases, entries describe the required platform, not current
Linux support. C2 includes metadata, even when bytes are unchanged.

| Candidate | C0 | C1 | C2 | Overall current-contract coverage / exact qualification |
| --- | --- | --- | --- | --- |
| N01 | Not relevant for internal hardlink alone; possible for additional external replacement | Expected if alias remains to protected file | Expected nlink/ctime; possible content write | PARTIALLY OBSERVABLE: hardlink arm observable; symlink text alone has no referent verdict |
| N02 | Not relevant for alias alone | Expected protected-file alias | Expected nlink/ctime; possible bytes | OBSERVABLE WITH CURRENT CONTRACTS for persistent alias; root-cause check/use trace absent |
| N03 | Not relevant for alias alone | Expected if final alias persists | Expected link metadata; possible bytes | OBSERVABLE WITH CURRENT CONTRACTS for alias; removed alias/transient chain effect not covered |
| N04 | Possible: external creation/replacement, not in-place overwrite | Not relevant for symlink-directed write | Expected if protected file changed | OBSERVABLE WITH CURRENT CONTRACTS for protected write or persistent external creation; cache cause requires review |
| N05 | Expected for external creation/replacement; possible for overwrite | Not relevant | Possible if destination protected | OBSERVABLE WITH CURRENT CONTRACTS for persistent effect; absolute destination must be in observed sandbox |
| N06 | Possible external creation/replacement | Not relevant | Expected when protected destination modified | OBSERVABLE WITH CURRENT CONTRACTS for POSIX persistent write; different spelling by itself is not violation |
| N07 | Possible | Not relevant for symlink arm | Possible protected write | PARTIALLY OBSERVABLE: effects only if platform equivalence supplied; no equivalence evidence/event history |
| N08 | Possible | Not relevant for symlink arm | Possible protected write | PARTIALLY OBSERVABLE: persistent effects, not race cause or transient event sequence |
| N09 | Not relevant to parser disagreement | Not relevant | Not relevant | NOT OBSERVABLE: missing parser-member comparison and required encoding, irrespective of incidental later effects |
| O01 | Not relevant for internal alias alone | Expected protected CWD-file alias | Expected nlink/ctime; possible bytes | OBSERVABLE WITH CURRENT CONTRACTS once CWD/source setup is available |
| O02 | Possible external creation/replacement | Not relevant for symlink-directed write | Expected if protected file overwritten | OBSERVABLE WITH CURRENT CONTRACTS for effect; lexical/final-component cause requires source review |
| O03 | Possible external creation/replacement | Not relevant | Possible protected write | PARTIALLY OBSERVABLE: effects supported, non-TAR title and existing-state setup absent |
| G01 | Possible only with correctly modeled designated root | Expected if surviving link names a protected source | Expected link metadata; possible bytes | PARTIALLY OBSERVABLE: fixed layout cannot automatically classify a narrower nested --one-top-level boundary |
| G02 | Possible persistent external creation/replacement | Not relevant | Possible protected overwrite | OBSERVABLE WITH CURRENT CONTRACTS for persistent effect; CLI selection/precondition must be fixed |
| G03 | Possible persistent external creation/replacement | Not relevant | Possible protected write | PARTIALLY OBSERVABLE: reused-tree setup absent; policy interpretation disputed, snapshots cannot settle it |

C4 is not inferred from R2 effects: a validated alias proves C1, not the exact
check/use sequence. No C3/C4 implementation or full tracing is requested for v1.
Writes outside the observed sandbox, dangling external links, confidential reads,
and effects undone before AFTER need evidence that current snapshots lack.

## Reachability means two different things

**Structure reachability** asks whether the seeds/operators' output language can
encode the semantic shape. **Benchmark reachability** additionally requires
reaching a protected controlled object under the actual runtime setup. Neither
measures how likely a finite search is to discover it. YES means a justified
finite construction exists in that language, not a bounded hit rate. PARTIAL
means some required semantics are representable but a named missing capability
remains. NO means a demonstrated language/setup exclusion; UNKNOWN means the
published condition is insufficiently specified.

Current seeds plus operator name vocabulary cannot spell `outside` or default
`sentinel.txt`: operators preserve existing characters and only append `x` or
path punctuation. In particular the needed `o`, `u`, `s`, `n` characters cannot
appear from the current stem/seed language. Thus no selected sentinel alias or
protected-byte rediscovery is reachable with the current default setup, even
if an arbitrary unprotected outside creation might be. This is a source-level
exclusion, not a failed fuzzing measurement.

## Gap matrix

✓ = required; – = not required for the selected arm; ? = condition unresolved.
“Existing FS” distinguishes an ordinary external sentinel from a required
pre-existing object inside extraction; only the latter needs a new setup hook.

| Candidates / class | Path | Hardlink | Symlink | Order | Existing FS | Structure / benchmark reachability now |
| --- | --- | --- | --- | --- | --- | --- |
| N01 / R1 link-field | ✓ | ✓ | – | – | External source | YES for simple link; NO for selected sentinel address |
| N02 / R2 | ✓ | ✓ | – | – | External source | PARTIAL nested path/target composition; NO for default sentinel |
| N03 / R3 | ✓ | ✓ | ✓ | ✓ | External source, nested parents | PARTIAL chain/component construction; NO for default sentinel |
| N04 / R4 | ✓ | – | ✓ | ✓ | External directory/file | PARTIAL directory/link collision names and link-to-directory target; NO for default protected destination |
| N05 / R1 member-root | ✓ | – | – | – | External writable directory | YES repeated-root spellings; NO for selected sentinel address |
| N06 / R4 alternate spelling | ✓ | – | ✓ | ✓ | External directory/file | NO: POSIX backslash spelling absent from output alphabet |
| N07/N08 / R5 | ✓ | – | ✓ | ✓ | Equivalent-name filesystem | NO: alphabet and supported filesystem prerequisites missing |
| N09 / R6 | ✓ | ? | ? | ✓ | None | NO: PAX/GNU metadata not in model/builder |
| O01 / R2 | ✓ | ✓ | – | – | External CWD source | YES relative link text; PARTIAL end-to-end: generic-name sentinel and isolated external CWD required |
| O02 / R3 write | ✓ | – | ✓ | ✓ | External file | PARTIAL chains, duplicate type/path alignment; NO for default sentinel |
| O03 / R8 API sink | ✓ | – | ✓ | – | Existing internal symlink | NO: title input and setup absent, not TAR-mutation benchmark |
| G01 / R7 | ✓ | ✓ | Possible | Possible | Source under wider CWD, optional internal symlink | UNKNOWN exact invocation/pin/root; PARTIAL types available |
| G02 / R1 selection | ✓ | – | – | ? | CLI-selected name and destination | UNKNOWN selection details; NO for default sentinel address |
| G03 / R8 reused tree | ✓ | – | ✓ | ✓ across runs | Existing internal symlink | NO: campaign creates fresh empty extract for each input |

## Smallest post-audit mutation work justified by these candidates

**M1: generic path-component replacement/recombination.** Allow an explicit
finite component dictionary and splice/replace operations for entry and link
text, including controlled sandbox-visible directory/file names. Include benign
archive components and sandbox topology for every target/variant equally;
exclude CVE-specific link sequences. N01 requires addressable external names (relative sanitation arm preferred);
N03 requires link target component composition; N04 requires renaming its
existing directory seed to collide with a link. Pin the complete dictionary,
sandbox-visible layout, grammar and probabilities in configuration.
Never substitute run paths after hashing/export without recording the logical
input and actual TAR mapping. Prefer relative names for selected structures: the merged container backend
preserves the identical random absolute run path, rather than a stable alias.
Absolute-address experiments need explicit input/run-context binding or a
qualified mount mapping, and are optional; do not request a competing backend.
Keep proposals within USTAR field limits; an over-limit proposal becomes a
deterministic counted no-op under the pinned future grammar, not a free retry.

M1 should be sufficient in principle with seeded directory entries and existing
reorder/duplicate/link operators. No new entry type, arbitrary mode mutation or
new-directory constructor is required by the four selected classes. Validate
this with constructive **logical, non-executing** reachability checks after the
audit; do not claim practical discoverability before a pilot.

**M2: optional generic dependency-aware link-chain proposal.** Consider only if
M1 still produces essentially no valid multi-link dependency states within a
predeclared pilot budget for N03 (or later O02). It may select existing paths and
compose multiple generic entries, without encoding an advisory recipe. Compare
all feedback variants using identical M2 policy. A multi-step macro changes the
search problem and must get its own policy revision. It is not required now.

**M3: optional literal-backslash component support** only if N06 is admitted to
a later set. Ordinary POSIX backslash semantics do not require Windows support.
Do not add Unicode, Windows aliases, PAX, races or persistent extraction trees
for excluded candidates merely to enlarge the feature list.

## Post-audit M1 address vocabulary requirements

Requirements only; no API or mutator implementation is introduced. Vocabulary
comes from the controlled setup and finite generic grammar, without CVE IDs,
upstream vulnerability paths, fix versions or target-specific entry sequences.

| Concept | Meaning / information later supplied by setup |
| --- | --- |
| Extraction root | Declared target-visible extraction directory and its relative name in the observed run; object identity belongs to observation, not mutation. |
| Controlled external root | Owned, observed external directory, same-device relation and relative components from the extraction root; no real host path or secret. |
| Protected sentinel basename | Public controlled relative name/component list for each regular sentinel, plus its declared protection role; exact spelling available to every comparison arm. |
| Archive namespace | Logical entry-name namespace and any declared upstream transport prefix; Node can use the logical root, ORAS's title-prefix transport must be explicit and separately hashed. |
| Relative component names | Finite ordinary names from seed/archive/setup plus declared generic names and syntax components; entry order and duplicate spellings remain significant. |

A future generic mutator needs a versioned finite vocabulary, applicable USTAR
byte bounds, current case names/link text, caller RNG and component-composition
rules. It does not need target family, CVE/version, protected inode, observed
violation or a recipe. Layout relation/protection names are public configuration;
oracle classification and success logic are not mutation hints. Freeze vocabulary,
order/weights/limits and digest in research config/provenance for all baseline arms.

Generic component replacement/splicing must be able to reuse names across
member/link fields, create differing-type same-name collisions and compose
relative paths from ordinary components, separators, dot and parent components.
Bound component depth/encoded byte lengths; define deterministic counted no-op
for inapplicable/out-of-bounds proposals. These are grammar capabilities, not a
prescribed attack order. Avoid binding a finite dictionary to one known target
path, one sentinel literal or one CVE. The same setup-derived words and grammar
must serve Node and ORAS; wrapper transport belongs to invocation, not a Node/
ORAS conditional in mutation.

Absolute per-run addresses, if later required, need separately frozen explicit
mapping and a generic grammar rule; they are not secretly interpolated into input.
Primary v1 does not require a stable mount alias for N01's relative arm. Do not
normalize raw spelling or link targets to make a candidate fit. Qualified logical
reachability and serializability tests will establish grammar ability after audit;
static requirements do not imply a measured search probability or oracle hit.
