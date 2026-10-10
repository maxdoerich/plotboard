"""
ui/tab_axes.py — scale, limits, gridlines, number format and tick geometry.

These controls used to be split between the Y-axis section of the Plot tab and
a single "Advanced" expander holding sixteen unrelated widgets — number
formatting, tick geometry, spines and axis limits in one drawer. They all
describe the axes, so they live together and are grouped by what they do.
"""

from __future__ import annotations

import streamlit as st

import dataio
import plotter
import settings

_Y_FORMAT_LABELS = {
    "auto":  "Auto",
    "plain": "Plain (no sci notation)",
    "sci":   "Scientific (×10ⁿ)",
    "SI":    "SI prefix (M, k…)",
}
_SPINE_LABELS = {"open": "Open (L-shape)", "all": "Full box", "none": "None"}
_TICK_DIR_LABELS = {"out": "Out", "in": "In", "inout": "Both"}


def render(ctx: dataio.DataContext) -> None:
    base_type = str(settings.get("ps_plot_type") or "bar+strip").split("+")[0]

    st.caption("Scale")
    log_scale = st.toggle("Log scale", key="ps_log_scale")
    if log_scale and ctx.df["value"].min() <= 0:
        st.info("Zero and negative values are excluded from a log-scale plot.")
    st.toggle("Horizontal gridlines", key="ps_show_grid")
    st.selectbox("Y-axis number format", list(_Y_FORMAT_LABELS),
                 key="ps_y_format", format_func=_Y_FORMAT_LABELS.get)

    _render_limits(base_type)
    _render_ticks(ctx, base_type)
    _render_frame()


def _render_limits(base_type: str) -> None:
    st.divider()
    st.caption("Limits — leave blank for automatic")
    col_min, col_max = st.columns(2)
    with col_min:
        st.text_input("Y min", key="ps_ymin_str", placeholder="auto")
    with col_max:
        st.text_input("Y max", key="ps_ymax_str", placeholder="auto")
    if base_type == "line":
        col_xmin, col_xmax = st.columns(2)
        with col_xmin:
            st.text_input("X min", key="ps_xmin_str", placeholder="auto")
        with col_xmax:
            st.text_input("X max", key="ps_xmax_str", placeholder="auto")
    if settings.get("ps_run_stats"):
        st.caption("Significance brackets are drawn before a manual Y max is "
                   "applied, so brackets above it will be cut off.")


def _render_ticks(ctx: dataio.DataContext, base_type: str) -> None:
    st.divider()
    st.caption("Ticks")

    numeric_x = base_type == "line" and plotter.x_axis_is_numeric(
        ctx.conditions, settings.get("ps_x_numeric"))

    col_interval_y, col_interval_x = st.columns(2)
    with col_interval_y:
        st.number_input("Y interval (0 = auto)", min_value=0.0,
                        key="ps_y_tick_interval", step=1.0)
    with col_interval_x:
        st.number_input("X interval (0 = auto)", min_value=0.0,
                        key="ps_x_tick_interval", step=1.0,
                        disabled=not numeric_x,
                        help="Only for line plots with a numeric x-axis.")

    col_rotation, col_size = st.columns(2)
    with col_rotation:
        st.slider("Label rotation °", 0, 90, key="ps_tick_rotation")
    with col_size:
        st.number_input("Label size", key="ps_tick_fontsize_adv",
                        min_value=4, max_value=40,
                        help="Overrides the Text tab's tick size once changed "
                             "from 10.")

    with st.expander("Tick marks", expanded=False):
        st.radio("Direction", list(_TICK_DIR_LABELS), key="ps_tick_direction",
                 horizontal=True, format_func=_TICK_DIR_LABELS.get)
        col_length, col_width = st.columns(2)
        with col_length:
            st.slider("Major length", 1.0, 12.0, key="ps_major_tick_length",
                      step=0.5)
        with col_width:
            st.slider("Major width", 0.3, 3.0, key="ps_major_tick_width",
                      step=0.1)

        col_minor_y, col_minor_x = st.columns(2)
        with col_minor_y:
            st.number_input("Minor ticks per interval (Y)", min_value=0,
                            max_value=9, key="ps_minor_ticks_y", step=1)
        with col_minor_x:
            st.number_input("Minor ticks per interval (X)", min_value=0,
                            max_value=9, key="ps_minor_ticks_x", step=1,
                            disabled=not numeric_x,
                            help="Only for line plots with a numeric x-axis.")
        col_mlength, col_mwidth = st.columns(2)
        with col_mlength:
            st.slider("Minor length", 1.0, 8.0, key="ps_minor_tick_length",
                      step=0.5)
        with col_mwidth:
            st.slider("Minor width", 0.3, 2.0, key="ps_minor_tick_width",
                      step=0.1)


def _render_frame() -> None:
    st.divider()
    st.caption("Frame")
    st.radio("Axis border", list(_SPINE_LABELS), key="ps_spines",
             format_func=_SPINE_LABELS.get, horizontal=True)
    st.slider("Border / tick width", 0.3, 3.0, key="ps_spine_width", step=0.1)
