import Link from "next/link";
import { ArrowRight, Bot, Map, Network, Vote } from "lucide-react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

type DemoStatus = "live" | "in-progress" | "planned";

type Demo = {
  number: number;
  title: string;
  tagline: string;
  description: string;
  showcase: string[];
  href: string | null;
  status: DemoStatus;
  Icon: typeof Vote;
};

const demos: Demo[] = [
  {
    number: 1,
    title: "Voting methods comparison",
    tagline: "Same ballots, different methods, different winners.",
    description:
      "Run the same set of ballots through plurality, IRV, Borda, Ranked Pairs, Score, Approval, and Quadratic — and see how the choice of method changes who wins.",
    showcase: ["Voting theory", "Electoral criteria", "Reproducibility"],
    href: "/methods",
    status: "live",
    Icon: Vote,
  },
  {
    number: 2,
    title: "Agent voting via preference models",
    tagline: "An LLM learns what you value, then votes on your behalf.",
    description:
      "Pairwise elicitation builds a Bayesian posterior over your civic preferences. An agent uses that posterior to cast ballots — and flags low-confidence margins for follow-up questions.",
    showcase: [
      "Bayesian inference",
      "Embeddings",
      "Active learning",
      "LLM orchestration",
    ],
    href: "/preferences",
    status: "in-progress",
    Icon: Bot,
  },
  {
    number: 3,
    title: "Algorithmic districting",
    tagline: "Fair, transparent district maps under explicit constraints.",
    description:
      "Generate and evaluate redistricting plans against population balance, compactness, and partisan-fairness targets — using ensemble methods that make trade-offs visible.",
    showcase: [
      "Optimization",
      "Graph algorithms",
      "Geo data",
      "Fairness metrics",
    ],
    href: "/districts",
    status: "in-progress",
    Icon: Map,
  },
  {
    number: 4,
    title: "Liquid democracy",
    tagline: "Delegate per topic to whomever you trust — transitively.",
    description:
      "Simulate delegation graphs with topic-conditional edges, study how outcomes diverge from direct democracy, and surface pathologies like super-delegate concentration.",
    showcase: [
      "Network analysis",
      "Simulation",
      "Graph dynamics",
    ],
    href: null,
    status: "planned",
    Icon: Network,
  },
];

const statusLabel: Record<DemoStatus, string> = {
  live: "Live",
  "in-progress": "In progress",
  planned: "Planned",
};

const statusVariant: Record<
  DemoStatus,
  "default" | "secondary" | "outline"
> = {
  live: "default",
  "in-progress": "secondary",
  planned: "outline",
};

export default function LandingPage() {
  return (
    <div className="container mx-auto px-4 py-12 max-w-5xl">
      <header className="mb-12 space-y-4">
        <h1 className="text-4xl font-bold tracking-tight">
          A portfolio of demos exploring better democratic voting.
        </h1>
        <p className="text-muted-foreground text-lg max-w-3xl">
          The gap between what voting theory recommends and what real polities
          use is technological as much as political. Each demo isolates one
          friction blocking electoral reform, and shows how AI, statistical
          modeling, optimization, or network analysis could plausibly dissolve
          it.
        </p>
        <p className="text-sm text-muted-foreground max-w-3xl">
          Voters are simulated personas — no real elections, no binding
          outcomes. This is a portfolio project demonstrating systems and ML
          engineering on a domain the author cares about.
        </p>
      </header>

      <div className="grid gap-6 sm:grid-cols-2">
        {demos.map((demo) => (
          <DemoCard key={demo.number} demo={demo} />
        ))}
      </div>
    </div>
  );
}

function DemoCard({ demo }: { demo: Demo }) {
  const { Icon } = demo;
  const isClickable = demo.href !== null;

  const card = (
    <Card
      className={
        isClickable
          ? "h-full transition-shadow hover:shadow-md"
          : "h-full opacity-75"
      }
    >
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="rounded-lg bg-muted p-2">
              <Icon className="h-5 w-5" />
            </div>
            <div className="flex flex-col">
              <span className="text-xs text-muted-foreground">
                Demo {demo.number}
              </span>
              <CardTitle className="text-lg">{demo.title}</CardTitle>
            </div>
          </div>
          <Badge variant={statusVariant[demo.status]}>
            {statusLabel[demo.status]}
          </Badge>
        </div>
        <CardDescription className="pt-2 text-sm font-medium text-foreground">
          {demo.tagline}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm text-muted-foreground">{demo.description}</p>
        <div className="flex flex-wrap gap-1.5">
          {demo.showcase.map((tag) => (
            <Badge key={tag} variant="outline" className="text-xs">
              {tag}
            </Badge>
          ))}
        </div>
        {isClickable && (
          <div className="flex items-center gap-1 text-sm font-medium text-primary">
            Open demo
            <ArrowRight className="h-4 w-4" />
          </div>
        )}
      </CardContent>
    </Card>
  );

  if (isClickable && demo.href) {
    return (
      <Link href={demo.href} className="block">
        {card}
      </Link>
    );
  }

  return card;
}
