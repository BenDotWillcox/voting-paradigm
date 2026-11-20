import { cn } from "@/lib/utils";

/**
 * What a section or figure may claim (prompts/demo-5-walkthrough.md):
 * a frozen result, read under the rules fixed before the run; an
 * exploratory analysis, made after the freeze; a proposal the study did not
 * test; or an illustration of how the system works, which claims nothing.
 */
export type Claim = "frozen" | "design" | "exploratory" | "proposal" | "illustration";

const TEXT: Record<Claim, string> = {
  frozen: "Frozen result",
  design: "Frozen design",
  exploratory: "Exploratory",
  proposal: "Proposal",
  illustration: "Illustration",
};

const TITLE: Record<Claim, string> = {
  frozen: "From the pre-registered benchmark, read under the rules fixed before it ran.",
  design: "A fact of the study's design, fixed before it ran.",
  exploratory: "Computed after the freeze. It changes no frozen result.",
  proposal: "A design idea the study did not test.",
  illustration: "Shows how the system works on one real city. It claims nothing on its own.",
};

export function ClaimLabel({ claim, className }: { claim: Claim; className?: string }) {
  return (
    <span
      title={TITLE[claim]}
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5 font-sans text-[0.7rem] font-medium tracking-wide ring-1",
        claim === "frozen" || claim === "design"
          ? "bg-story-surface text-story-ink-2 ring-story-rule"
          : "bg-transparent text-story-muted ring-story-axis",
        className
      )}
    >
      {TEXT[claim]}
    </span>
  );
}
