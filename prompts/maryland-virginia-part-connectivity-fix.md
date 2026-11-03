# Maryland and Virginia part-connectivity correction — October 23, 2026

Both corrected House-1,000 maps pass polygon-part connectivity, whole-block connectivity, and independent strict unsimplified polygon validation. Each correction moved one whole zero-population block, selected automatically from the saved assignments. Every district population is unchanged; exact map coverage is preserved and district interiors do not overlap. The original failed run directories were verified byte-for-byte unchanged.

[Corrected maps](http://127.0.0.1:8770/corrections/part-connectivity-v1/) · [Original diagnosis](maryland-virginia-geometry-diagnosis.md) · [Machine-readable evidence](maryland-virginia-part-connectivity-fix.json)

| State | Districts | Whole-block transfer | Maximum population deviation | Total correction/export time | Peak working set |
|---|---:|---|---|---:|---:|
| Maryland | 19 | 17 → 16 | 20.947 (0.006443%) | 3.04 min | 378.1 MiB |
| Virginia | 26 | 19 → 15 | 17.346 (0.005225%) | 8.70 min | 784.9 MiB |

Correction timing includes new part-graph creation, repair, audits, and complete map regeneration; it is separate from the original power-diagram solve, which was not rerun. The repair itself took Maryland 0.918s, Virginia 1.598s. The two corrections ran sequentially; desktop activity and test execution may affect timings.

## Implementation and guarantees

- `districting/part_connectivity.py` represents each source polygon part as a vertex, with explicit block ownership. Parts share an assignment but ownership never creates an edge. Each block's population is counted once.
- The deterministic local repair permits zero-population whole-block moves only when total component count decreases, neither affected district worsens, and neither becomes empty. It can report a local-search stall without claiming infeasibility.
- `repair_and_rebalance` now accepts a part graph. Subsequent population moves check donor and recipient part connectivity; the general-state benchmark always supplies it and independently records part counts. Historical Kansas entry points retain their legacy behavior until explicitly rerun with the new adapter.
- `scripts/district_block_part_graph.py` builds exact positive-length shared-edge adjacency and caches it separately from old whole-block graphs. Identity includes source/archive order, builder/domain code, topology rule and geometry-library versions. Cache loads reject corrupt checksums, ownership, CSR structure or metadata; pickle is disabled.
- `scripts/correct_state_block_parts.py` uses a separate output tree, state execution locks, saved-artifact/source checksums, original-file inventories, versioned final assignments, whole-block move audits, separate correction timing, and freshly generated compressed county shards/outlines. It refuses to overwrite prior correction attempts.

Validation: **261 districting/benchmark tests passed**, including exact Census-coordinate fixtures for both failures, multipart/corner/overlap cases, unsafe donor/recipient moves, population conservation, cache corruption, artifact preservation, and correction-to-export integration. Independent review found no actionable correctness issues. Mypy is not installed in the current venv, so strict static checking was not run.

The original national suite remains its historical 152-complete / 23-topology-exception / 2-failed snapshot. These two separately versioned replacements bring available validated plans to **154**, with the **23 topology-exception jobs unchanged**. This does not resolve the separate source-disconnection/antimeridian limitations or West Virginia's population-balance outlier. No nationwide rerun or application integration was performed.

## What the zero-population blocks are

| State / block | Published population | Housing units | Census land area | Census water area |
|---|---:|---:|---:|---:|
| Maryland `240419608001043` | 0 | 1 | 331,243 m² (100%) | 0 |
| Virginia `510010906001010` | 0 | 0 | 157,291 m² (5.47%) | 2,715,985 m² (94.53%) |

Census blocks cover all territory and are delineated by geographic boundaries, not population. Zero population is normal and does not identify a land-use category. [Census explanation](https://www.census.gov/newsroom/blogs/random-samplings/2011/07/what-are-census-blocks.html).

Virginia's block is mostly water with no housing. Maryland's is land with one housing unit; vacancy or seasonal use is possible but not established. The source metadata defines POP20 as adjusted by the Disclosure Avoidance System, so a published zero cannot establish exact occupancy. We have not determined whether privacy adjustments changed either count. The Census fields do not establish ownership or protected status. [Census invariants](https://content.govdelivery.com/accounts/USCENSUS/bulletins/2ae5eda).

The confirmed error was our whole-block graph representation, not a demonstrated Census data error. Original DBF records, metadata definitions, archive/checksum evidence and source links are included in the accompanying JSON.

## Reproduction

Use `scripts/correct_state_block_parts.py --original <preserved failed run> --output <new empty correction directory>`. The original run must have a verified source archive and final assignment digest. New output is mandatory; old source, solver measurements and failure evidence remain preserved. The correction results page links reports and move audits; each map viewer links its assignments and validation manifest.
