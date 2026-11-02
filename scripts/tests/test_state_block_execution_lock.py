"""Exclusive state ownership across processes, including crash recovery."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

from scripts import state_block_execution_lock as locks


def test_lock_rejects_competing_owner_and_releases_after_exception(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(locks, "LOCK_ROOT", tmp_path)
    with pytest.raises(RuntimeError, match="deliberate"):
        with locks.state_execution_lock("1") as path:
            assert path == tmp_path / "state-01.lock"
            with pytest.raises(locks.StateExecutionLockedError, match="already owned"):
                with locks.state_execution_lock("01"):
                    pytest.fail("A competing owner acquired the same state.")
            with locks.state_execution_lock("02"):
                pass
            raise RuntimeError("deliberate")
    with locks.state_execution_lock("01"):
        pass
    assert path.exists()  # Persistent files must never be mistaken for ownership.


def test_os_releases_state_lock_when_owner_process_is_terminated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(locks, "LOCK_ROOT", tmp_path)
    script = (
        "from pathlib import Path\n"
        "import time\n"
        "from scripts import state_block_execution_lock as locks\n"
        f"locks.LOCK_ROOT = Path({json.dumps(str(tmp_path))})\n"
        "with locks.state_execution_lock('10'):\n"
        "    print('owned', flush=True)\n"
        "    time.sleep(30)\n"
    )
    child = subprocess.Popen([sys.executable, "-c", script], cwd=locks.ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        assert child.stdout is not None
        assert child.stdout.readline().strip() == "owned"
        with pytest.raises(locks.StateExecutionLockedError, match="already owned"):
            with locks.state_execution_lock("10"):
                pytest.fail("A second process acquired an owned state.")
    finally:
        child.terminate()
        child.communicate(timeout=10)
    with locks.state_execution_lock("10"):
        pass


def test_lock_rejects_unsafe_state_tokens() -> None:
    for state_fips in ("../10", "100", "ab", "１２"):
        with pytest.raises(ValueError, match="digits"):
            with locks.state_execution_lock(state_fips):
                pass
