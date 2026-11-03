# New York: 1,000-iteration inner-budget experiment

New York 26 districts (House 435), 300 versus 1,000 inner iterations; all other numerical settings, source and recorded links fixed.

The larger inner budget produced a validated 26-district plan. All 81 inner passes succeeded; only passes 2, 3, 8 exceeded 300 iterations. The largest pass used 377 of the allowed 1,000 iterations. After repair/rebalancing, maximum population deviation is 11.884615 people (0.001529608%). The outer loop reached the 80-iteration limit without center convergence. Successful inner optimizer passes do not establish outer convergence. Final population balance and connectivity are assessed separately after repair/rebalancing.

Result: **complete_under_recorded_mixed_policy**. Original failed evidence and 1,083 protected files remain byte-identical.

| Measure | Original: 300 | Rerun: 1,000 |
|---|---:|---:|
| Timed pipeline | 126.413 s | 1027.022 s |
| Solve | 27.520 s | 356.010 s |
| Peak process working set | 1.029 GiB | 1.387 GiB |
| Accepted district plan | No | Yes |

The original failed on inner pass 2 at 300 iterations. The rerun recorded 81 inner passes and 5,683 accepted optimizer iterations. Observer overhead: 1.973 s.

| Pass | Inner iterations | Success | Objective gain | Max deviation at 300 (people) | Terminal max deviation (people) | Pass trace time |
|---:|---:|:---:|---:|---:|---:|---:|
| 1 | 192 | Yes | 0.0706555727 | Not reached | 1,349.885 | 10.668 s |
| 2 | 351 | Yes | 0.101581917 | 30,956.885 | 1,420.885 | 19.383 s |
| 3 | 377 | Yes | 0.000370328063 | 5,823.115 | 2,401.115 | 20.594 s |
| 4 | 156 | Yes | 3.94405874e-05 | Not reached | 2,699.115 | 8.497 s |
| 5 | 240 | Yes | 1.17168442e-05 | Not reached | 4,431.885 | 13.890 s |
| 6 | 215 | Yes | 1.19882029e-05 | Not reached | 1,138.885 | 11.624 s |
| 7 | 229 | Yes | 2.64896334e-05 | Not reached | 2,896.115 | 12.650 s |
| 8 | 303 | Yes | 3.77355178e-05 | 679.885 | 2,586.115 | 16.088 s |
| 9 | 280 | Yes | 2.3549451e-05 | Not reached | 1,133.115 | 17.185 s |
| 10 | 290 | Yes | 9.2513041e-06 | Not reached | 1,498.885 | 16.896 s |
| 11 | 220 | Yes | 3.6265724e-06 | Not reached | 2,609.885 | 12.582 s |
| 12 | 220 | Yes | 1.63568189e-06 | Not reached | 3,716.885 | 11.617 s |
| 13 | 160 | Yes | 9.15374375e-07 | Not reached | 1,313.115 | 8.872 s |
| 14 | 80 | Yes | 2.78808157e-07 | Not reached | 2,410.115 | 4.856 s |
| 15 | 285 | Yes | 9.93876414e-08 | Not reached | 2,474.885 | 17.596 s |
| 16 | 70 | Yes | 4.80551013e-08 | Not reached | 1,426.115 | 4.552 s |
| 17 | 86 | Yes | 3.15348964e-08 | Not reached | 874.115 | 4.870 s |
| 18 | 75 | Yes | 1.9855823e-08 | Not reached | 2,795.115 | 5.032 s |
| 19 | 87 | Yes | 1.5792902e-08 | Not reached | 2,082.885 | 6.276 s |
| 20 | 85 | Yes | 1.16340084e-08 | Not reached | 1,088.115 | 5.760 s |
| 21 | 77 | Yes | 6.22196209e-09 | Not reached | 1,949.885 | 4.311 s |
| 22 | 19 | Yes | 3.49961228e-09 | Not reached | 2,805.885 | 1.598 s |
| 23 | 55 | Yes | 6.252004e-09 | Not reached | 994.885 | 3.510 s |
| 24 | 26 | Yes | 2.51694324e-09 | Not reached | 1,005.885 | 1.761 s |
| 25 | 6 | Yes | 5.07664624e-09 | Not reached | 2,541.115 | 0.731 s |
| 26 | 29 | Yes | 5.14323012e-09 | Not reached | 2,453.115 | 1.912 s |
| 27 | 34 | Yes | 3.92981297e-09 | Not reached | 1,157.115 | 2.485 s |
| 28 | 9 | Yes | 4.96441731e-09 | Not reached | 2,539.885 | 0.884 s |
| 29 | 53 | Yes | 6.25732265e-09 | Not reached | 751.115 | 3.245 s |
| 30 | 40 | Yes | 4.18243818e-09 | Not reached | 3,902.885 | 2.702 s |
| 31 | 17 | Yes | 2.69341259e-09 | Not reached | 1,445.115 | 1.529 s |
| 32 | 36 | Yes | 2.94661688e-09 | Not reached | 3,628.115 | 2.129 s |
| 33 | 62 | Yes | 2.88789649e-09 | Not reached | 2,044.115 | 4.123 s |
| 34 | 23 | Yes | 1.04516261e-09 | Not reached | 1,917.885 | 1.687 s |
| 35 | 13 | Yes | 6.75015239e-10 | Not reached | 896.885 | 1.223 s |
| 36 | 58 | Yes | 1.18148061e-09 | Not reached | 1,284.885 | 3.580 s |
| 37 | 38 | Yes | 1.35412002e-09 | Not reached | 2,475.885 | 2.406 s |
| 38 | 23 | Yes | 1.37529342e-09 | Not reached | 2,360.885 | 1.829 s |
| 39 | 3 | Yes | 3.39304979e-10 | Not reached | 8,922.115 | 0.556 s |
| 40 | 43 | Yes | 1.69269381e-08 | Not reached | 2,003.115 | 2.682 s |
| 41 | 51 | Yes | 4.87291764e-09 | Not reached | 2,104.885 | 3.239 s |
| 42 | 36 | Yes | 1.44322649e-09 | Not reached | 2,194.115 | 2.542 s |
| 43 | 13 | Yes | 9.28742706e-10 | Not reached | 4,576.115 | 1.451 s |
| 44 | 51 | Yes | 5.29015221e-09 | Not reached | 1,993.885 | 3.198 s |
| 45 | 37 | Yes | 4.85001132e-09 | Not reached | 4,068.885 | 2.431 s |
| 46 | 12 | Yes | 2.11175757e-09 | Not reached | 3,758.885 | 1.246 s |
| 47 | 58 | Yes | 1.77412739e-09 | Not reached | 835.115 | 3.539 s |
| 48 | 20 | Yes | 5.36169765e-10 | Not reached | 862.115 | 1.448 s |
| 49 | 14 | Yes | 2.40105301e-10 | Not reached | 3,151.885 | 1.200 s |
| 50 | 17 | Yes | 3.09562344e-10 | Not reached | 1,854.885 | 1.412 s |
| 51 | 49 | Yes | 9.40144118e-10 | Not reached | 1,090.885 | 3.091 s |
| 52 | 48 | Yes | 6.45316726e-10 | Not reached | 919.115 | 3.035 s |
| 53 | 8 | Yes | 6.24900026e-11 | Not reached | 1,725.115 | 0.889 s |
| 54 | 46 | Yes | 6.92216563e-10 | Not reached | 1,251.115 | 2.922 s |
| 55 | 18 | Yes | 2.56700979e-10 | Not reached | 754.885 | 1.448 s |
| 56 | 7 | Yes | 4.54723771e-11 | Not reached | 1,384.885 | 0.794 s |
| 57 | 38 | Yes | 6.78517241e-10 | Not reached | 825.885 | 2.522 s |
| 58 | 11 | Yes | 1.08098967e-10 | Not reached | 1,178.115 | 0.994 s |
| 59 | 19 | Yes | 1.3834071e-10 | Not reached | 404.885 | 1.578 s |
| 60 | 29 | Yes | 1.83330387e-10 | Not reached | 910.115 | 2.298 s |
| 61 | 18 | Yes | 1.54216477e-10 | Not reached | 1,064.885 | 1.321 s |
| 62 | 8 | Yes | 5.24693792e-11 | Not reached | 1,289.115 | 0.891 s |
| 63 | 4 | Yes | 6.14965929e-11 | Not reached | 1,792.115 | 0.726 s |
| 64 | 24 | Yes | 6.96658396e-10 | Not reached | 1,979.885 | 1.539 s |
| 65 | 27 | Yes | 7.16681354e-10 | Not reached | 1,043.115 | 1.929 s |
| 66 | 37 | Yes | 5.36154851e-10 | Not reached | 750.885 | 2.495 s |
| 67 | 20 | Yes | 3.19946648e-10 | Not reached | 646.885 | 1.927 s |
| 68 | 16 | Yes | 1.48610874e-10 | Not reached | 1,098.885 | 1.452 s |
| 69 | 7 | Yes | 5.88366735e-11 | Not reached | 1,108.885 | 0.893 s |
| 70 | 31 | Yes | 4.11081103e-10 | Not reached | 1,636.115 | 2.076 s |
| 71 | 26 | Yes | 2.59724936e-10 | Not reached | 923.115 | 2.121 s |
| 72 | 38 | Yes | 5.84827485e-10 | Not reached | 1,002.115 | 2.503 s |
| 73 | 22 | Yes | 3.62966395e-10 | Not reached | 1,002.115 | 1.599 s |
| 74 | 19 | Yes | 1.96548262e-10 | Not reached | 903.885 | 1.575 s |
| 75 | 28 | Yes | 6.9396937e-10 | Not reached | 849.115 | 2.225 s |
| 76 | 1 | Yes | 3.2522986e-13 | Not reached | 1,419.115 | 0.464 s |
| 77 | 38 | Yes | 8.47244572e-10 | Not reached | 718.115 | 2.689 s |
| 78 | 19 | Yes | 5.08848632e-10 | Not reached | 1,534.885 | 1.532 s |
| 79 | 20 | Yes | 3.18219188e-10 | Not reached | 2,275.885 | 1.653 s |
| 80 | 13 | Yes | 3.08035309e-10 | Not reached | 1,511.115 | 1.218 s |
| 81 | 20 | Yes | 7.95470244e-10 | Not reached | 1,575.885 | 1.444 s |

The pass table shows intermediate point assignments, before connectivity repair and whole-block rebalancing.

On the originally failing pass 2, the new run continued for 51 iterations and 3.068 seconds beyond its own 300-iteration checkpoint. The normalized negative-dual objective decreased by 1.51345427298e-08; maximum population deviation changed from 30,956.884615 to 1,420.884615 people. These checkpoint values were observed in the new run; the preserved original attempt did not record that trajectory.

Final postprocessed maximum population deviation: **11.884615 people (0.001529608%)**. All 26 districts pass polygon-plus-recorded-link connectivity. Physical polygon components per district: `[1, 1, 1, 1, 1, 1, 1, 1, 1, 3, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1]`.

The outer loop reached the 80-iteration limit without center convergence. Successful inner optimizer passes do not establish outer convergence. Final population balance and connectivity are assessed separately after repair/rebalancing.

[Corrected district map](http://127.0.0.1:8770/corrections/new-york-inner-budget-v1/states/36/districts-26/)

[Interactive comparison and pass traces](http://127.0.0.1:8770/corrections/new-york-inner-budget-v1/)

Validation: 597 districting and script tests passed. Independent terminal process, fixed-code/settings, source DBF, trace arithmetic, final assignments, compressed maps, endpoint ownership and 1,083 preserved files verified. Browser checks passed for pass 2/3 charts, iteration/time axes, log/linear scales, national/state outlines, District 10 and both harbor links, and lazy county 061 detail (4,043 blocks). Both pages had no console warnings/errors. Benchmark processes exited and the state 36 lock was independently acquired/released.

- Normalized objective is the negative dual: lower is better. Positive gain is start objective minus current objective. Center updates change the objective; compare gains only within a balancing pass.
- The 300-iteration marker is a checkpoint in the new run, not a retroactively recorded baseline trajectory. Only pass 2 directly addresses the original failing pass; later passes have no prior-attempt counterpart.
- Population deviations use the fractional statewide ideal. Intermediate populations are reconstructed from already evaluated optimizer gradients; they are not a connected or accepted district plan.
- Whole blocks switch assignment in discrete jumps. Improving the dual objective does not require population imbalance to improve at every accepted step.
- Successful inner optimization, outer center convergence, final postprocessed population balance, and polygon-plus-link connectivity are separate outcomes.
- Both attempts ran serially on a shared desktop; timings include source preparation and, when reached, repair/export/validation. Instrumentation adds recorded overhead, so these are observational timings rather than isolated hardware benchmarks.
