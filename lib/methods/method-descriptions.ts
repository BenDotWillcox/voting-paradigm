import { VotingMethod } from "@/types/methods";

export interface MethodDescription {
  method: VotingMethod;
  name: string;
  aliases: string[];
  ballotType: string;
  howItWorks: string;
  strengths: string[];
  weaknesses: string[];
  realWorldUsage: string[];
}

export const methodDescriptions: Record<VotingMethod, MethodDescription> = {
  plurality: {
    method: "plurality",
    name: "Plurality",
    aliases: ["First-Past-The-Post", "FPTP", "Winner-Take-All"],
    ballotType: "Pick one candidate",
    howItWorks:
      "Each voter selects a single candidate. The candidate with the most votes wins, even without a majority. Simple to understand but can produce winners most voters oppose.",
    strengths: [
      "Simplest to understand and administer",
      "Fast to count — results can be announced immediately",
      "Clear, decisive outcome with a single winner",
    ],
    weaknesses: [
      "Spoiler effect: similar candidates split the vote",
      "Can elect a winner opposed by the majority",
      "Encourages strategic voting (voting against, not for)",
      "Tends toward two-party dominance (Duverger's law)",
    ],
    realWorldUsage: [
      "US congressional and presidential elections",
      "UK House of Commons",
      "Canadian federal elections",
      "Indian Lok Sabha elections",
    ],
  },

  approval: {
    method: "approval",
    name: "Approval Voting",
    aliases: ["Approval"],
    ballotType: "Approve as many candidates as you like",
    howItWorks:
      "Each voter marks all candidates they find acceptable. The candidate approved by the most voters wins. This captures breadth of support that plurality misses.",
    strengths: [
      "Eliminates the spoiler effect entirely",
      "Simple ballots — just check boxes",
      "Elects broadly acceptable consensus candidates",
      "No wasted votes — you can support all candidates you like",
    ],
    weaknesses: [
      "Cannot express preference intensity between approved candidates",
      "Strategy of 'bullet voting' (approving only one) can undermine results",
      "Less well-known, so voters may need education",
    ],
    realWorldUsage: [
      "Fargo, North Dakota city elections (2018+)",
      "St. Louis, Missouri primary elections (2020+)",
      "United Nations Secretary-General selection (informal rounds)",
      "Many professional and academic societies",
    ],
  },

  irv: {
    method: "irv",
    name: "Instant Runoff Voting",
    aliases: ["Ranked Choice Voting", "RCV", "Alternative Vote", "AV"],
    ballotType: "Rank all candidates in order of preference",
    howItWorks:
      "Voters rank candidates from favorite to least favorite. If no candidate has a majority, the candidate with the fewest first-choice votes is eliminated and those ballots transfer to each voter's next choice. This repeats until someone achieves a majority.",
    strengths: [
      "Winner always has majority support among remaining ballots",
      "Reduces spoiler effect — vote for your favorite without fear",
      "Encourages positive campaigning (candidates seek 2nd-choice votes)",
      "Voters can express full preference ordering",
    ],
    weaknesses: [
      "Non-monotonic: ranking a candidate higher can cause them to lose",
      "Later-no-harm: your lower rankings can never hurt your top choice (pro or con)",
      "More complex to count — cannot be tallied at the precinct level",
      "Can still eliminate a Condorcet winner in early rounds",
    ],
    realWorldUsage: [
      "New York City mayoral elections (2021+)",
      "Alaska statewide elections (2022+)",
      "Australian House of Representatives (since 1918)",
      "Irish presidential elections",
    ],
  },

  borda: {
    method: "borda",
    name: "Borda Count",
    aliases: ["Borda"],
    ballotType: "Rank all candidates in order of preference",
    howItWorks:
      "Voters rank all candidates. With N candidates, a first-place rank earns N-1 points, second place gets N-2, down to 0 for last. The candidate with the most total points wins. This rewards broad, consistent support.",
    strengths: [
      "Rewards consensus — consistently ranked 2nd beats polarizing 1st",
      "Simple point formula is easy to explain",
      "Every ranking position matters, not just first choice",
      "Good at finding the 'least objectionable' candidate",
    ],
    weaknesses: [
      "Highly susceptible to strategic nomination (adding clones)",
      "Irrelevant alternatives can change the winner",
      "Can elect a candidate nobody's first choice",
      "Requires complete rankings (no partial ballots)",
    ],
    realWorldUsage: [
      "Eurovision Song Contest (jury voting component)",
      "Slovenian parliamentary elections (ethnic minority seats)",
      "Kiribati presidential candidate selection",
      "Many university student government elections",
    ],
  },

  ranked_pairs: {
    method: "ranked_pairs",
    name: "Ranked Pairs",
    aliases: ["Tideman's Method", "Condorcet-Tideman"],
    ballotType: "Rank all candidates in order of preference",
    howItWorks:
      "First checks if any candidate beats every other head-to-head (Condorcet winner). If not, it lists all pairwise victories by margin, locks them in from strongest to weakest, and skips any that would create a cycle. The winner is the candidate with no locked losses.",
    strengths: [
      "Always elects the Condorcet winner when one exists",
      "Resists strategic voting well — hard to manipulate",
      "Considers every pairwise preference, not just first choices",
      "Consistent and fair cycle resolution",
    ],
    weaknesses: [
      "Complex to explain and compute — harder to audit",
      "Requires complete pairwise comparison matrix (O(n²) pairs)",
      "Not widely used in public elections, so unfamiliar to voters",
      "Ties in margins can still require an arbitrary tiebreak",
    ],
    realWorldUsage: [
      "Debian GNU/Linux project leader elections",
      "Wikimedia Foundation board elections",
      "Various open-source project governance",
      "Academic research and theory (benchmark method)",
    ],
  },

  score: {
    method: "score",
    name: "Score Voting",
    aliases: ["Range Voting", "Score"],
    ballotType: "Rate each candidate 0-10",
    howItWorks:
      "Each voter gives every candidate a score from 0 to 10 (unscored = 0). All scores are summed per candidate and the highest total wins. This captures preference intensity — you can distinguish between 'acceptable' and 'excellent'.",
    strengths: [
      "Captures preference intensity, not just ordering",
      "No spoiler effect — scoring one candidate doesn't affect others",
      "Simple to fill out and understand",
      "Encourages honest expression of preference strength",
    ],
    weaknesses: [
      "Strategic voters may bullet-vote (all 10s and 0s)",
      "Voters who score moderately have less influence than extreme scorers",
      "No standard way to decide the scoring range",
      "May not elect the Condorcet winner",
    ],
    realWorldUsage: [
      "STAR Voting (Score Then Automatic Runoff) variants",
      "Product ratings and reviews (conceptually similar)",
      "Some internal corporate decision-making",
      "Olympic judging systems (inspiration)",
    ],
  },

  quadratic: {
    method: "quadratic",
    name: "Quadratic Voting",
    aliases: ["QV"],
    ballotType: "Allocate votes from a credit budget (cost = votes²)",
    howItWorks:
      "Each voter receives a credit budget (default 100). Casting v votes for a candidate costs v² credits. This means 1 vote costs 1 credit, but 10 votes cost 100. Negative votes (opposition) are allowed. This forces voters to prioritize — you can go deep on one issue or spread across many.",
    strengths: [
      "Captures preference intensity via cost mechanism",
      "Prevents tyranny of the majority — passionate minorities can concentrate votes",
      "Mathematically optimal for preference aggregation (under certain assumptions)",
      "Allows expressing opposition through negative votes",
    ],
    weaknesses: [
      "Complex — voters need to understand v² cost",
      "Wealthy voters might buy extra credits in real-money variants",
      "Strategic complexity: optimal allocation is non-trivial",
      "Relatively new — limited empirical data on real-world performance",
    ],
    realWorldUsage: [
      "Colorado state legislature (2019 budget prioritization)",
      "RadicalxChange community governance experiments",
      "Gitcoin Grants (quadratic funding, related concept)",
      "Taiwan's Presidential Hackathon voting",
    ],
  },
};

/** Order of methods for tab display */
export const methodOrder: VotingMethod[] = [
  "plurality",
  "approval",
  "irv",
  "borda",
  "ranked_pairs",
  "score",
  "quadratic",
];
