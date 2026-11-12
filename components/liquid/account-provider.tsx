"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  getCategoryJudgmentsAction,
  resolveBallotPaperAction,
  validateDelegationAction,
} from "@/actions/delegation-actions";
import type {
  DelegationBallotPaper,
  DelegationQuestion,
  DelegationScenario,
  QuestionResult,
  ResolveBallotPaperResponse,
  ValidateDelegationResponse,
} from "@/types/delegation";
import type { Choice } from "./ballots";
import { buildDirectory, categoryKey, type Directory } from "./people";

/** A delegation the service has accepted, with what it said about it. */
export type HeldDelegation = {
  category: string;
  delegate: string;
  /** Ids of broader categories this one sits inside. */
  inside: string[];
  /** Whether every open question has a recorded judgment for the category. */
  judged: boolean;
  /** Open questions on which this delegation comes back to the viewer. */
  warnings: ValidateDelegationResponse["warnings"];
};

/** What the service said about a delegation the viewer wants to make. */
export type DelegationCheck =
  | { status: "ok"; held: HeldDelegation }
  | { status: "rejected"; reason: string; chain: string[] | null }
  | { status: "error"; message: string };

/** One question on an open ballot paper, with how it currently resolves. */
export type OpenVote = {
  paper: DelegationBallotPaper;
  question: DelegationQuestion;
  result: QuestionResult;
  viewerEligible: boolean;
};

type Account = {
  scenario: DelegationScenario;
  directory: Directory;
  /** False until the browser's saved account has been read. */
  ready: boolean;
  delegations: HeldDelegation[];
  votes: Record<string, Choice>;
  /** Every question on an open paper, soonest to close first; null while loading. */
  openVotes: OpenVote[] | null;
  resolving: boolean;
  error: string | null;
  /** Run the creation checks. `replacing` is the index of a delegation being edited. */
  check: (category: string, delegate: string, replacing?: number) => Promise<DelegationCheck>;
  add: (held: HeldDelegation) => void;
  replace: (index: number, held: HeldDelegation) => void;
  remove: (index: number) => void;
  /** What the viewer has done in this browser, most recent first. */
  log: LocalEvent[];
  /** Cast, change or (with null) withdraw the viewer's own vote on a question. */
  vote: (questionId: string, choice: Choice | null) => void;
  /** Go back to the account the scenario starts with. */
  reset: () => void;
  /** A closed ballot paper as it was resolved; fetched once. */
  closedPaper: (paperId: string) => Promise<ResolveBallotPaperResponse | null>;
};

const AccountContext = createContext<Account | null>(null);

export function useAccount(): Account {
  const account = useContext(AccountContext);
  if (!account) throw new Error("useAccount needs an AccountProvider above it");
  return account;
}

/** One thing the viewer did in this browser. */
export type LocalEvent = {
  /** When, as an ISO timestamp. */
  at: string;
  kind: "added" | "moved" | "renamed" | "removed" | "voted" | "withdrew";
  category?: string;
  /** The delegate after the change, and before it when it moved. */
  delegate?: string;
  before?: string;
  /** The category's earlier wording, when it was renamed. */
  was?: string;
  question?: string;
  choice?: Choice;
};

const MAX_LOG = 100;

type Saved = {
  delegations: HeldDelegation[];
  votes: Record<string, Choice>;
  log: LocalEvent[];
};

function startingDelegations(scenario: DelegationScenario): HeldDelegation[] {
  const pool = new Map(scenario.categories.map((entry) => [categoryKey(entry.text), entry]));
  return scenario.viewer_delegations.map(({ category, delegate }) => ({
    category,
    delegate,
    inside: pool.get(categoryKey(category))?.inside ?? [],
    judged: true,
    warnings: [],
  }));
}

function readSaved(key: string): Saved | null {
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) return null;
    const saved = JSON.parse(raw) as Partial<Saved>;
    if (!Array.isArray(saved.delegations) || typeof saved.votes !== "object") return null;
    // A vote is a list of option ids; anything else was saved by an older version.
    const votes = Object.fromEntries(
      Object.entries(saved.votes ?? {}).filter(([, choice]) => Array.isArray(choice))
    );
    return { delegations: saved.delegations, votes, log: Array.isArray(saved.log) ? saved.log : [] };
  } catch {
    return null; // storage blocked or the entry is damaged: start from the scenario
  }
}

/**
 * The viewer's account: their delegations and votes, kept in this browser,
 * and how every open question currently resolves. Closed ballot papers are
 * history and do not depend on anything here.
 */
export function AccountProvider({
  scenario,
  children,
}: {
  scenario: DelegationScenario;
  children: React.ReactNode;
}) {
  const directory = useMemo(() => buildDirectory(scenario), [scenario]);
  const storageKey = `liquid-account:${scenario.scenario}:${scenario.seed}`;
  const [ready, setReady] = useState(false);
  const [delegations, setDelegations] = useState(() => startingDelegations(scenario));
  const [votes, setVotes] = useState<Record<string, Choice>>({});
  const [log, setLog] = useState<LocalEvent[]>([]);

  useEffect(() => {
    const saved = readSaved(storageKey);
    if (saved) {
      setDelegations(saved.delegations);
      setVotes(saved.votes);
      setLog(saved.log);
    }
    setReady(true);
  }, [storageKey]);

  useEffect(() => {
    if (!ready) return;
    try {
      window.localStorage.setItem(storageKey, JSON.stringify({ delegations, votes, log }));
    } catch {
      // Not saved; the account still works for this visit.
    }
  }, [ready, storageKey, delegations, votes, log]);

  const openPapers = useMemo(
    () =>
      scenario.ballot_papers
        .filter((paper) => paper.status === "open")
        .sort((a, b) => a.closes_in_days - b.closes_in_days),
    [scenario.ballot_papers]
  );

  const [resolved, setResolved] = useState<{
    key: string;
    papers: ResolveBallotPaperResponse[];
  } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const requestKey = JSON.stringify({ delegations, votes });

  useEffect(() => {
    if (!ready) return;
    let stale = false;
    setError(null);
    const pairs = delegations.map(({ category, delegate }) => ({ category, delegate }));
    void Promise.all(
      openPapers.map((paper) => {
        const onPaper = new Set(paper.questions.map((question) => question.id));
        return resolveBallotPaperAction({
          ballot_paper: paper.id,
          viewer_delegations: pairs,
          viewer_votes: Object.fromEntries(
            Object.entries(votes).filter(([id]) => onPaper.has(id))
          ),
          threshold: scenario.threshold,
          tiebreak_seed: 0,
        });
      })
    ).then((results) => {
      if (stale) return;
      const papers = results.flatMap((result) => (result.data ? [result.data] : []));
      if (papers.length === results.length) {
        setResolved({ key: requestKey, papers });
      } else {
        setError(results.find((result) => !result.isSuccess)?.message ?? "Could not resolve.");
      }
    });
    return () => {
      stale = true;
    };
    // requestKey stands in for delegations and votes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, requestKey, openPapers, scenario.threshold]);

  const openVotes = useMemo(() => {
    if (!resolved) return null;
    const byPaper = new Map(resolved.papers.map((paper) => [paper.ballot_paper, paper]));
    return openPapers.flatMap((paper) => {
      const response = byPaper.get(paper.id);
      if (!response) return [];
      const results = new Map(response.questions.map((entry) => [entry.question_id, entry]));
      return paper.questions.flatMap((question) => {
        const result = results.get(question.id);
        return result
          ? [{ paper, question, result, viewerEligible: response.viewer_eligible }]
          : [];
      });
    });
  }, [resolved, openPapers]);

  const record = useCallback((event: Omit<LocalEvent, "at">) => {
    setLog((current) =>
      [{ ...event, at: new Date().toISOString() }, ...current].slice(0, MAX_LOG)
    );
  }, []);

  const check = useCallback<Account["check"]>(
    async (category, delegate, replacing) => {
      const others = delegations.filter((_, index) => index !== replacing);
      const checked = await validateDelegationAction({
        viewer_delegations: others.map((held) => ({
          category: held.category,
          delegate: held.delegate,
        })),
        proposed: { category, delegate },
        threshold: scenario.threshold,
      });
      if (!checked.isSuccess || !checked.data) {
        return { status: "error", message: checked.message };
      }
      const result = checked.data;
      if (!result.accepted) {
        return {
          status: "rejected",
          reason: result.reason ?? "The delegation was refused.",
          chain: result.chain,
        };
      }
      let judged = result.judged;
      let inside = result.category.inside;
      if (!judged && scenario.live_judgments) {
        // A category nobody has written before: ask the decision model now.
        const judgments = await getCategoryJudgmentsAction({
          category: result.category.text,
          held: others.map((held) => held.category),
        });
        if (judgments.isSuccess && judgments.data) {
          judged = judgments.data.judgments.missing === 0;
          inside = judgments.data.category.inside;
        }
      }
      return {
        status: "ok",
        held: {
          category: result.category.text,
          delegate,
          inside,
          judged,
          warnings: result.warnings,
        },
      };
    },
    [delegations, scenario.threshold, scenario.live_judgments]
  );

  const closedCache = useRef(new Map<string, Promise<ResolveBallotPaperResponse | null>>());
  const closedPaper = useCallback<Account["closedPaper"]>(
    (paperId) => {
      const cached = closedCache.current.get(paperId);
      if (cached) return cached;
      const request = resolveBallotPaperAction({
        ballot_paper: paperId,
        viewer_delegations: [],
        viewer_votes: {},
        threshold: scenario.threshold,
        tiebreak_seed: 0,
      }).then((result) => result.data ?? null);
      closedCache.current.set(paperId, request);
      return request;
    },
    [scenario.threshold]
  );

  const account = useMemo<Account>(
    () => ({
      scenario,
      directory,
      ready,
      delegations,
      votes,
      openVotes,
      resolving: ready && resolved?.key !== requestKey && error === null,
      error,
      check,
      log,
      add: (held) => {
        record({ kind: "added", category: held.category, delegate: held.delegate });
        setDelegations((current) => [...current, held]);
      },
      replace: (index, held) => {
        const was = delegations[index];
        if (was && was.delegate !== held.delegate) {
          record({
            kind: "moved",
            category: held.category,
            delegate: held.delegate,
            before: was.delegate,
          });
        }
        if (was && categoryKey(was.category) !== categoryKey(held.category)) {
          record({
            kind: "renamed",
            category: held.category,
            was: was.category,
            delegate: held.delegate,
          });
        }
        setDelegations((current) =>
          current.map((entry, position) => (position === index ? held : entry))
        );
      },
      remove: (index) => {
        const was = delegations[index];
        if (was) record({ kind: "removed", category: was.category, before: was.delegate });
        setDelegations((current) => current.filter((_, position) => position !== index));
      },
      vote: (questionId, choice) => {
        record(
          choice === null
            ? { kind: "withdrew", question: questionId }
            : { kind: "voted", question: questionId, choice }
        );
        setVotes((current) => {
          const next = { ...current };
          if (choice === null) delete next[questionId];
          else next[questionId] = choice;
          return next;
        });
      },
      reset: () => {
        setDelegations(startingDelegations(scenario));
        setVotes({});
        setLog([]);
      },
      closedPaper,
    }),
    [scenario, directory, ready, delegations, votes, log, record, openVotes, resolved, requestKey, error, check, closedPaper]
  );

  return <AccountContext.Provider value={account}>{children}</AccountContext.Provider>;
}
