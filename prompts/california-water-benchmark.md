# California: recorded-water K52 pilot

California K52 / House 435 first actual census-block solve with population-aware recorded water links and 1000 inner iterations.

Outcome: **complete_under_island_water_policy**. 20 historical files remain byte-identical.

| Metric | Preserved strict preflight | New water-policy pilot |
|---|---:|---:|
| Pipeline runtime | 3.20 min (192.043 s) | 37.91 min (2274.550 s) |
| Solver runtime | Not run | 14.82 min (889.398 s) |
| Repair and rebalancing | Not run | 1.04 min (62.189 s) |
| Polygon validation and map export | Not run | 18.63 min (1118.030 s) |
| Peak process memory | 1.377 GiB | 2.197 GiB |
| Maximum final deviation | No plan | 37.557692 people / 0.004939524% |

The earlier result stopped at a disconnected source graph. It did not test a 300-iteration solve or produce final districts.

All 52 districts pass the part graph and independent unsimplified polygon-plus-link audits. District 1: 5 pieces; District 6: 2 pieces; District 21: 2 pieces.
All 519,723 source blocks and 39,538,223 residents are retained. The remaining 49 districts are physically connected.

| Recorded connection | Distance | Endpoint districts | Used within district |
|---|---:|---|---|
| Mainland California ↔ Northern Channel Islands | 7.701 km | 6 / 6 | 6 |
| Mainland California ↔ Farallon Islands | 14.541 km | 21 / 21 | 21 |
| Mainland California ↔ Santa Catalina Island | 20.193 km | 1 / 1 | 1 |
| Santa Catalina Island ↔ San Clemente Island | 22.835 km | 1 / 1 | 1 |
| Santa Catalina Island ↔ Santa Barbara Island | 27.317 km | 1 / 1 | 1 |
| San Nicolas Island ↔ Santa Barbara Island | 31.783 km | 1 / 1 | 1 |

The outer loop reached the 80-iteration limit without center convergence. Successful inner optimizer passes do not establish outer convergence. Final population balance and connectivity are assessed separately after repair/rebalancing.

[Validated map](http://127.0.0.1:8770/policies/california-water-v1/states/06/districts-52/) · [Comparison and traces](http://127.0.0.1:8770/policies/california-water-v1/)

| Population stage | Maximum deviation |
|---|---:|
| initial | 1744.557692 people / 0.229441268% |
| after repair | 2236.442308 people / 0.294133097% |
| final | 37.557692 people / 0.004939524% |

Compressed map payload: national outlines 195,486 bytes; state entry outlines + detail index 1,000,798 bytes; link overlay 991 bytes. All county detail shards total 226,123,882 bytes and load individually on request. The largest county shard (county FIPS 037) is 16,941,018 compressed bytes.

Observed 81 balancing passes, 4,850 accepted iterations; the largest pass used **390 / 1,000**. Tracing bookkeeping/I/O overhead: 1.985 s.

Validation: 715 prelaunch districting/script tests and 18 focused summary checks passed. Terminal evidence, source DBF, trace arithmetic, map hashes, endpoint ownership, and preservation were independently verified. Browser QA confirmed all 52 district totals, six links, physical exceptions, national/state/exact outlines, Channel Islands and Farallons views, individual-link inspection, hide/show, explicit San Francisco county loading and clearing with no initial block detail, and both pass-2 charts (390 iterations / 407 evaluations). Map and comparison console warning/error logs were empty; validated-channel-islands.png preserves the rendered regional view.

[Saved prelaunch test record](http://127.0.0.1:8770/policies/california-water-v1/validation-tests.json): 715 tests passed before launch; the record checksum is retained in the comparison JSON.

- The original run stopped before optimization. This is not a controlled 300-versus-1000 iteration experiment or a completed-plan speed comparison.
- A successful inner optimizer, outer center convergence, final population balance, physical connectivity and recorded-link connectivity are distinct outcomes.
- The 1% root/group population budget selects links; it is not final district-balance acceptance.
- Connections preserve source polygons and populations. Open-Pacific attribution uses source-component clearance and official regional geography, not a global high-resolution shoreline certificate.
- Objective changes are meaningful within each pass only; intermediate trace populations are point assignments before connectivity repair.
- Pilot timings are from a shared desktop and include observational tracing. The original preflight built the historical block graph; the pilot uses a part graph and new policy.
- Map byte counts describe gzip artifacts, not browser memory or network latency. County detail loads only on request.
