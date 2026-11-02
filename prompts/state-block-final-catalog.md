# Final 50-state census-block plan catalog

**All four anchors are covered: 200/200 state–House combinations; 181/181 distinct plans.**

Scope: 50 states, 2020 Census blocks, House sizes **435 / 574 / 692 / 1,000**. District counts are independently reconciled with exact rational Huntington–Hill priorities. Apportionment uses apportionment population; district balance uses resident population.

[Interactive inventory](http://127.0.0.1:8770/final-anchors-v1/) · [Machine-readable catalog](state-block-final-catalog.json)

| House | States | Districts | Worst deviation | Largest deviation (people) | National outlines gzip |
|---:|---:|---:|---:|---:|---:|
| 435 | 50/50 | 435 | 0.005335% | 41.036 | 1.84 MiB |
| 574 | 50/50 | 574 | 0.009262% | 53.457 | 2.20 MiB |
| 692 | 50/50 | 692 | 0.012450% | 59.881 | 2.38 MiB |
| 1000 | 50/50 | 1000 | 0.012155% | 40.277 | 2.88 MiB |

## What validation establishes

Accepted final assignments cover every source block exactly once, with reconciled resident totals and nonempty districts. Full map polygons and connectivity are checked separately from simplified display outlines. Recorded water/exclave connections remain explicit; they do not turn separate polygons into physical shared edges. See each plan’s validation record for independent checks and retained historical audit evidence.

158 plans use strict shared-edge connectivity; 23 use recorded geographic connections. Alaska retains its documented longitude normalization and display seam handling.

Population balance is measured, not inferred from solver status. No new tolerance or global-optimality claim is imposed by this catalog. Whole blocks, zero-population blocks and water blocks remain included.

18 selected historical plans contain at least one unsuccessful legacy inner pass; 107 report an outer iteration cap. These flags remain in the catalog. They do not replace the independent final-map acceptance checks, and these runs must not be described as uniformly converged.

## State inventory

Each cell gives district count / maximum absolute population deviation in people. Equal state seat counts reuse the same accepted plan.

| State | House 435 | House 574 | House 692 | House 1,000 | Connectivity |
|---|---|---|---|---|---|
| Alabama | [7 / 1.857](http://127.0.0.1:8770/states/01/districts-7/) | [9 / 1.222](http://127.0.0.1:8770/states/01/districts-9/) | [11 / 1.636](http://127.0.0.1:8770/states/01/districts-11/) | [15 / 3.067](http://127.0.0.1:8770/states/01/districts-15/) | Shared edges |
| Alaska | [1 / 0.000](http://127.0.0.1:8770/policies/alaska-water-v1/states/02/districts-1/) | [1 / 0.000](http://127.0.0.1:8770/policies/alaska-water-v1/states/02/districts-1/) | [2 / 0.500](http://127.0.0.1:8770/policies/alaska-water-v1/states/02/districts-2/) | [2 / 0.500](http://127.0.0.1:8770/policies/alaska-water-v1/states/02/districts-2/) | Recorded connections |
| Arizona | [9 / 2.667](http://127.0.0.1:8770/states/04/districts-9/) | [12 / 2.500](http://127.0.0.1:8770/states/04/districts-12/) | [15 / 11.200](http://127.0.0.1:8770/states/04/districts-15/) | [22 / 4.727](http://127.0.0.1:8770/states/04/districts-22/) | Shared edges |
| Arkansas | [4 / 0.000](http://127.0.0.1:8770/states/05/districts-4/) | [5 / 1.200](http://127.0.0.1:8770/states/05/districts-5/) | [6 / 0.667](http://127.0.0.1:8770/states/05/districts-6/) | [9 / 4.222](http://127.0.0.1:8770/states/05/districts-9/) | Shared edges |
| California | [52 / 37.558](http://127.0.0.1:8770/policies/california-water-v1/states/06/districts-52/) | [69 / 49.275](http://127.0.0.1:8770/policies/california-water-anchors-v1/states/06/districts-69/) | [83 / 32.867](http://127.0.0.1:8770/policies/california-water-anchors-v1/states/06/districts-83/) | [120 / 30.808](http://127.0.0.1:8770/policies/california-water-anchors-v1/states/06/districts-120/) | Recorded connections |
| Colorado | [8 / 0.750](http://127.0.0.1:8770/states/08/districts-8/) | [10 / 1.600](http://127.0.0.1:8770/states/08/districts-10/) | [12 / 3.833](http://127.0.0.1:8770/states/08/districts-12/) | [17 / 3.235](http://127.0.0.1:8770/states/08/districts-17/) | Shared edges |
| Connecticut | [5 / 2.800](http://127.0.0.1:8770/states/09/districts-5/) | [6 / 3.667](http://127.0.0.1:8770/states/09/districts-6/) | [8 / 3.000](http://127.0.0.1:8770/states/09/districts-8/) | [11 / 5.091](http://127.0.0.1:8770/states/09/districts-11/) | Shared edges |
| Delaware | [1 / 0.000](http://127.0.0.1:8770/states/10/districts-1/) | [2 / 1.000](http://127.0.0.1:8770/states/10/districts-2/) | [2 / 1.000](http://127.0.0.1:8770/states/10/districts-2/) | [3 / 0.667](http://127.0.0.1:8770/states/10/districts-3/) | Shared edges |
| Florida | [28 / 41.036](http://127.0.0.1:8770/policies/florida-water-v1/states/12/districts-28/) | [37 / 16.162](http://127.0.0.1:8770/policies/florida-water-v1/states/12/districts-37/) | [45 / 44.622](http://127.0.0.1:8770/policies/florida-water-v1/states/12/districts-45/) | [65 / 40.277](http://127.0.0.1:8770/policies/florida-water-v1/states/12/districts-65/) | Recorded connections |
| Georgia | [14 / 3.286](http://127.0.0.1:8770/states/13/districts-14/) | [19 / 3.632](http://127.0.0.1:8770/states/13/districts-19/) | [22 / 3.091](http://127.0.0.1:8770/states/13/districts-22/) | [32 / 17.875](http://127.0.0.1:8770/states/13/districts-32/) | Shared edges |
| Hawaii | [2 / 14.500](http://127.0.0.1:8770/corrections/hawaii-optimizer-v1/states/15/districts-2/) | [3 / 2.667](http://127.0.0.1:8770/corrections/hawaii-optimizer-v1/states/15/districts-3/) | [3 / 2.667](http://127.0.0.1:8770/corrections/hawaii-optimizer-v1/states/15/districts-3/) | [4 / 10.750](http://127.0.0.1:8770/corrections/hawaii-optimizer-v1/states/15/districts-4/) | Recorded connections |
| Idaho | [2 / 0.000](http://127.0.0.1:8770/states/16/districts-2/) | [3 / 0.667](http://127.0.0.1:8770/states/16/districts-3/) | [4 / 1.500](http://127.0.0.1:8770/states/16/districts-4/) | [6 / 1.667](http://127.0.0.1:8770/states/16/districts-6/) | Shared edges |
| Illinois | [17 / 4.059](http://127.0.0.1:8770/states/17/districts-17/) | [22 / 8.273](http://127.0.0.1:8770/states/17/districts-22/) | [27 / 6.667](http://127.0.0.1:8770/states/17/districts-27/) | [39 / 7.154](http://127.0.0.1:8770/states/17/districts-39/) | Shared edges |
| Indiana | [9 / 1.556](http://127.0.0.1:8770/states/18/districts-9/) | [12 / 2.333](http://127.0.0.1:8770/states/18/districts-12/) | [14 / 2.571](http://127.0.0.1:8770/states/18/districts-14/) | [21 / 5.619](http://127.0.0.1:8770/states/18/districts-21/) | Shared edges |
| Iowa | [4 / 0.750](http://127.0.0.1:8770/states/19/districts-4/) | [6 / 0.833](http://127.0.0.1:8770/states/19/districts-6/) | [7 / 1.000](http://127.0.0.1:8770/states/19/districts-7/) | [10 / 1.100](http://127.0.0.1:8770/states/19/districts-10/) | Shared edges |
| Kansas | [4 / 0.000](http://127.0.0.1:8769/house-435/) | [5 / 0.000](http://127.0.0.1:8769/house-574/) | [6 / 0.667](http://127.0.0.1:8769/house-692/) | [9 / 1.111](http://127.0.0.1:8769/house-1000/) | Shared edges |
| Kentucky | [6 / 1.667](http://127.0.0.1:8770/policies/kentucky-exclave-v1/states/21/districts-6/) | [8 / 3.500](http://127.0.0.1:8770/policies/kentucky-exclave-v1/states/21/districts-8/) | [9 / 1.556](http://127.0.0.1:8770/policies/kentucky-exclave-v1/states/21/districts-9/) | [14 / 3.571](http://127.0.0.1:8770/policies/kentucky-exclave-v1/states/21/districts-14/) | Recorded connections |
| Louisiana | [6 / 1.167](http://127.0.0.1:8770/states/22/districts-6/) | [8 / 2.625](http://127.0.0.1:8770/states/22/districts-8/) | [10 / 4.700](http://127.0.0.1:8770/states/22/districts-10/) | [14 / 8.929](http://127.0.0.1:8770/states/22/districts-14/) | Shared edges |
| Maine | [2 / 0.500](http://127.0.0.1:8770/states/23/districts-2/) | [2 / 0.500](http://127.0.0.1:8770/states/23/districts-2/) | [3 / 0.667](http://127.0.0.1:8770/states/23/districts-3/) | [4 / 2.250](http://127.0.0.1:8770/states/23/districts-4/) | Shared edges |
| Maryland | [8 / 2.000](http://127.0.0.1:8770/states/24/districts-8/) | [11 / 9.182](http://127.0.0.1:8770/states/24/districts-11/) | [13 / 7.923](http://127.0.0.1:8770/states/24/districts-13/) | [19 / 20.947](http://127.0.0.1:8770/corrections/part-connectivity-v1/states/24/districts-19/) | Shared edges |
| Massachusetts | [9 / 3.111](http://127.0.0.1:8770/states/25/districts-9/) | [12 / 9.583](http://127.0.0.1:8770/states/25/districts-12/) | [15 / 4.867](http://127.0.0.1:8770/states/25/districts-15/) | [21 / 10.048](http://127.0.0.1:8770/states/25/districts-21/) | Shared edges |
| Michigan | [13 / 1.692](http://127.0.0.1:8770/states/26/districts-13/) | [18 / 7.722](http://127.0.0.1:8770/states/26/districts-18/) | [21 / 5.095](http://127.0.0.1:8770/states/26/districts-21/) | [30 / 4.033](http://127.0.0.1:8770/states/26/districts-30/) | Shared edges |
| Minnesota | [8 / 1.250](http://127.0.0.1:8770/states/27/districts-8/) | [10 / 3.400](http://127.0.0.1:8770/states/27/districts-10/) | [12 / 1.833](http://127.0.0.1:8770/states/27/districts-12/) | [17 / 2.882](http://127.0.0.1:8770/states/27/districts-17/) | Shared edges |
| Mississippi | [4 / 1.250](http://127.0.0.1:8770/states/28/districts-4/) | [5 / 1.200](http://127.0.0.1:8770/states/28/districts-5/) | [6 / 1.500](http://127.0.0.1:8770/states/28/districts-6/) | [9 / 1.000](http://127.0.0.1:8770/states/28/districts-9/) | Shared edges |
| Missouri | [8 / 2.875](http://127.0.0.1:8770/states/29/districts-8/) | [11 / 4.545](http://127.0.0.1:8770/states/29/districts-11/) | [13 / 3.846](http://127.0.0.1:8770/states/29/districts-13/) | [19 / 6.211](http://127.0.0.1:8770/states/29/districts-19/) | Shared edges |
| Montana | [2 / 0.500](http://127.0.0.1:8770/states/30/districts-2/) | [2 / 0.500](http://127.0.0.1:8770/states/30/districts-2/) | [2 / 0.500](http://127.0.0.1:8770/states/30/districts-2/) | [3 / 0.667](http://127.0.0.1:8770/states/30/districts-3/) | Shared edges |
| Nebraska | [3 / 0.667](http://127.0.0.1:8770/states/31/districts-3/) | [3 / 0.667](http://127.0.0.1:8770/states/31/districts-3/) | [4 / 1.000](http://127.0.0.1:8770/states/31/districts-4/) | [6 / 1.333](http://127.0.0.1:8770/states/31/districts-6/) | Shared edges |
| Nevada | [4 / 2.500](http://127.0.0.1:8770/states/32/districts-4/) | [5 / 7.200](http://127.0.0.1:8770/states/32/districts-5/) | [7 / 4.286](http://127.0.0.1:8770/states/32/districts-7/) | [9 / 2.889](http://127.0.0.1:8770/states/32/districts-9/) | Shared edges |
| New Hampshire | [2 / 0.500](http://127.0.0.1:8770/states/33/districts-2/) | [2 / 0.500](http://127.0.0.1:8770/states/33/districts-2/) | [3 / 0.667](http://127.0.0.1:8770/states/33/districts-3/) | [4 / 3.250](http://127.0.0.1:8770/states/33/districts-4/) | Shared edges |
| New Jersey | [12 / 2.833](http://127.0.0.1:8770/states/34/districts-12/) | [16 / 9.125](http://127.0.0.1:8770/states/34/districts-16/) | [19 / 17.421](http://127.0.0.1:8770/states/34/districts-19/) | [28 / 20.214](http://127.0.0.1:8770/states/34/districts-28/) | Shared edges |
| New Mexico | [3 / 0.667](http://127.0.0.1:8770/states/35/districts-3/) | [4 / 0.500](http://127.0.0.1:8770/states/35/districts-4/) | [4 / 0.500](http://127.0.0.1:8770/states/35/districts-4/) | [6 / 0.667](http://127.0.0.1:8770/states/35/districts-6/) | Shared edges |
| New York | [26 / 11.885](http://127.0.0.1:8770/corrections/new-york-inner-budget-v1/states/36/districts-26/) | [35 / 53.457](http://127.0.0.1:8770/corrections/new-york-inner-budget-anchors-v1/states/36/districts-35/) | [42 / 59.881](http://127.0.0.1:8770/corrections/new-york-inner-budget-anchors-v1/states/36/districts-42/) | [61 / 34.984](http://127.0.0.1:8770/corrections/new-york-inner-budget-anchors-v1/states/36/districts-61/) | Recorded connections |
| North Carolina | [14 / 5.571](http://127.0.0.1:8770/states/37/districts-14/) | [18 / 6.000](http://127.0.0.1:8770/states/37/districts-18/) | [22 / 6.636](http://127.0.0.1:8770/states/37/districts-22/) | [32 / 13.875](http://127.0.0.1:8770/states/37/districts-32/) | Shared edges |
| North Dakota | [1 / 0.000](http://127.0.0.1:8770/states/38/districts-1/) | [1 / 0.000](http://127.0.0.1:8770/states/38/districts-1/) | [2 / 0.000](http://127.0.0.1:8770/states/38/districts-2/) | [2 / 0.000](http://127.0.0.1:8770/states/38/districts-2/) | Shared edges |
| Ohio | [15 / 1.133](http://127.0.0.1:8770/states/39/districts-15/) | [20 / 4.400](http://127.0.0.1:8770/states/39/districts-20/) | [25 / 5.080](http://127.0.0.1:8770/states/39/districts-25/) | [36 / 7.556](http://127.0.0.1:8770/states/39/districts-36/) | Shared edges |
| Oklahoma | [5 / 0.600](http://127.0.0.1:8770/states/40/districts-5/) | [7 / 0.857](http://127.0.0.1:8770/states/40/districts-7/) | [8 / 1.125](http://127.0.0.1:8770/states/40/districts-8/) | [12 / 1.083](http://127.0.0.1:8770/states/40/districts-12/) | Shared edges |
| Oregon | [6 / 1.667](http://127.0.0.1:8770/states/41/districts-6/) | [7 / 1.714](http://127.0.0.1:8770/states/41/districts-7/) | [9 / 2.222](http://127.0.0.1:8770/states/41/districts-9/) | [13 / 5.769](http://127.0.0.1:8770/states/41/districts-13/) | Shared edges |
| Pennsylvania | [17 / 4.706](http://127.0.0.1:8770/states/42/districts-17/) | [23 / 13.783](http://127.0.0.1:8770/states/42/districts-23/) | [27 / 5.481](http://127.0.0.1:8770/states/42/districts-27/) | [39 / 9.436](http://127.0.0.1:8770/states/42/districts-39/) | Shared edges |
| Rhode Island | [2 / 0.500](http://127.0.0.1:8770/policies/island-water-v1/states/44/districts-2/) | [2 / 0.500](http://127.0.0.1:8770/policies/island-water-v1/states/44/districts-2/) | [2 / 0.500](http://127.0.0.1:8770/policies/island-water-v1/states/44/districts-2/) | [3 / 1.000](http://127.0.0.1:8770/policies/island-water-v1/states/44/districts-3/) | Recorded connections |
| South Carolina | [7 / 1.571](http://127.0.0.1:8770/states/45/districts-7/) | [9 / 2.111](http://127.0.0.1:8770/states/45/districts-9/) | [11 / 3.636](http://127.0.0.1:8770/states/45/districts-11/) | [16 / 5.562](http://127.0.0.1:8770/states/45/districts-16/) | Shared edges |
| South Dakota | [1 / 0.000](http://127.0.0.1:8770/states/46/districts-1/) | [2 / 0.500](http://127.0.0.1:8770/states/46/districts-2/) | [2 / 0.500](http://127.0.0.1:8770/states/46/districts-2/) | [3 / 0.667](http://127.0.0.1:8770/states/46/districts-3/) | Shared edges |
| Tennessee | [9 / 5.111](http://127.0.0.1:8770/states/47/districts-9/) | [12 / 4.667](http://127.0.0.1:8770/states/47/districts-12/) | [14 / 11.571](http://127.0.0.1:8770/states/47/districts-14/) | [21 / 3.619](http://127.0.0.1:8770/states/47/districts-21/) | Shared edges |
| Texas | [38 / 9.974](http://127.0.0.1:8770/states/48/districts-38/) | [51 / 8.490](http://127.0.0.1:8770/states/48/districts-51/) | [61 / 11.836](http://127.0.0.1:8770/states/48/districts-61/) | [88 / 15.080](http://127.0.0.1:8770/states/48/districts-88/) | Shared edges |
| Utah | [4 / 1.000](http://127.0.0.1:8770/states/49/districts-4/) | [6 / 5.333](http://127.0.0.1:8770/states/49/districts-6/) | [7 / 5.286](http://127.0.0.1:8770/states/49/districts-7/) | [10 / 2.600](http://127.0.0.1:8770/states/49/districts-10/) | Shared edges |
| Vermont | [1 / 0.000](http://127.0.0.1:8770/states/50/districts-1/) | [1 / 0.000](http://127.0.0.1:8770/states/50/districts-1/) | [1 / 0.000](http://127.0.0.1:8770/states/50/districts-1/) | [2 / 0.500](http://127.0.0.1:8770/states/50/districts-2/) | Shared edges |
| Virginia | [11 / 7.909](http://127.0.0.1:8770/states/51/districts-11/) | [15 / 17.200](http://127.0.0.1:8770/states/51/districts-15/) | [18 / 17.167](http://127.0.0.1:8770/states/51/districts-18/) | [26 / 17.346](http://127.0.0.1:8770/corrections/part-connectivity-v1/states/51/districts-26/) | Shared edges |
| Washington | [10 / 4.100](http://127.0.0.1:8770/states/53/districts-10/) | [13 / 2.077](http://127.0.0.1:8770/states/53/districts-13/) | [16 / 6.938](http://127.0.0.1:8770/states/53/districts-16/) | [23 / 3.783](http://127.0.0.1:8770/states/53/districts-23/) | Shared edges |
| West Virginia | [2 / 0.000](http://127.0.0.1:8770/states/54/districts-2/) | [3 / 0.667](http://127.0.0.1:8770/corrections/west-virginia-cached-balance-v1/states/54/districts-3/) | [4 / 0.000](http://127.0.0.1:8770/states/54/districts-4/) | [5 / 1.200](http://127.0.0.1:8770/states/54/districts-5/) | Shared edges |
| Wisconsin | [8 / 2.250](http://127.0.0.1:8770/states/55/districts-8/) | [10 / 1.200](http://127.0.0.1:8770/states/55/districts-10/) | [12 / 4.833](http://127.0.0.1:8770/states/55/districts-12/) | [18 / 9.222](http://127.0.0.1:8770/states/55/districts-18/) | Shared edges |
| Wyoming | [1 / 0.000](http://127.0.0.1:8770/states/56/districts-1/) | [1 / 0.000](http://127.0.0.1:8770/states/56/districts-1/) | [1 / 0.000](http://127.0.0.1:8770/states/56/districts-1/) | [2 / 0.500](http://127.0.0.1:8770/states/56/districts-2/) | Shared edges |

## Runtime, memory and verification cost

The 178 full-pipeline records have a median of 6.75 minutes. The slowest is Texas K88 at 156.19 minutes. The largest recorded process peak is 2.583 GiB for California K120. 3 selected corrections have separately scoped timings that exclude their original solve. These historical measurements span concurrent and serial execution and different code versions; they are not controlled speed comparisons.

This read-only audit verified 12,793 compressed payloads (13.62 GiB across distinct saved plans, including repeated geography). It did not generate or repair any districts. Its runtime is separate from the benchmark measurements.

## Integration boundary

- This catalog selects existing immutable results; it does not modify the demo or overwrite historical failures.
- The four anchors are ready only when all validation records pass. Intermediate slider values and House 11,037 are outside this catalog.
- Integration must preserve recorded links, Alaska seam handling, population/solver status, source provenance and the selected correction versions.
- The current app uses tract summary/topology files and its state page selects the 435-seat plan. It needs a deliberate block-plan adapter, anchor selection and truthful convergence labels; this catalog is not a drop-in replacement for that schema.
- Load national district outlines first, state outlines on selection, and county block detail on demand. Outline totals exclude links, manifests, application code and other request overhead.
- Runtime measurements span older two-worker runs and later serial runs, several numerical versions, and correction-only pipelines. They are observations, not controlled comparisons or a new nationwide runtime.
- No new solve, repair, export or connectivity-policy change was performed for this audit.

## Verification provenance

Audit generated 2026-10-26T20:19:25.442712+00:00; elapsed 614.6 seconds. The JSON records explicit selection reasons, original report hashes, apportionment, accepted audit checks and any failures. The detailed validation checkpoints are in `.cache/state-block-benchmark/suite-through-1000/final-anchors-v1/validation/`.

Final review: **82 regression tests passed** in 2.19 seconds. All 181 selected map URLs returned HTML successfully. The browser checks cover all four anchors, policy filters, corrected-map selection, solver warnings, search, sorting and the overview layout. Browser evidence is saved beside the catalog in `qa/`.
