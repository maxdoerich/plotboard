"""
Regression tests for the plotting app.

Run directly (no pytest needed):

    python tests/test_regressions.py

or, if pytest is installed:

    pytest tests/

The AppTest-based cases drive the real Streamlit script, which is the only way
to reproduce the widget-state behaviour these tests exist to protect:
Streamlit deletes the session-state entry of any widget that did not render in
a run, and that interacts with the app's own state handling in ways unit tests
cannot see.
"""

from __future__ import annotations

import os
import sys
import traceback

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(TESTS_DIR)
sys.path.insert(0, PROJECT_DIR)
os.chdir(PROJECT_DIR)

import pandas as pd  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402

import dataio  # noqa: E402
import figspec  # noqa: E402
import plotter  # noqa: E402
import presets as xpresets  # noqa: E402
import utils  # noqa: E402

DATA_FILE = os.path.join(PROJECT_DIR, "data", "E24_Analysis.xlsx")
TIMEOUT = 180


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _loaded_app() -> AppTest:
    """An app with the sample workbook open and no exceptions."""
    app = AppTest.from_file(os.path.join(PROJECT_DIR, "app.py"),
                            default_timeout=TIMEOUT)
    app.run()
    app.text_input[0].set_value(DATA_FILE)
    app.run()
    _assert_clean(app, "loading the sample workbook")
    return app


def _assert_clean(app: AppTest, context: str) -> None:
    if app.exception:
        detail = "; ".join(str(e.value)[:300] for e in app.exception)
        raise AssertionError(f"exception while {context}: {detail}")


def _settings(app: AppTest, *keys: str) -> dict:
    out = {}
    for key in keys:
        try:
            out[key] = app.session_state[key]
        except Exception:
            out[key] = "<missing>"
    return out


TRACKED = ("ps_fig_width", "ps_bar_gap", "ps_tick_rotation", "ps_point_size",
           "ps_spine_width", "ps_cap_size")
CUSTOM = {"ps_fig_width": 17, "ps_bar_gap": 0.45, "ps_tick_rotation": 75,
          "ps_point_size": 9.0, "ps_spine_width": 2.5, "ps_cap_size": 0.22}


def _apply_custom(app: AppTest) -> None:
    for key, value in CUSTOM.items():
        app.session_state[key] = value
    app.run()


# ---------------------------------------------------------------------------
# The reported bug
# ---------------------------------------------------------------------------

def test_sheet_switch_preserves_settings():
    """Switching sheets must not reset the plot settings.

    The old code reset the condition filter and called st.rerun() before the
    sidebar had rendered.  Streamlit dropped every widget value from the
    abandoned run, the app re-seeded them from DEFAULTS, and the sliders came
    back at their minimum.  The sheet selector lost its value too, so the app
    bounced back to the sheet you started on.
    """
    app = _loaded_app()
    _apply_custom(app)
    assert _settings(app, *TRACKED) == CUSTOM, "settings did not take effect"

    sheets = list(app.selectbox(key="_sheet_select").options)
    target = sheets[1]
    app.selectbox(key="_sheet_select").set_value(target).run()
    _assert_clean(app, "switching sheet")

    assert app.session_state["_sheet_select"] == target, (
        f"sheet bounced back to {app.session_state['_sheet_select']!r}")
    assert _settings(app, *TRACKED) == CUSTOM, (
        f"settings reset on sheet switch: {_settings(app, *TRACKED)}")


def test_hidden_widgets_keep_their_settings():
    """Settings whose widget is hidden by another choice must survive.

    ps_cap_size and the bar options only render for some plot types.  Streamlit
    culls the keys of widgets that did not render, so without the durable store
    they came back at their defaults.
    """
    app = _loaded_app()
    _apply_custom(app)

    app.session_state["ps_plot_type"] = "box+strip"
    app.run()
    app.session_state["ps_plot_type"] = "bar+strip"
    app.run()
    _assert_clean(app, "switching plot type")

    assert _settings(app, *TRACKED) == CUSTOM, (
        f"settings lost via hidden widgets: {_settings(app, *TRACKED)}")


SLIDER_KEYS = ("ps_bar_alpha", "ps_fig_width", "ps_point_size", "ps_spine_width")


def test_settings_are_pushed_to_the_browser():
    """Every setting must be sent to the browser, not left to its default.

    Streamlit only includes a widget's value in the message it sends when the
    value was set programmatically that run; otherwise the browser falls back
    on the widget's declared default. For these sliders the default is
    min_value, so any time the browser had to rebuild the widget -- the sidebar
    torn down by an st.stop() during a file swap, a remount, a dropped
    connection -- it drew the minimum. ps_bar_alpha at 0.1 is the washed-out,
    desaturated plot; one interaction then wrote the minimums back for good.
    """
    app = _loaded_app()
    for key, value in (("ps_bar_alpha", 0.75), ("ps_fig_width", 17),
                       ("ps_point_size", 9.0), ("ps_spine_width", 2.5)):
        app.slider(key=key).set_value(value).run()
    _assert_clean(app, "changing sliders")

    for key in SLIDER_KEYS:
        proto = app.slider(key=key).proto
        default = list(proto.default)[0]
        current = float(app.session_state[key])
        assert proto.set_value or abs(default - current) < 1e-9, (
            f"{key} is not sent to the browser and its default ({default}) "
            f"differs from its value ({current}) -- the browser would show "
            f"the default")


def test_live_edits_survive_the_push():
    """Re-asserting values must not overwrite what the user just changed."""
    app = _loaded_app()
    app.slider(key="ps_bar_alpha").set_value(0.75).run()
    assert app.session_state["ps_bar_alpha"] == 0.75
    app.slider(key="ps_bar_alpha").set_value(0.35).run()
    assert app.session_state["ps_bar_alpha"] == 0.35, (
        "hydrate() clobbered a live widget edit")


def test_settings_survive_a_file_swap():
    """Load one workbook, restyle, load another, switch sheet.

    The file-swap path goes through an st.stop() when the uploader is empty,
    which tears the whole sidebar down.
    """
    app = _loaded_app()
    for key, value in (("ps_bar_alpha", 0.75), ("ps_fig_width", 17),
                       ("ps_point_size", 9.0), ("ps_spine_width", 2.5)):
        app.slider(key=key).set_value(value).run()
    expected = {k: app.session_state[k] for k in SLIDER_KEYS}

    other = os.path.join(PROJECT_DIR, "data", "F39_Analysis.xlsx")
    if not os.path.exists(other):
        return
    app.text_input[0].set_value("")          # no file -> st.stop()
    app.run()
    app.text_input[0].set_value(other)       # second workbook
    app.run()
    _assert_clean(app, "swapping the workbook")

    got = {k: app.session_state[k] for k in SLIDER_KEYS}
    assert got == expected, f"settings lost on file swap: {got} != {expected}"

    sheets = list(app.selectbox(key="_sheet_select").options)
    app.selectbox(key="_sheet_select").set_value(sheets[2]).run()
    _assert_clean(app, "switching sheet after a file swap")
    got = {k: app.session_state[k] for k in SLIDER_KEYS}
    assert got == expected, f"settings lost on the later sheet switch: {got}"

    for key in SLIDER_KEYS:
        proto = app.slider(key=key).proto
        default = list(proto.default)[0]
        assert proto.set_value or abs(default - float(got[key])) < 1e-9, (
            f"{key} would render at its default after the swap")


def test_no_rerun_calls_in_app_code():
    """The state model must not need mid-run reruns to work.

    Parsed rather than grepped, so the explanations of *why* there are no
    reruns do not trip the check that there are none.
    """
    import ast

    offenders = []
    for root, dirs, files in os.walk(PROJECT_DIR):
        dirs[:] = [d for d in dirs if d not in
                   (".git", ".venv", "old_version", "__pycache__", "tests",
                    "logo", ".presets", "graphify-out", "data")]
        for name in files:
            if not name.endswith(".py"):
                continue
            path = os.path.join(root, name)
            with open(path, encoding="utf-8") as handle:
                tree = ast.parse(handle.read(), filename=path)
            for node in ast.walk(tree):
                if (isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Attribute)
                        and node.func.attr == "rerun"):
                    offenders.append(f"{name}:{node.lineno}")
    assert not offenders, f"st.rerun() reintroduced at {offenders}"


# ---------------------------------------------------------------------------
# Presets
# ---------------------------------------------------------------------------

def test_preset_roundtrip():
    name = "__pytest_tmp__"
    try:
        xpresets.save(name, {**xpresets.DEFAULTS, "ps_fig_width": 19,
                             "ps_bar_gap": 0.5, "ps_title": "should not persist"})
        loaded = xpresets.load(name)
        assert loaded["ps_fig_width"] == 19
        assert loaded["ps_bar_gap"] == 0.5
        assert loaded["ps_title"] == "", "title must not be stored in a preset"
    finally:
        xpresets.delete(name)


def test_preset_migrates_legacy_x_numeric():
    """Presets saved when x_numeric was a checkbox must still load."""
    name = "__pytest_legacy__"
    path = xpresets.PRESETS_DIR / f"{name}.json"
    try:
        xpresets.PRESETS_DIR.mkdir(exist_ok=True)
        path.write_text('{"ps_x_numeric": true, "ps_fig_width": 12}',
                        encoding="utf-8")
        assert xpresets.load(name)["ps_x_numeric"] == "numeric"
        path.write_text('{"ps_x_numeric": false}', encoding="utf-8")
        assert xpresets.load(name)["ps_x_numeric"] == "auto"
    finally:
        if path.exists():
            path.unlink()


def test_preset_load_applies_to_widgets():
    name = "__pytest_apply__"
    try:
        # Saved before the app starts so the preset is already among the
        # selectbox options the first time it renders.
        xpresets.save(name, {**xpresets.DEFAULTS, "ps_fig_width": 18,
                             "ps_tick_rotation": 15})
        app = _loaded_app()
        app.session_state["_preset_choice"] = name
        app.run()
        # Streamlit runs on_click callbacks before the next script run, which
        # is what lets a preset reach the widgets without an st.rerun().
        [button] = [b for b in app.button if b.label == "Load"]
        button.click().run()
        _assert_clean(app, "loading a preset")
        assert app.session_state["ps_fig_width"] == 18
        assert app.session_state["ps_tick_rotation"] == 15
    finally:
        xpresets.delete(name)


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

def test_stat_selection_draws_brackets():
    """Ticking a comparison must add a bracket in the same run."""
    app = _loaded_app()
    app.session_state["ps_run_stats"] = True
    app.run()
    _assert_clean(app, "enabling statistics")

    headings = [s.value for s in app.subheader]
    assert any("Statistical comparisons" in h for h in headings), (
        f"the comparisons table did not render; headings were {headings}")

    key = (f"_stat_editor::{app.session_state['ps_test_mode']}"
           f"::{app.session_state['ps_compare_axis']}"
           f"::{app.session_state['_sheet_select']}")
    app.session_state[key] = {"edited_rows": {0: {"Show bracket": True}},
                              "added_rows": [], "deleted_rows": []}
    app.run()
    _assert_clean(app, "selecting a comparison")

    # st.pyplot renders as an "imgs" element in the AppTest element tree.
    assert app.get("imgs"), "the plot disappeared once a bracket was selected"


def test_rename_reaches_stat_results():
    """Renaming labels must rename the stat table too, or brackets vanish.

    Bracket x-positions are looked up by group name among the plotted labels;
    an unrenamed table misses every lookup and silently draws nothing.
    """
    stats = pd.DataFrame({
        "treatment": ["A", "A"],
        "group_A": ["cond1", "cond1"],
        "group_B": ["cond2", "cond3"],
        "p_value": [0.01, 0.2],
        "stars": ["**", "ns"],
    })
    renamed = dataio.rename_stat_results(
        stats, {"cond1": "Control", "cond2": "Treated"}, {"A": "Drug"})
    assert list(renamed["group_A"]) == ["Control", "Control"]
    assert list(renamed["group_B"]) == ["Treated", "cond3"]
    assert list(renamed["treatment"]) == ["Drug", "Drug"]
    assert list(stats["group_A"]) == ["cond1", "cond1"], "input was mutated"


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def test_exports_are_not_rendered_eagerly():
    """No image encoding may happen unless a download is actually clicked."""
    calls = []
    original = utils.fig_to_bytes

    def counting(*args, **kwargs):
        calls.append(args[1] if len(args) > 1 else kwargs.get("fmt"))
        return original(*args, **kwargs)

    utils.fig_to_bytes = counting
    try:
        app = _loaded_app()
        app.session_state["ps_fig_width"] = 14
        app.run()
        _assert_clean(app, "re-rendering after a settings change")
    finally:
        utils.fig_to_bytes = original

    assert not calls, f"exports were rendered eagerly: {calls}"


def test_batch_export_uses_the_same_settings_as_the_preview():
    """Batch export used to hand-roll its kwargs and drop most of them."""
    current = {**xpresets.DEFAULTS, "ps_ymin_str": "0", "ps_ymax_str": "500",
               "ps_minor_ticks_y": 3, "ps_spines": "all", "ps_line_width": 2.5,
               "ps_tick_direction": "in"}
    kwargs = figspec.draw_kwargs(current, n_treatments=3, title="t", ylabel="y")
    assert kwargs["spines"] == "all"
    assert kwargs["minor_ticks_y"] == 3
    assert kwargs["line_width"] == 2.5
    assert kwargs["tick_direction"] == "in"
    assert figspec.axis_limits(current) == ((0.0, 500.0), None)


# ---------------------------------------------------------------------------
# Plotter
# ---------------------------------------------------------------------------

def test_figures_stay_off_the_pyplot_registry():
    """Figures must not accumulate in pyplot's global figure list."""
    import matplotlib.pyplot as plt

    frame = dataio.load_sheet(open(DATA_FILE, "rb").read(), "k", "Nano")
    before = len(plt.get_fignums())
    for _ in range(5):
        plotter.make_figure(frame, palette=utils.get_palette("iGEM", 4),
                            plot_type="bar")
    assert len(plt.get_fignums()) == before, "figures leaked into pyplot"


def test_x_axis_auto_detection():
    assert plotter.x_axis_is_numeric(["0", "2", "24"], "auto") is True
    assert plotter.x_axis_is_numeric(["1 h", "6 h"], "auto") is True
    assert plotter.x_axis_is_numeric(["ctrl", "drug"], "auto") is False
    assert plotter.x_axis_is_numeric(["0", "2"], "categorical") is False
    # Bools from presets saved before the three-way control.
    assert plotter.x_axis_is_numeric(["0", "2"], True) is True
    assert plotter.x_axis_is_numeric(["0", "2"], False) is False


def test_font_family_is_applied():
    """The font family control did nothing before: set_theme reset it."""
    frame = dataio.load_sheet(open(DATA_FILE, "rb").read(), "k", "Nano")
    figure = plotter.make_figure(frame, palette=utils.get_palette("iGEM", 4),
                                 plot_type="bar", font_family="serif")
    axes = figure.axes[0]
    assert "serif" in axes.yaxis.label.get_fontname().lower(), (
        f"y-label rendered as {axes.yaxis.label.get_fontname()!r}")


# ---------------------------------------------------------------------------
# Panel mode
# ---------------------------------------------------------------------------

def test_panels_keep_independent_settings():
    app = _loaded_app()
    app.session_state["_panel_mode"] = True
    app.run()
    _assert_clean(app, "enabling panel mode")

    app.session_state["ps_fig_width"] = 15
    app.run()

    switches = [b for b in app.button if b.key == "_panel_btn_1"]
    assert switches, "no second panel button rendered"
    switches[0].click().run()
    _assert_clean(app, "switching panel")
    assert app.session_state["_active_panel_idx"] == 1

    app.session_state["ps_bar_gap"] = 0.6
    app.run()

    back = [b for b in app.button if b.key == "_panel_btn_0"]
    back[0].click().run()
    _assert_clean(app, "switching back to the first panel")

    stored = app.session_state["panels"]
    assert stored[0]["ps_fig_width"] == 15, "panel A lost its width"
    assert stored[1]["ps_bar_gap"] == 0.6, "panel B lost its gap"
    assert stored[0]["ps_bar_gap"] != 0.6, "panel B's gap leaked into panel A"


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

# Collected at import: running the Streamlit app rebinds sys.modules["__main__"]
# to the app script, so this list cannot be rediscovered afterwards.
ALL_TESTS = [(name, obj) for name, obj in sorted(dict(globals()).items())
             if name.startswith("test_") and callable(obj)]


def _all_tests():
    return ALL_TESTS


def main() -> int:
    failures = []
    for name, func in _all_tests():
        try:
            func()
        except Exception as exc:  # noqa: BLE001 - the runner reports everything
            failures.append((name, exc, traceback.format_exc()))
            print(f"FAIL  {name}: {exc}", flush=True)
        else:
            print(f"ok    {name}", flush=True)

    print()
    total = len(_all_tests())
    if failures:
        print(f"{len(failures)}/{total} failed")
        for name, _exc, tb in failures:
            print(f"\n===== {name} =====\n{tb}")
        return 1
    print(f"all {total} tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
