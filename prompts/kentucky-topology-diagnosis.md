# Kentucky: a recorded connection for an exclave

**Kentucky Bend is a genuine detached piece of the state. One recorded connection resolves the source-graph obstruction, but the nearest line crosses Missouri land as well as river. It must be described as an explicit exclave connection, not a water-only link.**

[Explore the diagnostic map](http://127.0.0.1:8770/diagnostics/kentucky/). Colors show physical source components, not districts; the dashed line is hypothetical. No Kentucky district solver or district-map export ran in this diagnosis.

## What is disconnected?

| Component | Residents | Census blocks | Polygon parts |
|---|---:|---:|---:|
| Main Kentucky coverage | 4,505,827 | 132,657 | 132,664 |
| Kentucky Bend / Madrid Bend | 9 | 5 | 5 |
| Total | 4,505,836 | 132,662 | 132,669 |

The detached component lies in Fulton County. It includes **45.202351 km² of land and 24.427246 km² of water coverage**, with four zero-population blocks and two water-only blocks. All nine residents are in one of its five blocks. Nothing was discarded for having zero population. Four multipart blocks elsewhere in the state remain within their physical components; no block spans the two components. Both exact component unions are valid single polygons. The gap is positive, not a corner contact or a numerical crack.

The location matches Kentucky Bend, the peninsula whose neck joins Tennessee. Kentucky's boundary followed the Mississippi; the Kentucky Historical Society describes the river claim and the boundary survey settlement with Tennessee. This geographic explanation is supported by the [Madrid Bend historical marker](https://history.ky.gov/markers/madrid-bend); the exact populations and boundaries above are calculated from the saved 2020 Census blocks.

## What strict shared edges permit

Every retained physical component needs at least one district. A district confined to the detached component can contain at most nine residents. Therefore its deviation from the statewide ideal is at least `1 − 9 × district_count / 4,505,836`. The component-allocation calculation independently agrees with this bound:

| House size | Kentucky districts | Ideal residents per district | Unavoidable maximum deviation, at least |
|---|---:|---:|---:|
| 435 | 6 | 750,972.667 | 99.998802% |
| 574 | 8 | 563,229.500 | 99.998402% |
| 692 | 9 | 500,648.444 | 99.998202% |
| 1000 | 14 | 321,845.429 | 99.997204% |

These are necessary bounds, not constructed strict plans. They rule out near-equal population under strict shared-edge connectivity while retaining every block. More optimizer iterations cannot remove this geographic constraint.

## What a recorded connection changes

The population-aware selector used for Hawaii chooses one link at every Kentucky anchor: main block **210759602004000** to Bend block **210759602004105**. The mainland is the sole district-sized root; the nine-person component is undersized at all four counts. An independent traversal of the augmented graph reaches all **132,669 parts** after inserting that edge. Source polygons and physical adjacency remain unchanged.

The candidate is approximately **5.145 km** long, measured between original census-coverage boundaries. It is selected by an approximate equirectangular nearest-boundary search; reported length is the spherical distance between those endpoints, not a certified shortest geodesic or a shoreline distance.

The entire gap lies within Missouri census coverage. Official [2020 New Madrid County area-water polygons](https://www2.census.gov/geo/tiger/TIGER2020/AREAWATER/tl_2020_29143_areawater.zip) show **1.805 km crossing the Mississippi River in two segments**, and **3.340 km crossing Missouri land between them**. The full county layer has 271 features. The intersection audit uses exact source polygons; display context is simplified. This describes mapped 2020 geography, not current river levels, navigation or a road/ferry route. A longer curved water-only route was not searched, so this does not prove none exists.

**Recommendation:** reuse the population-aware grouping and recorded-link validation, with a clearly named **exclave connection** category for Kentucky. The link grants adjacency only between its two Kentucky endpoint blocks; it does not assign Missouri territory to a Kentucky district. A district may use it only when both endpoint blocks belong to that district.

This removes the component-population obstruction, but does not establish a balanced whole-block partition. A Kentucky adapter and fresh runs at 6, 8, 9 and 14 districts must still demonstrate population balance, repair/rebalancing behavior, and independent final polygon-plus-link connectivity. The Rhode Island and Hawaii geometry adapters are state-scoped; they were not silently applied to Kentucky.

## Verification and preserved evidence

All five protected historical files (the original Kentucky report/progress/log, national manifest and Kentucky source archive) remain byte-identical. The original six-district run stopped at source-topology preflight; the other three anchors reused that exception and did not have individual solver runs. The Missouri block archive and downloaded water archive were verified by hash. No numerical or existing policy code changed.

The final diagnostic used a warm graph cache and took 53.27 seconds. This is diagnostic timing, not a district benchmark; earlier diagnostic tooling repairs and cold preparation are retained separately in [attempt notes](http://127.0.0.1:8770/diagnostics/kentucky/diagnostic-attempt-notes.json).

[Exact source audit](http://127.0.0.1:8770/diagnostics/kentucky/diagnosis.json) · [Missouri coverage audit](http://127.0.0.1:8770/diagnostics/kentucky/missouri-connection-context.json) · [Water/land intersection audit](http://127.0.0.1:8770/diagnostics/kentucky/area-water-audit.json) · [Machine-readable summary](C:/Users/benja/projects/voting_paradigm/prompts/kentucky-topology-diagnosis.json).
