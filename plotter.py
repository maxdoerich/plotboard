"""
plotter.py — Build a publication-quality matplotlib Figure from a tidy DataFrame.

The DataFrame must have columns: condition, treatment, replicate, value
(as produced by parser.parse_sheet).
"""

from __future__ import annotations

import re

import matplotlib
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
import seaborn as sns

matplotlib.rcParams["pdf.fonttype"] = 42   # editable text in PDF/Illustrator
matplotlib.rcParams["svg.fonttype"] = "none"

_DEFAULTS = dict(
    title_fs=14,
    axis_label_fs=12,
    tick_fs=10,
    legend_fs=10,
    legend_title_fs=11,
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def make_figure(
    df: pd.DataFrame,
    *,
    # Plot type
    plot_type: str = "bar",          # "bar" | "box" | "violin"
    error_bar: str = "sd",           # "sd" | "sem" | "ci95"  (bar only)
    cap_size: float = 0.08,
    show_points: bool = True,
    point_size: float = 4.0,
    point_alpha: float = 0.7,
    # Scale / grid
    log_scale: bool = False,
    show_grid: bool = False,
    # Colors / style
    palette: list[str],
    bar_edge_width: float = 0.6,
    bar_edge_color: str = "black",
    bar_alpha: float = 1.0,
    bar_gap: float = 0.0,
    # Labels
    title: str = "",
    xlabel: str = "Condition",
    ylabel: str = "Value",
    legend_title: str = "Treatment",
    show_legend: bool = True,
    legend_inside: bool = False,
    # Figure size
    fig_width: float = 10.0,
    fig_height: float = 6.0,
    # Typography
    font_family: str = "sans-serif",
    font_scale: float = 1.0,          # global scale (used when fontsizes is empty)
    fontsizes: dict | None = None,    # per-element: keys title/axis_label/tick/legend
    # Axes
    tick_rotation: float = 40.0,
    tick_fontsize: float | None = None,   # None → use fontsizes / font_scale
    spines: str = "open",             # "open" | "all" | "none"
    spine_width: float = 1.0,
    y_format: str = "auto",           # "auto" | "plain" | "sci" | "SI"
    ylim: tuple | None = None,        # (min, max), either may be None
    xlim: tuple | None = None,
    # Line plot
    x_numeric: bool = False,       # True → proportional x spacing from numeric condition labels
    x_tick_interval: float = 0.0,  # 0 = auto; >0 → MultipleLocator(x_tick_interval)
    y_tick_interval: float = 0.0,  # 0 = auto; >0 → MultipleLocator(y_tick_interval)
    error_style: str = "band",     # "band" | "bars"
    line_width: float = 1.5,
    marker_style: str = "o",
    marker_size: float = 6.0,
    x_suffix: str = "",            # appended to tick labels when conditions are purely numeric
    trendline: str = "none",       # "none"|"smooth"|"linear"|"poly2"|"poly3"|"exp"|"log"|"power"|"spline"
    trendline_source: str = "means",  # "means" | "replicates"
    trendline_mode: str = "overlay",  # "overlay" | "replace"
    # Ticks
    tick_direction: str = "out",      # "in" | "out" | "inout"
    major_tick_length: float = 4.0,
    major_tick_width: float = 0.8,
    minor_ticks_y: int = 0,           # 0 = off, N = N minor ticks per major interval
    minor_ticks_x: int = 0,           # only applied for line plot with numeric x
    minor_tick_length: float = 2.0,
    minor_tick_width: float = 0.6,
    # Stats
    stat_results: pd.DataFrame | None = None,
    show_ns: bool = False,
    test_mode: str = "ttest",
    compare_axis: str = "conditions",
    bracket_linewidth: float = 0.9,
    bracket_fontsize: float = 11.0,
    show_pvalue: bool = False,
    show_significance: bool = True,
    show_fold_change: bool = False,
) -> matplotlib.figure.Figure:
    """
    Render *df* as a grouped bar / box / violin plot with optional
    overlaid individual data points and significance annotations.
    Returns the Figure (not shown or saved — caller decides what to do).
    """
    if df.empty:
        fig, ax = plt.subplots(figsize=(fig_width, fig_height))
        ax.text(0.5, 0.5, "No data to display", ha="center", va="center",
                transform=ax.transAxes, fontsize=14, color="gray")
        return fig

    # ------------------------------------------------------------------
    # Typography setup
    # ------------------------------------------------------------------
    matplotlib.rcParams["font.family"] = font_family

    fs = dict(_DEFAULTS)  # start from defaults
    if fontsizes:
        if "title"       in fontsizes: fs["title_fs"]       = fontsizes["title"]
        if "axis_label"  in fontsizes: fs["axis_label_fs"]  = fontsizes["axis_label"]
        if "tick"        in fontsizes: fs["tick_fs"]        = fontsizes["tick"]
        if "legend"      in fontsizes: fs["legend_fs"]      = fontsizes["legend"]
        if "legend"      in fontsizes: fs["legend_title_fs"] = fontsizes["legend"] + 1
        sns.set_theme(style="white", font_scale=1.0)
    else:
        sns.set_theme(style="white", font_scale=font_scale)
        # scale the defaults too so they're consistent
        for k in fs:
            fs[k] = fs[k] * font_scale

    _tick_fs = tick_fontsize if tick_fontsize is not None else fs["tick_fs"]

    # ------------------------------------------------------------------
    # Ordering
    # ------------------------------------------------------------------
    conditions = list(df["condition"].cat.categories) if hasattr(df["condition"], "cat") else list(df["condition"].unique())
    treatments = list(df["treatment"].cat.categories) if hasattr(df["treatment"], "cat") else list(df["treatment"].unique())

    color_map = {t: palette[i % len(palette)] for i, t in enumerate(treatments)}

    if log_scale and df["value"].min() <= 0:
        df = df[df["value"] > 0].copy()
        if hasattr(df["condition"], "cat"):
            df["condition"] = df["condition"].cat.remove_unused_categories()
        if hasattr(df["treatment"], "cat"):
            df["treatment"] = df["treatment"].cat.remove_unused_categories()

    fig, ax = plt.subplots(figsize=(fig_width, fig_height))

    # ------------------------------------------------------------------
    # Grid (draw before bars so bars sit on top)
    # ------------------------------------------------------------------
    if show_grid:
        ax.yaxis.grid(True, color="lightgray", linewidth=0.5, zorder=0)
        ax.set_axisbelow(True)

    # ------------------------------------------------------------------
    # Base layer
    # ------------------------------------------------------------------
    common_kw = dict(data=df, x="condition", y="value", hue="treatment",
                     hue_order=treatments, order=conditions,
                     palette=color_map, ax=ax)

    _elem_width = 0.8 * (1.0 - bar_gap)

    if plot_type == "bar":
        errorbar_arg = _errorbar_arg(error_bar)
        sns.barplot(
            **common_kw,
            errorbar=errorbar_arg,
            capsize=cap_size,
            edgecolor=bar_edge_color,
            linewidth=bar_edge_width,
            err_kws={"linewidth": 1.2},
            saturation=1.0,
        )
        # Post-draw: shrink bars symmetrically (bar centers fixed → strip/brackets stay aligned)
        if bar_gap > 0:
            for patch in ax.patches:
                if not isinstance(patch, mpatches.Rectangle):
                    continue
                w = patch.get_width()
                if w <= 0:
                    continue
                new_w = w * (1.0 - bar_gap)
                cx = patch.get_x() + w / 2
                patch.set_width(new_w)
                patch.set_x(cx - new_w / 2)
        # Apply alpha post-draw (seaborn doesn't accept alpha directly on barplot)
        if bar_alpha < 1.0:
            for patch in ax.patches:
                if isinstance(patch, mpatches.Rectangle) and patch.get_width() > 0:
                    patch.set_alpha(bar_alpha)
    elif plot_type == "box":
        sns.boxplot(
            **common_kw,
            linewidth=bar_edge_width,
            fliersize=0,
            width=_elem_width,
        )
    elif plot_type == "violin":
        sns.violinplot(
            **common_kw,
            inner=None,
            linewidth=bar_edge_width,
            width=_elem_width,
            cut=0,
        )
    elif plot_type == "line":
        # ---- Resolve x positions -----------------------------------------
        # Try to extract a leading numeric value from each condition label.
        # "1" → 1.0, "24" → 24.0, "1h" → 1.0, "100 nM" → 100.0
        # If all conditions yield a number AND x_numeric is requested, use
        # proportional spacing; otherwise fall back to 0,1,2,… (categorical).
        _NUM_RE = re.compile(r"^\s*([+-]?\d+(?:\.\d*)?(?:[eE][+-]?\d+)?)")

        def _try_numeric(s: str) -> float | None:
            m = _NUM_RE.match(str(s))
            return float(m.group(1)) if m else None

        _parsed = [_try_numeric(c) for c in conditions]
        _all_numeric = all(v is not None for v in _parsed)

        if x_numeric and _all_numeric:
            x_vals = [v for v in _parsed]      # type: ignore[misc]
            # Tick labels: use original condition string (already contains unit if present)
            # plus x_suffix only when the condition label is purely numeric (no letters)
            _tick_labels = [
                str(c) + (x_suffix if re.fullmatch(r"[+-]?\d+(?:\.\d*)?(?:[eE][+-]?\d+)?", str(c).strip()) else "")
                for c in conditions
            ]
        else:
            x_vals = list(range(len(conditions)))
            _tick_labels = [str(c) for c in conditions]

        # ---- One line per treatment ---------------------------------------
        for i, treatment in enumerate(treatments):
            color = palette[i % len(palette)]
            grp = df[df["treatment"] == treatment]
            means: list[float] = []
            errs: list[float] = []
            all_pts_x: list[float] = []
            all_pts_y: list[float] = []
            for j, cond in enumerate(conditions):
                vals = grp[grp["condition"] == cond]["value"].dropna().values
                n = len(vals)
                if n == 0:
                    means.append(float("nan"))
                    errs.append(float("nan"))
                    continue
                mean = float(np.mean(vals))
                means.append(mean)
                if n > 1:
                    sd = float(np.std(vals, ddof=1))
                    errs.append({"sd": sd,
                                 "sem": sd / np.sqrt(n),
                                 "ci95": 1.96 * sd / np.sqrt(n)}.get(error_bar, sd))
                else:
                    errs.append(float("nan"))
                # Collect replicate positions for trendline_source="replicates"
                all_pts_x.extend([x_vals[j]] * n)
                all_pts_y.extend(vals.tolist())

            m_arr = np.array(means)
            e_arr = np.array(errs)
            xv = np.array(x_vals)

            # Connected-means line (skipped in "replace" mode when trendline active)
            # Markers are always drawn so they remain visible even when the line is replaced.
            _draw_line = trendline == "none" or trendline_mode == "overlay"
            _marker = marker_style if marker_style != "none" else None
            if _draw_line:
                ax.plot(xv, m_arr, color=color, linewidth=line_width,
                        marker=_marker, markersize=marker_size, zorder=3)
            elif _marker:
                ax.plot(xv, m_arr, color=color, linewidth=0,
                        marker=_marker, markersize=marker_size, zorder=3)

            # Error band / bars
            valid = ~np.isnan(e_arr) & ~np.isnan(m_arr)
            if valid.any():
                if error_style == "band":
                    ax.fill_between(xv[valid], (m_arr - e_arr)[valid], (m_arr + e_arr)[valid],
                                    color=color, alpha=0.15, zorder=2)
                else:
                    ax.errorbar(xv[valid], m_arr[valid], yerr=e_arr[valid],
                                fmt="none", ecolor=color,
                                capsize=cap_size * 80, elinewidth=0.8, zorder=2)

            # Individual points
            if show_points:
                for j, cond in enumerate(conditions):
                    pts = grp[grp["condition"] == cond]["value"].dropna().values
                    ax.scatter([x_vals[j]] * len(pts), pts,
                               color=color, s=(point_size ** 2) * 0.5,
                               alpha=point_alpha, zorder=4, linewidths=0.3)

            # Trend line
            if trendline != "none":
                if trendline_source == "replicates" and len(all_pts_x) >= 2:
                    tx = np.array(all_pts_x, dtype=float)
                    ty = np.array(all_pts_y, dtype=float)
                else:
                    valid_m = ~np.isnan(m_arr)
                    tx = xv[valid_m]
                    ty = m_arr[valid_m]
                result = _fit_trend(tx, ty, trendline)
                if result is not None:
                    x_dense, y_dense = result
                    ax.plot(x_dense, y_dense, color=color,
                            linewidth=line_width + 0.5, linestyle="--",
                            zorder=5)

        # ---- X ticks -------------------------------------------------------
        if x_numeric and _all_numeric:
            # Continuous axis — let matplotlib auto-place major ticks so that:
            # - ticks appear at nice intervals across the full range (not just at data positions)
            # - default xlim rounds to nice numbers below/above the data range
            # Apply suffix (if any) via formatter on the auto-generated labels.
            if x_tick_interval and x_tick_interval > 0:
                ax.xaxis.set_major_locator(mticker.MultipleLocator(x_tick_interval))
            if x_suffix:
                ax.xaxis.set_major_formatter(
                    mticker.FuncFormatter(lambda v, _: f"{v:g}{x_suffix}")
                )
            ax.tick_params(axis="x", which="major", rotation=tick_rotation, labelsize=_tick_fs)
            if tick_rotation > 0:
                for lbl in ax.get_xticklabels():
                    lbl.set_ha("right")
        else:
            # Categorical spacing — force ticks at the data positions with their string labels
            ax.set_xticks(x_vals)
            ax.set_xticklabels(_tick_labels, rotation=tick_rotation,
                               fontsize=_tick_fs, ha="right" if tick_rotation > 0 else "center")

        # ---- Legend — filled rectangles (Patch), consistent with bar plots --
        if show_legend:
            leg_kw = (dict(loc="upper right", bbox_to_anchor=(0.98, 0.98), borderaxespad=0)
                      if legend_inside else
                      dict(loc="upper left", bbox_to_anchor=(1.02, 1), borderaxespad=0))
            _patch_handles = [
                mpatches.Patch(facecolor=palette[i % len(palette)], label=t)
                for i, t in enumerate(treatments)
            ]
            ax.legend(_patch_handles, treatments, title=legend_title, frameon=False,
                      fontsize=fs["legend_fs"], title_fontsize=fs["legend_title_fs"],
                      **leg_kw)
        else:
            ax.legend_.remove() if ax.get_legend() else None

        # ---- Axes styling --------------------------------------------------
        if log_scale:
            ax.set_yscale("log")
        ax.set_title(title, fontsize=fs["title_fs"], pad=10)
        ax.set_xlabel(xlabel, fontsize=fs["axis_label_fs"], labelpad=6)
        ax.set_ylabel(ylabel, fontsize=fs["axis_label_fs"], labelpad=6)
        if spines == "open":
            sns.despine(ax=ax, top=True, right=True)
        elif spines == "none":
            sns.despine(ax=ax, top=True, right=True, left=True, bottom=True)
            ax.tick_params(left=False, bottom=False)
        else:
            sns.despine(ax=ax, top=False, right=False)
        for spine in ax.spines.values():
            spine.set_linewidth(spine_width)
        _apply_y_format(ax, y_format)
        if y_tick_interval and y_tick_interval > 0:
            _safe_set_y_locator(ax, y_tick_interval)

        # ---- Tick marks — after despine; explicitly enable bottom/left -----
        ax.tick_params(axis="x", which="major", labelsize=_tick_fs,
                       direction=tick_direction, length=major_tick_length, width=major_tick_width,
                       bottom=True)
        ax.tick_params(axis="y", which="major", labelsize=_tick_fs,
                       direction=tick_direction, length=major_tick_length, width=major_tick_width,
                       left=True)
        if minor_ticks_y > 0:
            ax.yaxis.set_minor_locator(mticker.AutoMinorLocator(minor_ticks_y + 1))
            ax.tick_params(axis="y", which="minor", direction=tick_direction,
                           length=minor_tick_length, width=minor_tick_width, left=True)
        if minor_ticks_x > 0 and x_numeric and _all_numeric:
            ax.xaxis.set_minor_locator(mticker.AutoMinorLocator(minor_ticks_x + 1))
            ax.tick_params(axis="x", which="minor", direction=tick_direction,
                           length=minor_tick_length, width=minor_tick_width, bottom=True)

        fig.tight_layout()
        if ylim is not None:
            lo, hi = ylim
            cur_lo, cur_hi = ax.get_ylim()
            ax.set_ylim(lo if lo is not None else cur_lo,
                        hi if hi is not None else cur_hi)
        if xlim is not None:
            lo, hi = xlim
            cur_lo, cur_hi = ax.get_xlim()
            ax.set_xlim(lo if lo is not None else cur_lo,
                        hi if hi is not None else cur_hi)
        return fig

    else:
        raise ValueError(f"Unknown plot_type: {plot_type!r}")

    # ------------------------------------------------------------------
    # Strip overlay
    # ------------------------------------------------------------------
    if show_points:
        sns.stripplot(
            data=df,
            x="condition",
            y="value",
            hue="treatment",
            hue_order=treatments,
            order=conditions,
            dodge=True,
            jitter=True,
            marker="o",
            size=point_size,
            palette="dark:black",
            alpha=point_alpha,
            linewidth=0.5,
            ax=ax,
        )

    # ------------------------------------------------------------------
    # Legend
    # ------------------------------------------------------------------
    handles, labels_leg = ax.get_legend_handles_labels()
    n_t = len(treatments)
    if show_legend:
        if legend_inside:
            leg_kw = dict(loc="upper right", bbox_to_anchor=(0.98, 0.98),
                          borderaxespad=0)
        else:
            leg_kw = dict(loc="upper left", bbox_to_anchor=(1.02, 1),
                          borderaxespad=0)
        ax.legend(
            handles[:n_t], labels_leg[:n_t],
            title=legend_title,
            frameon=False,
            fontsize=fs["legend_fs"],
            title_fontsize=fs["legend_title_fs"],
            **leg_kw,
        )
    else:
        ax.legend_.remove() if ax.get_legend() else None

    # ------------------------------------------------------------------
    # Axes styling
    # ------------------------------------------------------------------
    if log_scale:
        ax.set_yscale("log")

    ax.set_title(title, fontsize=fs["title_fs"], pad=10)
    ax.set_xlabel(xlabel, fontsize=fs["axis_label_fs"], labelpad=6)
    ax.set_ylabel(ylabel, fontsize=fs["axis_label_fs"], labelpad=6)
    # Spines
    if spines == "open":
        sns.despine(ax=ax, top=True, right=True)
    elif spines == "none":
        sns.despine(ax=ax, top=True, right=True, left=True, bottom=True)
        ax.tick_params(left=False, bottom=False)
    else:  # "all" — full box
        sns.despine(ax=ax, top=False, right=False)

    for spine in ax.spines.values():
        spine.set_linewidth(spine_width)

    # Y-axis number format
    _apply_y_format(ax, y_format)

    if y_tick_interval and y_tick_interval > 0:
        _safe_set_y_locator(ax, y_tick_interval)

    # Tick marks — after despine; explicitly enable bottom/left so seaborn's
    # "white" style (which sets xtick.bottom/ytick.left=False) doesn't hide them.
    ax.tick_params(axis="x", which="major", rotation=tick_rotation, labelsize=_tick_fs,
                   direction=tick_direction, length=major_tick_length, width=major_tick_width,
                   bottom=True)
    ax.tick_params(axis="y", which="major", labelsize=_tick_fs,
                   direction=tick_direction, length=major_tick_length, width=major_tick_width,
                   left=True)
    if minor_ticks_y > 0:
        ax.yaxis.set_minor_locator(mticker.AutoMinorLocator(minor_ticks_y + 1))
        ax.tick_params(axis="y", which="minor", direction=tick_direction,
                       length=minor_tick_length, width=minor_tick_width, left=True)

    # ------------------------------------------------------------------
    # Statistical annotations
    # ------------------------------------------------------------------
    if stat_results is not None and not stat_results.empty:
        from stats import draw_significance_bars
        draw_significance_bars(
            ax=ax,
            df=df,
            stat_results=stat_results,
            show_ns=show_ns,
            test_mode=test_mode,
            compare_axis=compare_axis,
            log_scale=log_scale,
            bracket_linewidth=bracket_linewidth,
            bracket_fontsize=bracket_fontsize,
            show_pvalue=show_pvalue,
            show_significance=show_significance,
            show_fold_change=show_fold_change,
        )

    # ------------------------------------------------------------------
    # Axis limits — applied after tight_layout so it cannot re-expand them
    # ------------------------------------------------------------------
    fig.tight_layout()
    if ylim is not None:
        lo, hi = ylim
        cur_lo, cur_hi = ax.get_ylim()
        ax.set_ylim(lo if lo is not None else cur_lo,
                    hi if hi is not None else cur_hi)
    if xlim is not None:
        lo, hi = xlim
        cur_lo, cur_hi = ax.get_xlim()
        ax.set_xlim(lo if lo is not None else cur_lo,
                    hi if hi is not None else cur_hi)
    return fig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _errorbar_arg(error_bar: str):
    return {"sd": ("sd", 1), "sem": ("se", 1), "ci95": ("ci", 95)}.get(error_bar, ("sd", 1))


def _safe_set_y_locator(ax, interval: float, max_ticks: int = 100) -> None:
    """Apply MultipleLocator(interval) to the y-axis only if it produces a
    reasonable number of ticks.  Prevents matplotlib from hanging when the
    interval is small relative to the axis range (e.g. interval=1 on 0–50000)."""
    lo, hi = ax.get_ylim()
    if interval <= 0 or (hi - lo) / interval > max_ticks:
        return
    ax.yaxis.set_major_locator(mticker.MultipleLocator(interval))


def _fit_trend(
    x_fit: np.ndarray,
    y_fit: np.ndarray,
    kind: str,
) -> tuple[np.ndarray, np.ndarray] | None:
    """Return (x_dense, y_dense) for a smooth trend curve, or None on failure."""
    from scipy.interpolate import make_smoothing_spline

    if len(x_fit) < 2:
        return None
    try:
        x_dense = np.linspace(float(x_fit.min()), float(x_fit.max()), 200)
        if kind in ("linear", "poly2", "poly3"):
            deg = {"linear": 1, "poly2": 2, "poly3": 3}[kind]
            coeffs = np.polyfit(x_fit, y_fit, deg)
            y_dense = np.polyval(coeffs, x_dense)
        elif kind == "exp":
            if np.any(y_fit <= 0):
                return None
            coeffs = np.polyfit(x_fit, np.log(y_fit), 1)
            y_dense = np.exp(np.polyval(coeffs, x_dense))
        elif kind == "log":
            if np.any(x_fit <= 0):
                return None
            coeffs = np.polyfit(np.log(x_fit), y_fit, 1)
            y_dense = np.polyval(coeffs, np.log(x_dense))
        elif kind == "power":
            if np.any(x_fit <= 0) or np.any(y_fit <= 0):
                return None
            coeffs = np.polyfit(np.log(x_fit), np.log(y_fit), 1)
            y_dense = np.exp(np.polyval(coeffs, np.log(x_dense)))
        elif kind == "spline":
            spl = make_smoothing_spline(x_fit, y_fit)
            y_dense = spl(x_dense)
        elif kind == "smooth":
            from scipy.interpolate import CubicSpline
            # Sort by x and deduplicate (average y for identical x) before interpolating
            sort_idx = np.argsort(x_fit)
            xs, ys = x_fit[sort_idx], y_fit[sort_idx]
            unique_x, inv = np.unique(xs, return_inverse=True)
            unique_y = np.array([ys[inv == i].mean() for i in range(len(unique_x))])
            if len(unique_x) < 2:
                return None
            spl = CubicSpline(unique_x, unique_y)
            y_dense = spl(x_dense)
        else:
            return None
        return x_dense, y_dense
    except Exception:
        return None


def _apply_y_format(ax, y_format: str) -> None:
    if y_format == "plain":
        fmt = mticker.ScalarFormatter(useOffset=False)
        fmt.set_scientific(False)
        ax.yaxis.set_major_formatter(fmt)
    elif y_format == "sci":
        ax.ticklabel_format(style="sci", axis="y", scilimits=(0, 0))
    elif y_format == "SI":
        def _si(x, _):
            for thresh, suffix in [(1e9, "G"), (1e6, "M"), (1e3, "k")]:
                if abs(x) >= thresh:
                    return f"{x / thresh:.3g}{suffix}"
            return f"{x:.3g}"
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(_si))
    # "auto" → do nothing, matplotlib decides
