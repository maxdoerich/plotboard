"""
plotter.py — Build a publication-quality matplotlib Figure from a tidy DataFrame.

The DataFrame must have columns: condition, treatment, replicate, value
(as produced by parser.parse_sheet).

Two entry points:

* ``make_figure(df, ...)``  — creates its own Figure and returns it.
* ``draw_plot(ax, df, ...)`` — draws into an axes you own, so a panel figure can
  compose several plots.  It does not create figures, call ``tight_layout`` or
  apply axis limits; the caller owns those.

Figures are built with ``matplotlib.figure.Figure`` rather than ``pyplot``.
pyplot keeps every figure it creates in a global registry until someone calls
``plt.close()``, which in a Streamlit app means a figure leaks on any path that
raises before the close — and it makes figure creation depend on global state
shared between threads.  A plain ``Figure`` is freed by refcount like any other
object, which is also what lets the export buttons hold one until clicked.
"""

from __future__ import annotations

import re
import warnings
from contextlib import contextmanager
from functools import lru_cache

import matplotlib
import matplotlib.patches as mpatches
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
import seaborn as sns
from cycler import cycler
from matplotlib.figure import Figure

matplotlib.rcParams["pdf.fonttype"] = 42   # editable text in PDF/Illustrator
matplotlib.rcParams["svg.fonttype"] = "none"

_DEFAULTS = dict(
    title_fs=14,
    axis_label_fs=12,
    tick_fs=10,
    legend_fs=10,
    legend_title_fs=11,
)

# Leading number in a condition label: "24" → 24, "1h" → 1, "100 nM" → 100.
_LEADING_NUMBER_RE = re.compile(r"^\s*([+-]?\d+(?:\.\d*)?(?:[eE][+-]?\d+)?)")
_PURE_NUMBER_RE = re.compile(r"[+-]?\d+(?:\.\d*)?(?:[eE][+-]?\d+)?")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def make_figure(
    df: pd.DataFrame,
    *,
    fig_width: float = 10.0,
    fig_height: float = 6.0,
    ylim: tuple | None = None,
    xlim: tuple | None = None,
    **kwargs,
) -> Figure:
    """
    Create a Figure with a single Axes, draw the plot on it, and return the Figure.

    Thin wrapper around `draw_plot`: owns figure creation, tight_layout, and
    final axis-limit application. All other plotting kwargs are forwarded.
    """
    # The axes must be created *inside* the style context, not just drawn into
    # it: matplotlib reads rcParams when it builds the axes and its ticks, so
    # creating them first would leave them styled with matplotlib's defaults
    # and only the artists drawn afterwards styled with the theme.
    with plot_style(_theme_scale(kwargs), kwargs.get("font_family", "sans-serif")):
        fig = Figure(figsize=(fig_width, fig_height))
        ax = fig.add_subplot(111)
        draw_plot(ax, df, **kwargs)
        # matplotlib reports a failed layout as a warning on stderr, where the
        # user never sees it. Capture it so the app can say what to do about
        # it: it means the figure is too small for its decorations, which is
        # easy to hit at journal widths with the legend outside the axes.
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            fig.tight_layout()
        fig.layout_warning = any(
            "tight layout" in str(w.message).lower() for w in caught)
    _apply_axis_limits(ax, ylim=ylim, xlim=xlim)
    return fig


@contextmanager
def plot_style(font_scale: float = 1.0, font_family: str = "sans-serif"):
    """Apply the seaborn "white" theme for the duration of the block.

    ``sns.set_theme()`` writes into the global rcParams and never puts them
    back, so one plot's typography leaked into the next panel and into the next
    rerun.  Scoping the same values keeps each figure's styling to itself.
    """
    with matplotlib.rc_context(_theme_rc(font_scale, font_family)):
        yield


def _theme_scale(kwargs: dict) -> float:
    """Theme font scale: per-element sizing pins the theme at 1.0."""
    return 1.0 if kwargs.get("fontsizes") else float(kwargs.get("font_scale", 1.0))


def parse_leading_number(label: object) -> float | None:
    """Numeric prefix of a condition label, or None when there isn't one."""
    match = _LEADING_NUMBER_RE.match(str(label))
    return float(match.group(1)) if match else None


def x_axis_is_numeric(conditions, mode: object = "auto") -> bool:
    """Whether a line plot should space its x-axis by the conditions' values.

    ``mode`` is "auto" (use numeric spacing when every label starts with a
    number), "numeric" (same, requested explicitly), or "categorical" (never).
    Booleans from presets saved before the three-way control are accepted:
    True behaved like "numeric", False like "categorical".
    """
    if mode is False or mode == "categorical":
        return False
    return all(parse_leading_number(c) is not None for c in conditions)


def draw_plot(
    ax: matplotlib.axes.Axes,
    df: pd.DataFrame,
    *,
    # Plot type
    plot_type: str = "bar",          # "bar" | "box" | "violin" | "line"
    error_bar: str = "sd",           # "sd" | "sem" | "ci95"  (bar/line only)
    cap_size: float = 0.08,
    show_points: bool = True,
    point_size: float = 4.0,
    point_alpha: float = 0.7,
    point_colors: list[str] | None = None,  # per treatment; None = default
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
    # Line plot
    x_numeric: object = "auto",    # "auto" | "numeric" | "categorical"
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
    sigmoids: list[tuple[float, float, float, float, str]] = (),  # (A_low, A_high, P50, dP, color)
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
    show_ns: bool = True,
    test_mode: str = "ttest",
    compare_axis: str = "conditions",
    bracket_linewidth: float = 0.9,
    bracket_fontsize: float = 11.0,
    show_pvalue: bool = False,
    show_significance: bool = True,
    show_fold_change: bool = False,
) -> None:
    """
    Render *df* as a grouped bar / box / violin / line plot on *ax*.

    Does NOT create a figure, call tight_layout, or apply axis limits — the
    caller owns those (so panel mode can compose multiple plots into one
    figure). Use `make_figure` for the single-plot convenience wrapper.
    """
    fs = dict(_DEFAULTS)
    if fontsizes:
        fs["title_fs"] = fontsizes.get("title", fs["title_fs"])
        fs["axis_label_fs"] = fontsizes.get("axis_label", fs["axis_label_fs"])
        fs["tick_fs"] = fontsizes.get("tick", fs["tick_fs"])
        if "legend" in fontsizes:
            fs["legend_fs"] = fontsizes["legend"]
            fs["legend_title_fs"] = fontsizes["legend"] + 1
        theme_scale = 1.0
    else:
        theme_scale = font_scale
        # Scale the defaults too so they stay consistent with the theme.
        for key in fs:
            fs[key] = fs[key] * font_scale

    tick_fs = tick_fontsize if tick_fontsize is not None else fs["tick_fs"]

    # Style is applied for the duration of the draw only.  seaborn's set_theme
    # mutates the global rcParams, which leaks between panels of one figure and
    # between reruns; scoping it keeps each axes' styling to itself.
    with plot_style(theme_scale, font_family):
        family = _concrete_family(font_family)
        if df.empty:
            ax.text(0.5, 0.5, "No data to display", ha="center", va="center",
                    transform=ax.transAxes, fontsize=14, color="gray")
            _freeze_fonts(ax, family)
            return
        _draw(
            ax, df, font_family=family,
            plot_type=plot_type, error_bar=error_bar, cap_size=cap_size,
            show_points=show_points, point_size=point_size, point_alpha=point_alpha,
            point_colors=point_colors, log_scale=log_scale, show_grid=show_grid, palette=palette,
            bar_edge_width=bar_edge_width, bar_edge_color=bar_edge_color,
            bar_alpha=bar_alpha, bar_gap=bar_gap, title=title, xlabel=xlabel,
            ylabel=ylabel, legend_title=legend_title, show_legend=show_legend,
            legend_inside=legend_inside, fs=fs, tick_rotation=tick_rotation,
            tick_fs=tick_fs, spines=spines, spine_width=spine_width,
            y_format=y_format, x_numeric=x_numeric, x_tick_interval=x_tick_interval,
            y_tick_interval=y_tick_interval, error_style=error_style,
            line_width=line_width, marker_style=marker_style, marker_size=marker_size,
            x_suffix=x_suffix, trendline=trendline, trendline_source=trendline_source,
            trendline_mode=trendline_mode, sigmoids=sigmoids,
            tick_direction=tick_direction,
            major_tick_length=major_tick_length, major_tick_width=major_tick_width,
            minor_ticks_y=minor_ticks_y, minor_ticks_x=minor_ticks_x,
            minor_tick_length=minor_tick_length, minor_tick_width=minor_tick_width,
            stat_results=stat_results, show_ns=show_ns, test_mode=test_mode,
            compare_axis=compare_axis, bracket_linewidth=bracket_linewidth,
            bracket_fontsize=bracket_fontsize, show_pvalue=show_pvalue,
            show_significance=show_significance, show_fold_change=show_fold_change,
        )


# ---------------------------------------------------------------------------
# Drawing
# ---------------------------------------------------------------------------

def _draw(
    ax, df, *, font_family, plot_type, error_bar, cap_size, show_points, point_size,
    point_alpha, point_colors, log_scale, show_grid, palette, bar_edge_width, bar_edge_color,
    bar_alpha, bar_gap, title, xlabel, ylabel, legend_title, show_legend,
    legend_inside, fs, tick_rotation, tick_fs, spines, spine_width, y_format,
    x_numeric, x_tick_interval, y_tick_interval, error_style, line_width,
    marker_style, marker_size, x_suffix, trendline, trendline_source,
    trendline_mode, sigmoids, tick_direction, major_tick_length, major_tick_width,
    minor_ticks_y, minor_ticks_x, minor_tick_length, minor_tick_width,
    stat_results, show_ns, test_mode, compare_axis, bracket_linewidth,
    bracket_fontsize, show_pvalue, show_significance, show_fold_change,
) -> None:
    conditions = _categories(df["condition"])
    treatments = _categories(df["treatment"])
    color_map = {t: palette[i % len(palette)] for i, t in enumerate(treatments)}

    if log_scale and df["value"].min() <= 0:
        df = df[df["value"] > 0].copy()
        for col in ("condition", "treatment"):
            if hasattr(df[col], "cat"):
                df[col] = df[col].cat.remove_unused_categories()
        conditions = _categories(df["condition"])
        treatments = _categories(df["treatment"])

    # Grid is drawn before the data so bars sit on top of it.
    if show_grid:
        ax.yaxis.grid(True, color="lightgray", linewidth=0.5, zorder=0)
        ax.set_axisbelow(True)

    style_kw = dict(
        title=title, xlabel=xlabel, ylabel=ylabel, fs=fs, spines=spines,
        font_family=font_family,
        spine_width=spine_width, y_format=y_format,
        y_tick_interval=y_tick_interval, tick_fs=tick_fs,
        tick_direction=tick_direction, major_tick_length=major_tick_length,
        major_tick_width=major_tick_width, minor_ticks_y=minor_ticks_y,
        minor_tick_length=minor_tick_length, minor_tick_width=minor_tick_width,
        log_scale=log_scale,
    )

    if plot_type == "line":
        _draw_line(
            ax, df, conditions=conditions, treatments=treatments, palette=palette,
            error_bar=error_bar, cap_size=cap_size, show_points=show_points,
            point_size=point_size, point_alpha=point_alpha, point_colors=point_colors,
            error_style=error_style, line_width=line_width, marker_style=marker_style, marker_size=marker_size,
            x_numeric=x_numeric, x_suffix=x_suffix, x_tick_interval=x_tick_interval,
            tick_rotation=tick_rotation, tick_fs=tick_fs, trendline=trendline,
            trendline_source=trendline_source, trendline_mode=trendline_mode,
            sigmoids=sigmoids,
        )
        _draw_legend(ax, treatments, palette=palette, legend_title=legend_title,
                     show_legend=show_legend, legend_inside=legend_inside, fs=fs,
                     use_patches=True)
        _style_axes(ax, rotate_x=False, **style_kw)
        if minor_ticks_x > 0 and x_axis_is_numeric(conditions, x_numeric):
            ax.xaxis.set_minor_locator(mticker.AutoMinorLocator(minor_ticks_x + 1))
            ax.tick_params(axis="x", which="minor", direction=tick_direction,
                           length=minor_tick_length, width=minor_tick_width,
                           bottom=True)
        _freeze_fonts(ax, font_family)
        return

    _draw_categorical(
        ax, df, plot_type=plot_type, conditions=conditions, treatments=treatments,
        color_map=color_map, error_bar=error_bar, cap_size=cap_size,
        bar_edge_width=bar_edge_width, bar_edge_color=bar_edge_color,
        bar_alpha=bar_alpha, bar_gap=bar_gap,
    )

    if show_points:
        sns.stripplot(
            data=df, x="condition", y="value", hue="treatment",
            hue_order=treatments, order=conditions,
            dodge=True, jitter=True, marker="o", size=point_size,
            palette=(dict(zip(treatments, point_colors)) if point_colors
                     else "dark:black"),
            alpha=point_alpha, linewidth=0.5, ax=ax,
        )

    _draw_legend(ax, treatments, palette=palette, legend_title=legend_title,
                 show_legend=show_legend, legend_inside=legend_inside, fs=fs,
                 use_patches=False)
    _style_axes(ax, rotate_x=True, tick_rotation=tick_rotation, **style_kw)

    if stat_results is not None and not stat_results.empty:
        from stats import draw_significance_bars
        draw_significance_bars(
            ax=ax, df=df, stat_results=stat_results, show_ns=show_ns,
            test_mode=test_mode, compare_axis=compare_axis, log_scale=log_scale,
            bracket_linewidth=bracket_linewidth, bracket_fontsize=bracket_fontsize,
            show_pvalue=show_pvalue, show_significance=show_significance,
            show_fold_change=show_fold_change,
        )

    _freeze_fonts(ax, font_family)


def _draw_categorical(
    ax, df, *, plot_type, conditions, treatments, color_map, error_bar,
    cap_size, bar_edge_width, bar_edge_color, bar_alpha, bar_gap,
) -> None:
    """Bar / box / violin base layer."""
    common_kw = dict(data=df, x="condition", y="value", hue="treatment",
                     hue_order=treatments, order=conditions,
                     palette=color_map, ax=ax)
    elem_width = 0.8 * (1.0 - bar_gap)

    if plot_type == "bar":
        sns.barplot(
            **common_kw,
            errorbar=_errorbar_arg(error_bar),
            capsize=cap_size,
            edgecolor=bar_edge_color,
            linewidth=bar_edge_width,
            err_kws={"linewidth": 1.2},
            saturation=1.0,
        )
        # Bar gap and alpha are applied post-draw by resizing the patches.
        # Passing width= to seaborn would move the bar *centres*, which
        # misaligns the strip dots and every significance bracket.
        if bar_gap > 0:
            for patch in ax.patches:
                if not isinstance(patch, mpatches.Rectangle):
                    continue
                width = patch.get_width()
                if width <= 0:
                    continue
                new_width = width * (1.0 - bar_gap)
                centre = patch.get_x() + width / 2
                patch.set_width(new_width)
                patch.set_x(centre - new_width / 2)
        if bar_alpha < 1.0:
            for patch in ax.patches:
                if isinstance(patch, mpatches.Rectangle) and patch.get_width() > 0:
                    patch.set_alpha(bar_alpha)
    elif plot_type == "box":
        sns.boxplot(**common_kw, linewidth=bar_edge_width, fliersize=0,
                    width=elem_width)
    elif plot_type == "violin":
        sns.violinplot(**common_kw, inner=None, linewidth=bar_edge_width,
                       width=elem_width, cut=0)
    else:
        raise ValueError(f"Unknown plot_type: {plot_type!r}")


def _draw_line(
    ax, df, *, conditions, treatments, palette, error_bar, cap_size, show_points,
    point_size, point_alpha, point_colors, error_style, line_width, marker_style,
    marker_size, x_numeric, x_suffix, x_tick_interval, tick_rotation, tick_fs, trendline,
    trendline_source, trendline_mode, sigmoids,
) -> None:
    """One line per treatment, conditions along x."""
    numeric_x = x_axis_is_numeric(conditions, x_numeric)

    if numeric_x:
        x_vals = [parse_leading_number(c) for c in conditions]
        # The label already carries its unit if it has one; x_suffix only
        # applies to labels that are a bare number.
        tick_labels = [
            str(c) + (x_suffix if _PURE_NUMBER_RE.fullmatch(str(c).strip()) else "")
            for c in conditions
        ]
    else:
        x_vals = list(range(len(conditions)))
        tick_labels = [str(c) for c in conditions]

    # One pass over the data instead of a filtered scan per (treatment,
    # condition) cell — the old version rebuilt two boolean masks per cell.
    cells: dict[tuple[str, str], np.ndarray] = {
        (str(cond), str(treat)): group["value"].dropna().to_numpy()
        for (cond, treat), group in df.groupby(["condition", "treatment"], observed=True)
    }
    empty = np.empty(0)

    for i, treatment in enumerate(treatments):
        color = palette[i % len(palette)]
        point_color = point_colors[i % len(point_colors)] if point_colors else color
        means: list[float] = []
        errs: list[float] = []
        all_pts_x: list[float] = []
        all_pts_y: list[float] = []

        for j, cond in enumerate(conditions):
            vals = cells.get((str(cond), str(treatment)), empty)
            n = len(vals)
            if n == 0:
                means.append(float("nan"))
                errs.append(float("nan"))
                continue
            means.append(float(np.mean(vals)))
            if n > 1:
                sd = float(np.std(vals, ddof=1))
                errs.append({"sd": sd,
                             "sem": sd / np.sqrt(n),
                             "ci95": 1.96 * sd / np.sqrt(n)}.get(error_bar, sd))
            else:
                errs.append(float("nan"))
            all_pts_x.extend([x_vals[j]] * n)
            all_pts_y.extend(vals.tolist())

        m_arr = np.array(means)
        e_arr = np.array(errs)
        xv = np.array(x_vals, dtype=float)

        # In "replace" mode the connecting line gives way to the trend line,
        # but the markers stay so the measurements remain visible.
        draw_line = trendline == "none" or trendline_mode == "overlay"
        marker = marker_style if marker_style != "none" else None
        if draw_line:
            ax.plot(xv, m_arr, color=color, linewidth=line_width,
                    marker=marker, markersize=marker_size, zorder=3)
        elif marker:
            ax.plot(xv, m_arr, color=color, linewidth=0,
                    marker=marker, markersize=marker_size, zorder=3)

        valid = ~np.isnan(e_arr) & ~np.isnan(m_arr)
        if valid.any():
            if error_style == "band":
                ax.fill_between(xv[valid], (m_arr - e_arr)[valid],
                                (m_arr + e_arr)[valid],
                                color=color, alpha=0.15, zorder=2)
            else:
                ax.errorbar(xv[valid], m_arr[valid], yerr=e_arr[valid],
                            fmt="none", ecolor=color, capsize=cap_size * 80,
                            elinewidth=0.8, zorder=2)

        if show_points:
            for j, cond in enumerate(conditions):
                pts = cells.get((str(cond), str(treatment)), empty)
                if len(pts):
                    ax.scatter([x_vals[j]] * len(pts), pts, color=point_color,
                               s=(point_size ** 2) * 0.5, alpha=point_alpha,
                               zorder=4, linewidths=0.3)

        if trendline != "none":
            if trendline_source == "replicates" and len(all_pts_x) >= 2:
                tx = np.array(all_pts_x, dtype=float)
                ty = np.array(all_pts_y, dtype=float)
            else:
                valid_means = ~np.isnan(m_arr)
                tx = xv[valid_means]
                ty = m_arr[valid_means]
            fitted = _fit_trend(tx, ty, trendline)
            if fitted is not None:
                x_dense, y_dense = fitted
                ax.plot(x_dense, y_dense, color=color, linewidth=line_width + 0.5,
                        linestyle="--", zorder=5)

    # A(P) = A_low + (A_high - A_low) / (1 + exp((P - P50) / dP)), over the x data range.
    if len(x_vals) > 1 and max(x_vals) > min(x_vals):
        xs = np.linspace(min(x_vals), max(x_vals), 300)
        for a_low, a_high, p50, dp, color in sigmoids:
            if dp == 0:
                continue
            with np.errstate(over="ignore"):  # exp overflow -> curve saturates at A_low
                ys = a_low + (a_high - a_low) / (1.0 + np.exp((xs - p50) / dp))
            ax.plot(xs, ys, color=color, linewidth=line_width + 0.5, zorder=6)

    if numeric_x:
        # Continuous axis: let matplotlib place ticks at nice intervals across
        # the whole range rather than only where data points happen to fall.
        if x_tick_interval and x_tick_interval > 0:
            ax.xaxis.set_major_locator(mticker.MultipleLocator(x_tick_interval))
        if x_suffix:
            ax.xaxis.set_major_formatter(
                mticker.FuncFormatter(lambda v, _: f"{v:g}{x_suffix}")
            )
        ax.tick_params(axis="x", which="major", rotation=tick_rotation,
                       labelsize=tick_fs)
        _anchor_x_labels(ax, tick_rotation)
    else:
        ax.set_xticks(x_vals)
        ax.set_xticklabels(tick_labels, rotation=tick_rotation, fontsize=tick_fs,
                           ha="right" if tick_rotation > 0 else "center")
        _anchor_x_labels(ax, tick_rotation)


def _draw_legend(ax, treatments, *, palette, legend_title, show_legend,
                 legend_inside, fs, use_patches: bool) -> None:
    if not show_legend:
        if ax.get_legend() is not None:
            ax.get_legend().remove()
        return

    placement = (
        dict(loc="upper right", bbox_to_anchor=(0.98, 0.98), borderaxespad=0)
        if legend_inside else
        dict(loc="upper left", bbox_to_anchor=(1.02, 1), borderaxespad=0)
    )

    if use_patches:
        # Line plots build their own handles so the legend shows filled
        # swatches, matching how the bar/box/violin legends look.
        handles = [mpatches.Patch(facecolor=palette[i % len(palette)], label=t)
                   for i, t in enumerate(treatments)]
        labels = list(treatments)
    else:
        handles, labels = ax.get_legend_handles_labels()
        n = len(treatments)
        handles, labels = handles[:n], labels[:n]

    ax.legend(handles, labels, title=legend_title, frameon=False,
              fontsize=fs["legend_fs"], title_fontsize=fs["legend_title_fs"],
              **placement)


def _anchor_x_labels(ax, rotation: float) -> None:
    """Rotate x tick labels about their right-hand end.

    A rotated label that is centred on its tick sits half to the left and half
    to the right of the mark it names, so with several groups it is not obvious
    which label belongs to which. Anchoring the end of the text at the tick puts
    the last word of each label directly under its group.

    ``rotation_mode="anchor"`` is what makes this exact: without it matplotlib
    rotates the label and then aligns its bounding *box*, which leaves the text
    itself offset from the tick by an amount that grows with the label length.
    """
    if rotation <= 0:
        return
    for label in ax.get_xticklabels():
        label.set_horizontalalignment("right")
        label.set_rotation_mode("anchor")


def _style_axes(
    ax, *, title, xlabel, ylabel, fs, spines, spine_width, y_format,
    y_tick_interval, tick_fs, tick_direction, major_tick_length,
    major_tick_width, minor_ticks_y, minor_tick_length, minor_tick_width,
    log_scale, font_family, rotate_x: bool, tick_rotation: float = 0.0,
) -> None:
    if log_scale:
        ax.set_yscale("log")

    # The font family is set on the artists as well as through the theme.
    # Tick labels are rebuilt whenever the locator changes, so they would
    # otherwise pick up whatever rcParams happened to be active at that moment
    # — which in a panel figure is another panel's font.
    ax.set_title(title, fontsize=fs["title_fs"], pad=10, fontfamily=font_family)
    ax.set_xlabel(xlabel, fontsize=fs["axis_label_fs"], labelpad=6,
                  fontfamily=font_family)
    ax.set_ylabel(ylabel, fontsize=fs["axis_label_fs"], labelpad=6,
                  fontfamily=font_family)

    if spines == "open":
        sns.despine(ax=ax, top=True, right=True)
    elif spines == "none":
        sns.despine(ax=ax, top=True, right=True, left=True, bottom=True)
        ax.tick_params(left=False, bottom=False)
    else:  # "all" — full box
        sns.despine(ax=ax, top=False, right=False)

    for spine in ax.spines.values():
        spine.set_linewidth(spine_width)

    _apply_y_format(ax, y_format)
    if y_tick_interval and y_tick_interval > 0:
        _safe_set_y_locator(ax, y_tick_interval)

    # Ticks are configured after despine, and must ask for bottom/left
    # explicitly: seaborn's "white" style sets xtick.bottom=False and
    # ytick.left=False, so anything set before despine gets hidden again.
    x_kw = {"rotation": tick_rotation} if rotate_x else {}
    ax.tick_params(axis="x", which="major", labelsize=tick_fs,
                   direction=tick_direction, length=major_tick_length,
                   width=major_tick_width, bottom=True,
                   labelfontfamily=font_family, **x_kw)
    if rotate_x:
        _anchor_x_labels(ax, tick_rotation)
    ax.tick_params(axis="y", which="major", labelsize=tick_fs,
                   direction=tick_direction, length=major_tick_length,
                   width=major_tick_width, left=True,
                   labelfontfamily=font_family)
    if minor_ticks_y > 0:
        ax.yaxis.set_minor_locator(mticker.AutoMinorLocator(minor_ticks_y + 1))
        ax.tick_params(axis="y", which="minor", direction=tick_direction,
                       length=minor_tick_length, width=minor_tick_width, left=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_GENERIC_FAMILIES = {
    "sans-serif": "font.sans-serif",
    "serif": "font.serif",
    "monospace": "font.monospace",
    "cursive": "font.cursive",
    "fantasy": "font.fantasy",
}


@lru_cache(maxsize=None)
def _installed_fonts() -> frozenset[str]:
    from matplotlib import font_manager
    return frozenset(f.name for f in font_manager.fontManager.ttflist)


def _concrete_family(generic: str) -> list[str]:
    """Expand ``"sans-serif"`` to the theme's actual font list.

    A Text artist that keeps the generic name resolves it to a real font only
    when it is *drawn*, against whatever rcParams are active then.  In this app
    drawing happens later and elsewhere — ``st.pyplot`` and the export buttons
    both render long after the style context has exited — so the generic name
    would quietly fall back to matplotlib's DejaVu Sans instead of the theme's
    Arial.  Resolving the list here pins the font to the artist.

    Fonts that are not installed are dropped rather than passed through: they
    resolve identically either way, but matplotlib logs a warning for each one
    it has to skip, on every artist, on every render.
    """
    rc_key = _GENERIC_FAMILIES.get(generic)
    if rc_key is None:
        return [generic]
    available = _installed_fonts()
    return [*(f for f in matplotlib.rcParams[rc_key] if f in available), generic]


def _freeze_fonts(container, family: list[str]) -> None:
    """Pin every still-generic Text under *container* to a resolved font list."""
    for text in container.findobj(matplotlib.text.Text):
        current = text.get_fontfamily()
        if len(current) == 1 and current[0] in _GENERIC_FAMILIES:
            text.set_fontfamily(family)


def _theme_rc(font_scale: float, font_family: str) -> dict:
    """rcParams equivalent to ``sns.set_theme(style="white", font_scale=…)``.

    Returned as a dict so it can be applied with ``rc_context`` for the
    duration of one draw instead of being written into the global rcParams.
    """
    rc = dict(sns.axes_style("white"))
    rc.update(sns.plotting_context("notebook", font_scale=font_scale))
    rc["axes.prop_cycle"] = cycler("color", sns.color_palette("deep"))
    rc["patch.facecolor"] = sns.color_palette("deep")[0]
    rc["font.family"] = font_family
    rc["image.cmap"] = "rocket"
    return rc


def _categories(series: pd.Series) -> list:
    """Category order for a column, falling back to first-seen order."""
    if hasattr(series, "cat"):
        return list(series.cat.categories)
    return list(series.unique())


def _apply_axis_limits(
    ax: matplotlib.axes.Axes,
    *,
    ylim: tuple | None = None,
    xlim: tuple | None = None,
) -> None:
    """Apply ylim/xlim, allowing either bound to be None (keep current)."""
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
    from scipy.interpolate import CubicSpline, make_smoothing_spline

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
            y_dense = make_smoothing_spline(x_fit, y_fit)(x_dense)
        elif kind == "smooth":
            # Sort by x and average duplicate x values before interpolating.
            order = np.argsort(x_fit)
            xs, ys = x_fit[order], y_fit[order]
            unique_x, inverse = np.unique(xs, return_inverse=True)
            unique_y = np.array([ys[inverse == i].mean() for i in range(len(unique_x))])
            if len(unique_x) < 2:
                return None
            y_dense = CubicSpline(unique_x, unique_y)(x_dense)
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
