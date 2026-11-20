"""
The liquid walkthrough's static data (public/data/liquid-story/).

- measures.json is a fresh build of the committed benchmark summaries, and
  the manifest pins every input and output, city.json included.
- city.json keeps its invariants, and recomputing Swiss turnout with the
  frozen code reproduces that level and the mechanism byte for byte.
- Where the frozen benchmark's city records are present, the city's totals
  equal the recorded city's at every level.
"""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / "public" / "data" / "liquid-story"
FRONTIER = ROOT / "eval" / "benchmarks" / "delegation_frontier_v1"
CODES = set("MNmcn")


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def story() -> ModuleType:
    return _load("build_liquid_story")


@pytest.fixture(scope="module")
def builder() -> ModuleType:
    return _load("build_liquid_example_city")


@pytest.fixture(scope="module")
def city() -> dict[str, Any]:
    value: dict[str, Any] = json.loads((ARTIFACTS / "city.json").read_text(encoding="utf-8"))
    return value


@pytest.fixture(scope="module")
def results() -> dict[str, Any]:
    value: dict[str, Any] = json.loads((ARTIFACTS / "results.json").read_text(encoding="utf-8"))
    return value


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class TestStoryBuild:
    def test_the_build_is_deterministic(self, story: ModuleType) -> None:
        first = {n: story.dumps(p) for n, p in story.build_artifacts().items()}
        assert first == {n: story.dumps(p) for n, p in story.build_artifacts().items()}

    def test_committed_outputs_are_current(self, story: ModuleType) -> None:
        outputs = {n: story.dumps(p).encode("utf-8") for n, p in story.build_artifacts().items()}
        for name, body in outputs.items():
            assert (ARTIFACTS / name).read_bytes() == body, f"{name} is stale; run scripts/build_liquid_story.py"
        committed = (ARTIFACTS / "manifest.json").read_bytes()
        assert committed == story.dumps(story.manifest(outputs)).encode("utf-8"), "manifest.json is stale"

    def test_the_manifest_pins_every_file(self, story: ModuleType) -> None:
        manifest = json.loads((ARTIFACTS / "manifest.json").read_text(encoding="utf-8"))
        for path, digest in manifest["inputs"].items():
            assert sha256(ROOT / path) == digest, path
        for name, digest in {**manifest["outputs"], **manifest["city"]}.items():
            assert sha256(ARTIFACTS / name) == digest, name

    def test_measures_are_the_frozen_summaries(self) -> None:
        measures = json.loads((ARTIFACTS / "measures.json").read_text(encoding="utf-8"))
        with (FRONTIER / "measures.csv").open(encoding="utf-8", newline="") as handle:
            rows = [r for r in csv.DictReader(handle) if r["point"] == "primary: primary settings"]
        for row in rows:
            at = measures["levels"].get(row["level"], {}).get(row["arrangement"])
            if at is None:
                continue
            for field in ("fidelity", "contrary_share", "none_share", "overhead"):
                assert at[field] == float(row[field]), (row["level"], row["arrangement"], field)
        assert measures["verdict"]["text"] == "overhead condition not met where liquid is ahead"
        assert measures["verdict"]["gate_holds"] is False


class TestResults:
    def test_the_ladder_adds_up_to_the_lead_at_every_level(self, results: dict[str, Any]) -> None:
        for level, values in results["levels"].items():
            d = {k: v["estimate"] for k, v in values["decomposition"].items()}
            steps = (
                d["cost_of_sharing"]
                + d["choice_by_non_voters"]
                + d["city_wide_proxy_combined"]
                + d["specialisation"]
                - d["platform_against_record"]
            )
            assert steps == pytest.approx(d["h1"], abs=5e-6), level
            assert d["h1"] == values["h1"]["estimate"], level

    def test_the_result_is_the_frozen_reading(self, results: dict[str, Any]) -> None:
        with (FRONTIER / "levels.csv").open(encoding="utf-8", newline="") as handle:
            rows = {r["level"]: r for r in csv.DictReader(handle) if r["point"] == "primary: primary settings"}
        for level, values in results["levels"].items():
            row = rows[level]
            assert values["cap_share"] == float(row["cap_share"])
            assert values["h1"]["estimate"] == float(row["h1_all_estimate"])
            assert values["band"]["lower"] == float(row["band_all_lower"])
            assert (values["direction"], values["size"]) == (row["h1_direction"], row["h1_size"])
        assert results["threshold"]["confidence"] == [0.1, 0.3]
        assert results["threshold"]["gate_holds"] is False
        failing = [lv for lv, v in results["levels"].items()
                   if v["h1"]["estimate"] > 0 and v["cap_share"] < results["rules"]["feasible_share"]]
        assert failing == ["0.2", "0.9"]


class TestCity:
    def test_every_level_holds_every_resident(self, city: dict[str, Any]) -> None:
        residents = city["design"]["residents"]
        pairs = residents * city["design"]["topics"] * city["design"]["evaluation_per_topic"]
        grid = json.loads((ARTIFACTS / "measures.json").read_text(encoding="utf-8"))["protocol"]["turnout_grid"]
        assert list(city["levels"]) == [repr(level) for level in grid]
        assert sorted(city["order"]) == list(range(residents))
        for level, values in city["levels"].items():
            for name, codes in values["codes"].items():
                assert len(codes) == residents and set(codes) <= CODES, (level, name)
            assert set(values["codes"]["full_turnout"]) == {"M"}
            # Direct voting is always the resident's own ballot
            assert set(values["codes"]["direct"]) <= {"M", "N"}
            # Under liquid, a ballot is someone else's exactly when it was delegated
            reasons, liquid = values["liquid_reason"], values["codes"]["liquid"]
            assert len(reasons) == residents and set(reasons) <= set("dlek"), level
            assert all((r == "d") == (c in "mcn") for r, c in zip(reasons, liquid, strict=True)), level
            for name, totals in values["totals"].items():
                assert totals["match"] + totals["contrary"] + totals["none"] == pairs, (level, name)
                assert totals["fidelity"] == pytest.approx(totals["match"] / pairs, abs=1e-12)
        # Turnout draws are shared, so raising turnout only ever adds a
        # resident's own ballot under direct voting, never removes one
        levels = list(city["levels"].values())
        for low, high in zip(levels, levels[1:], strict=False):
            pairs_of = zip(low["codes"]["direct"], high["codes"]["direct"], strict=True)
            assert not any(a == "M" and b == "N" for a, b in pairs_of)

    def test_the_mechanism_tells_the_truth(self, city: dict[str, Any]) -> None:
        m = city["mechanism"]
        showcase = m["showcase"]
        top = showcase["candidates"][0]
        assert showcase["delegates"][showcase["topic"]] == top["person"]
        assert top["lower"] >= m["acceptance"]
        assert [c["lower"] for c in showcase["candidates"]] == sorted(
            (c["lower"] for c in showcase["candidates"]), reverse=True
        )
        assert m["short_record"]["candidates"][0]["lower"] < m["acceptance"]
        assert sum(m["handed_over"]) == city["design"]["residents"]
        # The calibrated level is the highest whose overhead stays under the cap
        curve = sorted(m["calibration"], key=lambda p: p["acceptance"])
        chosen = next(p for p in curve if p["acceptance"] == m["acceptance"])
        assert chosen["overhead"] <= m["cap"] + 1e-9
        assert all(p["overhead"] > m["cap"] for p in curve if p["acceptance"] > m["acceptance"])
        chain = m["chain"]
        if chain["ends"] == "loop":
            assert chain["cycle"][0] == chain["path"][-1] and len(chain["cycle"]) >= 2
        assert m["handed_pairs_ending_on_loop"] <= m["handed_pairs"]
        typical = m["typical"]
        assert set(typical["strips"]["liquid"]) <= CODES
        assert len(typical["questions"]) == len(typical["strips"]["direct"])

    def test_swiss_turnout_recomputes_byte_for_byte(self, builder: ModuleType, city: dict[str, Any]) -> None:
        population, result = builder._level(0.45)
        question = builder._feature(population, result)
        assert question == city["question"]["index"]
        level = city["levels"]["0.45"]
        for name in builder.ARRANGEMENTS:
            assert builder._codes(population, result, name, question) == level["codes"][name], name
            assert builder._totals(population, result, name) == level["totals"][name], name
        assert builder._reasons(population, result, question) == level["liquid_reason"]
        mechanism = json.loads(builder.dumps(builder._mechanism(population, result, question)))
        assert mechanism == city["mechanism"]

    @pytest.mark.skipif(not (FRONTIER / "primary_cities.jsonl.gz").exists(), reason="the city records are kept local")
    def test_the_city_is_the_recorded_city(self, builder: ModuleType, city: dict[str, Any]) -> None:
        assert builder.check_recorded(city) is True
