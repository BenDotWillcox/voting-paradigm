"""
The liquid walkthrough's static data (public/data/liquid-story/).

- measures.json is a fresh build of the committed benchmark summaries, and
  the manifest pins every input and output, city.json included.
- city.json keeps its invariants, and recomputing Swiss turnout with the
  frozen code reproduces that level and the mechanism byte for byte.
- Where the frozen benchmark's city records are present, the city's totals
  equal the recorded city's at every level.
- The everyone-votes reference point (exploratory) is its benchmark's
  summaries, and the city's everyone-votes setting recomputes byte for byte
  and, where that benchmark's city records are present, equals its record.
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
EVERYONE = ROOT / "eval" / "benchmarks" / "delegation_everyone_votes_v1"
FALLBACK = ROOT / "eval" / "benchmarks" / "delegation_fallback_v1"
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


@pytest.fixture(scope="module")
def exploratory() -> dict[str, Any]:
    return dict(json.loads((ARTIFACTS / "exploratory.json").read_text(encoding="utf-8")))


@pytest.fixture(scope="module")
def frozen() -> dict[str, Any]:
    return dict(json.loads((ARTIFACTS / "measures.json").read_text(encoding="utf-8"))["levels"])


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


class TestSweepsAndRouter:
    def test_the_panels_draw_every_declared_sweep_point_once(self, results: dict[str, Any]) -> None:
        sweeps = results["sweeps"]
        drawn = [s["point"] for panel in sweeps["panels"] for s in panel["series"]]
        declared = set(sweeps["points"]) - {sweeps["reference"]}
        assert set(drawn) - {sweeps["reference"]} == declared
        # The shared baseline appears once per panel that compares with it
        assert len(drawn) - drawn.count(sweeps["reference"]) == len(declared)
        assert all(p["levels"].keys() == results["levels"].keys() for p in sweeps["points"].values())

    def test_the_router_is_the_router_benchmark(self, results: dict[str, Any]) -> None:
        summary = json.loads(
            (ROOT / "eval" / "benchmarks" / "delegation_router_v1" / "summary.json").read_text(encoding="utf-8")
        )
        router = results["router"]
        assert router["model"] == summary["model"]
        for field, value in router["operating"].items():
            assert summary["router_at_operating_threshold"][field] == value, field
        assert [r["threshold"] for r in router["by_threshold"]] == [
            r["threshold"] for r in summary["router_by_threshold"]
        ]


class TestExploratory:
    def test_depth_zero_is_frozen_direct_voting(self, exploratory: dict[str, Any], frozen: dict[str, Any]) -> None:
        for level, points in exploratory["handover"]["levels"].items():
            assert [p["depth"] for p in points] == list(range(9))
            for field in ("fidelity", "overhead"):
                assert points[0][field] == pytest.approx(frozen[level]["direct"][field], abs=2e-6), (level, field)

    def test_the_wrong_ballot_scores_are_match_minus_w_contrary(self, exploratory: dict[str, Any]) -> None:
        for level, rows in exploratory["wrong_ballot"]["levels"].items():
            for name, r in rows.items():
                assert r["w0"] == pytest.approx(r["match"], abs=2e-6), (level, name)
                assert r["w1"] == pytest.approx(r["match"] - r["contrary"], abs=2e-6), (level, name)

    def test_the_agent_bars_come_from_the_frozen_shares(self, exploratory: dict[str, Any], frozen: dict[str, Any]) -> None:
        for level, bars in exploratory["agent_bars"]["levels"].items():
            rep, liquid = frozen[level]["representative"], frozen[level]["liquid"]
            assert bars["representative"] == pytest.approx(rep["fidelity"] / (1 - rep["none_share"]))
            cast = 1 - liquid["lost_share"] / liquid["delegated_share"]
            assert bars["delegate"] == pytest.approx(liquid["fidelity_resolved"] / cast)
        swiss = exploratory["agent_bars"]["levels"]["0.45"]
        assert (round(swiss["representative"], 3), round(swiss["delegate"], 3)) == (0.632, 0.747)

    def test_everyone_votes_is_its_benchmark(self, exploratory: dict[str, Any]) -> None:
        everyone = exploratory["everyone_votes"]
        with (EVERYONE / "measures.csv").open(encoding="utf-8", newline="") as handle:
            rows = {r["arrangement"]: r for r in csv.DictReader(handle)}
        for name, values in everyone["measures"].items():
            for field in ("fidelity", "contrary_share", "none_share", "overhead", "fidelity_lower"):
                assert values[field] == float(rows[name][field]), (name, field)
            # Everyone votes, so no ballot is missing under any arrangement
            assert values["none_share"] == 0.0, name
        assert everyone["measures"]["direct"]["fidelity"] == everyone["measures"]["direct"]["overhead"] == 1.0
        assert exploratory["label"] == "exploratory"
        assert everyone["setting"] == "everyone votes"

    def test_the_fallback_block_is_its_benchmark(self, exploratory: dict[str, Any]) -> None:
        fallback = exploratory["fallback"]
        hypothesis = json.loads((FALLBACK / "hypothesis.json").read_text(encoding="utf-8"))
        assert fallback["outcome"] == hypothesis["outcome"] == "supported"
        assert fallback["hypothesis_levels"] == [0.1, 0.2, 0.3]
        with (FALLBACK / "levels.csv").open(encoding="utf-8", newline="") as handle:
            levels = {r["level"]: r for r in csv.DictReader(handle)}
        with (FALLBACK / "measures.csv").open(encoding="utf-8", newline="") as handle:
            measures = {(r["level"], r["arrangement"]): r for r in csv.DictReader(handle)}
        for level, values in fallback["levels"].items():
            assert values["h1"]["estimate"] == float(levels[level]["h1_estimate"]), level
            assert values["cap_share"] == float(levels[level]["cap_share"]), level
            assert values["default_gain"]["lower"] == float(levels[level]["default_gain_lower"]), level
            for field, value in values["liquid_default"].items():
                assert value == float(measures[(level, "liquid_default")][field]), (level, field)

    def test_everyone_votes_ladder_adds_up_to_its_lead(self, exploratory: dict[str, Any]) -> None:
        everyone = exploratory["everyone_votes"]
        d = {k: v["estimate"] for k, v in everyone["contrasts"].items()}
        steps = (
            d["cost_of_sharing"]
            + d["choice_by_non_voters"]
            + d["city_wide_proxy_combined"]
            + d["specialisation"]
            - d["platform_against_record"]
        )
        assert steps == pytest.approx(d["h1"], abs=5e-6)
        lead = everyone["measures"]["liquid"]["fidelity"] - everyone["measures"]["representative"]["fidelity"]
        assert d["h1"] == pytest.approx(lead, abs=2e-6)


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
            questions = city["design"]["topics"] * city["design"]["evaluation_per_topic"]
            for name, winners in values["winners"].items():
                assert len(winners) == questions and set(winners) <= {"y", "n"}, (level, name)
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
        # The lost vote: its path ends at whoever did not vote, and the backup
        # is someone other than the voter and their chosen delegate
        lost = m["lost"]
        assert lost["path"][0] == lost["voter"] and lost["path"][-1] == lost["resolver"]
        assert lost["backup"] not in (lost["voter"], lost["path"][1])
        assert set(lost["catch"]) == {"you", "backup", "representative"}
        assert set(lost["catch"].values()) <= {"m", "c", "n"}
        assert city["levels"]["0.45"]["codes"]["liquid"][lost["voter"]] == "n"

    def test_swiss_turnout_recomputes_byte_for_byte(self, builder: ModuleType, city: dict[str, Any]) -> None:
        population, result = builder._level(0.45)
        question = builder._feature(population, result)
        assert question == city["question"]["index"]
        level = city["levels"]["0.45"]
        for name in builder.ARRANGEMENTS:
            assert builder._codes(population, result, name, question) == level["codes"][name], name
            assert builder._totals(population, result, name) == level["totals"][name], name
        assert builder._reasons(population, result, question) == level["liquid_reason"]
        for name in builder.ARRANGEMENTS:
            assert builder._winners(result, name) == level["winners"][name], name
        mechanism = json.loads(builder.dumps(builder._mechanism(population, result, question)))
        assert mechanism == city["mechanism"]

    @pytest.mark.skipif(not (FRONTIER / "primary_cities.jsonl.gz").exists(), reason="the city records are kept local")
    def test_the_city_is_the_recorded_city(self, builder: ModuleType, city: dict[str, Any]) -> None:
        assert builder.check_recorded(city) is True

    def test_with_everyone_voting_no_ballot_is_missing(self, city: dict[str, Any]) -> None:
        everyone = city["everyone"]
        assert everyone["label"] == "exploratory"
        for name, codes in everyone["codes"].items():
            assert len(codes) == city["design"]["residents"] and not set(codes) & {"N", "n"}, name
            assert everyone["totals"][name]["none"] == 0, name
        assert set(everyone["codes"]["direct"]) == {"M"}
        # Everyone has a full record, so no one keeps a topic for want of one
        assert "e" not in everyone["liquid_reason"]
        questions = city["design"]["topics"] * city["design"]["evaluation_per_topic"]
        for name, strip in everyone["typical_strips"].items():
            assert len(strip) == questions and not set(strip) & {"N", "n"}, name
        assert set(everyone["typical_strips"]["direct"]) == {"M"}

    def test_everyone_votes_delegations_give_the_deciders(self, city: dict[str, Any]) -> None:
        everyone = city["everyone"]
        typical = everyone["typical"]
        assert typical["voter"] == city["mechanism"]["typical"]["voter"]
        assert len(typical["delegates"]) == len(typical["resolvers"]) == city["design"]["topics"]
        chain = typical["chain"]
        assert chain["path"][0] == typical["voter"]
        assert chain["path"][-1] == typical["resolvers"][chain["topic"]]
        assert chain["path"][1:2] == [typical["delegates"][chain["topic"]]][: len(chain["path"]) - 1]
        # Following everyone's delegations in the featured question's topic
        # reaches whoever decides for them on that question
        graph = everyone["graph"]
        assert graph["topic"] == city["question"]["topic"]
        delegate_of, resolver = graph["delegate_of"], everyone["liquid_resolver"]
        for voter, decider in enumerate(resolver):
            seen, at = {voter}, voter
            while at != decider:
                at = delegate_of[at]
                assert at >= 0 and at not in seen, voter
                seen.add(at)

    def test_everyone_votes_part_one_data(self, city: dict[str, Any]) -> None:
        everyone = city["everyone"]
        votes = everyone["featured_votes"]
        assert len(votes) == city["design"]["residents"] and set(votes) <= {"y", "n"}
        # With everyone voting, direct voting's winner is the plurality of these votes
        winner = "y" if votes.count("y") > votes.count("n") else "n"
        assert everyone["winners"]["direct"][city["question"]["index"]] == winner
        typical = everyone["typical"]
        # Their representative lives in their district; their proxy is someone else
        assert city["district"][typical["representative"]] == city["district"][typical["voter"]]
        assert typical["proxy"] != typical["voter"]
        assert typical["proxy_resolver"] >= 0

    def test_everyone_votes_recomputes_byte_for_byte(self, builder: ModuleType, city: dict[str, Any]) -> None:
        reference, _ = builder._level(0.45)
        everyone = json.loads(
            builder.dumps(builder._everyone(reference, city["question"]["index"], city["mechanism"]["typical"]["voter"]))
        )
        assert everyone == city["everyone"]

    @pytest.mark.skipif(not (EVERYONE / "cities.jsonl.gz").exists(), reason="the city records are kept local")
    def test_everyone_votes_is_the_recorded_city(self, builder: ModuleType, city: dict[str, Any]) -> None:
        assert builder.check_everyone_recorded(city) is True
