import * as React from "react";

import { citableFacts } from "@/lib/apportionment/facts";

/**
 * Methods & sources: how the essay's numbers were made, then every claim it
 * may cite from data/apportionment/facts.json with its sources (and, for
 * derived claims, the computation).
 */
export function MethodsAndSources() {
  const facts = citableFacts();
  return (
    <section
      id="methods"
      aria-labelledby="methods-heading"
      className="mx-auto mt-24 max-w-[38rem] px-4 font-sans text-sm leading-relaxed text-story-ink-2"
    >
      <h2 id="methods-heading" className="font-story-serif text-2xl font-medium text-story-ink sm:text-3xl">
        Methods &amp; sources
      </h2>
      <div className="mt-4 space-y-3 [&_strong]:font-semibold [&_strong]:text-story-ink">
        <p>
          <strong>Seats.</strong> Seats per state for every apportionment from 1787 to 2020 come from the
          House Historian’s table, cross-checked against the U.S. Senate Manual and the Census Bureau’s
          historical apportionment data. The two disagree only through a documented convention and one
          Senate Manual erratum (Maine, 1860).
        </p>
        <p>
          <strong>People.</strong> National totals are census resident populations. State figures for 2020
          are apportionment populations: residents plus overseas military and federal employees who can be
          allocated to a home state. People per seat is resident population divided by seats through 1910,
          and the Census Bureau’s average apportionment population per representative from 1920.
        </p>
        <p>
          <strong>Every House size.</strong> Seats at any size are computed with the method of equal
          proportions, in law since 1941: once in Python when the essay’s data is built, and again in
          TypeScript in your browser. Tests check that both reproduce the published 2020 apportionment and
          agree with each other at every size from 435 to 11,036 seats.
        </p>
        <p>
          <strong>The person.</strong> The person is fictional: a role and a real congressional district,
          with circumstances drawn at random and checked so none contradicts another. Views are never
          inferred from occupation, faith or any other identity.
        </p>
        <p>
          <strong>Quotes.</strong> Quoted passages are verbatim from the sources cited, with omissions marked
          by ellipses.
        </p>
      </div>
      <details className="mt-6">
        <summary className="cursor-pointer font-semibold text-story-ink select-none">
          Every claim and its source ({facts.length})
        </summary>
        <ol className="mt-4 space-y-4">
          {facts.map((fact) => (
            <li key={fact.id}>
              <p className="text-story-ink">{fact.claim}</p>
              {fact.status === "derived" && fact.derivation ? (
                <p className="mt-1 text-xs text-story-muted">Computed: {fact.derivation}</p>
              ) : null}
              {fact.sources.length > 0 ? (
                <p className="mt-1 text-xs text-story-muted">
                  {fact.sources.map((source, index) => (
                    <React.Fragment key={source.url + index}>
                      {index > 0 ? "; " : null}
                      <a href={source.url} className="underline decoration-story-axis underline-offset-2 hover:text-story-ink">
                        {source.title}
                      </a>
                      {source.publisher ? `, ${source.publisher}` : null}
                      {source.locator ? ` (${source.locator})` : null}
                    </React.Fragment>
                  ))}
                </p>
              ) : null}
            </li>
          ))}
        </ol>
      </details>
    </section>
  );
}
