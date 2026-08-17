"""ui/tab_data.py — sheet choice, condition filter, ordering, presets."""

from __future__ import annotations

import pandas as pd
import streamlit as st

import dataio
import presets as xpresets
import settings

PREVIEW_KEY = "_show_preview"
PRESET_NAME_KEY = "_preset_name_input"
PRESET_CHOICE_KEY = "_preset_choice"


def render(ctx: dataio.DataContext, *, scope: str = "") -> dict:
    """Draw the Data tab.  Returns the selections the rest of the app needs.

    *scope* namespaces the per-sheet widget keys; panel mode passes the panel
    index so each slot keeps its own filter and ordering.
    """
    st.selectbox("Sheet", ctx.sheets, key="_sheet_select")

    st.caption("Filter")
    # One widget key per (scope, sheet, condition set): a new sheet gets a fresh
    # multiselect that defaults to all of its conditions, and coming back to a
    # sheet restores the selection left there.  The alternative — overwriting
    # the selection in session_state — needed an st.rerun() to take effect,
    # which is what used to wipe every other setting on a sheet change.
    filter_key = settings.filter_key(f"{scope}::{ctx.sheet}", ctx.conditions)
    # Passing default= for a key that already holds a value makes Streamlit warn
    # about the two competing; the stored selection is the one we want anyway.
    default = ({} if filter_key in st.session_state
               else {"default": list(ctx.conditions)})
    selected = st.multiselect(
        "Show conditions",
        options=ctx.conditions,
        key=filter_key,
        label_visibility="collapsed",
        **default,
    )

    conditions, treatments = _render_reorder(ctx, scope)
    _render_presets(ctx)

    show_preview = st.checkbox("Show / edit labels & raw data", key=PREVIEW_KEY)

    return {
        "selected_conditions": selected,
        "conditions": conditions,
        "treatments": treatments,
        "show_preview": show_preview,
    }


# ---------------------------------------------------------------------------
# Reorder
# ---------------------------------------------------------------------------

def _render_reorder(ctx: dataio.DataContext, scope: str) -> tuple[list, list]:
    """Order editors for conditions and treatments.

    Editor keys are scoped to the sheet: sharing one key across sheets made
    Streamlit replay the previous sheet's row edits onto whatever rows happened
    to sit at the same index.
    """
    with st.expander("↕ Reorder", expanded=False):
        st.caption("Change the order number to reorder items in the plot.")
        left, right = st.columns(2)

        with left:
            st.caption("Conditions (x-axis)")
            conditions = _order_editor(
                "Condition", ctx.conditions, f"_cond_order::{scope}::{ctx.sheet}")
        with right:
            st.caption("Treatments (legend)")
            treatments = _order_editor(
                "Treatment", ctx.treatments, f"_treat_order::{scope}::{ctx.sheet}")

    return conditions, treatments


def _order_editor(label: str, values: list, key: str) -> list:
    edited = st.data_editor(
        pd.DataFrame({label: values, "Order": range(1, len(values) + 1)}),
        width="stretch",
        hide_index=True,
        column_config={
            label: st.column_config.TextColumn(disabled=True),
            "Order": st.column_config.NumberColumn(min_value=1, step=1),
        },
        key=key,
    )
    return edited.sort_values("Order", kind="stable")[label].tolist()


# ---------------------------------------------------------------------------
# Presets
# ---------------------------------------------------------------------------

def _apply_preset_cb(name: str) -> None:
    settings.apply_preset(name)
    st.toast(f"Loaded preset '{name}'", icon="✅")


def _save_preset_cb() -> None:
    name = str(st.session_state.get(PRESET_NAME_KEY, "")).strip()
    if not name:
        st.toast("Enter a preset name first.", icon="⚠️")
        return
    # snapshot() reads through to the durable store, so a setting whose widget
    # is currently hidden (bar options while a box plot is shown) is saved at
    # its real value instead of raising KeyError.
    xpresets.save(name, settings.snapshot())
    st.session_state[PRESET_NAME_KEY] = ""
    st.toast(f"Saved preset '{name}'", icon="💾")


def _delete_preset_cb(name: str) -> None:
    xpresets.delete(name)
    st.toast(f"Deleted preset '{name}'", icon="🗑")


def _set_startup_cb(name: str) -> None:
    xpresets.set_startup_preset(name)
    st.toast(f"'{name}' will load on startup", icon="⭐")


def _render_presets(ctx: dataio.DataContext) -> None:
    with st.expander("💾 Presets", expanded=False):
        saved = xpresets.list_presets()
        startup = xpresets.get_startup_preset()

        if saved:
            col_select, col_load = st.columns([3, 1])
            with col_select:
                choice = st.selectbox(
                    "Saved presets", saved, label_visibility="collapsed",
                    key=PRESET_CHOICE_KEY,
                    format_func=lambda n: f"★ {n}" if n == startup else n,
                )
            with col_load:
                st.button("Load", width="stretch",
                          on_click=_apply_preset_cb, args=(choice,))

            col_startup, col_delete = st.columns(2)
            with col_startup:
                st.button("⭐ Set as startup", width="stretch",
                          help="Load this preset automatically when a file is opened.",
                          on_click=_set_startup_cb, args=(choice,))
            with col_delete:
                st.button("🗑 Delete", width="stretch",
                          on_click=_delete_preset_cb, args=(choice,))
        else:
            st.caption("No saved presets yet.")

        st.divider()

        col_name, col_save = st.columns([3, 1])
        with col_name:
            st.text_input("Preset name", placeholder="e.g. Publication style",
                          label_visibility="collapsed", key=PRESET_NAME_KEY)
        with col_save:
            st.button("Save", width="stretch", on_click=_save_preset_cb)
