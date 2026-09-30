# Spectrum elicitation — PR 1

This public no-save prototype tests whether people can express three different
things without forcing unrelated values into a pairwise trade-off. It is not
the frozen blinded study, a learned preference model, or a ballot readout.

## Three separate reports

1. **Position:** the currently preferred point on a clearly defined numeric
   axis. Explicit selection is required, including when keeping the initial
   displayed position. The UI never interprets distance from the midpoint as
   evidence weight or importance.
2. **Reported uncertainty:** optional numeric `{sd_fraction}` describing the
   chosen curve width, not three semantic categories. The display samples a
   Gaussian-shaped kernel on the normalized axis, normalizes its area, and
   uses a fixed vertical scale. Its kernel SD is adjustable from 0.08 to 0.28
   of the full axis span; pointer/keyboard changes use 0.001 increments (201
   widths), and the API preserves any finite in-range numeric width exactly.
   The selected position remains the peak, including at an endpoint; it is not
   claimed to be the mean of the bounded curve. Kernel SD is an illustrative
   width parameter, not the actual SD of the bounded curve or a calibrated
   probability. Missing uncertainty stays null; a dashed preview is not an
   answer until the participant explicitly adjusts/includes it. Persistent
   “Answer uncertainty” / “Leave uncertainty unanswered” controls restore the
   last local width when answering again.
3. **Acceptable interval:** optional lower/upper bounds, independently reported
   and displayed on the same graph. Full-width Min/Max bars are visible by
   default as an amber, unconfirmed preview. Manipulating either graph bound
   or editing a bound in Fine adjustment includes the range; “Use this range”
   includes unchanged displayed bounds. Untouched defaults remain unanswered.
   “Leave range unanswered” preserves that preview. Hiding omits the range;
   showing it restores the last bounds as a preview, not an included answer.
   Omission means null, not full-scale acceptance. This interval
   never clips the uncertainty curve or silently moves the position. A
   position outside the interval can be recorded without automatic correction;
   the reports are kept as given rather than made artificially consistent.

Skip and depends/hard-to-place are distinct non-numeric responses. Neither is a
middle position. A single interval cannot express two separated acceptable
regions. Use depends/hard-to-place when this interaction does not fit.

## One graph, three independent controls

- Move the position thumb along the axis, or tap the axis directly.
- Pull the peak up to narrow the curve or down to broaden it. The drag inverts
  the plotted peak height so it follows the pointer, including at endpoints;
  numerical width changes are preserved end to end.
- Drag either acceptable-bound bar or its Min/Max tab horizontally. The tabs
  use separate hit-target lanes so a zero-width interval remains editable.
- Tab and arrow keys work on every handle; Home/End reach its limits.
  Collapsible fine adjustments use numeric inputs, or clock-labeled time
  choices for clock axes; stored hours remain numeric.
- Proposed bounds become an answer on direct editing or explicit inclusion,
  and never affect the curve. Previous/Next question navigation and summary
  Edit links preserve each question's draft, omitted settings, and later
  recorded responses. Recording an update replaces only that question's
  response; the summary excludes edits that have not been recorded.
- Centered optional-answer controls show the current included numeric values.
  Red-tinted X buttons omit those reports; amber text and an icon distinguish
  the optional, unanswered range preview from included bounds.
  Keyboard/tap-accessible help popovers explain each report and its preview.

The presentation uses regularly spaced ticks from the actual numeric step
grid, not the three authored anchors. Narrow layouts thin labels without
moving ticks or endpoints or reducing input precision. The public-comment
question accepts every whole day from 7 through 56, including range bounds.
A live position readout sits below the thumb, width
beside the peak (above it when space is tight), and values beside each bound.
The full readback remains available; redundant below-graph visual summaries
are removed. Local light/dark tokens use charcoal for position, clay for the
curve, and teal for acceptance. Colors identify signals, not favored answers
or higher-confidence rewards; dashed previews and distinct handle shapes do
not rely on color alone. Width is never labeled as calibrated confidence.

## Public content and contract

`preferences/data/spectrum_demo_v1.json` contains four authored hypothetical
questions. Each has a stable ID, version, context, one numeric scale, units,
step, and named anchors. This data is separate from the existing 36-item
pairwise bank and all restricted evaluation material. No facts about a real
jurisdiction or observed public preferences are asserted.

The stateless `/api/preferences/elicitation` request contains the bank version
and a prefix of explicit responses. The Python service validates each
question ID/version and each numeric response against the authored scale.
The response returns all four public questions and accepted responses so an
early summary can distinguish unasked questions from skips. Both HTTP
boundaries validate shapes; the browser also checks each answer against the
current question. Upstream results must echo the submitted responses exactly.

No save, database writes, browser storage, participant-response logging,
provider calls, or credentials are added. Responses do travel to the app's
Python service; deployment telemetry is a separate privacy consideration.
Reset/refresh clears the browser state. A failed submission retains accepted
history and draft controls without advancing the question. Navigation itself
does not submit anything; all question drafts remain in local browser memory.

## Verification and comprehension check

- Narrow uncertainty with broad acceptance, and the reverse, are independently
  expressible. Acceptance editing has no input into curve sampling.
- Null optional fields remain null. Explicit zero is valid on a scale that
  includes it. Skip and depends have no numeric fields.
- Bad versions, question order, finite/range/step violations, and inconsistent
  counts fail at the boundary without reflecting response contents in errors.
- Curve area is normalized; peaks and endpoint behavior remain finite on the
  fixed display scale. Custom handles have keyboard controls and touch-sized
  targets, with native fine-adjustment controls as an alternative.
- Test early summary, completed/all-skipped sessions, reset/refresh, failures,
  and narrow layouts. Run web-boundary/helper tests, API tests, Python
  regression tests, lint/types, and the production build.

Before PR 2, Ben should express several specified combinations and explain the
resulting picture back in his own words. That is a comprehension check, not
evidence of predictive accuracy. Additional participants or retained answers
require separate approval.

### Implemented and checked — 2026-09-25

PR 1 is implemented locally, awaiting review. The frontend reuses the session
shell and existing UI primitives; the pairwise models and evaluation artifacts
are untouched. After Ben's first walkthrough, the separate controls were
replaced with the integrated graph and granular numeric width. This supersedes
the first version's three radios and deferred curve-dragging plan.

- Full Python suite: **1,339 passed**. Four warnings: three existing warnings
  plus a sandbox pytest-cache write warning; no test failures.
- Web bridge and curve helpers: **49 passed** via
  `node --test tests/elicitation-route.test.mjs tests/spectrum-controls.test.mjs`.
- `npm run build`: passed compilation, lint/types, and page generation.
- Browser checks: narrow mobile layout without horizontal overflow, keyboard
  position/range controls and heading focus, early-summary draft preservation,
  independent curve/range edits, omitted details, zero-valued answers,
  skip/depends, completed readback, reset/refresh, and API-down recovery without
  draft loss or double advancement.
  The integrated revision additionally checks direct peak and bar-shaft drags,
  intermediate widths (10.3% / 13.7%), multi-digit numeric typing, coincident
  bounds, and continuous-width API/readback preservation. An unconfirmed range
  survives review/back without becoming an accepted answer.
- The subsequent presentation-only pass re-ran all 49 web tests and the
  production build. Browser checks covered 1280px desktop and 375px/320px
  mobile layouts, all four numeric axes, endpoint and coincident-bound labels,
  direct position/peak dragging, 13.7% readback, skip/depends, and reset. New
  label colors exceed 4.5:1 against the graph background in both defined
  palettes; dark-mode contrast was calculated, not browser-tested. Python and
  API contracts were unchanged, so the earlier full Python result above was
  not re-run for this styling pass.
- The optional-control refinement passed **58 frontend tests**:
  `node --test tests/elicitation-route.test.mjs tests/spectrum-controls.test.mjs tests/spectrum-fine-adjustment.test.mjs tests/spectrum-answer.test.mjs`.
  New component tests check server-rendered controls; transitions were checked
  in the browser, not an automated interaction suite. The production build
  passed including lint/types. Browser checks covered omission/restoration,
  focused toggles, clock labels, summary “Not provided” for omitted width and
  unconfirmed range, fresh-question resets, and help/layout at 1280px desktop
  and 320px mobile without overflow. Python was not re-run for this
  frontend-only refinement; the earlier 1,339-test result remains historical.
- `git diff --check`: clean. `mypy` is not installed in the project venv, so
  that separate check was not run.

These are implementation checks, not evidence that users understand the
interaction or that it predicts preferences accurately.

### Navigation and inclusion revision — 2026-09-29

Ben's next walkthrough replaces the earlier confirmation-after-edit behavior:
editing either bound now includes the range, like editing uncertainty. The
initial amber preview still does not answer for the participant. Live numeric
readouts and red/X omission buttons make the current answer explicit.
Previous/Next and summary Edit links support revisiting questions without a
restart or losing later responses. The public-comment scale now advances one
day at a time; label spacing remains a display concern.

The question-navigation arrows sit beside Start again above the progress bar,
not below the answer controls. They cannot advance past an unanswered question;
summary mode keeps its explicit Edit and Back-to-question controls instead.
The placement follow-up passed the same 65 frontend tests and production build;
desktop/320px browser checks confirmed named 44px targets, first/frontier
disabled states, keyboard navigation with heading focus, and preserved drafts.

- Focused frontend tests: **65 passed** across the route, graph helpers, fine
  controls, rendered components, and navigation tests.
- Focused API tests: **114 passed**, including positions and acceptable bounds
  at 8 and 29 days, with fractional days still rejected.
- Full Python suite: **1,341 passed**, with three pre-existing deprecation
  warnings and one sandbox pytest-cache-write warning.
- Browser checks: Previous/Next preserved later recorded responses and
  unfinished drafts, including omitted uncertainty and hidden ranges. Updating
  an earlier answer kept later responses, completed-summary Edit returned to
  the selected question, and unrecorded changes stayed out of the summary.
  Graph-keyboard and fine-input bound edits included the range without
  selecting position or uncertainty. One ArrowRight moved 29 to 30 days, and
  the 8–29-day range recorded correctly. Desktop and 320px panels had no
  horizontal overflow.
- `npm run build` passed, including lint/types. The September 25 build results
  above remain historical.

## Next, not implemented here

Add one explicit per-axis position estimator with a stated observation model.
Initially use positions with a declared baseline noise assumption, rather
than treating reported certainty as model confidence. Any uncertainty
weighting is a separate modeling choice to evaluate. Acceptance remains a
separate report until its modeling interpretation is defined. Do not map the
new axes implicitly into the old utility coordinates or transfer the
synthetic pairwise benchmark's claims to this interaction.
