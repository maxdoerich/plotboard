"""
ui/panels.py — panel mode: one figure built from several independent plots.

State model
-----------
``st.session_state["panels"]`` is a list of dicts, one per grid slot:

    mode        "plot" | "empty"
    sheet       which sheet this slot plots
    filter      condition selection for this slot
    cond_order  display order of conditions / treatments
    treat_order
    label       custom label override ("" = use the label style)
    touched     which follow-the-data settings the user has overridden
    stat_rows   the significance comparisons ticked for this slot
    ps_*        every visual setting

The *active* panel's settings are mirrored into the live ``ps_*`` keys so the
ordinary sidebar tabs edit it with no special-casing.  Switching panels happens
in an ``on_click`` callback: callbacks run between script runs, so the restored
values are already in place when the widgets render.  The previous version
wrote them mid-run and called ``st.rerun()``, which discarded the run before any
widget had registered and took every setting down with it.

Widget keys for the per-panel filter and ordering editors are scoped by panel
index, so each slot keeps its own selection without any copying.
"""

from __future__ import annotations

import matplotlib
import pandas as pd
import streamlit as st

import dataio
import figspec
import panel as xpanel
import plotter
import presets as xpresets
import settings

MODE_KEY = "_panel_mode"
PANELS_KEY = "panels"
ACTIVE_KEY = "_active_panel_idx"


def is_active() -> bool:
    return bool(st.session_state.get(MODE_KEY))


def active_index() -> int:
    return int(st.session_state.get(ACTIVE_KEY, 0))


def scope() -> str:
    """Suffix that makes the data-tab widget keys panel-specific."""
    return f"panel{active_index()}" if is_active() else ""


# ---------------------------------------------------------------------------
# Snapshot / restore
# ---------------------------------------------------------------------------

def _new_panel(sheet: str) -> dict:
    panel = settings.snapshot()
    panel.update(
        mode="plot", sheet=sheet, filter=[], cond_order=[], treat_order=[],
        label="", touched=sorted(settings.touched_keys()), stat_rows=[],
    )
    return panel


def ensure_initialised(sheet: str) -> None:
    if not st.session_state.get(PANELS_KEY):
        st.session_state[PANELS_KEY] = [_new_panel(sheet)]
        st.session_state[ACTIVE_KEY] = 0


def capture_active(
    *,
    sheet: str,
    filter_conditions: list,
    cond_order: list,
    treat_order: list,
    stat_rows: pd.DataFrame | None = None,
) -> None:
    """Mirror the live widget state into the active panel.  Read-only on
    session_state, so it is safe to call at any point in a run."""
    if not is_active():
        return
    panels = st.session_state.get(PANELS_KEY) or []
    index = active_index()
    if index >= len(panels):
        return

    panel = panels[index]
    if panel.get("mode") == "empty":
        return

    panel.update(settings.snapshot())
    panel["sheet"] = sheet
    panel["filter"] = list(filter_conditions)
    panel["cond_order"] = list(cond_order)
    panel["treat_order"] = list(treat_order)
    panel["touched"] = sorted(settings.touched_keys())
    if stat_rows is not None:
        panel["stat_rows"] = stat_rows.to_dict("records")


def _restore(index: int) -> None:
    """Load a panel into the live widgets.  Callback context only."""
    panels = st.session_state.get(PANELS_KEY) or []
    if index >= len(panels):
        return
    panel = panels[index]
    if panel.get("mode") == "empty":
        return

    settings.update({k: panel[k] for k in xpresets.DEFAULTS if k in panel},
                    mark_touched=False)
    settings.restore_touched(panel.get("touched", []))

    if panel.get("sheet"):
        st.session_state["_sheet_select"] = panel["sheet"]

    # Re-seed this panel's condition and treatment filters. The widget keys
    # depend on the sheet's contents, so the sheet has to be parsed — it is
    # cached, and this only runs when the user clicks a different panel.
    # ``treat_order`` holds only the shown treatments (see tab_data.render).
    stored_filter = panel.get("filter")
    stored_treat = panel.get("treat_order")
    if (stored_filter or stored_treat) and panel.get("sheet"):
        try:
            frame = _sheet_frame(panel["sheet"])
            scope = f"panel{index}::{panel['sheet']}"
            conditions = dataio.categories(frame["condition"])
            treatments = dataio.categories(frame["treatment"])
            shown = [c for c in stored_filter or [] if c in conditions]
            if shown:
                st.session_state[settings.filter_key(scope, conditions)] = shown
            shown = [t for t in stored_treat or [] if t in treatments]
            if shown:
                key = settings.filter_key(f"{scope}::treatments", treatments)
                st.session_state[key] = shown
        except Exception:
            pass  # a missing sheet must not block the panel switch


def _switch_cb(index: int) -> None:
    st.session_state[ACTIVE_KEY] = index
    _restore(index)


def _set_mode_cb(index: int, widget_key: str) -> None:
    panels = st.session_state.get(PANELS_KEY) or []
    if index < len(panels):
        panels[index]["mode"] = st.session_state.get(widget_key, "plot")


def _set_label_cb(index: int, widget_key: str) -> None:
    panels = st.session_state.get(PANELS_KEY) or []
    if index < len(panels):
        panels[index]["label"] = st.session_state.get(widget_key, "")


def _resize(target: int, sheet: str) -> None:
    panels = st.session_state.setdefault(PANELS_KEY, [])
    while len(panels) < target:
        panels.append(_new_panel(sheet))
    while len(panels) > target:
        panels.pop()


# ---------------------------------------------------------------------------
# Sidebar UI
# ---------------------------------------------------------------------------

def render_controls(ctx: dataio.DataContext) -> bool:
    """Panel toggle, layout controls and the slot selector.  Returns the mode."""
    panel_mode = st.toggle(
        "🔲 Panel mode (multi-plot figure)", key=MODE_KEY,
        help="Build a publication panel: a single figure containing several "
             "plots arranged in a grid. Click a panel button to edit it.",
    )
    if not panel_mode:
        return False

    ensure_initialised(ctx.sheet)
    rows, cols = _render_layout()

    total = int(rows) * int(cols)
    _resize(total, ctx.sheet)
    if active_index() >= total:
        st.session_state[ACTIVE_KEY] = 0

    _render_selector(rows, cols, total)
    st.divider()
    return True


def _render_layout() -> tuple[int, int]:
    with st.expander("Layout", expanded=False):
        col_rows, col_cols = st.columns(2)
        with col_rows:
            rows = st.number_input("Rows", min_value=1, max_value=6,
                                   key="ph_rows", step=1)
        with col_cols:
            cols = st.number_input("Cols", min_value=1, max_value=6,
                                   key="ph_cols", step=1)
        col_w, col_h = st.columns(2)
        with col_w:
            st.slider("Width (in)", 4, 24, key="ph_fig_width")
        with col_h:
            st.slider("Height (in)", 3, 18, key="ph_fig_height")
        col_ws, col_hs = st.columns(2)
        with col_ws:
            st.slider("Horizontal gap", 0.0, 1.5, key="ph_wspace", step=0.05)
        with col_hs:
            st.slider("Vertical gap", 0.0, 1.5, key="ph_hspace", step=0.05)

        st.caption("Panel labels")
        st.selectbox("Label style", xpanel.LABEL_STYLES, key="ph_label_style",
                     format_func=xpanel.LABEL_STYLE_DISPLAY.get)
        col_size, col_weight = st.columns(2)
        with col_size:
            st.slider("Label size", 8, 32, key="ph_label_fontsize")
        with col_weight:
            st.selectbox("Weight", ["normal", "bold"], key="ph_label_fontweight")
        col_x, col_y = st.columns(2)
        with col_x:
            st.slider("Label X offset", -0.5, 0.5, key="ph_label_x_offset",
                      step=0.01)
        with col_y:
            st.slider("Label Y offset", 0.5, 1.5, key="ph_label_y_offset",
                      step=0.01)
    return int(rows), int(cols)


def _render_selector(rows: int, cols: int, total: int) -> None:
    label_style = st.session_state.get("ph_label_style", "A")
    panels = st.session_state[PANELS_KEY]
    active = active_index()

    st.caption("Panels — click to edit")
    for row in range(rows):
        button_cols = st.columns(cols)
        for col in range(cols):
            index = row * cols + col
            if index >= total:
                continue
            label = xpanel.panel_label(index, label_style) or f"#{index + 1}"
            if panels[index].get("mode") == "empty":
                label = f"{label} ∅"
            button_cols[col].button(
                label, key=f"_panel_btn_{index}",
                type="primary" if index == active else "secondary",
                width="stretch",
                on_click=_switch_cb, args=(index,),
                disabled=index == active,
            )

    current = panels[active]
    default_label = xpanel.panel_label(active, label_style)
    st.caption(f"Editing **panel {default_label or active + 1}** "
               f"({active + 1}/{total})")

    mode_key = f"_panel_slot_mode_{active}"
    st.session_state.setdefault(mode_key, current.get("mode", "plot"))
    st.radio("Slot type", ["plot", "empty"], key=mode_key, horizontal=True,
             format_func=lambda s: {"plot": "Plot",
                                    "empty": "Empty (placeholder)"}[s],
             on_change=_set_mode_cb, args=(active, mode_key))

    label_key = f"_panel_custom_label_{active}"
    st.session_state.setdefault(label_key, current.get("label", ""))
    st.text_input("Custom label (empty = use style)", key=label_key,
                  placeholder=default_label or "(none)",
                  on_change=_set_label_cb, args=(active, label_key))


# ---------------------------------------------------------------------------
# Figure
# ---------------------------------------------------------------------------

def _sheet_frame(sheet: str) -> pd.DataFrame:
    ctx_bytes = st.session_state.get("_file_bytes")
    ctx_key = st.session_state.get("_file_key")
    return dataio.load_sheet(ctx_bytes, ctx_key, sheet)


def build_figure(ctx: dataio.DataContext) -> matplotlib.figure.Figure:
    """Compose the multi-panel figure from the stored panel configs."""
    rows = int(st.session_state.get("ph_rows", 2))
    cols = int(st.session_state.get("ph_cols", 2))
    total = rows * cols
    stored = st.session_state.get(PANELS_KEY) or []

    specs: list[dict] = []
    for index in range(total):
        panel = stored[index] if index < len(stored) else {"mode": "empty"}
        if panel.get("mode", "plot") == "empty":
            specs.append({"mode": "empty", "label": panel.get("label", "")})
            continue
        specs.append(_panel_spec(ctx, panel, index))

    return xpanel.make_panel_figure(
        specs, rows=rows, cols=cols,
        fig_width=float(st.session_state.get("ph_fig_width", 12)),
        fig_height=float(st.session_state.get("ph_fig_height", 9)),
        wspace=float(st.session_state.get("ph_wspace", 0.30)),
        hspace=float(st.session_state.get("ph_hspace", 0.40)),
        label_style=st.session_state.get("ph_label_style", "A"),
        label_fontsize=float(st.session_state.get("ph_label_fontsize", 16)),
        label_fontweight=st.session_state.get("ph_label_fontweight", "bold"),
        label_x_offset=float(st.session_state.get("ph_label_x_offset", -0.12)),
        label_y_offset=float(st.session_state.get("ph_label_y_offset", 1.03)),
    )


def _panel_spec(ctx: dataio.DataContext, panel: dict, index: int) -> dict:
    sheet = panel.get("sheet") or ctx.sheets[0]
    if sheet not in ctx.sheets:
        sheet = ctx.sheets[0]

    frame = dataio.load_sheet(ctx.file_bytes, ctx.key, sheet)
    if frame.empty:
        return {"mode": "plot", "df": frame, "config": {},
                "label": panel.get("label", "")}

    conditions = panel.get("cond_order") or dataio.categories(frame["condition"])
    treatments = panel.get("treat_order") or dataio.categories(frame["treatment"])
    selection = panel.get("filter") or conditions
    frame = dataio.apply_selection(frame, selection, treatments)

    touched = set(panel.get("touched", []))
    title = panel.get("ps_title", "") if "ps_title" in touched else sheet
    ylabel = panel.get("ps_ylabel", "") if "ps_ylabel" in touched else sheet

    stat_rows = panel.get("stat_rows") or []
    stat_results = pd.DataFrame(stat_rows) if stat_rows else None

    config = figspec.draw_kwargs(
        panel,
        n_treatments=len(dataio.categories(frame["treatment"])),
        title=title,
        ylabel=ylabel or sheet,
        stat_results=stat_results,
    )
    ylim, xlim = figspec.axis_limits(panel)

    return {"mode": "plot", "df": frame, "config": config,
            "ylim": ylim, "xlim": xlim, "label": panel.get("label", "")}
