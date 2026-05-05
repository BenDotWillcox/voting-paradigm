/**
 * Per-state Albers Equal-Area Conic projection.
 *
 * For each US state we want a projection that:
 *   - is equal-area (so the choropleth is honest about land area), and
 *   - has minimal distortion *within* that state.
 *
 * The standard recipe for Albers Conic Equal-Area against a target
 * region:
 *   - Two standard parallels at 1/6 and 5/6 of the way from the south
 *     to the north of the region (Snyder, *Map Projections — A
 *     Working Manual*, USGS PP 1395, 1987).
 *   - Center longitude at the region's central meridian.
 *
 * That formula gets <0.1% area distortion across any state in the
 * union — including Alaska and Hawaii — because the parallels are
 * tuned to the state's own latitude band rather than CONUS's.
 *
 * `state-fitted-albers.ts` returns a *bare* projection (no scale or
 * translate set); the renderer calls `.fitSize([w, h], feature)` to
 * size it into whatever SVG viewBox it wants.
 */

import { geoAlbersUsa, geoConicEqualArea, geoBounds } from "d3-geo";
import type { GeoProjection } from "d3-geo";
import type {
  Feature,
  FeatureCollection,
  GeoJsonProperties,
  Geometry,
} from "geojson";

/** Aspect ratio for state detail cards. Drives every state SVG to a
 *  consistent shape regardless of the state's bbox. 4:3 is roomy enough
 *  for tall states (ID, NV) without leaving wide states (TN, OK)
 *  feeling cramped. */
export const STATE_DETAIL_VIEWBOX = { width: 800, height: 600 } as const;

/** Canonical viewBox for the national overview. Matches the d3-geo
 *  Albers USA convention (975x610) which is what most US map demos
 *  use, so visual designs that target Albers USA fit straight in. */
export const NATIONAL_VIEWBOX = { width: 975, height: 610 } as const;

/**
 * Build an Albers Equal-Area Conic projection that minimizes
 * distortion within `feature`'s bbox.
 *
 * The returned projection has scale and translate set by `fitSize` to
 * fill the requested viewBox. Padding is applied as a 4% margin so
 * the state outline doesn't kiss the card edges.
 */
export function stateFittedAlbers(
  feature: Feature<Geometry, GeoJsonProperties>,
  width: number = STATE_DETAIL_VIEWBOX.width,
  height: number = STATE_DETAIL_VIEWBOX.height,
  paddingFraction: number = 0.04
): GeoProjection {
  const [[lonMin, latMin], [lonMax, latMax]] = geoBounds(feature);
  const latRange = latMax - latMin;
  // d3.geoBounds returns lonMin > lonMax when the geometry crosses
  // the antimeridian (Alaska's Aleutian Islands). In that case the
  // *real* longitude range is `lonMin → 180 → -180 → lonMax`, and
  // the naive midpoint puts the central meridian on the opposite side
  // of the planet. Unwrap by shifting lonMax up by 360, computing the
  // midpoint, and folding back into [-180, 180].
  let lonCenter: number;
  if (lonMin > lonMax) {
    const unwrapped = (lonMin + (lonMax + 360)) / 2;
    lonCenter = unwrapped > 180 ? unwrapped - 360 : unwrapped;
  } else {
    lonCenter = (lonMin + lonMax) / 2;
  }
  const phi1 = latMin + latRange / 6;
  const phi2 = latMax - latRange / 6;

  const projection = geoConicEqualArea()
    .parallels([phi1, phi2])
    .rotate([-lonCenter, 0]);

  // Inset by `paddingFraction` on every side so polygons don't sit
  // flush with the SVG edge.
  const padX = width * paddingFraction;
  const padY = height * paddingFraction;
  projection.fitExtent(
    [
      [padX, padY],
      [width - padX, height - padY],
    ],
    feature
  );
  return projection;
}

/**
 * National-overview projection: Albers USA (composite — CONUS plus
 * AK/HI insets in the lower-left), sized to fill `width × height`.
 *
 * Pass the FeatureCollection of all 50 states so the projection can
 * fit the entire union.
 */
export function nationalAlbers(
  features: FeatureCollection<Geometry, GeoJsonProperties>,
  width: number = NATIONAL_VIEWBOX.width,
  height: number = NATIONAL_VIEWBOX.height,
  paddingFraction: number = 0.02
): GeoProjection {
  const padX = width * paddingFraction;
  const padY = height * paddingFraction;
  return geoAlbersUsa().fitExtent(
    [
      [padX, padY],
      [width - padX, height - padY],
    ],
    features
  );
}
