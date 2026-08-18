"""
app.py — Streamlit entry point for the experimental results plotting tool.

Run with:  streamlit run app.py

This module is deliberately thin: it loads the workbook, hands a DataContext to
the sidebar tabs in ``ui/``, and assembles the figure from whatever they left in
``settings``.  The widgets themselves live in ``ui/``, the state model in
``settings.py``, and the settings-to-plot translation in ``figspec.py``.

Layout order matters in three places:

*  ``settings.hydrate()`` runs before any widget so that values Streamlit culled
   at the end of the previous run are back in place, and so the browser is told
   each value; ``settings.persist()`` runs after the sidebar.
*  The figure is the first thing in the main area. Everything optional — the
   stats tables, the raw data, batch export — sits below it, so a settings
   change never pushes the plot off screen.
*  The statistics table is *rendered into* a container that sits below the plot
   but is *executed* before it, so ticking a bracket updates the plot in the
   same run rather than one interaction later.

There are no ``st.rerun()`` calls.  Anything that needs to change a widget-backed
value does it from an ``on_click``/``on_change`` callback, which runs between
runs — a mid-run rerun aborts the script before the widgets register and
Streamlit then loses every one of their values.
"""

from __future__ import annotations

import matplotlib
import streamlit as st

import dataio
import figspec
import panel as xpanel
import plotter
import settings
from ui import export, panels, preview, sidebar_top, stats_table, tab_axes
from ui import tab_data, tab_plot, tab_stats, tab_text

st.set_page_config(
    page_title="Experimental Plotter",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded",
)

with st.sidebar:
    file_bytes, file_label = sidebar_top.render_file_input()

if file_bytes is None:
    # The full title only shows on the empty state; once a file is open the
    # figure takes the top of the page instead of a banner.
    st.title("🔬 Experimental Results Plotter")
    st.info(
        "**Getting started**\n\n"
        "1. Upload an Excel file using the sidebar (or enter a local path).\n"
        "2. Select the sheet to plot.\n"
        "3. Adjust the plot settings in the sidebar.\n"
        "4. Download your figure using the button below the plot.\n\n"
        "**Expected data format** — one row per condition, treatments in groups "
        "of columns (treatment name in the first column of each group, replicate "
        "values in subsequent columns). This is the GraphPad Prism grouped layout."
    )
    st.stop()


# ---------------------------------------------------------------------------
# Settings must be in place before the first widget renders
# ---------------------------------------------------------------------------

settings.ensure_startup_preset()
settings.hydrate()

for key, value in xpanel.PANEL_DEFAULTS.items():
    st.session_state.setdefault(key, value)
# Panel layout sliders default to their minimum too, so they need the same
# push as the plot settings if the browser ever rebuilds them.
settings.reassert(*xpanel.PANEL_DEFAULTS)


# ---------------------------------------------------------------------------
# Load the sheet
# ---------------------------------------------------------------------------

file_key = dataio.file_key(file_bytes)
# panels.build_figure resolves sheets for slots that are not on screen.
st.session_state["_file_bytes"] = file_bytes
st.session_state["_file_key"] = file_key

all_sheets = dataio.sheet_names(file_bytes, file_key)
if not all_sheets:
    st.error("This workbook contains no sheets.")
    st.stop()

# The selectbox reads its value from session_state, so it has to hold a sheet
# that exists in this workbook before the widget is built.  It is re-assigned
# every run for the same reason settings.hydrate() re-asserts its values: a
# selectbox the browser has to rebuild falls back to the first option, which
# would silently plot a different sheet than the one shown as selected.
selected_sheet = st.session_state.get("_sheet_select")
st.session_state["_sheet_select"] = (
    selected_sheet if selected_sheet in all_sheets else all_sheets[0])

with st.sidebar:
    current_sheet = sidebar_top.render_sheet(all_sheets)

df_raw = dataio.load_sheet(file_bytes, file_key, current_sheet)
if df_raw.empty:
    st.warning(
        f"Sheet **{current_sheet}** contains no parseable numeric data. "
        "Try a different sheet, or check that the file uses the expected layout."
    )
    st.stop()

ctx = dataio.DataContext(
    file_bytes=file_bytes,
    file_label=file_label,
    key=file_key,
    sheets=all_sheets,
    sheet=current_sheet,
    df=df_raw,
    conditions=dataio.categories(df_raw["condition"]),
    treatments=dataio.categories(df_raw["treatment"]),
)


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    sidebar_top.render_shape(ctx)
    sidebar_top.render_presets()

    st.divider()
    panel_mode = panels.render_controls(ctx)

    tabs = st.tabs(["Data", "Plot", "Axes", "Text", "Stats"])
    with tabs[0]:
        data_out = tab_data.render(ctx, scope=panels.scope())
    with tabs[1]:
        tab_plot.render(ctx)
    with tabs[2]:
        tab_axes.render(ctx)
    with tabs[3]:
        tab_text.render(ctx)
    with tabs[4]:
        stats_out = tab_stats.render(ctx)

    # Every ps_ widget has now rendered, so the store can be brought up to date.
    settings.persist()

current = settings.snapshot()

if not data_out["selected_conditions"]:
    st.warning("Select at least one condition in the Data tab.")
    st.stop()

df = dataio.apply_selection(
    ctx.df, data_out["selected_conditions"], data_out["treatments"])
conditions = [c for c in data_out["conditions"]
              if c in set(data_out["selected_conditions"])]
treatments = dataio.categories(df["treatment"])


# ---------------------------------------------------------------------------
# Main area
#
# Containers are created in display order — figure first — then filled in
# dependency order: the stats table is executed before the plot that reads it.
# ---------------------------------------------------------------------------

plot_slot = st.container()
export_slot = st.container()
notes_slot = st.container()
rename_slot = st.container()
anova_slot = st.container()
table_slot = st.container()
preview_slot = st.container()
batch_slot = st.container()

scope_key = f"{panels.scope()}::{ctx.sheet}"

cond_rename: dict[str, str] = {}
treat_rename: dict[str, str] = {}
if data_out["show_preview"]:
    with rename_slot:
        cond_rename, treat_rename = preview.render_renames(
            conditions, treatments, scope=scope_key)

with table_slot:
    selected_stats = stats_table.render(
        stats_out["stat_results_all"],
        test_mode=str(current["ps_test_mode"]),
        compare_axis=str(current["ps_compare_axis"]),
        sheet=ctx.sheet,
    )

with anova_slot:
    if current["ps_test_mode"] == "two_way_anova" and current["ps_run_stats"]:
        stats_table.render_anova(stats_out["anova_table"])

# Renaming has to reach the stat table as well: brackets are positioned by
# looking their group names up among the plotted labels, so leaving them as the
# original names makes every bracket silently disappear.
selected_stats = dataio.rename_stat_results(
    selected_stats, cond_rename, treat_rename)

panels.capture_active(
    sheet=ctx.sheet,
    filter_conditions=data_out["selected_conditions"],
    cond_order=data_out["conditions"],
    treat_order=data_out["treatments"],
    stat_rows=selected_stats,
)

df_plot = dataio.apply_renames(df, cond_rename, treat_rename)


def _build_single_figure() -> matplotlib.figure.Figure:
    ylim, xlim = figspec.axis_limits(current)
    return plotter.make_figure(
        df_plot,
        **figspec.figure_size(current),
        ylim=ylim,
        xlim=xlim,
        **figspec.draw_kwargs(
            current,
            n_treatments=len(treatments),
            title=settings.auto_text("ps_title", ctx.default_title),
            ylabel=settings.auto_text("ps_ylabel", ctx.sheet),
            stat_results=selected_stats,
        ),
    )


with plot_slot:
    try:
        fig = panels.build_figure(ctx) if panel_mode else _build_single_figure()
    except Exception as exc:
        # A bad combination of settings should cost you the preview, not the
        # session — the sidebar stays usable so the setting can be undone.
        fig = None
        st.error(f"Could not draw the figure: {exc}")
    else:
        st.pyplot(fig, width="content")

if fig is not None:
    with export_slot:
        safe_sheet = ctx.sheet.replace(" ", "_")
        stem = file_label.replace(".xlsx", "").replace(" ", "_")
        export.render_downloads(
            fig, f"{stem}_{'panel' if panel_mode else safe_sheet}")

# Notes sit under the figure rather than above it: a warning at the top of the
# page pushes the plot down every time the data changes.
with notes_slot:
    if getattr(fig, "layout_warning", False):
        st.caption(
            "⚠️ The figure is too small to fit everything around the axes. "
            "Widen it, shrink the fonts, or put the legend inside the plot "
            "(Text tab) — otherwise labels may be clipped on export."
        )
    if dataio.min_replicates(df) < 2:
        st.caption("⚠️ Some groups have fewer than 2 replicates — error bars "
                   "and statistical tests are skipped for those groups.")

if data_out["show_preview"]:
    with preview_slot:
        preview.render_data(df)

if not panel_mode:
    with batch_slot:
        export.render_batch(ctx)
