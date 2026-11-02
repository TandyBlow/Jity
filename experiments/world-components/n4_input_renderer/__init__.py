# N4 formal component: narrative input renderer (program-only).
#
# New numbering (2026-11-02):
#   N4 = input rendering (this package)
#   N5 = narrative generation (old N4)
#   N6 = verification (old N5)

from .renderer import (  # noqa: F401
    N4_VERSION,
    N4RenderError,
    render_fact_line,
    render_input,
    render_narrative_input,
    render_plan_input,
)
from .scene_context import build_scene_context  # noqa: F401
