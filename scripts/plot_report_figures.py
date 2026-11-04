"""Generate report figures comparing the historical baseline with the optimized queries."""
import argparse
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from scripts.config import ROOT

SCALE_FACTORS = (1, 2, 4, 8)
NUM_QUERIES = 99
BASELINE_FILE = "results/pt_sf={sf}_full_combined_sf{sf}.txt"
OPTIMIZED_CSV = "results/overnight_scientific_benchmark.csv"
OPTIMIZED_COLUMN = "Warm_Median_2_5"

# Reference palette, light mode (the figures are printed): one fixed color per series
BASELINE_COLOR = "#2a78d6"
OPTIMIZED_COLOR = "#eb6834"
SURFACE = "#fcfcfb"
TEXT = "#0b0b0b"
TEXT_SECONDARY = "#52514e"
GRID = "#e4e3df"
NEUTRAL = "#a3a29c"


def load_baseline(path):
    """Return {query: seconds} from a power-test result file (one line per query, then Total)."""
    times = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line.lower().startswith("total"):
                break
            if line:
                times.append(float(line))
    if len(times) < NUM_QUERIES:
        raise ValueError(f"{path}: expected {NUM_QUERIES} query times, found {len(times)}")
    return {q: t for q, t in enumerate(times[:NUM_QUERIES], 1)}


def load_optimized(path, column=OPTIMIZED_COLUMN):
    """Return {(scale_factor, query): seconds} from the overnight benchmark CSV."""
    df = pd.read_csv(path)
    times = {(int(r.Scale_Factor), int(r.Query)): float(getattr(r, column)) for r in df.itertuples()}
    for sf in sorted({sf for sf, _ in times}):
        missing = [q for q in range(1, NUM_QUERIES + 1) if (sf, q) not in times]
        if missing:
            raise ValueError(f"{path}: SF{sf} is missing queries {missing}")
    return times


def style_axes(ax):
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=TEXT_SECONDARY, labelcolor=TEXT_SECONDARY, length=3)
    ax.grid(axis="y", which="major", color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    ax.xaxis.label.set_color(TEXT)
    ax.yaxis.label.set_color(TEXT)


def new_figure(width, height):
    fig, ax = plt.subplots(figsize=(width, height), facecolor=SURFACE)
    style_axes(ax)
    return fig, ax


def save(fig, out_dir, name):
    path = os.path.join(out_dir, name)
    fig.savefig(path, dpi=300, bbox_inches="tight", facecolor=SURFACE)
    plt.close(fig)
    return path


def scale_factor_axis(ax):
    ax.set_xscale("log", base=2)
    ax.set_xticks(SCALE_FACTORS)
    ax.set_xticklabels([f"SF{sf}" for sf in SCALE_FACTORS])
    ax.minorticks_off()
    ax.set_xlim(0.8, 11)
    ax.set_xlabel("Scale factor")


def plot_series_by_sf(ax, baseline, optimized, unit_label):
    """Two lines over the scale factors with values labelled at SF1 and SF8."""
    for values, color, name in ((baseline, BASELINE_COLOR, "Baseline (historical)"),
                                (optimized, OPTIMIZED_COLOR, "Optimized (final_combined)")):
        ax.plot(SCALE_FACTORS, values, color=color, linewidth=2, marker="o", markersize=6,
                markeredgecolor=SURFACE, markeredgewidth=1, label=name)
        for sf, value, ha, dx in ((SCALE_FACTORS[0], values[0], "right", -8), (SCALE_FACTORS[-1], values[-1], "left", 8)):
            ax.annotate(f"{value:,.2f} {unit_label}" if value < 10 else f"{value:,.0f} {unit_label}",
                        (sf, value), xytext=(dx, 0), textcoords="offset points",
                        ha=ha, va="center", fontsize=8, color=TEXT)
    ax.set_yscale("log")


def plot_total_runtime(baseline, optimized, out_dir):
    base_totals = [sum(baseline[sf].values()) for sf in SCALE_FACTORS]
    opt_totals = [sum(optimized[(sf, q)] for q in range(1, NUM_QUERIES + 1)) for sf in SCALE_FACTORS]
    fig, ax = new_figure(6.4, 4.0)
    ax.plot(SCALE_FACTORS, [base_totals[0] * sf for sf in SCALE_FACTORS], color=NEUTRAL,
            linewidth=1, linestyle="--", label="Linear scaling from baseline SF1")
    plot_series_by_sf(ax, base_totals, opt_totals, "s")
    scale_factor_axis(ax)
    ax.set_xlim(0.55, 16)
    ax.set_ylabel("Total runtime of 99 queries (s, log scale)")
    ax.legend(frameon=False, fontsize=8, labelcolor=TEXT, loc="upper left")
    return save(fig, out_dir, "total_runtime_vs_sf.png"), base_totals, opt_totals


def plot_query_times(baseline, optimized, sf, out_dir):
    order = sorted(baseline[sf], key=lambda q: baseline[sf][q], reverse=True)
    base = [baseline[sf][q] for q in order]
    opt = [optimized[(sf, q)] for q in order]
    x = range(len(order))
    fig, ax = new_figure(10.0, 4.2)
    ax.vlines(x, [min(b, o) for b, o in zip(base, opt)], [max(b, o) for b, o in zip(base, opt)],
              color=NEUTRAL, linewidth=0.8, zorder=1)
    for values, color, name in ((base, BASELINE_COLOR, "Baseline (historical)"),
                                (opt, OPTIMIZED_COLOR, "Optimized (final_combined)")):
        ax.scatter(x, values, s=16, color=color, edgecolors=SURFACE, linewidths=0.5, zorder=2, label=name)
    ax.set_yscale("log")
    ax.set_xticks(list(x))
    ax.set_xticklabels([f"Q{q}" for q in order], rotation=90, fontsize=5)
    ax.set_xlim(-1, len(order))
    ax.set_xlabel(f"Query, ordered by baseline runtime at SF{sf}")
    ax.set_ylabel("Runtime (s, log scale)")
    ax.set_title(f"SF{sf}", loc="left", fontsize=10, color=TEXT)
    ax.legend(frameon=False, fontsize=8, labelcolor=TEXT, loc="upper right")
    return save(fig, out_dir, f"query_times_sf{sf}.png")


def plot_highlight(baseline, optimized, query, out_dir):
    base = [baseline[sf][query] for sf in SCALE_FACTORS]
    opt = [optimized[(sf, query)] for sf in SCALE_FACTORS]
    fig, ax = new_figure(5.6, 3.6)
    plot_series_by_sf(ax, base, opt, "s")
    scale_factor_axis(ax)
    ax.set_xlim(0.55, 16)
    ax.set_ylabel(f"Q{query} runtime (s, log scale)")
    ax.legend(frameon=False, fontsize=8, labelcolor=TEXT, loc="upper left")
    return save(fig, out_dir, f"highlight_q{query}.png")


def main(args):
    out_dir = args.out if os.path.isabs(args.out) else os.path.join(ROOT, args.out)
    os.makedirs(out_dir, exist_ok=True)
    baseline = {sf: load_baseline(os.path.join(ROOT, BASELINE_FILE.format(sf=sf))) for sf in SCALE_FACTORS}
    optimized = load_optimized(os.path.join(ROOT, OPTIMIZED_CSV))

    path, base_totals, opt_totals = plot_total_runtime(baseline, optimized, out_dir)
    paths = [path] + [plot_query_times(baseline, optimized, sf, out_dir) for sf in SCALE_FACTORS]
    paths += [plot_highlight(baseline, optimized, q, out_dir) for q in (args.highlight or [21])]
    for sf, b, o in zip(SCALE_FACTORS, base_totals, opt_totals):
        print(f"SF{sf}: baseline {b:.1f} s, optimized {o:.1f} s ({b / o:.1f}x)")
    for p in paths:
        print(os.path.relpath(p, ROOT))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Plot baseline vs optimized runtimes for the report")
    parser.add_argument("--out", default="report", help="Output directory. Default is report/")
    parser.add_argument("--highlight", type=int, action="append", default=None,
                        help="Query to plot across scale factors; repeat for several. Default is 21")
    main(parser.parse_args())
