"""
ui/tab_text.py — titles, axis labels, the legend, and typography.

All the words on the figure in one place. Previously the labels sat in the Plot
tab while the fonts that render them were an expander in Style.
"""

from __future__ import annotations

import streamlit as st

import dataio
import settings


def render(ctx: dataio.DataContext) -> None:
    # Title and y-label follow the data until you edit them, and must still be
    # allowed to be empty afterwards. A blank value cannot express both, so
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

    st.divider()
    st.caption("Legend")
    st.text_input("Legend title", key="ps_leg_title")
    col_show, col_inside = st.columns(2)
    with col_show:
        st.toggle("Show legend", key="ps_show_legend")
    with col_inside:
        st.toggle("Place inside", key="ps_legend_inside")

    st.divider()
    st.caption("Typography")
    st.selectbox("Font family", ["sans-serif", "serif", "monospace"],
                 key="ps_font_family")
    mode = st.radio("Sizing", ["Global scale", "Per element"],
                    key="ps_font_mode", horizontal=True)
    if mode == "Global scale":
        st.slider("Font scale", 0.5, 2.5, key="ps_font_scale", step=0.1)
        return

    col_title, col_axis = st.columns(2)
    col_tick, col_legend = st.columns(2)
    with col_title:
        st.number_input("Title", key="ps_fs_title", min_value=4, max_value=40)
    with col_axis:
        st.number_input("Axis labels", key="ps_fs_axis",
                        min_value=4, max_value=40)
    with col_tick:
        st.number_input("Tick labels", key="ps_fs_tick",
                        min_value=4, max_value=40)
    with col_legend:
        st.number_input("Legend", key="ps_fs_legend", min_value=4, max_value=40)
