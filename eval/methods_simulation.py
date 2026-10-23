"""
The voting-methods simulation: how often the seven methods disagree, and how
often each elects the Condorcet winner, over seeded two-dimensional spatial
elections (prompts/demo-1-methods-instrument.md, Simulation).

Each election is regenerated from (study seed, candidate count, election
index) alone, so results never depend on how elections are split across
processes. Elections are sampled by voting.spatial.sample_spatial_election
and counted exactly as the instrument counts a profile
(voting.spatial.ProfileCounter): sincere-v1 ballots, and a fresh tiebreak
per method seeded with the tiebreak seed.

Every rate carries a 95% Wilson score interval. Tied elections keep the
winner the seeded tiebreak drew, as in the instrument, and each method's tie
rate is reported beside it. Instant runoff's ties are split by kind: the
tiebreak chose, or candidates tied for last were eliminated together, with or
without first choices of their own (without, the order cannot matter).
"""

import math
from collections.abc import Iterable, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np

from voting.ballot_models import SINCERE_V1, rankings_of
from voting.ballots.ranked_profile import profile_ballots
from voting.methods.irv import resolve_irv
from voting.spatial import (
    COUNTED_METHODS,
    ProfileCounter,
    SpatialElection,
    sample_spatial_election,
)
from voting.types import DEFAULT_TIEBREAK_SEED, Candidate, random_tiebreak

STUDY_ID = "methods_simulation_v1"
METHODS: tuple[str, ...] = tuple(COUNTED_METHODS)
# Two-sided 95% normal quantile
Z_95 = 1.959963984540054
# Elections per worker task
CHUNK = 500
# How an instant-runoff tie was settled
IRV_TIE_KINDS = ("tiebreak", "together", "together_empty")


@dataclass(frozen=True)
class SimulationConfig:
    seed: int = 20261023
    voters: int = 101
    candidate_counts: tuple[int, ...] = (3, 4, 5)
    elections: int = 10_000
    tiebreak_seed: int = DEFAULT_TIEBREAK_SEED


@dataclass(frozen=True)
class ElectionRecord:
    """One election's winners under every method, in METHODS order."""
    candidates: int
    index: int
    winners: tuple[str, ...]
    # False where a tiebreak decided the winner
    decisive: tuple[bool, ...]
    condorcet: str | None
    # One of IRV_TIE_KINDS where instant runoff was not decisive, else ""
    irv_tie: str = ""


def election_rng(config: SimulationConfig, candidates: int, index: int) -> np.random.Generator:
    """The generator for one election, independent of every other election's."""
    return np.random.default_rng([config.seed, candidates, index])


def run_election(config: SimulationConfig, candidates: int, index: int) -> ElectionRecord:
    election = sample_spatial_election(
        election_rng(config, candidates, index), config.voters, candidates
    )
    count = ProfileCounter(election.candidates, config.tiebreak_seed).count(election.profile.rows)
    ids = election.candidates
    return ElectionRecord(
        candidates=candidates,
        index=index,
        winners=tuple(ids[count.winners[m]] for m in COUNTED_METHODS),
        decisive=tuple(count.decisive[m] for m in COUNTED_METHODS),
        condorcet=ids[count.condorcet] if count.condorcet >= 0 else None,
        irv_tie="" if count.decisive["irv"] else irv_tie_kind(election, config.tiebreak_seed),
    )


def irv_tie_kind(election: SpatialElection, tiebreak_seed: int) -> str:
    """How instant runoff settled a tie, recounted with the reference method."""
    rankings = rankings_of(election.profile, SINCERE_V1)
    candidates = [Candidate(id=c, name=c) for c in election.candidates]
    result = resolve_irv(candidates, profile_ballots(rankings), random_tiebreak(tiebreak_seed))
    if result.tiebreak_applied:
        return "tiebreak"
    together = [r for r in result.rounds if len(r.eliminated) > 1]
    empty = all(r.vote_counts.get(c, 0) == 0 for r in together for c in r.eliminated)
    return "together_empty" if empty else "together"


def run_simulation(config: SimulationConfig, workers: int = 1) -> list[ElectionRecord]:
    """Every election, ordered by candidate count and then index."""
    tasks = [
        (config, candidates, start, min(start + CHUNK, config.elections))
        for candidates in config.candidate_counts
        for start in range(0, config.elections, CHUNK)
    ]
    if workers <= 1:
        chunks = [_run_chunk(task) for task in tasks]
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            chunks = list(pool.map(_run_chunk, tasks))
    return [record for chunk in chunks for record in chunk]


def _run_chunk(task: tuple[SimulationConfig, int, int, int]) -> list[ElectionRecord]:
    config, candidates, start, stop = task
    return [run_election(config, candidates, i) for i in range(start, stop)]


def wilson_interval(successes: int, n: int, z: float = Z_95) -> tuple[float, float]:
    """The Wilson score interval for a binomial proportion."""
    if n == 0:
        return (0.0, 1.0)
    p = successes / n
    z2 = z * z
    center = (p + z2 / (2 * n)) / (1 + z2 / n)
    half = z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / (1 + z2 / n)
    return (max(0.0, center - half), min(1.0, center + half))


def rate(successes: int, n: int) -> dict[str, Any]:
    low, high = wilson_interval(successes, n)
    return {
        "count": successes,
        "of": n,
        "rate": round(successes / n, 6) if n else None,
        "interval": [round(low, 6), round(high, 6)],
    }


def summarize(records: Sequence[ElectionRecord], config: SimulationConfig) -> dict[str, Any]:
    """Condorcet-winner existence, Condorcet efficiency, tie and disagreement rates."""
    by_candidates = []
    for k in config.candidate_counts:
        group = [r for r in records if r.candidates == k]
        n = len(group)
        with_winner = [r for r in group if r.condorcet is not None]
        by_candidates.append(
            {
                "candidates": k,
                "elections": n,
                "condorcet_winner": rate(len(with_winner), n),
                "condorcet_efficiency": {
                    m: rate(sum(r.winners[i] == r.condorcet for r in with_winner), len(with_winner))
                    for i, m in enumerate(METHODS)
                },
                "tie_rate": {
                    m: rate(sum(not r.decisive[i] for r in group), n) for i, m in enumerate(METHODS)
                },
                "irv_ties": {
                    kind: rate(sum(r.irv_tie == kind for r in group), n) for kind in IRV_TIE_KINDS
                },
                "disagreement": [
                    {"a": a, "b": b, **rate(sum(r.winners[i] != r.winners[j] for r in group), n)}
                    for i, a in enumerate(METHODS)
                    for j, b in enumerate(METHODS)
                    if i < j
                ],
            }
        )
    return {
        "study": STUDY_ID,
        "config": config_json(config),
        "methods": list(METHODS),
        "ballot_model": "sincere-v1",
        "interval": "95% Wilson score",
        "by_candidates": by_candidates,
    }


def config_json(config: SimulationConfig) -> dict[str, Any]:
    data = asdict(config)
    data["candidate_counts"] = list(config.candidate_counts)
    return data


# --- Per-election records as CSV ------------------------------------------

def record_header() -> list[str]:
    return (
        ["candidates", "index", "condorcet"]
        + [f"{m}_winner" for m in METHODS]
        + [f"{m}_decisive" for m in METHODS]
        + ["irv_tie"]
    )


def record_row(record: ElectionRecord) -> list[str]:
    return (
        [str(record.candidates), str(record.index), record.condorcet or ""]
        + list(record.winners)
        + ["1" if d else "0" for d in record.decisive]
        + [record.irv_tie]
    )


def record_from_row(row: Sequence[str]) -> ElectionRecord:
    k = len(METHODS)
    return ElectionRecord(
        candidates=int(row[0]),
        index=int(row[1]),
        condorcet=row[2] or None,
        winners=tuple(row[3 : 3 + k]),
        decisive=tuple(cell == "1" for cell in row[3 + k : 3 + 2 * k]),
        irv_tie=row[3 + 2 * k],
    )


def records_from_rows(rows: Iterable[Sequence[str]]) -> list[ElectionRecord]:
    return [record_from_row(row) for row in rows]
