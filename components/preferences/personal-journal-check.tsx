import { Button } from "@/components/ui/button";
import type { JournalCheck, JournalEntry, JournalPrediction } from "@/lib/personal-journal-types";

type Revealed = Extract<JournalEntry, { status: "revealed" }>;
type Paired = Revealed & { comparison: NonNullable<Revealed["comparison"]> };
export function hasPairedForecasts(entry: Revealed): entry is Paired {
  return !!entry.comparison;
}
const forecasts = [
  { label: "Original baseline", get: (entry: Paired) => entry.comparison.baseline },
  { label: "New model with reasoning", get: (entry: Paired) => entry.prediction },
  { label: "New model without reasoning", get: (entry: Paired) => entry.comparison.withoutReasoning },
];
const percent = new Intl.NumberFormat(undefined, { style: "percent", maximumFractionDigits: 1 });

function brier(prediction: JournalPrediction, vote: Revealed["vote"]) {
  return (prediction.probabilityYes - (vote === "yes" ? 1 : 0)) ** 2;
}

export function PairedPredictions({ entry }: { entry: Paired }) {
  return (
    <section aria-label="Locked forecasts" className="space-y-3 rounded-lg border border-foreground/20 p-4 sm:p-5">
      <div><h3 className="font-semibold">Your vote was {entry.vote === "yes" ? "Yes" : "No"}</h3>
        {entry.forecastMeasure && <p className="mt-1 text-sm text-muted-foreground">These forecasts used the original wording. This corrected entry is excluded from the check scores.</p>}
      </div>
      <table className="w-full text-left text-sm">
        <caption className="sr-only">Forecasts locked before your vote</caption>
        <thead className="border-b text-muted-foreground"><tr>
          <th scope="col" className="pb-2 font-normal">Forecast</th><th scope="col" className="pb-2 pl-2 font-normal">Vote</th>
          <th scope="col" className="pb-2 pl-2 text-right font-normal">Chance of Yes</th>
        </tr></thead>
        <tbody className="divide-y">{forecasts.map(({ label, get }) => {
          const prediction = get(entry);
          return <tr key={label}><th scope="row" className="py-2 font-medium">{label}</th>
            <td className="py-2 pl-2">{prediction.choice === "yes" ? "Yes" : "No"}</td>
            <td className="py-2 pl-2 text-right tabular-nums">{percent.format(prediction.probabilityYes)}</td></tr>;
        })}</tbody>
      </table>
      <details><summary className="cursor-pointer text-sm font-medium">Forecast explanations</summary>
        <dl className="mt-3 space-y-3 text-sm">{forecasts.map(({ label, get }) => <div key={label}>
          <dt className="font-semibold">{label}</dt><dd className="mt-1 whitespace-pre-wrap break-words">{get(entry).explanation}</dd>
          <dd className="mt-1 break-words text-xs text-muted-foreground">{get(entry).model}</dd>
        </div>)}</dl>
      </details>
    </section>
  );
}

export function FiveMeasureCheck({ check, entries, busy, onStart }: {
  check: JournalCheck | null; entries: JournalEntry[]; busy: boolean; onStart: () => void;
}) {
  const members = check ? entries.filter(entry => entry.checkId === check.id) : [];
  const revealed = members.filter((entry): entry is Revealed => entry.status === "revealed");
  const scored = revealed.filter((entry): entry is Paired => !!entry.comparison && !entry.forecastMeasure && !entry.measure.familiar);
  const corrected = revealed.filter(entry => entry.forecastMeasure).length;
  const familiar = revealed.filter(entry => !entry.forecastMeasure && entry.measure.familiar).length;
  const changes = scored.map(entry =>
    (entry.prediction.probabilityYes - entry.comparison.withoutReasoning.probabilityYes) * (entry.vote === "yes" ? 1 : -1));
  return (
    <section aria-label="Five-measure check" className="mb-6 space-y-3 rounded-lg border bg-card p-4 sm:p-5">
      <h2 className="font-serif text-2xl tracking-tight">Five-measure check</h2>
      {check ? <>
        <p className="text-sm"><strong>{members.length} of {check.slotIds.length}</strong> measures locked · {revealed.length} voted · {scored.length} scored</p>
        <p className="text-sm text-muted-foreground">Evidence frozen from {check.evidenceCount} prior {check.evidenceCount === 1 ? "vote" : "votes"} and {check.clarificationCount} saved follow-up {check.clarificationCount === 1 ? "answer" : "answers"}.</p>
        {scored.length > 0 && <>
          <table className="w-full text-left text-sm">
            <caption className="sr-only">Results on the same {scored.length} eligible measures</caption>
            <thead className="border-b text-muted-foreground"><tr><th scope="col" className="pb-2 font-normal">Forecast</th>
              <th scope="col" className="pb-2 pl-2 font-normal">Correct</th><th scope="col" className="pb-2 pl-2 text-right font-normal">Mean Brier score</th></tr></thead>
            <tbody className="divide-y">{forecasts.map(({ label, get }) => {
              const correct = scored.filter(entry => get(entry).choice === entry.vote).length;
              const mean = scored.reduce((sum, entry) => sum + brier(get(entry), entry.vote), 0) / scored.length;
              return <tr key={label}><th scope="row" className="py-2 font-medium">{label}</th><td className="py-2 pl-2 tabular-nums">{correct}/{scored.length}</td>
                <td className="py-2 pl-2 text-right tabular-nums">{mean.toFixed(3)}</td></tr>;
            })}</tbody>
          </table>
          <p className="text-sm">Adding your reasoning moved the probability toward your vote on <strong>{changes.filter(change => change > 0).length}</strong> of {scored.length}, away on {changes.filter(change => change < 0).length}, and left it unchanged on {changes.filter(change => change === 0).length}.</p>
          <p className="text-sm text-muted-foreground">A lower Brier score means the probabilities were closer to your votes across these measures.</p>
        </>}
        {corrected > 0 && <p className="text-sm text-muted-foreground">{corrected} {corrected === 1 ? "entry was" : "entries were"} excluded after a wording correction.</p>}
        {familiar > 0 && <p className="text-sm text-muted-foreground">{familiar} familiar {familiar === 1 ? "entry was" : "entries were"} excluded.</p>}
      </> : <>
        <p className="max-w-3xl text-sm text-muted-foreground">Finish any follow-ups you want to include, then freeze your evidence for five measures that are new to you. Each measure gets the original baseline and the new model with and without your reasoning.</p>
        <Button variant="outline" disabled={busy} onClick={onStart}>Start five-measure check</Button>
      </>}
    </section>
  );
}
