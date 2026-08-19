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
- **4E — qualification, robustness, and final freeze (precommitment
  implemented):** the public robustness profile requires three open-weight
  development candidates and one selected model across every LLM role. Hosted
  inference is allowed; local inference is not required; closed-weight models
  have no automatic fallback. The profile freezes pseudonymous-data rules, the
  answer-before-reveal interaction order, a hard USD 20 provider budget, a
  single-call primary estimator, three-call shadow repeats, prompt/order/label
  probes, outcomes, and claim limits. Robustness records bind the exact profile,
  candidate revision, and probe artifact; outstanding call authorizations
  reserve budget before any provider request. Candidate evaluation still
  occurs only on public development data. No candidate has yet qualified and
  no live call is part of this precommitment slice.

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

The Phase 4A command prints content hashes and aggregate architecture counts.
Phase 4A does not choose an LLM provider, prompt, model version, evidence
weights, semantic mapper, or robustness estimator. The reviewed semantic map
and public Phase 4E precommitment now close two of those boundaries; the live
candidate, provider deployment, prompts, seeds, policy values, and qualified
thresholds still must be selected on public development data and frozen before
any held-out response is viewed.
