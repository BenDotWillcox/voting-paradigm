"use client";

import { X } from "lucide-react";

import { CRITERIA, describeTransformation, roleLabel } from "@/lib/methods/gallery";
import { METHOD_META } from "@/lib/methods/instrument";
import { cn } from "@/lib/utils";
import type { Specimen, SpecimenRole } from "@/types/methods";

import { CandidateMark } from "./glyph";

/**
 * A gallery specimen loaded into the instrument: which of its profiles is
 * showing, what changes between them, and the failing method's winners.
 */
export function SpecimenBanner({
  specimen,
  role,
  maxVoters,
  onRole,
  onClose,
}: {
  specimen: Specimen;
  role: SpecimenRole;
  maxVoters: number;
  onRole: (role: SpecimenRole) => void;
  onClose: () => void;
}) {
  const method = METHOD_META[specimen.method].label;
  const criterion = CRITERIA.find((c) => c.id === specimen.criterion);
  const winner = (r: SpecimenRole) => specimen.profiles.find((p) => p.role === r)?.winner ?? "";

  let story: string;
  if (specimen.criterion === "consistency") {
    story = `Each electorate alone elects ${winner("first")} under ${method}. ${describeTransformation(specimen)} Together, ${method} elects ${winner("combined")}.`;
  } else if (specimen.transformation === null) {
    story = `${describeTransformation(specimen)} ${method} elects ${winner("profile")}.`;
  } else {
    story = `${method} elects ${winner("before")}. ${describeTransformation(specimen)} Then ${method} elects ${winner("after")}.`;
  }

  return (
    <section
      aria-label="Specimen"
      className="rounded-[4px] border border-mi-ink bg-mi-surface p-4"
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="font-mi-mono text-xs text-mi-muted">Specimen · {specimen.id}</p>
          <h2 className="mt-1 text-lg font-semibold text-mi-ink">
            {method} fails {criterion?.label.toLowerCase()}
          </h2>
          <p className="text-xs text-mi-muted">{criterion?.definition}</p>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close the specimen"
          title="Close the specimen"
          className="grid size-7 shrink-0 place-items-center rounded-[3px] text-mi-ink-2 hover:bg-mi-wash hover:text-mi-ink"
        >
          <X className="size-4" />
        </button>
      </div>

      <p className="mt-3 text-sm leading-relaxed text-mi-ink">{story}</p>

      {specimen.profiles.length > 1 ? (
        <div className="mt-3 flex flex-wrap gap-1.5" role="group" aria-label="Specimen profiles">
          {specimen.profiles.map((profile) => (
            <button
              key={profile.role}
              type="button"
              aria-pressed={profile.role === role}
              onClick={() => onRole(profile.role)}
              className={cn(
                "inline-flex items-center gap-2 rounded-[3px] border px-2.5 py-1 text-sm",
                profile.role === role
                  ? "border-mi-ink bg-mi-ink text-mi-surface"
                  : "border-mi-rule text-mi-ink hover:border-mi-ink"
              )}
            >
              {roleLabel(profile.role)}
              <span className="font-mi-mono text-xs opacity-80">
                {profile.rows.reduce((sum, [count]) => sum + count, 0)} voters
              </span>
              <span className="inline-flex items-center gap-1 text-xs">
                → <CandidateMark id={profile.winner} size={11} />
              </span>
            </button>
          ))}
        </div>
      ) : null}

      <p className="mt-3 text-xs leading-relaxed text-mi-muted">
        {specimen.ballot_model ? (
          <>
            The smallest electorate found: an exhaustive search of every three-candidate electorate
            of voter types up to {maxVoters} voters, re-checked against the reference
            implementation. Utilities load as found, and every ballot comes from the{" "}
            {specimen.ballot_model} model.
          </>
        ) : (
          <>
            The smallest electorate found: an exhaustive search of every three-candidate electorate
            up to {maxVoters} voters, re-checked against the reference implementation. Rankings
            load as evenly spaced voter types, so the rated counts assume that spacing.
          </>
        )}
      </p>
    </section>
  );
}
