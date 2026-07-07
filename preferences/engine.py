"""
Elicitation engine: orchestrates the model, question bank, and session flow.

The engine builds questions from the bank, converts user answers into typed
`Evidence`, applies it through the model, and picks the next question via a
pluggable acquisition policy (default: max-variance uncertainty sampling).
"""

import datetime as dt
import random
from dataclasses import dataclass
from typing import Optional

from .acquisition import DEFAULT_SELECTOR_NAME, PairSelector, create_selector
from .model import (
    DEFAULT_MODEL_NAME,
    PreferenceModel,
    create_model,
    model_for_version,
)
from .questions.bank import QuestionBank
from .types import (
    Evidence,
    PreferenceState,
    Question,
    SessionProgress,
    ValueEstimate,
)


@dataclass
class EngineConfig:
    target_questions: int = 25
    seed: Optional[int] = None
    selection_policy: str = DEFAULT_SELECTOR_NAME


class ElicitationEngine:
    """Orchestrates preference elicitation for a single user session."""

    def __init__(
        self,
        model: Optional[PreferenceModel] = None,
        question_bank: Optional[QuestionBank] = None,
        config: Optional[EngineConfig] = None,
        selector: Optional[PairSelector] = None,
    ):
        self.model = model or create_model(DEFAULT_MODEL_NAME)
        self.bank = question_bank or QuestionBank.load_default()
        self.config = config or EngineConfig()
        self.selector = selector or create_selector(self.config.selection_policy)
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

    def submit_evidence(
        self,
        state: PreferenceState,
        evidence: Evidence,
    ) -> tuple[PreferenceState, Optional[Question]]:
        """Apply one piece of evidence and return the next question (or None)."""
        # A state must be resumed by the model family that produced it —
        # mu/sigma have model-specific semantics (legacy version strings map
        # to their renamed successors via model_for_version).
        owner = model_for_version(state.model_version)
        if type(owner) is not type(self.model):
            raise ValueError(
                f"State was produced by '{state.model_version}' but the "
                f"engine is running '{self.model.model_version}'"
            )
        if evidence.timestamp is None:
            evidence.timestamp = (
                dt.datetime.now(dt.timezone.utc)
                .isoformat()
                .replace("+00:00", "Z")
            )
        new_state = self.model.update(state, evidence)
        if new_state.n_questions_asked >= self.config.target_questions:
            return new_state, None
        next_q = self._select_next_question(new_state)
        return new_state, next_q

    # ------------------------------------------------------------------
    # Question selection
    # ------------------------------------------------------------------

    def _select_next_question(self, state: PreferenceState) -> Optional[Question]:
        """Ask the acquisition policy for a pair, avoiding already-asked pairs."""
        pair = self.selector.select_pair(
            state=state,
            model=self.model,
            bank=self.bank,
            exclude_pairs=self._seen_pairs(state),
            rng=self._rng,
        )
        if pair is None:
            return None
        a_id, b_id = pair
        qid = f"q{state.n_questions_asked + 1}_{a_id}_vs_{b_id}"
        return self.bank.build_pairwise_question(a_id, b_id, question_id=qid)

    @staticmethod
    def _seen_pairs(state: PreferenceState) -> set[frozenset[str]]:
        """Item pairs already covered by the state's evidence trail."""
        return {
            frozenset((ev.item_a, ev.item_b))
            for ev in state.evidence
            if ev.item_a != ev.item_b
        }

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
