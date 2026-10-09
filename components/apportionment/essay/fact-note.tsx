import * as React from "react";

import { Sidenote } from "@/components/story/sidenote";
import { citableFact } from "@/lib/apportionment/facts";

/**
 * A margin note citing an entry in data/apportionment/facts.json. Rendering
 * an unknown or unverified fact throws, so the build fails rather than
 * publishing an unsupported claim.
 */
export function FactNote({
  id,
  children,
}: {
  id: string;
  children?: React.ReactNode;
}) {
  const fact = citableFact(id);
  return (
    <Sidenote id={id} sources={fact.sources}>
      {children ?? fact.claim}
      {fact.status === "derived" && fact.derivation ? (
        <span className="mt-1 block text-story-muted">Computed: {fact.derivation}</span>
      ) : null}
    </Sidenote>
  );
}

/** Compact source line(s) for step cards, where margin notes don't fit. */
export function FactSources({ ids }: { ids: readonly string[] }) {
  const sources = ids.flatMap((id) => citableFact(id).sources);
  const unique = sources.filter(
    (source, index) => sources.findIndex((s) => s.url === source.url) === index
  );
  if (unique.length === 0) return null;
  return (
    <p className="mt-3 font-sans text-xs leading-relaxed text-story-muted">
      Source{unique.length > 1 ? "s" : ""}:{" "}
      {unique.map((source, index) => (
        <React.Fragment key={source.url}>
          {index > 0 ? "; " : null}
          <a
            href={source.url}
            className="underline decoration-story-axis underline-offset-2 hover:text-story-ink"
          >
            {source.title}
          </a>
        </React.Fragment>
      ))}
    </p>
  );
}
