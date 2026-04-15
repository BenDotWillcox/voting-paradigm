"""
Elicitation engine: orchestrates the model, question bank, and session flow.

v1 picks the next question at random from the bank. Future versions will plug
in an acquisition function and an LLM question generator.
"""

import datetime as dt
import random
from dataclasses import dataclass
from typing import Optional

from .model.thurstone import ThurstonePairwiseModel
from .questions.bank import QuestionBank
from .types import (
    PreferenceState,
    Question,
    Response,
    SessionProgress,
    ValueEstimate,
)


@dataclass
class EngineConfig:
    target_questions: int = 25
    seed: Optional[int] = None


class ElicitationEngine:
    """Orchestrates preference elicitation for a single user session."""

    def __init__(
        self,
        model: Optional[ThurstonePairwiseModel] = None,
        question_bank: Optional[QuestionBank] = None,
        config: Optional[EngineConfig] = None,
    ):
        self.model = model or ThurstonePairwiseModel()
        self.bank = question_bank or QuestionBank.load_default()
        self.config = config or EngineConfig()
        self._rng = random.Random(self.config.seed)

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    def start_session(
        self,
        user_id: str,
        session_id: str,
    ) -> tuple[PreferenceState, Question]:
        """Create a fresh state and pick the first question."""
        state = self.model.initialize(
            user_id=user_id,
            session_id=session_id,
            item_ids=self.bank.item_ids(),
        )
        question = self._select_next_question(state)
        if question is None:
            raise RuntimeError("Could not generate initial question")
        return state, question

    def submit_response(
        self,
        state: PreferenceState,
        response: Response,
        question_options: list[str],
    ) -> tuple[PreferenceState, Optional[Question]]:
        """Update the model with a response and return the next question (or None)."""
        if response.timestamp is None:
            response.timestamp = dt.datetime.utcnow().isoformat() + "Z"
        new_state = self.model.update(state, response, question_options)
        if new_state.n_questions_asked >= self.config.target_questions:
            return new_state, None
        next_q = self._select_next_question(new_state)
        return new_state, next_q

    # ------------------------------------------------------------------
    # Question selection (v1: random from bank)
    # ------------------------------------------------------------------

    def _select_next_question(self, state: PreferenceState) -> Optional[Question]:
        """Pick the next question. v1 = random, avoiding already-asked pairs."""
        seen_pairs = self._seen_pairs(state)
        try:
            a_id, b_id = self.bank.random_pair(
                exclude_pairs=seen_pairs,
                rng=self._rng,
            )
        except RuntimeError:
            return None
        qid = f"q{state.n_questions_asked + 1}_{a_id}_vs_{b_id}"
        return self.bank.build_pairwise_question(a_id, b_id, question_id=qid)

    @staticmethod
    def _seen_pairs(state: PreferenceState) -> set[frozenset[str]]:
        """Reconstruct the set of (item_a, item_b) pairs already asked."""
        # Question IDs follow "q{n}_{a}_vs_{b}" — parse items out. For robustness
        # in case IDs change, also look at responses where possible.
        pairs: set[frozenset[str]] = set()
        for qid in state.asked_question_ids:
            # Split off the "q{n}_" prefix and then "_vs_" delimiter
            try:
                rest = qid.split("_", 1)[1]  # "{a}_vs_{b}"
                a, b = rest.split("_vs_")
                pairs.add(frozenset((a, b)))
            except (IndexError, ValueError):
                continue
        return pairs

    # ------------------------------------------------------------------
    # Summary / reporting
    # ------------------------------------------------------------------

    def get_progress(self, state: PreferenceState) -> SessionProgress:
        target = self.config.target_questions
        n = state.n_questions_asked
        # Convergence proxy: fraction of target questions answered.
        # Later versions can use posterior entropy reduction.
        convergence_pct = min(100.0, 100.0 * n / max(target, 1))
        return SessionProgress(
            n_answered=n,
            target_questions=target,
            convergence_pct=convergence_pct,
            is_complete=n >= target,
        )

    def get_value_estimates(
        self, state: PreferenceState
    ) -> list[ValueEstimate]:
        """Return all items ranked by posterior mean utility (descending)."""
        estimates = self.model.get_utility_estimates(state)
        # Sort by mean descending
        sorted_items = sorted(
            estimates.items(), key=lambda kv: kv[1][0], reverse=True
        )
        return [
            ValueEstimate(item_id=iid, mean=mean, std=std, rank=rank)
            for rank, (iid, (mean, std)) in enumerate(sorted_items)
        ]

    def get_summary(self, state: PreferenceState) -> dict:
        """Structured summary for the UI."""
        estimates = self.get_value_estimates(state)
        progress = self.get_progress(state)
        # Enrich with item metadata from the bank
        enriched = []
        for est in estimates:
            try:
                item = self.bank.get(est.item_id)
                enriched.append(
                    {
                        "item_id": est.item_id,
                        "text": item.text,
                        "description": item.description,
                        "domain": item.domain,
                        "mean": est.mean,
                        "std": est.std,
                        "rank": est.rank,
                    }
                )
            except KeyError:
                enriched.append(
                    {
                        "item_id": est.item_id,
                        "text": est.item_id,
                        "description": "",
                        "domain": None,
                        "mean": est.mean,
                        "std": est.std,
                        "rank": est.rank,
                    }
                )
        return {
            "progress": {
                "n_answered": progress.n_answered,
                "target_questions": progress.target_questions,
                "convergence_pct": progress.convergence_pct,
                "is_complete": progress.is_complete,
            },
            "values": enriched,
            "model_version": state.model_version,
        }
