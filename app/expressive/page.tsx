import type { Metadata } from "next";
import { ExpressiveHero } from "@/components/expressive/expressive-hero";
import { ScalarComparison } from "@/components/expressive/scalar-comparison";

export const metadata: Metadata = {
  title: "Expressive ballots",
  description:
    "Compare a yes/no tax question with a richer ballot, explore 100 voters’ preferences, and see how those same ballots combine into a tax rate.",
};

export default function ExpressivePage() {
  return (
    <main>
      <ExpressiveHero />
      <ScalarComparison />
    </main>
  );
}
