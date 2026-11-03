# New York: remaining 1,000-iteration anchors

New York K35/K42/K61 for House 574/692/1000 with 1,000 inner iterations; K26 is a preserved prior reference.

3 accepted new plans; 0 failed new attempts. 1,172 historical files remain byte-identical.

| Districts / House | Outcome | Maximum final deviation | Pipeline | Solve | Peak memory | Outer centers |
|---|---|---:|---:|---:|---:|---|
| 26 / 435 (prior reference) | complete_under_recorded_mixed_policy | 11.884615 people (0.001529608%) | 1027.022 s | 356.010 s | 1.387 GiB | outer_iteration_limit_without_center_convergence |
| 35 / 574 | complete_under_recorded_mixed_policy | 53.457143 people (0.009261804%) | 1214.198 s | 535.075 s | 1.386 GiB | outer_iteration_limit_without_center_convergence |
| 42 / 692 | complete_under_recorded_mixed_policy | 59.880952 people (0.012449725%) | 1753.425 s | 1078.791 s | 1.379 GiB | outer_iteration_limit_without_center_convergence |
| 61 / 1000 | complete_under_recorded_mixed_policy | 34.983607 people (0.010563703%) | 2149.513 s | 1474.088 s | 1.334 GiB | outer_iteration_limit_without_center_convergence |

## 35 districts / House 574

Original failure: 133.753 s through solver failure on pass 2 at 300 iterations. New trace: 81 passes, 7,043 accepted iterations, 2.518 s observed overhead.

The largest inner pass used **410 of 1,000 allowed iterations**; 6 passes exceeded the original 300-iteration budget.

The outer loop reached the 80-iteration limit without center convergence. Successful inner optimizer passes do not establish outer convergence. Final population balance and connectivity are assessed separately after repair/rebalancing.

All 35 districts pass graph and independent polygon-plus-link connectivity. Physical polygon components per district: `[1, 1, 1, 1, 1, 1, 3, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1]`. Recorded links belong to display district(s): `[7, 7]`.

[Validated district map](http://127.0.0.1:8770/corrections/new-york-inner-budget-anchors-v1/states/36/districts-35/)

At the new run's checkpoint corresponding to the original failing pass 2, maximum population deviation **decreased** from 4180.457143 people at iteration 300 to 2400.542857 at termination; additional objective improvement 4.02295545867e-09. These are intermediate optimizer assignments, before repair/rebalancing.

## 42 districts / House 692

Original failure: 140.284 s through solver failure on pass 2 at 300 iterations. New trace: 81 passes, 14,305 accepted iterations, 5.164 s observed overhead.

The largest inner pass used **557 of 1,000 allowed iterations**; 15 passes exceeded the original 300-iteration budget.

The outer loop reached the 80-iteration limit without center convergence. Successful inner optimizer passes do not establish outer convergence. Final population balance and connectivity are assessed separately after repair/rebalancing.

All 42 districts pass graph and independent polygon-plus-link connectivity. Physical polygon components per district: `[1, 1, 1, 1, 1, 1, 3, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1]`. Recorded links belong to display district(s): `[7, 7]`.

[Validated district map](http://127.0.0.1:8770/corrections/new-york-inner-budget-anchors-v1/states/36/districts-42/)

At the new run's checkpoint corresponding to the original failing pass 2, maximum population deviation **decreased** from 85993.119048 people at iteration 300 to 2251.119048 at termination; additional objective improvement 6.74031110015e-06. These are intermediate optimizer assignments, before repair/rebalancing.

## 61 districts / House 1000

Original failure: 135.291 s through solver failure on pass 1 at 300 iterations. New trace: 81 passes, 14,087 accepted iterations, 5.659 s observed overhead.

The largest inner pass used **779 of 1,000 allowed iterations**; 12 passes exceeded the original 300-iteration budget.

The outer loop reached the 80-iteration limit without center convergence. Successful inner optimizer passes do not establish outer convergence. Final population balance and connectivity are assessed separately after repair/rebalancing.

All 61 districts pass graph and independent polygon-plus-link connectivity. Physical polygon components per district: `[1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 3, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1]`. Recorded links belong to display district(s): `[31, 31]`.

[Validated district map](http://127.0.0.1:8770/corrections/new-york-inner-budget-anchors-v1/states/36/districts-61/)

At the new run's checkpoint corresponding to the original failing pass 1, maximum population deviation **increased** from 910.016393 people at iteration 300 to 1664.016393 at termination; additional objective improvement 3.8819669701e-11. These are intermediate optimizer assignments, before repair/rebalancing.

[Interactive comparison and optimizer traces](http://127.0.0.1:8770/corrections/new-york-inner-budget-anchors-v1/)

Validation: Prelaunch full districting/script suite: 659 tests passed. Post-metadata focused validation: 34 runner and 34 comparison tests passed. Independent terminal source DBF, trace arithmetic, final population, compressed-map, endpoint-ownership, fixed-code/settings and 1,172-file historical-preservation checks passed. Parent and child processes exited; the state 36 lock was acquired/released. All three map pages passed browser checks for district/population totals, both recorded links owned by D7/D7/D31, state detail and explicit county 061 loading of 4,043 blocks, with no initial block-detail load. Combined comparison passed all three plan selectors, original-failing-pass defaults, manual pass selection, iteration/time axes and linear/log population scales. Page layouts and saved screenshots were inspected; no console warnings or errors were reported.

- Each new plan is compared with its own original failed 300-iteration attempt. Only inner_max_iterations changes to 1,000; original code, source, seed, other settings and recorded links are retained.
- K26 was not rerun. Its timing and results are a read-only reference from the earlier completed experiment, excluded from new-suite elapsed time and counts.
- An original failed runtime stops in optimization; it is not the runtime of a complete district plan. New completed runtimes include repair, independent polygon validation and map export. Runs are serial on a shared desktop, with measured observer overhead.
- Normalized negative dual is minimized. Objective gain is initial minus current objective within one balancing pass only; center changes alter the objective between passes. Whole-block population imbalance can worsen while objective improves.
- Iteration-300 checkpoints are observations in the new runs. Historical failed attempts did not save objective or population trajectories. Diagnostic point assignments are not accepted connected plans.
- Successful inner optimization, outer center convergence, postprocessed population balance and polygon-plus-recorded-link connectivity are separate outcomes. Physical connectivity remains distinct from recorded-link policy connectivity.
- Map payloads are compressed bytes on disk, not browser memory or transfer latency. Full block geometry remains split into county files loaded on demand.
