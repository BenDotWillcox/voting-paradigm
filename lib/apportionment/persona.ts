/**
 * The essay's fictional person: a role, a life, and a real congressional
 * district in the reader's state.
 *
 * Deterministic: the same (visitor seed, state) always yields the same
 * person, so scrolling back, resizing, or replaying never swaps them out.
 *
 * Contradiction-free by construction: a person is first a hidden fact sheet
 * (household, housing, faith, work, money, health), drawn so the facts agree
 * with each other and with the role. Every piece of their life is a
 * statement that is eligible only when those facts make it true, so any two
 * pieces describe the same life (nobody pays down a mortgage while hoping to
 * buy a first home). `scripts/check-persona-consistency.mjs` samples many
 * people and checks an independent list of incompatible pairs.
 *
 * Concerns and beliefs are never inferred from occupation, faith, or other
 * identity: a concern depends only on its factual prerequisites (rent
 * worries need a renter), and combinations are free to cross stereotypes.
 */

export type LifeStage = "young" | "working" | "older";
export type WorkStatus = "employed" | "student" | "retired" | "home";
export type PieceCategory = "family" | "circumstance" | "belief" | "concern" | "everyday";

export interface Role {
  id: string;
  /** Noun phrase without an article, e.g. "teacher". */
  noun: string;
  status: WorkStatus;
  stage: LifeStage;
  /** Can plausibly run their own business. */
  canOwnBusiness?: boolean;
  /** Commonly works nights. */
  nightShifts?: boolean;
  /** Usually needs a college degree (so student loans are common). */
  degree?: boolean;
  /** Commonly unionized. */
  union?: boolean;
  /** Can plausibly work from home. */
  remote?: boolean;
  /** Drives for a living (so "driving an hour to work" would be odd). */
  drives?: boolean;
  /** A second job would be unusual. */
  salaried?: boolean;
}

export const ROLES: readonly Role[] = [
  { id: "nurse", noun: "nurse", status: "employed", stage: "working", nightShifts: true, degree: true, union: true },
  { id: "doctor", noun: "doctor", status: "employed", stage: "working", nightShifts: true, canOwnBusiness: true, degree: true, salaried: true },
  { id: "teacher", noun: "teacher", status: "employed", stage: "working", degree: true, union: true },
  { id: "lawyer", noun: "lawyer", status: "employed", stage: "working", canOwnBusiness: true, degree: true, salaried: true },
  { id: "electrician", noun: "electrician", status: "employed", stage: "working", canOwnBusiness: true, union: true },
  { id: "construction", noun: "construction worker", status: "employed", stage: "working", union: true },
  { id: "retail", noun: "retail worker", status: "employed", stage: "working", union: true },
  { id: "cook", noun: "line cook", status: "employed", stage: "working", nightShifts: true, canOwnBusiness: true, union: true },
  { id: "trucker", noun: "truck driver", status: "employed", stage: "working", nightShifts: true, canOwnBusiness: true, union: true, drives: true },
  { id: "warehouse", noun: "warehouse worker", status: "employed", stage: "working", nightShifts: true, union: true },
  { id: "factory", noun: "factory worker", status: "employed", stage: "working", nightShifts: true, union: true },
  { id: "farmer", noun: "farmer", status: "employed", stage: "working", canOwnBusiness: true },
  { id: "maintenance", noun: "maintenance worker", status: "employed", stage: "working", nightShifts: true, union: true },
  { id: "military", noun: "service member", status: "employed", stage: "working", salaried: true },
  { id: "athlete", noun: "minor-league athlete", status: "employed", stage: "young" },
  { id: "caregiver", noun: "home health aide", status: "employed", stage: "working", nightShifts: true, union: true },
  { id: "firefighter", noun: "firefighter", status: "employed", stage: "working", nightShifts: true, union: true },
  { id: "mail", noun: "mail carrier", status: "employed", stage: "working", union: true },
  { id: "software", noun: "software developer", status: "employed", stage: "working", canOwnBusiness: true, degree: true, remote: true, salaried: true },
  { id: "bus", noun: "bus driver", status: "employed", stage: "working", union: true, drives: true },
  { id: "hairstylist", noun: "hairstylist", status: "employed", stage: "working", canOwnBusiness: true },
  { id: "accountant", noun: "accountant", status: "employed", stage: "working", canOwnBusiness: true, degree: true, remote: true, salaried: true },
  { id: "barista", noun: "barista", status: "employed", stage: "young" },
  { id: "social", noun: "social worker", status: "employed", stage: "working", degree: true, union: true },
  { id: "plumber", noun: "plumber", status: "employed", stage: "working", canOwnBusiness: true, union: true },
  { id: "pharmacist", noun: "pharmacist", status: "employed", stage: "working", degree: true, salaried: true },
  { id: "childcare", noun: "child care worker", status: "employed", stage: "working", canOwnBusiness: true },
  { id: "parent", noun: "stay-at-home parent", status: "home", stage: "working" },
  { id: "student", noun: "college student", status: "student", stage: "young" },
  { id: "retired", noun: "retired machinist", status: "retired", stage: "older" },
];

// ---------------------------------------------------------------------------
// The fact sheet
// ---------------------------------------------------------------------------

export type Housing = "rent" | "mortgage" | "owned" | "with-family" | "dorm";
export type KidsAge = "young" | "school" | "teen" | "grown";
export type Faith =
  | "christian"
  | "catholic"
  | "jewish"
  | "muslim"
  | "hindu"
  | "buddhist"
  | "lapsed"
  | "spiritual"
  | "none";

/** Everything true about one person; every piece of their life must agree. */
export interface Facts {
  role: Role;
  stage: LifeStage;
  status: WorkStatus;
  partner: boolean;
  children: number;
  /** Ages of their children (null without children). */
  kidsAge: KidsAge | null;
  singleParent: boolean;
  raisingGrandkids: boolean;
  caringForParent: boolean;
  caringForSpouse: boolean;
  housing: Housing;
  pet: "dog" | "cat" | null;
  faith: Faith;
  veteran: boolean;
  union: boolean;
  studentLoans: boolean;
  firstGen: boolean;
  ownsBusiness: boolean;
  remote: boolean;
  nightShifts: boolean;
  longCommute: boolean;
  busCommute: boolean;
  twoJobs: boolean;
  nightSchool: boolean;
  tightBudget: boolean;
  newcomer: boolean;
  chronicCondition: boolean;
}

/** Faith is drawn independently of everything else about a person. */
const FAITHS: ReadonlyArray<[Faith, number]> = [
  ["christian", 28],
  ["catholic", 18],
  ["jewish", 6],
  ["muslim", 6],
  ["hindu", 5],
  ["buddhist", 4],
  ["lapsed", 9],
  ["spiritual", 10],
  ["none", 14],
];

function sampleFacts(random: () => number, role: Role): Facts {
  const chance = (p: number) => random() < p;
  const pick = <T>(items: readonly T[]): T => items[Math.floor(random() * items.length)];
  const weighted = <T>(items: ReadonlyArray<[T, number]>): T => {
    let r = random() * items.reduce((sum, [, w]) => sum + w, 0);
    for (const [item, w] of items) if ((r -= w) < 0) return item;
    return items[items.length - 1][0];
  };
  const { stage, status } = role;
  const employed = status === "employed";
  const student = status === "student";

  // Household: children first (their ages follow the life stage), then a
  // partner, which decides who is a single parent.
  let children = 0;
  let kidsAge: KidsAge | null = null;
  if (status === "home") {
    children = weighted([[1, 4], [2, 4], [3, 2]]);
    kidsAge = pick(["young", "school"] as const);
  } else if (stage === "working") {
    children = weighted([[0, 38], [1, 24], [2, 25], [3, 13]]);
    if (children > 0) kidsAge = pick(["young", "school", "teen"] as const);
  } else if (stage === "older" && chance(0.75)) {
    children = 1 + Math.floor(random() * 3);
    kidsAge = "grown";
  }
  const youngKids = children > 0 && kidsAge !== "grown";
  const partner = student
    ? chance(0.08)
    : stage === "young"
      ? chance(0.2)
      : youngKids
        ? chance(0.72)
        : chance(0.6);
  const singleParent = youngKids && !partner;

  // Housing: students may live in a dorm; living with parents only without
  // a partner or children of their own.
  let housing: Housing;
  if (student && !partner) housing = weighted([["dorm", 45], ["rent", 35], ["with-family", 20]]);
  else if (stage === "young") housing = partner ? "rent" : weighted([["rent", 60], ["with-family", 40]]);
  else if (stage === "older") housing = weighted([["owned", 55], ["mortgage", 20], ["rent", 25]]);
  else if (partner || children > 0) housing = weighted([["mortgage", 55], ["rent", 35], ["owned", 10]]);
  else housing = weighted([["rent", 55], ["mortgage", 30], ["owned", 5], ["with-family", 10]]);

  // Work.
  const ownsBusiness = employed && stage === "working" && !!role.canOwnBusiness && chance(0.35);
  const remote = employed && !!role.remote && chance(0.5);
  const nightShifts = employed && !!role.nightShifts && chance(0.55);
  const longCommute = employed && !remote && !role.drives && chance(0.25);
  const busCommute = employed && !remote && !longCommute && !role.drives && chance(0.12);
  const twoJobs = employed && !ownsBusiness && !role.salaried && chance(0.18);
  const nightSchool = employed && stage === "working" && !nightShifts && !twoJobs && chance(0.08);

  return {
    role,
    stage,
    status,
    partner,
    children,
    kidsAge,
    singleParent,
    raisingGrandkids: stage === "older" && kidsAge === "grown" && chance(0.12),
    caringForParent: stage === "working" ? chance(0.14) : stage === "older" ? chance(0.04) : false,
    caringForSpouse: stage === "older" && partner && chance(0.12),
    housing,
    pet: housing === "dorm" ? null : weighted([["dog", 35], ["cat", 25], [null, 40]]),
    faith: weighted(FAITHS),
    veteran: role.id !== "military" && (stage === "older" ? chance(0.2) : stage === "working" ? chance(0.07) : false),
    union: employed && !!role.union && !ownsBusiness && chance(0.4),
    studentLoans: student
      ? chance(0.7)
      : stage === "older"
        ? false
        : role.degree
          ? chance(0.55)
          : chance(stage === "young" ? 0.3 : 0.15),
    firstGen: (student || !!role.degree) && chance(0.3),
    ownsBusiness,
    remote,
    nightShifts,
    longCommute,
    busCommute,
    twoJobs,
    nightSchool,
    tightBudget: (employed || status === "home") && housing !== "owned" && chance(0.3),
    newcomer: chance(0.15),
    chronicCondition: chance(stage === "older" ? 0.3 : stage === "working" ? 0.12 : 0.05),
  };
}

// ---------------------------------------------------------------------------
// Statements: each true only of the facts it requires
// ---------------------------------------------------------------------------

export interface Statement {
  text: string;
  when: (f: Facts) => boolean;
}

const always = () => true;
const owner = (f: Facts) => f.housing === "mortgage" || f.housing === "owned";
const adult = (f: Facts) => f.status !== "student";

/** Responsibilities at home (the first named piece, when there is one). */
export const FAMILY: readonly Statement[] = [
  { text: "Raising a toddler", when: (f) => f.children === 1 && f.kidsAge === "young" && !f.singleParent },
  { text: "Raising two young kids", when: (f) => f.children === 2 && f.kidsAge === "young" && !f.singleParent },
  { text: "Raising two kids", when: (f) => f.children === 2 && f.kidsAge === "school" && !f.singleParent },
  { text: "Raising three kids", when: (f) => f.children === 3 && f.kidsAge !== "grown" && !f.singleParent },
  { text: "Raising a teenager", when: (f) => f.children === 1 && f.kidsAge === "teen" && !f.singleParent },
  { text: "Raising two teenagers", when: (f) => f.children === 2 && f.kidsAge === "teen" && !f.singleParent },
  { text: "Raising a child alone", when: (f) => f.singleParent && f.children === 1 },
  { text: "Raising two kids alone", when: (f) => f.singleParent && f.children === 2 },
  { text: "Raising three kids alone", when: (f) => f.singleParent && f.children === 3 },
  { text: "Expecting their first child", when: (f) => f.partner && f.children === 0 && f.stage === "working" },
  { text: "Newly married", when: (f) => f.partner && f.children === 0 && f.stage !== "older" },
  { text: "Caring for an aging parent", when: (f) => f.caringForParent },
  { text: "Caring for a spouse with dementia", when: (f) => f.caringForSpouse },
  { text: "Helping raise a younger sibling", when: (f) => f.stage === "young" && f.housing === "with-family" },
  { text: "Raising two grandchildren", when: (f) => f.raisingGrandkids },
  { text: "Grandparent of five", when: (f) => f.stage === "older" && f.kidsAge === "grown" && f.children >= 2 && !f.raisingGrandkids },
  { text: "Kids grown and moved away", when: (f) => f.kidsAge === "grown" && !f.raisingGrandkids },
];

/** Where and how they live and work. */
export const CIRCUMSTANCE: readonly Statement[] = [
  { text: "Renting an apartment", when: (f) => f.housing === "rent" },
  { text: "Renting with two roommates", when: (f) => f.housing === "rent" && !f.partner && f.children === 0 && f.stage !== "older" },
  { text: "Paying down a mortgage", when: (f) => f.housing === "mortgage" },
  { text: "Owns their home outright", when: (f) => f.housing === "owned" },
  { text: "Living with their parents", when: (f) => f.housing === "with-family" },
  { text: "Living in a college dorm", when: (f) => f.housing === "dorm" },
  { text: "Working night shifts", when: (f) => f.nightShifts },
  { text: "Working two jobs", when: (f) => f.twoJobs },
  { text: "Driving an hour to work", when: (f) => f.longCommute },
  { text: "Takes the bus to work", when: (f) => f.busCommute },
  { text: "Works from home", when: (f) => f.remote },
  { text: "Taking night classes", when: (f) => f.nightSchool },
  { text: "Paying off student loans", when: (f) => f.studentLoans && f.status !== "student" },
  { text: "Taking out loans for school", when: (f) => f.studentLoans && f.status === "student" },
  { text: "First in their family to go to college", when: (f) => f.firstGen },
  { text: "Recently retired", when: (f) => f.status === "retired" },
  { text: "Living on a fixed income", when: (f) => f.status === "retired" },
  { text: "Running a small business", when: (f) => f.ownsBusiness },
  { text: "Saving for retirement", when: (f) => f.status === "employed" && f.stage === "working" && !f.tightBudget },
  { text: "Living paycheck to paycheck", when: (f) => f.tightBudget },
  { text: "Managing diabetes", when: (f) => f.chronicCondition },
  { text: "Moved here two years ago", when: (f) => f.newcomer },
  {
    text: "Has lived in the same town all their life",
    when: (f) => !f.newcomer && f.housing !== "dorm" && !f.veteran && f.role.id !== "military",
  },
  { text: "Served in the Army", when: (f) => f.veteran },
  { text: "Has moved bases four times", when: (f) => f.role.id === "military" },
];

/** Faith, or ties to a community. */
export const FAITH_TIES: readonly Statement[] = [
  { text: "Active in their church", when: (f) => f.faith === "christian" },
  { text: "Goes to Mass every Sunday", when: (f) => f.faith === "catholic" },
  { text: "Active in their synagogue", when: (f) => f.faith === "jewish" },
  { text: "Active in their mosque", when: (f) => f.faith === "muslim" },
  { text: "Active in their temple", when: (f) => f.faith === "hindu" },
  { text: "Meditates with a Buddhist group", when: (f) => f.faith === "buddhist" },
  { text: "Raised Catholic, rarely goes now", when: (f) => f.faith === "lapsed" },
  { text: "Spiritual but not religious", when: (f) => f.faith === "spiritual" },
  { text: "Not religious", when: (f) => f.faith === "none" },
];

export const COMMUNITY_TIES: readonly Statement[] = [
  { text: "Volunteers at a food bank", when: always },
  { text: "Volunteer firefighter", when: (f) => adult(f) && f.role.id !== "firefighter" && f.stage !== "older" },
  { text: "Union member", when: (f) => f.union },
  { text: "On the PTA", when: (f) => f.kidsAge === "school" },
  { text: "Member of the American Legion", when: (f) => f.veteran },
  { text: "Mentors kids in the neighborhood", when: adult },
  { text: "Votes in every local election", when: always },
  { text: "Hasn't voted in years", when: (f) => f.stage !== "young" },
  { text: "Has never voted", when: (f) => f.stage === "young" },
  { text: "Sits on the library board", when: (f) => f.stage !== "young" },
  { text: "Belongs to a neighborhood association", when: owner },
  { text: "Organizes the block party", when: (f) => f.housing !== "dorm" },
  { text: "Volunteers at the animal shelter", when: always },
];

/** A concern or hope. Prerequisites are facts, never identity. */
export const CONCERN: readonly Statement[] = [
  { text: "Wants affordable childcare", when: (f) => f.kidsAge === "young" },
  { text: "Wants lower taxes", when: always },
  { text: "Wants clean drinking water", when: always },
  { text: "Wants the local hospital to stay open", when: always },
  { text: "Wants their kids to afford a home nearby", when: (f) => f.kidsAge === "teen" || f.kidsAge === "grown" },
  { text: "Hopes to buy a first home", when: (f) => (f.housing === "rent" || f.housing === "with-family") && f.stage !== "older" },
  { text: "Worries about rising rent", when: (f) => f.housing === "rent" },
  { text: "Worries about property taxes", when: owner },
  { text: "Worries about medical bills", when: always },
  { text: "Worries about the cost of groceries", when: always },
  { text: "Worries about paying for prescriptions", when: (f) => f.chronicCondition },
  { text: "Hopes to retire someday", when: (f) => f.status === "employed" && f.stage === "working" },
  { text: "Worries about outliving their savings", when: (f) => f.stage === "older" },
  { text: "Worries about Social Security", when: (f) => f.stage === "older" },
  { text: "Wants safer streets", when: always },
  { text: "Wants better public schools", when: always },
  { text: "Wants the roads fixed", when: always },
  { text: "Wants reliable internet", when: always },
  { text: "Worries about job security", when: (f) => f.status === "employed" && !f.ownsBusiness },
  { text: "Hopes their kids go to college", when: (f) => f.kidsAge === "school" || f.kidsAge === "teen" },
  { text: "Worries about student debt", when: (f) => f.studentLoans },
  { text: "Hopes to start a business", when: (f) => f.status === "employed" && !f.ownsBusiness && f.stage !== "older" },
  { text: "Wants more jobs in town", when: always },
  { text: "Worries about extreme weather", when: always },
  { text: "Wants a shorter commute", when: (f) => f.longCommute },
  { text: "Wants college to cost less", when: (f) => f.status === "student" || f.kidsAge === "teen" },
  { text: "Worries about care for their parent", when: (f) => f.caringForParent },
];

/** Everyday texture: habits and pastimes. */
export const EVERYDAY: readonly Statement[] = [
  { text: "Keeps a vegetable garden", when: (f) => owner(f) || f.housing === "with-family" },
  { text: "Grows tomatoes on the balcony", when: (f) => f.housing === "rent" },
  { text: "Plays in a band on weekends", when: always },
  { text: "Coaches a youth soccer team", when: adult },
  { text: "Always halfway through a book", when: always },
  { text: "Fixes things for the neighbors", when: always },
  { text: "Walks the dog every morning", when: (f) => f.pet === "dog" },
  { text: "Has a cat named Biscuit", when: (f) => f.pet === "cat" },
  { text: "Hunts every fall", when: always },
  { text: "Fishes on weekends", when: always },
  { text: "Bakes bread on Sundays", when: always },
  { text: "Never misses a home game", when: always },
  { text: "Plays pickup basketball", when: (f) => f.stage !== "older" },
  { text: "Runs half marathons", when: (f) => !f.chronicCondition },
  { text: "Builds furniture in the garage", when: owner },
  { text: "Quilts", when: always },
  { text: "Plays video games with friends online", when: always },
  { text: "Sings in the church choir", when: (f) => f.faith === "christian" || f.faith === "catholic" },
  { text: "Restores old cars", when: (f) => f.housing !== "dorm" },
  { text: "Bowls on Thursday nights", when: (f) => !f.nightShifts },
  { text: "Hikes state parks", when: always },
  { text: "Cooks a big dinner every Sunday", when: (f) => f.housing !== "dorm" },
  { text: "Learning to play guitar", when: always },
  { text: "Does the crossword every morning", when: always },
  { text: "Knits for the grandkids", when: (f) => f.stage === "older" && f.kidsAge === "grown" },
  { text: "Drives the kids to soccer practice", when: (f) => f.kidsAge === "school" || f.kidsAge === "teen" },
];

// ---------------------------------------------------------------------------
// The person
// ---------------------------------------------------------------------------

export interface PersonaPiece {
  category: PieceCategory;
  text: string;
}

export interface Persona {
  seed: number;
  stateFips: string;
  role: Role;
  /** The hidden facts every piece agrees with. */
  facts: Facts;
  /** District number, or null for an at-large state. */
  district: number | null;
  /**
   * The three pieces that are named as they arrive: a responsibility or
   * circumstance, a belief or community tie, then a concern or hope.
   */
  readable: readonly [PersonaPiece, PersonaPiece, PersonaPiece];
  /** Further facets of the same life (texture; not required reading). */
  more: readonly PersonaPiece[];
}

/** Generate the person for a visitor seed and a state with `seats` districts. */
export function generatePersona(seed: number, stateFips: string, seats: number): Persona {
  const random = mulberry32(hash(`${seed}:${stateFips}`));
  const pick = <T>(items: readonly T[]): T => items[Math.floor(random() * items.length)];
  const role = pick(ROLES);
  const facts = sampleFacts(random, role);
  const eligible = (statements: readonly Statement[]) => statements.filter((s) => s.when(facts));

  const family = eligible(FAMILY);
  const circumstance = pick(eligible(CIRCUMSTANCE)).text;
  const faith = eligible(FAITH_TIES);
  const community = eligible(COMMUNITY_TIES);
  const belief = pick(random() < 0.5 && faith.length > 0 ? faith : community).text;
  const concern = pick(eligible(CONCERN)).text;
  const everyday = pick(eligible(EVERYDAY)).text;

  const familyFirst = family.length > 0 && random() < 0.75;
  const first: PersonaPiece = familyFirst
    ? { category: "family", text: pick(family).text }
    : { category: "circumstance", text: circumstance };
  const more: PersonaPiece[] = [
    ...(familyFirst ? [{ category: "circumstance" as const, text: circumstance }] : []),
    { category: "everyday", text: everyday },
  ];

  return {
    seed,
    stateFips,
    role,
    facts,
    district: seats <= 1 ? null : 1 + Math.floor(random() * seats),
    readable: [first, { category: "belief", text: belief }, { category: "concern", text: concern }],
    more,
  };
}

// ---------------------------------------------------------------------------
// Grammar
// ---------------------------------------------------------------------------

/** "a teacher", "an electrician". */
export function withArticle(noun: string): string {
  return `${/^[aeiou]/i.test(noun) ? "an" : "a"} ${noun}`;
}

/** 1st, 2nd, 3rd, 4th, 11th, 12th, 13th, 21st, 22nd... */
export function ordinal(n: number): string {
  const tens = n % 100;
  if (tens >= 11 && tens <= 13) return `${n}th`;
  return `${n}${({ 1: "st", 2: "nd", 3: "rd" } as Record<number, string>)[n % 10] ?? "th"}`;
}

/** "Ohio’s 7th congressional district" / "Wyoming’s at-large congressional district". */
export function districtLabel(stateName: string, district: number | null): string {
  return `${stateName}’s ${district === null ? "at-large" : ordinal(district)} congressional district`;
}

/** "A teacher in Ohio’s 7th congressional district." */
export function personaDescription(persona: Persona, stateName: string): string {
  const who = withArticle(persona.role.noun);
  return `${who[0].toUpperCase()}${who.slice(1)} in ${districtLabel(stateName, persona.district)}.`;
}

// ---------------------------------------------------------------------------
// Seeded randomness (reproducible per visitor and state)
// ---------------------------------------------------------------------------

export function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** FNV-1a, for turning strings into seeds. */
export function hash(text: string): number {
  let h = 0x811c9dc5;
  for (let i = 0; i < text.length; i++) {
    h ^= text.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return h >>> 0;
}
