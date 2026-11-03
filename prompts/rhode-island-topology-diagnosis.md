# Rhode Island topology diagnosis

Rhode Island can be partitioned into two districts that meet strict shared-edge connectivity, but their populations are forced to be **1,095,969 and 1,410**. A near-balanced plan is impossible at either requested district count under the unchanged source coverage. This is a geographic population constraint, independent of solver convergence.

[Explore the disconnected components](http://127.0.0.1:8770/diagnostics/rhode-island/) · [Inspect the exported connectivity-only K2 example](http://127.0.0.1:8770/diagnostics/rhode-island/connectivity-only-k2/) · [Compact evidence report](/C:/Users/benja/projects/voting_paradigm/prompts/rhode-island-topology-diagnosis.json)

## What is disconnected, and why?

The independently audited polygon-part graph has exactly two components:

| Source component | Census blocks | Polygon parts | Resident population | Water-only blocks |
|---|---:|---:|---:|---:|
| Main Rhode Island component | 25,585 | 25,593 | 1,095,969 | 804 |
| Block Island / New Shoreham component | 64 | 64 | 1,410 | 14 |
| Total | 25,649 | 25,657 | 1,097,379 | 818 |

New Shoreham encompasses Block Island; the official 2020 municipal population of 1,410 matches the isolated component. [Town of New Shoreham](https://newshorehamri.gov/216/Welcome-to-New-Shoreham), [Rhode Island population table](https://planning.ri.gov/documents/census/2021/POP-BY-C%26T-2010%20-%202020.pdf).

The isolated component contains **62 blocks in tract 44009041500 and two in water tract 44009990200**. All 818 water-only blocks statewide were already retained. Existing water polygons can provide legitimate shared-edge paths, but their coverage has boundaries. The closest boundaries of these two components remain approximately **2,333.895 meters (2.3339 km)** apart. This is a positive source-coverage gap, not a corner contact or a tiny numerical crack. It is not a measured shore-to-shore distance, and this analysis does not classify the gap's jurisdiction.

Both exact component unions are single valid polygons, with no overlapping interiors. The part graph and an independent traversal agree. No whole block owns parts in both components. The single multipart block has all its parts in the main component, so the Maryland/Virginia ownership defect is not causing this exception. The viewer's land-bearing layer is for orientation; the all-block source footprint is authoritative for connectivity.

## What does strict connectivity permit?

Every connected district must lie entirely inside one global source component. Every retained component needs at least one district. Hence the 1,410-person component must supply at least one entire district; assigning it to a mainland district would violate the shared-edge rule.

| District count | House sizes | Ideal population | Best component allocation | Unavoidable maximum deviation from ideal |
|---|---|---:|---|---:|
| 2 | 435, 574, 692 | 548,689.5 | Main 1 / island 1 | **547,279.5 people (99.743024%)**, exact |
| 3 | 1,000 | 365,793 | Main 2 / island 1 | **At least 364,383 people (99.614536%)** |

K2 has only one possible component allocation, so those populations and that optimum are forced. K3's figure is the strongest lower bound obtainable from the component totals and integer district populations alone. A connected whole-block split of the main component may impose a higher deviation. **No K3 map was constructed**, and the relaxed population allocation is not a claim of geometric feasibility. Any maximum-deviation tolerance below these bounds is impossible under the current territory and connectivity rules.

The existing connected-source preflight is stricter than a general partitioner requires: disconnected source components can each contain connected districts. A component-aware preflight could test integer district allocations and their population bounds before solving. That improvement would explain this exception more precisely, but would not create a near-balanced Rhode Island plan. More iterations, different centers, or the local multipart repair cannot overcome the component-population bound.

## Verified diagnostic export

The K2 example assigns each whole component to one district. Both districts pass the block graph, polygon-part graph, and independent unsimplified polygon checks. Every block is assigned once; all 1,097,379 residents and the exact original component geometry are retained; district interiors do not overlap. No source coordinate was changed and no synthetic connection was added.

The example is explicitly labeled **connected but not population balanced**. It is not promoted to a successful benchmark plan. The original `unsupported_topology` report and national suite are preserved byte-for-byte. Creating and validating the example took **33.40 seconds**, including full map export, without running the numerical solver. The resulting maps include exact and simplified outlines plus county block detail.

## Evidence and reproduction

- [Full component diagnosis](/C:/Users/benja/projects/voting_paradigm/.cache/state-block-benchmark/suite-through-1000/diagnostics/rhode-island/diagnosis.json) and [analysis script](/C:/Users/benja/projects/voting_paradigm/.cache/state-block-benchmark/suite-through-1000/diagnostics/rhode-island/analyze.py).
- [Exact population-bound certificate](/C:/Users/benja/projects/voting_paradigm/.cache/state-block-benchmark/suite-through-1000/diagnostics/rhode-island/feasibility.json) and [calculation script](/C:/Users/benja/projects/voting_paradigm/.cache/state-block-benchmark/suite-through-1000/diagnostics/rhode-island/build-feasibility.py).
- [Witness validation and provenance](/C:/Users/benja/projects/voting_paradigm/.cache/state-block-benchmark/suite-through-1000/diagnostics/rhode-island/connectivity-only-k2/witness.json), [map manifest](/C:/Users/benja/projects/voting_paradigm/.cache/state-block-benchmark/suite-through-1000/diagnostics/rhode-island/connectivity-only-k2/maps/map-manifest.json), and [export script](/C:/Users/benja/projects/voting_paradigm/.cache/state-block-benchmark/suite-through-1000/diagnostics/rhode-island/export-connectivity-witness.py).
- [Geographic context and primary sources](/C:/Users/benja/projects/voting_paradigm/.cache/state-block-benchmark/suite-through-1000/diagnostics/rhode-island/geography-context.json).

SHA-256 identities:

| Evidence | SHA-256 |
|---|---|
| Census source archive | `79d10c9dfec1e3e0962e13d6295b53856db286a156d9937d3737adb0c542f35b` |
| Original topology-exception report | `4fe142128a5305fe7b53ed28ee04e5380eb20652928344645d5bc81db3f6c3cf` |
| Independent component diagnosis | `ad5441968267f4098506b46fdf4b665ecfd28c58aefb9bbf3aca80f350357d7c` |

The compact JSON also records the certificate, witness and context checksums, part graph cache key, preservation checks and measured payload sizes. Numerical algorithms and historical benchmark statuses were not changed by this diagnosis.
