# Alaska recorded-water benchmark

2020 census blocks, K1 for House 435/574 and K2 for House 692/1000; 49 explicit water links, continuous-longitude normalization, 1,000 inner and 80 outer iterations for K2.

Status: **complete**. All 28,568 source blocks and 733,391 residents are retained.

| Districts | House sizes | Result | Max population deviation | Physical components by district | Components with links |
|---:|---|---|---|---|---|
| [1-district map](http://127.0.0.1:8770/policies/alaska-water-v1/states/02/districts-1/maps/) | 435, 574 | Validated | 0.000 people (0.000000%) | 50 | 1 |
| [2-district map](http://127.0.0.1:8770/policies/alaska-water-v1/states/02/districts-2/maps/) | 692, 1000 | Validated | 0.500 people (0.000136%) | 2, 49 | 1, 1 |

| Districts | Pipeline seconds | Solver seconds | Direct assignment seconds | Export / validation seconds | Peak GiB |
|---:|---:|---:|---:|---:|---:|
| 1 | 268.616 | — | 0.131 | 181.272 | 0.861 |
| 2 | 268.540 | 0.491 | — | 180.856 | 0.670 |

## 1 districts

District populations: 733,391.
Every source block is assigned directly to the one district; optimization and center convergence are not applicable.
Map geometry: national 15,227 gzip bytes; state 46,807; full 122,100; connections 9,333. County detail: 53,140,682 bytes in total, 6,682,814 at most for one county. Initial map plus links: 24,560 compressed geometry bytes, plus 17,400 HTML and 63,853 manifest bytes.
All 68 compressed payloads, every source block, full district coverage, link ownership, and wrapped seam reconstruction independently verified.

## 2 districts

District populations: 366,695, 366,696.
The outer loop met its center-convergence tolerance after 5 iterations. Successful inner optimizer passes do not establish outer convergence. Final population balance and connectivity are assessed separately after repair/rebalancing.
All 6 inner solves succeeded; maximum 10 iterations against the 1,000-iteration cap.
Map geometry: national 21,200 gzip bytes; state 94,176; full 680,201; connections 9,340. County detail: 53,146,723 bytes in total, 6,684,256 at most for one county. Initial map plus links: 30,540 compressed geometry bytes, plus 17,400 HTML and 64,889 manifest bytes.
All 68 compressed payloads, every source block, full district coverage, link ownership, and wrapped seam reconstruction independently verified.

Serial parent elapsed time: 540.495s. Independent summary validation: 651.552s; this is not added to the measured plan runtime.

31 historical files rehashed unchanged. Prelaunch tests: 1347 passed. Summary-only tests: 43 passed.

Independently reloaded original source DBF and normalized polygon parts; verified assignments, replayed moves, induced graph connectivity, full polygon coverage, same-district water-link ownership, every compressed district/county artifact and saved seam reconstruction. Original evidence and frozen runtime hashes unchanged; summary-only tests recorded separately. Browser checks are recorded separately in qa/browser-qa.json. The first summary attempt passed the expensive plan checks but stopped at a reporting-only shared-preflight lookup assumption; its evidence is preserved under summary-history/attempt-1. This corrected full audit is not a benchmark retry. Separate summary audit timings are recorded in summary-validation-history.json.

Limits:

- K1 is a direct assignment of every block; it has no solver runtime or convergence result.
- The strict batch ran K1 preflight and reused its antimeridian rejection for unstarted K2; no solver ran and there is no solved strict-plan baseline.
- Physical shared-edge connectivity is separate from connectivity through same-district recorded links.
- Regional ocean evidence and Alaska source-interior checks do not certify a global land mask, foreign-land clearance or navigability.
- All source polygons and populations are preserved. Seam cuts affect displayed longitude representation, not physical graph connectivity.
- Original NAD83 source coordinates are retained; no WGS84 datum conversion or strict RFC7946 claim.
- The existing population-centered equirectangular solver distance model is approximate across Alaska.
- Pipeline timings include source reading, repeated graph/policy verification and map export; trace observation overhead is included. Independent summary time is separate.
- K2 inner optimizer success, outer center convergence and final whole-block population balance are separate findings.

[Local comparison](http://127.0.0.1:8770/policies/alaska-water-v1/) · [Machine-readable comparison](http://127.0.0.1:8770/policies/alaska-water-v1/comparison.json)
