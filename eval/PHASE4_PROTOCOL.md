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
- **4C — confirmed conversational evidence (fixed-ontology slice
  implemented):**
  fixed-ontology proposal, per-claim confirmation/edit/rejection,
  append-only correction, provenance, durable IDs, and same-cutoff evidence
  views are implemented. Ontology-expansion admission, duplicate, merge,
  shrinkage, and prune rules remain next.
- **4D — prediction readouts:** add `prediction_snapshot.v2` and a compatible
  versioned run contract for ranking tiers, approval sets, scores, and
  quadratic allocations; preserve `prediction_snapshot.v1` and the frozen
  Phase 3C bundle hashes. Then implement authored semantic mapping, direct LLM
  control, and hybrid readouts on common evidence cutoffs.
- **4E — robustness and final freeze:** test prompt paraphrases, option order
  and labels, stochastic sensitivity, and unsupported assumptions before the
  held-out case study.

## Validation

The Phase 4A profile binds to the public Phase 3A bank profile, not the
restricted 48-measure fixture:

```bash
python -m eval.validate_phase4_protocol \
  eval/fixtures/preference_eval_phase4_protocol_v1.json \
  eval/fixtures/preference_eval_bank_profile_v1.json
```

The command prints content hashes and aggregate architecture counts. Phase 4A
does not choose an LLM provider, prompt, model version, evidence weights,
semantic mapper, or final robustness estimator; those must be implemented and
frozen before any held-out response is viewed.
