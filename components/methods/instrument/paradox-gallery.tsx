"use client";

import { Check, X } from "lucide-react";
import { useState } from "react";

import {
  CRITERIA,
  GALLERY_METHODS,
  describeTransformation,
  galleryCell,
  type GalleryCell,
} from "@/lib/methods/gallery";
import { METHOD_META } from "@/lib/methods/instrument";
import { cn } from "@/lib/utils";
import type { CriterionId, RankedMethod, Specimen, SpecimenSearch } from "@/types/methods";

/**
 * Methods × criteria. A failure with a specimen opens that specimen in the
 * instrument; a cell settled by proof or citation shows its reason here.
 */
export function ParadoxGallery({
  searches,
  activeSpecimen,
  onOpen,
}: {
  searches: SpecimenSearch[];
  activeSpecimen: string | null;
  onOpen: (specimen: Specimen) => void;
}) {
  const [noted, setNoted] = useState<{ method: RankedMethod; criterion: CriterionId } | null>(null);
  const note = noted ? galleryCell(searches, noted.method, noted.criterion) : null;

  return (
    <div className="space-y-4">
      <p className="max-w-3xl text-sm leading-relaxed text-mi-ink-2">
        Every ranked method fails some criterion. Each ✗ with a number is the smallest
        three-candidate electorate an exhaustive search found where the method fails, re-checked
        against the reference implementation; open it to load it above. A ✓ is a proof, not
        an empty search.
      </p>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[46rem] border-collapse text-sm">
          <caption className="sr-only">Ranked methods against eight criteria</caption>
          <thead>
            <tr className="border-b border-mi-rule">
              <th className="py-2 pr-3 text-left text-xs font-normal text-mi-muted">Method</th>
              {CRITERIA.map((criterion) => (
                <th
                  key={criterion.id}
                  scope="col"
                  title={`${criterion.label}: ${criterion.definition}`}
                  className="px-1 py-2 text-center text-xs font-normal text-mi-muted"
                >
                  {criterion.short}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {GALLERY_METHODS.map((method) => (
              <tr key={method} className="border-b border-mi-rule last:border-0">
                <th scope="row" className="py-1.5 pr-3 text-left font-medium text-mi-ink">
                  {METHOD_META[method].label}
                </th>
                {CRITERIA.map((criterion) => {
                  const cell = galleryCell(searches, method, criterion.id);
                  const active =
                    cell.kind === "specimen"
                      ? cell.specimen.id === activeSpecimen
                      : noted?.method === method && noted.criterion === criterion.id;
                  return (
                    <td key={criterion.id} className="px-1 py-1.5 text-center">
                      <CellButton
                        cell={cell}
                        label={`${METHOD_META[method].label}, ${criterion.label}`}
                        active={active}
                        onClick={() => {
                          if (cell.kind === "specimen") {
                            setNoted(null);
                            onOpen(cell.specimen);
                          } else {
                            setNoted({ method, criterion: criterion.id });
                          }
                        }}
                      />
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-mi-muted">
        <span className="inline-flex items-center gap-1.5">
          <Swatch kind="fail" /> fails: smallest specimen, voters
        </span>
        <span className="inline-flex items-center gap-1.5">
          <Swatch kind="cited" /> fails: known theorem, beyond the search
        </span>
        <span className="inline-flex items-center gap-1.5">
          <Swatch kind="pass" /> satisfies: proof
        </span>
        <span>Approval, score and quadratic cells come with the next slice.</span>
      </div>

      {noted && note ? <CellNote method={noted.method} criterion={noted.criterion} cell={note} /> : null}
    </div>
  );
}

function CellButton({
  cell,
  label,
  active,
  onClick,
}: {
  cell: GalleryCell;
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  const failsBySpecimen = cell.kind === "specimen";
  const failsByCitation = cell.kind === "cited" && cell.cited.verdict === "fails";
  const description = failsBySpecimen
    ? `fails; smallest specimen has ${cell.specimen.voters} voters. Open it.`
    : failsByCitation
      ? "fails by a known theorem; show why"
      : cell.kind === "cited"
        ? "satisfies; show the proof"
        : "unsettled";
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      aria-label={`${label}: ${description}`}
      className={cn(
        "inline-flex h-8 min-w-[3.25rem] items-center justify-center gap-1 rounded-[3px] px-2 font-mi-mono text-xs",
        "focus-visible:outline-1 focus-visible:outline-offset-1 focus-visible:outline-mi-ink",
        failsBySpecimen && "bg-mi-ink text-mi-surface hover:opacity-85",
        failsByCitation && "border border-mi-ink text-mi-ink hover:bg-mi-wash",
        !failsBySpecimen && !failsByCitation && "text-mi-ink-2 hover:bg-mi-wash",
        active && "ring-2 ring-mi-ink ring-offset-1 ring-offset-mi-surface"
      )}
    >
      {failsBySpecimen ? (
        <>
          <X className="size-3" aria-hidden />
          {cell.specimen.voters}
        </>
      ) : failsByCitation ? (
        <>
          <X className="size-3" aria-hidden />
          cited
        </>
      ) : cell.kind === "cited" ? (
        <Check className="size-3.5" aria-hidden />
      ) : (
        "?"
      )}
    </button>
  );
}

function Swatch({ kind }: { kind: "fail" | "cited" | "pass" }) {
  return (
    <span
      aria-hidden
      className={cn(
        "grid size-4 place-items-center rounded-[3px]",
        kind === "fail" && "bg-mi-ink text-mi-surface",
        kind === "cited" && "border border-mi-ink text-mi-ink",
        kind === "pass" && "text-mi-ink-2"
      )}
    >
      {kind === "pass" ? <Check className="size-3" /> : <X className="size-2.5" />}
    </span>
  );
}

function CellNote({
  method,
  criterion,
  cell,
}: {
  method: RankedMethod;
  criterion: CriterionId;
  cell: GalleryCell;
}) {
  const definition = CRITERIA.find((c) => c.id === criterion);
  return (
    <div className="rounded-[3px] border border-mi-rule p-3 text-sm" aria-live="polite">
      <p className="font-medium text-mi-ink">
        {METHOD_META[method].label} ·{" "}
        {cell.kind === "cited" ? cell.cited.verdict : "unsettled"} {definition?.label.toLowerCase()}
      </p>
      <p className="mt-1 text-xs text-mi-muted">{definition?.definition}</p>
      {cell.kind === "cited" ? (
        <p className="mt-2 text-mi-ink-2">{cell.cited.reason}</p>
      ) : null}
      <p className="mt-2 text-xs text-mi-muted">
        The search found no specimen with up to {cell.maxVoters} voters
        {cell.kind === "cited" && cell.cited.verdict === "passes" ? ", as the proof predicts." : "."}
      </p>
    </div>
  );
}

/** One line about a specimen, for tooltips and the banner. */
export function specimenSummary(specimen: Specimen): string {
  const criterion = CRITERIA.find((c) => c.id === specimen.criterion)?.label.toLowerCase();
  return `${METHOD_META[specimen.method].label} fails ${criterion}: ${describeTransformation(specimen)}`;
}
