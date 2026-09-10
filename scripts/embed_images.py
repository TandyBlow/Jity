"""
Insert rendered Mermaid PNGs into the thesis .docx at correct positions.
Uses unique text markers to find insertion points.
"""
from docx import Document
from docx.shared import Inches, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
import os

THESIS_PATH = r"D:\others\2025-2026.2\fyp\PartialThesis_AI_TRPG_Context_Engineering.docx"
DIAGRAMS_DIR = r"D:\others\Jity\scripts\diagrams"
OUTPUT_PATH = THESIS_PATH

# Map: unique search text → (image_filename, figure_label, width_inches)
# Each search text must appear exactly once in the thesis
IMAGES = [
    (
        "系统整体架构如图3.1所示",
        "fig3_1_system_architecture.png",
        "图3.1  Jity系统总体架构图：展示了前端、API层、服务层、Agent层、记忆层和数据层的分层架构及模块间调用关系。",
        5.8,
    ),
    (
        "图3.2展示了三层架构的数据流",
        "fig3_2_memory_architecture.png",
        "图3.2  Nyarlathotep三层记忆架构数据流图：L0工作记忆全量注入、L1叙事记忆语义检索Top-5、L2世界记忆关键词触发，以及生成后的异步记忆维护流程。",
        5.8,
    ),
    (
        "图3.3展示了管线的数据流",
        "fig3_3_agent_pipeline.png",
        "图3.3  多智能体叙事管线序列图：Examiner判定的短路机制、Director的六种重定向策略激活条件、以及Narrator的指令注入流程。",
        5.8,
    ),
    (
        "FSM状态流转如图3.4所示",
        "fig3_4_campaign_fsm.png",
        "图3.4  战役层次化有限状态机（FSM）状态图：idle → session_active → session_recap → arc_transition → arc_intro → campaign_end的状态流转路径，以及锚点触发、偏离检测和重定向策略的激活条件。",
        5.8,
    ),
    (
        "完整数据处理流程如图4.1所示",
        "fig3_5_turn_dataflow.png",
        "图4.1  单回合完整数据处理流程序列图：展示了从玩家输入到响应返回的九个处理阶段——①加载状态 ②RAG检索 ③记忆上下文组装 ④构建Prompt ⑤多Agent管线（Examiner→Director→Narrator）⑥状态应用与验证 ⑦两阶段DB持久化 ⑧异步记忆维护（Fire-and-Forget）⑨返回渲染响应。",
        5.8,
    ),
]


def insert_image_after_paragraph(doc, search_text, image_path, caption_text, width_inches):
    """Find the ONE paragraph containing search_text, insert image+caption after it."""
    candidates = []
    for i, para in enumerate(doc.paragraphs):
        if search_text in para.text:
            candidates.append((i, para))

    if len(candidates) == 0:
        print(f"  [WARN] No match for: '{search_text[:80]}'")
        return False
    if len(candidates) > 1:
        print(f"  [WARN] Multiple matches ({len(candidates)}) for: '{search_text[:80]}', using first at idx {candidates[0][0]}")

    idx, para = candidates[0]

    # Create image paragraph after the target
    img_para = OxmlElement('w:p')
    pPr = OxmlElement('w:pPr')
    jc = OxmlElement('w:jc')
    jc.set(qn('w:val'), 'center')
    pPr.append(jc)
    img_para.append(pPr)

    r = OxmlElement('w:r')
    # Inline drawing
    drawing_xml = f'''<w:drawing xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"
xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
</w:drawing>'''
    drawing_elem = OxmlElement('w:drawing')
    r.append(drawing_elem)
    img_para.append(r)

    # Insert after target paragraph
    para._element.addnext(img_para)

    # Now use python-docx API on a real paragraph for the image
    # The above XML approach is fragile; let's use the proper API instead
    # Remove the placeholder
    img_para.getparent().remove(img_para)

    # Create proper paragraph with image using docx API
    # We need to insert at the right position in the document body
    body = doc.element.body
    new_p = OxmlElement('w:p')
    new_pPr = OxmlElement('w:pPr')
    new_jc = OxmlElement('w:jc')
    new_jc.set(qn('w:val'), 'center')
    new_pPr.append(new_jc)
    new_p.append(new_pPr)

    # Add the image via a proper document paragraph
    # Unfortunately add_picture only works on Run objects in paragraphs created via doc.add_paragraph
    # Workaround: create paragraph, add picture, then move the XML element
    temp_para = doc.add_paragraph()
    temp_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = temp_para.add_run()
    run.add_picture(image_path, width=Inches(width_inches))

    # Move temp_para's element to right after the target paragraph
    para._element.addnext(temp_para._element)

    # Caption below image
    cap_para = doc.add_paragraph()
    cap_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    cap_run = cap_para.add_run(caption_text)
    cap_run.font.size = Pt(9)
    cap_run.italic = True

    # Move caption after image
    temp_para._element.addnext(cap_para._element)

    print(f"  [OK] {os.path.basename(image_path)} → after para[{idx}] '{para.text[:60]}...'")
    return True


def main():
    print("=" * 60)
    print("Embedding Mermaid Diagrams into Thesis")
    print("=" * 60)

    if not os.path.exists(THESIS_PATH):
        print(f"ERROR: Thesis not found at {THESIS_PATH}")
        print("Run generate_thesis.py first!")
        return

    doc = Document(THESIS_PATH)
    print(f"Loaded: {len(doc.paragraphs)} paragraphs")

    ok = 0
    fail = 0
    for search_text, img_name, caption, width in IMAGES:
        img_path = os.path.join(DIAGRAMS_DIR, img_name)
        if not os.path.exists(img_path):
            print(f"\n  [SKIP] Image not found: {img_path}")
            fail += 1
            continue
        print(f"\n{img_name} ({os.path.getsize(img_path)/1024:.0f} KB)")
        if insert_image_after_paragraph(doc, search_text, img_path, caption, width):
            ok += 1
        else:
            fail += 1

    doc.save(OUTPUT_PATH)
    print(f"\n{'=' * 60}")
    print(f"Saved: {OUTPUT_PATH}")
    print(f"  {ok} images embedded, {fail} failed")
    print(f"  Final paragraphs: {len(doc.paragraphs)}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
