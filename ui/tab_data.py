"""ui/tab_data.py — which conditions and treatments to show, and in what order.

The sheet selector and the preset row used to live here; they moved above the
tabs (``ui/sidebar_top.py``) because they are the most-used controls in the app.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

import dataio
import settings

PREVIEW_KEY = "_show_preview"


def render(ctx: dataio.DataContext, *, scope: str = "") -> dict:
    """Draw the Data tab.  Returns the selections the rest of the app needs.

    *scope* namespaces the per-sheet widget keys; panel mode passes the panel
    index so each slot keeps its own filter and ordering.
    """
    st.caption("Conditions to show")

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
    # A rebuilt multiselect falls back to an empty selection, which would leave
    # the app reporting that no conditions are selected.
    settings.reassert(filter_key)
    selected = st.multiselect(
        "Show conditions",
        options=ctx.conditions,
        key=filter_key,
        label_visibility="collapsed",
        **default,
    )
    if len(selected) < len(ctx.conditions):
        st.caption(f"Showing {len(selected)} of {len(ctx.conditions)}.")

    st.caption("Treatments to show")
    treat_key = settings.filter_key(f"{scope}::{ctx.sheet}::treatments",
                                    ctx.treatments)
    treat_default = ({} if treat_key in st.session_state
                     else {"default": list(ctx.treatments)})
    settings.reassert(treat_key)
    selected_treatments = st.multiselect(
        "Show treatments",
        options=ctx.treatments,
        key=treat_key,
        label_visibility="collapsed",
        **treat_default,
    )

    conditions, treatments = _render_reorder(ctx, scope)
    # The order list doubles as the selection: dataio.apply_selection drops
    # every treatment that is not in it, and each panel stores it as-is.
    treatments = [t for t in treatments if t in set(selected_treatments)]

    st.divider()
    show_preview = st.toggle("Rename labels & show raw data", key=PREVIEW_KEY)

    return {
        "selected_conditions": selected,
        "selected_treatments": selected_treatments,
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
    with st.expander("Reorder", icon=":material/swap_vert:", expanded=False):
        st.caption("Change the order number to reorder items in the plot.")
        conditions = _order_editor(
            "Condition", ctx.conditions, f"_cond_order::{scope}::{ctx.sheet}")
        treatments = _order_editor(
            "Treatment", ctx.treatments, f"_treat_order::{scope}::{ctx.sheet}")

    return conditions, treatments


def _order_editor(label: str, values: list, key: str) -> list:
    st.caption("Conditions (x-axis)" if label == "Condition"
               else "Treatments (legend)")
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
