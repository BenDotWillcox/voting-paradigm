/**
 * The video that opens /liquid (prompts/demo-5-walkthrough.md, "The video
 * opening and the trim"). Ben records it; it explains liquid democracy
 * against direct and representative voting, and carries no study numbers.
 *
 * Until it is recorded this stays null: the opening has no video, and the
 * readable version of the idea shows open. Once it exists, set it here.
 * Only the poster and the captions are committed (under public/); the video
 * file itself is hosted outside Git, on Cloudflare R2 first.
 */
export interface ExplainerVideo {
  /** The MP4's full URL. */
  src: string;
  /** A still shown before the video plays, as a public/ path. */
  poster: string;
  /** English captions as WebVTT, as a public/ path. */
  captions: string;
  /** The length in whole minutes, for the label. */
  minutes: number;
  /** One chapter per beat, in order: where it starts, in seconds, and its title. */
  chapters: ReadonlyArray<{ start: number; title: string }>;
}

export const EXPLAINER_VIDEO: ExplainerVideo | null = null;
