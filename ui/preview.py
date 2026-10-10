"""ui/preview.py — display-label renaming and the raw-data preview."""

from __future__ import annotations

import pandas as pd
import streamlit as st

import dataio


def render_renames(
    conditions: list,
    treatments: list,
    *,
    scope: str,
) -> tuple[dict, dict]:
    """Editable display labels.  Returns ``(cond_rename, treat_rename)``.

    Editor keys include the scope (sheet, and panel when in panel mode) so that
    switching sheets does not replay the previous sheet's edits onto whichever
    labels now occupy the same rows.
    """
    st.subheader("✏️ Rename labels")
    left, right = st.columns(2)

    with left:
        st.caption("Condition labels (x-axis)")
        cond_rename = _rename_editor(conditions, f"_cond_rename::{scope}")
    with right:
        st.caption("Treatment labels (legend)")
        treat_rename = _rename_editor(treatments, f"_treat_rename::{scope}")

    return cond_rename, treat_rename


def _rename_editor(values: list, key: str) -> dict:
    edited = st.data_editor(
        pd.DataFrame({"Original": values, "Display": values}),
        width="stretch",
        hide_index=True,
        column_config={"Original": st.column_config.TextColumn(disabled=True)},
        key=key,
    )
    return {
        str(original): (str(display) if display else str(original))
        for original, display in zip(edited["Original"], edited["Display"])
    }


def render_data(df: pd.DataFrame) -> None:
    st.subheader("Summary statistics")
    st.dataframe(dataio.summary_table(df), width="stretch")
    with st.expander("All individual values"):
        st.dataframe(df.sort_values(["condition", "treatment", "replicate"]),
                     width="stretch")
