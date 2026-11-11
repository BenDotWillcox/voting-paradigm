/** Historical ballot content; model scores and electorates remain illustrative. */
export const TAX_MEASURE = {
  id: "colorado-2022-proposition-121",
  title: "Proposition 121 (STATUTORY)",
  shortTitle: "State Income Tax Rate Reduction",
  jurisdiction: "State of Colorado",
  county: "Larimer County, Colorado",
  electionDate: "November 8, 2022",
  statusQuo: 4.55,
  proposal: 4.40,
  question: "Shall there be a change to the Colorado Revised Statutes reducing the state income tax rate from 4.55% to 4.40%?",
  ballotUrl: "https://www.larimer.gov/sites/default/files/2022_general_election_sample_ballot.pdf#page=2",
  instructionsUrl: "https://www.larimer.gov/sites/default/files/2022_general_election_sample_ballot.pdf#page=1",
  guideUrl: "https://content.leg.colorado.gov/sites/default/files/images/blue_book_2022_english_for_web.pdf#page=23",
  recordUrl: "https://historicalelectiondata.coloradosos.gov/contest/25862",
} as const;

export const BALLOT_INSTRUCTIONS = [
  "Use black ink.",
  "Fill in the oval completely.",
  "Do not mark in any of the incorrect ways shown below.",
  "If you make a mistake, ask for a new ballot.",
] as const;

export const BALLOT_PREAMBLE = 'Ballot questions referred by the general assembly or any political subdivision are listed by letter, and ballot questions initiated by the people are listed numerically. A ballot question listed as an "amendment" proposes a change to the Colorado constitution, and a ballot question listed as a "proposition" proposes a change to the Colorado Revised Statutes. A "yes/for" vote on any ballot question is a vote in favor of changing current law or existing circumstances, and a "no/against" vote on any ballot question is a vote against changing current law or existing circumstances.';
