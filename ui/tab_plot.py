"""ui/tab_plot.py — plot type, y-axis, labels, and the line-plot options."""

from __future__ import annotations

import streamlit as st

import dataio
import plotter
import settings

PLOT_TYPES = ["bar+strip", "box+strip", "violin+strip", "line+scatter"]

_ERROR_BAR_LABELS = {"sd": "SD", "sem": "SEM", "ci95": "95 % CI"}
_X_MODE_LABELS = {
    "auto": "Auto-detect",
    "numeric": "Numeric (proportional spacing)",
    "categorical": "Categorical (equal spacing)",
}
_MARKER_LABELS = {
    "o": "● Circle", "s": "■ Square", "^": "▲ Triangle up", "D": "◆ Diamond",
    "x": "✕ Cross", "v": "▼ Triangle down", "P": "✚ Plus (filled)",
    "none": "No marker",
}
_TRENDLINES = ["none", "smooth", "linear", "poly2", "poly3", "exp", "log",
               "power", "spline"]
_TRENDLINE_LABELS = {
    "none": "None", "smooth": "Smooth (through points)", "linear": "Linear",
    "poly2": "Polynomial deg 2", "poly3": "Polynomial deg 3",
    "exp": "Exponential", "log": "Logarithmic", "power": "Power law",
    "spline": "Smoothing spline",
}


def render(ctx: dataio.DataContext) -> None:
    st.radio("Plot type", PLOT_TYPES, key="ps_plot_type",
             label_visibility="collapsed")
    base_type = str(settings.get("ps_plot_type")).split("+")[0]

    st.divider()
    st.caption("Y-axis")
    log_scale = st.checkbox("Log scale", key="ps_log_scale")
    if log_scale and ctx.df["value"].min() <= 0:
        st.info("Zero/negative values will be excluded from the log-scale plot.")
    st.checkbox("Y-axis gridlines", key="ps_show_grid")

    if base_type in ("bar", "line"):
        col_err, col_cap = st.columns(2)
        with col_err:
            st.radio("Error bar", ["sd", "sem", "ci95"], key="ps_error_bar",
                     format_func=_ERROR_BAR_LABELS.get)
        with col_cap:
            st.slider("Cap size", 0.0, 0.3, key="ps_cap_size", step=0.01)

    if st.checkbox("Show individual data points", key="ps_show_points"):
        col_size, col_alpha = st.columns(2)
        with col_size:
            st.slider("Dot size", 1.0, 12.0, key="ps_point_size", step=0.5)
        with col_alpha:
            st.slider("Dot opacity", 0.1, 1.0, key="ps_point_alpha", step=0.05)

    st.divider()
    _render_labels(ctx)

    if base_type == "line":
        st.divider()
        _render_line_options(ctx)


# ---------------------------------------------------------------------------
# Labels
# ---------------------------------------------------------------------------

def _render_labels(ctx: dataio.DataContext) -> None:
    st.caption("Labels")

    # Title and y-label follow the data until you edit them, and must still be
    # allowed to be empty afterwards.  A blank value cannot express both, so
    # settings records which of them the user has actually touched.
    st.text_input(
        "Title", key="ps_title", placeholder=ctx.default_title,
        help="Leave empty to use the file and sheet name.",
        on_change=settings.mark_touched, args=("ps_title",),
    )
    st.text_input("X-axis label", key="ps_xlabel")
    st.text_input(
        "Y-axis label", key="ps_ylabel", placeholder=ctx.sheet,
        help="Leave empty to use the sheet name.",
        on_change=settings.mark_touched, args=("ps_ylabel",),
    )
    st.text_input("Legend title", key="ps_leg_title")

    col_show, col_inside = st.columns(2)
    with col_show:
        st.checkbox("Show legend", key="ps_show_legend")
    with col_inside:
        st.checkbox("Legend inside", key="ps_legend_inside")


# ---------------------------------------------------------------------------
# Line options
# ---------------------------------------------------------------------------

def _render_line_options(ctx: dataio.DataContext) -> None:
    st.caption("Line options")

    mode = st.selectbox(
        "X-axis spacing", ["auto", "numeric", "categorical"], key="ps_x_numeric",
        format_func=_X_MODE_LABELS.get,
        help="Auto uses proportional spacing when every condition label starts "
             "with a number.",
    )
    detected = plotter.x_axis_is_numeric(ctx.conditions, mode)
    if mode == "auto":
        st.caption("Detected: proportional spacing."
                   if detected else
                   "Detected: equal spacing (labels are not numeric).")
    elif mode == "numeric" and not detected:
        st.warning("Condition labels do not start with a number — falling back "
                   "to equal spacing.")

    st.text_input("X-axis unit suffix (appended to pure-number labels)",
                  key="ps_x_suffix", placeholder="e.g.  h  or  nM")

    col_x, col_y = st.columns(2)
    with col_x:
        st.number_input("X tick interval (0 = auto)", min_value=0.0,
                        key="ps_x_tick_interval", step=1.0)
    with col_y:
        st.number_input("Y tick interval (0 = auto)", min_value=0.0,
                        key="ps_y_tick_interval", step=1.0)

    st.radio("Error style", ["band", "bars"], key="ps_error_style",
             format_func=lambda x: {"band": "Shaded band",
                                    "bars": "Error bars"}[x],
             horizontal=True)

    col_width, col_marker = st.columns(2)
    with col_width:
        st.slider("Line width", 0.5, 4.0, key="ps_line_width", step=0.1)
    with col_marker:
        st.slider("Marker size", 2.0, 14.0, key="ps_marker_size", step=0.5)
    st.selectbox("Marker", list(_MARKER_LABELS), key="ps_marker_style",
                 format_func=_MARKER_LABELS.get)

    st.caption("Trend line")
    trendline = st.selectbox("Fit type", _TRENDLINES, key="ps_trendline",
                             format_func=_TRENDLINE_LABELS.get)
    if trendline != "none":
        col_source, col_mode = st.columns(2)
        with col_source:
            st.radio("Fit data", ["means", "replicates"],
                     key="ps_trendline_source",
                     format_func=lambda x: {"means": "Means",
                                            "replicates": "All replicates"}[x])
        with col_mode:
            st.radio("Mode", ["overlay", "replace"], key="ps_trendline_mode",
                     format_func=lambda x: {"overlay": "Overlay",
                                            "replace": "Replace line"}[x])
