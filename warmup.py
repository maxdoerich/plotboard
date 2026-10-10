"""
warmup.py — load the plotting stack while the user is still choosing a file.

seaborn (which pulls in ``scipy.stats``), pandas, openpyxl and matplotlib take
5–10 s to import. Nothing on the empty landing page needs any of them, so
``app.py`` renders that page with only Streamlit loaded and calls ``start()``,
which imports them — and draws one throwaway figure, to prime the font lookup
and seaborn's first-call setup — on a background thread.

``wait()`` must be called before ``app.py`` imports any of these modules itself.
The main thread then never imports concurrently with the warm-up thread, which
keeps clear of the import-lock edge cases that come with circular imports inside
large libraries. The thread starts once per server process; later sessions find
the modules already in ``sys.modules``.
"""

from __future__ import annotations

import io
import threading

_thread: threading.Thread | None = None
_start_lock = threading.Lock()


def _warm() -> None:
    try:
        import pandas as pd

        import dataio  # noqa: F401  (pulls in parser, stats, openpyxl, scipy.stats)
        import figspec
        import panel  # noqa: F401
        import plotter
        import presets
        import utils  # noqa: F401
        from ui import export, panels, preview, stats_table  # noqa: F401
        from ui import tab_axes, tab_data, tab_plot, tab_stats, tab_text  # noqa: F401

        # The first figure a process draws is ~1 s slower than the rest (font
        # lookup, seaborn's first-call setup). Pay that here instead.
        df = pd.DataFrame({
            "condition": pd.Categorical(["a", "a", "b", "b"] * 2),
            "treatment": pd.Categorical(["x"] * 4 + ["y"] * 4),
            "replicate": [1, 2] * 4,
            "value": [1.0, 1.2, 2.0, 2.1, 1.5, 1.4, 2.5, 2.7],
        })
        fig = plotter.make_figure(
            df, **figspec.draw_kwargs(dict(presets.DEFAULTS), n_treatments=2))
        fig.savefig(io.BytesIO(), format="png")
    except Exception:
        # Only a head start: app.py imports the same modules after wait(), so a
        # genuine failure is still reported there, in the page.
        pass


def start() -> None:
    """Begin warming up in the background. Safe to call on every run."""
    global _thread
    with _start_lock:
        if _thread is None:
            _thread = threading.Thread(target=_warm, name="plotboard-warmup",
                                       daemon=True)
            _thread.start()


def wait() -> None:
    """Block until the warm-up is done (returns at once if it already is)."""
    if _thread is not None:
        _thread.join()
