# Alaska census block topology diagnosis

Alaska has a workable path through the current topology exception: use a continuous longitude frame for geometry and apply explicitly recorded connections to the remaining island gaps. The coordinate transformation and proposed source graph have passed independent checks. This is a topology diagnosis; district optimization and production map export have not run.

[Interactive diagnosis](http://127.0.0.1:8770/diagnostics/alaska/) · [Saved evidence](alaska-topology-diagnosis.json)

## The original exception was a longitude handling guard

The strict batch stopped before constructing Alaska's graph because its coordinates span −179.23° to +179.86°. The western Aleutians appear on the opposite end of a conventional longitude axis. The 180th meridian crosses the island chain; the International Date Line bends around it and is a different concept. [Alaska geography](https://www.alaska.gov/Kids/learn/aboutgeography.htm), [NOAA explanation](https://oceanservice.noaa.gov/facts/international-date-line.html).

The verified 2020 source needs only a whole-geometry translation: subtract 360° from the 99 blocks represented with positive longitude. These blocks contain 232 residents. No source block mixes the two longitude sides, and no source ring needs splitting. Alaska's working longitude span falls from 359.09° to 57.68°. Every inverse-translated coordinate equals the original exactly in this source.

All **28,568 blocks, 28,706 polygon parts and 733,391 residents** remain included. Original and normalized graphs have the identical **68,050 shared edges**, with no overlapping interiors and no synthetic edges between parts belonging to the same block. All 50 graph components independently dissolve to valid single polygons. The source includes 94 multipart blocks; none spans disconnected global components.

## Genuine island gaps remain

Normalization leaves **50 physical coverage components**: 11 populated and 39 with zero population. The main component contains 711,702 residents; the other 49 contain 21,689. These are Census coverage components, including water, rather than separate dry-land islands. [Census geography glossary](https://www.census.gov/programs-surveys/geography/about/glossary.html).

| Approximate detached coverage region | Residents |
|---|---:|
| Kodiak archipelago | 13,101 |
| Eastern Aleutians, including Unalaska and Umnak | 5,882 |
| St. Lawrence Island | 1,475 |
| St. Paul and nearby Pribilof coverage | 413 |
| Semichi Islands and Shemya | 232 |
| Central Aleutians, including Adak and Atka | 227 |
| Nunivak Island | 206 |
| Little Diomede | 83 |
| St. George | 67 |
| Sanak Islands | 3 |

Region names are inferred from source bounds and official maps, not an exact island spatial join. In particular, a connected coverage region may contain several islands linked by Census water polygons. See the [DOI Aleutian map](https://www.doi.gov/sites/default/files/documents/2025-09/aleutianislands508.pdf), [NOAA Bering Sea map](https://www.pmel.noaa.gov/foci/foci_moorings/foci_moormap3.shtml), and the viewer's geographic evidence links.

## The existing population rule can cover both anchors

The four requested House sizes yield only two distinct Alaska plans:

| House sizes | Alaska districts | Ideal residents per district | Proposed links | Augmented source components |
|---|---:|---:|---:|---:|
| 435 and 574 | 1 | 733,391 | 49 | 1 |
| 692 and 1,000 | 2 | 366,695.5 | 49 | 1 |

With full coverage and strict shared-edge connectivity, 50 components require at least 50 districts. Thus one or two physically connected districts cannot cover this source without an explicit geographic exception.

At two districts, only the main component reaches the existing root threshold of 99% of ideal population. The largest detached group is only 3.57% of an ideal district. At one district, no individual component reaches that threshold, so the existing rule's all-components fallback applies. Both cases therefore require one connected group.

The Hawaii implementation caps its general search at eight populated components; Alaska has eleven. For these two anchors, no exponential grouping search is needed: with at most one eligible root, a deterministic minimum spanning tree implements the same grouping rule. Regression cases match the existing selector, including its tie breaks. This shortcut deliberately rejects multiple eligible roots, which would require the general policy.

Of 1,225 component-pair candidates, 291 pass the positive-gap and source-interior checks. The same 49-link tree connects every source part for both anchors. Links range from **345 meters to 292.56 kilometers**, totaling about **1,550 kilometers**. Nearby islands can connect through one another; they do not all connect directly to the mainland.

The longest proposed connection joins St. George coverage to Bogoslof coverage across the southeastern Bering Sea. Another spans about 251.12 km between Nunivak and the St. Matthew group. These regional interpretations are supported by [NOAA's Pribilof and Bogoslof map, Figure 1](https://apps-afsc.fisheries.noaa.gov/Publications/AFSC-TM/NOAA-TM-AFSC-174.pdf) and [NOAA bathymetric regions](https://www.ngdc.noaa.gov/mgg/bathymetry/maps/area7.html). Candidate tests cover Alaska source interiors, not a global land mask or foreign territory. Distances are spherical distances between Census boundary endpoints selected in a local plane; they are not certified shortest geodesics, shoreline distances or travel routes.

## Implementation needed before district runs

1. Carry the declared continuous longitude frame through solving, polygon-part repair and independent full-resolution polygon validation. Retain original coordinates and exact source-part ownership for every recorded endpoint.
2. Add the reviewed 49 links as explicit policy edges. A connection counts within a district only when both endpoint blocks belong to that district. Physical connectivity remains a separate reported metric.
3. Extend the exporter and viewer consistently. A standard geographic export must handle the antimeridian; display cuts must not be mistaken for real physical disconnection. The present diagnostic deliberately uses unwrapped coordinates and labels them as such. [RFC 7946 antimeridian guidance](https://www.rfc-editor.org/rfc/rfc7946#section-3.1.9).
4. Validate the one-district assignment, then benchmark the two-district solve and its repair. The source-group population bound is zero, but that does not predict achieved two-district whole-block balance. A one-district assignment needs no population optimization.

The existing internal-point loader already unwraps Alaska longitudes, but its equirectangular distance model remains approximate across this broad state. Alaska Albers is an established regional projection; changing the optimizer's projection should be a separately recorded numerical choice, not silently bundled with the topology fix. [USGS coordinate-system specifications](https://www.usgs.gov/ngp-standards-and-specifications/elevation-derived-hydrography-data-acquisition-specifications-0).

## Validation and preservation

The final diagnostic completed in **84.28 seconds**, peaking at approximately **1.01 GiB**. This includes two independent source loads, original and normalized graph construction, full polygon checks, all candidate pairs and both policy preflights; it is not a district-solver benchmark. **129 tests passed in 2.01 seconds**, covering Alaska normalization, population-policy equivalence and the existing Hawaii and part-graph helpers.

Six original archive, manifest and strict-run files remain byte-identical. Existing state adapters, optimization code and prior state maps are unchanged. The initial diagnostic is preserved separately; the reviewed rerun produced identical components, candidate endpoints and selected links. Final code, artifact and preservation hashes were checked before publication.
