# New York recorded harbor links benchmark

0 accepted plans; 4 failed attempts. The independently checked input has 288,819 source blocks and 20,201,249 residents.

[Open comparison and maps](http://127.0.0.1:8770/policies/new-york-links-v1/)

| House size | Districts | Max deviation (people) | Max deviation (%) | Pipeline (s) | Solve (s) | Peak MiB | Policy-connected |
|---|---:|---:|---:|---:|---:|---:|---:|
| 435 | 26 | No accepted plan | — | 126.41 | 27.520 | 1,053.9 | Not evaluated |
| 574 | 35 | No accepted plan | — | 133.75 | 35.252 | 1,053.6 | Not evaluated |
| 692 | 42 | No accepted plan | — | 140.28 | 43.322 | 1,052.4 | Not evaluated |
| 1000 | 61 | No accepted plan | — | 135.29 | 30.816 | 1,052.8 | Not evaluated |

[Inspect the recorded source connections](http://127.0.0.1:8770/policies/new-york-links-v1/connections/). This source map does not assign district labels.

## Two explicit geographic connections

Liberty Island uses a recorded 795 m water connection. New York’s Ellis Island block uses a recorded 852 m exclave connection: about 827 m of mapped harbor water and 26 m of New Jersey land. Both island blocks have zero resident population and connect to the same New York water block. The records grant graph adjacency only; no New Jersey territory or population is assigned and no source geometry changes. Each link contributes only when its endpoint blocks belong to the same district. Physical and policy connectivity remain distinct.

### 26 districts

The inner weight optimizer failed on balance pass 2 after 300 iterations: STOP: TOTAL NO. OF ITERATIONS REACHED LIMIT. Its configured inner iteration limit was 300. This is an inner-optimizer failure, separate from the outer center-convergence limit. No validated district plan or completed map is accepted from this attempt. Final population balance and district connectivity are unavailable; failure time and peak process memory are still measured.

[Preserved failed report](C:/Users/benja/projects/voting_paradigm/.cache/state-block-benchmark/suite-through-1000/policies/new-york-links-v1/states/36/districts-26/benchmark.json) · [Source connections map](http://127.0.0.1:8770/policies/new-york-links-v1/connections/)

### 35 districts

The inner weight optimizer failed on balance pass 2 after 300 iterations: STOP: TOTAL NO. OF ITERATIONS REACHED LIMIT. Its configured inner iteration limit was 300. This is an inner-optimizer failure, separate from the outer center-convergence limit. No validated district plan or completed map is accepted from this attempt. Final population balance and district connectivity are unavailable; failure time and peak process memory are still measured.

[Preserved failed report](C:/Users/benja/projects/voting_paradigm/.cache/state-block-benchmark/suite-through-1000/policies/new-york-links-v1/states/36/districts-35/benchmark.json) · [Source connections map](http://127.0.0.1:8770/policies/new-york-links-v1/connections/)

### 42 districts

The inner weight optimizer failed on balance pass 2 after 300 iterations: STOP: TOTAL NO. OF ITERATIONS REACHED LIMIT. Its configured inner iteration limit was 300. This is an inner-optimizer failure, separate from the outer center-convergence limit. No validated district plan or completed map is accepted from this attempt. Final population balance and district connectivity are unavailable; failure time and peak process memory are still measured.

[Preserved failed report](C:/Users/benja/projects/voting_paradigm/.cache/state-block-benchmark/suite-through-1000/policies/new-york-links-v1/states/36/districts-42/benchmark.json) · [Source connections map](http://127.0.0.1:8770/policies/new-york-links-v1/connections/)

### 61 districts

The inner weight optimizer failed on balance pass 1 after 300 iterations: STOP: TOTAL NO. OF ITERATIONS REACHED LIMIT. Its configured inner iteration limit was 300. This is an inner-optimizer failure, separate from the outer center-convergence limit. No validated district plan or completed map is accepted from this attempt. Final population balance and district connectivity are unavailable; failure time and peak process memory are still measured.

[Preserved failed report](C:/Users/benja/projects/voting_paradigm/.cache/state-block-benchmark/suite-through-1000/policies/new-york-links-v1/states/36/districts-61/benchmark.json) · [Source connections map](http://127.0.0.1:8770/policies/new-york-links-v1/connections/)

## Strict baseline and interpretation

The preserved strict K26 attempt stopped at source-topology preflight after 99.3615688 seconds. K35/K42/K61 reused that exception. No prior strict solver runtimes or solved populations exist; this is not a before/after solver speed comparison.

## Validation and timing limits

Independently read the original DBF, checked official source totals and zero-population endpoint blocks, matched both typed connection records and provenance to each report, checked the saved source graph audits (three physical components, two recorded links, one augmented component), and verified 1052 preserved historical file hashes. For 4 failed attempts, checked recorded failure and execution evidence. No final assignment coverage, population balance, compressed district map or district-connectivity validation is claimed for those attempts.

All 526 districting and script regression tests passed in 11.13 seconds. Browser checks passed for the comparison, harbor and island views, Ellis land crossing, and link/context toggles, with no captured browser errors or warnings. Source-map screenshots are saved beside the comparison. Both orchestrators and all four benchmark children have exited; the state36 execution lock was independently verified free.

- New plans run serially in fresh processes with cached source and part graphs; shared-desktop timings are observations, not isolated hardware comparisons.
- For accepted plans, pipeline time includes source and link preparation, solving, repair/rebalance, independent polygon validation, map export, viewer generation and preservation checks. For failed attempts it measures only work through the failed phase plus failure cleanup/preservation; unexecuted repair or export phases are not included.
- Process imports, initial preservation inventory and final report flush are outside the pipeline timer.
- Strict topology rejection happened before solving; it is not a before/after solver-performance baseline.
- Physical shared-edge connectivity and policy connectivity are separate. Liberty uses a water link; Ellis uses an explicit exclave link over New Jersey land and water. No New Jersey area or population is assigned.
- Only accepted-plan population deviations are independently recomputed from source DBF and final assignments. Failed attempts have no accepted final balance or district-connectivity measurement. Local whole-block balancing does not establish global optimality.
- Successful inner optimizer passes, outer center convergence, final postprocessed population balance and policy connectivity are independent outcomes. Outer iteration-limit cases are disclosed explicitly.
- Compressed payloads measure saved map bytes, not browser memory or latency. New Jersey diagnostic context loads only on connection/harbor inspection and is separate from the map export sizes.

[Water / land audit](C:/Users/benja/projects/voting_paradigm/.cache/state-block-benchmark/suite-through-1000/diagnostics/new-york/geography-context.json) · [Original diagnosis](http://127.0.0.1:8770/diagnostics/new-york/) · [Machine-readable comparison](C:/Users/benja/projects/voting_paradigm/prompts/new-york-links-benchmark.json)

## Attempt history

Original suite: `stopped`, 129.548 s. Its manifest and first attempted plan remain preserved.

Supplemental first attempts: `complete`, 426.824 s. These attempted previously unstarted district counts with unchanged code and settings; they did not retry K26.

A terminal attempt may be failed. Supplemental jobs are first attempts for originally unstarted anchors; the failed original attempt is retained without retry.
