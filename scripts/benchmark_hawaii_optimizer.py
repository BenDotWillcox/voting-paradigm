"""Benchmark the optimizer correction without rewriting original Hawaii runs."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.benchmark_hawaii_water import run


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--district-count', type=int, choices=(2, 3, 4), default=2)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run(args.district_count, args.output, optimizer_correction=True)


if __name__ == '__main__':
    main()
