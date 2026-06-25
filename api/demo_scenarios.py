"""
Interactive voting-method demo scenarios.

This module turns civic voter blocs into concrete ballots for each supported
voting method. The resolvers still live in the voting package; this layer only
derives deterministic demo inputs from sliders.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from voting.ballots.approval import create_approval_ballot
from voting.ballots.quadratic import create_quadratic_ballot
from voting.ballots.ranked_choice import create_ranked_choice_ballot
from voting.ballots.score import create_score_ballot
from voting.ballots.single_choice import create_single_choice_ballot
from voting.methods.approval import resolve_approval
from voting.methods.borda import resolve_borda
from voting.methods.irv import resolve_irv
from voting.methods.plurality import resolve_plurality
from voting.methods.quadratic import resolve_quadratic
from voting.methods.ranked_pairs import resolve_ranked_pairs
from voting.methods.score import resolve_score
from voting.types import Candidate, CandidateId

VotingMethod = str

METHODS: list[VotingMethod] = [
    "plurality",
    "approval",
    "irv",
    "borda",
    "ranked_pairs",
    "score",
    "quadratic",
]


def deterministic_tiebreak(tied: list[CandidateId]) -> CandidateId:
    return sorted(tied)[0]


def _candidate(id: str, name: str) -> dict[str, str]:
    return {"id": id, "name": name}


def _control(
    id: str,
    label: str,
    description: str,
    default: int,
    low_label: str,
    high_label: str,
) -> dict[str, Any]:
    return {
        "id": id,
        "label": label,
        "description": description,
        "min": 0,
        "max": 100,
        "step": 5,
        "default": default,
        "low_label": low_label,
        "high_label": high_label,
    }


SCENARIOS: list[dict[str, Any]] = [
    {
        "id": "transportation",
        "title": "Transit Vote Split",
        "domain": "Transportation",
        "thesis": "Two similar transit options split first choices, while broader methods surface a majority-backed alternative.",
        "lesson": "Plurality can reward vote splitting; approval, score, and Condorcet-style methods expose broader support.",
        "voter_count": 100,
        "candidates": [
            _candidate("bus", "Bus Rapid Transit"),
            _candidate("rail", "Light Rail"),
            _candidate("bike", "Protected Bike Lanes"),
            _candidate("highway", "Highway Expansion"),
        ],
        "controls": [
            _control("polarization", "Polarization", "Push blocs toward their favorite and away from opponents.", 45, "Pragmatic", "Hard lines"),
            _control("compromise", "Compromise bloc size", "Grow or shrink voters who prefer a broadly acceptable transit option.", 45, "Small", "Large"),
            _control("strategy", "Strategic voting", "Move some first-choice voters toward a viable anti-highway option under plurality.", 20, "Sincere", "Strategic"),
            _control("turnout", "Turnout imbalance", "Shift turnout toward highway voters at high values and transit voters at low values.", 45, "Transit edge", "Highway edge"),
            _control("intensity", "Preference intensity", "Make scores and quadratic allocations more extreme.", 55, "Soft", "Intense"),
        ],
        "blocs": [
            {"id": "bus-riders", "name": "Bus Riders", "description": "Dense-corridor commuters who want fast rollout.", "share": 28, "color": "oklch(0.6 0.16 162)", "turnout_bias": -0.3, "compromise_bias": 0.0, "strategic_target": "rail", "utilities": {"bus": 94, "rail": 82, "bike": 68, "highway": 18}},
            {"id": "rail-urbanists", "name": "Rail Urbanists", "description": "Long-range transit voters who prefer rail but accept BRT.", "share": 23, "color": "oklch(0.58 0.18 248)", "turnout_bias": -0.2, "compromise_bias": 0.5, "strategic_target": "bus", "utilities": {"rail": 96, "bus": 84, "bike": 72, "highway": 16}},
            {"id": "bike-climate", "name": "Bike & Climate Voters", "description": "Safety and emissions voters who like all non-highway plans.", "share": 17, "color": "oklch(0.68 0.16 130)", "turnout_bias": -0.4, "compromise_bias": 0.1, "strategic_target": "rail", "utilities": {"bike": 96, "rail": 76, "bus": 74, "highway": 10}},
            {"id": "car-commuters", "name": "Car Commuters", "description": "Suburban commuters focused on road capacity.", "share": 32, "color": "oklch(0.68 0.16 55)", "turnout_bias": 0.7, "compromise_bias": -0.4, "strategic_target": "highway", "utilities": {"highway": 92, "bus": 36, "rail": 30, "bike": 12}},
        ],
    },
    {
        "id": "energy",
        "title": "Clean Energy Transfer",
        "domain": "Energy",
        "thesis": "A fossil option leads first choices, but ranked transfers and broad scores consolidate around cleaner alternatives.",
        "lesson": "IRV can change the winner when eliminated voters have aligned second choices.",
        "voter_count": 100,
        "candidates": [
            _candidate("solar", "Solar Farm"),
            _candidate("wind", "Wind Turbines"),
            _candidate("nuclear", "Nuclear Plant"),
            _candidate("gas", "Natural Gas"),
        ],
        "controls": [
            _control("polarization", "Polarization", "Widen the gap between fossil and clean-energy blocs.", 50, "Mixed", "Polarized"),
            _control("compromise", "Compromise bloc size", "Grow voters who prefer wind/nuclear as pragmatic compromise choices.", 50, "Small", "Large"),
            _control("strategy", "Strategic voting", "Move some clean-energy first choices toward the perceived viable clean option.", 15, "Sincere", "Strategic"),
            _control("turnout", "Turnout imbalance", "Shift turnout toward gas voters at high values and clean-energy voters at low values.", 50, "Clean edge", "Gas edge"),
            _control("intensity", "Preference intensity", "Make score and quadratic ballots more expressive.", 55, "Soft", "Intense"),
        ],
        "blocs": [
            {"id": "gas-reliability", "name": "Reliability Voters", "description": "Prioritize low prices and dispatchable power.", "share": 34, "color": "oklch(0.65 0.16 50)", "turnout_bias": 0.6, "compromise_bias": -0.3, "strategic_target": "gas", "utilities": {"gas": 92, "nuclear": 68, "wind": 34, "solar": 24}},
            {"id": "solar-greens", "name": "Solar Greens", "description": "Climate voters with a strong preference for solar.", "share": 28, "color": "oklch(0.78 0.17 88)", "turnout_bias": -0.5, "compromise_bias": -0.1, "strategic_target": "wind", "utilities": {"solar": 96, "wind": 84, "nuclear": 48, "gas": 8}},
            {"id": "wind-pragmatists", "name": "Wind Pragmatists", "description": "Clean-energy voters comfortable with practical tradeoffs.", "share": 23, "color": "oklch(0.66 0.12 190)", "turnout_bias": -0.2, "compromise_bias": 0.8, "strategic_target": "wind", "utilities": {"wind": 92, "solar": 76, "nuclear": 66, "gas": 24}},
            {"id": "nuclear-engineers", "name": "Nuclear Engineers", "description": "Decarbonization voters focused on firm power.", "share": 15, "color": "oklch(0.62 0.16 285)", "turnout_bias": 0.1, "compromise_bias": 0.4, "strategic_target": "wind", "utilities": {"nuclear": 94, "wind": 78, "solar": 58, "gas": 40}},
        ],
    },
    {
        "id": "parks",
        "title": "Consensus Park Project",
        "domain": "Parks",
        "thesis": "A polarizing project earns many first-choice votes, but a consistently liked project wins under broad-support methods.",
        "lesson": "Borda and score can reward options that are rarely hated and often ranked second.",
        "voter_count": 100,
        "candidates": [
            _candidate("playground", "Playground"),
            _candidate("garden", "Community Garden"),
            _candidate("sports", "Sports Complex"),
            _candidate("nature", "Nature Preserve"),
            _candidate("pool", "Swimming Pool"),
        ],
        "controls": [
            _control("polarization", "Polarization", "Make factional park preferences more intense.", 40, "Neighborly", "Factional"),
            _control("compromise", "Compromise bloc size", "Grow voters who consistently like the garden.", 60, "Small", "Large"),
            _control("strategy", "Strategic voting", "Move some voters toward their strongest anti-sports alternative.", 10, "Sincere", "Strategic"),
            _control("turnout", "Turnout imbalance", "Shift turnout toward organized sports voters at high values.", 45, "Families edge", "Sports edge"),
            _control("intensity", "Preference intensity", "Make scored support less or more extreme.", 45, "Soft", "Intense"),
        ],
        "blocs": [
            {"id": "sports-league", "name": "Sports League Families", "description": "Organized around fields and tournaments.", "share": 30, "color": "oklch(0.58 0.19 35)", "turnout_bias": 0.7, "compromise_bias": -0.4, "strategic_target": "playground", "utilities": {"sports": 96, "garden": 70, "pool": 58, "playground": 54, "nature": 20}},
            {"id": "young-families", "name": "Young Families", "description": "Want daily-use amenities for children.", "share": 25, "color": "oklch(0.7 0.14 250)", "turnout_bias": -0.2, "compromise_bias": 0.2, "strategic_target": "garden", "utilities": {"playground": 94, "garden": 82, "nature": 64, "pool": 58, "sports": 28}},
            {"id": "garden-neighbors", "name": "Garden Neighbors", "description": "Favor quiet, shared neighborhood space.", "share": 25, "color": "oklch(0.62 0.16 142)", "turnout_bias": -0.1, "compromise_bias": 0.8, "strategic_target": "garden", "utilities": {"garden": 92, "nature": 78, "playground": 72, "pool": 52, "sports": 34}},
            {"id": "nature-advocates", "name": "Nature Advocates", "description": "Prefer preserving habitat and passive recreation.", "share": 20, "color": "oklch(0.55 0.13 118)", "turnout_bias": -0.3, "compromise_bias": 0.3, "strategic_target": "garden", "utilities": {"nature": 94, "garden": 82, "playground": 58, "pool": 42, "sports": 18}},
        ],
    },
    {
        "id": "budget",
        "title": "Intensity In The Budget",
        "domain": "City Budget",
        "thesis": "Moderate support wins many methods, while quadratic voting reveals which priorities voters are willing to spend credits on.",
        "lesson": "Score and quadratic voting expose intensity that rankings flatten.",
        "voter_count": 100,
        "candidates": [
            _candidate("education", "Education"),
            _candidate("health", "Healthcare"),
            _candidate("infra", "Infrastructure"),
            _candidate("defense", "Public Safety"),
            _candidate("arts", "Arts & Culture"),
        ],
        "controls": [
            _control("polarization", "Polarization", "Make budget factions less willing to support rival priorities.", 45, "Coalitional", "Factional"),
            _control("compromise", "Compromise bloc size", "Grow voters who divide support across education, health, and infrastructure.", 50, "Small", "Large"),
            _control("strategy", "Strategic voting", "Move first choices toward broadly viable budget categories.", 10, "Sincere", "Strategic"),
            _control("turnout", "Turnout imbalance", "Shift turnout toward public-safety voters at high values.", 50, "Services edge", "Safety edge"),
            _control("intensity", "Preference intensity", "Make quadratic credit allocations more concentrated.", 70, "Spread", "Concentrated"),
        ],
        "blocs": [
            {"id": "parents", "name": "Parents & Teachers", "description": "Strongly prioritize schools.", "share": 28, "color": "oklch(0.62 0.17 255)", "turnout_bias": -0.2, "compromise_bias": 0.1, "strategic_target": "health", "utilities": {"education": 98, "health": 76, "arts": 62, "infra": 54, "defense": 22}},
            {"id": "care-workers", "name": "Healthcare Advocates", "description": "Prioritize clinics, prevention, and mental health.", "share": 25, "color": "oklch(0.65 0.16 165)", "turnout_bias": -0.1, "compromise_bias": 0.3, "strategic_target": "education", "utilities": {"health": 96, "education": 78, "infra": 60, "arts": 50, "defense": 26}},
            {"id": "builders", "name": "Infrastructure Voters", "description": "Want roads, water, and maintenance funded first.", "share": 22, "color": "oklch(0.66 0.12 75)", "turnout_bias": 0.1, "compromise_bias": 0.4, "strategic_target": "health", "utilities": {"infra": 92, "health": 70, "education": 68, "defense": 52, "arts": 32}},
            {"id": "safety-hawks", "name": "Public Safety Hawks", "description": "Prefer enforcement and emergency-response spending.", "share": 15, "color": "oklch(0.58 0.16 28)", "turnout_bias": 0.8, "compromise_bias": -0.5, "strategic_target": "defense", "utilities": {"defense": 96, "infra": 62, "health": 42, "education": 36, "arts": 8}},
            {"id": "artists", "name": "Cultural Workers", "description": "Small bloc with intense support for arts funding.", "share": 10, "color": "oklch(0.62 0.22 320)", "turnout_bias": -0.3, "compromise_bias": -0.1, "strategic_target": "education", "utilities": {"arts": 100, "education": 72, "health": 66, "infra": 34, "defense": 4}},
        ],
    },
    {
        "id": "cycle",
        "title": "Condorcet Cycle",
        "domain": "Committee Choice",
        "thesis": "Collective preferences can cycle even when every voter has a clear ranking.",
        "lesson": "Ranked Pairs makes the pairwise structure visible and resolves cycles by locking strongest victories first.",
        "voter_count": 100,
        "candidates": [
            _candidate("A", "Plan A"),
            _candidate("B", "Plan B"),
            _candidate("C", "Plan C"),
            _candidate("D", "Plan D"),
        ],
        "controls": [
            _control("polarization", "Polarization", "Strengthen each faction's top plan.", 65, "Soft", "Hard"),
            _control("compromise", "Compromise bloc size", "Grow voters who put Plan D first as a compromise.", 20, "Small", "Large"),
            _control("strategy", "Strategic voting", "Move some first choices toward Plan D.", 15, "Sincere", "Strategic"),
            _control("turnout", "Turnout imbalance", "Shift turnout from Plan C voters toward Plan A voters.", 50, "C edge", "A edge"),
            _control("intensity", "Preference intensity", "Make score ballots more decisive.", 55, "Soft", "Intense"),
        ],
        "blocs": [
            {"id": "a-over-b", "name": "A over B Bloc", "description": "Prefers A, then B, then C.", "share": 32, "color": "oklch(0.62 0.18 20)", "turnout_bias": 0.6, "compromise_bias": -0.2, "strategic_target": "D", "utilities": {"A": 96, "B": 72, "C": 46, "D": 40}},
            {"id": "b-over-c", "name": "B over C Bloc", "description": "Prefers B, then C, then A.", "share": 28, "color": "oklch(0.62 0.16 250)", "turnout_bias": 0.0, "compromise_bias": -0.1, "strategic_target": "D", "utilities": {"B": 96, "C": 72, "A": 46, "D": 40}},
            {"id": "c-over-a", "name": "C over A Bloc", "description": "Prefers C, then A, then B.", "share": 28, "color": "oklch(0.62 0.16 145)", "turnout_bias": -0.6, "compromise_bias": -0.1, "strategic_target": "D", "utilities": {"C": 96, "A": 72, "B": 46, "D": 40}},
            {"id": "d-compromise", "name": "D Compromise Bloc", "description": "Small group that likes the lower-conflict fallback.", "share": 12, "color": "oklch(0.66 0.12 85)", "turnout_bias": 0.0, "compromise_bias": 1.0, "strategic_target": "D", "utilities": {"D": 86, "A": 62, "B": 62, "C": 62}},
        ],
    },
]


def list_demo_scenarios() -> list[dict[str, Any]]:
    return [_public_scenario(s) for s in SCENARIOS]


def resolve_demo_scenario(scenario_id: str, controls: dict[str, int] | None = None) -> dict[str, Any] | None:
    scenario = _find_scenario(scenario_id)
    if scenario is None:
        return None

    values = _control_values(scenario, controls or {})
    adjusted_blocs = _adjust_blocs(scenario, values)
    candidates = [Candidate(id=c["id"], name=c["name"]) for c in scenario["candidates"]]
    candidate_ids = [c.id for c in candidates]

    ballots = _derive_ballots(adjusted_blocs, candidate_ids, values)
    results = {
        "plurality": asdict(resolve_plurality(candidates, ballots["plurality"]["resolver"], deterministic_tiebreak)),
        "approval": asdict(resolve_approval(candidates, ballots["approval"]["resolver"], deterministic_tiebreak)),
        "irv": asdict(resolve_irv(candidates, ballots["ranked"]["resolver"], deterministic_tiebreak)),
        "borda": asdict(resolve_borda(candidates, ballots["ranked"]["resolver"], deterministic_tiebreak)),
        "ranked_pairs": asdict(resolve_ranked_pairs(candidates, ballots["ranked"]["resolver"], deterministic_tiebreak)),
        "score": asdict(resolve_score(candidates, ballots["score"]["resolver"], deterministic_tiebreak)),
        "quadratic": asdict(resolve_quadratic(candidates, ballots["quadratic"]["resolver"], deterministic_tiebreak)),
    }

    comparison = {
        method: _comparison_row(method, results[method], candidates)
        for method in METHODS
    }

    return {
        "scenario": _public_scenario(scenario, adjusted_blocs=adjusted_blocs),
        "controls": values,
        "results": results,
        "comparison": comparison,
        "annotations": _annotations(results, comparison),
        "derived_ballots": {
            key: value["payload"]
            for key, value in ballots.items()
        },
    }


def _find_scenario(scenario_id: str) -> dict[str, Any] | None:
    return next((s for s in SCENARIOS if s["id"] == scenario_id), None)


def _public_scenario(
    scenario: dict[str, Any],
    adjusted_blocs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    controls = scenario["controls"]
    return {
        "id": scenario["id"],
        "title": scenario["title"],
        "domain": scenario["domain"],
        "thesis": scenario["thesis"],
        "lesson": scenario["lesson"],
        "voter_count": scenario["voter_count"],
        "candidates": scenario["candidates"],
        "controls": controls,
        "default_controls": {c["id"]: c["default"] for c in controls},
        "blocs": adjusted_blocs or scenario["blocs"],
    }


def _control_values(scenario: dict[str, Any], overrides: dict[str, int]) -> dict[str, int]:
    values = {c["id"]: c["default"] for c in scenario["controls"]}
    for key, value in overrides.items():
        if key in values:
            values[key] = int(max(0, min(100, value)))
    return values


def _adjust_blocs(scenario: dict[str, Any], controls: dict[str, int]) -> list[dict[str, Any]]:
    polarization = controls["polarization"] / 100
    compromise = (controls["compromise"] - 50) / 50
    turnout = (controls["turnout"] - 50) / 50
    intensity = controls["intensity"] / 100

    adjusted = []
    raw_weights = []
    for bloc in scenario["blocs"]:
        weight = bloc["share"]
        weight *= 1 + (bloc.get("compromise_bias", 0) * compromise * 0.45)
        weight *= 1 + (bloc.get("turnout_bias", 0) * turnout * 0.35)
        weight = max(1, weight)
        raw_weights.append(weight)

        utilities = {}
        for cid, utility in bloc["utilities"].items():
            spread = utility - 50
            adjusted_utility = 50 + spread * (0.72 + polarization * 0.5 + intensity * 0.18)
            utilities[cid] = int(round(max(0, min(100, adjusted_utility))))

        adjusted.append({**bloc, "utilities": utilities})

    total = sum(raw_weights)
    scaled_counts = [max(1, round((w / total) * scenario["voter_count"])) for w in raw_weights]
    delta = scenario["voter_count"] - sum(scaled_counts)
    while delta != 0:
        if delta > 0:
            index = max(range(len(scaled_counts)), key=lambda i: raw_weights[i])
            scaled_counts[index] += 1
            delta -= 1
        else:
            index = max(range(len(scaled_counts)), key=lambda i: scaled_counts[i])
            if scaled_counts[index] > 1:
                scaled_counts[index] -= 1
                delta += 1
            else:
                break

    for bloc, count in zip(adjusted, scaled_counts):
        bloc["voters"] = count
        bloc["share"] = round((count / scenario["voter_count"]) * 100, 1)
        bloc["preference_summary"] = _preference_summary(bloc)

    return adjusted


def _derive_ballots(
    blocs: list[dict[str, Any]],
    candidate_ids: list[str],
    controls: dict[str, int],
) -> dict[str, dict[str, Any]]:
    resolver_ballots = {
        "plurality": [],
        "approval": [],
        "ranked": [],
        "score": [],
        "quadratic": [],
    }
    payload_ballots = {
        "plurality": [],
        "approval": [],
        "ranked": [],
        "score": [],
        "quadratic": [],
    }

    voter_index = 0
    for bloc in blocs:
        ranked = _ranking(bloc, candidate_ids)
        approvals = [cid for cid in ranked if bloc["utilities"][cid] >= _approval_threshold(controls)]
        if not approvals:
            approvals = [ranked[0]]
        scores = _scores(bloc, candidate_ids, controls)
        allocations = _quadratic_allocations(bloc, ranked, controls)
        strategic_count = round(bloc["voters"] * controls["strategy"] / 100)

        for i in range(bloc["voters"]):
            voter_index += 1
            voter_id = f"{bloc['id']}-{voter_index}"
            plurality_choice = ranked[0]
            if i < strategic_count and bloc.get("strategic_target") in candidate_ids:
                plurality_choice = bloc["strategic_target"]

            resolver_ballots["plurality"].append(create_single_choice_ballot(voter_id, plurality_choice))
            resolver_ballots["approval"].append(create_approval_ballot(voter_id, approvals))
            resolver_ballots["ranked"].append(create_ranked_choice_ballot(voter_id, ranked, candidate_ids))
            resolver_ballots["score"].append(create_score_ballot(voter_id, scores))
            resolver_ballots["quadratic"].append(create_quadratic_ballot(voter_id, allocations, credit_budget=100))

            payload_ballots["plurality"].append({"voter_id": voter_id, "choice": plurality_choice, "bloc": bloc["id"]})
            payload_ballots["approval"].append({"voter_id": voter_id, "approvals": approvals, "bloc": bloc["id"]})
            payload_ballots["ranked"].append({"voter_id": voter_id, "ranking": ranked, "bloc": bloc["id"]})
            payload_ballots["score"].append({"voter_id": voter_id, "scores": scores, "bloc": bloc["id"]})
            payload_ballots["quadratic"].append({"voter_id": voter_id, "allocations": allocations, "credit_budget": 100, "bloc": bloc["id"]})

    return {
        key: {"resolver": resolver_ballots[key], "payload": payload_ballots[key]}
        for key in resolver_ballots
    }


def _ranking(bloc: dict[str, Any], candidate_ids: list[str]) -> list[str]:
    return sorted(candidate_ids, key=lambda cid: (-bloc["utilities"].get(cid, 0), cid))


def _approval_threshold(controls: dict[str, int]) -> int:
    return int(round(54 + (controls["polarization"] - 50) * 0.08))


def _scores(bloc: dict[str, Any], candidate_ids: list[str], controls: dict[str, int]) -> dict[str, int]:
    exaggeration = controls["intensity"] / 100
    scores = {}
    for cid in candidate_ids:
        utility = bloc["utilities"].get(cid, 0)
        adjusted = 50 + (utility - 50) * (0.8 + exaggeration * 0.45)
        scores[cid] = int(round(max(0, min(10, adjusted / 10))))
    return scores


def _quadratic_allocations(
    bloc: dict[str, Any],
    ranked: list[str],
    controls: dict[str, int],
) -> dict[str, int]:
    intensity = 0.55 + controls["intensity"] / 100
    allocations: dict[str, int] = {}
    for cid in ranked[:3]:
        utility = bloc["utilities"].get(cid, 0)
        if utility >= 55:
            allocations[cid] = max(1, min(7, round(((utility - 45) / 55) * 5 * intensity)))

    lowest = ranked[-1]
    if bloc["utilities"].get(lowest, 50) <= 20 and controls["polarization"] >= 45:
        allocations[lowest] = -2

    while sum(v * v for v in allocations.values()) > 100:
        key = max(allocations, key=lambda k: abs(allocations[k]))
        allocations[key] += -1 if allocations[key] > 0 else 1
        if allocations[key] == 0:
            del allocations[key]

    return allocations


def _comparison_row(method: str, result: dict[str, Any], candidates: list[Candidate]) -> dict[str, Any]:
    name_map = {c.id: c.name for c in candidates}
    winner_id = result["winners"][0] if result["winners"] else None
    basis = _result_basis(method, result)
    return {
        "method": method,
        "winner": winner_id,
        "winner_name": name_map.get(winner_id, "No winner"),
        "basis": basis,
        "reason": _reason(method, result, name_map),
    }


def _result_basis(method: str, result: dict[str, Any]) -> str:
    if method == "approval":
        return "Approvals"
    if method == "irv":
        return f"Round {result.get('winning_round', '-')}"
    if method == "borda":
        return "Borda points"
    if method == "ranked_pairs":
        return "Pairwise wins"
    if method == "score":
        return "Total score"
    if method == "quadratic":
        return "Net QV votes"
    return "First choices"


def _reason(method: str, result: dict[str, Any], name_map: dict[str, str]) -> str:
    winner = result["winners"][0] if result["winners"] else ""
    winner_name = name_map.get(winner, winner)
    if method == "plurality":
        return f"{winner_name} has the most first-choice votes, even if similar alternatives split support."
    if method == "approval":
        return f"{winner_name} is acceptable to the largest number of voters."
    if method == "irv":
        return f"{winner_name} survives eliminations and transfers among remaining ballots."
    if method == "borda":
        return f"{winner_name} earns the strongest ranking points across the full ballot."
    if method == "ranked_pairs":
        return f"{winner_name} has the strongest pairwise path after cycles are handled."
    if method == "score":
        return f"{winner_name} receives the highest total rating when intensity is counted."
    return f"{winner_name} receives the strongest net allocation after quadratic costs."


def _annotations(
    results: dict[str, dict[str, Any]],
    comparison: dict[str, dict[str, Any]],
) -> list[dict[str, str]]:
    annotations: list[dict[str, str]] = []
    plurality_winner = comparison["plurality"]["winner"]
    approval_winner = comparison["approval"]["winner"]
    ranked_pairs = results["ranked_pairs"]
    score_winner = comparison["score"]["winner"]
    quadratic_winner = comparison["quadratic"]["winner"]

    if plurality_winner and approval_winner and plurality_winner != approval_winner:
        annotations.append({
            "type": "spoiler_effect",
            "label": "Spoiler effect detected",
            "severity": "warning",
            "description": "Plurality selects a different winner than approval, suggesting first-choice vote splitting or narrow factional support.",
        })

    if approval_winner in {
        comparison["borda"]["winner"],
        comparison["score"]["winner"],
        comparison["ranked_pairs"]["winner"],
    }:
        annotations.append({
            "type": "consensus_winner",
            "label": "Consensus winner surfaced",
            "severity": "success",
            "description": "Multiple broad-support methods converge on the same winner.",
        })

    annotations.append({
        "type": "condorcet",
        "label": "Condorcet winner selected" if ranked_pairs.get("had_condorcet_winner") else "Condorcet cycle resolved",
        "severity": "info",
        "description": "Ranked Pairs checks every head-to-head matchup and then locks victories from strongest to weakest.",
    })

    irv_rounds = results["irv"].get("rounds", [])
    if irv_rounds:
        first_round_leader = max(irv_rounds[0]["vote_counts"].items(), key=lambda item: item[1])[0]
        if first_round_leader != comparison["irv"]["winner"]:
            annotations.append({
                "type": "transfer_comeback",
                "label": "Transfer comeback",
                "severity": "info",
                "description": "The IRV winner was not the first-round leader; lower-ranked preferences changed the outcome.",
            })

    ordinal_winners = {comparison[m]["winner"] for m in ["plurality", "irv", "borda", "ranked_pairs"]}
    if score_winner not in ordinal_winners or quadratic_winner not in ordinal_winners:
        annotations.append({
            "type": "intensity_changes_outcome",
            "label": "Intensity changes outcome",
            "severity": "warning",
            "description": "Score or quadratic voting differs from ordinal methods because voters can express strength of preference.",
        })

    return annotations


def _preference_summary(bloc: dict[str, Any]) -> str:
    ranked = sorted(bloc["utilities"].items(), key=lambda item: (-item[1], item[0]))
    return " > ".join(cid for cid, _ in ranked[:3])
