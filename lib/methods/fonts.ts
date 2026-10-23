import { Instrument_Sans, JetBrains_Mono } from "next/font/google";

/**
 * The methods instrument's type: a geometric sans for words and a mono for
 * every number and profile row. No serif, unlike the essays. Applied on the
 * instrument root and the methods home card only, so other routes don't
 * load these fonts.
 */
export const instrumentSans = Instrument_Sans({
  subsets: ["latin"],
  variable: "--font-instrument-sans",
  display: "swap",
});

export const instrumentMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains-mono",
  display: "swap",
});
