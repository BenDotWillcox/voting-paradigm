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
  votes: Record<string, string>;
  /** Every question on an open paper, soonest to close first; null while loading. */
  openVotes: OpenVote[] | null;
  resolving: boolean;
  error: string | null;
  /** Run the creation checks. `replacing` is the index of a delegation being edited. */
  check: (category: string, delegate: string, replacing?: number) => Promise<DelegationCheck>;
  add: (held: HeldDelegation) => void;
  replace: (index: number, held: HeldDelegation) => void;
  remove: (index: number) => void;
  vote: (questionId: string, optionId: string | null) => void;
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

type Saved = { delegations: HeldDelegation[]; votes: Record<string, string> };

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
    return { delegations: saved.delegations, votes: saved.votes ?? {} };
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
  const [votes, setVotes] = useState<Record<string, string>>({});

  useEffect(() => {
    const saved = readSaved(storageKey);
    if (saved) {
      setDelegations(saved.delegations);
      setVotes(saved.votes);
    }
    setReady(true);
  }, [storageKey]);

  useEffect(() => {
    if (!ready) return;
    try {
      window.localStorage.setItem(storageKey, JSON.stringify({ delegations, votes }));
    } catch {
      // Not saved; the account still works for this visit.
    }
  }, [ready, storageKey, delegations, votes]);

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
      add: (held) => setDelegations((current) => [...current, held]),
      replace: (index, held) =>
        setDelegations((current) =>
          current.map((entry, position) => (position === index ? held : entry))
        ),
      remove: (index) =>
        setDelegations((current) => current.filter((_, position) => position !== index)),
      vote: (questionId, optionId) =>
        setVotes((current) => {
          const next = { ...current };
          if (optionId === null) delete next[questionId];
          else next[questionId] = optionId;
          return next;
        }),
      reset: () => {
        setDelegations(startingDelegations(scenario));
        setVotes({});
      },
      closedPaper,
    }),
    [scenario, directory, ready, delegations, votes, openVotes, resolved, requestKey, error, check, closedPaper]
  );

  return <AccountContext.Provider value={account}>{children}</AccountContext.Provider>;
}
