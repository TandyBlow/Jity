"""Make the experiment's tools importable when pytest runs from anywhere."""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
for entry in (str(HERE), str(HERE / "tests")):
    if entry not in sys.path:
        sys.path.insert(0, entry)
