# Compatibility shim. The formal N4 component now lives in
# `n4_input_renderer/`; this module only keeps the approved dev-corpus
# previews and the old pipeline import path working.
#
# New numbering (2026-11-02): N4 = input renderer, N5 = generation,
# N6 = verification. See design/world-engine-reports/components/
# n4-input-renderer.md.

import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
WC = HERE.parent
if str(WC) not in sys.path:
    sys.path.insert(0, str(WC))

from n4_input_renderer.renderer import (  # noqa: E402,F401
    N4_VERSION,
    N4RenderError,
    render_fact_line,
    render_input,
    render_narrative_input,
    render_plan_input,
)


def load_world(path=None):
    p = pathlib.Path(path) if path else HERE / "world.json"
    return json.loads(p.read_text(encoding="utf-8"))
