# National district-map performance — 2026-10-28

Status: complete. Published and running at port 3011; production build and browser QA passed.

The four national maps now use a separate, lighter display layer. Hover updates only the affected state controls and borders. A shared cache reuses prepared SVG paths across remounts and retains at most two views / an estimated 64 MiB of path strings and bookkeeping. The decoded asset caches are separate; this is not a browser heap limit.

## Comparison at 1,000 seats

| Measurement | Before | After | Reduction |
| --- | ---: | ---: | ---: |
| All seven national inputs, compressed | 16.53 MB | 7.08 MB | 57.2% |
| Decoded JSON | 61.62 MB | 33.22 MB | 46.1% |
| Cold decode through validated prepared paths | 3,569 ms | 911 ms | 74.5% |
| SVG path generation | 1,888 ms | 467 ms | 75.3% |
| Projection preparation | 157 ms | 33 ms | 78.7% |
| Warm decoded anchor return / prepared-cache lookup | 1,831 ms | 0.666 ms | 99.96% |
| Stored SVG path characters | 25.66 million | 6.42 million | 75.0% |
| Peak Node RSS | 1,499 MiB | 510 MiB | 66.0% |

Timings are medians of five measured samples after one warmup, using serial fresh Node processes on this desktop (Node 22.14.0, Ryzen 7 3700X), after generation and tests finished and before the Next build. Compressed buffers were resident before measurement; the benchmark uses the actual validation, projection, drawing and cache helpers. These are CPU/preparation and Node resident-memory measurements, **not browser FPS, end-to-end navigation latency, network timing, GPU paint or browser memory**. The warm result excludes mounting and painting SVG nodes. The original hover already avoided d3 path recalculation; that was not presented as a new saving.

A separate deterministic test of both real components uses identical original 1,000-seat geometry and the same California → Texas hover sequence. It preserves the exact ordered SVG path hash, while district-fill descriptor construction falls from **1,000 to zero**, static mesh paths from **100 to zero**, and connection paths from **126 to zero**. Only two state groups and four border paths update. Total host-element descriptors fall from 1,573 to 37. On a cached remount, 1,276 geometry calls and one projection become zero calls; the cache returns the same prepared object. These are component workload counts, not elapsed browser measurements. The rendered map still has 1,326 SVG paths and 50 keyboard-selectable states.

## Geometry and preservation

`build_national_land_overview.py` produces 12 additive fill/coast/divider assets, referenced by the optional `nationalLandAnchors` manifest field. Shared arcs are simplified jointly with topology preservation and original-coordinate subsequences. Source edges near neighboring states are fixed two-point obstacles, so existing interstate edges remain exact. Matching coast/divider meshes come from the resulting polygons. Default tolerance is 0.02 coordinate degrees with a 0.05-degree neighbor guard; independently checked continuous per-district boundary-error bounds are below 0.025 degrees, including the sampling margin. These are display-coordinate bounds, not a claim about legal boundaries or distances in meters.

| House size | Original polygon coordinates | New coordinates | Three geometry layers, gzip before → after |
| --- | ---: | ---: | ---: |
| 435 | 743,457 | 190,086 | 10.81 → 2.99 MB |
| 574 | 799,767 | 193,792 | 11.47 → 3.04 MB |
| 692 | 830,738 | 200,423 | 11.83 → 3.13 MB |
| 1,000 | 905,440 | 209,252 | 12.70 → 3.25 MB |

All 200 state/anchor displays retain their source district properties, polygon parts and holes, valid coverage and coordinate frames. Three West Virginia views (435/K2, 692/K4, 1,000/K5) retain their original geometry: simplification/local restoration could not establish a valid candidate. This is a conservative cartographic fallback, not a failed saved plan or a population/connectivity change. Source interstate display seams are preserved rather than repaired.

The independent audit confirms all **181 accepted plans and source-proof records**, **520,468 existing asset records**, and every original manifest field remain exact. Twelve new assets were independently checked against raw/compressed hashes. The four anchors contain 50 states, exactly 435 / 574 / 692 / 1,000 districts and **330,759,736 residents** each. All original derived/recorded connection references and their eight aggregate files are unchanged; there are 76 recorded connections per national anchor. Alaska retains continuous longitudes and its dedicated inset projection. State geometry, full census extent, county/city layers and block chunks remain unchanged. No solver or block generator ran.

Publication uses a checked prepared report with frozen runtime/base hashes, then saves byte-exact manifest/index backups before adding the national references. It does not rerun geometry preparation. Generation took 770 seconds. The full census toggle still uses the original national geometry.

## Validation and evidence

**94 regressions passed in 48.14 seconds.** Coverage includes shared edges in opposite directions, enclave holes, narrow coastlines, original-coordinate preservation, explicit fallbacks, stale/tampered publication rejection, cache byte/LRU bounds, failed and late requests, keyboard focus, current callbacks, anchor resets and unchanged state-detail behavior. TypeScript and focused ESLint checks also passed.

- Machine-readable durable comparison: [national-map-performance.json](national-map-performance.json).
- Independent timings/preservation/hover evidence: `.cache/block-main-port/national-performance-v1/` (`matched-comparison.json`, `preservation-after.json`, `frontend-hover-workload.json`, pinned before/after source and input records, test/build logs).
- Geometry report and exact historical metadata: `data/districting-block-plans/national-land-overview-v1/publication.json` and `publication-history/`.
- Preview: [district explorer at 1,000 seats](http://127.0.0.1:3011/districts/explore?cap=1000).

Production build `YoQe2B8Rl5lp573JLHZMU` passed (163 kB explorer first-load JavaScript). Browser checks passed all four anchors, correct district/state counts, 76 recorded links per anchor, separate derived paths, full-census mode, bounded-cache hits on recent anchor returns, whole Alaska/Hawaii inset clicks, a Northeast shortcut, keyboard focus and Enter selection. Michigan and Alaska state-view SVG paths and data-card text matched the captured prior version exactly. Kent County block inspection loaded 19,950 blocks, retained detail while panning, and released its canvas on leaving Blocks; switching to Ionia County preserved whole-county population/share cards. Counties/cities remain enabled by default. No application console errors or server stderr were observed; unrelated browser-extension warnings were retained separately in the raw evidence.

Live House-1000 SVG path text is 8,224,432 characters versus 30,286,505 before (72.8% less); this DOM measure includes repeated border-casing paths, unlike the unique stored-string benchmark above. The map keeps 50 selectable states, eight Northeast shortcuts, two inset panels and all 1,000 district fills. Browser QA is functional/visual rather than a frame-rate or heap profile; no network throttling or touch-device emulation was performed.

Browser evidence and before/after screenshots are `browser-qa.json`, `before.jpg` and `after.jpg` in the evidence directory. No commit was created.
