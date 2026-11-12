import * as React from "react";
import Link from "next/link";
import { ArrowRight, Bot, Landmark, Map, Network, SlidersHorizontal, Vote } from "lucide-react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ApportionmentCard } from "@/components/home/apportionment-card";
import { DistrictingCard } from "@/components/home/districting-card";
import { ExpressiveCard } from "@/components/home/expressive-card";
import { MethodsCard } from "@/components/home/methods-card";
import { DemoGrid } from "@/components/home/demo-grid";
import { SketchBackdrop } from "@/components/home/sketch/sketch-backdrop";
import {
  showcaseData,
  statusLabel,
  type Demo,
  type DemoStatus,
  type ShowcaseDemo,
} from "@/components/home/demo-types";
import { loadDistrictingCard, type DistrictingCardData } from "@/lib/districting-home-card";
import { loadHomeCardAtlas, type HomeCardAtlas } from "@/lib/methods/instrument-data";
import { SITE_NAME } from "@/lib/site";

/**
 * Demos with their own animated card in the demo's visual identity; the
 * rest use the shared neutral card until theirs is built. The methods card
 * draws the atlas's hub maps and the districting card Michigan's recorded
 * solve, both read from the build artifacts on the server.
 */
function showcaseCards(
  methodsAtlas: HomeCardAtlas,
  districting: DistrictingCardData
): Partial<Record<number, (demo: ShowcaseDemo) => React.ReactNode>> {
  return {
    1: (demo) => <MethodsCard demo={demo} atlas={methodsAtlas} />,
    3: (demo) => <DistrictingCard demo={demo} data={districting} />,
    4: (demo) => <ApportionmentCard demo={demo} />,
    6: (demo) => <ExpressiveCard demo={demo} />,
  };
}

/**
 * `number` is only an id (it keys the showcase cards) and is not shown. The
 * grid sorts by completion, title or readiness, breaking ties by
 * `impressiveness` (1 first). Readiness: voting methods such as ranked
 * choice are already used in real elections; a larger House and computed
 * districts need only a law; liquid democracy needs real-world pilots;
 * voting through preference agents is still research.
 */
const demos: Demo[] = [
  {
    number: 3,
    title: "Algorithmic districting",
    tagline: "A full 50-state district plan, computed rather than drawn.",
    description:
      "A practical proposal for every congressional district in all 50 states, computed by one algorithm from 2020 census blocks: equal population, connected districts, and no party, race or incumbent data. An explorer shows each state's map at four House sizes, and a step-by-step walkthrough follows the algorithm through Michigan, from 254,730 blocks to 13 districts within two people of equal.",
    showcase: [
      "Computational geometry",
      "Graph algorithms",
      "Geo data",
    ],
    href: "/districts",
    status: "live",
    readiness: 2,
    impressiveness: 1,
    Icon: Map,
  },
  {
    number: 1,
    title: "Voting methods",
    tagline: "Same voters, different winners.",
    description:
      "Seven voting methods, one Python package. A code explorer steps through each method's actual source beside the count it produces. Then see why the methods disagree on the same voters, open the smallest elections in which each fails a fairness criterion, map who wins where across a plane of voters, read 30,000 seeded simulations, and build your own electorate.",
    showcase: ["Voting theory", "Exhaustive search", "Spatial models", "Simulation"],
    href: "/methods",
    status: "live",
    readiness: 1,
    impressiveness: 2,
    Icon: Vote,
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
    readiness: 2,
    impressiveness: 3,
    Icon: Landmark,
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
    readiness: 4,
    impressiveness: 4,
    Icon: Bot,
  },
  {
    number: 6,
    title: "Expressive ballots",
    tagline: "What does a yes or no leave unsaid?",
    description:
      "Answer Colorado's 2022 income-tax question with a traditional yes/no ballot and a richer preference curve. Explore 100 voters' curves, see how different preferences compress into the same binary choice, then combine those same ballots into a tax rate under an explicit mean-score rule.",
    showcase: ["Preference elicitation", "Interactive visualization", "Social choice"],
    href: "/expressive",
    status: "in-progress",
    readiness: 3,
    impressiveness: 6,
    Icon: SlidersHorizontal,
  },
  {
    number: 5,
    title: "Liquid democracy",
    tagline: "Hand categories of decisions, in your own words, to people you trust.",
    description:
      "Write your own categories and delegate each to someone in a simulated city. A decision model routes every ballot question for every voter, loops are refused or resolved, and the delegated result sits beside direct voting.",
    showcase: [
      "Decision-model routing",
      "Graph algorithms",
      "Simulation",
    ],
    href: "/liquid",
    status: "in-progress",
    readiness: 3,
    impressiveness: 5,
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

/**
 * The home page: the intro and a sortable grid of demo cards, front and
 * center, over pencil sketches that come and go in the open paper, roughly
 * in the order democracy grew. Demo pages carry the header; this page links
 * to every demo already.
 */
export default async function LandingPage() {
  const [methodsAtlas, districting] = await Promise.all([loadHomeCardAtlas(), loadDistrictingCard()]);
  const cards = showcaseCards(methodsAtlas, districting);
  return (
    <main className="relative isolate min-h-dvh overflow-x-clip bg-white text-site-navy">
      <SketchBackdrop />
      <div className="container mx-auto max-w-7xl px-4 pt-10 pb-24 sm:pt-12">
        {/* data-sketch-avoid marks what the background sketches keep clear of. */}
        <header className="mx-auto max-w-5xl text-center" data-sketch-avoid>
          <h1 className="text-4xl leading-[1.05] font-semibold tracking-[-0.035em] text-balance sm:text-5xl lg:text-6xl">{SITE_NAME}</h1>
        </header>

        <section
          aria-label="About this project"
          data-sketch-avoid
          className="relative mx-auto mt-8 max-w-5xl rounded-2xl border border-site-navy/10 bg-white/85 px-6 py-5 text-center shadow-[0_18px_50px_-30px_rgb(13_23_38/0.35)] backdrop-blur-md sm:px-8"
        >
          <div
            aria-hidden
            className="absolute inset-x-10 -top-px h-px bg-[linear-gradient(90deg,transparent,var(--color-site-aqua),var(--color-site-blue),var(--color-site-rose),var(--color-site-sun),transparent)]"
          />
          <p className="text-base leading-relaxed text-pretty text-site-navy/85">
            Democracy has come a long way since its beginnings in ancient
            Athens. A less-told part of that story is the ideas and technology
            behind its mechanics: how votes are cast, counted and turned into
            representation. Elections have grown more efficient and far more
            inclusive, yet the systems most of us vote in still fall well short
            of what social choice theory shows is possible. The demos below
            explore ideas and systems that I believe could close some of that
            gap.
          </p>
          <div aria-hidden className="mx-auto my-3.5 flex w-44 items-center gap-2">
            <span className="h-px flex-1 bg-site-navy/10" />
            <span className="size-1.5 rounded-full bg-site-blue" />
            <span className="size-1.5 rounded-full bg-site-aqua" />
            <span className="size-1.5 rounded-full bg-site-rose" />
            <span className="size-1.5 rounded-full bg-site-sun" />
            <span className="h-px flex-1 bg-site-navy/10" />
          </div>
          <p className="text-[13px] leading-relaxed text-balance text-site-navy/60">
            This is a personal portfolio project. Nothing here runs a real
            election or produces a binding result; the demos use public data
            and simulations to show what each idea could do.
          </p>
        </section>

        <DemoGrid
          items={demos.map((demo) => {
            const showcase = cards[demo.number];
            return {
              id: demo.number,
              title: demo.title,
              status: demo.status,
              readiness: demo.readiness,
              impressiveness: demo.impressiveness,
              card: showcase ? showcase(showcaseData(demo)) : <DemoCard demo={demo} />,
            };
          })}
        />
      </div>
    </main>
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
            <CardTitle className="text-lg">{demo.title}</CardTitle>
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
        <p className="home-card-description text-sm text-muted-foreground">{demo.description}</p>
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
      <Link href={demo.href} className="block h-full">
        {card}
      </Link>
    );
  }

  return card;
}
