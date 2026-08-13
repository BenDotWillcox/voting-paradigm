"""Tests for PreferenceState serialization, including legacy upgrades."""

import json

from preferences.model.gaussian_linear import GaussianLinearUtilityModel
from preferences.serialization import state_from_dict, state_to_dict
from preferences.types import Evidence, EvidenceSource

ITEMS = ["freedom", "security", "equality"]


def make_state():
    model = GaussianLinearUtilityModel()
    state = model.initialize("u1", "s1", ITEMS)
    ev = Evidence(
        source=EvidenceSource.PAIRWISE,
        item_a="freedom",
        item_b="security",
        value=7.5,
        prompt_id="q1_freedom_vs_security",
        response_time_ms=1200,
    )
    return model.update(state, ev)


class TestRoundtrip:
    def test_state_roundtrips_through_json(self):
        state = make_state()
        data = json.loads(json.dumps(state_to_dict(state)))
        restored = state_from_dict(data)
        assert restored.mu == state.mu
        assert restored.sigma_flat == state.sigma_flat
        assert restored.item_ids == state.item_ids
        assert restored.model_version == state.model_version
        assert len(restored.evidence) == 1
        ev = restored.evidence[0]
        assert ev.source is EvidenceSource.PAIRWISE
        assert ev.item_a == "freedom"
        assert ev.value == 7.5

    def test_source_serialized_as_string(self):
        data = state_to_dict(make_state())
        assert data["evidence"][0]["source"] == "pairwise"

    def test_typed_confirmation_and_event_id_round_trip(self):
        state = make_state()
        state.evidence[0].event_id = "evidence_one"
        state.evidence[0].confirmed_by_participant = True

        restored = state_from_dict(state_to_dict(state))

        assert restored.evidence[0].event_id == "evidence_one"
        assert restored.evidence[0].confirmed_by_participant is True


class TestLegacyUpgrade:
    def legacy_dict(self):
        return {
            "user_id": "u1",
            "session_id": "s1",
            "item_ids": ITEMS,
            "mu": [0.3, -0.3, 0.0],
            "sigma_flat": [1.0, 0.0, 1.0, 0.0, 0.0, 1.0],
            "responses": [
                {
                    "question_id": "q1_freedom_vs_security",
                    "chosen_option_id": "freedom",
                    "strength": 8.0,
                    "response_time_ms": 900,
                    "timestamp": "2026-01-01T00:00:00Z",
                }
            ],
            "n_questions_asked": 1,
            "asked_question_ids": ["q1_freedom_vs_security"],
            "model_version": "thurstone_v1",
        }

    def test_model_version_upgraded(self):
        state = state_from_dict(self.legacy_dict())
        assert state.model_version == "gaussian_linear_v1"

    def test_responses_converted_to_evidence(self):
        state = state_from_dict(self.legacy_dict())
        assert len(state.evidence) == 1
        ev = state.evidence[0]
        assert ev.source is EvidenceSource.PAIRWISE
        assert ev.item_a == "freedom"
        assert ev.item_b == "security"
        assert ev.value == 8.0  # chose item_a with strength 8
        assert ev.prompt_id == "q1_freedom_vs_security"

    def test_chose_b_gives_negative_value(self):
        data = self.legacy_dict()
        data["responses"][0]["chosen_option_id"] = "security"
        state = state_from_dict(data)
        assert state.evidence[0].value == -8.0

    def test_unparseable_question_id_dropped(self):
        data = self.legacy_dict()
        data["responses"][0]["question_id"] = "weird-id"
        state = state_from_dict(data)
        assert state.evidence == []
        # Posterior untouched by the drop.
        assert state.mu == [0.3, -0.3, 0.0]

    def test_upgraded_state_accepts_new_updates(self):
        state = state_from_dict(self.legacy_dict())
        model = GaussianLinearUtilityModel()
        ev = Evidence(
            source=EvidenceSource.PAIRWISE,
            item_a="equality",
            item_b="security",
            value=5.0,
        )
        new_state = model.update(state, ev)
        assert new_state.n_questions_asked == 2
