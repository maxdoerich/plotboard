"""
settings.py — the single source of truth for every ``ps_*`` plot setting.

Why this module exists
----------------------
Streamlit stores widget values in ``st.session_state`` keyed by the widget's
``key=``, but it *deletes* those entries at the end of any run in which the
widget was not rendered ("widget culling").  Two things follow from that:

1.  A setting whose widget is hidden by a conditional (bar-only options while a
    box plot is selected) is wiped, and reappears at its default when the
    widget comes back.
2.  If a run ends early — ``st.rerun()`` before the sidebar is built — *no*
    widget renders, so *every* setting is wiped at once.  That was the cause of
    the "change sheet, everything jumps to minimum" bug: the app called
    ``st.rerun()`` on sheet change before any widget had been instantiated.

The fix is to stop treating widget state as storage.  This module keeps a
plain dict (``st.session_state["_settings_store"]``) that Streamlit never
touches, and mirrors it into the widget keys at the start of every run:

    run start ──► hydrate()   store ──► session_state (fills culled keys)
    ...widgets render and update session_state...
    sidebar end ─► persist()  session_state ──► store

Because the store is a normal session-state value it survives culling, early
``st.stop()``, and hidden widgets alike.  Settings are therefore sticky:
switching plot type away and back keeps the settings you had.

``hydrate()`` re-asserts *every* setting rather than only the missing ones, so
the browser is always told each widget's value.  Left to itself the browser
falls back on the widget's declared default whenever it has to build the widget
afresh, and for a slider that default is its minimum — see ``hydrate``.

Rules for callers
-----------------
* ``hydrate()`` must run before the first ``ps_*`` widget of the run.
* ``persist()`` must run after the last one (i.e. at the end of the sidebar).
* Never write a ``ps_*`` key after its widget has rendered — Streamlit raises.
  Write from an ``on_change``/``on_click`` callback instead; callbacks run
  between runs, which is also why no code here ever calls ``st.rerun()``.
"""

from __future__ import annotations

from typing import Any, Iterable

import streamlit as st

import presets

# Session-state keys owned by this module.  All start with "_" so they are
# clearly not widget keys and never collide with a ps_* setting.
STORE_KEY = "_settings_store"
TOUCHED_KEY = "_settings_touched"

# Number of custom-colour pickers mirrored per palette (cp_0 … cp_{N-1}).
CP_MAX = 32
# (stored list key, picker widget-key prefix)
_COLOR_LISTS = (("ps_custom_colors", "cp_"), ("ps_point_colors", "pc_"))


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

# Settings the user types into rather than drags. These are only gap-filled,
# never re-asserted: forcing a value onto a text box that the user may be part
# way through editing would discard what they were typing.
_TYPED_KEYS = frozenset({
    "ps_title", "ps_xlabel", "ps_ylabel", "ps_leg_title", "ps_x_suffix",
    "ps_ymin_str", "ps_ymax_str", "ps_xmin_str", "ps_xmax_str",
})


def hydrate() -> None:
    """Mirror the durable store into the widget keys.  Call once, before the UI.

    Every setting is written back into ``session_state``, not just the ones
    Streamlit dropped. That looks redundant but is the point: writing a widget's
    key marks it as a programmatic change, and Streamlit then *tells the browser*
    the value (``set_value`` in the widget's proto) instead of leaving the
    browser to fall back on the widget's declared default.

    That fallback is what produced the "everything jumps to its minimum" bug.
    A slider declared as ``st.slider("Bar opacity", 0.1, 1.0, key=...)`` has a
    default of ``0.1`` — its *minimum*. Whenever the browser had to build the
    widget afresh — the sidebar was torn down by an ``st.stop()`` while a file
    was being swapped, a tab remounted, the connection dropped — it had no value
    of its own and drew the default. Bar opacity 0.1 is the washed-out,
    desaturated plot; every other slider pinned to its low end is the rest of it.
    One interaction then wrote those minimums back and the corruption stuck.

    The value written is the *effective* one, read back through session_state
    first, so a value the user just changed in the browser still wins: Streamlit
    has already applied incoming widget values by the time this runs.
    """
    store: dict[str, Any] = st.session_state.setdefault(STORE_KEY, {})
    st.session_state.setdefault(TOUCHED_KEY, set())

    # Fill in settings added since the store was created (e.g. after an update).
    for key, default in presets.DEFAULTS.items():
        store.setdefault(key, default)

    for key in presets.DEFAULTS:
        present = key in st.session_state
        if present and key in _TYPED_KEYS:
            store[key] = st.session_state[key]
            continue
        value = st.session_state[key] if present else store[key]
        st.session_state[key] = value
        store[key] = value

    # Custom palette / point colour pickers mirror their stored lists.
    for list_key, prefix in _COLOR_LISTS:
        for i, colour in enumerate(store.get(list_key) or []):
            if not colour:
                continue
            key = f"{prefix}{i}"
            st.session_state[key] = st.session_state.get(key, colour)


def reassert(*keys: str) -> None:
    """Force Streamlit to send these widgets' current values to the browser.

    Writing a widget's key marks it as a programmatic change, which is what
    makes Streamlit include the value in the widget's proto instead of letting
    the browser fall back on the declared default.  Needed for any widget whose
    default is not a sensible value to be left showing — a slider's default is
    its minimum, and a multiselect's is an empty selection.

    Only widgets outside ``presets.DEFAULTS`` need this explicitly; ``hydrate``
    already does it for every setting.
    """
    for key in keys:
        if key in st.session_state:
            st.session_state[key] = st.session_state[key]


def persist() -> None:
    """Copy live widget values back into the durable store.  Call after the UI."""
    store: dict[str, Any] = st.session_state.setdefault(STORE_KEY, {})
    for key in presets.DEFAULTS:
        if key in st.session_state:
            store[key] = st.session_state[key]


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------

def get(key: str, default: Any = None) -> Any:
    """Read one setting: live widget value, else store, else DEFAULTS."""
    if key in st.session_state:
        return st.session_state[key]
    store = st.session_state.get(STORE_KEY) or {}
    if key in store:
        return store[key]
    if default is not None:
        return default
    return presets.DEFAULTS.get(key)


def snapshot() -> dict[str, Any]:
    """All settings as a plain dict — for presets, panels, and figure specs."""
    return {key: get(key) for key in presets.DEFAULTS}


# ---------------------------------------------------------------------------
# Writing (safe to call from callbacks and before the UI renders)
# ---------------------------------------------------------------------------

def update(values: dict[str, Any], *, mark_touched: bool = True) -> None:
    """Write several settings at once into both session_state and the store.

    Only valid before the matching widgets have rendered this run — i.e. from a
    callback, or from the top of the script.
    """
    store: dict[str, Any] = st.session_state.setdefault(STORE_KEY, {})
    for key, value in values.items():
        if key not in presets.DEFAULTS:
            continue
        store[key] = value
        st.session_state[key] = value
    if mark_touched:
        touched = st.session_state.setdefault(TOUCHED_KEY, set())
        touched.update(k for k in values if k in presets.DEFAULTS)

    # Curve widgets are keyed by curve id, which a restored list may reuse for
    # different values; drop them so they re-seed from the new list.
    if "ps_sigmoids" in values:
        for key in [k for k in st.session_state if str(k).startswith("sg_")]:
            del st.session_state[key]

    # Keep the colour pickers in step with a restored palette.
    for list_key, prefix in _COLOR_LISTS:
        for i, colour in enumerate(values.get(list_key) or []):
            if colour:
                st.session_state[f"{prefix}{i}"] = colour


def set_custom_colors(colors: list[str], key: str = "ps_custom_colors") -> None:
    """Store a colour list (custom palette or point colours).  These keys have no
    widget of their own, so unlike other settings they are safe to write after
    the pickers rendered."""
    st.session_state[key] = list(colors)
    store = st.session_state.setdefault(STORE_KEY, {})
    store[key] = list(colors)


def set_sigmoids(curves: list[dict]) -> None:
    """Store the sigmoid curve list (no widget of its own; see set_custom_colors)."""
    st.session_state["ps_sigmoids"] = list(curves)
    st.session_state.setdefault(STORE_KEY, {})["ps_sigmoids"] = list(curves)


# ---------------------------------------------------------------------------
# "Touched" tracking
#
# Some settings follow the data until the user overrides them: the title and
# y-axis label default to the sheet name, but must stay put once edited — and
# must be allowed to be genuinely empty.  A sentinel value cannot express both,
# so we record which keys the user has actually edited.
# ---------------------------------------------------------------------------

def mark_touched(*keys: str) -> None:
    """``on_change`` handler: record that the user edited these settings."""
    st.session_state.setdefault(TOUCHED_KEY, set()).update(keys)


def is_touched(key: str) -> bool:
    return key in (st.session_state.get(TOUCHED_KEY) or set())


def touched_keys() -> set[str]:
    return set(st.session_state.get(TOUCHED_KEY) or set())


def restore_touched(keys: Iterable[str]) -> None:
    """Replace the touched set — used when switching between panels."""
    st.session_state[TOUCHED_KEY] = set(keys)


def auto_text(key: str, fallback: str) -> str:
    """Resolve a follow-the-data text setting to its effective value."""
    return str(get(key) or "") if is_touched(key) else fallback


# ---------------------------------------------------------------------------
# Presets
# ---------------------------------------------------------------------------

def apply_preset(name: str) -> None:
    """Load a named preset into the live settings."""
    update(presets.load(name))


def ensure_startup_preset() -> None:
    """Seed the settings from the startup preset, once per session.

    Runs before any widget is created, so no rerun is needed to make the values
    visible — which is exactly what the old implementation used ``st.rerun()``
    for, at the cost of wiping every widget key.
    """
    if st.session_state.get("_startup_preset_loaded"):
        return
    st.session_state["_startup_preset_loaded"] = True
    try:
        update(presets.load(presets.get_startup_preset()), mark_touched=False)
    except (OSError, ValueError):
        # A corrupt or deleted preset must not stop the app from starting.
        update(dict(presets.DEFAULTS), mark_touched=False)


# ---------------------------------------------------------------------------
# Sheet-scoped widget keys
#
# The condition filter must reset when the sheet changes.  Rather than
# overwriting the widget's state mid-run (which needed an st.rerun() to take
# effect, and took every other setting down with it), give each sheet its own
# widget key: a new sheet gets a fresh widget that defaults to "all
# conditions", and returning to a sheet restores the selection you left there.
#
# The condition list is folded into the key so that re-uploading a file whose
# sheet has different conditions cannot leave an out-of-range selection behind.
# ---------------------------------------------------------------------------

def filter_key(sheet: str, conditions: Iterable[str]) -> str:
    digest = abs(hash(tuple(str(c) for c in conditions))) % 10_000_000
    return f"_filter::{sheet}::{digest}"
