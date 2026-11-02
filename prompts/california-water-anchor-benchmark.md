# California water-policy anchor benchmark

California K69/K83/K120 for House 574/692/1000 with the same recorded water policy and 1,000 inner iterations; K52 is an unchanged saved reference.

Outcome: **complete**. 104 historical files independently rehashed and unchanged.

| Districts | Final maximum deviation | Population range | Policy connected | Physically connected | Largest inner pass |
|---|---:|---:|---:|---:|---:|
| 52 (prior) | 37.558 people / 0.004940% | 760,335–760,388 | 52/52 | 49/52 | 390 |
| 69 | 49.275 people / 0.008599% | 572,995–573,067 | 69/69 | 66/69 | 385 |
| 83 | 32.867 people / 0.006900% | 476,337–476,397 | 83/83 | 80/83 | 486 |
| 120 | 30.808 people / 0.009350% | 329,461–329,516 | 120/120 | 117/120 | 862 |

| Districts | Pipeline min | Solver min | Export/validation min | Peak GiB |
|---|---:|---:|---:|---:|
| 52 | 37.91 | 14.82 | 18.63 | 2.197 |
| 69 | 67.10 | 41.83 | 18.15 | 2.543 |
| 83 | 70.52 | 46.55 | 18.34 | 2.534 |
| 120 | 79.73 | 54.54 | 17.89 | 2.583 |

Preparation: 1.690 s. Serial child processes: 217.53 min. Overall launcher elapsed time, including between-run validation: 217.73 min. [Execution record](http://127.0.0.1:8770/policies/california-water-anchors-v1/run.json). K52’s original runtime is not added to the new serial batch.

## House 435: 52 districts (saved reference)

[Validated map](http://127.0.0.1:8770/policies/california-water-v1/states/06/districts-52/). District 1: 5 physical pieces; District 6: 2 physical pieces; District 21: 2 physical pieces.
The outer loop reached the 80-iteration limit without center convergence. Successful inner optimizer passes do not establish outer convergence. Final population balance and connectivity are assessed separately after repair/rebalancing.

| Stage | Maximum deviation people | Maximum deviation % |
|---|---:|---:|
| initial | 1744.557692 | 0.229441268 |
| after repair | 2236.442308 | 0.294133097 |
| final | 37.557692 | 0.004939524 |

All 519,723 blocks and 39,538,223 residents are assigned once. 62 compressed map artifacts verified. Gzip bytes: national 195,486; state entry 1,000,798; connections 991; all county shards 226,123,882.

| Link | Endpoint districts | Used within district |
|---|---|---|
| ca-water-001 | 6 / 6 | 6 |
| ca-water-002 | 21 / 21 | 21 |
| ca-water-003 | 1 / 1 | 1 |
| ca-water-004 | 1 / 1 | 1 |
| ca-water-005 | 1 / 1 | 1 |
| ca-water-006 | 1 / 1 | 1 |

81 inner passes; 4,850 accepted iterations; all inner passes succeeded: True.

## House 574: 69 districts

[Validated map](http://127.0.0.1:8770/policies/california-water-anchors-v1/states/06/districts-69/). District 6: 2 physical pieces; District 12: 5 physical pieces; District 21: 2 physical pieces.
The outer loop reached the 80-iteration limit without center convergence. Successful inner optimizer passes do not establish outer convergence. Final population balance and connectivity are assessed separately after repair/rebalancing.

| Stage | Maximum deviation people | Maximum deviation % |
|---|---:|---:|
| initial | 3534.275362 | 0.616782904 |
| after repair | 3374.275362 | 0.588860557 |
| final | 49.275362 | 0.008599274 |

All 519,723 blocks and 39,538,223 residents are assigned once. 62 compressed map artifacts verified. Gzip bytes: national 252,213; state entry 1,282,470; connections 994; all county shards 226,171,219.

| Link | Endpoint districts | Used within district |
|---|---|---|
| ca-water-001 | 6 / 6 | 6 |
| ca-water-002 | 21 / 21 | 21 |
| ca-water-003 | 12 / 12 | 12 |
| ca-water-004 | 12 / 12 | 12 |
| ca-water-005 | 12 / 12 | 12 |
| ca-water-006 | 12 / 12 | 12 |

81 inner passes; 12,476 accepted iterations; all inner passes succeeded: True.

## House 692: 83 districts

[Validated map](http://127.0.0.1:8770/policies/california-water-anchors-v1/states/06/districts-83/). District 12: 5 physical pieces; District 46: 2 physical pieces; District 54: 2 physical pieces.
The outer loop reached the 80-iteration limit without center convergence. Successful inner optimizer passes do not establish outer convergence. Final population balance and connectivity are assessed separately after repair/rebalancing.

| Stage | Maximum deviation people | Maximum deviation % |
|---|---:|---:|
| initial | 1267.132530 | 0.266000827 |
| after repair | 1267.132530 | 0.266000827 |
| final | 32.867470 | 0.006899653 |

All 519,723 blocks and 39,538,223 residents are assigned once. 62 compressed map artifacts verified. Gzip bytes: national 251,315; state entry 1,301,343; connections 996; all county shards 226,198,692.

| Link | Endpoint districts | Used within district |
|---|---|---|
| ca-water-001 | 54 / 54 | 54 |
| ca-water-002 | 46 / 46 | 46 |
| ca-water-003 | 12 / 12 | 12 |
| ca-water-004 | 12 / 12 | 12 |
| ca-water-005 | 12 / 12 | 12 |
| ca-water-006 | 12 / 12 | 12 |

81 inner passes; 11,734 accepted iterations; all inner passes succeeded: True.

## House 1000: 120 districts

[Validated map](http://127.0.0.1:8770/policies/california-water-anchors-v1/states/06/districts-120/). District 46: 2 physical pieces; District 75: 2 physical pieces; District 106: 5 physical pieces.
The outer loop reached the 80-iteration limit without center convergence. Successful inner optimizer passes do not establish outer convergence. Final population balance and connectivity are assessed separately after repair/rebalancing.

| Stage | Maximum deviation people | Maximum deviation % |
|---|---:|---:|
| initial | 733.808333 | 0.222713600 |
| after repair | 1391.808333 | 0.422419085 |
| final | 30.808333 | 0.009350446 |

All 519,723 blocks and 39,538,223 residents are assigned once. 62 compressed map artifacts verified. Gzip bytes: national 290,112; state entry 1,502,757; connections 999; all county shards 226,275,986.

| Link | Endpoint districts | Used within district |
|---|---|---|
| ca-water-001 | 75 / 75 | 75 |
| ca-water-002 | 46 / 46 | 46 |
| ca-water-003 | 106 / 106 | 106 |
| ca-water-004 | 106 / 106 | 106 |
| ca-water-005 | 106 / 106 | 106 |
| ca-water-006 | 106 / 106 | 106 |

81 inner passes; 9,738 accepted iterations; all inner passes succeeded: True.

Validation: Prelaunch districting/scripts suite: 844 passed in 36.20s. Final summary-only suite: 77 passed in 0.38s, including recorded PID, state06 OS-lock and prelaunch metadata verification; prior test evidence retained. All child exit codes are zero. Browser QA loaded all three maps, displayed their six links, and verified K120 state detail and county003 lazy loading (202 blocks); no console errors observed in the checked map tabs. Screenshot evidence is saved in the anchor namespace.

[Saved prelaunch test evidence](http://127.0.0.1:8770/policies/california-water-anchors-v1/validation-tests.json): 844 tests passed; the checksum is retained in the comparison JSON.

[Summary validation evidence](http://127.0.0.1:8770/policies/california-water-anchors-v1/summary-validation-tests.json): 77 focused checks passed; the tested summary and test-source hashes are recorded.

- K52 was computed earlier and is reused without rerunning. The three new anchors run serially; preparation and child timing remain separate.
- The preserved strict source-topology exception did not solve any plan. These are not 300-versus-1000 iteration experiments.
- Successful inner solves, outer center convergence, population balance and connectivity under recorded water links are separate outcomes.
- Physical polygons remain unchanged. A water connection counts only when both endpoint blocks belong to the same district.
- All six links retain the K52 records. Distances span census-coverage boundaries, not shorelines or ferry routes; open-Pacific attribution is not a global high-resolution shoreline certificate.
- The 1% group/root preflight guides policy selection; it is not a final population-balance acceptance guarantee.
- Wall timings include tracing and desktop contention; gzip file sizes do not measure browser memory or network latency.
