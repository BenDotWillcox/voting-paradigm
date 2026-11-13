"use client";

import { useEffect, useMemo, useState } from "react";
import { Loader2 } from "lucide-react";
import { getCityVoteAction } from "@/actions/delegation-actions";
import type { CityResults, CityVote } from "@/types/delegation";
import { useAccount } from "./account-provider";
import { AppLink as Link } from "./app-link";
import { choiceLabel, findQuestion, optionName } from "./ballots";
import { ago, percent, personName, profileHref } from "./people";

// Validated together for a dark surface (dataviz validate_palette, all checks).
const OPTION_COLORS = ["#2f8fd0", "#d97706", "#8b5cf6", "#1fa97f"];
const OTHER_COLOR = "#8a8f98";

const HOMES = "";
const SITE_LETTERS = "ABCDEFGH";

/** A place in the unit square as SVG units; north is up. */
const at = ([x, y]: number[]) => ({ x: x * 100, y: (1 - y) * 100 });

type Key = { id: string; label: string; color: string };

/**
 * Port Alder drawn from the coordinates the simulation already has: the
 * three districts, where each resident lives, and, for a closed question,
 * the ballot that counted for each of them and whose it was.
 */
export function CityMap({ city }: { city: CityResults }) {
  const { scenario, directory } = useAccount();
  const [questionId, setQuestionId] = useState(HOMES);
  const [vote, setVote] = useState<CityVote | null>(null);
  const [failed, setFailed] = useState(false);
  const [lines, setLines] = useState(true);
  const [picked, setPicked] = useState<string | null>(null);

  useEffect(() => {
    let current = true;
    setVote(null);
    setFailed(false);
    if (questionId === HOMES) return;
    void getCityVoteAction(questionId).then((answer) => {
      if (!current) return;
      if (answer.isSuccess && answer.data) setVote(answer.data);
      else setFailed(true);
    });
    return () => {
      current = false;
    };
  }, [questionId]);

  const districts = scenario.jurisdictions.filter((place) => place.area);
  const residents = useMemo(
    () => scenario.persons.filter((person) => person.location),
    [scenario.persons],
  );
  const deciders = useMemo(
    () => new Map(city.deciders.map((entry) => [entry.person, entry.votes_decided])),
    [city.deciders],
  );
  const most = Math.max(1, ...deciders.values());

  const question = vote ? findQuestion(scenario, vote.question_id) : undefined;
  const approval = vote?.ballot_type === "approval";
  const winner = vote?.winners[0];

  // What a counted ballot is coloured by: its single or first choice, or for
  // an approval question whether it approved the option that won.
  const keys: Key[] = !vote
    ? []
    : approval
      ? [
          { id: "approved", label: `Approved ${optionName(question, winner ?? "")}`, color: OPTION_COLORS[0] },
          { id: "not", label: "Did not", color: OPTION_COLORS[1] },
        ]
      : vote.options.map((option, index) => ({
          id: option.id,
          label: vote.ballot_type === "ranked" ? `${option.name} first` : option.name,
          color: OPTION_COLORS[index] ?? OTHER_COLOR,
        }));
  const keyOf = (choice: string[] | null): Key | null => {
    if (!choice) return null;
    const id = approval ? (winner && choice.includes(winner) ? "approved" : "not") : choice[0];
    return keys.find((key) => key.id === id) ?? null;
  };

  const byPerson = useMemo(
    () => new Map((vote?.residents ?? []).map((resident) => [resident.person, resident])),
    [vote],
  );
  const counts = new Map<string, number>();
  let uncounted = 0;
  for (const resident of vote?.residents ?? []) {
    const key = keyOf(resident.choice);
    if (key) counts.set(key.id, (counts.get(key.id) ?? 0) + 1);
    else uncounted += 1;
  }

  // For a yes/no measure with one site: how people near it voted, and the rest.
  const single = vote && vote.sites.length === 1 && vote.ballot_type === "single_choice";
  const split = { near: [0, 0], far: [0, 0] };
  if (vote && single) {
    const [sx, sy] = vote.sites[0].location;
    for (const resident of vote.residents) {
      const home = directory.persons.get(resident.person)?.location;
      if (!home || !resident.choice) continue;
      const bucket = Math.hypot(home[0] - sx, home[1] - sy) <= vote.reach ? split.near : split.far;
      bucket[0] += resident.choice[0] === "yes" ? 1 : 0;
      bucket[1] += 1;
    }
  }

  const sited = city.questions.filter((row) => row.has_site);
  const unsited = city.questions.filter((row) => !row.has_site);
  const chosen = picked ? directory.persons.get(picked) : undefined;
  const chosenVote = picked ? byPerson.get(picked) : undefined;

  return (
    <section className="space-y-3">
      <h3 className="liquid-label">Map</h3>
      <div className="liquid-panel grid gap-5 p-4 lg:grid-cols-[minmax(0,34rem)_minmax(0,1fr)]">
        <div className="space-y-2">
          <svg
            viewBox="-1 -1 102 102"
            role="img"
            aria-label={
              vote
                ? `Map of ${scenario.city}: the ballot that counted for each resident on ${vote.title}. The table beside it gives the counts by district.`
                : `Map of ${scenario.city}: its three districts and where each resident lives.`
            }
            className="aspect-square w-full"
          >
            {districts.map((place) => {
              const [x0, y0, x1, y1] = place.area ?? [0, 0, 0, 0];
              const corner = at([x0, y1]);
              return (
                <g key={place.id}>
                  <rect
                    x={corner.x}
                    y={corner.y}
                    width={(x1 - x0) * 100}
                    height={(y1 - y0) * 100}
                    className="fill-white/[0.03] stroke-white/25"
                    strokeWidth={0.4}
                  />
                  <text
                    x={corner.x + 1.5}
                    y={corner.y + 4}
                    fontSize={3}
                    className="fill-muted-foreground font-mono uppercase"
                  >
                    {place.name}
                  </text>
                </g>
              );
            })}

            {vote && lines && (
              <g className="stroke-white/20" strokeWidth={0.18}>
                {vote.residents.map((resident) => {
                  if (resident.how !== "delegated") return null;
                  const from = directory.persons.get(resident.person)?.location;
                  const to = directory.persons.get(resident.resolver)?.location;
                  if (!from || !to) return null;
                  const a = at(from);
                  const b = at(to);
                  return <line key={resident.person} x1={a.x} y1={a.y} x2={b.x} y2={b.y} />;
                })}
              </g>
            )}

            {single && vote && (
              <circle
                cx={at(vote.sites[0].location).x}
                cy={at(vote.sites[0].location).y}
                r={vote.reach * 100}
                fill="none"
                className="stroke-white/40"
                strokeWidth={0.3}
                strokeDasharray="1.2 1.2"
              />
            )}

            {residents.map((person) => {
              const point = at(person.location ?? [0, 0]);
              const isViewer = person.id === directory.viewer;
              const select = () => setPicked(person.id === picked ? null : person.id);
              const ring = person.id === picked || isViewer;
              let dot: React.ReactNode;
              let title = `${person.name}`;
              if (!vote) {
                const held = deciders.get(person.id);
                dot = held ? (
                  <circle r={1.1 + (held / most) * 1.6} className="fill-primary" />
                ) : (
                  <circle r={0.75} className="fill-muted-foreground" opacity={0.75} />
                );
                if (held) title += `: decided ${held} votes for others`;
              } else {
                const resident = byPerson.get(person.id);
                const key = resident ? keyOf(resident.choice) : null;
                if (!resident) {
                  dot = <circle r={0.6} className="fill-muted-foreground" opacity={0.2} />;
                  title += ": not issued this question";
                } else if (!key) {
                  dot = (
                    <circle r={0.8} fill="none" className="stroke-muted-foreground" strokeWidth={0.3} />
                  );
                  title += ": no ballot counted";
                } else {
                  dot = <circle r={0.95} fill={key.color} />;
                  title += `: ${key.label}${
                    resident.how === "delegated"
                      ? `, decided by ${personName(directory, resident.resolver)}`
                      : ""
                  }`;
                }
              }
              return (
                <g
                  key={person.id}
                  transform={`translate(${point.x} ${point.y})`}
                  className="cursor-pointer"
                  onClick={select}
                >
                  <title>{title}</title>
                  {/* A larger target than the mark */}
                  <circle r={1.8} fill="transparent" />
                  {dot}
                  {ring && (
                    <circle r={2.1} fill="none" className="stroke-white" strokeWidth={0.35} />
                  )}
                  {isViewer && (
                    <text x={2.8} y={1} fontSize={2.6} className="fill-foreground font-medium">
                      You
                    </text>
                  )}
                </g>
              );
            })}

            {vote?.sites.map((site, index) => {
              const point = at(site.location);
              return (
                <g key={site.option} transform={`translate(${point.x} ${point.y})`}>
                  <title>{site.name}</title>
                  <rect
                    x={-1.7}
                    y={-1.7}
                    width={3.4}
                    height={3.4}
                    transform="rotate(45)"
                    className="fill-background stroke-white"
                    strokeWidth={0.4}
                  />
                  <text
                    y={0.95}
                    fontSize={2.6}
                    textAnchor="middle"
                    className="fill-foreground font-mono font-semibold"
                  >
                    {SITE_LETTERS[index]}
                  </text>
                </g>
              );
            })}
          </svg>
          <p className="text-xs text-muted-foreground">
            Homes are seeded points in each district’s part of a unit square. The city has no
            streets; only distance to a site matters. Select a dot for the person.
          </p>
        </div>

        <div className="min-w-0 space-y-4 text-sm">
          <div className="space-y-1.5">
            <label htmlFor="city-map-question" className="liquid-label block">
              Show
            </label>
            <select
              id="city-map-question"
              value={questionId}
              onChange={(event) => {
                setQuestionId(event.target.value);
                setPicked(null);
              }}
              className="w-full rounded-md border bg-background px-2 py-1.5 text-sm"
            >
              <option value={HOMES}>Where people live, and who decides most</option>
              <optgroup label="Closed votes about a place">
                {sited.map((row) => (
                  <option key={row.question_id} value={row.question_id}>
                    {row.title}
                  </option>
                ))}
              </optgroup>
              <optgroup label="Other closed votes">
                {unsited.map((row) => (
                  <option key={row.question_id} value={row.question_id}>
                    {row.title}
                  </option>
                ))}
              </optgroup>
            </select>
          </div>

          {questionId === HOMES && (
            <ul className="space-y-1.5 text-muted-foreground">
              <li className="flex items-center gap-2">
                <svg viewBox="0 0 10 10" className="h-3.5 w-3.5 shrink-0" aria-hidden="true">
                  <circle cx={5} cy={5} r={4.5} className="fill-primary" />
                </svg>
                One of the {city.deciders.length} people who decided the most votes for others;
                larger means more.{" "}
                {residents.filter((person) => deciders.has(person.id)).length} live in the city
              </li>
              <li className="flex items-center gap-2">
                <svg viewBox="0 0 10 10" className="h-3.5 w-3.5 shrink-0" aria-hidden="true">
                  <circle cx={5} cy={5} r={2.2} className="fill-muted-foreground" />
                </svg>
                A resident ({residents.length} in all)
              </li>
              <li className="flex items-center gap-2">
                <svg viewBox="0 0 10 10" className="h-3.5 w-3.5 shrink-0" aria-hidden="true">
                  <circle cx={5} cy={5} r={4} fill="none" className="stroke-white" strokeWidth={1} />
                </svg>
                You, or the person selected
              </li>
            </ul>
          )}

          {questionId !== HOMES && failed && (
            <p className="text-muted-foreground">This vote could not be loaded just now.</p>
          )}
          {questionId !== HOMES && !vote && !failed && (
            <p className="flex items-center gap-2 text-muted-foreground">
              <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
              Loading the vote…
            </p>
          )}

          {vote && (
            <>
              <p>
                <Link
                  href={`/liquid/votes/${vote.question_id}`}
                  className="font-medium underline-offset-4 hover:underline"
                >
                  {vote.title}
                </Link>
                <span className="block font-mono text-xs text-muted-foreground">
                  {vote.label} · {directory.jurisdictions.get(vote.jurisdiction) ?? vote.jurisdiction}{" "}
                  · closed {ago(vote.closed_days_ago)}
                </span>
              </p>

              <ul className="space-y-1.5">
                {keys.map((key) => (
                  <li key={key.id} className="flex items-center gap-2">
                    <span
                      className="h-3 w-3 shrink-0 rounded-full"
                      style={{ background: key.color }}
                      aria-hidden="true"
                    />
                    <span>{key.label}</span>
                    <span className="ml-auto font-mono tabular-nums text-muted-foreground">
                      {counts.get(key.id) ?? 0}
                    </span>
                  </li>
                ))}
                <li className="flex items-center gap-2 text-muted-foreground">
                  <span
                    className="h-3 w-3 shrink-0 rounded-full border border-muted-foreground"
                    aria-hidden="true"
                  />
                  <span>No ballot counted</span>
                  <span className="ml-auto font-mono tabular-nums">{uncounted}</span>
                </li>
                {vote.sites.map((site, index) => (
                  <li key={site.option} className="flex items-center gap-2 text-muted-foreground">
                    <span className="w-3 shrink-0 text-center font-mono text-xs font-semibold text-foreground">
                      {SITE_LETTERS[index]}
                    </span>
                    <span>{vote.sites.length > 1 ? site.name : "Where it would be"}</span>
                  </li>
                ))}
              </ul>

              {single && split.near[1] > 0 && split.far[1] > 0 && (
                <p className="text-muted-foreground">
                  Inside the dashed circle{" "}
                  <span className="text-foreground">
                    {percent(split.near[0] / split.near[1])} voted yes
                  </span>{" "}
                  ({split.near[0]} of {split.near[1]} ballots). Further away it was{" "}
                  <span className="text-foreground">{percent(split.far[0] / split.far[1])}</span> (
                  {split.far[0]} of {split.far[1]}).
                </p>
              )}

              <label className="flex items-center gap-2 text-muted-foreground">
                <input
                  type="checkbox"
                  checked={lines}
                  onChange={(event) => setLines(event.target.checked)}
                />
                Draw a line from each delegated vote to whoever decided it
              </label>

              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <caption className="sr-only">Ballots that counted, by district</caption>
                  <thead className="text-muted-foreground">
                    <tr>
                      <th scope="col" className="py-1 pr-3 font-normal">
                        District
                      </th>
                      {vote.options.map((option) => (
                        <th key={option.id} scope="col" className="py-1 pr-3 text-right font-normal">
                          {option.name}
                        </th>
                      ))}
                      <th scope="col" className="py-1 text-right font-normal">
                        Not counted
                      </th>
                    </tr>
                  </thead>
                  <tbody className="font-mono tabular-nums">
                    {vote.districts.map((district) => (
                      <tr key={district.jurisdiction} className="border-t">
                        <th scope="row" className="py-1 pr-3 font-sans font-normal">
                          {directory.jurisdictions.get(district.jurisdiction) ??
                            district.jurisdiction}
                        </th>
                        {vote.options.map((option) => (
                          <td key={option.id} className="py-1 pr-3 text-right">
                            {district.by_option[option.id] ?? 0}
                          </td>
                        ))}
                        <td className="py-1 text-right">{district.voters - district.counted}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {vote.ballot_type !== "single_choice" && (
                  <p className="pt-1 text-xs text-muted-foreground">
                    {approval
                      ? "Each ballot counts once for every option it approved."
                      : "First choices only."}
                  </p>
                )}
              </div>
            </>
          )}

          {chosen && (
            <div className="space-y-1 border-t pt-3">
              <p>
                <Link
                  href={profileHref(directory, chosen.id)}
                  className="font-medium underline-offset-4 hover:underline"
                >
                  {chosen.name}
                </Link>{" "}
                <span className="text-muted-foreground">
                  @{chosen.username} · {directory.jurisdictions.get(chosen.home ?? "") ?? ""}
                </span>
              </p>
              {!vote && deciders.has(chosen.id) && (
                <p className="text-muted-foreground">
                  Decided {deciders.get(chosen.id)} votes for other people across the closed
                  questions.
                </p>
              )}
              {vote && (
                <p className="text-muted-foreground">
                  {!chosenVote
                    ? "Was not issued this question."
                    : !chosenVote.choice
                      ? chosenVote.how === "delegated"
                        ? `Their vote went to ${personName(directory, chosenVote.resolver)}, who did not vote.`
                        : "Did not vote."
                      : chosenVote.how === "delegated"
                        ? `Their vote was decided by ${personName(directory, chosenVote.resolver)}: ${choiceLabel(question, chosenVote.choice)}.`
                        : `Voted ${choiceLabel(question, chosenVote.choice)}.`}
                </p>
              )}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
