import { Newsreader } from "next/font/google";

/**
 * Editorial serif for story headlines and prose. Charts, labels, and hero
 * numbers stay in the app's sans; the serif is never used for data.
 * Applied per story page (StoryRoot) so other routes don't load it.
 */
export const storySerif = Newsreader({
  subsets: ["latin"],
  style: ["normal", "italic"],
  axes: ["opsz"],
  variable: "--font-newsreader",
  display: "swap",
});
