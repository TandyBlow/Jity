"""Thesis section: TITLE PAGE. Appends to the shared document on import."""
from thesis.document import (
    add_heading,
    add_page_break,
    add_para,
    doc,
)
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt

# ============================================================
# TITLE PAGE
# ============================================================

# Empty lines for centering
for _ in range(6):
    add_para('', alignment=WD_ALIGN_PARAGRAPH.CENTER)

add_para(
    'Context Engineering and Memory Management\n'
    'for Web-Based Chinese AI Tabletop Role-Playing Games',
    bold=True, font_size=18, alignment=WD_ALIGN_PARAGRAPH.CENTER
)

add_para('', alignment=WD_ALIGN_PARAGRAPH.CENTER)
add_para('', alignment=WD_ALIGN_PARAGRAPH.CENTER)

add_para('by', alignment=WD_ALIGN_PARAGRAPH.CENTER)
add_para('', alignment=WD_ALIGN_PARAGRAPH.CENTER)
add_para('【学生姓名】', bold=True, font_size=14, alignment=WD_ALIGN_PARAGRAPH.CENTER)
add_para('(【学号】)', font_size=12, alignment=WD_ALIGN_PARAGRAPH.CENTER)

for _ in range(4):
    add_para('', alignment=WD_ALIGN_PARAGRAPH.CENTER)

add_para('A Final Year Project-I Partial Thesis', alignment=WD_ALIGN_PARAGRAPH.CENTER)
add_para('submitted in partial fulfillment of the requirements', alignment=WD_ALIGN_PARAGRAPH.CENTER)
add_para('for the degree of', alignment=WD_ALIGN_PARAGRAPH.CENTER)
add_para('Bachelor of Science (Honours)', alignment=WD_ALIGN_PARAGRAPH.CENTER)
add_para('in', alignment=WD_ALIGN_PARAGRAPH.CENTER)
add_para('Computer Science and Technology', alignment=WD_ALIGN_PARAGRAPH.CENTER)
add_para('at', alignment=WD_ALIGN_PARAGRAPH.CENTER)
add_para('BEIJING NORMAL-HONG KONG BAPTIST UNIVERSITY', alignment=WD_ALIGN_PARAGRAPH.CENTER)

for _ in range(3):
    add_para('', alignment=WD_ALIGN_PARAGRAPH.CENTER)

add_para('June, 2026', alignment=WD_ALIGN_PARAGRAPH.CENTER)

add_page_break()
