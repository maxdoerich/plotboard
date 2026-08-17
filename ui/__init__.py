"""ui — the Streamlit widget layer, one module per sidebar tab plus the
main-area blocks (plot export, stats table, data preview).

Modules here own widgets and nothing else: settings are written to
``st.session_state`` under their ``ps_*`` keys and read back through
``settings.get()``/``settings.snapshot()``, so a tab never has to hand its
values to the caller.  Only genuinely non-setting choices (which conditions are
selected, what the stat test returned) are returned to ``app.py``.

Every callback that writes a ``ps_*`` key must run as an ``on_click``/
``on_change`` handler.  Callbacks execute between script runs, so the value is
already in place when the widget renders — no ``st.rerun()``, and none of the
widget-state loss that came with it.
"""
