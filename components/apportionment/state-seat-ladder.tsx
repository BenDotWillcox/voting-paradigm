import type { AllocationStep } from "@/lib/apportionment-sequence";

interface StateSeatLadderProps {
  steps: AllocationStep[];
}

export function StateSeatLadder({ steps }: StateSeatLadderProps) {
  if (steps.length === 0) {
    return (
      <div className="rounded-md border p-4 text-sm text-muted-foreground">
        This state only has its constitutionally guaranteed first seat at this
        House size.
      </div>
    );
  }

  return (
    <ol className="max-h-96 space-y-1.5 overflow-y-auto pr-1">
      {steps.map((step) => (
        <li
          key={step.seatNumber}
          className="grid grid-cols-[4.5rem_minmax(0,1fr)_auto] items-center gap-3 rounded-md border px-3 py-2 text-sm"
        >
          <span className="text-xs tabular-nums text-muted-foreground">
            Seat #{step.seatNumber}
          </span>
          <span>
            {step.previousSeats} to {step.newSeats} representatives
          </span>
          <span className="text-xs tabular-nums text-muted-foreground">
            {Math.round(step.priority).toLocaleString()}
          </span>
        </li>
      ))}
    </ol>
  );
}
