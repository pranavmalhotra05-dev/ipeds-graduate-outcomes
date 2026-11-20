"""Build the static charts used in README.md (docs/img/*.png).

Reads only the published CSVs in tableau_ready/ (suppressed display files and
aggregate summaries). Grayscale-safe: fills differ in lightness and carry
hatch patterns; every bar and line is labelled directly.

Run: python src/06_make_charts.py
"""
from pathlib import Path

import matplotlib
import matplotlib.ticker

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
TR = ROOT / "tableau_ready"
IMG = ROOT / "docs" / "img"
IMG.mkdir(parents=True, exist_ok=True)

INK = "#111111"
DARK = "#1a1a1a"
MID = "#8c8c8c"
LIGHT = "#d9d9d9"

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 11,
    "axes.edgecolor": INK,
    "axes.labelcolor": INK,
    "xtick.color": INK,
    "ytick.color": INK,
    "axes.spines.top": False,
    "axes.spines.right": False,
})

LEVELS = ["masters", "research_doctorate", "professional_doctorate", "other_doctorate", "all_masters_doctoral"]
LABELS = {
    "masters": "Master's",
    "research_doctorate": "Doctorate:\nresearch",
    "professional_doctorate": "Doctorate:\nprofessional",
    "other_doctorate": "Doctorate:\nother",
    "all_masters_doctoral": "All levels",
}


def pct(x):
    return f"{100 * x:.1f}%"


def chart_hidden_share(sup):
    """Share of program cells under 10 vs share of completions held in them, 2023, by level."""
    d = sup[(sup.year == 2023) & (sup.threshold == 10)].set_index("level_key").loc[LEVELS]
    fig, ax = plt.subplots(figsize=(9.5, 5.2), dpi=150)
    x = range(len(LEVELS))
    w = 0.38
    b1 = ax.bar([i - w / 2 for i in x], d.share_cells_primary_suppressed, w, color=DARK, edgecolor=INK,
                label="Share of program cells with fewer than 10 completions")
    b2 = ax.bar([i + w / 2 for i in x], d.share_completions_in_primary_suppressed, w, color=LIGHT, edgecolor=INK,
                hatch="///", label="Share of all completions held in those cells")
    for bars, col in ((b1, "share_cells_primary_suppressed"), (b2, "share_completions_in_primary_suppressed")):
        for bar, v in zip(bars, d[col]):
            ax.text(bar.get_x() + bar.get_width() / 2, v + 0.012, pct(v), ha="center", va="bottom", fontsize=10)
    ax.set_xticks(list(x))
    ax.set_xticklabels([f"{LABELS[k]}\nn = {int(d.loc[k, 'n_cells']):,}" for k in LEVELS])
    ax.set_ylim(0, 1.0)
    ax.set_yticks([0, .2, .4, .6, .8, 1.0])
    ax.set_yticklabels(["0%", "20%", "40%", "60%", "80%", "100%"])
    ax.set_ylabel("Share")
    ax.legend(loc="upper right", frameon=False, fontsize=9.5)
    fig.suptitle("Small program rows are common; the completions they hold vary by level",
                 x=0.01, ha="left", fontsize=13.5, fontweight="bold")
    ax.set_title(f"2023, threshold of 10 completions; n = {int(d.loc['all_masters_doctoral', 'n_cells']):,} "
                 "program rows (institution x 6-digit CIP x award level)", loc="left", fontsize=10.5)
    fig.text(0.01, 0.01, "Source: IPEDS Completions 2023 (final), first majors; counts of zero are included in the "
             "share under 10. See METHODS.md.", fontsize=8.5)
    fig.tight_layout(rect=(0, 0.03, 1, 0.97))
    fig.savefig(IMG / "share_hidden_by_level_2023.png")
    plt.close(fig)


def chart_thresholds(sup):
    """Sensitivity to the threshold: all levels and master's, 2023."""
    fig, axes = plt.subplots(1, 2, figsize=(10, 5), dpi=150, sharey=True)
    ths = [5, 10, 20]
    spec = [("masters", "Master's"), ("research_doctorate", "Research doctorate")]
    for ax, (lv, name) in zip(axes, spec):
        d = sup[(sup.year == 2023) & (sup.level_key == lv)].set_index("threshold").loc[ths]
        x = range(len(ths))
        w = 0.38
        b1 = ax.bar([i - w / 2 for i in x], d.share_cells_primary_suppressed, w, color=DARK, edgecolor=INK,
                    label="Share of program cells under the threshold")
        b2 = ax.bar([i + w / 2 for i in x], d.share_completions_in_primary_suppressed, w, color=LIGHT,
                    edgecolor=INK, hatch="///", label="Share of completions held in those cells")
        for bars, col in ((b1, "share_cells_primary_suppressed"), (b2, "share_completions_in_primary_suppressed")):
            for bar, v in zip(bars, d[col]):
                ax.text(bar.get_x() + bar.get_width() / 2, v + 0.012, f"{100 * v:.0f}%", ha="center",
                        va="bottom", fontsize=9.5)
        ax.set_xticks(list(x))
        ax.set_xticklabels([f"under {t}" for t in ths])
        ax.set_xlabel("Primary suppression threshold (completions)")
        ax.set_title(f"{name} (n = {int(d.n_cells.iloc[0]):,} rows)", loc="left", fontsize=11)
        ax.set_ylim(0, 1.05)
    axes[0].set_ylabel("Share")
    axes[0].set_yticks([0, .2, .4, .6, .8, 1.0])
    axes[0].set_yticklabels(["0%", "20%", "40%", "60%", "80%", "100%"])
    h, lab = axes[0].get_legend_handles_labels()
    fig.legend(h, lab, loc="lower center", bbox_to_anchor=(0.5, 0.035), ncol=2, frameon=False, fontsize=9.5)
    fig.suptitle("Threshold sensitivity: share of program rows vs share of completions hidden",
                 x=0.01, ha="left", fontsize=12.5, fontweight="bold")
    fig.text(0.01, 0.005, "2023, IPEDS first majors. Thresholds 5, 10 and 20 are all computed; the published files use 10.",
             fontsize=8.5)
    fig.tight_layout(rect=(0, 0.11, 1, 0.97))
    fig.savefig(IMG / "threshold_sensitivity_2023.png")
    plt.close(fig)


def chart_national(nat):
    """National completions by level 2020-2023 (indexed to 2020 = 100 so the small levels are visible)."""
    d = nat[nat.level_key != "all_masters_doctoral"]
    piv = d.pivot(index="year", columns="level_key", values="completions_total")
    fig, (axl, axr) = plt.subplots(1, 2, figsize=(10.5, 5), dpi=150, gridspec_kw={"width_ratios": [1, 1]})
    styles = {
        "masters": ("-", "o", DARK),
        "research_doctorate": ("--", "s", MID),
        "professional_doctorate": ("-.", "^", "#4d4d4d"),
        "other_doctorate": (":", "D", "#b3b3b3"),
    }
    names = {"masters": "Master's", "research_doctorate": "Doctorate: research",
             "professional_doctorate": "Doctorate: professional", "other_doctorate": "Doctorate: other"}
    for lv, (ls, mk, col) in styles.items():
        axl.plot(piv.index, piv[lv] / 1000, ls=ls, marker=mk, color=col, lw=2, ms=6, mec=INK)
        axl.text(2023.08, piv.loc[2023, lv] / 1000, f"{names[lv]}  {piv.loc[2023, lv]:,.0f}", va="center", fontsize=8.5)
        idx = piv[lv] / piv.loc[2020, lv] * 100
        axr.plot(piv.index, idx, ls=ls, marker=mk, color=col, lw=2, ms=6, mec=INK)
        axr.text(2023.08, idx.loc[2023] + (-0.6 if lv == "other_doctorate" else 0), f"{idx.loc[2023]:.1f}", va="center", fontsize=8.5)
    axl.set_xlim(2019.8, 2025.2)
    axl.set_xticks([2020, 2021, 2022, 2023])
    axl.set_ylabel("Completions (thousands)")
    axl.set_title("Completions", loc="left", fontsize=11)
    axl.set_yscale("log")
    axl.set_yticks([2, 5, 10, 20, 50, 100, 200, 500, 1000])
    axl.get_yaxis().set_major_formatter(matplotlib.ticker.ScalarFormatter())
    axr.set_xlim(2019.8, 2024.1)
    axr.set_xticks([2020, 2021, 2022, 2023])
    axr.set_ylabel("Index (2020 = 100)")
    axr.set_title("Change relative to 2020", loc="left", fontsize=11)
    axr.axhline(100, color=INK, lw=0.6)
    for ax in (axl, axr):
        ax.set_xlabel("IPEDS file year (2023 = academic year 2022-23)")
    tot = nat[nat.level_key == "all_masters_doctoral"].set_index("year").completions_total
    fig.suptitle("National master's and doctoral completions by level, 2020-2023",
                 x=0.01, ha="left", fontsize=13.5, fontweight="bold")
    fig.text(0.01, 0.01, f"n = {int(tot.loc[2023]):,} completions in 2023 ({int(tot.loc[2020]):,} in 2020), first majors, "
             "all U.S. institutions reporting to IPEDS. Left panel uses a log scale.", fontsize=8.5)
    fig.tight_layout(rect=(0, 0.03, 1, 0.97))
    fig.savefig(IMG / "national_completions_2020_2023.png")
    plt.close(fig)


def main():
    sup = pd.read_csv(TR / "suppression_impact.csv")
    nat = pd.read_csv(TR / "national_totals.csv")
    chart_hidden_share(sup)
    chart_thresholds(sup)
    chart_national(nat)
    for p in sorted(IMG.glob("*.png")):
        print("wrote", p.relative_to(ROOT), p.stat().st_size // 1024, "KB")


if __name__ == "__main__":
    main()
