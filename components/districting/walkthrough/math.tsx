const SUPERSCRIPT = "⁰¹²³⁴⁵⁶⁷⁸⁹";

/** 2.74 × 10¹¹ style, for quantities too large to read in full. */
export function sci(value: number, digits = 2) {
  if (value === 0) return "0";
  const exponent = Math.floor(Math.log10(Math.abs(value)));
  const power = String(exponent).split("").map((char) => char === "-" ? "⁻" : SUPERSCRIPT[Number(char)]).join("");
  return `${(value / 10 ** exponent).toFixed(digits)} × 10${power}`;
}

/** A small probability as odds: "1 in 150,408". */
export const oneIn = (chance: number) => `1 in ${Math.round(1 / chance).toLocaleString()}`;
