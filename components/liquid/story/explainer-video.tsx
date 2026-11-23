"use client";

import * as React from "react";

import type { ExplainerVideo as Video } from "@/lib/liquid/explainer-video";

/** "1:05" from 65 seconds. */
function clock(seconds: number): string {
  const whole = Math.max(0, Math.round(seconds));
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}

/**
 * The opening video, in the browser's own player: nothing loads until the
 * reader presses play, and no outside embed is involved. Captions are on by
 * default where the browser allows, and each chapter jumps the video to its
 * beat. A YouTube embed would replace only the player element.
 */
export function ExplainerVideo({ video }: { video: Video }) {
  const player = React.useRef<HTMLVideoElement | null>(null);

  const jump = (start: number) => {
    const node = player.current;
    if (!node) return;
    node.currentTime = start;
    void node.play().catch(() => undefined);
  };

  return (
    <figure className="mt-8 font-sans">
      <video
        ref={player}
        controls
        playsInline
        preload="none"
        poster={video.poster}
        className="aspect-video w-full rounded-lg bg-story-surface ring-1 ring-story-rule"
      >
        <source src={video.src} type="video/mp4" />
        <track kind="captions" src={video.captions} srcLang="en" label="English" default />
      </video>
      <figcaption className="mt-2 text-sm text-story-ink-2">
        Liquid democracy from the idea up, against direct and representative voting: {video.minutes} minutes, with
        captions. It states no results; the page below gives them.
      </figcaption>
      {video.chapters.length ? (
        <ol aria-label="Chapters" className="mt-3 grid gap-x-4 gap-y-1 text-sm sm:grid-cols-2">
          {video.chapters.map((chapter) => (
            <li key={chapter.start}>
              <button
                type="button"
                onClick={() => jump(chapter.start)}
                className="text-left text-story-ink-2 hover:text-story-ink"
              >
                <span className="mr-2 text-story-muted tabular-nums">{clock(chapter.start)}</span>
                {chapter.title}
              </button>
            </li>
          ))}
        </ol>
      ) : null}
    </figure>
  );
}
