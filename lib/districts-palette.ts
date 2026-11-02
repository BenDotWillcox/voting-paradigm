/**
 * "Peridot Sunrise Meadow" for the districting dashboard: a muted white board,
 * steel circuit traces, yellow signal lights and soft blue selected keys.
 * app/globals.css mirrors these as `--dd-*` tokens. `oliveDeep` and
 * `selectDeep` are derived for text, which the lighter tones cannot carry.
 */
export const DD_PALETTE = {
  signal: "#fee643",
  olive: "#9ca742",
  oliveDeep: "#626a0f",
  peridot: "#adb948",
  board: "#f7fffe",
  select: "#b1ebfc",
  selectDeep: "#17708c",
  steel: "#d9dee1",
  ink: "#464a3b",
  white: "#ffffff",
} as const;

/**
 * Roles for map marks. Data colors (district fills, density bins, connection
 * kinds) are deliberately not palette colors. Hover and selection outlines are
 * a heavier black line over a white casing.
 */
export const MAP_COLORS = {
  grid: DD_PALETTE.steel,
  line: "#454545",
  casing: DD_PALETTE.white,
  selection: "#000000",
  selectionCasing: DD_PALETTE.white,
  derivedWater: "#00838f",
  recordedWater: "#a445a2",
  recordedExclave: "#b45309",
  label: "#454545",
  labelHalo: DD_PALETTE.white,
  /** District fill while population density is drawn over the land. */
  neutralLand: "#eef1ef",
  insetFill: DD_PALETTE.white,
  insetHover: "#eefafe",
  insetActive: DD_PALETTE.selectDeep,
} as const;

/** Circuit backdrop: steel traces on the board; electrons run peridot into signal. */
export const CIRCUIT_COLORS = {
  board: DD_PALETTE.board,
  trace: DD_PALETTE.steel,
  tail: DD_PALETTE.peridot,
  core: DD_PALETTE.oliveDeep,
  glow: DD_PALETTE.signal,
} as const;
