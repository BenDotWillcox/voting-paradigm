from expressive.home_card import ARTIFACT, MAX_IDEAL, SAMPLE_SIZE, home_card_payload, render


def test_committed_artifact_matches_fixture() -> None:
    assert ARTIFACT.read_text(encoding="utf-8") == render(), (
        "lib/expressive-home-card.json is stale; run `python -m expressive.home_card`."
    )


def test_sample_is_ordered_distinct_and_in_view() -> None:
    voters = home_card_payload()["voters"]
    assert len(voters) == SAMPLE_SIZE
    assert len({v["id"] for v in voters}) == SAMPLE_SIZE
    ideals = [v["ideal"] for v in voters]
    assert ideals == sorted(ideals)
    assert all(ideal <= MAX_IDEAL for ideal in ideals)
    assert {v["binary_vote"] for v in voters} >= {"yes", "no"}
