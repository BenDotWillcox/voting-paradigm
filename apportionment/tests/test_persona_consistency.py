"""
The essay's fictional people never contradict themselves.

Runs scripts/check-persona-consistency.mjs, which samples many people from
lib/apportionment/persona.ts and checks them against independent rules
(incompatible pairs, role-only statements, reachability, label length).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js not available")
def test_personas_are_consistent():
    result = subprocess.run(
        ["node", str(ROOT / "scripts" / "check-persona-consistency.mjs")],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
