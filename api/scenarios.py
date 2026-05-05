"""
Curated example elections for each voting method.

Each scenario is designed to highlight the unique behavior and trade-offs
of its method with ~15-25 voters — enough to demonstrate dynamics while
remaining walkable.
"""

from voting.types import Candidate

# Shared candidate pools
# -----------------------------------------------------------------------

_TRANSPORT_CANDIDATES = [
    Candidate(id="bus", name="Bus Rapid Transit"),
    Candidate(id="rail", name="Light Rail"),
    Candidate(id="bike", name="Protected Bike Lanes"),
    Candidate(id="highway", name="Highway Expansion"),
]

_ENERGY_CANDIDATES = [
    Candidate(id="solar", name="Solar Farm"),
    Candidate(id="wind", name="Wind Turbines"),
    Candidate(id="nuclear", name="Nuclear Plant"),
    Candidate(id="gas", name="Natural Gas"),
]

_PARK_CANDIDATES = [
    Candidate(id="playground", name="Playground"),
    Candidate(id="garden", name="Community Garden"),
    Candidate(id="sports", name="Sports Complex"),
    Candidate(id="nature", name="Nature Preserve"),
    Candidate(id="pool", name="Swimming Pool"),
]

_BUDGET_CANDIDATES = [
    Candidate(id="education", name="Education"),
    Candidate(id="health", name="Healthcare"),
    Candidate(id="infra", name="Infrastructure"),
    Candidate(id="defense", name="Defense"),
    Candidate(id="arts", name="Arts & Culture"),
]


# Scenario data structure
# -----------------------------------------------------------------------

def get_scenarios() -> dict:
    """Return all 7 curated election scenarios."""
    return {
        "plurality": _plurality_scenario(),
        "approval": _approval_scenario(),
        "irv": _irv_scenario(),
        "borda": _borda_scenario(),
        "ranked_pairs": _ranked_pairs_scenario(),
        "score": _score_scenario(),
        "quadratic": _quadratic_scenario(),
    }


def get_scenario(method: str) -> dict | None:
    """Return a single scenario by method name."""
    scenarios = get_scenarios()
    return scenarios.get(method)


# Individual scenarios
# -----------------------------------------------------------------------

def _plurality_scenario() -> dict:
    """
    'The Spoiler Effect' — two similar candidates split the progressive vote,
    letting the minority-preferred candidate win.
    """
    candidates = _TRANSPORT_CANDIDATES
    cids = [c.id for c in candidates]

    # 20 voters: Bus and Rail split the transit vote, Highway wins with plurality
    ballots = []
    voter = 0

    # 7 voters prefer Bus (transit progressives group A)
    for _ in range(7):
        voter += 1
        ballots.append({"voter_id": f"v{voter}", "choice": "bus"})

    # 6 voters prefer Rail (transit progressives group B)
    for _ in range(6):
        voter += 1
        ballots.append({"voter_id": f"v{voter}", "choice": "rail"})

    # 3 voters prefer Bike Lanes
    for _ in range(3):
        voter += 1
        ballots.append({"voter_id": f"v{voter}", "choice": "bike"})

    # 8 voters prefer Highway
    for _ in range(8):
        voter += 1
        ballots.append({"voter_id": f"v{voter}", "choice": "highway"})

    return {
        "method": "plurality",
        "title": "The Spoiler Effect",
        "description": (
            "A city votes on a transportation plan. Two transit options (Bus and Rail) "
            "split the progressive vote, allowing Highway Expansion to win with only 33% "
            "support — even though 54% of voters preferred a transit option."
        ),
        "candidates": [{"id": c.id, "name": c.name} for c in candidates],
        "ballots": ballots,
        "ballot_type": "single_choice",
        "voter_count": voter,
        "key_insight": "The winner has only 33% support. A majority preferred transit options.",
    }


def _approval_scenario() -> dict:
    """
    'Finding Consensus' — the most broadly acceptable candidate wins,
    even if they're nobody's first choice in a plurality system.
    """
    candidates = _TRANSPORT_CANDIDATES
    voter = 0
    ballots = []

    # 7 Bus fans — also approve Rail (similar transit option)
    for _ in range(7):
        voter += 1
        ballots.append({"voter_id": f"v{voter}", "approvals": ["bus", "rail"]})

    # 6 Rail fans — also approve Bus
    for _ in range(6):
        voter += 1
        ballots.append({"voter_id": f"v{voter}", "approvals": ["rail", "bus"]})

    # 3 Bike fans — also approve Bus and Rail (all transit)
    for _ in range(3):
        voter += 1
        ballots.append({"voter_id": f"v{voter}", "approvals": ["bike", "bus", "rail"]})

    # 8 Highway fans — only approve highway
    for _ in range(8):
        voter += 1
        ballots.append({"voter_id": f"v{voter}", "approvals": ["highway"]})

    return {
        "method": "approval",
        "title": "Finding Consensus",
        "description": (
            "Same transportation election, but voters can approve multiple options. "
            "Transit supporters approve each other's plans. The broadly acceptable "
            "option emerges — even though Highway had the most plurality support."
        ),
        "candidates": [{"id": c.id, "name": c.name} for c in candidates],
        "ballots": ballots,
        "ballot_type": "approval",
        "voter_count": voter,
        "key_insight": "Rail and Bus both beat Highway because approval captures breadth of support.",
    }


def _irv_scenario() -> dict:
    """
    'Elimination Changes Everything' — the first-round leader loses
    after lower candidates are eliminated and votes redistribute.
    """
    candidates = _ENERGY_CANDIDATES
    cids = [c.id for c in candidates]
    voter = 0
    ballots = []

    # 8 voters: Gas > Nuclear > Wind > Solar (gas loyalists)
    for _ in range(8):
        voter += 1
        ballots.append({
            "voter_id": f"v{voter}",
            "ranking": ["gas", "nuclear", "wind", "solar"],
        })

    # 7 voters: Solar > Wind > Nuclear > Gas (green first-choice)
    for _ in range(7):
        voter += 1
        ballots.append({
            "voter_id": f"v{voter}",
            "ranking": ["solar", "wind", "nuclear", "gas"],
        })

    # 5 voters: Wind > Solar > Nuclear > Gas
    for _ in range(5):
        voter += 1
        ballots.append({
            "voter_id": f"v{voter}",
            "ranking": ["wind", "solar", "nuclear", "gas"],
        })

    # 3 voters: Nuclear > Wind > Solar > Gas
    for _ in range(3):
        voter += 1
        ballots.append({
            "voter_id": f"v{voter}",
            "ranking": ["nuclear", "wind", "solar", "gas"],
        })

    return {
        "method": "irv",
        "title": "Elimination Changes Everything",
        "description": (
            "A region votes on an energy plan. Gas leads in the first round with 8 votes, "
            "but as less popular options are eliminated, their voters' second choices "
            "concentrate around a clean-energy alternative."
        ),
        "candidates": [{"id": c.id, "name": c.name} for c in candidates],
        "ballots": ballots,
        "ballot_type": "ranked_choice",
        "voter_count": voter,
        "key_insight": "The first-round leader (Gas) loses as eliminated voters' preferences redistribute.",
    }


def _borda_scenario() -> dict:
    """
    'Broad Support Wins' — a candidate who is consistently ranked 2nd
    beats a polarizing candidate who gets lots of 1st and last places.
    """
    candidates = _PARK_CANDIDATES
    cids = [c.id for c in candidates]
    voter = 0
    ballots = []

    # 6 voters: Sports > Garden > Pool > Playground > Nature
    for _ in range(6):
        voter += 1
        ballots.append({
            "voter_id": f"v{voter}",
            "ranking": ["sports", "garden", "pool", "playground", "nature"],
        })

    # 5 voters: Playground > Garden > Nature > Pool > Sports
    for _ in range(5):
        voter += 1
        ballots.append({
            "voter_id": f"v{voter}",
            "ranking": ["playground", "garden", "nature", "pool", "sports"],
        })

    # 4 voters: Nature > Garden > Playground > Pool > Sports
    for _ in range(4):
        voter += 1
        ballots.append({
            "voter_id": f"v{voter}",
            "ranking": ["nature", "garden", "playground", "pool", "sports"],
        })

    # 4 voters: Pool > Garden > Sports > Nature > Playground
    for _ in range(4):
        voter += 1
        ballots.append({
            "voter_id": f"v{voter}",
            "ranking": ["pool", "garden", "sports", "nature", "playground"],
        })

    # 3 voters: Garden > Nature > Playground > Pool > Sports
    for _ in range(3):
        voter += 1
        ballots.append({
            "voter_id": f"v{voter}",
            "ranking": ["garden", "nature", "playground", "pool", "sports"],
        })

    return {
        "method": "borda",
        "title": "Broad Support Wins",
        "description": (
            "A neighborhood votes on a park project. Sports Complex gets the most "
            "first-place votes but is ranked last by many others. Community Garden "
            "is consistently ranked 2nd and wins on broad appeal."
        ),
        "candidates": [{"id": c.id, "name": c.name} for c in candidates],
        "ballots": ballots,
        "ballot_type": "ranked_choice",
        "voter_count": voter,
        "key_insight": "Garden wins by being broadly liked, even though Sports gets the most 1st-place votes.",
    }


def _ranked_pairs_scenario() -> dict:
    """
    'Breaking the Cycle' — A beats B, B beats C, C beats A.
    Ranked pairs resolves this by locking victories from strongest margin first.
    """
    candidates = [
        Candidate(id="A", name="Plan A"),
        Candidate(id="B", name="Plan B"),
        Candidate(id="C", name="Plan C"),
        Candidate(id="D", name="Plan D"),
    ]
    voter = 0
    ballots = []

    # 7 voters: A > B > C > D
    for _ in range(7):
        voter += 1
        ballots.append({
            "voter_id": f"v{voter}",
            "ranking": ["A", "B", "C", "D"],
        })

    # 5 voters: B > C > A > D
    for _ in range(5):
        voter += 1
        ballots.append({
            "voter_id": f"v{voter}",
            "ranking": ["B", "C", "A", "D"],
        })

    # 4 voters: C > A > B > D
    for _ in range(4):
        voter += 1
        ballots.append({
            "voter_id": f"v{voter}",
            "ranking": ["C", "A", "B", "D"],
        })

    # 3 voters: D > C > B > A
    for _ in range(3):
        voter += 1
        ballots.append({
            "voter_id": f"v{voter}",
            "ranking": ["D", "C", "B", "A"],
        })

    return {
        "method": "ranked_pairs",
        "title": "Breaking the Cycle",
        "description": (
            "A committee chooses between four plans. The group preferences form a "
            "cycle: A beats B, B beats C, but C beats A in head-to-head matchups. "
            "Ranked Pairs resolves this by locking the strongest victories first "
            "and skipping any that would create a cycle."
        ),
        "candidates": [{"id": c.id, "name": c.name} for c in candidates],
        "ballots": ballots,
        "ballot_type": "ranked_choice",
        "voter_count": voter,
        "key_insight": "When preferences cycle, Ranked Pairs uses margin strength to find the fairest winner.",
    }


def _score_scenario() -> dict:
    """
    'Intensity Matters' — a candidate with strong 8-9 scores beats one
    with polarized 10s and 0s.
    """
    candidates = _ENERGY_CANDIDATES
    voter = 0
    ballots = []

    # 8 voters strongly for Gas, strongly against Solar
    for _ in range(8):
        voter += 1
        ballots.append({
            "voter_id": f"v{voter}",
            "scores": {"gas": 10, "nuclear": 6, "wind": 2, "solar": 0},
        })

    # 7 voters strongly for Solar, hate Gas
    for _ in range(7):
        voter += 1
        ballots.append({
            "voter_id": f"v{voter}",
            "scores": {"solar": 10, "wind": 9, "nuclear": 4, "gas": 0},
        })

    # 5 voters moderate — like Wind most, acceptable to all
    for _ in range(5):
        voter += 1
        ballots.append({
            "voter_id": f"v{voter}",
            "scores": {"wind": 9, "solar": 7, "nuclear": 6, "gas": 3},
        })

    # 3 voters pro-nuclear
    for _ in range(3):
        voter += 1
        ballots.append({
            "voter_id": f"v{voter}",
            "scores": {"nuclear": 10, "wind": 8, "solar": 5, "gas": 4},
        })

    return {
        "method": "score",
        "title": "Intensity Matters",
        "description": (
            "A region rates energy options 0-10. Gas and Solar are polarizing (lots of "
            "10s and 0s). Wind Turbines receive consistent 8-9 scores from nearly "
            "everyone, capturing preference intensity that plurality misses."
        ),
        "candidates": [{"id": c.id, "name": c.name} for c in candidates],
        "ballots": ballots,
        "ballot_type": "score",
        "voter_count": voter,
        "key_insight": "Wind wins because consistent high scores beat polarizing love-it-or-hate-it options.",
    }


def _quadratic_scenario() -> dict:
    """
    'Strategic Allocation' — v² cost forces voters to spread support,
    rewarding those who allocate wisely across issues they care about.
    """
    candidates = _BUDGET_CANDIDATES
    voter = 0
    ballots = []

    # 6 voters: focus heavily on Education
    for _ in range(6):
        voter += 1
        ballots.append({
            "voter_id": f"v{voter}",
            "allocations": {"education": 7, "health": 4, "arts": 3},
            "credit_budget": 100,
        })

    # 5 voters: focus on Healthcare
    for _ in range(5):
        voter += 1
        ballots.append({
            "voter_id": f"v{voter}",
            "allocations": {"health": 8, "education": 4, "infra": 2},
            "credit_budget": 100,
        })

    # 4 voters: balanced infra/defense
    for _ in range(4):
        voter += 1
        ballots.append({
            "voter_id": f"v{voter}",
            "allocations": {"infra": 6, "defense": 5, "health": 3},
            "credit_budget": 100,
        })

    # 3 voters: anti-defense, pro-arts
    for _ in range(3):
        voter += 1
        ballots.append({
            "voter_id": f"v{voter}",
            "allocations": {"arts": 7, "education": 5, "defense": -3},
            "credit_budget": 100,
        })

    # 2 voters: spread across everything
    for _ in range(2):
        voter += 1
        ballots.append({
            "voter_id": f"v{voter}",
            "allocations": {"education": 4, "health": 4, "infra": 4, "arts": 4},
            "credit_budget": 100,
        })

    return {
        "method": "quadratic",
        "title": "Strategic Allocation",
        "description": (
            "Citizens allocate 100 credits across budget priorities. The cost to cast "
            "v votes is v², so going all-in on one issue is expensive. "
            "This encourages spreading support and allows expressing opposition "
            "through negative votes."
        ),
        "candidates": [{"id": c.id, "name": c.name} for c in candidates],
        "ballots": ballots,
        "ballot_type": "quadratic",
        "voter_count": voter,
        "key_insight": "Quadratic cost prevents a passionate minority from dominating. Defense gets negative votes.",
    }
