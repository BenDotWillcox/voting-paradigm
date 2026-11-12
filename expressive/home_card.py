"""Export a small, exact sample of the prepared electorate for the home card.

The home page renders without the Python service, so the card reads a
committed JSON artifact. It holds real fixture voters (not new curves),
evenly spaced through the electorate ordered by ideal rate, mirroring the
demo's voter browser. A test regenerates the payload and compares it with the
committed file, so the card cannot drift from the fixture.

Regenerate with ``python -m expressive.home_card``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from expressive.comparison import ELECTORATE_SEED, PROPOSAL, STATUS_QUO, prepared_voters

ARTIFACT = Path(__file__).resolve().parent.parent / "lib" / "expressive-home-card.json"
SAMPLE_SIZE = 14
# The card's axis runs 0-10%; keep each sampled peak inside it.
MAX_IDEAL = 9.0


def home_card_payload() -> dict[str, Any]:
    voters = prepared_voters()
    ordered = sorted((v for v in voters if v.ballot.ideal <= MAX_IDEAL), key=lambda v: (v.ballot.ideal, v.id))
    step = (len(ordered) - 1) / (SAMPLE_SIZE - 1)
    sample = [ordered[round(index * step)] for index in range(SAMPLE_SIZE)]
    return {
        "source": "expressive.comparison.prepared_voters",
        "seed": ELECTORATE_SEED,
        "status_quo": STATUS_QUO,
        "proposal": PROPOSAL,
        "electorate_size": len(voters),
        "binary_tally": {
            vote: sum(1 for v in voters if v.binary_vote == vote) for vote in ("yes", "no", "abstain")
        },
        "voters": [
            {
                "id": v.id,
                "label": v.label,
                "ideal": v.ballot.ideal,
                "lower_half_width": v.ballot.lower_half_width,
                "upper_half_width": v.ballot.upper_half_width,
                "approval_min": v.ballot.approval_min,
                "approval_max": v.ballot.approval_max,
                "binary_vote": v.binary_vote,
            }
            for v in sample
        ],
    }


def render() -> str:
    return json.dumps(home_card_payload(), indent=2) + "\n"


if __name__ == "__main__":
    ARTIFACT.write_text(render(), encoding="utf-8", newline="\n")
    print(f"Wrote {ARTIFACT}")
