"use client";

import { Minus, Plus, X } from "lucide-react";

import { MAX_CANDIDATES, MIN_CANDIDATES } from "@/lib/methods/candidates";
import {
  MAX_ROW_COUNT,
  addCandidate,
  addRow,
  rankingOf,
  removeCandidate,
  removeRow,
  setRowCount,
  setUtility,
  totalVoters,
} from "@/lib/methods/profile";
import { cn } from "@/lib/utils";
import type { UtilityProfile } from "@/types/methods";

import { CandidateGlyph, CandidateMark } from "./glyph";
import { UtilityTrack } from "./utility-track";

/**
 * The electorate as voter types: how many voters share one placement of the
 * candidates on a 0–10 track. Order along the track is their ranking;
 * spacing is intensity. Editing a row selects it for the ballots panel.
 */
export function ProfileEditor({
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
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3 text-sm">
        <div className="flex items-center gap-2">
          <span className="text-mi-ink-2">Candidates</span>
          <IconButton
            label="Remove the last candidate"
            disabled={profile.candidates.length <= MIN_CANDIDATES}
            onClick={() => onChange(removeCandidate(profile))}
          >
            <Minus className="size-3.5" />
          </IconButton>
          <span className="flex gap-2">
            {profile.candidates.map((id) => (
              <CandidateMark key={id} id={id} size={13} className="text-sm" />
            ))}
          </span>
          <IconButton
            label="Add a candidate"
            disabled={profile.candidates.length >= MAX_CANDIDATES}
            onClick={() => onChange(addCandidate(profile))}
          >
            <Plus className="size-3.5" />
          </IconButton>
        </div>
        <span className="font-mi-mono text-mi-ink-2">
          {voters} {voters === 1 ? "voter" : "voters"}
        </span>
      </div>

      {/* Same columns as a row, so the labels sit over the track's 0, 5 and 10 */}
      <div className="flex items-center gap-1 pl-1" aria-hidden>
        <span className="w-[5.75rem] shrink-0" />
        <span className="relative mx-2.5 h-4 flex-1 font-mi-mono text-[0.6875rem] text-mi-muted">
          <span className="absolute left-0">0 worst</span>
          <span className="absolute left-1/2 -translate-x-1/2">5</span>
          <span className="absolute right-0">best 10</span>
        </span>
        <span className="w-7 shrink-0" />
      </div>

      <ol className="divide-y divide-mi-rule border-y border-mi-rule">
        {profile.rows.map((row, index) => (
          <li
            key={index}
            className={cn(
              "relative py-1.5 pl-1",
              index === selected && "bg-mi-wash before:absolute before:inset-y-0 before:left-0 before:w-0.5 before:bg-mi-ink"
            )}
            onPointerDownCapture={() => onSelect(index)}
            onFocusCapture={() => onSelect(index)}
          >
            <div className="flex items-center gap-1">
              <CountInput
                value={row.count}
                label={`Voters of type ${index + 1}`}
                onChange={(count) => onChange(setRowCount(profile, index, count))}
              />
              <UtilityTrack
                candidates={profile.candidates}
                utilities={row.utilities}
                label={`Voter type ${index + 1}: utilities`}
                onChange={(candidate, value) =>
                  onChange(setUtility(profile, index, candidate, value))
                }
              />
              <IconButton
                label={`Remove voter type ${index + 1}`}
                disabled={profile.rows.length <= 1}
                onClick={() => onChange(removeRow(profile, index))}
              >
                <X className="size-3.5" />
              </IconButton>
            </div>
            <p className="ml-[6.875rem] flex items-center gap-1 font-mi-mono text-[0.6875rem] text-mi-muted">
              <span className="sr-only">Ranking:</span>
              {rankingOf(profile.candidates, row).map((id, position) => (
                <span key={id} className="inline-flex items-center gap-0.5">
                  {position > 0 ? <span aria-hidden>›</span> : null}
                  <CandidateGlyph id={id} size={9} />
                  {id}
                </span>
              ))}
            </p>
          </li>
        ))}
      </ol>

      <button
        type="button"
        onClick={() => {
          onChange(addRow(profile));
          onSelect(profile.rows.length);
        }}
        className="inline-flex items-center gap-1.5 rounded-[3px] border border-mi-rule px-2.5 py-1 text-sm text-mi-ink hover:bg-mi-wash focus-visible:outline-1 focus-visible:outline-mi-ink"
      >
        <Plus className="size-3.5" aria-hidden /> Add a voter type
      </button>
      <p className="text-xs leading-relaxed text-mi-muted">
        Drag a candidate along its track, or focus it and use the arrow keys. Order is
        the ranking; distance is how strongly the voter prefers one to another.
      </p>
    </div>
  );
}

export function CountInput({
  value,
  label,
  onChange,
}: {
  value: number;
  label: string;
  onChange: (count: number) => void;
}) {
  return (
    <span className="flex shrink-0 items-center">
      <IconButton compact label={`Fewer: ${label}`} disabled={value <= 0} onClick={() => onChange(value - 1)}>
        <Minus className="size-3" />
      </IconButton>
      <input
        type="number"
        inputMode="numeric"
        min={0}
        max={MAX_ROW_COUNT}
        value={value}
        aria-label={label}
        onChange={(event) => {
          const next = Number.parseInt(event.target.value, 10);
          onChange(Number.isFinite(next) ? next : 0);
        }}
        className={cn(
          "h-8 w-11 rounded-[3px] border border-mi-rule bg-mi-surface text-center font-mi-mono text-sm text-mi-ink",
          "[appearance:textfield] focus-visible:border-mi-ink focus-visible:outline-none",
          "[&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
        )}
      />
      <IconButton
        compact
        label={`More: ${label}`}
        disabled={value >= MAX_ROW_COUNT}
        onClick={() => onChange(value + 1)}
      >
        <Plus className="size-3" />
      </IconButton>
    </span>
  );
}

export function IconButton({
  label,
  disabled,
  compact,
  onClick,
  children,
}: {
  label: string;
  disabled?: boolean;
  compact?: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      disabled={disabled}
      onClick={onClick}
      className={`grid shrink-0 ${compact ? "size-6" : "size-7"} place-items-center rounded-[3px] text-mi-ink-2 hover:bg-mi-wash hover:text-mi-ink focus-visible:outline-1 focus-visible:outline-mi-ink disabled:opacity-35 disabled:hover:bg-transparent`}
    >
      {children}
    </button>
  );
}
