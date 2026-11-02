"""Process-owned per-state locks for block jobs and extraction cleanup.

The stable lock directory is independent of output and custom source paths.
Lock files remain in place; the OS releases ownership when the owning process
exits, including after a crash. Persistent files are not evidence of ownership.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import os
from pathlib import Path
import sys

if sys.platform == "win32":
    import msvcrt
else:
    import fcntl


ROOT = Path(__file__).resolve().parents[1]
LOCK_ROOT = ROOT / ".cache/state-block-benchmark/locks"


class StateExecutionLockedError(RuntimeError):
    """Another process currently owns this state's source and output work."""


@contextmanager
def state_execution_lock(state_fips: str) -> Iterator[Path]:
    """Acquire a nonblocking exclusive state lock until the context exits."""
    if not isinstance(state_fips, str):
        raise ValueError("State FIPS must be an ASCII numeric string.")
    token = state_fips.strip().zfill(2)
    if len(token) != 2 or not token.isascii() or not token.isdigit():
        raise ValueError("State FIPS must contain one or two ASCII digits.")
    LOCK_ROOT.mkdir(parents=True, exist_ok=True)
    path = LOCK_ROOT / f"state-{token}.lock"
    with path.open("a+b") as stream:
        if stream.seek(0, os.SEEK_END) == 0:
            stream.write(b"\0")
            stream.flush()
        stream.seek(0)
        try:
            if sys.platform == "win32":
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise StateExecutionLockedError(
                f"State {token} is already owned by another active block job or cleanup process "
                f"({path}). Retry after that process finishes."
            ) from error
        try:
            yield path
        finally:
            stream.seek(0)
            if sys.platform == "win32":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
