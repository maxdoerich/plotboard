"""
ui/tab_plot.py — everything about the marks: plot type, colours, bars, points.

Grouped by what a control affects rather than by category. Bar gap, opacity and
edge width used to sit in a separate "Style" tab from the error bars and data
points they share the figure with, so adjusting how the bars looked meant
moving between two tabs.
"""

from __future__ import annotations

import streamlit as st

import dataio
import figspec
import plotter
import settings
import utils

PLOT_TYPES = ["bar+strip", "box+strip", "violin+strip", "line+scatter"]
_PLOT_TYPE_LABELS = {
    "bar+strip": "Bar", "box+strip": "Box",
    "violin+strip": "Violin", "line+scatter": "Line",
}
_ERROR_BAR_LABELS = {"sd": "SD", "sem": "SEM", "ci95": "95 % CI"}
_X_MODE_LABELS = {
    "auto": "Auto-detect",
    "numeric": "Numeric (proportional spacing)",
    "categorical": "Categorical (equal spacing)",
}
_MARKER_LABELS = {
    "o": "Circle", "s": "Square", "^": "Triangle up", "D": "Diamond",
    "x": "Cross", "v": "Triangle down", "P": "Plus (filled)",
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

# Journal figure widths. These figures are drawn for publication, where the
# column width is fixed — inches on a slider is the wrong unit for that job.
FIGURE_PRESET_KEY = "_figure_size_preset"
FIGURE_PRESETS: dict[str, tuple[float, float] | None] = {
    "Custom": None,
    "Single column · 85 mm": (3.35, 2.8),
    "1.5 column · 114 mm": (4.5, 3.4),
    "Double column · 180 mm": (7.1, 4.6),
    "Slide · 16:9": (10.0, 5.6),
    "Square": (6.0, 6.0),
}


def _apply_figure_preset_cb() -> None:
    size = FIGURE_PRESETS.get(st.session_state.get(FIGURE_PRESET_KEY))
    if size:
        settings.update({"ps_fig_width": size[0], "ps_fig_height": size[1]})


def render(ctx: dataio.DataContext) -> None:
    st.segmented_control(
        "Plot type", PLOT_TYPES, key="ps_plot_type", required=True,
        format_func=_PLOT_TYPE_LABELS.get, label_visibility="collapsed",
    )
    base_type = str(settings.get("ps_plot_type") or "bar+strip").split("+")[0]

    _render_colors(ctx)
    _render_marks(base_type)
    _render_points(ctx, base_type)
    _render_figure_size()

    if base_type == "line":
        st.divider()
        _render_line_options(ctx)
        _render_sigmoid_options()


# ---------------------------------------------------------------------------
# Colours
# ---------------------------------------------------------------------------

def _render_colors(ctx: dataio.DataContext) -> None:
    st.divider()
    st.caption("Colours")
    palette_name = st.selectbox("Palette", utils.PALETTE_NAMES,
                                key="ps_palette_name")
    if palette_name != "Custom":
        return

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
# Marks
# ---------------------------------------------------------------------------

def _render_marks(base_type: str) -> None:
    if base_type == "line":
        return

    st.divider()
    st.caption({"bar": "Bars", "box": "Boxes", "violin": "Violins"}[base_type])
    st.slider("Gap between groups", 0.0, 0.8, key="ps_bar_gap", step=0.05,
              help="Gap between the marks within one condition group.")

    if base_type != "bar":
        return

    st.slider("Opacity", 0.1, 1.0, key="ps_bar_alpha", step=0.05)
    col_width, col_colour = st.columns(2)
    with col_width:
        st.slider("Edge width", 0.0, 3.0, key="ps_bar_edge_width", step=0.1)
    with col_colour:
        st.color_picker("Edge colour", key="ps_bar_edge_color")

    col_error, col_cap = st.columns(2)
    with col_error:
        st.radio("Error bar", ["sd", "sem", "ci95"], key="ps_error_bar",
                 format_func=_ERROR_BAR_LABELS.get)
    with col_cap:
        st.slider("Cap size", 0.0, 0.3, key="ps_cap_size", step=0.01)


def _render_points(ctx: dataio.DataContext, base_type: str) -> None:
    st.divider()
    if not st.toggle("Show individual data points", key="ps_show_points"):
        return
    col_size, col_alpha = st.columns(2)
    with col_size:
        st.slider("Dot size", 1.0, 12.0, key="ps_point_size", step=0.5)
    with col_alpha:
        st.slider("Dot opacity", 0.1, 1.0, key="ps_point_alpha", step=0.05)

    if not st.toggle("Custom dot colour per treatment", key="ps_point_custom",
                     help="Off: black dots on bars/boxes/violins, the line "
                          "colour on line plots."):
        return
    stored = list(settings.get("ps_point_colors") or [])
    # Seed like the palette pickers: line dots start at their line colour,
    # the rest at the black they were drawn in before this option existed.
    if base_type == "line":
        seed = figspec.resolve_palette(settings.snapshot(), max(ctx.n_treatments, 1))
    else:
        seed = ["#000000"]
    chosen: list[str] = []
    for i, treatment in enumerate(ctx.treatments[:settings.CP_MAX]):
        if f"pc_{i}" not in st.session_state:
            st.session_state[f"pc_{i}"] = (
                stored[i] if i < len(stored) and stored[i] else seed[i % len(seed)]
            )
        chosen.append(st.color_picker(str(treatment), key=f"pc_{i}"))
    settings.set_custom_colors(chosen, "ps_point_colors")


def _render_figure_size() -> None:
    st.divider()
    st.caption("Figure size")
    st.selectbox(
        "Preset", list(FIGURE_PRESETS), key=FIGURE_PRESET_KEY,
        on_change=_apply_figure_preset_cb,
        help="Common publication widths. A preset only sets a starting size — "
             "fine-tune with the sliders afterwards.",
    )
    col_width, col_height = st.columns(2)
    with col_width:
        st.slider("Width (in)", 3.0, 20.0, key="ps_fig_width", step=0.1)
    with col_height:
        st.slider("Height (in)", 2.0, 14.0, key="ps_fig_height", step=0.1)


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
        st.caption("Detected: proportional spacing." if detected
                   else "Detected: equal spacing (labels are not numeric).")
    elif mode == "numeric" and not detected:
        st.warning("Condition labels do not start with a number — falling back "
                   "to equal spacing.")

    st.text_input("X-axis unit suffix (appended to pure-number labels)",
                  key="ps_x_suffix", placeholder="e.g.  h  or  nM")

    st.radio("Error style", ["band", "bars"], key="ps_error_style",
             format_func=lambda x: {"band": "Shaded band",
                                    "bars": "Error bars"}[x],
             horizontal=True)
    col_error, col_cap = st.columns(2)
    with col_error:
        st.radio("Error bar", ["sd", "sem", "ci95"], key="ps_error_bar",
                 format_func=_ERROR_BAR_LABELS.get)
    with col_cap:
        st.slider("Cap size", 0.0, 0.3, key="ps_cap_size", step=0.01)

    col_line, col_marker = st.columns(2)
    with col_line:
        st.slider("Line width", 0.5, 4.0, key="ps_line_width", step=0.1)
    with col_marker:
        st.slider("Marker size", 2.0, 14.0, key="ps_marker_size", step=0.5)
    st.selectbox("Marker", list(_MARKER_LABELS), key="ps_marker_style",
                 format_func=_MARKER_LABELS.get)

    st.caption("Trend line")
    trendline = st.selectbox("Fit type", _TRENDLINES, key="ps_trendline",
                             format_func=_TRENDLINE_LABELS.get)
    if trendline == "none":
        return
    col_source, col_mode = st.columns(2)
    with col_source:
        st.radio("Fit data", ["means", "replicates"], key="ps_trendline_source",
                 format_func=lambda x: {"means": "Means",
                                        "replicates": "All replicates"}[x])
    with col_mode:
        st.radio("Mode", ["overlay", "replace"], key="ps_trendline_mode",
                 format_func=lambda x: {"overlay": "Overlay",
                                        "replace": "Replace line"}[x])


_SIGMOID_FIELDS = (("alow", "A_low", 0.0), ("ahigh", "A_high", 1.0),
                   ("p50", "P50", 1.0), ("dp", "dP", 1.0))


def _add_sigmoid_cb() -> None:
    curves = list(settings.get("ps_sigmoids") or [])
    new_id = max((c["id"] for c in curves), default=-1) + 1
    curves.append({"id": new_id, "color": "#000000",
                   **{k: d for k, _, d in _SIGMOID_FIELDS}})
    settings.update({"ps_sigmoids": curves}, mark_touched=False)


def _remove_sigmoid_cb(curve_id: int) -> None:
    curves = [c for c in settings.get("ps_sigmoids") or [] if c["id"] != curve_id]
    settings.update({"ps_sigmoids": curves}, mark_touched=False)


def _render_sigmoid_options() -> None:
    st.caption("Sigmoid curves")
    st.caption("A(P) = A_low + (A_high − A_low) / (1 + exp((P − P50) / dP)); "
               "P is the x-axis value, so use a numeric x-axis.")
    chosen = []
    for n, curve in enumerate(settings.get("ps_sigmoids") or [], start=1):
        cid = curve["id"]
        # Keyed by curve id (not position) so removing one keeps the others'
        # values. Seeded from the stored list, like the custom palette pickers.
        for field in ("color", *(f for f, _, _ in _SIGMOID_FIELDS)):
            st.session_state.setdefault(f"sg_{cid}_{field}", curve[field])
        with st.container(border=True):
            head, rm = st.columns([4, 1])
            head.markdown(f"**Curve {n}**")
            rm.button("✕", key=f"sg_{cid}_rm", on_click=_remove_sigmoid_cb,
                      args=(cid,), help="Remove this curve")
            cols = st.columns(2)
            vals = {"id": cid}
            for j, (field, label, _) in enumerate(_SIGMOID_FIELDS):
                with cols[j % 2]:
                    vals[field] = st.number_input(label, key=f"sg_{cid}_{field}",
                                                  format="%g")
            vals["color"] = st.color_picker("Colour", key=f"sg_{cid}_color")
            chosen.append(vals)
    st.button("＋ Add sigmoid curve", key="sg_add", on_click=_add_sigmoid_cb)

    # ps_sigmoids has no widget of its own, so it is safe to write after the
    # curve widgets rendered — and is what carries them into presets and panels.
    settings.set_sigmoids(chosen)
