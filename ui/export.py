"""
ui/export.py — download buttons and the batch "plot all sheets" export.

Export bytes are produced lazily.  ``st.download_button`` accepts a callable
for ``data``, which Streamlit registers as a deferred file and invokes only
when the user actually clicks.  The previous version rendered PNG 300, PNG 600,
SVG and PDF on *every* rerun — about 1.7 s of encoding per slider drag, thrown
away unless a button happened to be clicked, and roughly nine tenths of the
app's per-interaction latency.
"""

from __future__ import annotations

import io
import zipfile
from typing import Callable

import matplotlib
import streamlit as st

import dataio
import figspec
import plotter
import settings
import utils

ZIP_KEY = "_batch_export_zip"
ZIP_NAME_KEY = "_batch_export_name"

_FORMATS: list[tuple[str, str, str, int]] = [
    # label, format, mime, dpi
    ("⬇️ PNG 300 DPI", "png", "image/png", 300),
    ("⬇️ PNG 600 DPI", "png", "image/png", 600),
    ("⬇️ SVG", "svg", "image/svg+xml", 0),
    ("⬇️ PDF", "pdf", "application/pdf", 0),
]


@st.fragment
def render_downloads(fig: matplotlib.figure.Figure, base_name: str) -> None:
    """Background options plus the four download buttons.

    A fragment, so changing the export background re-runs only this block
    instead of rebuilding the figure and re-running the whole page.
    """
    columns = st.columns(len(_FORMATS))
    background = st.columns([1, 1, 4])

    with background[0]:
        transparent = st.checkbox("Transparent background",
                                  key="ps_export_transparent")
    with background[1]:
        st.color_picker("Background color", key="ps_export_bg",
                        disabled=transparent, label_visibility="collapsed")

    export_kwargs = figspec.export_kwargs(settings.snapshot())

    for column, (label, fmt, mime, dpi) in zip(columns, _FORMATS):
        suffix = f"_{dpi}dpi" if dpi else ""
        with column:
            st.download_button(
                label,
                data=_deferred(fig, fmt, dpi or 300, export_kwargs),
                file_name=f"{base_name}{suffix}.{fmt}",
                mime=mime,
                width="stretch",
            )


def _deferred(fig, fmt: str, dpi: int, export_kwargs: dict) -> Callable[[], bytes]:
    """Render *fig* only when the download is actually clicked."""
    return lambda: utils.fig_to_bytes(fig, fmt, dpi, **export_kwargs)


# ---------------------------------------------------------------------------
# Batch export
# ---------------------------------------------------------------------------

def render_batch(ctx: dataio.DataContext) -> None:
    with st.expander("📦 Batch export — plot all sheets", expanded=False):
        st.caption(
            "Generates one PNG (300 DPI) per sheet and bundles them into a ZIP "
            "archive. The current plot settings are applied to every sheet."
        )
        if st.button("Generate ZIP of all sheets"):
            _build_zip(ctx)

        if st.session_state.get(ZIP_KEY):
            # Held in session state so the button survives the rerun that
            # clicking it triggers — previously the download button vanished
            # as soon as the page re-ran.
            st.download_button(
                "⬇️ Download ZIP",
                data=st.session_state[ZIP_KEY],
                file_name=st.session_state.get(ZIP_NAME_KEY, "sheets.zip"),
                mime="application/zip",
            )


def _build_zip(ctx: dataio.DataContext) -> None:
    current = settings.snapshot()
    buffer = io.BytesIO()
    progress = st.progress(0.0, text="Plotting…")

    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for index, sheet in enumerate(ctx.sheets, start=1):
            progress.progress(index / len(ctx.sheets), text=f"Plotting {sheet}…")
            frame = dataio.load_sheet(ctx.file_bytes, ctx.key, sheet)
            if frame.empty:
                continue
            # Batch output goes through the same spec builder as the preview,
            # so axis limits, tick styling and line options are no longer
            # silently dropped from the exported figures.
            treatments = dataio.categories(frame["treatment"])
            ylim, xlim = figspec.axis_limits(current)
            figure = plotter.make_figure(
                frame,
                **figspec.figure_size(current),
                ylim=ylim,
                xlim=xlim,
                **figspec.draw_kwargs(current, n_treatments=len(treatments),
                                      title=sheet, ylabel=sheet),
            )
            archive.writestr(f"{sheet}.png", utils.fig_to_bytes(
                figure, "png", 300, **figspec.export_kwargs(current)))

    progress.empty()
    buffer.seek(0)
    st.session_state[ZIP_KEY] = buffer.getvalue()
    st.session_state[ZIP_NAME_KEY] = (
        f"{ctx.file_label.replace('.xlsx', '') or 'plots'}_all_sheets.zip")
