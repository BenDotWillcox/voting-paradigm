"""
Two numbers demo 5's research protocol takes from Voteview (amendments A1
and A4 in prompts/demo-5-liquid-democracy.md):

  1. How often House members cast a yea or nay on roll calls held while
     they were members (the office-holder turnout rate).
  2. How many contested substantive roll calls one Congress takes: passage
     and amendment votes, excluding procedural motions, where the minority
     side had at least 10% (the realistic length of a voting record).

Reads the cached files, which are not in the repo. Fetch them once from
https://voteview.com/static/data/out/ into .cache/voteview/:
votes/H117_votes.csv, votes/H118_votes.csv, rollcalls/H117_rollcalls.csv,
rollcalls/H118_rollcalls.csv. Their SHA-256 are checked below.

    python -m scripts.voteview_house_rates
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".cache/voteview"
FILES = {
    "H117_votes.csv": "275556a0c568a8e2b63e0055bd8b9b90a3b4ba4a56e33806b248987a0a83abea",
    "H118_votes.csv": "010f076aeba2bff307cb3326dd03c35ecc8c7f87f0628573345ce025e513ad09",
    "H117_rollcalls.csv": "833cac93ea9029c33212e307cd32655101c3e3b6352ed0cfdf16ac86056ac35d",
    "H118_rollcalls.csv": "11dc64dcc712e6946b0de10bc02871a53b4a1243ba736a32403ab22b7aa817c1",
}
# Voteview cast codes: 1 yea, 6 nay; 2-5 paired or announced (not votes);
# 7-8 present; 9 not voting; 0 not a member at the time
YEA_NAY = {1, 6}
CONTESTED_MINORITY = 0.10


def _check() -> None:
    for name, digest in FILES.items():
        path = CACHE / name
        if not path.exists():
            sys.exit(f"Missing {path}; see this script's docstring.")
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            sys.exit(f"{path} does not match its recorded SHA-256.")


def participation(congress: str) -> dict[str, float]:
    """Yea-or-nay share of roll calls held while each member served."""
    cast = eligible = 0
    per_member: dict[str, list[int]] = {}
    with (CACHE / f"H{congress}_votes.csv").open(newline="") as handle:
        for row in csv.DictReader(handle):
            code = int(float(row["cast_code"]))
            if code == 0:
                continue
            counts = per_member.setdefault(row["icpsr"], [0, 0])
            counts[1] += 1
            eligible += 1
            if code in YEA_NAY:
                counts[0] += 1
                cast += 1
    rates = sorted(c / e for c, e in per_member.values() if e >= 100)
    return {
        "pooled": cast / eligible,
        "member_median": rates[len(rates) // 2],
        "member_p10": rates[len(rates) // 10],
        "members": len(per_member),
    }


def _kind(question: str) -> str:
    q = question.lower()
    if "agreeing to the amendment" in q:
        return "amendment"
    if any(
        k in q
        for k in (
            "on passage",
            "suspend the rules and pass",
            "concur in the senate",
            "objections of the president",
        )
    ):
        return "passage"
    return "procedural"


def substantive(congress: str) -> dict[str, int]:
    """Roll calls by kind, and the contested passage and amendment votes."""
    counts = {"procedural": 0, "passage": 0, "amendment": 0, "contested_substantive": 0}
    with (CACHE / f"H{congress}_rollcalls.csv").open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            kind = _kind(row["vote_question"])
            counts[kind] += 1
            yea, nay = int(row["yea_count"] or 0), int(row["nay_count"] or 0)
            if kind != "procedural" and yea + nay and min(yea, nay) / (yea + nay) >= CONTESTED_MINORITY:
                counts["contested_substantive"] += 1
    return counts


def main() -> None:
    _check()
    out = {c: {"participation": participation(c), "roll_calls": substantive(c)} for c in ("117", "118")}
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
