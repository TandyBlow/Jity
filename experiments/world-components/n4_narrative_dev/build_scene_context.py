# Compatibility shim. N4.1 scene-context assembly now lives in
# `n4_input_renderer/scene_context.py` (formal component N4).

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
WC = HERE.parent
if str(WC) not in sys.path:
    sys.path.insert(0, str(WC))

from n4_input_renderer.scene_context import build_scene_context  # noqa: E402,F401
