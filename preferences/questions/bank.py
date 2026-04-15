"""
Question bank: manages the pool of items used to construct pairwise questions.

In v1, the "bank" is a JSON file of civic value items. The engine generates
pairwise questions dynamically by picking two items — this way the same N items
produce N*(N-1)/2 possible questions without predefined pairs.
"""

import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..types import ItemId, Question, QuestionOption, QuestionType


@dataclass
class Item:
    """A single civic value item."""
    id: ItemId
    text: str
    description: str = ""
    domain: Optional[str] = None


DEFAULT_SEED_PATH = Path(__file__).parent / "seed_items.json"


class QuestionBank:
    """A pool of items used to dynamically construct pairwise questions."""

    def __init__(self, items: list[Item]):
        if len(items) < 2:
            raise ValueError("QuestionBank requires at least 2 items")
        self.items = items
        self._by_id = {it.id: it for it in items}

    @classmethod
    def load_default(cls) -> "QuestionBank":
        """Load the bundled seed items."""
        return cls.load_from_path(DEFAULT_SEED_PATH)

    @classmethod
    def load_from_path(cls, path: Path | str) -> "QuestionBank":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        items = [
            Item(
                id=it["id"],
                text=it["text"],
                description=it.get("description", ""),
                domain=it.get("domain"),
            )
            for it in data["items"]
        ]
        return cls(items)

    def item_ids(self) -> list[ItemId]:
        return [it.id for it in self.items]

    def get(self, item_id: ItemId) -> Item:
        return self._by_id[item_id]

    def domains(self) -> list[str]:
        return sorted({it.domain for it in self.items if it.domain})

    # ------------------------------------------------------------------
    # Question generation
    # ------------------------------------------------------------------

    def build_pairwise_question(
        self,
        item_a_id: ItemId,
        item_b_id: ItemId,
        question_id: Optional[str] = None,
    ) -> Question:
        """Build a pairwise Question from two item ids."""
        a = self.get(item_a_id)
        b = self.get(item_b_id)
        qid = question_id or f"pairwise_{a.id}_vs_{b.id}"
        domain = a.domain if a.domain == b.domain else "cross_domain"
        return Question(
            id=qid,
            question_type=QuestionType.PAIRWISE,
            prompt=f"Which matters more to you: {a.text} or {b.text}?",
            options=[
                QuestionOption(
                    item_id=a.id, text=a.text, description=a.description
                ),
                QuestionOption(
                    item_id=b.id, text=b.text, description=b.description
                ),
            ],
            domain=domain,
            source="bank",
        )

    def random_pair(
        self,
        exclude_pairs: Optional[set[frozenset[ItemId]]] = None,
        rng: Optional[random.Random] = None,
    ) -> tuple[ItemId, ItemId]:
        """Pick a random pair of distinct items, optionally avoiding seen pairs."""
        rng = rng or random.Random()
        exclude_pairs = exclude_pairs or set()
        max_tries = 200
        ids = [it.id for it in self.items]
        for _ in range(max_tries):
            a, b = rng.sample(ids, 2)
            if frozenset((a, b)) not in exclude_pairs:
                return a, b
        # Fall back to first unseen pair if saturation
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                if frozenset((ids[i], ids[j])) not in exclude_pairs:
                    return ids[i], ids[j]
        raise RuntimeError("All possible pairs have been asked")
