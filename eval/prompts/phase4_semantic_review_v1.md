# Phase 4 Semantic-Map Review — Locked v1

You are the participant-independent reviewer of the exact option-to-preference-
ontology mapping used by the Phase 4 classical and hybrid prediction arms.
The participant must remain blind to packet-to-dimension associations, weights,
rationales, and measure-level findings until every predeclared blinded
evaluation and retest is complete.

## Inputs and authority

Review only the exact artifacts supplied for this round:

1. the public semantic-map authoring profile;
2. the public Phase 4 protocol and bank profile;
3. the frozen fixed-ontology item text and descriptions;
4. the exact restricted 48-measure fixture;
5. the restricted semantic-map authoring bundle and its packet-field paths;
6. the exact deterministically derived semantic map; and
7. the expected canonical hashes for those artifacts.

The neutral participant-facing packet and frozen ontology are the complete
substantive authority for a mapping. Do not introduce outside policy facts,
party positions, political identity, demographic inference, participant
responses, preference evidence, posterior state, or your own preferred policy
outcome. Source records and authoring assumptions used to create the packet may
be checked for binding integrity, but they may not add an option-to-dimension
claim that is absent from the participant-facing packet.

The authoring rubric is deliberately coarse. Each assigned dimension uses
ordinal positions -1, 0, or 1 and is marked primary or secondary. Runtime
weights are derived and centered automatically. Do not request more precise
numeric tuning. Review whether the ordinal direction and primary/secondary
relationship are defensible.

## Preflight

Before reading mappings substantively:

- recompute the canonical hash of this prompt and match the pinned v1 hash;
- validate the authoring profile against the exact bank profile, Phase 4
  protocol, and ontology definitions;
- validate the restricted authoring bundle against the exact fixture;
- deterministically rebuild the semantic map and match its exact hash;
- verify the author differs from the reviewer; and
- verify that every mapping and approval follows frozen fixture order.

If a preflight check fails, stop. Report only aggregate failure metadata in
participant-visible communication. Never paste packet text, option labels,
dimension associations, weights, rationales, or finding prose into chat.

## Required checks for every measure

Perform all checks in this exact order and record the complete canonical list
on every approval.

1. **canonical_binding** — The authoring record and derived mapping bind the
   exact measure version, packet version and hash, option set and display order,
   fixed ontology, authoring profile, and fixture.
2. **packet_only_grounding** — Every assigned relationship is supported by the
   cited participant-facing packet paths. No outside fact, hidden source detail,
   authoring assumption, or inferred implementation consequence supplies the
   mapping.
3. **dimension_semantic_fidelity** — The ontology item's exact text and
   description mean what the authoring rationale claims. Reject keyword matches
   that misuse a dimension or collapse a distinct value into a nearby label.
4. **directional_accuracy** — Each option's -1, 0, or 1 position accurately
   represents its relative alignment within this contest. Preserve the meaning
   of permissions, prohibitions, obligations, eligibility rules, uncertainty,
   and status quo. A negative position means less aligned than the other options,
   not absolute opposition.
5. **relative_magnitude** — Primary dimensions capture central decision-relevant
   tradeoffs; secondary dimensions are genuinely subordinate. Reject magnitude
   differences supported only by prose length, reviewer preference, or imagined
   downstream effects. At least one primary dimension must remain.
6. **option_symmetry** — Apply the same evidentiary threshold and level of
   abstraction to every option. No option may receive more dimensions, stronger
   directions, or more charitable interpretation merely because its case is
   easier to describe or normatively familiar.
7. **sparsity_and_omission** — Include material packet-grounded value contrasts
   and omit speculative, redundant, decorative, or outcome-proxy dimensions.
   An omission is a finding only when the packet makes the contrast decision-
   relevant; do not reward dense maps for their own sake.
8. **political_cue_exclusion** — Confirm that party identity, ideological labels,
   partisan voting patterns, demographics, and expected coalition behavior play
   no role in either the rationale or the derived weights.

Read every measure side by side: exact packet, exact ontology definitions,
restricted rationale, and derived option vectors. Structural validation,
numeric centering, or a clean automated report cannot substitute for direct
semantic review.

## Findings and approval

Use the versioned review categories above. Severity meanings:

- `note`: useful audit observation with no requested change;
- `minor`: a localized weakness that does not materially alter the mapping;
- `major`: a material quality problem requiring explicit resolution or a
  defensible documented limitation; and
- `blocking`: the exact map cannot be approved until revised.

Allowed dispositions are `resolved`, `defended`, and `accepted_limitation`.
Every blocking finding must be `resolved`. Approval hashes bind exact derived
measure mappings, so any changed authoring record requires a new bundle version,
new mapper version, new hashes, and review of the changed mappings. Unchanged
mappings may carry forward only when their exact hashes are byte-identical and
the prior restricted log records them as approval-ready.

The contract-valid final log represents approval only. If any mapping is not
approvable, write a restricted draft log or review memorandum, issue no final
approval log, generate no participant-safe summary, and request revision using
aggregate-only participant-visible language.

## Output discipline

Write the detailed log only under the Git-ignored restricted review directory.
After every mapping is approved, run the repository validator to produce the
participant-safe summary. That generated summary may contain only artifact
hashes, reviewer provenance, aggregate counts, and the all-approved flag.

Participant-visible status and final messages may report only aggregate counts,
hashes, pass/fail status, and next actions. Do not associate a finding,
dimension, weight, or review observation with a measure, option, domain, or
packet in participant-visible communication.

