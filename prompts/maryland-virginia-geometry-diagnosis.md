# Maryland and Virginia polygon-connectivity diagnosis — October 23, 2026

**Implemented follow-up:** the part-level fix and regression tests are complete, and both corrected maps pass strict validation in separately versioned directories. See the [correction results](maryland-virginia-part-connectivity-fix.md). The diagnosis below describes the preserved original failures and candidate analysis.

Both failed House-1,000 runs saved complete map exports. The exact failure is now traced to a zero-population multipart census block in each state. A one-block reassignment fixes each plan on a diagnostic copy, with no artificial connections and no population changes. The original benchmark reports and assignments remain failed and unchanged.

[Interactive diagnosis and candidate preview](http://127.0.0.1:8770/diagnostics/) · [Maryland original map](http://127.0.0.1:8770/states/24/districts-19/) · [Virginia original map](http://127.0.0.1:8770/states/51/districts-26/) · [Detailed evidence](maryland-virginia-geometry-diagnosis.json).

## Confirmed mechanism

The current shared-edge graph has one vertex per census block. A block may contain multiple disjoint polygon parts. Edges from different parts all meet at the same graph vertex, creating a logical route that does not exist in the geometry. Consequently, a district can pass whole-block graph connectivity while retaining a detached polygon.

This is not an export-simplification artifact or an introduced geometric sliver. The failed polygons are evaluated before simplification, and the offending blocks were assigned to the same district in initial, after-repair, and final checkpoints. The whole-block component repair could not see the separation. Population rebalancing skips zero-population moves, so it did not repair it incidentally.

## Maryland: 19 districts

- Display District **17** (index 16) contains three polygon components.
- All three parts of census block **240419608001043** (Talbot County; population 0) were assigned to District 17. Its southern part joins that district's main component, while its northern two parts are detached.
- The detached polygons exactly equal those two source-block parts: approximately **39,653 m²** and **11,019 m²**, near longitude −76.372, latitude 38.767–38.770.
- Each of the block's three parts shares a positive-length edge with **District 16** (index 15).
- Candidate: move the **entire block from District 17 to District 16**.

The candidate produces one graph component and one valid polygon for every district. Coverage is unchanged, overlap remains zero, and every district population is unchanged. Maximum population deviation remains **20.947 people (0.006443%)**.

## Virginia: 26 districts

- Display District **19** (index 18) contains two polygon components.
- The detached piece is part of census block **510010906001010**, population 0 and housing count 0. Its larger part joins District 19; the detached part touches only a District 15 block, **510010906001004**.
- The detached piece is approximately **2,711 m²**, near longitude **−76.007972**, latitude **37.901087**. The larger source part is approximately 2.87 km². Both parts have genuine edge connections to District 15.
- Candidate: move the **entire block from District 19 to District 15** (index 14).

The candidate produces 26 connected graph districts and 26 valid single-component polygons. The affected union is exactly unchanged, overlap remains zero, and every district population is unchanged. Maximum population deviation remains **17.346 people (0.005225%)**.

Areas use local planar approximations for scale; topology checks use exact saved source coordinates without snapping or buffering.

## Recommended implementation

1. **Separate assignment units from connectivity units.** Keep one district assignment and one population value per census block, but represent each polygon part separately for connectivity. Couple all parts of the same block to that assignment; do not connect those parts by synthetic edges.
2. **Make repair and move validation use the part graph.** Evaluate genuine part-to-part shared edges. Permit zero-population whole-block moves when they fix geometry; a population-only objective cannot discover them. Verify both donor and recipient, because moving an entire multipart block could disconnect either one elsewhere.
3. **Use these failures as regression cases.** A disconnected multipart block must fail even when its whole-block graph passes. The two candidate moves must preserve all populations, block indivisibility, graph and polygon connectivity, nonempty districts, exact coverage, and zero overlap. Include a negative case where only one part fits the recipient, so an unsafe whole-block move is rejected.
4. **Export new, versioned corrected plans and run the existing strict validator.** Record the moved GEOID, old/new district, reason, source/code/assignment hashes, and correction timing. Preserve original failed attempts. These local moves do not require rerunning the numerical power-diagram solve to demonstrate feasibility.

This fixes the proven multipart-node defect. It does not resolve the separate disconnected-source-graph exceptions, antimeridian support, or West Virginia's balancing limit. The final independent polygon validator should remain in place after graph changes.

## Reproducible evidence

The combined JSON records source identities, components, neighbor GEOIDs, shared-edge evidence, assignment history, candidate moves, and validation results. Reproducible scripts and diagnostic copies live under:

- `.cache/state-block-benchmark/suite-through-1000/diagnostics/maryland/analyze.py`
- `.cache/state-block-benchmark/suite-through-1000/diagnostics/virginia/analyze.py`

Each directory contains `diagnosis.json`, `components.geojson`, `local-blocks.geojson`, and `candidate-affected-districts.geojson`. The viewer's local detail preview changes the proposed block's displayed assignment only; its state overview remains the original map as a location reference. The full-map links are explicitly labeled diagnostic/failed.

Candidate verification checked all district graph/polygon component counts, polygon validity, unchanged coverage/overlap, unchanged populations, and preserved whole-block assignment. Original stored benchmark statuses were checked after viewer creation and remain failed. No numerical solver or correction has been applied to the canonical benchmark plans in this diagnostic step.
