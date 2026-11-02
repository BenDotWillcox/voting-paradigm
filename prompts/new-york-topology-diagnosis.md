# New York topology diagnosis

[Open the interactive diagnostic](http://127.0.0.1:8770/diagnostics/new-york/)

**The population-aware selector resolves the graph obstruction, but a water-only policy is insufficient for Ellis Island.** Use a recorded water link for Liberty Island and an explicit exclave connection for New York’s portion of Ellis Island. No district plans were generated and no existing connectivity policy was changed.

| Physical component | Blocks | Polygon parts | 2020 residents |
|---|---:|---:|---:|
| Main New York coverage | 288,817 | 288,839 | 20,201,249 |
| Liberty Island | 1 | 1 | 0 |
| New York portion of Ellis Island | 1 | 1 | 0 |

All 288,819 census blocks remain included. The 12 multipart blocks stay within their respective components; there is no population allocation ambiguity between detached parts. Both isolated blocks record zero housing units as well as zero residents. They are real park/museum geography, not missing records. Zero resident population does not mean zero visitors.

The main component includes 7,660 water-only census blocks. Shared-edge connectivity here covers the complete census geography; it is not a continuous-dry-land or road-access test. Long Island, Staten Island and Manhattan do not create additional disconnected components in this source.

## Why these two blocks are separate

Liberty Island is in New York’s territorial jurisdiction. Ellis Island has a split boundary: its original New York portion contains the museum’s Main Building, while most expanded land is in New Jersey. The Census geometry reflects that separation. [National Park Service: Liberty Island](https://www.nps.gov/stli/planyourvisit/frequently-asked-questions-statue-of-liberty.htm); [National Park Service: Ellis Island](https://www.nps.gov/elis/faqs.htm).

## Proposed connections

| Candidate | Total distance | Mapped water | New Jersey land | Selected |
|---|---:|---:|---:|---|
| Liberty → main coverage | 795.3 m | 795.3 m | 0.0 m | All four anchors |
| Ellis → main coverage | 852.0 m | 826.5 m | 25.5 m | All four anchors |
| Liberty → Ellis | 973.0 m | 821.6 m | 151.4 m | No |

Both selected links end on the same New York water-only block, `360610005000003`. These are distances to included census boundaries, not to a Manhattan shoreline or ferry terminal. The candidate between the islands is longer and is not selected.

The entire boundary of the New York Ellis block is surrounded by New Jersey nonwater coverage in the 2020 data. Its closest mapped-water gap is 2.34 m. Thus changing the candidate’s direction cannot make a strictly water-only route leave this block in the audited geometry. The proposed direct link crosses about 25.5 m of New Jersey land, verified both against county water polygons and a land-only New Jersey census block. This is the same kind of explicit geographic exception used for Kentucky, on a much shorter land segment. No New Jersey territory or population would be assigned.

## Population-aware feasibility

| House size | New York districts | Ideal resident population | Proposed links | Source components after links |
|---:|---:|---:|---:|---:|
| 435 | 26 | 776,971.115 | 2 | 1 |
| 574 | 35 | 577,178.543 | 2 | 1 |
| 692 | 42 | 480,982.119 | 2 | 1 |
| 1,000 | 61 | 331,168.016 | 2 | 1 |

The unchanged population-aware selector chooses the same two edges at every anchor. An independent full-graph traversal reaches all 288,841 polygon parts. There is only one populated component, so no large-island seat-allocation tradeoff arises.

Under strict physical connectivity with every block assigned, each single-block island would require a zero-population district: at least 100% maximum population deviation. The policy’s grouped-population lower bound becomes 0%; this is an optimistic mathematical bound, not achieved district balance. More specifically, any valid connected partition of the main component can be extended by assigning both zero-population island blocks to the district containing their shared endpoint block, without changing population totals. The balanced partition of the main component still needs to be computed and independently validated.

## Validation and limits

- Independently reread original ZIP DBF records; verified block/population totals, island records, endpoint ownership, selected links, and water/land segment reconciliation.
- Verified source/artifact checksums and all 5 protected historical files, including the strict result, national manifest and original New York archive.
- Source polygons and physical adjacency remain unchanged. Proposed links are conceptual graph edges, not roads, ferries or boundary transfers.
- Exact part adjacency and polygon intersections use unsimplified 2020 geometry. Display polygons are simplified separately.
- Candidate search uses an approximate per-pair projection; lengths are not certified shortest geodesics. Water classifications describe mapped 2020 geography, not navigability or current water levels.
- Original strict K26 stopped before solving after 99.36 seconds; K35/K42/K61 reused its topology exception. No new district runtime, balance or compactness results exist yet.

[Detailed topology evidence](../.cache/state-block-benchmark/suite-through-1000/diagnostics/new-york/diagnosis.json) · [Independent crossing audit](../.cache/state-block-benchmark/suite-through-1000/diagnostics/new-york/geography-context.json)
