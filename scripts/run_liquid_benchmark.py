"""
Run demo 5's benchmark and read its verdicts.

  python -m scripts.run_liquid_benchmark smoke
      A few small cities on development seeds, to check the pipeline end to
      end in about a minute. Never the primary namespace.
  python -m scripts.run_liquid_benchmark primary
      The 200 primary cities at every level of the turnout dial, with the
      attendance frontier. Run only from the frozen, committed checkout.
  python -m scripts.run_liquid_benchmark sweeps [--point "history: 10 per topic"]
      Every declared sweep point on its 48 cities at every level.
  python -m scripts.run_liquid_benchmark analyse primary
      Write report.json and report.md for a finished (or partial) run.

Runs checkpoint after every city and resume where they stopped; the
manifest binds a run directory to one commit. Output defaults to
.cache/liquid-benchmark/<mode>/ (Git-ignored). Design:
prompts/demo-5-liquid-democracy.md, "Research protocol".
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from collections.abc import Callable
from pathlib import Path

from delegation.comparison.runner import (
    analyse,
    primary_tasks,
    run,
    smoke_tasks,
    sweep_tasks,
    write_report,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / ".cache" / "liquid-benchmark"


def _progress(started: float) -> Callable[[int, int], None]:
    def report(count: int, total: int) -> None:
        elapsed = time.time() - started
        left = elapsed / count * (total - count)
        print(f"  {count}/{total} cities, {elapsed / 60:.1f} min elapsed, ~{left / 60:.0f} min left", flush=True)

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("smoke", "primary", "sweeps"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--out", type=Path, default=None)
        cmd.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 2))
        cmd.add_argument("--allow-dirty", action="store_true", help="development only")
        if name == "sweeps":
            cmd.add_argument("--point", default=None, help="one sweep point, by its 'family: label'")
    report = sub.add_parser("analyse")
    report.add_argument("mode", choices=["smoke", "primary", "sweeps"])
    report.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    if args.command == "analyse":
        out = args.out or DEFAULT_OUT / args.mode
        path = write_report(out, analyse(out, args.mode))
        print(f"wrote {path} and {path.with_suffix('.md')}")
        return

    out = args.out or DEFAULT_OUT / args.command
    if args.command == "smoke":
        tasks = smoke_tasks()
    elif args.command == "primary":
        tasks = primary_tasks()
    else:
        tasks = sweep_tasks(args.point)
    print(f"{args.command}: {len(tasks)} cities into {out} with {args.workers} workers", flush=True)
    started = time.time()
    try:
        ran = run(
            tasks,
            out,
            args.command,
            workers=args.workers,
            allow_dirty=args.allow_dirty,
            progress=_progress(started),
        )
    except RuntimeError as error:
        sys.exit(str(error))
    print(f"ran {ran} cities in {(time.time() - started) / 60:.1f} min", flush=True)
    path = write_report(out, analyse(out, args.command))
    print(f"wrote {path} and {path.with_suffix('.md')}")


if __name__ == "__main__":
    main()
