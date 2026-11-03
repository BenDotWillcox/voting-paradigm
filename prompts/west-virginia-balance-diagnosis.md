# West Virginia: diagnosing the population-balance outlier

The original three-district plan is a valid, strictly connected map, but its population balancing stopped at the 1,000-move budget. The initial numerical solve was already well balanced. Connectivity repair, followed by incomplete boundary rebalancing, explains the final 2.25359% deviation.

[Interactive stage maps and measured trace](http://127.0.0.1:8770/diagnostics/west-virginia/) · [Original connected map](http://127.0.0.1:8770/states/54/districts-3/) · [Diagnostic evidence](http://127.0.0.1:8770/diagnostics/west-virginia/diagnosis.json)

| Districts / House | Maximum deviation | Pipeline | Peak memory | Balancing stop |
|---|---:|---:|---:|---|
| 2 / 435 | 0.000 people (0.000000%) | 4.13 min | 615.6 MiB | 1 moves; local_optimum |
| 3 / 574 | 13,474.333 people (2.253590%) | 29.96 min | 590.5 MiB | 1,000 moves; max_moves |
| 4 / 692 | 0.000 people (0.000000%) | 3.24 min | 530.4 MiB | 4 moves; local_optimum |
| 5 / 1000 | 1.200 people (0.000335%) | 3.29 min | 522.2 MiB | 12 moves; local_optimum |

All four original plans retain 72,558 whole census blocks and 1,793,716 residents. Each passes the saved independent strict unsimplified polygon audit. The source is connected and has no multipart blocks; no water links are involved.

| Three-district stage | Populations | Maximum deviation | Graph components | Independent polygon audit |
|---|---|---:|---|---|
| Initial numerical assignment | 597,906 / 597,900 / 597,910 | 5.333 people (0.000892%) | [5, 10, 9] | Not strict-valid (diagnostic stage); [5, 10, 9] components |
| After connectivity repair | 597,919 / 544,030 / 651,767 | 53,875.333 people (9.010680%) | [1, 1, 1] | Strict validation passed; [1, 1, 1] components |
| Original final (1,000 moves) | 597,919 / 584,431 / 611,366 | 13,474.333 people (2.253590%) | [1, 1, 1] | Strict validation passed; [1, 1, 1] components |
| Diagnostic continuation | 597,919 / 586,313 / 609,484 | 11,592.333 people (1.938824%) | [1, 1, 1] | Strict validation passed; [1, 1, 1] components |

Initial numerical assignment: The diagnostic fast coverage dissolve was invalid for display district(s) 3; the independent audit uses robust unary union of unchanged source polygons.

The largest repair moves 1,753 Northern Panhandle blocks and 53,789 residents from display District 2 to District 3. That restores connectivity but creates the large imbalance. All 1,000 original balancing moves transfer population back from District 3 to District 2; the last 100 moves still transfer 1,893 residents. Stopping at the budget does not establish a local or global optimum.

The original solve took 3.963 seconds, with successful inner passes and converged centers. Connectivity repair plus rebalancing took 1598.964 seconds; validation/export took 191.141 seconds. The next step is faster exact donor-connectivity checks, followed by a larger-budget continuation of the saved connected assignment. Increasing the inner optimizer budget would target the wrong stage.

The diagnostic continuation made **100 additional moves** in 244.189 seconds, reaching **11,592.333 people (1.938824%)** maximum deviation. Its stop reason is `max_moves`. This is bounded diagnostic evidence, not an accepted corrected plan or a guarantee that a larger budget alone will finish balancing. A longer correction run would need its own preserved output and full validation before acceptance.

The probe itself passed its independent unsimplified polygon audit. Its donor-connectivity guard ran 21,785 times, rejected 21,684 candidates, and consumed 242.775 seconds. These observational measurements describe the continuation; they do not change stopping rules or the numerical objective.

Donor-connectivity checks account for **99.42% of probe wall time**. The candidate performance fix is a per-district articulation-point cache, invalidated for both donor and recipient after every transfer, with regression checks that preserve exact candidate order and move traces. This has not been implemented or timed here. After validating that optimization, a longer continuation can test whether more boundary moves achieve acceptable balance; eventual success is not guaranteed.

The chart uses saved/replayed moves and the measured continuation. Maximum absolute deviation is the primary objective; the sum of squared population deviations breaks ties as the secondary objective in the lexicographic rule. Display geometry is simplified for inspection and is not a topology certificate.

Historical runtime hashes differ from current solver/connectivity/export code. A fresh solve with current code would therefore not isolate a budget change. This diagnosis preserves the original solve and records the continuation code separately. Historical two-worker timings and the diagnostic continuation are not isolated performance benchmarks.

The original K2 report records one unsuccessful inner pass under the earlier permissive optimizer handling (status 2, ABNORMAL, after 11 iterations and 107 evaluations); its subsequent six passes converged. Its final balance is exact and geometry validation passed. K3 records no unsuccessful inner passes. That legacy numerical warning is separate from this K3 postprocessing issue.

Original source archive SHA-256: `04e931a5d288ed62da3b947239f3f23f8b6a8d8b4a749ec749eb90158b50f863`. Original assignments, move audits, maps and benchmark reports remain the historical evidence; preservation and continuation provenance are recorded in the diagnostic JSON.

The first diagnostic audit stopped on the initial, pre-repair assignment after the fast coverage dissolve failed its validation. That attempt and its log are preserved. A geometry-only finalization audited the saved assignments with robust unary union and retained the fast-dissolve evidence; the balancing probe was not repeated. Finalization time is separate from the measured continuation.
