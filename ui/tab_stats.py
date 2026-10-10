"""ui/tab_stats.py — test selection and bracket styling."""

from __future__ import annotations

import pandas as pd
import streamlit as st

import dataio
import settings

TEST_LABELS = {
    "ttest":         "t-test vs reference condition",
    "tukey":         "ANOVA + Tukey HSD (all pairs)",
    "two_way_anova": "Two-way ANOVA + Sidak",
}
AXIS_LABELS = {
    "conditions": "Conditions (per treatment)",
    "treatments": "Treatments (per condition)",
    "cells":      "All cell means — global Sidak",
}
REF_COND_KEY = "_stat_reference_condition"


def _reset_compare_axis_cb() -> None:
    """"cells" only exists for the two-way ANOVA; drop it when leaving that test.

    Runs as an on_change callback so the value is corrected before the radio is
    built, instead of being written mid-run and needing a rerun to show up.
    """
    if (st.session_state.get("ps_test_mode") != "two_way_anova"
            and st.session_state.get("ps_compare_axis") == "cells"):
        st.session_state["ps_compare_axis"] = "conditions"


def render(ctx: dataio.DataContext) -> dict:
    """Draw the Stats tab.  Returns the computed tables (or Nones)."""
    base_type = str(settings.get("ps_plot_type")).split("+")[0]
    result: dict = {"anova_table": None, "stat_results_all": None}

    if base_type == "line":
        st.info("Statistical annotations are not available for line plots.")

    run_stats = st.checkbox("Run statistical tests", key="ps_run_stats",
                            disabled=base_type == "line")
    if not run_stats or base_type == "line":
        return result

    test_mode = st.radio("Test", list(TEST_LABELS), key="ps_test_mode",
                         format_func=TEST_LABELS.get,
                         on_change=_reset_compare_axis_cb)

    compare_axis = settings.get("ps_compare_axis")
    if test_mode in ("tukey", "two_way_anova"):
        options = (["conditions", "treatments", "cells"]
                   if test_mode == "two_way_anova"
                   else ["conditions", "treatments"])
        compare_axis = st.radio("Compare", options, key="ps_compare_axis",
                                format_func=AXIS_LABELS.get, horizontal=True)

    st.checkbox("Show p-values instead of stars", key="ps_show_pvalue")
    col_sig, col_fold = st.columns(2)
    with col_sig:
        st.checkbox("Show significance", key="ps_show_significance")
    with col_fold:
        st.checkbox("Show fold change", key="ps_show_fold_change")

    if test_mode == "ttest":
        ref_cond = st.selectbox("Reference condition", ctx.conditions,
                                key=f"{REF_COND_KEY}::{ctx.sheet}")
    else:
        ref_cond = ctx.conditions[0]

    try:
        anova_table, posthoc = dataio.run_stat_test(
            ctx.file_bytes, ctx.key, ctx.sheet, test_mode, compare_axis, ref_cond
        )
        result["anova_table"] = anova_table
        result["stat_results_all"] = posthoc
    except Exception as exc:
        st.error(f"Statistical test failed: {exc}")

    st.caption("Bracket style")
    col_lw, col_fs = st.columns(2)
    with col_lw:
        st.slider("Line width", 0.3, 3.0, key="ps_bracket_linewidth", step=0.1)
    with col_fs:
        st.slider("Font size", 6.0, 18.0, key="ps_bracket_fontsize", step=0.5)

    return result
