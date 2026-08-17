"""ui/stats_table.py — the comparison table that chooses which brackets to draw."""

from __future__ import annotations

import pandas as pd
import streamlit as st

SHOW_COLUMN = "Show bracket"

_LAYOUTS = {
    "cells": (
        ["cond_A", "treat_A", "cond_B", "treat_B", "p-adj", "stars", SHOW_COLUMN],
        {"cond_A": "Condition A", "treat_A": "Treatment A",
         "cond_B": "Condition B", "treat_B": "Treatment B", "stars": "Sig."},
    ),
    "treatments": (
        ["condition", "group_A", "group_B", "p-adj", "stars", SHOW_COLUMN],
        {"condition": "Condition", "group_A": "Treatment A",
         "group_B": "Treatment B", "stars": "Sig."},
    ),
    "ttest": (
        ["treatment", "reference", "condition", "p-adj", "stars", SHOW_COLUMN],
        {"treatment": "Treatment", "reference": "Reference",
         "condition": "Condition", "stars": "Sig."},
    ),
    "conditions": (
        ["treatment", "group_A", "group_B", "p-adj", "stars", SHOW_COLUMN],
        {"treatment": "Treatment", "group_A": "Condition A",
         "group_B": "Condition B", "stars": "Sig."},
    ),
}


def render(
    stat_results_all: pd.DataFrame | None,
    *,
    test_mode: str,
    compare_axis: str,
    sheet: str,
) -> pd.DataFrame | None:
    """Draw the table and return the rows the user ticked, or None.

    Rendered into a container placed below the plot but *executed* before it,
    so the plot in the same run already reflects the current ticks.  The old
    version had to reconstruct the selection from Streamlit's internal
    ``edited_rows`` dict to achieve that; reading the editor's return value is
    both simpler and not dependent on a private format.
    """
    if stat_results_all is None:
        return None
    if stat_results_all.empty:
        st.info("No comparisons could be computed "
                "(check that all groups have ≥ 2 replicates).")
        return None

    st.subheader("📋 Statistical comparisons")
    st.caption("Tick a row to draw its bracket on the plot.")

    ordered = (stat_results_all
               .sort_values("p_value", kind="stable")
               .reset_index(drop=True))

    display = ordered.copy()
    display["p-adj"] = display["p_value"].map(
        lambda p: f"{p:.4f}" if p >= 0.0001 else "<0.0001")
    display[SHOW_COLUMN] = False

    layout_key = compare_axis if compare_axis in ("cells", "treatments") else (
        "ttest" if test_mode == "ttest" else "conditions")
    columns, labels = _LAYOUTS[layout_key]

    table = display[[c for c in columns if c in display.columns]].rename(
        columns=labels)

    column_config = {c: st.column_config.TextColumn(c, disabled=True)
                     for c in table.columns if c != SHOW_COLUMN}
    column_config[SHOW_COLUMN] = st.column_config.CheckboxColumn(
        SHOW_COLUMN, help="Tick to draw a bracket on the plot")

    edited = st.data_editor(
        table,
        column_config=column_config,
        width="stretch",
        hide_index=True,
        key=f"_stat_editor::{test_mode}::{compare_axis}::{sheet}",
    )

    mask = edited[SHOW_COLUMN].fillna(False).astype(bool).to_numpy()
    selected = ordered[mask]
    return selected if not selected.empty else None


def render_anova(anova_table: pd.DataFrame | None) -> None:
    """Show the two-way ANOVA table, tolerating pingouin's column naming."""
    if anova_table is None or anova_table.empty:
        return

    st.subheader("Two-way ANOVA table")
    p_col = next((c for c in ("p-unc", "p_unc", "pvalue")
                  if c in anova_table.columns), None)
    df_col = next((c for c in ("DF", "df", "ddof1")
                   if c in anova_table.columns), None)
    keep = [c for c in ("Source", "SS", df_col, "MS", "F", p_col)
            if c and c in anova_table.columns]

    display = anova_table[keep].copy()
    if p_col:
        display[p_col] = display[p_col].map(
            lambda p: f"{p:.4f}" if pd.notna(p) and p >= 0.0001
            else ("<0.0001" if pd.notna(p) else "—"))
        display = display.rename(columns={p_col: "p-value"})
    if df_col:
        display = display.rename(columns={df_col: "df"})
    st.dataframe(display, width="stretch")
