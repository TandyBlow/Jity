"""Portable paths shared by the historical thesis tools."""
import os
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TOOLS_DIR.parents[1]
DIAGRAMS_DIR = TOOLS_DIR / "diagrams"
THESIS_PATH = Path(os.environ.get(
    "JITY_THESIS_OUTPUT",
    str(REPO_ROOT / "docs/research/generated/PartialThesis_AI_TRPG_Context_Engineering.docx"),
)).expanduser()
