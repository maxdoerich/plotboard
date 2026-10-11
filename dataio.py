"""
dataio.py — cached workbook access and the DataFrame reshaping the UI needs.

Everything here is pure with respect to Streamlit widgets: it takes bytes and
DataFrames and returns DataFrames, so the caching decorators are the only
Streamlit dependency.

Caching keys on a short digest of the file rather than the bytes themselves —
``@st.cache_data`` hashes every argument on every call, and re-hashing a whole
workbook on each rerun is pure overhead when the content cannot have changed.
Arguments prefixed with an underscore are excluded from that hashing.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

import pandas as pd
import streamlit as st

import parser as xparser
import stats as xstats


@dataclass
class DataContext:
    """What every sidebar tab needs to know about the workbook being plotted."""

    file_bytes: bytes
    file_label: str
    key: str
    sheets: list[str]
    sheet: str
    df: pd.DataFrame
    conditions: list = field(default_factory=list)
    treatments: list = field(default_factory=list)

    @property
    def n_treatments(self) -> int:
        return len(self.treatments)

    @property
    def default_title(self) -> str:
        return f"{self.file_label}  ·  {self.sheet}" if self.file_label else self.sheet

STAT_COLUMNS_CONDITION = ("condition", "reference", "group_A", "group_B",
                          "cond_A", "cond_B")
STAT_COLUMNS_TREATMENT = ("treatment", "treat_A", "treat_B")


def file_key(file_bytes: bytes) -> str:
    """Short stable identifier for a workbook's contents."""
    return hashlib.blake2b(file_bytes, digest_size=16).hexdigest()


# ---------------------------------------------------------------------------
# Cached loading
# ---------------------------------------------------------------------------

@st.cache_resource(show_spinner="Opening workbook…", max_entries=3)
def _workbook(_file_bytes: bytes, key: str):
    return xparser.load_workbook(_file_bytes)


@st.cache_data(show_spinner=False)
def sheet_names(_file_bytes: bytes, key: str) -> list[str]:
    return xparser.sheet_names(_workbook(_file_bytes, key))


@st.cache_data(show_spinner="Parsing sheet…")
def load_sheet(_file_bytes: bytes, key: str, sheet: str) -> pd.DataFrame:
    return xparser.parse_sheet(_workbook(_file_bytes, key), sheet)


@st.cache_data(show_spinner="Running statistical tests…")
def run_stat_test(
    _file_bytes: bytes,
    key: str,
    sheet: str,
    test_mode: str,
    compare_axis: str,
    ref_cond: str,
) -> tuple[pd.DataFrame | None, pd.DataFrame | None]:
    """Return ``(anova_table, posthoc_df)``.

    Cached so that restyling the plot does not re-run Tukey or the ANOVA, which
    are by far the most expensive thing the app does.
    """
    df = load_sheet(_file_bytes, key, sheet)
    if test_mode == "ttest":
        return None, xstats.run_ttests_vs_reference(df, ref_cond)
    if test_mode == "two_way_anova":
        return xstats.run_two_way_anova_sidak(df, compare_axis)
    if compare_axis == "conditions":
        return None, xstats.run_tukey(df)
    return None, xstats.run_tukey_between_treatments(df)


# ---------------------------------------------------------------------------
# Reshaping
# ---------------------------------------------------------------------------

def categories(series: pd.Series) -> list:
    """Category order of a column, falling back to first-seen order."""
    if hasattr(series, "cat"):
        return list(series.cat.categories)
    return list(series.unique())


def apply_selection(
    df: pd.DataFrame,
    conditions: list,
    treatments: list,
) -> pd.DataFrame:
    """Filter to the chosen conditions and treatments, in the chosen order.

    *treatments* is both the selection and the legend order; a list with no
    known treatment in it keeps them all.
    """
    known = set(categories(df["condition"]))
    conditions = [c for c in conditions if c in known] or list(known)
    treat_known = [t for t in treatments if t in set(categories(df["treatment"]))]

    keep = df["condition"].isin(conditions)
    if treat_known:
        keep &= df["treatment"].isin(treat_known)
    out = df[keep].copy()
    out["condition"] = pd.Categorical(out["condition"], categories=conditions,
                                      ordered=True)
    out["treatment"] = pd.Categorical(out["treatment"],
                                      categories=treat_known or treatments,
                                      ordered=True)
    return out


def apply_renames(
    df: pd.DataFrame,
    cond_rename: dict[str, str],
    treat_rename: dict[str, str],
) -> pd.DataFrame:
    """Return a copy with display labels applied; *df* is left untouched."""
    out = df.copy()
    if any(new != old for old, new in cond_rename.items()):
        order = _renamed_order(categories(df["condition"]), cond_rename)
        out["condition"] = pd.Categorical(
            [cond_rename.get(c, c) for c in out["condition"]],
            categories=order, ordered=True,
        )
    if any(new != old for old, new in treat_rename.items()):
        order = _renamed_order(categories(df["treatment"]), treat_rename)
        out["treatment"] = pd.Categorical(
            [treat_rename.get(t, t) for t in out["treatment"]],
            categories=order, ordered=True,
        )
    return out


def rename_stat_results(
    stat_results: pd.DataFrame | None,
    cond_rename: dict[str, str],
    treat_rename: dict[str, str],
) -> pd.DataFrame | None:
    """Map a stat table's group names through the display renames.

    Significance brackets are positioned by looking each group name up in the
    plotted axes.  Without this the brackets carry the original names, every
    lookup misses, and they silently vanish the moment a label is renamed.
    """
    if stat_results is None or stat_results.empty:
        return stat_results
    if not cond_rename and not treat_rename:
        return stat_results

    out = stat_results.copy()
    for col in STAT_COLUMNS_CONDITION:
        if col in out.columns:
            out[col] = out[col].map(lambda v: cond_rename.get(v, v))
    for col in STAT_COLUMNS_TREATMENT:
        if col in out.columns:
            out[col] = out[col].map(lambda v: treat_rename.get(v, v))
    return out


def summary_table(df: pd.DataFrame) -> pd.DataFrame:
    """Mean / SD / N per (condition, treatment)."""
    return (
        df.groupby(["condition", "treatment"], observed=True)["value"]
        .agg(["mean", "std", "count"])
        .rename(columns={"mean": "Mean", "std": "SD", "count": "N"})
        .reset_index()
    )


def min_replicates(df: pd.DataFrame) -> int:
    counts = df.groupby(["condition", "treatment"], observed=True)["value"].count()
    return int(counts.min()) if len(counts) else 0


def _renamed_order(original_order: list, rename: dict[str, str]) -> list:
    """Preserve order while dropping duplicates that renaming may introduce."""
    seen: dict[str, None] = {}
    for value in original_order:
        seen.setdefault(rename.get(value, value), None)
    return list(seen)
