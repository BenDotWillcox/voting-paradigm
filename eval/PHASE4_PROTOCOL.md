# Phase 4: Preference-System Comparison Protocol

Phase 4 asks whether an LLM can improve preference elicitation and prediction
without turning the LLM itself into an unauditable store of the participant's
preferences.

The hill is:

> Can a tool-using LLM conduct a natural, adaptive civic-values conversation
> that builds an explicit, auditable preference model capable of accurately
> and confidently predicting choices on previously unseen civic decisions
> with less user effort than conventional questionnaires?

Phase 4A freezes the architecture and comparison logic before a provider,
model, prompt, or live LLM call is selected. The machine-readable contract is
`eval/fixtures/preference_eval_phase4_protocol_v1.json`; its schema and
validator are in `eval/phase4_protocol.py`.

## Component Boundaries

The intended system is a pipeline with separate responsibilities:

1. **Interviewer:** chooses what to ask and renders a natural interaction. It
   may inspect uncertainty, candidate-question scores, evidence coverage, and
   conflicts through typed tools.
2. **Evidence extractor:** proposes normalized evidence from conversation. An
   inferred proposal has zero model weight until the participant confirms it.
3. **Preference posterior:** owns durable preference state. It is the only
   component allowed to update that state, and it consumes typed evidence
   rather than raw LLM output.
4. **Ballot semantic mapper:** maps an unseen packet's options into the
   preference representation. It does not store the participant's values.
5. **Prediction readout:** emits a probability for every option, a top option,
   and confidence.
6. **Action policy:** applies the participant-authorized selection rule. In
   this experiment it is held constant rather than optimized with the models.

The direct LLM arm is a required experimental control: it tests whether an
explicit posterior adds value beyond prompting an LLM with eligible evidence
and the target packet. It is not the intended durable-state architecture.
An optional party-conditioned prior remains an evaluation-only benchmark where
external evidence supports one. It can use party metadata collected only after
the final retest and never enters live evidence or model selection.

## What Is Compared

Phase 4 separates four layers that answer different questions.

### Elicitation policy

- fixed sequence;
- random vetted questions;
- max-variance questions; and
- a tool-using LLM interviewer.

These policies create different evidence. They can be compared causally with
seeded synthetic personas or, later, randomized human assignment. Ben's one
realized interview path is descriptive and cannot reveal what he would have
answered on the unasked counterfactual paths.

### Preference representation

- an uninformative prior;
- Gaussian linear fixed-ontology posterior;
- Bradley-Terry fixed-ontology posterior;
- hybrid fixed-ontology explicit posterior; and
- hybrid expanding-ontology explicit posterior.

Representation, evidence-condition, readout, and evidence-weighting variants
can be replayed at identical evidence cutoffs on the same realized history.
The six named model arms are the exact frozen reporting anchors. Additional
component variants are reported as ablation replays rather than added as new
arms. The required ablations independently compare acquisition, structured
versus confirmed LLM extraction, evidence condition, fixed versus expanding
ontology, authored versus direct-LLM versus hybrid readout, and reliability-
weighted versus uniform evidence.

### Evidence condition and ballot readout

The LLM control and hybrid arms expose structured-only, conversation-only, and
combined evidence. The frozen readouts are an uninformative prior, authored
semantic mapping, direct LLM probabilities, and LLM-plus-explicit-posterior
probabilities. All prediction arms receive the same versioned neutral target
packet at a given snapshot.

### Action policy

Every model must emit a complete probability distribution. A single-choice
ballot selects the top-probability option; ranked, approval, score, and
quadratic measures additionally require a complete format-specific prediction
that validates against the measure contract. Confidence is the top-option
probability and is shown when the prediction is revealed. The model does not
abstain or defer; the participant may override it or deliberately abstain.
Candidate confidence thresholds remain evaluation diagnostics. A future
product may let the user authorize automatic action only above a chosen
threshold, but that is a separate policy and not a way for the evaluated model
to avoid difficult predictions.

## Initial LLM Interviewer Boundary

The first LLM interviewer is provider-neutral and constrained. It may:

- choose a versioned question from the vetted bank;
- clarify existing evidence while retaining the linked evidence identifiers;
- pause and resume an ongoing conversation; and
- use typed posterior-uncertainty, candidate-score, coverage, and conflict
  tools.

It may render vetted content naturally, but it may not add substantive claims
or generate a new substantive civic question in v1. Generated questions and
new ontology dimensions are later ablations, not assumptions smuggled into the
first comparison.

There is no single primary session length. Question efficiency is a learning
curve over confirmed-evidence prefixes. Accuracy and calibration remain
primary; fewer questions cannot compensate for worse preference alignment.

## Held-Out Isolation

In primary delegation-prediction mode, the interviewer and evidence extractor
cannot inspect a target packet while eliciting preferences. The prediction
readout sees the packet only when the pre-answer prediction is frozen. It may
not ask a target-specific follow-up after that exposure. Otherwise the task
would become policy consultation rather than prediction from an already-built
preference model.

A future consultation or showcase mode may allow target-aware questions, but
its results must be reported separately. Political identity, partisan voting
history, and demographic proxies remain excluded throughout.

## Phase Sequence

- **4A — architecture and experiment contract:** freeze the boundaries,
  comparison matrix, target isolation, and action rule. No provider calls.
- **4B — tool-using interviewer (implemented):** provider-neutral tool request
  and result contracts, deterministic fixed-sequence acquisition, constrained
  structured actions, complete input/tool auditing, content-addressed
  private-safe caching, and deterministic test doubles. This phase is
  implemented without selecting or calling a live provider adapter.
- **4C — confirmed conversational evidence and ontology lifecycle
  (implemented):**
  fixed-ontology proposal, per-claim confirmation/edit/rejection,
  append-only correction, provenance, durable IDs, and same-cutoff evidence
  views are implemented. The expanding-ontology slice adds zero-weight
  proposals, condition-specific replay without conversational leakage into
  structured-only, exact and reviewed duplicate defenses, explicit
  participant admit/map/reject decisions, correction-stable support
  shrinkage, and participant-confirmed support, merge, and prune events. Seed
  dimensions cannot be merged or pruned. Policy parameters remain versioned
  inputs until the final experiment freeze; no live provider is selected.
- **4D — prediction readouts (implementation complete):** separate
  `prediction_snapshot.v2` and `evaluation_run.v2` contracts now bind exact
  packets, eligible evidence and conversation prefixes, posterior/ontology
  state, component artifacts, and pre-answer chronology while preserving the
  v1 records and Phase 3C bundle hashes. Normalized option probabilities are
  separate from complete ranking, approval, score, and quadratic actions.
  Same-checkpoint comparisons enforce common cutoffs and evidence views. A
  fixture/packet/ontology-bound authored stance map now drives both Gaussian
  and Bradley-Terry posteriors through one uncertainty-aware probability
  readout and common rich-ballot policy. The public development map validates
  end to end. Provider-neutral direct-LLM and fixed/expanding hybrid readouts
  now bind exact evidence-condition inputs, recompute their posterior context,
  cache structured outputs by full request, and reuse the same ballot policy.
  The deterministic backend is only a boundary test double; the restricted
  final-bank map has now passed the locked blinded review. Its public authoring
  profile freezes packet-and-ontology-only inputs, coarse ordinal positions,
  derived centering, independent review, participant-safe output,
  restricted-only map writes, and a run-level approved-mapper attestation
  before any exact held-out mapping is used. No live provider or final
  prediction prompt is selected before Phase 4E.
- **4E — qualification, robustness, and final freeze (precommitment and
  runtime boundary implemented):** the public robustness profile requires three open-weight
  development candidates and one selected model across every LLM role. Hosted
  inference is allowed; local inference is not required; closed-weight models
  have no automatic fallback. The profile freezes pseudonymous-data rules, the
  answer-before-reveal interaction order, a hard USD 20 provider budget, a
  single-call primary estimator, three-call shadow repeats, prompt/order/label
  probes, outcomes, and claim limits. Robustness records bind the exact profile,
  candidate revision, and probe artifact; outstanding call authorizations
  reserve budget before any provider request. Candidate evaluation still
  occurs only on public development data. A shared provider runtime now binds
  private structured inputs to content-free request records, uses exact price
  cards and incremental pre-call reservations, records true spend when a token
  estimate is exceeded, and requires no-charge evidence before a cancellation
  can release budget. It records request-seed support separately from the seed
  itself and validates deterministic three-candidate selection with frozen
  practical-equivalence bands between ordered criteria. Its injected test
  transport makes no network request. The no-spend Together suite now binds
  GPT-OSS 120B, Nemotron 3 Ultra 550B A55B, and GLM-5.2 at exact upstream
  revisions; one captured serverless catalog, terms snapshot, price card,
  shared role prompt/schema/tool surface, request codec, and conservative
  qualification/held-out workload envelopes. It makes zero network calls and
  records zero spend. The separate readiness artifact now binds the exact
  revision-pinned upstream tokenizer files, all 456 rendered qualification
  request hashes and local counts, a deterministic resume order, and a public
  synthetic calibration of six initial waves plus 12 post-wave-six retests.
  The retests add 192 readout calls, for 1,104 held-out calls per candidate. It
  includes the initial and one tool-result follow-up payload for each
  interviewer call, while the live transport rejects a different round limit.
  It freezes USD 0.40 qualification and USD 0.50 held-out minimum headroom under
  a sequential proof that combines exact projected spend with the largest
  single-call envelope reservation, while retaining the sum of every envelope
  as a non-authorizing stress diagnostic. It records zero inference calls and
  zero spend. Together does not expose a
  cryptographic serverless
  serving-weight attestation, so the captured catalog hash is recorded as the
  serving revision and that limitation remains explicit. The round-number
  workload remains a non-authorizing feasibility plan, while the new readiness
  bundle closes the exact local-tokenizer projection and headroom gates. It
  does not claim provider-billing token equivalence because Together does not
  attest its internal serving tokenizer. Exact counting immediately before
  every future request remains mandatory, and a request that no longer fits
  its frozen envelope pauses without transmission. The live boundary now
  requires a manual account-privacy attestation and public-source receipt for a
  one-shot authenticated `/models` check; the paid HTTP/tool-loop transport
  cannot be constructed without a separate authorization object binding its
  tokenizer and headroom artifacts. Advertised context windows remain in
  candidate provenance while the receipt separately records live deployment
  ceilings, surfaces their aggregate divergence, and requires every live
  ceiling to fit the largest frozen request envelope. Live authorizations are
  segment-scoped: initial capability and qualification calls use the USD 4
  qualification segment, while retries require a fresh authorization for the
  USD 3 retry reserve and retain exact ledger lineage. Held-out authorization
  remains outside this qualification slice. A tracked capability plan binds
  the exact first 15 qualification entries: one canonical public-development
  request for every candidate and role. Corrected execution partitions that
  matrix into independent five-call candidate plans, each with a private,
  expiring approval and its exact reservation ceiling. A runner rebuilds every
  request from readiness inputs, stops on the candidate's first non-success,
  and issues a receipt only after all five role contracts pass and the
  interviewer completes a real typed-tool round. Closed candidate failures are
  terminal; ambiguous sent requests retain their reservation for manual
  reconciliation. Two v2 public-development attempts spent 13,143 microusd;
  no candidate has yet qualified, and no v3 paid call has occurred.

## Validation

The Phase 4A profile binds to the public Phase 3A bank profile, not the
restricted 48-measure fixture:

```bash
python -m eval.validate_phase4_protocol \
  eval/fixtures/preference_eval_phase4_protocol_v1.json \
  eval/fixtures/preference_eval_bank_profile_v1.json
```

Validate the separate semantic-map authoring precommitment with:

```bash
python -m eval.validate_phase4_semantic_profile \
  eval/fixtures/preference_eval_semantic_authoring_profile_v1.json \
  eval/fixtures/preference_eval_bank_profile_v1.json \
  eval/fixtures/preference_eval_phase4_protocol_v1.json
```

Validate the Phase 4E robustness and qualification precommitment with:

```bash
python -m eval.validate_phase4_robustness \
  eval/fixtures/preference_eval_phase4_robustness_v1.json \
  eval/fixtures/preference_eval_phase4_protocol_v1.json \
  eval/review_summaries/semantic_map_summary.json
```

The command binds 4E to the exact Phase 4 protocol and the approved,
participant-safe semantic-map summary. It prints hashes and aggregate policy
counts only. The profile does not contain packet text, participant evidence,
model responses, or a selected provider.

A completed public-development qualification is separately validated with
`python -m eval.validate_phase4_qualification`. The qualification bundle binds
the exact three candidate and price-card artifacts, provider usage ledger,
content-free execution journal, development fixture, hard-gate results, and
deterministically selected candidate. The bundle also binds the exact
sequential selection tolerances, so negligible sensitivity differences cannot
silence quality, cost, and latency. The tracked Together suite freezes the
three candidate artifacts, prices, and candidate-independent prompts/codecs
before that run. The live HTTP client/tool loop and no-spend readiness gate are
implemented. The account, source, and catalog receipt must be reissued against
the corrected v5 suite before constructing a paid authorization. The original
all-candidate capability gate stopped twice within the first candidate: once
on a transient provider error and once on an interviewer invalid-output
result. Direct review found that v2 combined tools, automatic tool choice, and
strict final-output formatting in the same round, so the second result is
harness-inconclusive, not a GLM rejection. V3 requires a tool-only first phase
and a separate strict decision phase. The tracked candidate-isolated
continuation binds both private attempts and derives separate five-role checks
for all three candidates, but it cannot authorize qualification. A later
reviewed, zero-spend aggregation must bind the independent receipts into the
full capability matrix. The catalog preflight makes authenticated network GETs but
invokes no model and has an exact zero-provider-spend authorization.

The following command preserves the historical v3 capability-plan replay:

```bash
python -m eval.validate_phase4_capability \
  eval/fixtures/preference_eval_phase4_together_capability_v2.json \
  eval/fixtures/preference_eval_phase4_together_v3.json \
  eval/fixtures/preference_eval_phase4_robustness_v1.json \
  eval/fixtures/preference_eval_phase4_together_readiness_v3.json \
  eval/fixtures/preference_eval_dev_v1.json \
  eval/fixtures/preference_eval_dev_session_v1.json \
  eval/fixtures/preference_eval_dev_semantic_map_v1.json
```

This validator makes no network request, accepts no credential, and reports
only aggregate counts, hashes, and cost bounds. Authorization and execution
remain separate private commands and require a new explicit spend decision.

Validate the post-failure continuation with
`python -m eval.validate_phase4_capability_continuation`. It binds the exact
private authorization/state pairs for both original attempts, records one
transient provider failure and one harness-inconclusive result, and derives
independent five-call plans for all three candidates from the corrected plan.
The historical 15-call plan and three-candidate qualification contract remain
auditable and are not reinterpreted.

The continuation predeclares one cross-candidate disposition before any v3
call is made. If all three interviewers complete the required tool phase and
then fail the separate final phase on strict validation of the shared root-
union schema, the result is a shared provider/schema incompatibility. The
schema and protocol must be revised and all three candidates retested; the
uniform pattern cannot disqualify all three models. Candidate-specific or
nonuniform failures remain subject to the ordinary capability gate. The
required zero-spend aggregator will enforce this rule against the three exact
receipts.

The first corrected GLM run subsequently passed the two-phase interviewer and
three other roles, then failed strict validation for the ontology proposer. Its
exact ignored state is retained as a provisional candidate failure rather than
a final rejection. A separate tracked zero-spend adjudication policy binds that
state and extends the predeclared discipline: three failures on the same role
and exact response schema require shared-harness review, while a nonuniform
pattern receives candidate-specific review. Before either remaining candidate
runs, the provider boundary must checkpoint the billed-call audit state and
then capture invalid-output error counts, error types, and schema-relative
paths in an ignored sidecar. It omits values, messages, and context and leaves
all existing journal/state hashes unchanged.
Future private authorizations wrap the original five-call authorization with
the exact adjudication-policy and provisional-state hashes; the future
execution state binds that wrapper while the preserved GLM state remains
byte-identical.

Those two comparison runs then exposed a broader provider-contract omission.
GPT-OSS and Nemotron stopped on the evidence extractor with identical
content-free claim-level paths, but the same audit found schema-invisible rules
in the ontology and readout response models. GLM's provisional ontology failure
therefore cannot be treated as a settled candidate limit. The correction fixes
the class rather than one prompt: a machine-readable 26-invariant manifest
records whether every provider-facing rule is visible in schema or prompt,
normalized on receipt, or checked against the exact request after parsing.
Nonsemantic list order and repeated identifiers are canonicalized; reversed
fixed-ontology pairs are reordered with the signed value inverted so meaning is
preserved. Request-bound semantic validation now covers all five roles.

Suite v4 upgrades only the interviewer, evidence-extractor, and ontology-
proposer wire contracts to v2. The direct and hybrid readout wire contracts
remain byte-identical v1 contracts, allowing their four exact successful calls
to carry forward. Provider request v2 hash-binds the semantic-validator
artifact, and execution resolves that identity only through the trusted local
validator registry before parsing. Bound execution cannot accept a caller
registry or adapter; it lazily resolves the exact module-owned singleton.
Implementation identity
`f077e2713b7ba0e6735f07e0ee367cc6d2203074841f78afda86ca450c009a09`
also binds emitted schemas, prompts, semantic constants, reviewed validator and
normalizer source, behavior probes, and the pinned Pydantic 2.13.4 /
pydantic-core 2.46.4 runtime. The frozen artifact hashes are suite v4
`aea27b51ed24c8e4c11bfe0648a04ff0e29d25faeb519a9afa95e594a3d84283`,
readiness v4
`517e955976eaeec708cbedfadb46673038dcfd47e472407573997c4913ab1cd5`,
capability plan v3
`2b78f3659e8a38e5ae74ea070172ea7eb9bc83a6c251a8bde2524573c6f12381`,
and capability delta
`25d286a8ceb16373e6868bb62bd81d3cf9b4cb0d2255f4ce02f66b2d4687f8e2`.

The generic delta carries four exact direct/hybrid successes and reruns eleven
conversational-role calls across all three candidates: three for GLM and four
each for GPT-OSS and Nemotron. It records 31,639 microusd already spent,
projects 52,140 microusd for the delta, and caps new authorizations at 93,300
microusd, for a 124,939-microusd cumulative worst case under the original
150,000-microusd ceiling. Building and validating the correction made no
provider call and spent nothing. No paid delta call may run until the corrected
artifacts are reviewed and merged, followed by a fresh catalog preflight and
explicit user approval. That v4 requirement is preserved as the historical
authorization boundary; current execution must bind the v5 selector-recovery
chain below.

Candidate-specific authorization follows the candidate order frozen in the
delta. Each later authorization must supply the exact preceding authorization
and terminal-state prefix, binding those state hashes and actual spend before
proving that prior actual spend plus all remaining maximum reservations stays
under the original 150,000-microusd ceiling. A sent call that exceeds a manual
or provider cap is nevertheless checkpointed as an auditable terminal state;
it cannot receive a success receipt, resume, or authorize another candidate.

The content-free delta source proof, hash
`58d65a797d832a39ae1c3e2f65cddff893a296e04fa88b07f97ab89a187d5b15`,
is emitted only after the exact ignored source audits rebuild the delta. It
binds the source attempts and carry/rerun partition without retaining values,
messages, or context. Candidate authorization and execution require this exact
proof and bind it into the manual approval, so a structurally valid alternate
partition cannot pass the paid boundary under the reviewed receipt.

The later GLM suite-v4 delta attempt passed extraction and made a real
interviewer tool call, then failed validation at the nested question field while
reproducing the complete canonical question object. The content-free diagnostic
does not isolate the failing nested invariant. This is a serialization burden
introduced by the harness, not the research decision being tested. The question
bank remains dynamic: the exact current tool invocation ranks vetted candidates
from the full bank, and the LLM still chooses which candidate to ask, clarify,
or pause. Suite v5 narrows only the provider wire response for an ask decision
to `selected_question_id`. Trusted local code requires that id to match an exact
candidate returned by the same tool call, verifies its canonical checksum
locally, then hydrates and validates the existing full decision. The invariant
manifest v2, hash
`944efa35f60c3a9286f96b201ef21a9b1ff7ecda1a9a6ae96369c491e959523b`,
records selector grounding as post-parse and local materialization as normalized
plus post-parse. The byte-identical v1 manifest remains available only for
historical audit reconstruction. The ephemeral tool-result context is never
stored; its exact hash is bound into the finalization. Model selection failures
and missing or malformed local context have distinct audited outcomes.

The operative frozen hashes are suite v5
`e97b6213955cf86d18da98d2d1300679b17ab773838d1ed10fcdb84b1f1de9b8`,
readiness v5
`f6ac45a3da3a4c14784aa6a9562ec1e3c62cd141aba214748b4f6a9fcbbaf5fd`,
and capability plan v4
`e42b7d71c9ccfb07e6583313f07af60678178ef72eacf7182fa78255fa6f1fde`.
The chained selector-recovery delta v2 has hash
`0a09365d59e01694fbe33a3d4d3b6af335c35a01f0e45ae658467309bd53adb4`;
its source proof has hash
`c60ca23180894287f18f964e503f91ecb59a70a497f0d9a54fee075145be8261`.
It carries five exact successes and reruns ten calls. It records 40,227
microusd already spent, projects 43,584 microusd more, caps new authorizations
at 80,500 microusd, and bounds the cumulative worst case at 120,727 microusd
under the original 150,000-microusd ceiling. Constructing all v5 artifacts
made no inference call and spent nothing.

Validate the current no-spend capability plan with:

```bash
python -m eval.validate_phase4_capability \
  eval/fixtures/preference_eval_phase4_together_capability_v4.json \
  eval/fixtures/preference_eval_phase4_together_v5.json \
  eval/fixtures/preference_eval_phase4_robustness_v1.json \
  eval/fixtures/preference_eval_phase4_together_readiness_v5.json \
  eval/fixtures/preference_eval_dev_v1.json \
  eval/fixtures/preference_eval_dev_session_v1.json \
  eval/fixtures/preference_eval_dev_semantic_map_v1.json
```

The paid selector-recovery calls ran only after independent review and merge, a
fresh suite-v5 catalog preflight, and new short-lived explicit user approvals.
The existing candidate-specific delta authorization and runner commands load
this v2 plan/proof only through explicit schema dispatch; the historical v1
loaders remain exact. The shared execution records bind the opaque reviewed
delta/proof hashes, exact candidate subset, manifest version, ordered prior
states, and cumulative spend, so no v1 conversion artifact is introduced.
If the reviewed id-only selector still fails, stop adding provider-specific
patches and reassess the provider boundary and project scope. Missing or invalid
local hydration context remains a harness error and cannot support a candidate
verdict. OpenRouter remains only a controlled alternate-host diagnostic: it
requires
an exact model and endpoint pin, disabled fallbacks and response healing,
recorded routing provenance, and a separate reviewed budget and authorization.
Any cross-host result is deployment evidence, not a model-family claim.

The resulting capability evidence is frozen in
`preference_eval_phase4_together_capability_aggregation_v1.json`, canonical
hash
`e9a0bd7141a9536041e3d242d0696daade3b3325c562cf1bd2a4b5f34dd8452e`.
Its content-free source proof has hash
`de14bde9c424c530a62367ffec202d936f8180ec123db300996baa4956c9a156`.
GLM-5.2 and GPT-OSS 120B have complete five-role capability evidence and are
capability-passed, not qualified. The exact Nemotron 3 Ultra/Together
deployment is provider/deployment-inconclusive after an HTTP 400 with no model
output returned, no provider-reported token usage, and no charge; this does not
establish a model-capability failure. The aggregate binds 5 carried successes,
6 observed successes, 1
provider failure, 3 unattempted suffix roles, 7 recovery calls, and cumulative
capability spend of 51,042 microusd. Building the aggregate made no provider
call and spent nothing.

`python -m eval.prepare_phase4_capability_aggregation` rebuilds the tracked
result from the exact ignored authorization/state sources.
`python -m eval.validate_phase4_capability_aggregation` rechecks the complete
public chain without private access and emits aggregate-only output. The result
records no reviewed v1 capability receipt or qualification authorization, so
the controlled workflow remains blocked. This is not an unbypassable property
of the old v1 validator, which cannot replay a supplied receipt's private
provider audit. The v1 qualification bundle also requires exactly three
complete candidate results. Qualification therefore requires a separately
reviewed versioned authorization and result scope that preserves the original
roster, retains the affected deployment as inconclusive and not run in
qualification, forbids replacement, and precommits the two-runnable-candidate
comparison before any qualification metric is observed. The qualification
runner must consume and source-validate that scope as its actual gate; it must
not emit or be described as a v1 `Phase4QualificationBundle`.

The Phase 4A command prints content hashes and aggregate architecture counts.
Phase 4A does not choose an LLM provider, prompt, model version, evidence
weights, semantic mapper, or robustness estimator. The reviewed semantic map
and public Phase 4E precommitment now close two of those boundaries; the
qualified candidate, live deployment attestation, seeds, remaining policy
values, and calibrated thresholds still must be selected on public development
data and frozen before any held-out response is viewed.
