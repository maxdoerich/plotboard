"""
app.py — Streamlit entry point for the experimental results plotting tool.

Run with:  streamlit run app.py
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

import parser as xparser
import plotter
import presets as xpresets
import stats as xstats
import utils

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Experimental Plotter",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("🔬 Experimental Results Plotter")
st.caption(
    "Upload a GraphPad Prism-style Excel file, configure the plot in the "
    "sidebar, and download publication-ready figures."
)


# ---------------------------------------------------------------------------
# Session state initialisation
# Populate any missing preset keys with their defaults so every widget has
# a value on first load and after a preset is applied.
# ---------------------------------------------------------------------------


# Shorthand: read a preset-keyed value from session_state, falling back to
# DEFAULTS so that keys for unrendered widgets (cleared by Streamlit) still work.
def _ps(key: str):
    return st.session_state.get(key, xpresets.DEFAULTS.get(key))


# ---------------------------------------------------------------------------
# Cached data loading
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner="Parsing sheet…")
def _load_sheet(file_bytes: bytes, sheet_name: str) -> pd.DataFrame:
    wb = xparser.load_workbook(file_bytes)
    return xparser.parse_sheet(wb, sheet_name)


@st.cache_data(show_spinner="Opening workbook…")
def _get_sheet_names(file_bytes: bytes) -> list[str]:
    wb = xparser.load_workbook(file_bytes)
    return xparser.sheet_names(wb)


@st.cache_data(show_spinner="Running statistical tests…")
def _run_stat_test(
    file_bytes: bytes,
    sheet_name: str,
    test_mode: str,
    compare_axis: str,
    ref_cond: str,
) -> tuple[pd.DataFrame | None, pd.DataFrame | None]:
    """Returns (anova_table, posthoc_df). Cached so style changes don't retrigger tests."""
    df_raw = _load_sheet(file_bytes, sheet_name)
    if test_mode == "ttest":
        return None, xstats.run_ttests_vs_reference(df_raw, ref_cond)
    elif test_mode == "two_way_anova":
        anova_tbl, posthoc = xstats.run_two_way_anova_sidak(df_raw, compare_axis)
        return anova_tbl, posthoc
    elif compare_axis == "conditions":
        return None, xstats.run_tukey(df_raw)
    else:
        return None, xstats.run_tukey_between_treatments(df_raw)


# ---------------------------------------------------------------------------
# Sidebar — file loading (stays above tabs; drives st.stop())
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("📂 Data")

    upload = st.file_uploader("Upload .xlsx file", type=["xlsx"])
    local_path = st.text_input(
        "…or enter a local file path",
        placeholder=r"C:\Users\you\data\results.xlsx",
    )

    file_bytes: bytes | None = None
    file_label = ""

    if upload is not None:
        file_bytes = upload.read()
        file_label = upload.name
    elif local_path.strip():
        p = Path(local_path.strip())
        if p.exists() and p.suffix.lower() == ".xlsx":
            file_bytes = p.read_bytes()
            file_label = p.name
        else:
            st.error("File not found or not an .xlsx file.")

# ---------------------------------------------------------------------------
# Load Default preset whenever a new file is opened
# ---------------------------------------------------------------------------

if file_bytes is not None and "_active_file" not in st.session_state:
    st.session_state.update(xpresets.load(xpresets.get_startup_preset()))
    st.session_state["_active_file"] = True
    st.rerun()

# Seed any DEFAULTS keys missing from session_state so sliders always find
# their value and don't fall back to min_value on first render after a
# plot-type switch clears unrendered widget keys.
for _k, _v in xpresets.DEFAULTS.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v

# ---------------------------------------------------------------------------
# If no file: show instructions and stop
# ---------------------------------------------------------------------------

if file_bytes is None:
    st.info(
        "**Getting started**\n\n"
        "1. Upload an Excel file using the sidebar (or enter a local path).\n"
        "2. Select the sheet to plot.\n"
        "3. Adjust the plot settings in the sidebar.\n"
        "4. Download your figure using the buttons below the plot.\n\n"
        "**Expected data format** — one row per condition, treatments in groups "
        "of columns (treatment name in the first column of each group, replicate "
        "values in subsequent columns). This is the GraphPad Prism grouped layout."
    )
    st.stop()

# ---------------------------------------------------------------------------
# Pre-load data using session-state for sheet (allows tabs to render with
# conditions/treatments known before widgets in tab_data update them).
# ---------------------------------------------------------------------------

all_sheets = _get_sheet_names(file_bytes)
_cur_sheet = st.session_state.get("_sheet_select", all_sheets[0])
if _cur_sheet not in all_sheets:
    _cur_sheet = all_sheets[0]

df = _load_sheet(file_bytes, _cur_sheet)

if df.empty:
    st.warning(
        f"Sheet **{_cur_sheet}** contains no parseable numeric data. "
        "Try a different sheet, or check that the file uses the expected layout."
    )
    st.stop()

conditions = (
    list(df["condition"].cat.categories)
    if hasattr(df["condition"], "cat")
    else list(df["condition"].unique())
)
treatments = (
    list(df["treatment"].cat.categories)
    if hasattr(df["treatment"], "cat")
    else list(df["treatment"].unique())
)
n_treatments = len(treatments)

# When the sheet changes: reset the filter to all conditions, then rerun so
# that session-state values are all from a *prior* run when widgets next render.
# This follows the same pattern as the _active_file / startup-preset rerun and
# prevents the slider-initialization quirk (set-in-same-run → min_value display)
# as well as the radio jumping to its first option.
_sel_cond_key = "filter_conditions"
_prev_sheet_key = "_prev_loaded_sheet"
if st.session_state.get(_prev_sheet_key) != _cur_sheet:
    st.session_state[_sel_cond_key] = list(conditions)
    st.session_state[_prev_sheet_key] = _cur_sheet
    st.rerun()

# Ensure filter selection only contains conditions valid for this sheet.
_cur_filter = st.session_state.get(_sel_cond_key, list(conditions))
_cur_filter = [c for c in _cur_filter if c in conditions] or list(conditions)
st.session_state[_sel_cond_key] = _cur_filter

# Initialise stat variables before the sidebar tabs so main-area code can
# reference them regardless of which tab the user has open.
stat_results: pd.DataFrame | None = None
stat_results_all: pd.DataFrame | None = None
anova_table: pd.DataFrame | None = None

# ---------------------------------------------------------------------------
# Sidebar — tabbed configuration
# ---------------------------------------------------------------------------

with st.sidebar:
    tab_data, tab_plot, tab_style, tab_stats = st.tabs(["Data", "Plot", "Style", "Stats"])

    # =========================================================
    # TAB: Data — sheet, filter, reorder, presets, preview
    # =========================================================
    with tab_data:
        sheet = st.selectbox(
            "Sheet",
            all_sheets,
            index=all_sheets.index(_cur_sheet),
            key="_sheet_select",
        )

        st.caption("Filter")
        selected_conditions = st.multiselect(
            "Show conditions",
            options=conditions,
            key=_sel_cond_key,
            label_visibility="collapsed",
        )

        with st.expander("↕ Reorder", expanded=False):
            st.caption("Change the order number to reorder items in the plot.")
            reorder_col1, reorder_col2 = st.columns(2)

            with reorder_col1:
                st.caption("Conditions (x-axis)")
                cond_order_df = pd.DataFrame({
                    "Condition": conditions,
                    "Order": list(range(1, len(conditions) + 1)),
                })
                edited_cond_order = st.data_editor(
                    cond_order_df,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Condition": st.column_config.TextColumn(disabled=True),
                        "Order": st.column_config.NumberColumn(min_value=1, step=1),
                    },
                    key="cond_order_editor",
                )
                conditions = (
                    edited_cond_order.sort_values("Order", kind="stable")["Condition"]
                    .tolist()
                )

            with reorder_col2:
                st.caption("Treatments (legend)")
                treat_order_df = pd.DataFrame({
                    "Treatment": treatments,
                    "Order": list(range(1, len(treatments) + 1)),
                })
                edited_treat_order = st.data_editor(
                    treat_order_df,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Treatment": st.column_config.TextColumn(disabled=True),
                        "Order": st.column_config.NumberColumn(min_value=1, step=1),
                    },
                    key="treat_order_editor",
                )
                treatments = (
                    edited_treat_order.sort_values("Order", kind="stable")["Treatment"]
                    .tolist()
                )

        with st.expander("💾 Presets", expanded=False):
            saved = xpresets.list_presets()
            startup_preset = xpresets.get_startup_preset()

            if saved:
                def _preset_label(name: str) -> str:
                    return f"★ {name}" if name == startup_preset else name

                col_ps, col_pl = st.columns([3, 1])
                with col_ps:
                    preset_choice = st.selectbox(
                        "Saved presets", saved, label_visibility="collapsed",
                        format_func=_preset_label,
                    )
                with col_pl:
                    if st.button("Load", use_container_width=True):
                        loaded = xpresets.load(preset_choice)
                        st.session_state.update(loaded)
                        for _i, _c in enumerate(loaded.get("ps_custom_colors", [])):
                            if _c:
                                st.session_state[f"cp_{_i}"] = _c
                        st.toast(f"Loaded preset '{preset_choice}'", icon="✅")
                        st.rerun()

                col_startup, col_del = st.columns(2)
                with col_startup:
                    if st.button("⭐ Set as startup", use_container_width=True,
                                 help="Load this preset automatically when a file is opened."):
                        xpresets.set_startup_preset(preset_choice)
                        st.toast(f"'{preset_choice}' will load on startup", icon="⭐")
                with col_del:
                    if st.button("🗑 Delete", use_container_width=True):
                        xpresets.delete(preset_choice)
                        st.toast(f"Deleted preset '{preset_choice}'", icon="🗑")
                        st.rerun()
            else:
                st.caption("No saved presets yet.")

            st.divider()

            col_sn, col_sb = st.columns([3, 1])
            with col_sn:
                new_preset_name = st.text_input(
                    "Preset name", placeholder="e.g. Publication style",
                    label_visibility="collapsed",
                )
            with col_sb:
                if st.button("Save", use_container_width=True):
                    if new_preset_name.strip():
                        settings = {k: st.session_state[k] for k in xpresets.DEFAULTS}
                        if st.session_state.get("ps_palette_name") == "Custom":
                            settings["ps_custom_colors"] = [
                                st.session_state.get(f"cp_{_i}", "")
                                for _i in range(len(treatments))
                            ]
                        xpresets.save(new_preset_name.strip(), settings)
                        st.toast(f"Saved preset '{new_preset_name.strip()}'", icon="💾")
                        st.rerun()
                    else:
                        st.warning("Enter a name first.")

        show_preview = st.checkbox("Show / edit labels & raw data", value=False)

    # =========================================================
    # TAB: Plot — plot type, y-axis, labels, line options
    # =========================================================
    with tab_plot:
        plot_type = st.radio(
            "Plot type",
            ["bar+strip", "box+strip", "violin+strip", "line+scatter"],
            key="ps_plot_type",
            label_visibility="collapsed",
        )
        _base_type = plot_type.split("+")[0]

        st.divider()
        st.caption("Y-axis")
        log_scale_req = st.checkbox("Log scale", key="ps_log_scale")
        log_scale = log_scale_req
        if log_scale_req and df["value"].min() <= 0:
            st.info("Zero/negative values will be excluded from the log-scale plot.")

        show_grid = st.checkbox("Y-axis gridlines", key="ps_show_grid")

        if _base_type in ("bar", "line"):
            col_eb, col_cap = st.columns(2)
            with col_eb:
                error_bar = st.radio(
                    "Error bar",
                    ["sd", "sem", "ci95"],
                    key="ps_error_bar",
                    format_func=lambda x: {"sd": "SD", "sem": "SEM", "ci95": "95 % CI"}[x],
                )
            with col_cap:
                cap_size = st.slider("Cap size", 0.0, 0.3, key="ps_cap_size", step=0.01)
        else:
            error_bar = "sd"
            cap_size = 0.08

        show_points = st.checkbox("Show individual data points", key="ps_show_points")
        if show_points:
            col_ps2, col_pa = st.columns(2)
            with col_ps2:
                point_size = st.slider("Dot size", 1.0, 12.0, key="ps_point_size", step=0.5)
            with col_pa:
                point_alpha = st.slider("Dot opacity", 0.1, 1.0, key="ps_point_alpha", step=0.05)
        else:
            point_size = _ps("ps_point_size")
            point_alpha = _ps("ps_point_alpha")

        st.divider()
        st.caption("Labels")
        default_title = f"{file_label}  ·  {sheet}" if file_label else sheet
        # Title is intentionally NOT preset-keyed — it's file/sheet specific.
        title = st.text_input("Title", value=default_title)
        xlabel = st.text_input("X-axis label", key="ps_xlabel")
        # ylabel defaults to the sheet name on first load; preset overrides after that.
        if "ps_ylabel" not in st.session_state or st.session_state["ps_ylabel"] == "":
            st.session_state["ps_ylabel"] = sheet
        ylabel    = st.text_input("Y-axis label", key="ps_ylabel")
        leg_title = st.text_input("Legend title", key="ps_leg_title")
        col_sl, col_li = st.columns(2)
        with col_sl:
            show_legend = st.checkbox("Show legend", key="ps_show_legend")
        with col_li:
            legend_inside = st.checkbox("Legend inside", key="ps_legend_inside")

        # Line options — only shown for line plots
        if _base_type == "line":
            st.divider()
            import re as _re
            _NUM_RE = _re.compile(r"^\s*[+-]?\d+(?:\.\d*)?(?:[eE][+-]?\d+)?")
            _auto_numeric = all(_NUM_RE.match(str(c)) for c in conditions)
            if "ps_x_numeric" not in st.session_state:
                st.session_state["ps_x_numeric"] = _auto_numeric
            st.caption("Line options")
            x_numeric = st.checkbox("Numeric x-axis (proportional spacing)",
                                    key="ps_x_numeric",
                                    help="Auto-detected from condition labels. Uncheck to use equal spacing.")
            x_suffix = st.text_input("X-axis unit suffix (appended to pure-number labels)",
                                     key="ps_x_suffix", placeholder="e.g.  h  or  nM")
            col_xti, col_yti = st.columns(2)
            with col_xti:
                x_tick_interval = st.number_input(
                    "X tick interval (0 = auto)", min_value=0.0,
                    key="ps_x_tick_interval", step=1.0,
                )
            with col_yti:
                y_tick_interval = st.number_input(
                    "Y tick interval (0 = auto)", min_value=0.0,
                    key="ps_y_tick_interval", step=1.0,
                )
            error_style = st.radio("Error style", ["band", "bars"], key="ps_error_style",
                                   format_func=lambda x: {"band": "Shaded band", "bars": "Error bars"}[x],
                                   horizontal=True)
            col_lw, col_ms = st.columns(2)
            with col_lw:
                line_width = st.slider("Line width", 0.5, 4.0, key="ps_line_width", step=0.1)
            with col_ms:
                marker_size = st.slider("Marker size", 2.0, 14.0, key="ps_marker_size", step=0.5)
            marker_style = st.selectbox(
                "Marker",
                ["o", "s", "^", "D", "x", "v", "P", "none"],
                key="ps_marker_style",
                format_func=lambda x: {"o": "● Circle", "s": "■ Square", "^": "▲ Triangle up",
                                       "D": "◆ Diamond", "x": "✕ Cross", "v": "▼ Triangle down",
                                       "P": "✚ Plus (filled)", "none": "No marker"}[x],
            )
            st.caption("Trend line")
            trendline = st.selectbox(
                "Fit type",
                ["none", "smooth", "linear", "poly2", "poly3", "exp", "log", "power", "spline"],
                key="ps_trendline",
                format_func=lambda x: {
                    "none": "None", "smooth": "Smooth (through points)",
                    "linear": "Linear", "poly2": "Polynomial deg 2",
                    "poly3": "Polynomial deg 3", "exp": "Exponential",
                    "log": "Logarithmic", "power": "Power law",
                    "spline": "Smoothing spline",
                }[x],
            )
            if trendline != "none":
                col_ts, col_tm = st.columns(2)
                with col_ts:
                    trendline_source = st.radio("Fit data", ["means", "replicates"],
                                                key="ps_trendline_source",
                                                format_func=lambda x: {"means": "Means", "replicates": "All replicates"}[x])
                with col_tm:
                    trendline_mode = st.radio("Mode", ["overlay", "replace"],
                                              key="ps_trendline_mode",
                                              format_func=lambda x: {"overlay": "Overlay", "replace": "Replace line"}[x])
            else:
                trendline_source = _ps("ps_trendline_source")
                trendline_mode   = _ps("ps_trendline_mode")
        else:
            x_numeric        = _ps("ps_x_numeric")
            x_suffix         = _ps("ps_x_suffix")
            x_tick_interval  = _ps("ps_x_tick_interval")
            y_tick_interval  = _ps("ps_y_tick_interval")
            error_style      = _ps("ps_error_style")
            line_width       = _ps("ps_line_width")
            marker_size      = _ps("ps_marker_size")
            marker_style     = _ps("ps_marker_style")
            trendline        = _ps("ps_trendline")
            trendline_source = _ps("ps_trendline_source")
            trendline_mode   = _ps("ps_trendline_mode")

    # =========================================================
    # TAB: Style — colors, figure size, typography, advanced
    # =========================================================
    with tab_style:
        st.caption("Colors")
        palette_name = st.selectbox("Palette", utils.PALETTE_NAMES, key="ps_palette_name")

        custom_colors: list[str] = []
        if palette_name == "Custom":
            st.caption("Pick a color for each treatment:")
            default_palette = utils.get_palette("iGEM", n_treatments)
            for i, t in enumerate(treatments):
                col = st.color_picker(
                    f"{t}",
                    value=default_palette[i % len(default_palette)],
                    key=f"cp_{i}",
                )
                custom_colors.append(col)
            palette = custom_colors
        else:
            palette = utils.get_palette(palette_name, n_treatments)

        if _base_type == "bar":
            col_ew, col_ec = st.columns(2)
            with col_ew:
                bar_edge_width = st.slider("Edge width", 0.0, 3.0, key="ps_bar_edge_width", step=0.1)
            with col_ec:
                bar_edge_color = st.color_picker("Edge color", key="ps_bar_edge_color")
            bar_alpha = st.slider("Bar opacity", 0.1, 1.0, key="ps_bar_alpha", step=0.05)
        else:
            bar_edge_width = 0.8
            bar_edge_color = _ps("ps_bar_edge_color")
            bar_alpha = 1.0

        st.divider()
        st.caption("Figure size")
        col_w, col_h = st.columns(2)
        with col_w:
            fig_width = st.slider("Width (in)", 6, 20, key="ps_fig_width")
        with col_h:
            fig_height = st.slider("Height (in)", 4, 12, key="ps_fig_height")
        bar_gap = st.slider(
            "Bar gap", 0.0, 0.8, key="ps_bar_gap", step=0.05,
            help="Gap between bars within the same condition group.",
        )

        with st.expander("🔤 Typography", expanded=False):
            font_family = st.selectbox(
                "Font family",
                ["sans-serif", "serif", "monospace"],
                key="ps_font_family",
            )
            font_mode = st.radio(
                "Font sizing",
                ["Global scale", "Per element"],
                key="ps_font_mode",
                horizontal=True,
            )
            fontsizes: dict | None = None
            font_scale = _ps("ps_font_scale")
            if font_mode == "Global scale":
                font_scale = st.slider("Font scale", 0.5, 2.5, key="ps_font_scale", step=0.1)
            else:
                col_ft, col_fa = st.columns(2)
                col_ftk, col_fl = st.columns(2)
                with col_ft:
                    fs_title  = st.number_input("Title",       key="ps_fs_title",  min_value=4, max_value=40)
                with col_fa:
                    fs_axis   = st.number_input("Axis labels", key="ps_fs_axis",   min_value=4, max_value=40)
                with col_ftk:
                    fs_tick   = st.number_input("Tick labels", key="ps_fs_tick",   min_value=4, max_value=40)
                with col_fl:
                    fs_legend = st.number_input("Legend",      key="ps_fs_legend", min_value=4, max_value=40)
                fontsizes = {
                    "title": fs_title, "axis_label": fs_axis,
                    "tick":  fs_tick,  "legend":     fs_legend,
                }

        with st.expander("⚙️ Advanced", expanded=False):
            y_format = st.selectbox(
                "Y-axis number format",
                ["auto", "plain", "sci", "SI"],
                key="ps_y_format",
                format_func=lambda x: {
                    "auto":  "Auto",
                    "plain": "Plain (no sci notation)",
                    "sci":   "Scientific (×10ⁿ)",
                    "SI":    "SI prefix (M, k…)",
                }[x],
            )

            col_tr, col_tf = st.columns(2)
            with col_tr:
                tick_rotation = st.slider("Tick rotation °", 0, 90, key="ps_tick_rotation")
            with col_tf:
                tick_fontsize_adv = st.number_input(
                    "Tick font size", key="ps_tick_fontsize_adv",
                    min_value=4, max_value=40,
                    help="Overrides global/per-element tick setting when changed.",
                )

            spines = st.radio(
                "Axis border style",
                ["open", "all", "none"],
                key="ps_spines",
                format_func=lambda x: {"open": "Open (L-shape)", "all": "Full box", "none": "None"}[x],
                horizontal=True,
            )
            spine_width = st.slider("Border / tick width", 0.3, 3.0, key="ps_spine_width", step=0.1)

            st.caption("Tick marks")
            tick_direction = st.radio("Direction", ["out", "in", "inout"],
                                      key="ps_tick_direction", horizontal=True,
                                      format_func=lambda x: {"out": "Out", "in": "In", "inout": "Both"}[x])
            col_tl, col_tw = st.columns(2)
            with col_tl:
                major_tick_length = st.slider("Major length", 1.0, 12.0, key="ps_major_tick_length", step=0.5)
            with col_tw:
                major_tick_width = st.slider("Major width", 0.3, 3.0, key="ps_major_tick_width", step=0.1)
            col_my, col_mx = st.columns(2)
            with col_my:
                minor_ticks_y = st.number_input("Minor ticks / interval (Y)", min_value=0, max_value=9,
                                                key="ps_minor_ticks_y", step=1)
            with col_mx:
                _mx_disabled = not (_base_type == "line" and _ps("ps_x_numeric"))
                minor_ticks_x = st.number_input("Minor ticks / interval (X)", min_value=0, max_value=9,
                                                key="ps_minor_ticks_x", step=1,
                                                disabled=_mx_disabled,
                                                help="Only available for line plots with numeric x-axis.")
            col_sl, col_sw = st.columns(2)
            with col_sl:
                minor_tick_length = st.slider("Minor length", 1.0, 8.0, key="ps_minor_tick_length", step=0.5)
            with col_sw:
                minor_tick_width = st.slider("Minor width", 0.3, 2.0, key="ps_minor_tick_width", step=0.1)

            st.caption("Axis limits (leave blank for auto)")
            col_y1, col_y2 = st.columns(2)
            with col_y1:
                ymin_str = st.text_input("Y min", key="ps_ymin_str", placeholder="auto")
            with col_y2:
                ymax_str = st.text_input("Y max", key="ps_ymax_str", placeholder="auto")
            col_x1, col_x2 = st.columns(2)
            with col_x1:
                xmin_str = st.text_input("X min", key="ps_xmin_str", placeholder="auto")
            with col_x2:
                xmax_str = st.text_input("X max", key="ps_xmax_str", placeholder="auto")

            def _parse_lim(s: str):
                s = s.strip()
                if not s:
                    return None
                try:
                    return float(s)
                except ValueError:
                    return None

            ylim = (_parse_lim(ymin_str), _parse_lim(ymax_str))
            xlim = (_parse_lim(xmin_str), _parse_lim(xmax_str))
            if all(v is None for v in ylim):
                ylim = None
            if all(v is None for v in xlim):
                xlim = None

    # =========================================================
    # TAB: Stats — statistical tests and bracket styling
    # =========================================================
    with tab_stats:
        if _base_type == "line":
            st.info("Statistical annotations are not available for line plots.")
        run_stats = st.checkbox("Run statistical tests", key="ps_run_stats",
                                disabled=_base_type == "line")
        test_mode    = _ps("ps_test_mode")
        compare_axis = _ps("ps_compare_axis")
        show_ns      = True
        bracket_linewidth = _ps("ps_bracket_linewidth")
        bracket_fontsize  = _ps("ps_bracket_fontsize")
        show_pvalue       = _ps("ps_show_pvalue")
        show_significance = _ps("ps_show_significance")
        show_fold_change  = _ps("ps_show_fold_change")

        if run_stats:
            test_mode = st.radio(
                "Test",
                ["ttest", "tukey", "two_way_anova"],
                key="ps_test_mode",
                format_func=lambda x: {
                    "ttest":         "t-test vs reference condition",
                    "tukey":         "ANOVA + Tukey HSD (all pairs)",
                    "two_way_anova": "Two-way ANOVA + Sidak",
                }[x],
            )

            if test_mode in ("tukey", "two_way_anova"):
                # "cells" is only valid for two_way_anova; reset if tukey is picked
                if test_mode == "tukey" and st.session_state.get("ps_compare_axis") == "cells":
                    st.session_state["ps_compare_axis"] = "conditions"
                _axis_opts = (["conditions", "treatments", "cells"]
                              if test_mode == "two_way_anova"
                              else ["conditions", "treatments"])
                compare_axis = st.radio(
                    "Compare",
                    _axis_opts,
                    key="ps_compare_axis",
                    format_func=lambda x: {
                        "conditions": "Conditions (per treatment)",
                        "treatments": "Treatments (per condition)",
                        "cells":      "All cell means — global Sidak",
                    }[x],
                    horizontal=True,
                )

            show_pvalue = st.checkbox("Show p-values instead of stars", key="ps_show_pvalue")
            col_ss, col_sfc = st.columns(2)
            with col_ss:
                show_significance = st.checkbox("Show significance", key="ps_show_significance")
            with col_sfc:
                show_fold_change = st.checkbox("Show fold change", key="ps_show_fold_change")

            if test_mode == "ttest":
                ref_cond = st.selectbox("Reference condition", conditions)
            else:
                ref_cond = conditions[0]

            try:
                anova_table, stat_results_all = _run_stat_test(
                    file_bytes, _cur_sheet, test_mode, compare_axis, ref_cond
                )
            except Exception as e:
                st.error(f"Statistical test failed: {e}")
                stat_results_all = None

            st.caption("Bracket style")
            col_blw, col_bfs = st.columns(2)
            with col_blw:
                bracket_linewidth = st.slider("Line width", 0.3, 3.0, key="ps_bracket_linewidth", step=0.1)
            with col_bfs:
                bracket_fontsize = st.slider("Font size", 6.0, 18.0, key="ps_bracket_fontsize", step=0.5)

# ---------------------------------------------------------------------------
# Post-tabs: apply filter and reorder to df
# ---------------------------------------------------------------------------

if not selected_conditions:
    st.warning("Select at least one condition.")
    st.stop()

if selected_conditions != conditions:
    df = df[df["condition"].isin(selected_conditions)].copy()
    if hasattr(df["condition"], "cat"):
        df["condition"] = df["condition"].cat.remove_unused_categories()
    conditions = selected_conditions

# Apply reordering to df so downstream plotting respects the new order
df["condition"] = pd.Categorical(df["condition"], categories=conditions, ordered=True)
df["treatment"] = pd.Categorical(df["treatment"], categories=treatments, ordered=True)

n_treatments = len(treatments)

# Warn about missing replicates
min_reps = df.groupby(["condition", "treatment"], observed=True)["value"].count().min()
if min_reps < 2:
    st.warning("Some groups have fewer than 2 replicates — error bars and statistical tests will be skipped for those groups.")

# ---------------------------------------------------------------------------
# Resolve effective tick font size
# ---------------------------------------------------------------------------
_effective_tick_fs: float | None = None
if tick_fontsize_adv != 10:
    _effective_tick_fs = float(tick_fontsize_adv)
elif fontsizes is not None:
    _effective_tick_fs = fontsizes.get("tick")


# ---------------------------------------------------------------------------
# Label renaming (applied to df before plotting)
# ---------------------------------------------------------------------------

cond_rename: dict[str, str] = {}
treat_rename: dict[str, str] = {}

if show_preview:
    st.subheader("✏️ Rename labels")
    rename_col1, rename_col2 = st.columns(2)

    with rename_col1:
        st.caption("Condition labels (x-axis)")
        cond_df = pd.DataFrame({"Original": conditions, "Display": conditions})
        edited_cond = st.data_editor(
            cond_df,
            use_container_width=True,
            hide_index=True,
            column_config={"Original": st.column_config.TextColumn(disabled=True)},
            key="cond_editor",
        )
        cond_rename = dict(zip(edited_cond["Original"], edited_cond["Display"]))

    with rename_col2:
        st.caption("Treatment labels (legend)")
        treat_df = pd.DataFrame({"Original": treatments, "Display": treatments})
        edited_treat = st.data_editor(
            treat_df,
            use_container_width=True,
            hide_index=True,
            column_config={"Original": st.column_config.TextColumn(disabled=True)},
            key="treat_editor",
        )
        treat_rename = dict(zip(edited_treat["Original"], edited_treat["Display"]))

# Apply renames to a plotting copy (raw df is never mutated)
df_plot = df.copy()
if any(v != k for k, v in cond_rename.items()):
    df_plot["condition"] = df_plot["condition"].map(cond_rename)
    df_plot["condition"] = pd.Categorical(
        df_plot["condition"],
        categories=[cond_rename.get(c, c) for c in conditions],
        ordered=True,
    )
if any(v != k for k, v in treat_rename.items()):
    df_plot["treatment"] = df_plot["treatment"].map(treat_rename)
    df_plot["treatment"] = pd.Categorical(
        df_plot["treatment"],
        categories=[treat_rename.get(t, t) for t in treatments],
        ordered=True,
    )

if stat_results is not None and not stat_results.empty and (cond_rename or treat_rename):
    stat_results = stat_results.copy()
    for col in ["condition", "reference", "group_A", "group_B", "cond_A", "cond_B"]:
        if col in stat_results.columns:
            stat_results[col] = stat_results[col].map(lambda v: cond_rename.get(v, v))
    for col in ["treatment", "treat_A", "treat_B"]:
        if col in stat_results.columns:
            stat_results[col] = stat_results[col].map(lambda v: treat_rename.get(v, v))


# ---------------------------------------------------------------------------
# Main area — "Plot All Sheets" batch export
# ---------------------------------------------------------------------------

def _build_fig_for_sheet(sheet_name: str) -> matplotlib.figure.Figure | None:
    d = _load_sheet(file_bytes, sheet_name)
    if d.empty:
        return None
    n_t = len(d["treatment"].unique())
    pal = utils.get_palette(palette_name if palette_name != "Custom" else "iGEM", n_t)
    fig = plotter.make_figure(
        d,
        plot_type=_base_type,
        error_bar=error_bar,
        cap_size=cap_size,
        show_points=show_points,
        point_size=point_size,
        point_alpha=point_alpha,
        log_scale=log_scale,
        show_grid=show_grid,
        palette=pal,
        bar_edge_width=bar_edge_width,
        bar_edge_color=bar_edge_color,
        bar_alpha=bar_alpha,
        bar_gap=bar_gap,
        title=sheet_name,
        xlabel=xlabel,
        ylabel=sheet_name,
        legend_title=leg_title,
        show_legend=show_legend,
        legend_inside=legend_inside,
        fig_width=fig_width,
        fig_height=fig_height,
        font_family=font_family,
        font_scale=font_scale,
        fontsizes=fontsizes,
        tick_rotation=tick_rotation,
        tick_fontsize=_effective_tick_fs,
        spines=spines,
        spine_width=spine_width,
        y_format=y_format,
        stat_results=None,
    )
    return fig


with st.expander("📦 Batch export — plot all sheets", expanded=False):
    st.caption(
        "Generates one PNG (300 DPI) per sheet and bundles them into a ZIP archive. "
        "Plot settings from the sidebar are applied to all sheets."
    )
    if st.button("Generate ZIP of all sheets"):
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            progress = st.progress(0, text="Plotting…")
            for idx, sname in enumerate(all_sheets):
                progress.progress((idx + 1) / len(all_sheets), text=f"Plotting {sname}…")
                fig_s = _build_fig_for_sheet(sname)
                if fig_s is None:
                    continue
                png_bytes = utils.fig_to_bytes(fig_s, "png", dpi=300)
                zf.writestr(f"{sname}.png", png_bytes)
                plt.close(fig_s)
            progress.empty()
        zip_buf.seek(0)
        st.download_button(
            "⬇️ Download ZIP",
            data=zip_buf.read(),
            file_name=f"{file_label.replace('.xlsx','')}_all_sheets.zip",
            mime="application/zip",
        )


# ---------------------------------------------------------------------------
# Main area — statistical comparisons table (bracket selector)
# Rendered before the plot so checkbox edits take effect on the same run.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Main area — resolve stat_results from previous run's checkbox state
# The comparison table is rendered BELOW the plot; its session-state key
# carries the user's selections into the next rerun, which the plot reads here.
# ---------------------------------------------------------------------------

_editor_key = f"stat_editor_{test_mode}_{compare_axis}_{sheet}"

if run_stats and stat_results_all is not None and not stat_results_all.empty:
    # Sort once numerically and cache so the table and the plot use identical ordering.
    _sa_sorted = stat_results_all.sort_values("p_value").reset_index(drop=True)
    st.session_state[_editor_key + "_sorted"] = _sa_sorted

    # Reconstruct current checkbox state from the raw edit dict Streamlit stores.
    # Format: {"edited_rows": {str(row_idx): {"col": val, ...}}, ...}
    _raw = st.session_state.get(_editor_key, {})
    _show = [False] * len(_sa_sorted)
    for _idx_str, _changes in _raw.get("edited_rows", {}).items():
        if "Show bracket" in _changes:
            _show[int(_idx_str)] = bool(_changes["Show bracket"])

    _selected = _sa_sorted[_show].copy()
    stat_results = _selected if not _selected.empty else None

# ---------------------------------------------------------------------------
# Main area — current sheet figure
# ---------------------------------------------------------------------------

fig = plotter.make_figure(
    df_plot,
    plot_type=_base_type,
    error_bar=error_bar,
    cap_size=cap_size,
    show_points=show_points,
    point_size=point_size,
    point_alpha=point_alpha,
    log_scale=log_scale,
    show_grid=show_grid,
    palette=palette,
    bar_edge_width=bar_edge_width,
    bar_edge_color=bar_edge_color,
    bar_alpha=bar_alpha,
    bar_gap=bar_gap,
    title=title,
    xlabel=xlabel,
    ylabel=ylabel,
    legend_title=leg_title,
    show_legend=show_legend,
    legend_inside=legend_inside,
    fig_width=fig_width,
    fig_height=fig_height,
    font_family=font_family,
    font_scale=font_scale,
    fontsizes=fontsizes,
    tick_rotation=tick_rotation,
    tick_fontsize=_effective_tick_fs,
    spines=spines,
    spine_width=spine_width,
    y_format=y_format,
    ylim=ylim,
    xlim=xlim,
    x_numeric=x_numeric,
    x_tick_interval=x_tick_interval,
    y_tick_interval=y_tick_interval,
    error_style=error_style,
    line_width=line_width,
    marker_style=marker_style,
    marker_size=marker_size,
    x_suffix=x_suffix,
    trendline=trendline,
    trendline_source=trendline_source,
    trendline_mode=trendline_mode,
    tick_direction=_ps("ps_tick_direction"),
    major_tick_length=_ps("ps_major_tick_length"),
    major_tick_width=_ps("ps_major_tick_width"),
    minor_ticks_y=int(_ps("ps_minor_ticks_y")),
    minor_ticks_x=int(_ps("ps_minor_ticks_x")),
    minor_tick_length=_ps("ps_minor_tick_length"),
    minor_tick_width=_ps("ps_minor_tick_width"),
    stat_results=stat_results if _base_type != "line" else None,
    show_ns=show_ns,
    test_mode=test_mode,
    compare_axis=compare_axis,
    bracket_linewidth=bracket_linewidth,
    bracket_fontsize=bracket_fontsize,
    show_pvalue=show_pvalue,
    show_significance=show_significance,
    show_fold_change=show_fold_change,
)

st.pyplot(fig, use_container_width=False)

# ---------------------------------------------------------------------------
# Download buttons
# ---------------------------------------------------------------------------

safe_name = f"{file_label.replace('.xlsx','').replace(' ','_')}_{sheet}"

dl_cols = st.columns(4)

# Background options (shown before rendering bytes so they apply to all buttons)
bg_cols = st.columns([1, 1, 4])
with bg_cols[0]:
    export_transparent = st.checkbox("Transparent background", value=False)
with bg_cols[1]:
    export_bg_color = st.color_picker("Background color", value="#FFFFFF",
                                      disabled=export_transparent,
                                      label_visibility="collapsed")

_export_kwargs = dict(transparent=export_transparent, facecolor=export_bg_color)

with dl_cols[0]:
    st.download_button(
        "⬇️ PNG 300 DPI",
        data=utils.fig_to_bytes(fig, "png", 300, **_export_kwargs),
        file_name=f"{safe_name}_300dpi.png",
        mime="image/png",
    )
with dl_cols[1]:
    st.download_button(
        "⬇️ PNG 600 DPI",
        data=utils.fig_to_bytes(fig, "png", 600, **_export_kwargs),
        file_name=f"{safe_name}_600dpi.png",
        mime="image/png",
    )
with dl_cols[2]:
    st.download_button(
        "⬇️ SVG",
        data=utils.fig_to_bytes(fig, "svg", **_export_kwargs),
        file_name=f"{safe_name}.svg",
        mime="image/svg+xml",
    )
with dl_cols[3]:
    st.download_button(
        "⬇️ PDF",
        data=utils.fig_to_bytes(fig, "pdf", **_export_kwargs),
        file_name=f"{safe_name}.pdf",
        mime="application/pdf",
    )

plt.close(fig)

# ---------------------------------------------------------------------------
# Stats table
# ---------------------------------------------------------------------------

if run_stats and test_mode == "two_way_anova" and anova_table is not None and not anova_table.empty:
    st.subheader("Two-way ANOVA table")
    # pingouin column names vary by version; pick what's available
    _p_col = next((c for c in ["p-unc", "p_unc", "pvalue"] if c in anova_table.columns), None)
    _df_col = next((c for c in ["DF", "df", "ddof1"] if c in anova_table.columns), None)
    _keep = [c for c in ["Source", "SS", _df_col, "MS", "F", _p_col] if c is not None and c in anova_table.columns]
    display_anova = anova_table[_keep].copy()
    if _p_col and _p_col in display_anova.columns:
        display_anova[_p_col] = display_anova[_p_col].map(
            lambda p: f"{p:.4f}" if pd.notna(p) and p >= 0.0001 else ("<0.0001" if pd.notna(p) else "—")
        )
        display_anova = display_anova.rename(columns={_p_col: "p-value"})
    if _df_col and _df_col in display_anova.columns:
        display_anova = display_anova.rename(columns={_df_col: "df"})
    st.dataframe(display_anova, use_container_width=True)

# ---------------------------------------------------------------------------
# Statistical comparisons table (bracket selector)
# ---------------------------------------------------------------------------

if run_stats and stat_results_all is not None and not stat_results_all.empty:
    st.subheader("📋 Statistical comparisons")
    st.caption("Tick a row to draw its bracket on the plot.")

    # Use the same numerically-sorted frame that the plot reads from.
    _sa = st.session_state.get(_editor_key + "_sorted", stat_results_all.sort_values("p_value").reset_index(drop=True)).copy()
    _sa["p-adj"] = _sa["p_value"].map(
        lambda p: f"{p:.4f}" if p >= 0.0001 else "<0.0001"
    )
    _sa["Show bracket"] = False   # default; Streamlit restores user edits via _editor_key

    if compare_axis == "cells":
        _disp_cols = ["cond_A", "treat_A", "cond_B", "treat_B", "p-adj", "stars", "Show bracket"]
        _col_labels = {"cond_A": "Condition A", "treat_A": "Treatment A",
                       "cond_B": "Condition B", "treat_B": "Treatment B", "stars": "Sig."}
    elif compare_axis == "treatments":
        _disp_cols = ["condition", "group_A", "group_B", "p-adj", "stars", "Show bracket"]
        _col_labels = {"condition": "Condition", "group_A": "Treatment A",
                       "group_B": "Treatment B", "stars": "Sig."}
    elif test_mode == "ttest":
        _disp_cols = ["treatment", "reference", "condition", "p-adj", "stars", "Show bracket"]
        _col_labels = {"treatment": "Treatment", "reference": "Reference",
                       "condition": "Condition", "stars": "Sig."}
    else:
        _disp_cols = ["treatment", "group_A", "group_B", "p-adj", "stars", "Show bracket"]
        _col_labels = {"treatment": "Treatment", "group_A": "Condition A",
                       "group_B": "Condition B", "stars": "Sig."}

    _disp = _sa[[c for c in _disp_cols if c in _sa.columns]].rename(columns=_col_labels)

    _col_cfg = {c: st.column_config.TextColumn(c, disabled=True)
                for c in _disp.columns if c != "Show bracket"}
    _col_cfg["Show bracket"] = st.column_config.CheckboxColumn(
        "Show bracket", help="Tick to draw a bracket on the plot"
    )

    st.data_editor(
        _disp,
        column_config=_col_cfg,
        use_container_width=True,
        hide_index=True,
        key=_editor_key,
    )

elif run_stats and stat_results_all is not None and stat_results_all.empty:
    st.info("No comparisons could be computed (check that all groups have ≥ 2 replicates).")

# ---------------------------------------------------------------------------
# Data preview
# ---------------------------------------------------------------------------

if show_preview:
    st.subheader("Summary statistics")
    pivot = (
        df.groupby(["condition", "treatment"], observed=True)["value"]
        .agg(["mean", "std", "count"])
        .rename(columns={"mean": "Mean", "std": "SD", "count": "N"})
        .reset_index()
    )
    st.dataframe(pivot, use_container_width=True)
    with st.expander("All individual values"):
        st.dataframe(
            df.sort_values(["condition", "treatment", "replicate"]),
            use_container_width=True,
        )
