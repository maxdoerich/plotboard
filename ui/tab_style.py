"""ui/tab_style.py — colours, figure size, typography, and advanced axis options."""

from __future__ import annotations

import streamlit as st

import dataio
import plotter
import settings
import utils

_Y_FORMAT_LABELS = {
    "auto":  "Auto",
    "plain": "Plain (no sci notation)",
    "sci":   "Scientific (×10ⁿ)",
    "SI":    "SI prefix (M, k…)",
}
_SPINE_LABELS = {"open": "Open (L-shape)", "all": "Full box", "none": "None"}
_TICK_DIR_LABELS = {"out": "Out", "in": "In", "inout": "Both"}


def render(ctx: dataio.DataContext) -> None:
    base_type = str(settings.get("ps_plot_type")).split("+")[0]

    _render_colors(ctx)

    if base_type == "bar":
        col_width, col_color = st.columns(2)
        with col_width:
            st.slider("Edge width", 0.0, 3.0, key="ps_bar_edge_width", step=0.1)
        with col_color:
            st.color_picker("Edge color", key="ps_bar_edge_color")
        st.slider("Bar opacity", 0.1, 1.0, key="ps_bar_alpha", step=0.05)

    st.divider()
    st.caption("Figure size")
    col_w, col_h = st.columns(2)
    with col_w:
        st.slider("Width (in)", 6, 20, key="ps_fig_width")
    with col_h:
        st.slider("Height (in)", 4, 12, key="ps_fig_height")
    st.slider("Bar gap", 0.0, 0.8, key="ps_bar_gap", step=0.05,
              help="Gap between bars within the same condition group.")

    _render_typography()
    _render_advanced(ctx, base_type)


# ---------------------------------------------------------------------------
# Colours
# ---------------------------------------------------------------------------

def _render_colors(ctx: dataio.DataContext) -> None:
    st.caption("Colors")
    palette_name = st.selectbox("Palette", utils.PALETTE_NAMES,
                                key="ps_palette_name")
    if palette_name != "Custom":
        return

    st.caption("Pick a color for each treatment:")
    stored = list(settings.get("ps_custom_colors") or [])
    fallback = utils.get_palette("iGEM", max(ctx.n_treatments, 1))

    chosen: list[str] = []
    for i, treatment in enumerate(ctx.treatments[:settings.CP_MAX]):
        # settings.hydrate() seeds cp_i from the stored palette, so the picker
        # keeps its colour across reruns and preset loads without a default=
        # that would fight the session-state value.
        if f"cp_{i}" not in st.session_state:
            st.session_state[f"cp_{i}"] = (
                stored[i] if i < len(stored) and stored[i]
                else fallback[i % len(fallback)]
            )
        chosen.append(st.color_picker(str(treatment), key=f"cp_{i}"))

    # ps_custom_colors has no widget of its own, so writing it after the
    # pickers have rendered is safe — and is what makes the palette survive
    # into presets and panel snapshots.
    settings.set_custom_colors(chosen)


# ---------------------------------------------------------------------------
# Typography
# ---------------------------------------------------------------------------

def _render_typography() -> None:
    with st.expander("🔤 Typography", expanded=False):
        st.selectbox("Font family", ["sans-serif", "serif", "monospace"],
                     key="ps_font_family")
        mode = st.radio("Font sizing", ["Global scale", "Per element"],
                        key="ps_font_mode", horizontal=True)
        if mode == "Global scale":
            st.slider("Font scale", 0.5, 2.5, key="ps_font_scale", step=0.1)
        else:
            col_title, col_axis = st.columns(2)
            col_tick, col_legend = st.columns(2)
            with col_title:
                st.number_input("Title", key="ps_fs_title",
                                min_value=4, max_value=40)
            with col_axis:
                st.number_input("Axis labels", key="ps_fs_axis",
                                min_value=4, max_value=40)
            with col_tick:
                st.number_input("Tick labels", key="ps_fs_tick",
                                min_value=4, max_value=40)
            with col_legend:
                st.number_input("Legend", key="ps_fs_legend",
                                min_value=4, max_value=40)


# ---------------------------------------------------------------------------
# Advanced
# ---------------------------------------------------------------------------

def _render_advanced(ctx: dataio.DataContext, base_type: str) -> None:
    with st.expander("⚙️ Advanced", expanded=False):
        st.selectbox("Y-axis number format", list(_Y_FORMAT_LABELS),
                     key="ps_y_format", format_func=_Y_FORMAT_LABELS.get)

        col_rotation, col_size = st.columns(2)
        with col_rotation:
            st.slider("Tick rotation °", 0, 90, key="ps_tick_rotation")
        with col_size:
            st.number_input(
                "Tick font size", key="ps_tick_fontsize_adv",
                min_value=4, max_value=40,
                help="Overrides global/per-element tick setting when changed.")

        st.radio("Axis border style", list(_SPINE_LABELS), key="ps_spines",
                 format_func=_SPINE_LABELS.get, horizontal=True)
        st.slider("Border / tick width", 0.3, 3.0, key="ps_spine_width",
                  step=0.1)

        st.caption("Tick marks")
        st.radio("Direction", list(_TICK_DIR_LABELS), key="ps_tick_direction",
                 horizontal=True, format_func=_TICK_DIR_LABELS.get)
        col_len, col_wid = st.columns(2)
        with col_len:
            st.slider("Major length", 1.0, 12.0, key="ps_major_tick_length",
                      step=0.5)
        with col_wid:
            st.slider("Major width", 0.3, 3.0, key="ps_major_tick_width",
                      step=0.1)

        col_minor_y, col_minor_x = st.columns(2)
        with col_minor_y:
            st.number_input("Minor ticks / interval (Y)", min_value=0,
                            max_value=9, key="ps_minor_ticks_y", step=1)
        with col_minor_x:
            numeric_x = base_type == "line" and plotter.x_axis_is_numeric(
                ctx.conditions, settings.get("ps_x_numeric"))
            st.number_input(
                "Minor ticks / interval (X)", min_value=0, max_value=9,
                key="ps_minor_ticks_x", step=1, disabled=not numeric_x,
                help="Only available for line plots with a numeric x-axis.")

        col_mlen, col_mwid = st.columns(2)
        with col_mlen:
            st.slider("Minor length", 1.0, 8.0, key="ps_minor_tick_length",
                      step=0.5)
        with col_mwid:
            st.slider("Minor width", 0.3, 2.0, key="ps_minor_tick_width",
                      step=0.1)

        st.caption("Axis limits (leave blank for auto)")
        col_ymin, col_ymax = st.columns(2)
        with col_ymin:
            st.text_input("Y min", key="ps_ymin_str", placeholder="auto")
        with col_ymax:
            st.text_input("Y max", key="ps_ymax_str", placeholder="auto")
        col_xmin, col_xmax = st.columns(2)
        with col_xmin:
            st.text_input("X min", key="ps_xmin_str", placeholder="auto")
        with col_xmax:
            st.text_input("X max", key="ps_xmax_str", placeholder="auto")
