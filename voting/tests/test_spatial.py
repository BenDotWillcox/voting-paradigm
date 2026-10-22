"""Tests for spatial electorates and the atlas."""

import math

import numpy as np
import pytest

from voting.ballot_models import UTILITY_SCALE
from voting.spatial import (
    DEFAULT_CLOUD,
    InvalidLayoutError,
    cell_center,
    cloud_distances,
    cloud_utilities,
    compute_atlas,
    electorate_at,
    sunflower_cloud,
)

ABC = ("A", "B", "C")
# Far apart, so a cloud on top of one candidate is all its own
SPREAD_OUT = [(0.5, 0.27), (0.27, 0.68), (0.73, 0.68)]
HUB = (("A", "B", "C", "D"), [(0.5, 0.26), (0.27, 0.66), (0.73, 0.66), (0.5, 0.53)])


class TestCloud:
    def test_default_cloud_is_nineteen_types_of_five(self):
        assert len(DEFAULT_CLOUD.offsets) == 19
        assert DEFAULT_CLOUD.total_voters == 95

    def test_no_two_types_share_a_coordinate(self):
        """A lattice's shared columns would stripe the maps."""
        xs = [round(x, 9) for x, _ in DEFAULT_CLOUD.offsets]
        ys = [round(y, 9) for _, y in DEFAULT_CLOUD.offsets]

        assert len(set(xs)) == len(xs)
        assert len(set(ys)) == len(ys)

    def test_radii_follow_gaussian_quantiles(self):
        cloud = sunflower_cloud(types=4, spread=1.0)
        radii = [math.hypot(x, y) for x, y in cloud.offsets]

        for i, radius in enumerate(radii):
            mass_inside = 1 - math.exp(-radius * radius / 2)
            assert mass_inside == pytest.approx((i + 0.5) / 4)

    def test_rejects_an_empty_cloud(self):
        with pytest.raises(InvalidLayoutError):
            sunflower_cloud(types=0)


class TestUtilities:
    def test_nearest_is_the_top_and_farthest_the_bottom(self):
        distances = np.array([[0.1, 0.3, 0.5]])

        assert cloud_utilities(distances).tolist() == [[100, 50, 0]]

    def test_rounds_half_up(self):
        # The middle candidate sits 3/8 of the way: 62.5 rounds to 63
        distances = np.array([[0.0, 0.3, 0.8]])

        assert cloud_utilities(distances).tolist() == [[100, 63, 0]]

    def test_a_voter_equally_far_from_everyone_is_indifferent(self):
        distances = np.array([[0.4, 0.4, 0.4]])

        assert cloud_utilities(distances).tolist() == [[UTILITY_SCALE // 2] * 3]

    def test_electorate_is_the_cloud_in_order(self):
        profile = electorate_at((0.5, 0.5), ABC, SPREAD_OUT, DEFAULT_CLOUD)

        assert profile.candidates == ABC
        assert [count for count, _ in profile.rows] == [5] * 19
        distances = cloud_distances(np.array([[0.5, 0.5]]), SPREAD_OUT, DEFAULT_CLOUD)
        assert [list(row) for _, row in profile.rows] == cloud_utilities(distances)[0].tolist()

    @pytest.mark.parametrize(
        "candidates, positions",
        [
            (("A",), [(0.5, 0.5)]),
            (("A", "A"), [(0.2, 0.5), (0.8, 0.5)]),
            (("A", "B"), [(0.2, 0.5)]),
            (("A", "B"), [(0.2, 0.5), (math.nan, 0.5)]),
        ],
        ids=["one-candidate", "repeated", "missing-position", "nan"],
    )
    def test_invalid_layouts(self, candidates, positions):
        with pytest.raises(InvalidLayoutError):
            electorate_at((0.5, 0.5), candidates, positions, DEFAULT_CLOUD)


@pytest.fixture(scope="module")
def hub():
    return compute_atlas(*HUB, size=16)


class TestAtlas:
    def test_every_map_covers_the_grid(self, hub):
        cells = 16 * 16

        assert set(hub.maps) == {
            "plurality", "irv", "borda", "ranked_pairs", "approval", "score", "quadratic",
        }
        for map_ in hub.maps.values():
            assert len(map_.winners) == len(map_.decisive) == cells
        assert len(hub.condorcet) == len(hub.utilitarian) == len(hub.disagreement) == cells

    def test_ranked_pairs_elects_every_condorcet_winner(self, hub):
        """Ranked Pairs is Condorcet-consistent; the two maps must agree."""
        rp = hub.maps["ranked_pairs"].winners

        for cell, winner in enumerate(hub.condorcet):
            if winner >= 0:
                assert rp[cell] == winner

    def test_disagreement_counts_distinct_winners(self, hub):
        for cell, count in enumerate(hub.disagreement):
            assert count == len({m.winners[cell] for m in hub.maps.values()})

    def test_utilitarian_is_the_least_total_distance(self, hub):
        centers = np.array([cell_center(c, 16) for c in range(16 * 16)])
        totals = cloud_distances(centers, HUB[1], DEFAULT_CLOUD).sum(axis=1)

        assert list(hub.utilitarian) == totals.argmin(axis=1).tolist()

    def test_a_cloud_on_a_lone_candidate_elects_it_everywhere(self):
        atlas = compute_atlas(ABC, SPREAD_OUT, size=10)
        # Cell (2, 5) is centered at (0.55, 0.25), beside A at (0.5, 0.27)
        cell = 2 * 10 + 5

        for map_ in atlas.maps.values():
            assert map_.winners[cell] == 0
            assert map_.decisive[cell]
        assert atlas.condorcet[cell] == atlas.utilitarian[cell] == 0

    def test_records_its_inputs(self, hub):
        assert hub.candidates == HUB[0]
        assert hub.ballot_model == "sincere-v1"
        assert hub.tiebreak_seed == 0
        assert hub.cloud == DEFAULT_CLOUD

    def test_cell_centers_are_row_major_from_the_top_left(self):
        assert cell_center(0, 4) == (0.125, 0.125)
        assert cell_center(5, 4) == (0.375, 0.375)
        assert cell_center(15, 4) == (0.875, 0.875)

    SCRIPT = (
        "from voting.spatial import compute_atlas\n"
        "a = compute_atlas(('A', 'B', 'C', 'D'), "
        "[(0.5, 0.26), (0.27, 0.66), (0.73, 0.66), (0.5, 0.53)], size=12)\n"
        "print(sorted((m, x.winners, x.decisive) for m, x in a.maps.items()), a.condorcet)\n"
    )

    def test_same_maps_under_any_hash_seed(self):
        import os
        import subprocess
        import sys
        from pathlib import Path

        root = Path(__file__).resolve().parents[2]
        outputs = set()
        for seed in ("0", "1", "2", "3"):
            env = {**os.environ, "PYTHONHASHSEED": seed, "PYTHONPATH": str(root)}
            completed = subprocess.run(
                [sys.executable, "-c", self.SCRIPT],
                capture_output=True,
                text=True,
                env=env,
                cwd=root,
                check=True,
            )
            outputs.add(completed.stdout)

        assert len(outputs) == 1
