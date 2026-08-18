"""
ui/sidebar_top.py — everything above the settings tabs.

The file input, the sheet selector and the preset row live here rather than
inside a tab. All three are used constantly — the sheet selector most of all —
and burying them one click deep meant the two controls with the highest traffic
were the hardest to reach while the Data tab held only two widgets.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

import dataio
import presets as xpresets
import settings

PRESET_CHOICE_KEY = "_preset_choice"
PRESET_NAME_KEY = "_preset_name_input"


def render_file_input() -> tuple[bytes | None, str]:
    """File uploader plus a local-path fallback.  Returns ``(bytes, label)``."""
    st.subheader("📂 Data", anchor=False)
    upload = st.file_uploader("Upload .xlsx file", type=["xlsx"])
    local_path = st.text_input(
        "…or enter a local file path",
        placeholder=r"C:\Users\you\data\results.xlsx",
    )

    if upload is not None:
        # getvalue() rather than read(): it does not consume the stream, so a
        # rerun cannot come back with an empty buffer.
        return upload.getvalue(), upload.name

    text = local_path.strip().strip('"')
    if text:
        path = Path(text)
        if path.exists() and path.suffix.lower() == ".xlsx":
            return path.read_bytes(), path.name
        st.error("File not found or not an .xlsx file.")

    return None, ""


def render_sheet(all_sheets: list[str]) -> str:
    """Sheet selector.  Rendered before the data loads, so it returns the name."""
    return st.selectbox("Sheet", all_sheets, key="_sheet_select")


def render_shape(ctx: dataio.DataContext) -> None:
    """One line describing what actually parsed out of the sheet.

    This layout reads GraphPad's grouped format by position, so a stray header
    cell silently turns four treatments into one. Stating the shape means that
    shows up here instead of being something you have to infer from a wrong plot.
    """
    counts = ctx.df.groupby(["condition", "treatment"], observed=True)["value"].count()
    if counts.empty:
        return
    low, high = int(counts.min()), int(counts.max())
    replicates = f"{low}" if low == high else f"{low}–{high}"
    st.caption(
        f"**{len(ctx.conditions)}** conditions · **{len(ctx.treatments)}** "
        f"treatments · **{replicates}** replicates"
    )


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


def _reset_cb() -> None:
    settings.update(dict(xpresets.DEFAULTS), mark_touched=False)
    settings.restore_touched([])
    st.toast("Settings reset to defaults", icon="↩️")


def render_presets() -> None:
    """Compact preset row: pick, Load, and the rest behind a popover."""
    saved = xpresets.list_presets()
    startup = xpresets.get_startup_preset()

    col_choice, col_load, col_more = st.columns([5, 3, 2],
                                                vertical_alignment="bottom")
    choice = ""
    with col_choice:
        if saved:
            choice = st.selectbox(
                "Preset", saved, key=PRESET_CHOICE_KEY,
                format_func=lambda n: f"★ {n}" if n == startup else n,
                label_visibility="collapsed",
            )
        else:
            st.caption("No saved presets yet.")
    with col_load:
        st.button("Load", width="stretch", disabled=not saved,
                  on_click=_apply_preset_cb, args=(choice,))
    with col_more:
        with st.popover("⋯", width="stretch", help="Save, delete, reset"):
            st.text_input("Save current settings as",
                          placeholder="e.g. Publication style",
                          key=PRESET_NAME_KEY)
            st.button("💾 Save preset", width="stretch",
                      on_click=_save_preset_cb)
            st.divider()
            if saved:
                st.caption(f"Selected: **{choice}**")
                st.button("⭐ Load this preset on startup", width="stretch",
                          on_click=_set_startup_cb, args=(choice,))
                st.button("🗑 Delete this preset", width="stretch",
                          on_click=_delete_preset_cb, args=(choice,))
                st.divider()
            st.button("↩️ Reset all settings to defaults", width="stretch",
                      on_click=_reset_cb)
