"""
The essay's committed artifacts are reproducible and agree with the explorer.

- Building twice gives byte-identical outputs.
- The committed files in public/data/apportionment-story/ equal a fresh build,
  so a source or code change without a rebuild fails here.
- The TypeScript sequence behind /apportionment/explore gives the same seats
  as the Python package at every rule-defined House size.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / "public" / "data" / "apportionment-story"


def _load_build_module():
    spec = importlib.util.spec_from_file_location(
        "build_apportionment_story", ROOT / "scripts" / "build_apportionment_story.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def build():
    return _load_build_module()


def test_build_is_deterministic(build):
    first = {name: build.dumps(payload) for name, payload in build.build_artifacts().items()}
    second = {name: build.dumps(payload) for name, payload in build.build_artifacts().items()}
    assert first == second


def test_committed_artifacts_are_current(build):
    for name, payload in build.build_artifacts().items():
        committed = (ARTIFACTS / name).read_bytes()
        assert committed == build.dumps(payload).encode("utf-8"), (
            f"{name} is stale; run scripts/build_apportionment_story.py"
        )


def test_manifest_hashes_match_outputs(build):
    manifest = json.loads((ARTIFACTS / "manifest.json").read_text(encoding="utf-8"))
    for name, digest in manifest["outputs"].items():
        assert build.sha256((ARTIFACTS / name).read_bytes()) == digest, name
    for name, source in manifest["sources"].items():
        assert build.sha256((build.SOURCES / name).read_bytes()) == source["sha256"], name


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js not available")
def test_typescript_sequence_matches_python():
    result = subprocess.run(
        ["node", str(ROOT / "scripts" / "check-apportionment-parity.mjs")],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
