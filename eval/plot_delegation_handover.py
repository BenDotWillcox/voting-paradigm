"""
Render the exploratory handover benchmark's figure from its summaries.

  python -m eval.plot_delegation_handover [DIRECTORY]

Writes handover_curve.png and figures.json (input, source and image hashes)
into eval/benchmarks/delegation_handover_v1/ by default. One panel per
turnout level: liquid's overhead against its fidelity at every handover
depth, beside the frozen benchmark's calibrated liquid point and district
representative, and full turnout. Exploratory, after the freeze; the
figure draws only what the summaries hold.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
from collections.abc import Sequence
from io import BytesIO
from pathlib import Path
from typing import Final

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

from .delegation_handover import CURVE, DEFAULT_OUT, FRONTIER, ROOT, _frontier_rows  # noqa: E402

# The frozen benchmark's figure module sets the shared style on import, so
# both benchmarks' figures read the same way
from .plot_delegation_frontier import (  # noqa: E402
    CAP,
    INK,
    INK_2,
    MUTED,
    SERIES_1,
    SERIES_2,
    SURFACE,
    SWISS,
    _header,
)

SOURCE: Final = "eval/plot_delegation_handover.py"
FIGURE: Final = "handover_curve.png"
COLUMNS: Final = 5


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def figure(directory: Path) -> Figure:
    curve = _rows(directory / CURVE)
    levels = sorted({float(r["level"]) for r in curve})
    frozen = {(float(r["level"]), r["arrangement"]): r for r in _frontier_rows(FRONTIER)}
    cities = int(curve[0]["cities"])
    rows = -(-len(levels) // COLUMNS)

    fig, axes = plt.subplots(rows, COLUMNS, sharex=True, sharey=True, figsize=(11.0, 5.4 * rows / 2 + 1.6))
    fig.subplots_adjust(left=0.065, right=0.985, top=0.83, bottom=0.17, hspace=0.32, wspace=0.08)
    _header(
        fig,
        "Exploratory: handing over more topics raises fidelity up to turnout 0.7, and lowers it from 0.8",
        f"{cities} primary cities. At depth d every voter hands over their d best topics. Depth 0, direct voting, "
        "is each curve's right end;\ndepth 8, everything a voter can hand over, its left end. Computed after "
        "the freeze with the frozen code; it changes no frozen reading.",
    )
    for ax, level in zip(axes.flat, levels, strict=False):
        points = sorted((r for r in curve if float(r["level"]) == level), key=lambda r: int(r["depth"]))
        x = np.array([float(r["overhead"]) for r in points])
        y = np.array([float(r["fidelity"]) for r in points])
        ax.grid(zorder=0)
        ax.axvline(CAP, color=MUTED, lw=0.8, ls=(0, (4, 3)), zorder=1)
        ax.plot(x, y, color=SERIES_1, lw=1.8, zorder=3, solid_capstyle="round")
        ax.plot(x, y, "o", color=SERIES_1, ms=4.2, mec=SURFACE, mew=0.9, zorder=4)
        if level == levels[0]:
            # Named once; every panel runs the same way along the x axis
            deepest = len(points) - 1
            for depth, offset, align in ((0, (-3, -10), "right"), (deepest, (0, 11), "center")):
                ax.annotate(
                    f"depth {depth}", (x[depth], y[depth]), xytext=offset, textcoords="offset points",
                    ha=align, va="center", fontsize=7.5, color=INK_2,
                )
        calibrated = frozen[(level, "liquid")]
        ax.plot(
            float(calibrated["overhead"]), float(calibrated["fidelity"]), "o", ms=7, mfc="none", mec=INK,
            mew=1.2, zorder=5,
        )
        representative = frozen[(level, "representative")]
        ax.plot(
            float(representative["overhead"]), float(representative["fidelity"]), "D", ms=5.5, color=SERIES_2,
            mec=SURFACE, mew=0.9, zorder=5,
        )
        ax.plot(1.0, 1.0, "s", ms=5, color=INK_2, zorder=5)
        title = f"Turnout {level:g}" + (" (Swiss)" if level == SWISS else "")
        ax.set_title(title, loc="left", fontsize=9, fontweight="bold", pad=4)
        ax.set_xlim(-0.04, 1.06)
        ax.set_ylim(0.0, 1.06)
        ax.set_xticks([0, 0.25, 0.5, 0.75, 1.0])
        ax.set_xticklabels(["0", "", "0.5", "", "1"])
        ax.set_yticks([0, 0.25, 0.5, 0.75, 1.0])
        ax.set_yticklabels(["0", "", "0.5", "", "1"])
        for tick in ax.get_xticklabels() + ax.get_yticklabels():
            tick.set_fontsize(7.5)
    for ax in axes[-1]:
        ax.set_xlabel("Overhead", fontsize=8)
    for ax in axes[:, 0]:
        ax.set_ylabel("Fidelity", fontsize=8)
    fig.legend(
        handles=[
            Line2D([], [], color=SERIES_1, lw=1.8, marker="o", ms=4.2, mec=SURFACE, label="Liquid, depths 0 to 8"),
            Line2D([], [], color=INK, ls="none", marker="o", ms=7, mfc="none", mew=1.2,
                   label="Liquid as calibrated in the frozen benchmark"),
            Line2D([], [], color=SERIES_2, ls="none", marker="D", ms=5.5, mec=SURFACE, label="District representative"),
            Line2D([], [], color=INK_2, ls="none", marker="s", ms=5, label="Full turnout"),
            Line2D([], [], color=MUTED, lw=0.8, ls=(0, (4, 3)), label="10% overhead"),
        ],
        loc="lower center",
        ncol=5,
        fontsize=8,
        bbox_to_anchor=(0.5, 0.05),
    )
    fig.text(
        0.065, 0.004,
        "The calibrated point is the frozen rule: the highest acceptance level whose overhead on history "
        "questions is at most 10%, so as little\ndelegation as meets the cap. Where no level meets it (0.1, 0.2 "
        "and 0.9) it falls back to acceptance 0, which is depth 8. Means over cities; intervals in curve.csv.",
        fontsize=7.4, color=MUTED, va="bottom", linespacing=1.35,
    )
    return fig


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def render(directory: Path) -> list[Path]:
    """The figure and figures.json, from the summaries in `directory`."""
    inputs = {
        CURVE: _sha256((directory / CURVE).read_bytes()),
        "frontier measures.csv": _sha256((FRONTIER / "measures.csv").read_bytes()),
    }
    fig = figure(directory)
    buffer = BytesIO()
    fig.savefig(buffer, format="png", dpi=160, metadata={"Software": "delegation-handover-benchmark"})
    plt.close(fig)
    image = buffer.getvalue()
    (directory / FIGURE).write_bytes(image)
    manifest = {
        "figure_manifest_version": 1,
        "environment": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "matplotlib": matplotlib.__version__,
        },
        "input_sha256": inputs,
        "source_sha256_lf_normalized": {SOURCE: _sha256((ROOT / SOURCE).read_bytes().replace(b"\r\n", b"\n"))},
        "png_sha256": {FIGURE: _sha256(image)},
    }
    path = directory / "figures.json"
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return [directory / FIGURE, path]


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("directory", type=Path, nargs="?", default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    for path in render(args.directory):
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
