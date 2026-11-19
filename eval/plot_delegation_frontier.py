"""
Render demo 5's published benchmark figures from its CSV summaries.

  python -m eval.plot_delegation_frontier [DIRECTORY]

Writes four PNGs and figures.json (input, source and image hashes) into the
benchmark directory, eval/benchmarks/delegation_frontier_v1/ by default:

  figure1_threshold.png        H1: liquid minus representative fidelity across
                               the turnout dial, both curves and their
                               simultaneous band, with the overhead gate below
  figure2_frontier.png         the attendance frontier: the difference with
                               delegates at their own rate and always voting,
                               and what each attendance floor adds
  overhead_fidelity_plane.png  every arrangement's overhead and fidelity at
                               the Swiss marker
  sweeps.png                   every sweep point across the turnout dial, one
                               panel per family, beside its declared baseline

The figures draw only what the summaries hold; every value is also in the
CSVs. Synthetic cities, not sampled voters.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import textwrap
from collections.abc import Mapping, Sequence
from io import BytesIO
from pathlib import Path
from typing import Any, Final

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.axes import Axes  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402
from matplotlib.legend_handler import HandlerTuple  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402
from matplotlib.ticker import FuncFormatter, MultipleLocator, PercentFormatter  # noqa: E402

from delegation.comparison.sweeps import PRIMARY_POINT  # noqa: E402

from .delegation_frontier import (  # noqa: E402
    DEFAULT_OUT,
    PRIMARY_KEY,
    REFERENCE_KEY,
    ROOT,
    STRUCTURAL_BASELINE,
)

SOURCE: Final = "eval/plot_delegation_frontier.py"
INPUTS: Final = ("thresholds.csv", "levels.csv", "frontier.csv", "measures.csv")
SWISS: Final = 0.45
CAP: Final = 0.10
GATE: Final = 0.95
DELTA_POINTS: Final = 2.0
OFFICE_HOLDER_RATE: Final = 0.96

# The reference palette (dataviz skill): two categorical slots, validated
# adjacent and all-pairs on the light surface; chrome and ink tokens
SURFACE: Final = "#fcfcfb"
INK: Final = "#0b0b0b"
INK_2: Final = "#52514e"
MUTED: Final = "#898781"
GRID: Final = "#e1e0d9"
AXIS: Final = "#c3c2b7"
SERIES_1: Final = "#2a78d6"
SERIES_2: Final = "#eb6834"
CRITICAL: Final = "#d03b3b"
# Ordinal steps of the blue ramp for ordered settings, light to dark; on the
# light surface an ordinal ramp starts no lighter than step 250
BLUE_250: Final = "#86b6ef"
BLUE_300: Final = "#6da7ec"
BLUE_650: Final = "#104281"
ORDINAL: Final = {1: (SERIES_1,), 2: (BLUE_250, BLUE_650), 3: (BLUE_250, SERIES_1, BLUE_650)}
# The dial's tenths; the Swiss marker is drawn as a labelled line, not a tick
TENTHS: Final = tuple(round(0.1 * i, 1) for i in range(1, 10))

plt.rcParams.update(
    {
        # Bundled with Matplotlib, so the images do not depend on installed fonts
        "font.family": "DejaVu Sans",
        "font.size": 9,
        "text.color": INK,
        "axes.edgecolor": AXIS,
        "axes.labelcolor": INK_2,
        "axes.titlecolor": INK,
        "axes.facecolor": SURFACE,
        "figure.facecolor": SURFACE,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.linewidth": 0.8,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "xtick.labelcolor": INK_2,
        "ytick.labelcolor": INK_2,
        "grid.color": GRID,
        "grid.linewidth": 0.8,
        "legend.frameon": False,
        "svg.hashsalt": "delegation-frontier",
    }
)


def _rows(directory: Path, name: str) -> list[dict[str, str]]:
    with (directory / name).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _f(value: str) -> float:
    return float("nan") if value == "" else float(value)


def _points(values: Sequence[str]) -> np.ndarray[Any, np.dtype[np.float64]]:
    """Fidelity differences in percentage points."""
    return np.array([_f(v) * 100 for v in values], dtype=np.float64)


def _header(fig: Figure, title: str, subtitle: str) -> None:
    fig.text(0.06, 0.975, title, fontsize=11.5, fontweight="bold", va="top", ha="left")
    fig.text(0.06, 0.935, subtitle, fontsize=9, color=INK_2, va="top", ha="left")


def _point_axis(ax: Axes) -> None:
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:+.0f}" if v else "0"))


def _dial_axis(ax: Axes, *, fontsize: float = 8.5) -> None:
    ax.set_xlim(0.05, 0.95)
    ax.set_xticks(TENTHS)
    ax.set_xticklabels([f"{x:g}" for x in TENTHS], fontsize=fontsize)


def _swiss_label(ax: Axes, text: str = f"Swiss mean turnout {SWISS:g}") -> None:
    ax.text(SWISS + 0.008, ax.get_ylim()[1], text, color=INK_2, fontsize=8, va="top")


def figure1(directory: Path) -> Figure:
    rows = [r for r in _rows(directory, "levels.csv") if r["point"] == PRIMARY_KEY]
    threshold = next(r for r in _rows(directory, "thresholds.csv") if r["point"] == PRIMARY_KEY)
    levels = np.array([float(r["level"]) for r in rows])
    cities = int(threshold["cities"])
    city = PRIMARY_POINT.config(1, SWISS)
    residents = city.districts * city.residents_per_district
    shares = np.array([float(r["cap_share"]) for r in rows])
    failing = shares < GATE
    low, high = float(threshold["confidence_low"]), float(threshold["confidence_high"])
    crossing = _f(threshold["all_cities_interpolated"])
    first = _f(threshold["first_supported"])

    fig, (ax, gate) = plt.subplots(
        2, 1, sharex=True, figsize=(8.0, 7.7), gridspec_kw={"height_ratios": [3.2, 1.45], "hspace": 0.12}
    )
    fig.subplots_adjust(left=0.115, right=0.97, top=0.835, bottom=0.165)
    reading = ""
    if threshold["gate_holds"] == "false" and not np.isnan(crossing):
        short = [f"{level:g}" for level in levels[failing] if level >= first]
        reading = (
            f"Liquid overtakes the representative near {crossing:.2f}, but at {' and '.join(short)} fewer than "
            f"{GATE:.0%} of cities keep its overhead at or under {CAP:.0%}. "
        )
    subtitle = (
        f"{cities} simulated cities of {residents} residents each "
        f"({city.districts} districts of {city.residents_per_district}); every point averages them.\n"
        + textwrap.fill(f"{reading}Frozen verdict: {threshold['verdict']}.", width=100)
    )
    _header(fig, "H1: liquid delegation minus the district representative, across the turnout dial", subtitle)
    gate_limits = (-0.05, 1.32)
    for axis in (ax, gate):
        axis.axvspan(low, high, color=GRID, alpha=0.6, lw=0, zorder=0)
    # The Swiss line is drawn above only: below, the 0.45 stem marks the level,
    # and a line would strike through its label
    ax.axvline(SWISS, color=MUTED, lw=0.8, zorder=1)
    ax.grid(axis="y", zorder=0)
    ax.axhline(0, color=AXIS, lw=1.0, zorder=1)
    ax.axhline(DELTA_POINTS, color=MUTED, lw=0.9, ls=(0, (4, 3)), zorder=1)
    ax.text(0.935, DELTA_POINTS + 0.5, f"δ = {DELTA_POINTS:g} points", color=INK_2, fontsize=8, ha="right")

    all_mean = _points([r["h1_all_estimate"] for r in rows])
    band_low = _points([r["band_all_lower"] for r in rows])
    band_high = _points([r["band_all_upper"] for r in rows])

    # The cap-meeting curve, drawn under the all-city line: where (nearly)
    # every city meets the cap the two coincide and it is hidden, so it only
    # shows where few cities qualify. Its band is drawn there alone, since
    # elsewhere it lies inside the all-city band
    cap_rows = [r for r in rows if r["h1_cap_estimate"]]
    cap_x = np.array([float(r["level"]) for r in cap_rows])
    cap_mean = _points([r["h1_cap_estimate"] for r in cap_rows])
    cap_counts = np.array([int(r["cap_meeting_cities"]) for r in cap_rows])
    thin = cap_counts < GATE * cities
    cap_low = _points([r["band_cap_lower"] for r in cap_rows])[thin]
    cap_high = _points([r["band_cap_upper"] for r in cap_rows])[thin]
    ax.plot(cap_x, cap_mean, color=SERIES_2, lw=1.5, ls=(0, (3, 2)), zorder=2.6)
    ax.vlines(cap_x[thin], cap_low, cap_high, colors=SERIES_2, lw=1.4, zorder=2.6)
    ax.plot(cap_x[thin], cap_mean[thin], "o", ls="none", ms=4.5, color=SERIES_2, mec=SURFACE, mew=1.0, zorder=4.5)

    ax.fill_between(levels, band_low, band_high, color=SERIES_1, alpha=0.14, lw=0, zorder=2)
    ax.plot(levels, all_mean, color=SERIES_1, lw=2, zorder=3, solid_capstyle="round")
    ax.plot(levels, all_mean, "o", color=SERIES_1, ms=6, mec=SURFACE, mew=1.5, zorder=4)
    _swiss_label(ax)
    bottom = ax.get_ylim()[0]
    # The threshold's confidence set is a range of turnout, so it is drawn
    # across the x-axis, not as a band on the difference
    ax.text(
        (low + high) / 2 + 0.02, bottom + 0.6, "95% range for\nthe crossing", color=INK_2, fontsize=8,
        ha="center", va="bottom",
    )
    if not np.isnan(crossing):
        # Small, so the cap curve's band at the next level stays visible beside it
        ax.plot(crossing, 0, "o", ms=5, mfc=SURFACE, mec=INK, mew=1.3, zorder=6)
        ax.annotate(
            f"overtakes near {crossing:.2f}", (crossing, 0), xytext=(10, -15), textcoords="offset points",
            fontsize=8, color=INK, va="center",
        )
    swiss = rows[[i for i, r in enumerate(rows) if float(r["level"]) == SWISS][0]]
    lead = _f(swiss["h1_all_estimate"]) * 100
    ax.annotate(
        f"{lead:+.1f} points at Swiss turnout",
        (SWISS, lead),
        xytext=(28, -26),
        textcoords="offset points",
        ha="left",
        va="center",
        fontsize=8.5,
        color=INK,
        arrowprops={"arrowstyle": "-", "color": INK_2, "lw": 0.8, "shrinkA": 3, "shrinkB": 5},
    )
    ax.set_ylabel("Liquid minus representative fidelity (points)")
    _point_axis(ax)
    ax.legend(
        handles=[
            Line2D([], [], color=SERIES_1, lw=2, marker="o", ms=6, mec=SURFACE, label=f"All {cities} cities"),
            Rectangle((0, 0), 1, 1, color=SERIES_1, alpha=0.14, lw=0, label="95% band for that curve"),
            Line2D(
                [], [], color=SERIES_2, lw=1.5, ls=(0, (3, 2)), marker="o", ms=4.5, mec=SURFACE,
                label=f"Only cities under the {CAP:.0%} cap",
            ),
        ],
        loc="upper left",
        fontsize=8.5,
    )

    # Dots on stems, not bars: the dial is a continuous axis with an extra
    # level at 0.45, and a bar's width makes that look like uneven spacing
    gate.vlines(levels, 0, shares, colors=GRID, lw=1.6, zorder=2)
    gate.scatter(
        levels, shares, s=34, c=np.where(failing, CRITICAL, INK_2), edgecolors=SURFACE, linewidths=1.2,
        zorder=4, clip_on=False,
    )
    gate.axhline(GATE, color=INK_2, lw=0.9, ls=(0, (4, 3)), zorder=3)
    # Inside the confidence range, where no stem reaches the line
    gate.text(0.115, GATE - 0.08, f"gate: {GATE:.0%} of cities", color=INK_2, fontsize=8, ha="left", va="top")
    # Every share is labelled: near the top, 98% and 100% look the same. A
    # failing level also gives its count of cities, which the top panel's
    # orange curve rests on there
    for row, x, share, fails in zip(rows, levels, shares, failing, strict=True):
        under = int(row["cap_meeting_cities"])
        lift = 6
        if fails and under:
            gate.annotate(
                f"{under} cities", (x, share), xytext=(0, lift), textcoords="offset points", ha="center",
                va="bottom", fontsize=7.3, color=INK_2,
            )
            lift += 10
        gate.annotate(
            f"{share * 100:.1f}".rstrip("0").rstrip(".") + "%", (x, share), xytext=(0, lift),
            textcoords="offset points", ha="center", va="bottom", fontsize=7.5, color=INK,
            fontweight="bold" if fails else "normal",
        )
    gate.set_ylim(*gate_limits)
    gate.set_yticks([0, 0.5, 1])
    gate.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
    gate.set_ylabel(f"Share of cities with\noverhead ≤ {CAP:.0%}", labelpad=4)
    _dial_axis(gate)
    gate.set_xlabel("Mean citizen turnout (the dial)")

    # What the plot cannot say briefly, said once below it
    close = cap_x[~thin]
    gap = np.abs(cap_mean[~thin] - all_mean[np.isin(levels, close)]).max()
    sparse = ", ".join(f"{count} at {x:g}" for x, count in zip(cap_x[thin], cap_counts[thin], strict=True))
    empty = [f"{level:g}" for level in levels if level not in cap_x]
    dips = [x for x, bound in zip(cap_x[thin], cap_low, strict=True) if bound < 0 < x < high]
    caption = (
        f"Dashed orange: the same difference over only the cities whose overhead stays at or under {CAP:.0%}. "
        f"From {close.min():g} to {close.max():g} nearly every city qualifies and it lies within "
        f"{max(gap, 0.1):.1f} points of the blue curve, hidden under it. At the ends it rests on few cities "
        f"({sparse}; bars: its 95% band)"
        + (f", and at {' and '.join(empty)} none qualify" if empty else "")
        + "."
        + (
            f" Its band at {dips[0]:g} dips below zero, which is why the range for the crossing runs to {high:g}."
            if dips
            else ""
        )
        + f" δ = {DELTA_POINTS:g} points is the smallest lead counted as worthwhile."
    )
    fig.text(0.115, 0.018, textwrap.fill(caption, width=118), fontsize=7.6, color=INK_2, va="bottom")
    return fig


LEADS_AT_OWN_RATE: Final = "leads at the lowest floor"


def figure2(directory: Path) -> Figure:
    rows = _rows(directory, "frontier.csv")
    estimate = {(float(r["level"]), float(r["floor"])): _f(r["estimate"]) * 100 for r in rows}
    status = {float(r["level"]): r["status"] for r in rows}
    levels = sorted(status)
    floors = sorted({floor for _, floor in estimate})
    primary = [r for r in _rows(directory, "levels.csv") if r["point"] == PRIMARY_KEY]
    caps = {float(r["level"]): int(r["cap_meeting_cities"]) for r in primary}
    cities = int(next(r for r in _rows(directory, "thresholds.csv") if r["point"] == PRIMARY_KEY)["cities"])

    x = np.array(levels)
    own = np.array([estimate[level, 0.0] for level in levels])
    office = np.array([estimate[level, OFFICE_HOLDER_RATE] for level in levels])
    always = np.array([estimate[level, 1.0] for level in levels])
    # The floors not drawn, and the most any of them moves the difference
    lower = [floor for floor in floors if 0 < floor < OFFICE_HOLDER_RATE]
    most = max(abs(estimate[level, floor] - estimate[level, 0.0]) for level in levels for floor in lower)
    leading = [level for level in levels if status[level] == LEADS_AT_OWN_RATE]
    sustained = bool(leading) and leading == levels[levels.index(leading[0]) :]

    fig, (ax, gain) = plt.subplots(
        2, 1, sharex=True, figsize=(8.0, 6.8), gridspec_kw={"height_ratios": [3.0, 1.45], "hspace": 0.12}
    )
    fig.subplots_adjust(left=0.1, right=0.97, top=0.84, bottom=0.145)
    subtitle = (
        f"{cities} primary cities. Each delegate votes at the larger of their own rate and a floor; "
        f"office holders stay at {OFFICE_HOLDER_RATE:g}."
    )
    if sustained:
        subtitle += (
            f"\nFrom {leading[0]:g} upward liquid already leads with delegates at their own rate, "
            "so no floor changes where it leads."
        )
    _header(fig, "Attendance frontier: how far better delegate attendance moves Figure 1", subtitle)
    for axis in (ax, gain):
        axis.grid(axis="y", zorder=0)
        axis.axvline(SWISS, color=MUTED, lw=0.8, zorder=1)
        axis.axhline(0, color=AXIS, lw=1.0, zorder=1)

    ax.fill_between(x, own, always, color=SERIES_1, alpha=0.14, lw=0, zorder=2)
    ax.plot(x, always, color=BLUE_650, lw=1.6, ls=(0, (4, 2)), zorder=3)
    ax.plot(x, own, color=SERIES_1, lw=2, zorder=4, solid_capstyle="round")
    ax.plot(x, own, "o", color=SERIES_1, ms=5.5, mec=SURFACE, mew=1.3, zorder=5)
    ax.set_ylim(np.floor(min(own.min(), always.min()) / 5) * 5 - 1, np.ceil(max(own.max(), always.max()) / 5) * 5)
    _swiss_label(ax)
    if always[0] < 0:
        ax.text(
            levels[0] + 0.035,
            own[0],
            f"At {levels[0]:g} liquid trails by {abs(own[0]):.1f} points,\n"
            f"and still by {abs(always[0]):.1f} if every delegate always votes:\n"
            "the shortfall is residents who keep their own vote.",
            color=INK_2,
            fontsize=8,
            va="center",
        )
    ax.set_ylabel("Liquid minus representative (points)")
    _point_axis(ax)
    ax.legend(
        handles=[
            Line2D(
                [], [], color=SERIES_1, lw=2, marker="o", ms=5.5, mec=SURFACE,
                label="Delegates at their own rate (Figure 1)",
            ),
            Line2D([], [], color=BLUE_650, lw=1.6, ls=(0, (4, 2)), label="Every delegate always votes (floor 1)"),
            Rectangle((0, 0), 1, 1, color=SERIES_1, alpha=0.14, lw=0, label="The most better attendance could add"),
        ],
        loc="upper left",
        fontsize=8.5,
    )

    for floor, values, color, label in (
        (1.0, always, BLUE_650, "Floor 1: every delegate always votes"),
        (OFFICE_HOLDER_RATE, office, BLUE_300, f"Floor {OFFICE_HOLDER_RATE:g}: the office-holder rate"),
    ):
        added = values - own
        gain.plot(x, added, color=color, lw=1.8, zorder=3, solid_capstyle="round", label=label)
        gain.plot(x, added, "o", color=color, ms=4.5, mec=SURFACE, mew=1.1, zorder=4)
        gain.annotate(
            f"+{added[0]:.1f}", (x[0], added[0]), xytext=(7, 0), textcoords="offset points", va="center",
            fontsize=8, color=INK_2,
        )
    gain.set_ylim(-0.3, np.ceil((always - own).max()) + 0.6)
    gain.yaxis.set_major_locator(MultipleLocator(1))
    gain.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"+{v:.0f}" if v > 0 else f"{v:.0f}"))
    gain.set_ylabel("Added (points)")
    gain.legend(loc="upper right", fontsize=8.5)
    _dial_axis(gain)
    gain.set_xlabel("Mean citizen turnout (the dial)")
    for tick in ax.get_yticklabels() + gain.get_yticklabels():
        tick.set_fontsize(8.5)

    sparse = [level for level in levels if caps[level] < GATE * cities]
    fig.text(
        0.1,
        0.015,
        f"Floors {lower[0]:g} to {lower[-1]:g} add at most {most:.1f} points at any level and are not drawn.\n"
        "Cities under the 10% cap: "
        + ", ".join(f"{caps[level]} at {level:g}" for level in sparse)
        + "; the frontier reads both curves, as Figure 1 does.",
        fontsize=7.5,
        color=MUTED,
    )
    return fig


ARRANGEMENTS: Final = (
    ("full_turnout", "Full turnout (reference)", "left", (-10, 0)),
    ("direct", "Direct voting at this turnout", "left", (-10, 0)),
    ("representative", "District representative", "right", (10, -2)),
    ("proxy", "Personal proxy", "right", (10, -12)),
    ("liquid", "Liquid delegation", "right", (10, 12)),
)


def plane(directory: Path) -> Figure:
    rows = {
        r["arrangement"]: r
        for r in _rows(directory, "measures.csv")
        if r["point"] == PRIMARY_KEY and float(r["level"]) == SWISS
    }
    fig, ax = plt.subplots(figsize=(7.2, 5.6))
    fig.subplots_adjust(left=0.11, right=0.96, top=0.84, bottom=0.15)
    _header(
        fig,
        "Overhead and fidelity at the Swiss marker (mean turnout 0.45)",
        "Means over the 200 primary cities. Overhead: the share of questions a voter decides themself.",
    )
    ax.grid(zorder=0)
    ax.axvline(CAP, color=MUTED, lw=0.9, ls=(0, (4, 3)), zorder=1)
    ax.text(CAP + 0.012, 0.415, "10% overhead cap", color=INK_2, fontsize=8, va="bottom")
    for key, label, side, offset in ARRANGEMENTS:
        x, y = float(rows[key]["overhead"]), float(rows[key]["fidelity"])
        liquid = key == "liquid"
        ax.plot(
            x, y, "o", color=SERIES_1 if liquid else INK_2, ms=8 if liquid else 7, mec=SURFACE, mew=1.5, zorder=4
        )
        ax.annotate(
            f"{label}\nfidelity {y:.3f}, overhead {x:.3f}",
            (x, y),
            xytext=offset,
            textcoords="offset points",
            ha="right" if side == "left" else "left",
            va="center",
            fontsize=8.5,
            color=INK,
        )
    ax.set_xlim(-0.04, 1.06)
    ax.set_ylim(0.4, 1.04)
    ax.set_xlabel("Overhead")
    ax.set_ylabel("Fidelity (share of counted ballots matching the voter)")
    for tick in ax.get_xticklabels() + ax.get_yticklabels():
        tick.set_fontsize(8.5)
    fig.text(
        0.11,
        0.035,
        "Liquid's curve by number of categories handed over is not in the recorded runs; "
        "the matched arms are in measures.csv.",
        fontsize=7.5,
        color=MUTED,
    )
    return fig


# One panel per sweep family: its points in their natural order, with the
# declared baseline in its place. A colour of None takes the next step of the
# ordinal ramp; a named colour marks a point that is not on the family's scale.
SweepSeries = tuple[str, str, str | None]
SWEEP_PANELS: Final[tuple[tuple[str, tuple[SweepSeries, ...]], ...]] = (
    (
        "History questions per topic",
        (
            ("history: 10 per topic", "10", None),
            ("history: 20 per topic", "20", None),
            (REFERENCE_KEY, "50", None),
            ("history: 100 per topic", "100", None),
        ),
    ),
    (
        "Turnout spread (engagement)",
        (
            ("turnout_spread: engagement spread 1.0", "1.0 (an even electorate)", None),
            ("turnout_spread: engagement spread 2.07", "2.07", None),
            (REFERENCE_KEY, "2.81 (Geneva)", None),
            ("turnout_spread: engagement spread 3.5", "3.5", None),
        ),
    ),
    (
        "Within-topic spread",
        (
            ("within_topic_spread: spread x0.5", "×0.5", None),
            (REFERENCE_KEY, "×1", None),
            ("within_topic_spread: spread x1.5", "×1.5", None),
        ),
    ),
    (
        "Districts per city",
        (
            ("districts: 2 districts", "2", None),
            (REFERENCE_KEY, "5", None),
            ("districts: 10 districts", "10", None),
        ),
    ),
    (
        "Evaluation topic mix",
        (
            (REFERENCE_KEY, "even", None),
            ("evaluation_mix: one topic 2x in evaluation", "one topic 2× heavier", None),
            ("evaluation_mix: one topic 4x in evaluation", "one topic 4× heavier", None),
        ),
    ),
    (
        "Belief structure (one-factor generator)",
        (
            ("belief_structure: correlation 0", "correlation 0", None),
            ("belief_structure: correlation 0.4", "0.4", None),
            (STRUCTURAL_BASELINE or "", "0.87 (CES-matched)", None),
            ("belief_structure: correlation 0.95", "0.95", None),
            ("belief_structure: two blocks of four: 0.87 within, 0.2 across", "two blocks of four", SERIES_2),
        ),
    ),
    (
        "Ballot days and the stress case",
        (
            (REFERENCE_KEY, "primary settings", None),
            ("attendance: ballot days of three questions", "ballot days of three", SERIES_1),
            ("stress: stress case", "stress case", SERIES_2),
        ),
    ),
)
SWEEP_COLUMNS: Final = 3


def sweeps(directory: Path) -> Figure:
    rows = _rows(directory, "levels.csv")
    curves: dict[str, dict[float, Mapping[str, str]]] = {}
    for row in rows:
        curves.setdefault(row["point"], {})[float(row["level"])] = row
    baseline_of = {point: next(iter(curve.values()))["baseline"] for point, curve in curves.items()}
    thresholds = _rows(directory, "thresholds.csv")
    drawn = {key for _, series in SWEEP_PANELS for key, _, _ in series}
    declared = {r["point"] for r in thresholds} - {PRIMARY_KEY}
    if drawn != declared:
        raise RuntimeError(f"sweep panels do not match the declared points: {sorted(drawn ^ declared)}")
    cities = int(next(r for r in thresholds if r["point"] == REFERENCE_KEY)["cities"])
    levels = sorted(curves[REFERENCE_KEY])
    x = np.array(levels)

    def difference(point: str) -> np.ndarray[Any, np.dtype[np.float64]]:
        return np.array([_f(curves[point][level]["h1_all_estimate"]) * 100 for level in levels])

    def failing(point: str) -> np.ndarray[Any, np.dtype[np.bool_]]:
        return np.array([float(curves[point][level]["cap_share"]) < GATE for level in levels])

    sweep_points = [point for point in drawn if point != REFERENCE_KEY] + [REFERENCE_KEY]
    every = np.concatenate([difference(point) for point in sweep_points])
    halfwidths = np.array(
        [
            (_f(curves[point][level]["h1_all_upper"]) - _f(curves[point][level]["h1_all_lower"])) * 50
            for point in sweep_points
            for level in levels
        ]
    )

    fig = plt.figure(figsize=(10.5, 10.4))
    grid = fig.add_gridspec(3, SWEEP_COLUMNS, left=0.075, right=0.985, top=0.86, bottom=0.06, hspace=0.5, wspace=0.07)
    _header(
        fig,
        "Robustness sweeps: liquid minus the representative across the turnout dial",
        f"{cities} cities per sweep point. In every panel the x-axis is mean citizen turnout, as in Figure 1.\n"
        "Each line is one value of the setting named above the panel; "
        "the dark line is the baseline it is compared with.",
    )
    first = fig.add_subplot(grid[0, 0])
    panels = [first] + [
        fig.add_subplot(grid[i // SWEEP_COLUMNS, i % SWEEP_COLUMNS], sharex=first, sharey=first)
        for i in range(1, len(SWEEP_PANELS))
    ]
    first.set_ylim(np.floor(every.min() / 5) * 5 - 1, np.ceil(every.max() / 5) * 5 + 1)
    first.yaxis.set_major_locator(MultipleLocator(10))
    _point_axis(first)
    _dial_axis(first, fontsize=7.5)
    for i, (ax, (title, series)) in enumerate(zip(panels, SWEEP_PANELS, strict=True)):
        panel_row, panel_column = divmod(i, SWEEP_COLUMNS)
        keys = [key for key, _, _ in series]
        (baseline,) = {baseline_of[key] for key in keys if baseline_of[key] in keys}
        ax.grid(axis="y", zorder=0)
        ax.axhline(0, color=AXIS, lw=1.0, zorder=1)
        ax.axvline(SWISS, color=MUTED, lw=0.8, zorder=1)
        ax.set_title(title, loc="left", fontsize=9, fontweight="bold", pad=6)
        ramp = iter(ORDINAL.get(sum(1 for key, _, color in series if key != baseline and color is None), ()))
        handles: list[Line2D] = []
        context = baseline_of[baseline]
        if context:
            # A baseline that is itself compared with another (the one-factor
            # 0.87 point with the fitted reference) shows that one in grey
            ax.plot(x, difference(context), color=MUTED, lw=1.2, ls=(0, (3, 2)), zorder=2)
            handles.append(Line2D([], [], color=MUTED, lw=1.2, ls=(0, (3, 2)), label="fitted reference"))
        for key, label, named in series:
            is_baseline = key == baseline
            color = INK_2 if is_baseline else (named or next(ramp))
            values, gate_fails = difference(key), failing(key)
            # The baseline is drawn wider and underneath, so a setting that
            # matches it shows as a coloured line inside a dark one
            width = 2.8 if is_baseline else 1.6
            ax.plot(x, values, color=color, lw=width, zorder=2.5 if is_baseline else 3, solid_capstyle="round")
            ax.plot(
                x[gate_fails], values[gate_fails], "o", ls="none", ms=4.5, mfc=SURFACE, mec=color, mew=1.2,
                zorder=5,
            )
            handles.append(
                Line2D([], [], color=color, lw=width, label=f"{label}, baseline" if is_baseline else label)
            )
        ax.legend(handles=handles, loc="lower right", fontsize=7.3, handlelength=1.8, borderaxespad=0.3)
        # Turnout is labelled on every panel: the title names the setting,
        # which the lines vary, not the x-axis
        ax.tick_params(labelleft=panel_column == 0, labelbottom=True)
        for tick in ax.get_xticklabels() + ax.get_yticklabels():
            tick.set_fontsize(7.5)
        ax.set_xlabel("Mean citizen turnout", fontsize=8, labelpad=3)
        if panel_column == 0:
            ax.set_ylabel("Liquid minus representative (points)", fontsize=8)
    first.text(SWISS + 0.012, first.get_ylim()[1] - 1, f"Swiss {SWISS:g}", color=INK_2, fontsize=7.5, va="top")

    guide = fig.add_subplot(grid[2, 1:])
    guide.axis("off")
    guide.legend(
        handles=[
            Line2D([], [], color=INK_2, lw=2.8),
            tuple(Line2D([], [], color=step, lw=1.6) for step in ORDINAL[3]),
            Line2D([], [], color=INK_2, ls="none", marker="o", ms=4.5, mfc=SURFACE, mew=1.2),
            Line2D([], [], color=MUTED, lw=0.8),
        ],
        labels=[
            "baseline: the first 48 primary cities (belief structure: its own 0.87 point)",
            "the family's other settings, light to dark in their order",
            "fewer than 95% of cities under the 10% overhead cap at that level",
            f"Swiss mean turnout, {SWISS:g}",
        ],
        handler_map={tuple: HandlerTuple(ndivide=None, pad=0.2)},
        loc="upper left",
        fontsize=8.3,
        handlelength=3.2,
        title="How to read the panels",
        title_fontproperties={"size": 8.8, "weight": "bold"},
        alignment="left",
    )
    guide.text(
        0.0,
        0.12,
        f"City-level 95% intervals are about ±{np.median(halfwidths):.1f} points (at most ±{halfwidths.max():.1f}),\n"
        "so lines closer than about a point are not distinguished. Intervals are in levels.csv;\n"
        "the paired gaps at 0.45 and the threshold verdicts are in the README.",
        transform=guide.transAxes,
        fontsize=7.8,
        color=INK_2,
        va="bottom",
    )
    return fig


FIGURES: Final = {
    "figure1_threshold.png": figure1,
    "figure2_frontier.png": figure2,
    "overhead_fidelity_plane.png": plane,
    "sweeps.png": sweeps,
}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def render(directory: Path) -> list[Path]:
    """Every figure and figures.json, from the summaries in `directory`."""
    inputs = {name: _sha256((directory / name).read_bytes()) for name in INPUTS}
    images = {}
    for name, draw in FIGURES.items():
        fig = draw(directory)
        buffer = BytesIO()
        fig.savefig(buffer, format="png", dpi=160, metadata={"Software": "delegation-frontier-benchmark"})
        plt.close(fig)
        images[name] = buffer.getvalue()
    if {name: _sha256((directory / name).read_bytes()) for name in INPUTS} != inputs:
        raise RuntimeError("a summary changed while the figures were drawn")
    paths = []
    for name, data in images.items():
        (directory / name).write_bytes(data)
        paths.append(directory / name)
    manifest = {
        "figure_manifest_version": 1,
        "environment": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "matplotlib": matplotlib.__version__,
        },
        "input_sha256": inputs,
        "source_sha256_lf_normalized": {SOURCE: _sha256((ROOT / SOURCE).read_bytes().replace(b"\r\n", b"\n"))},
        "png_sha256": {name: _sha256(data) for name, data in images.items()},
    }
    path = directory / "figures.json"
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return [*paths, path]


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("directory", type=Path, nargs="?", default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    for path in render(args.directory):
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
