"""Generate FYP-1 Partial Thesis .docx — entry point.

Section content lives in thesis/section_*.py; each appends to the shared
document (thesis.document.doc) at import time, in the order below.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import thesis.section_01_title_page  # noqa: F401  (appends section)
import thesis.section_02_abstract  # noqa: F401  (appends section)
import thesis.section_03_chapter_1_introduction  # noqa: F401  (appends section)
import thesis.section_04_chapter_2_related_work  # noqa: F401  (appends section)
import thesis.section_05a_chapter_3_system_design  # noqa: F401  (appends section)
import thesis.section_05b_chapter_3_system_design  # noqa: F401  (appends section)
import thesis.section_06_chapter_4_implementation  # noqa: F401  (appends section)
import thesis.section_07_chapter_5_experiments_evaluati  # noqa: F401  (appends section)
import thesis.section_08_chapter_6_conclusion_future_wo  # noqa: F401  (appends section)
import thesis.section_09_references  # noqa: F401  (appends section)

from thesis import document  # noqa: E402

# ── SAVE ──────────────────────────────────────────────────────
document.doc.save(document.OUTPUT)
print(f'[OK] Thesis saved to: {document.OUTPUT}')
print(f'   Paragraphs: {len(document.doc.paragraphs)}')
print(f'   Tables: {len(document.doc.tables)}')
