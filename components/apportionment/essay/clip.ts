import type { Fact } from "@/lib/apportionment/facts";

import type { StageClip } from "./house-stage";

/**
 * A clip of a verified quote from the fact register, shown verbatim. With
 * `excerpt`, the clip opens on those verbatim segments of the quote (joined
 * by ellipses) and the full passage is a click away; highlights must then
 * fall inside the excerpt.
 */
export function clipOf(
  fact: Fact,
  label: string,
  extra: Pick<StageClip, "highlights" | "stamp"> & { moreSources?: Fact[]; excerpt?: readonly string[] } = {}
): StageClip {
  if (!fact.quote) throw new Error(`Fact "${fact.id}" has no quote to clip`);
  const quote = fact.quote;
  let excerpt: string | undefined;
  if (extra.excerpt && extra.excerpt.length > 0) {
    for (const segment of extra.excerpt) {
      if (!quote.includes(segment)) throw new Error(`Excerpt not in "${fact.id}": ${segment}`);
    }
    const first = extra.excerpt[0];
    const last = extra.excerpt[extra.excerpt.length - 1];
    excerpt =
      (quote.startsWith(first) ? "" : "… ") + extra.excerpt.join(" … ") + (quote.endsWith(last) ? "" : " …");
  }
  const sources = [fact, ...(extra.moreSources ?? [])].flatMap((f) =>
    f.sources.map((source) => ({ title: source.title, url: source.url }))
  );
  for (const h of extra.highlights ?? []) {
    if (!(excerpt ?? quote).includes(h.text)) throw new Error(`Highlight not in "${fact.id}": ${h.text}`);
  }
  return {
    id: fact.id,
    label,
    quote,
    excerpt,
    highlights: extra.highlights,
    stamp: extra.stamp,
    sources: sources.filter((s, i) => sources.findIndex((t) => t.url === s.url) === i),
  };
}
