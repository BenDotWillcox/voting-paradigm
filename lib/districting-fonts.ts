import { JetBrains_Mono } from "next/font/google";

/**
 * The districting demo's mono face for readouts, labels and controls; it
 * backs --dd-mono in app/globals.css. Applied on /districts and the
 * districting home card only, so other routes don't load it.
 */
export const districtsMono = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-dd-mono",
});
