import localFont from "next/font/local";

/**
 * The methods instrument's type: a geometric sans for words and a mono for
 * every number and profile row. No serif, unlike the essays. Applied on the
 * instrument root and the methods home card only, so other routes don't
 * load these fonts.
 */
export const instrumentSans = localFont({
  src: "../../app/fonts/InstrumentSans.woff2",
  weight: "400 700",
  variable: "--font-instrument-sans",
  display: "swap",
});

export const instrumentMono = localFont({
  src: "../../app/fonts/JetBrainsMono.woff2",
  weight: "100 800",
  variable: "--font-jetbrains-mono",
  display: "swap",
});
