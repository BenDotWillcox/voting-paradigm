# Phase 3 Evaluation-Bank Authoring

Phase 3 turns the settled evaluation design into a reviewed, immutable input
bank. The machine-checkable starting point is
`fixtures/preference_eval_bank_profile_v1.json`; validate it with:

```bash
python -m eval.validate_bank_profile \
  eval/fixtures/preference_eval_bank_profile_v1.json
```

The profile is an authoring contract, not an evaluation fixture and not a
research result. It freezes the common setting, allocation matrix, source and
neutrality requirements, order policy, and retest target before exact measure
language is drafted.

Profile validation proves that these targets are internally consistent. Final-
bank validation enforces the canonical fixture shape, linked retest selection,
slot bindings, and review provenance. Realized six-wave execution and the
7-14 day retest interval remain run-level checks that must land before the
held-out freeze.

Phase 3B authors the exact bank through reviewable six-measure domain batches.
`eval/bank_authoring.py` defines the source-evidence and batch contracts, and
`python -m eval.build_final_bank` accepts only one conforming batch from every
domain before writing the canonical 48-measure fixture. The command prints an
aggregate manifest rather than exact packet content:

```bash
python -m eval.build_final_bank \
  eval/fixtures/preference_eval_bank_profile_v1.json \
  path/to/batch-1.json path/to/batch-2.json ... path/to/batch-8.json \
  --fixture-id preference_eval_final_v1 \
  --created-at 2026-08-01T12:00:00-05:00 \
  --output eval/fixtures/preference_eval_final_v1.json
```

## Frozen Jurisdiction

The evaluation uses the fictional State of Meridian and City of Harborview as
of January 1, 2026. It is deliberately ordinary: a medium-sized U.S. state,
one large municipality, mixed urban/suburban/rural settlement, common state
and local institutions, and plausible fiscal and service baselines.

The numbers are synthetic. They are calibrated to the scale and categories in
official national sources including Census population and government-finance
data, HUD rent data, FHWA transportation statistics, EIA electricity
profiles, NCES education statistics, CMS health-coverage data, BJS justice
data, and EAC election-administration data. The source records say exactly how
each source was used; none of the fictional values is attributed to a real
state or city.

The profile contains only facts likely to change a civic choice. Packet facts
override the general profile when they are more specific. Every measure is
counterfactual and independent: previous proposals never change the legal,
fiscal, or service baseline, although explicit preference evidence may
accumulate.

## Bank Matrix

Every domain supplies six measures:

- four real-world-anchored and two constructed;
- two intended-familiar, two intended-adjacent, and two intended-novel; and
- the ballot formats assigned by its six frozen authoring slots.

Across the bank this produces:

| Dimension | Frozen count |
|---|---:|
| Real-world-anchored | 32 |
| Constructed | 16 |
| Familiar | 16 |
| Adjacent | 16 |
| Novel | 16 |
| Binary single choice | 38 |
| Ranked rich response | 3 |
| Approval rich response | 3 |
| Score rich response | 3 |
| Quadratic allocation | 1 |

The constructed tier pair rotates by domain. Constructed does not mean novel:
the resulting source/tier cross-tab is 11/11/10
familiar/adjacent/novel among real-world items and 5/5/6 among constructed
items. That makes source kind and intended novelty separately testable instead
of building the intended result into the labels.

An intended tier is an authoring label:

- **Familiar:** a widely encountered civic tradeoff with recognizable policy
  mechanisms.
- **Adjacent:** familiar values applied through a less common institution,
  implementation detail, or combination.
- **Novel:** a policy mechanism or interaction that should require
  extrapolation beyond ordinary issue bundles.

It is not a claim about what a particular participant already knows. At
prediction time, participant-specific evidence coverage remains the stronger
measure of realized novelty.

## Packet And Source Rules

Participant and model receive the same frozen packet. A packet must state the
status quo, exact change, affected groups, fiscal or operational effects, the
strongest good-faith argument for every option, material uncertainty, needed
definitions, and source-specific adaptation notes.

Every packet also receives a contextual-sufficiency audit. The author and
reviewer identify material circumstances that could reasonably change the
choice, verify that known values are stated, and preserve genuinely unresolved
facts as explicit unknowns. Do not add fictional personal or jurisdictional
detail merely to eliminate uncertainty, and do not let a model invent an
unstated participant fact or policy effect.

For a real-world-anchored measure:

- include at least two URL-backed records;
- classify at least one as a primary official source in the review ledger; and
- use the real measure as an anchor, then adapt its jurisdiction-specific
  facts consistently to Meridian or Harborview.

For a constructed measure:

- include at least one URL-backed context source;
- state which tradeoff is controlled and which quantities are held constant;
  and
- do not invent an empirical effect estimate merely to make the options look
  symmetric.

Every packet source requires a publisher, URL, access date, and adaptation
notes. The fixture validator can enforce those fields and the numeric source
minimums. It cannot safely infer that a publisher string represents a primary
official source; that classification belongs in the signed review ledger.

Every `SourceRecord` is paired with a `SourceCaptureRecord` that records its
primary-official, official-context, or independent-context role and binds the
record hash to the retrieved document bytes or a normalized claim-relevant
text extraction. A `ContentTraceRecord` stores one exact participant-facing
string, its JSON Pointer within the measure, the supporting packet source IDs
or frozen jurisdiction facts, and its adaptation notes. Validation fails if a
real-world adaptation lacks a primary official capture, a source is
decorative, a source record changes, a jurisdiction fact is unknown, or the
adapted packet text drifts. Full third-party documents belong only in the
ignored authoring cache; the repository stores their hashes and locators, not
wholesale copyrighted copies.

Packets exclude party labels, politicians, sponsors or campaign organizations,
endorsements, polling, and campaign slogans. Political identity, partisan
voting history, and demographic proxies remain unavailable to every live
model. Directly relevant circumstances volunteered by a participant are
evidence, not demographic inference.

## Draft And Review Workflow

Author the bank in domain batches. A batch is not frozen merely because it
passes schema validation.

1. **Source capture:** identify the primary official material and independent
   context; record access dates, source-record hashes, retrieved-content
   hashes and scopes, locators, and exact content traces.
2. **Packet draft:** write the packet from the frozen slot brief and common
   jurisdiction, without party or campaign cues.
3. **Structural validation:** check option IDs and order, packet completeness,
   source fields, response fields, format counts, and matrix allocation.
4. **Factual review:** trace every concrete quantity and legal claim to either
   the common fictional baseline, the adapted source calculation, or an
   explicitly labeled uncertainty.
5. **Contextual-sufficiency review:** identify material circumstances that
   could change the choice; verify that known values are present and unresolved
   values are explicitly unknown rather than silently inferred.
6. **Adversarial neutrality review:** look for asymmetric word count,
   specificity, valence, cost/benefit treatment, uncertainty, and omitted
   implementation risk. Record each finding and disposition.
7. **Participant-independent approval:** approve the exact packet version after
   the prior reviews. Record whether the reviewer is human or AI and, for an AI
   reviewer, the provider, model/version, review-prompt hash, findings, and
   dispositions. Approval is an auditable gate, not an inference from a passing
   test.

Source selection should not force superficial textual balance. A material
benefit or cost belongs in the packet even when the source evidence is
asymmetric. Neutrality means the adaptation does not silently advocate; it
does not mean pretending the evidence is evenly divided.

## Packet-Blind Case-Study Exposure

Ben has seen the 48 topic-level authoring briefs in the Phase 3A profile as of
July 30, 2026. He remains blind to the exact frozen packet language, option
wording, quantitative values, arguments, and uncertainties until each measure
is presented. Codex may author the bank and Claude may perform the
participant-blinded adversarial content review. Before Ben answers, he may
inspect the schema, allocation counts, nonrevealing review summary,
dispositions by category and severity, and final content hashes, but not the
exact packet contents.

The Claude review uses the immutable
`eval/prompts/phase3_packet_review_v1.md` prompt. Its canonical SHA-256 is
`b2e0cc374e0de755fb45ed8e6997cbdeeefc32f75827fcedf5e6abac435f7f32`.
The restricted `DomainBatchReviewLog` may contain exact packet excerpts and
measure-level findings. Only the output of
`build_nonrevealing_review_summary` is participant-safe: it contains hashes,
reviewer provenance, approval status, and aggregate category/severity/
disposition counts, with no finding or packet prose.
After validation, `bank_review_ledger_entries_for_batch` converts source roles,
completed checks, exact measure hashes, and review provenance into the six
canonical `BankReviewLedgerEntry` records without manual re-entry.

Validate an individual batch before review, then validate the restricted
review log and write its safe summary with:

```bash
python -m eval.validate_domain_batch \
  eval/fixtures/preference_eval_bank_profile_v1.json \
  path/to/domain-batch.json

python -m eval.validate_batch_review \
  eval/fixtures/preference_eval_bank_profile_v1.json \
  path/to/domain-batch.json \
  path/to/restricted-review-log.json \
  --summary-output path/to/nonrevealing-summary.json
```

The review is described as **participant-blinded, AI-assisted independent
review**, not independent human review. The ledger records the Claude
model/version and locked review-prompt hash. A human content review is required
before an external participant pilot or a broader claim of human validity.
The case study is described as cold to exact packet content, not as an
unqualified cold first exposure. Analysis of the intended-novel slice must
carry the topic-exposure caveat because prior knowledge of the planned
mechanisms may reduce realized novelty.

## Multi-Option And Retest Rules

Each of the nine ordinary multi-option contests collects the same rich ground
truth in this order: top choice, tie-aware partial ranking, approval set, and
0–10 score for every option. Its declared ballot type controls the primary
presentation, not which ground-truth fields are retained. The quadratic
contest uses a 100-credit budget and records only quadratic allocations.

The retest target is twelve measures after 7–14 days:

- at least one measure from every domain;
- eight real-world and four constructed;
- four familiar, four adjacent, and four novel; and
- eight binary plus one ranked, one approval, one score, and the quadratic
  contest.

A retest may paraphrase neutral wording and reorder options. It must preserve
the facts, fiscal estimates, option set, and material consequences. Prior
answers and predictions remain hidden until the retest response is frozen.
Analysis reports participant self-consistency, including stable-answer and
changed-answer slices, as a secondary benchmark. It does not mechanically
normalize the primary log-loss or delegated-risk results from twelve retests.

Retest variants live in a separate linked registry rather than as duplicate
fixture measures. Each variant identifies one canonical `measure_id@version`,
retains its packet lineage with a higher packet version, preserves canonical
option IDs and source IDs. The presentation plan owns seeded option ordering
for both initial and retest presentations. Run validation resolves the
alternate packet only for a retest presentation. This keeps the canonical bank
at exactly 48 measures.

## Remaining Phase 3 Deliverables

The bank profile is Phase 3A. Phase 3B infrastructure now supplies exact source
capture, domain batches, deterministic assembly, a locked Claude review prompt,
restricted disposition logs, and nonrevealing aggregate summaries. The
remaining content and finalization work is:

1. source and draft the 32 real-world and 16 constructed packets in domain
   batches;
2. review each exact batch and populate the final ledger binding every measure
   to its authoring slot,
   primary-source classification, factual review, contextual-sufficiency
   review, neutrality review, reviewer provenance, findings, dispositions, and
   participant-independent approval;
3. select and write the twelve retest variants;
4. derive the seeded six-wave order and per-presentation option order;
5. validate the complete non-development fixture against the profile; and
6. add presentation-plan/run validation for realized wave membership,
   presentation seeds, and retest timing; and
7. freeze the fixture, review ledger, retest variants, and manifests by content
   hash.

The packet-blind exposure policy above is now frozen for Ben's case study. If
exact packet content is exposed early despite that policy, record the protocol
deviation and do not describe the affected result as cold to exact packet
content.
