# N4.0 narrative input packing (program sub-step of the N4 generation model).
#
# Numbering (2026-11-02, option A):
#   N1 extraction -> N2 selection -> N3 organization
#   -> N4.0 structured input packing (this package, program)
#   -> N4 narrative generation (model)
#   -> N5 verification
#
# The legacy sentence-row renderer is kept for the frozen v2/v3 models and
# byte regression; pack_narrative_input is the new N4 input contract.

from .packer import N4_INPUT_VERSION, pack_narrative_input  # noqa: F401
from .renderer import (  # noqa: F401
    N4_VERSION,
    N4RenderError,
    render_fact_line,
    render_input,
    render_narrative_input,
    render_plan_input,
)
from .scene_context import build_scene_context  # noqa: F401
