import * as React from "react";
import Link from "next/link";
import { ArrowRight, Bot, Landmark, Map, Network, Vote } from "lucide-react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ApportionmentCard } from "@/components/home/apportionment-card";
import { MethodsCard } from "@/components/home/methods-card";
import {
  showcaseData,
  statusLabel,
  type Demo,
  type DemoStatus,
  type ShowcaseDemo,
} from "@/components/home/demo-types";
import { loadHomeCardAtlas, type HomeCardAtlas } from "@/lib/methods/instrument-data";

/**
 * Demos with their own animated card in the demo's visual identity; the
 * rest use the shared neutral card until theirs is built. The methods card
 * draws the atlas's hub maps, read from the build artifacts on the server.
 */
function showcaseCards(
  methodsAtlas: HomeCardAtlas
): Partial<Record<number, (demo: ShowcaseDemo) => React.ReactNode>> {
  return {
    1: (demo) => <MethodsCard demo={demo} atlas={methodsAtlas} />,
    4: (demo) => <ApportionmentCard demo={demo} />,
  };
}

const demos: Demo[] = [
  {
    number: 1,
    title: "Voting methods",
    tagline: "Same voters, different winners.",
    description:
      "An instrument for seven voting methods. Edit an electorate and watch plurality, instant runoff, Borda, Ranked Pairs, approval, score and quadratic voting count it side by side, open the smallest elections in which each fails a fairness criterion, map who wins where across a plane of voters, and read 30,000 simulated elections.",
    showcase: ["Voting theory", "Exhaustive search", "Spatial models", "Simulation"],
    href: "/methods",
    status: "live",
    Icon: Vote,
  },
  {
    number: 2,
    title: "Agent voting via preference models",
    tagline: "A local open-weight agent learns what you value, then previews a vote.",
    description:
      "A video-first walkthrough and static replay show GPT-OSS interviewing one voter, extracting structured preference evidence, and producing an auditable ballot preview.",
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
      "Draw population-balanced congressional districts for every state with a reproducible balanced power-diagram algorithm over census tracts — no party data, no incumbents, one explicit rule.",
    showcase: [
      "Optimization",
      "Graph algorithms",
      "Geo data",
      "Fairness metrics",
    ],
    href: "/districts",
    status: "live",
    Icon: Map,
  },
  {
    number: 4,
    title: "Apportionment",
    tagline: "A data essay on the case for a bigger House.",
    description:
      "The House grew with the country for more than a century, then froze at 435 seats. This scrolling essay follows the evidence behind calls to expand it: how large districts have grown, how unequal they are between states, what the popular proposals would actually change, and what a larger House would cost.",
    showcase: ["Data storytelling", "Historical research", "Apportionment math"],
    href: "/apportionment",
    status: "live",
    Icon: Landmark,
  },
  {
    number: 5,
    title: "Liquid democracy",
    tagline: "Delegate per topic to whomever you trust — transitively.",
    description:
      "Simulate delegation graphs with topic-conditional edges, study how outcomes diverge from direct democracy, and surface pathologies like super-delegate concentration.",
    showcase: [
      "Network analysis",
      "Simulation",
      "Graph dynamics",
    ],
    href: "/liquid",
    status: "planned",
    Icon: Network,
  },
];

const statusVariant: Record<
  DemoStatus,
  "default" | "secondary" | "outline"
> = {
  live: "default",
  "in-progress": "secondary",
  planned: "outline",
};

export default async function LandingPage() {
  const cards = showcaseCards(await loadHomeCardAtlas());
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
        {demos.map((demo) => {
          const showcase = cards[demo.number];
          return showcase ? (
            <React.Fragment key={demo.number}>{showcase(showcaseData(demo))}</React.Fragment>
          ) : (
            <DemoCard key={demo.number} demo={demo} />
          );
        })}
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
