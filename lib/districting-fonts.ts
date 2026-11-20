import localFont from "next/font/local";

/**
 * The districting demo's mono face for readouts, labels and controls; it
 * backs --dd-mono in app/globals.css. Applied on /districts and the
 * districting home card only, so other routes don't load it.
 */
export const districtsMono = localFont({
  src: "../app/fonts/JetBrainsMono.woff2",
  weight: "400 600",
  variable: "--font-dd-mono",
  display: "swap",
});
