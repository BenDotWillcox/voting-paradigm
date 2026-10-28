"use client";

import { rankingOf, setRowCount, totalVoters } from "@/lib/methods/profile";
import { cn } from "@/lib/utils";
import type { UtilityProfile } from "@/types/methods";

import { CandidateGlyph } from "./glyph";
import { CountInput } from "./profile-editor";

/**
 * The playground's basic control: each voter type's ranking and a count
 * stepper. Utilities, voter types and candidates are edited under Advanced
 * controls. Choosing a row selects that voter type for the ballots.
 */
export function VoterCounts({
  profile,
  selected,
  onSelect,
  onChange,
}: {
  profile: UtilityProfile;
  selected: number;
  onSelect: (row: number) => void;
  onChange: (profile: UtilityProfile) => void;
}) {
  const voters = totalVoters(profile);
  return (
    <div>
      <p className="mb-1.5 flex justify-between text-xs text-mi-muted">
        <span>Voter types</span>
        <span className="font-mi-mono">
          {voters} {voters === 1 ? "voter" : "voters"}
        </span>
      </p>
      <ol className="divide-y divide-mi-rule border-y border-mi-rule">
        {profile.rows.map((row, index) => (
          <li
            key={index}
            className={cn(
              "relative flex items-center gap-2 py-1 pl-1.5",
              index === selected &&
                "bg-mi-wash before:absolute before:inset-y-0 before:left-0 before:w-0.5 before:bg-mi-ink"
            )}
            onPointerDownCapture={() => onSelect(index)}
            onFocusCapture={() => onSelect(index)}
          >
            <CountInput
              value={row.count}
              label={`Voters of type ${index + 1}`}
              onChange={(count) => onChange(setRowCount(profile, index, count))}
            />
            <button
              type="button"
              onClick={() => onSelect(index)}
              aria-label={`Voter type ${index + 1}: ${rankingOf(profile.candidates, row).join(" over ")}`}
              className="flex min-h-11 min-w-0 flex-1 flex-wrap items-center gap-1 rounded-[3px] px-1 py-1 text-left font-mi-mono text-sm text-mi-ink-2 hover:text-mi-ink sm:min-h-0 sm:text-xs"
            >
              {rankingOf(profile.candidates, row).map((id, position) => (
                <span key={id} className="inline-flex items-center gap-0.5">
                  {position > 0 ? <span aria-hidden>›</span> : null}
                  <CandidateGlyph id={id} size={10} className="size-3.5 sm:size-2.5" />
                  {id}
                </span>
              ))}
            </button>
          </li>
        ))}
      </ol>
    </div>
  );
}
