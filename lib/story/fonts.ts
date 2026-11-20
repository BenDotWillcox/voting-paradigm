import localFont from "next/font/local";

/**
 * Editorial serif for story headlines and prose. Charts, labels, and hero
 * numbers stay in the app's sans; the serif is never used for data.
 * Applied per story page (StoryRoot) so other routes don't load it.
 */
export const storySerif = localFont({
  src: [
    { path: "../../app/fonts/Newsreader.woff2", style: "normal" },
    { path: "../../app/fonts/Newsreader-Italic.woff2", style: "italic" },
  ],
  weight: "200 800",
  adjustFontFallback: "Times New Roman",
  variable: "--font-newsreader",
  display: "swap",
});
