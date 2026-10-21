"""Tests for the seeded default tiebreak."""

from voting import (
    Candidate,
    create_single_choice_ballot,
    random_tiebreak,
    resolve_plurality,
)


def test_same_seed_gives_same_sequence():
    first = random_tiebreak(7)
    second = random_tiebreak(7)
    tied = ["a", "b", "c", "d"]

    assert [first(tied) for _ in range(20)] == [second(tied) for _ in range(20)]


def test_different_seeds_can_differ():
    tied = ["a", "b", "c", "d"]
    sequences = {
        tuple(tiebreak(tied) for _ in range(20))
        for tiebreak in (random_tiebreak(seed) for seed in range(5))
    }

    assert len(sequences) > 1


def test_pick_ignores_input_order():
    first = random_tiebreak(3)
    second = random_tiebreak(3)

    picks_sorted = [first(["a", "b", "c"]) for _ in range(20)]
    picks_shuffled = [second(["c", "a", "b"]) for _ in range(20)]

    assert picks_sorted == picks_shuffled


def test_pick_is_one_of_the_tied():
    tiebreak = random_tiebreak()

    assert all(tiebreak(["x", "y"]) in {"x", "y"} for _ in range(20))


def test_methods_default_to_a_reproducible_tiebreak():
    """A tie resolved without an explicit tiebreak is the same every time."""
    candidates = [Candidate(id="alice", name="Alice"), Candidate(id="bob", name="Bob")]
    ballots = [
        create_single_choice_ballot("v1", "alice"),
        create_single_choice_ballot("v2", "bob"),
    ]

    winners = {tuple(resolve_plurality(candidates, ballots).winners) for _ in range(30)}

    assert len(winners) == 1
