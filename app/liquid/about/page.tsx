import type { Metadata } from "next";
import { getDelegationScenario } from "@/lib/delegation-api";

export const metadata: Metadata = { title: "About · Liquid democracy" };

export default async function LiquidAboutPage() {
  const scenario = await getDelegationScenario().catch(() => null);

  return (
    <article className="max-w-3xl space-y-6 leading-relaxed">
      <h2 className="text-2xl font-semibold tracking-tight">What this demo is</h2>
      <p>
        Direct democracy asks every voter to research every question. Representative democracy
        gives you one person for everything. Liquid democracy sits between them: you hand
        particular kinds of decisions to people you trust, keep the rest, and can take any of
        it back. This demo is an account in a city that votes that way.
      </p>

      <section className="space-y-2">
        <h3 className="text-lg font-semibold">The three parts it has to get right</h3>
        <ul className="list-disc space-y-2 pl-5 text-muted-foreground">
          <li>
            <span className="font-medium text-foreground">Which category a question belongs to.</span>{" "}
            Categories are whatever each voter writes, so there is no shared list to file a
            question under. A hosted decision model
            {scenario ? ` (${scenario.model})` : ""} answers one yes/no question per category:
            is this ballot question about it? Code then applies a fixed rule. Categories under
            the {scenario ? scenario.threshold : 0.7} threshold drop out, a narrower category
            overrules a broader one it sits inside, the highest score left wins, and if nothing
            is left the vote stays with the voter.
          </li>
          <li>
            <span className="font-medium text-foreground">Processing an election.</span> A
            ballot is issued only to the residents of its jurisdiction. Each resident&apos;s vote
            on each question is routed separately, and whoever receives it applies their own
            delegations in turn. The person a vote ends with can live in another district or
            outside the city. A ballot counted for you is a copy of that person&apos;s ballot;
            there are no weighted votes.
          </li>
          <li>
            <span className="font-medium text-foreground">Loops.</span> A delegation that would
            hand a category straight back around a circle is refused when you make it. A loop
            that only appears for some questions, between differently worded categories, is
            allowed with a warning; when it happens, everyone on the loop keeps their own
            decision. Every vote therefore ends with exactly one person.
          </li>
        </ul>
      </section>

      <section className="space-y-2">
        <h3 className="text-lg font-semibold">What is made up</h3>
        <p className="text-muted-foreground">
          Everything about the city. The network is synthetic and seeded
          {scenario ? ` (seed ${scenario.seed})` : ""}: three districts of 80 residents, 20
          people outside the city who can still be delegates, and you. Names are invented. A
          third of people keep every decision; the rest hand three to seven categories to a
          well-known person or a neighbour. Those behaviours and their shares are assumptions
          chosen to make delegation visible. The measures are invented too. How each person
          votes comes from a toy model: a position on three issues, a lean for each district
          and a pull from living near a measure&apos;s site. Not everyone votes on everything;
          each person has a seeded chance of filling in a question, so a vote that ends with
          someone who did not vote is an abstention. Your account starts with eight
          delegations and a year of history so there is something to look at. None of it says
          how real voters would behave.
        </p>
      </section>

      <section className="space-y-2">
        <h3 className="text-lg font-semibold">What was measured</h3>
        <p className="text-muted-foreground">
          The decision model is not repeatable to the last digit, so its first answer to each
          question is recorded and every run replays the record. On a labelled set of 68
          questions and 30 categories, routing at the 0.7 threshold sent 4 of 292 delegated
          votes to a category the question was not about, and kept 21 of 309 votes that had an
          acceptable category. One author wrote both the categories and the labels, so those
          rates reflect the labels as well as the model.
        </p>
        <p className="text-muted-foreground">
          People write the same category in different words. A vote only ever moves under the
          words its voter wrote, but profiles and suggestions count wordings together when the
          decision model says each one sits inside the other. Of 20 extra wordings written for
          this city, it grouped 16 with the category they were written beside and read the
          other 4 as broader or narrower (“tax policy” as part of “all things taxes”, for
          one). It grouped no two categories that were written as different things. The same
          author wrote the wordings, so this is a small check, not a measurement.
        </p>
      </section>

      <section className="space-y-2">
        <h3 className="text-lg font-semibold">What it leaves out</h3>
        <p className="text-muted-foreground">
          Sign-in, identity checks, ballot secrecy and anything a real election needs to be
          trusted. Votes are public here, which is what makes a delegate&apos;s record readable
          and is also a real cost. Your changes are kept in this browser only. Deadlines count
          from the day you open the page.
        </p>
      </section>
    </article>
  );
}
