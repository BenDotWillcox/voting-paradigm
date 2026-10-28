import { pythonTokens } from "@/lib/methods/code-listing";
import { cn } from "@/lib/utils";
import type { ProfileResolveResponse, SimulationSummary, VotingMethod } from "@/types/methods";

import { TOKEN_CLASS } from "./code-view";
import { CandidateGlyph } from "./glyph";
import { CONTAINER } from "./section-band";

const WORDS = ["no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"];
const word = (count: number) => WORDS[count] ?? String(count);
const capitalized = (text: string) => text.charAt(0).toUpperCase() + text.slice(1);

// A wrapped session line continues under the code, past its prompt.
const HANG = { paddingLeft: "4ch", textIndent: "-4ch" } as const;

const CALLS: { method: VotingMethod; call: string; ballots: string }[] = [
  { method: "plurality", call: "resolve_plurality", ballots: "first_choices" },
  { method: "irv", call: "resolve_irv", ballots: "ranked" },
  { method: "ranked_pairs", call: "resolve_ranked_pairs", ballots: "ranked" },
];

/**
 * The thesis before anything else: one electorate, the package's three
 * calls, three different saved winners. Every count and winner comes from
 * the preset's stored resolution; the session elides only the inputs.
 */
export function MethodsHero({ label, resolution, simulation, criteria }: {
  label: string;
  resolution: ProfileResolveResponse;
  simulation: SimulationSummary;
  criteria: number;
}) {
  const methods = resolution.results.length;
  const winners = new Set(resolution.results.map((result) => result.winner)).size;
  const elections = simulation.config.elections * simulation.config.candidate_counts.length;
  const groups = resolution.rankings.rows.map((row) => row.count).join(" / ");
  const session = [
    "from voting import (resolve_irv, resolve_plurality,",
    "    resolve_ranked_pairs)",
    `candidates = [...]  # ${resolution.rankings.candidates.join(", ")}`,
    `ranked = [...]  # ${resolution.total_voters} voters: ${groups}`,
    "first_choices = [...]  # each voter's top choice",
  ];
  return (
    <header className="mi-island">
      <div className={cn(CONTAINER, "grid items-center gap-8 py-10 sm:gap-10 sm:py-20 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)] lg:gap-14")}>
        <div className="min-w-0 space-y-5">
          <p className="font-mi-mono text-sm text-mi-tone-1">Demo 01 · Voting methods</p>
          <h1 className="text-5xl font-semibold leading-[1.02] tracking-[-0.035em] text-mi-ink sm:text-6xl xl:text-7xl">
            <span className="block">Same voters.</span>
            <span className="block">{capitalized(word(methods))} rules.</span>
            <span className="block">{capitalized(word(winners))} {winners === 1 ? "winner" : "winners"}.</span>
          </h1>
          <p className="max-w-xl text-lg leading-relaxed text-mi-ink-2">One Python package counts the same {resolution.total_voters} ballots {word(methods)} ways. Read the code, see why the winners differ, then build your own electorate.</p>
          <p className="font-mi-mono text-sm text-mi-muted">{methods} methods · {criteria} criteria · {elections.toLocaleString("en-US")} seeded elections</p>
        </div>
        <figure className="min-w-0 space-y-3">
          <pre tabIndex={0} aria-label="A Python session calling three of the package's methods on this electorate" className="whitespace-pre-wrap break-words rounded-[6px] border border-mi-rule bg-mi-code p-4 font-mi-mono text-[0.8125rem] leading-7 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-mi-ink sm:p-5 sm:text-sm"><code>
            {session.map((line, index) => <span key={index} className="block" style={HANG}><Prompt continuation={index === 1} /><Tokens line={line} />{"\n"}</span>)}
            {CALLS.map(({ method, call, ballots }) => {
              const winner = resolution.results.find((result) => result.method === method)?.winner;
              return winner ? <span key={method} className="mt-2 block">
                <span className="block" style={HANG}><Prompt /><Tokens line={`${call}(candidates, ${ballots}).winners`} />{"\n"}</span>
                <span className="flex items-center gap-2.5 text-mi-code-plain"><CandidateGlyph id={winner} size={14} />[&apos;{winner}&apos;]{"\n"}</span>
              </span> : null;
            })}
          </code></pre>
          <figcaption className="font-mi-mono text-sm text-mi-muted">Saved package results · {label.toLowerCase()} · seed {resolution.tiebreak_seed}</figcaption>
        </figure>
      </div>
    </header>
  );
}

function Prompt({ continuation = false }: { continuation?: boolean }) {
  return <span aria-hidden className="select-none text-mi-code-comment">{continuation ? "... " : ">>> "}</span>;
}

function Tokens({ line }: { line: string }) {
  return <>{pythonTokens(line).map((token, index) => <span key={index} className={TOKEN_CLASS[token.kind]}>{token.text}</span>)}</>;
}
