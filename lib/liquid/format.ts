/** Number formats for the liquid walkthrough. Every quoted value goes through these. */

/** 0.4503 -> "45.0%". */
export function pct(value: number, digits = 1): string {
  return `${(value * 100).toFixed(digits)}%`;
}

/** 0.4503 -> "0.450". */
export function dec(value: number, digits = 3): string {
  return value.toFixed(digits);
}

/** A difference in points: 0.102 -> "+10.2 points". */
export function points(value: number, digits = 1): string {
  const text = (value * 100).toFixed(digits);
  return `${value > 0 ? "+" : ""}${text} points`;
}

/** A resident by array index: 310 -> "Resident 310". */
export function resident(index: number): string {
  return `Resident ${index}`;
}

/** A district by index: 0 -> "District 1". */
export function district(index: number): string {
  return `District ${index + 1}`;
}

/** 3590 of 3740 -> "96%". */
export function share(part: number, whole: number): string {
  return `${Math.round((100 * part) / whole)}%`;
}
