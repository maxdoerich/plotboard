"""
stats.py — Statistical tests and significance bar drawing for grouped plots.

Three test modes:
  "ttest"         — independent two-sample t-test, each condition vs. a chosen
                    reference, per treatment group.
  "tukey"         — one-way ANOVA per treatment group followed by Tukey's HSD
                    across all pairwise condition combinations.
  "two_way_anova" — two-way ANOVA (condition × treatment) followed by Sidak
                    post-hoc pairwise comparisons with correction applied across
                    all tests in the design.

Significance thresholds: *** p<0.001 | ** p<0.01 | * p<0.05 | ns
"""

from __future__ import annotations

import warnings

import matplotlib.axes
import numpy as np
import pandas as pd
from scipy import stats as scipy_stats


# ---------------------------------------------------------------------------
# p-value → stars
# ---------------------------------------------------------------------------

def pval_to_stars(p: float) -> str:
    if p < 0.001:
        return "***"
    if p < 0.01:
        return "**"
    if p < 0.05:
        return "*"
    return "ns"


# ---------------------------------------------------------------------------
# Statistical tests
# ---------------------------------------------------------------------------

def run_ttests_vs_reference(
    df: pd.DataFrame,
    reference_condition: str,
) -> pd.DataFrame:
    """
    For every (treatment, non-reference condition) pair, run an independent
    two-sample t-test against (treatment, reference_condition).

    Returns a DataFrame with columns:
        treatment, condition, reference, t_stat, p_value, stars
    """
    records = []
    ref_rows = df[df["condition"] == reference_condition]

    for treatment in df["treatment"].unique():
        ref_vals = (
            ref_rows[ref_rows["treatment"] == treatment]["value"]
            .dropna()
            .values
        )
        if len(ref_vals) < 2:
            continue

        for condition in df["condition"].unique():
            if condition == reference_condition:
                continue
            test_vals = (
                df[(df["condition"] == condition) & (df["treatment"] == treatment)]["value"]
                .dropna()
                .values
            )
            if len(test_vals) < 2:
                continue

            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                t_stat, p_value = scipy_stats.ttest_ind(ref_vals, test_vals)

            records.append(
                {
                    "treatment": str(treatment),
                    "condition": str(condition),
                    "reference": reference_condition,
                    "t_stat": round(float(t_stat), 4),
                    "p_value": float(p_value),
                    "stars": pval_to_stars(p_value),
                }
            )

    return pd.DataFrame(records) if records else pd.DataFrame(
        columns=["treatment", "condition", "reference", "t_stat", "p_value", "stars"]
    )


def run_tukey(df: pd.DataFrame) -> pd.DataFrame:
    """
    One-way ANOVA + Tukey HSD across conditions, per treatment group.
    compare_axis="conditions": for each treatment, compare all condition pairs.

    Returns a DataFrame with columns:
        treatment, group_A, group_B, p_value, stars, compare_axis
    """
    return _run_tukey_impl(df, between="condition", fixed_col="treatment")


def run_tukey_between_treatments(df: pd.DataFrame) -> pd.DataFrame:
    """
    One-way ANOVA + Tukey HSD across treatments, per condition group.
    compare_axis="treatments": for each condition, compare all treatment pairs.

    Returns a DataFrame with columns:
        condition, group_A, group_B, p_value, stars, compare_axis
    """
    return _run_tukey_impl(df, between="treatment", fixed_col="condition")


def run_two_way_anova_sidak(
    df: pd.DataFrame,
    compare_axis: str = "conditions",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Two-way ANOVA (condition × treatment) + Sidak post-hoc pairwise comparisons.

    Post-hoc uses the ANOVA's own MSresidual as the pooled error term (matching
    Prism's behaviour), not individual per-pair variances:
        t = (mean_A - mean_B) / sqrt(MSresidual * (1/nA + 1/nB))
        p_raw  ~ t-distribution with df_residual degrees of freedom
        p_sidak = 1 - (1 - p_raw) ^ k   [applied across all k pairs at once]

    compare_axis="conditions" — condition pairs within each treatment (k = C(nC,2)*nT)
    compare_axis="treatments" — treatment pairs within each condition (k = C(nT,2)*nC)
    compare_axis="cells"      — all cell pairs regardless of row/column, matches
                                Prism "Compare cell means regardless of rows and columns"
                                (k = C(nC*nT, 2))

    Returns (anova_table, posthoc_df).
      anova_table — pingouin ANOVA DataFrame (Source, SS, DF, MS, F, p-unc, np2)
      posthoc_df  — columns depend on compare_axis; bracket drawing handles all three
    """
    import itertools

    try:
        import pingouin as pg
    except ImportError:
        raise ImportError(
            "pingouin is required for Two-way ANOVA. Install with: pip install pingouin"
        )

    sub = df[["condition", "treatment", "value"]].dropna().copy()
    sub["condition"] = sub["condition"].astype(str)
    sub["treatment"] = sub["treatment"].astype(str)

    if sub["condition"].nunique() < 2:
        raise ValueError("Two-way ANOVA requires at least 2 conditions.")
    if sub["treatment"].nunique() < 2:
        raise ValueError("Two-way ANOVA requires at least 2 treatments.")

    # --- Two-way ANOVA table ------------------------------------------------
    anova_table = pg.anova(
        data=sub, dv="value", between=["condition", "treatment"], ss_type=2
    )

    # Extract pooled error from ANOVA (Residual row)
    res_rows = anova_table[anova_table["Source"] == "Residual"]
    if res_rows.empty or float(res_rows.iloc[0]["MS"]) <= 0:
        raise ValueError("Could not extract valid MSresidual from the ANOVA table.")
    ms_res = float(res_rows.iloc[0]["MS"])
    df_res = float(res_rows.iloc[0]["DF"])

    def _pvalue(vals_a: np.ndarray, vals_b: np.ndarray) -> float | None:
        """t-test using ANOVA's pooled MSresidual as the error term."""
        if len(vals_a) < 1 or len(vals_b) < 1:
            return None
        se = np.sqrt(ms_res * (1.0 / len(vals_a) + 1.0 / len(vals_b)))
        if se == 0:
            return None
        t = (float(np.mean(vals_a)) - float(np.mean(vals_b))) / se
        return float(2.0 * scipy_stats.t.sf(abs(t), df=df_res))

    # --- Build raw pair list ------------------------------------------------
    records_raw: list[dict] = []

    if compare_axis == "conditions":
        all_conditions = list(sub["condition"].unique())
        for treatment in sub["treatment"].unique():
            grp = sub[sub["treatment"] == treatment]
            for cond_a, cond_b in itertools.combinations(all_conditions, 2):
                vals_a = grp[grp["condition"] == cond_a]["value"].values
                vals_b = grp[grp["condition"] == cond_b]["value"].values
                p = _pvalue(vals_a, vals_b)
                if p is not None:
                    records_raw.append({"treatment": str(treatment),
                                        "group_A": cond_a, "group_B": cond_b, "p_raw": p})
        fixed_key, axis_label = "treatment", "conditions"
        cols = ["treatment", "group_A", "group_B", "p_value", "stars", "compare_axis"]

    elif compare_axis == "treatments":
        all_treatments = list(sub["treatment"].unique())
        for condition in sub["condition"].unique():
            grp = sub[sub["condition"] == condition]
            for treat_a, treat_b in itertools.combinations(all_treatments, 2):
                vals_a = grp[grp["treatment"] == treat_a]["value"].values
                vals_b = grp[grp["treatment"] == treat_b]["value"].values
                p = _pvalue(vals_a, vals_b)
                if p is not None:
                    records_raw.append({"condition": str(condition),
                                        "group_A": treat_a, "group_B": treat_b, "p_raw": p})
        fixed_key, axis_label = "condition", "treatments"
        cols = ["condition", "group_A", "group_B", "p_value", "stars", "compare_axis"]

    else:  # "cells" — all cell means vs all, matches Prism's option
        all_conditions = list(sub["condition"].unique())
        all_treatments = list(sub["treatment"].unique())
        all_cells = list(itertools.product(all_conditions, all_treatments))
        for (cA, tA), (cB, tB) in itertools.combinations(all_cells, 2):
            vals_a = sub[(sub["condition"] == cA) & (sub["treatment"] == tA)]["value"].values
            vals_b = sub[(sub["condition"] == cB) & (sub["treatment"] == tB)]["value"].values
            p = _pvalue(vals_a, vals_b)
            if p is not None:
                records_raw.append({"cond_A": cA, "treat_A": tA,
                                    "cond_B": cB, "treat_B": tB, "p_raw": p})
        fixed_key, axis_label = None, "cells"
        cols = ["cond_A", "treat_A", "cond_B", "treat_B", "p_value", "stars", "compare_axis"]

    # --- Apply Sidak correction across all k pairs --------------------------
    k = len(records_raw)
    records = []
    for r in records_raw:
        p_sidak = min(1.0 - (1.0 - r["p_raw"]) ** k, 1.0)
        if axis_label == "cells":
            entry = {"cond_A": r["cond_A"], "treat_A": r["treat_A"],
                     "cond_B": r["cond_B"], "treat_B": r["treat_B"],
                     "p_value": p_sidak, "stars": pval_to_stars(p_sidak),
                     "compare_axis": "cells"}
        else:
            entry = {"group_A": r["group_A"], "group_B": r["group_B"],
                     "p_value": p_sidak, "stars": pval_to_stars(p_sidak),
                     "compare_axis": axis_label, fixed_key: r[fixed_key]}
        records.append(entry)

    posthoc_df = pd.DataFrame(records, columns=cols) if records else pd.DataFrame(columns=cols)
    return anova_table, posthoc_df


def _run_tukey_impl(df: pd.DataFrame, *, between: str, fixed_col: str) -> pd.DataFrame:
    try:
        import pingouin as pg
    except ImportError:
        raise ImportError(
            "pingouin is required for Tukey HSD. Install it with: pip install pingouin"
        )

    records = []
    for fixed_val in df[fixed_col].unique():
        sub = (
            df[df[fixed_col] == fixed_val][["condition", "treatment", "value"]]
            .dropna()
            .copy()
        )
        sub[between] = sub[between].astype(str)
        if sub[between].nunique() < 2:
            continue

        try:
            tukey = pg.pairwise_tukey(data=sub, dv="value", between=between)
        except Exception:
            continue

        for _, row in tukey.iterrows():
            records.append(
                {
                    fixed_col: str(fixed_val),
                    "group_A": row["A"],
                    "group_B": row["B"],
                    "p_value": float(row["p_tukey"]),
                    "stars": pval_to_stars(float(row["p_tukey"])),
                    "compare_axis": between + "s",   # "conditions" or "treatments"
                }
            )

    if not records:
        cols = [fixed_col, "group_A", "group_B", "p_value", "stars", "compare_axis"]
        return pd.DataFrame(columns=cols)
    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# Significance bar drawing
# ---------------------------------------------------------------------------

def draw_significance_bars(
    ax: matplotlib.axes.Axes,
    df: pd.DataFrame,
    stat_results: pd.DataFrame,
    *,
    show_ns: bool = True,
    test_mode: str = "ttest",
    compare_axis: str = "conditions",   # "conditions" | "treatments"
    log_scale: bool = False,
    bracket_linewidth: float = 0.9,
    bracket_fontsize: float = 11.0,
    show_pvalue: bool = False,
    show_significance: bool = True,
    show_fold_change: bool = False,
) -> None:
    """
    Draw horizontal significance brackets above the relevant bars on *ax*.

    compare_axis="conditions": brackets span bars of the same treatment across
        different condition groups (the default Tukey / t-test mode).
    compare_axis="treatments": brackets span bars of different treatments within
        the same condition group (between-treatment Tukey).
    compare_axis="cells": brackets span any two bars (two-way ANOVA all-cell
        comparison); x-positions are computed for each specific cell.

    Bracket x-positions use seaborn's dodge formula:
        x_center = condition_idx + (treatment_idx - (n_treatments-1)/2) * (0.8/n_treatments)
    """
    if stat_results.empty:
        return

    conditions = _ordered_unique(df["condition"])
    treatments = _ordered_unique(df["treatment"])
    n_treatments = len(treatments)
    dodge_width = 0.8 / n_treatments
    _ci = {c: i for i, c in enumerate(conditions)}
    _ti = {t: i for i, t in enumerate(treatments)}

    def bar_x(ci: int, ti: int) -> float:
        return ci + (ti - (n_treatments - 1) / 2.0) * dodge_width

    # Precompute per-cell means for fold change labels
    means_dict: dict[tuple[str, str], float] = {}
    if show_fold_change:
        for (cond, treat), grp in df.groupby(["condition", "treatment"], observed=True):
            vals = grp["value"].dropna().values
            if len(vals) > 0:
                means_dict[(str(cond), str(treat))] = float(np.mean(vals))

    # ---- Collect bracketing jobs ----------------------------------------
    jobs: list[dict] = []

    for _, row in stat_results.iterrows():
        stars = row["stars"]
        if stars == "ns" and not show_ns:
            continue

        if compare_axis == "cells":
            cond_a = str(row["cond_A"])
            cond_b = str(row["cond_B"])
            treat_a = str(row["treat_A"])
            treat_b = str(row["treat_B"])
            if cond_a not in _ci or cond_b not in _ci or treat_a not in _ti or treat_b not in _ti:
                continue
            x1 = bar_x(_ci[cond_a], _ti[treat_a])
            x2 = bar_x(_ci[cond_b], _ti[treat_b])
            k1 = f"{cond_a}|{treat_a}"
            k2 = f"{cond_b}|{treat_b}"
            pair_key = (min(k1, k2), max(k1, k2))
            group1 = (cond_a, treat_a)
            group2 = (cond_b, treat_b)

        elif compare_axis == "treatments":
            condition = str(row["condition"])
            if condition not in _ci:
                continue
            treat_a = str(row["group_A"])
            treat_b = str(row["group_B"])
            if treat_a not in _ti or treat_b not in _ti:
                continue
            x1 = bar_x(_ci[condition], _ti[treat_a])
            x2 = bar_x(_ci[condition], _ti[treat_b])
            pair_key = (condition, min(treat_a, treat_b), max(treat_a, treat_b))
            group1 = (condition, treat_a)
            group2 = (condition, treat_b)

        else:
            treatment = str(row["treatment"])
            if treatment not in _ti:
                continue
            t_idx = _ti[treatment]

            if "reference" in stat_results.columns:
                cond_a = str(row["reference"])
                cond_b = str(row["condition"])
            else:
                cond_a = str(row["group_A"])
                cond_b = str(row["group_B"])

            if cond_a not in _ci or cond_b not in _ci:
                continue

            x1 = bar_x(_ci[cond_a], t_idx)
            x2 = bar_x(_ci[cond_b], t_idx)
            pair_key = (treatment, min(cond_a, cond_b), max(cond_a, cond_b))
            group1 = (cond_a, treatment)
            group2 = (cond_b, treatment)

        jobs.append({
            "x1": x1, "x2": x2, "stars": stars,
            "p_value": float(row["p_value"]) if "p_value" in stat_results.columns else None,
            "pair_key": pair_key,
            "group1": group1,
            "group2": group2,
        })

    if not jobs:
        return

    # ---- Assign bracket heights without overlaps -----------------------
    # Sort by x-span width (widest brackets go highest, narrowest stay low).
    # Then use interval-greedy stacking: place each bracket at the lowest
    # available level whose rightmost x does not overlap the new bracket.
    y_lo, y_hi = ax.get_ylim()
    data_range = y_hi - y_lo if not log_scale else None
    margin = 0.05  # a little padding so adjacent brackets don't touch

    jobs_sorted = sorted(
        jobs, key=lambda j: abs(j["x2"] - j["x1"]), reverse=True
    )

    # level_right_x[i] = rightmost x used by any bracket already at level i
    level_right_x: list[float] = []
    # x1, x2, stars, p_value, level, group1, group2
    annotated: list[tuple[float, float, str, float | None, int, tuple, tuple]] = []

    for job in jobs_sorted:
        x_lo = min(job["x1"], job["x2"]) - margin
        x_hi = max(job["x1"], job["x2"]) + margin

        assigned = None
        for i, right_x in enumerate(level_right_x):
            if x_lo >= right_x:          # no overlap at this level
                level_right_x[i] = x_hi
                assigned = i
                break
        if assigned is None:
            assigned = len(level_right_x)
            level_right_x.append(x_hi)

        annotated.append((
            job["x1"], job["x2"], job["stars"], job.get("p_value"), assigned,
            job.get("group1", ("", "")), job.get("group2", ("", "")),
        ))

    # Convert levels to y-coordinates
    def level_to_y(level: int) -> float:
        if log_scale:
            return y_hi * (1.08 ** (level + 1))
        return y_hi + data_range * 0.09 * (level + 1)

    # ---- Draw brackets -------------------------------------------------
    for x1, x2, stars, p_value, level, group1, group2 in annotated:
        y = level_to_y(level)
        if log_scale:
            tick_h = y * 0.025
        else:
            tick_h = data_range * 0.015

        ax.plot(
            [x1, x1, x2, x2],
            [y - tick_h, y, y, y - tick_h],
            color="black",
            linewidth=bracket_linewidth,
            clip_on=False,
        )

        # Build annotation label: fold change (top) and/or significance (bottom)
        parts: list[str] = []
        if show_fold_change:
            m1 = means_dict.get(group1)
            m2 = means_dict.get(group2)
            if m1 is not None and m2 is not None and min(m1, m2) > 0:
                fc = max(m1, m2) / min(m1, m2)
                parts.append(f"{fc:.1f}x")
        if show_significance:
            if show_pvalue and p_value is not None:
                parts.append(f"p={p_value:.3f}" if p_value >= 0.001 else "p<0.001")
            else:
                parts.append(stars)
        label = "\n".join(parts)

        if label:
            ax.text(
                (x1 + x2) / 2,
                y,
                label,
                ha="center",
                va="bottom",
                fontsize=bracket_fontsize,
                clip_on=False,
            )

    # ---- Expand y-axis to fit all brackets ----------------------------
    if annotated:
        max_level = max(a[4] for a in annotated)
        max_y = level_to_y(max_level)
        if log_scale:
            ax.set_ylim(top=max_y * 1.25)
        else:
            ax.set_ylim(top=max_y + data_range * 0.09 * 1.5)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ordered_unique(series: pd.Series) -> list[str]:
    """Return unique values in first-occurrence order, as strings."""
    if hasattr(series, "cat"):
        return [str(c) for c in series.cat.categories]
    seen: dict[str, None] = {}
    for v in series:
        seen[str(v)] = None
    return list(seen)
