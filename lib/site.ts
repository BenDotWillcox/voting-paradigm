/**
 * The site's name and palette. The name appears in the demo header, on the
 * home page and in the tab title, so a rename is this one line.
 *
 * The palette dresses the site's own chrome: the white home page, its
 * voting-history scene and the header above every demo. It is bright on
 * purpose: navy carries text, and the accents carry light and motion. Demo
 * cards and demo pages keep their own identities. app/globals.css mirrors
 * these as `--color-site-*` tokens.
 */
export const SITE_NAME = "Future Democratic Systems Lab";

export const SITE_PALETTE = {
  navy: "#0d1726",
  mist: "#f3f6fd",
  blue: "#2f6bff",
  aqua: "#1ec8d8",
  rose: "#e2457e",
  sun: "#ffb547",
  /** A fifth accent, so each future branch in the scene has its own color. */
  violet: "#7c5cff",
} as const;
