"""Thesis section: ABSTRACT. Appends to the shared document on import."""
from thesis.document import (
    add_heading,
    add_page_break,
    add_para,
    doc,
)

# ============================================================
# ABSTRACT
# ============================================================

add_heading('ABSTRACT', level=1)
add_para('')

abstract_text = (
    "Tabletop Role-Playing Games (TRPGs) present a unique challenge for AI Game Masters: "
    "maintaining consistent memory of game state, character relationships, and narrative context "
    "across sessions that can span hundreds of dialogue turns. Existing approaches relying on "
    "full conversation history injection suffer from the \"lost-in-the-middle\" effect and "
    "token budget exhaustion, while generic memory frameworks lack TRPG-specific optimizations "
    "for rule consistency and state tracking.\n\n"
    "This thesis presents Jity, a web-based Chinese AI TRPG system that addresses these challenges "
    "through a three-layer memory architecture (Nyarlathotep) and a multi-agent narrative pipeline. "
    "The memory system integrates MOOM's hierarchical summarization (three-level narrative abstraction "
    "with geometric thresholds), SCORE's finite-state item tracking (active/lost/destroyed/unknown "
    "with continuity violation detection), and a competition-inhibition forgetting mechanism. "
    "The narrative pipeline replaces single-model generation with a three-stage SENNA-inspired "
    "architecture: an Examiner agent judges action feasibility, a Director agent produces "
    "narrative direction with six redirection strategies, and a Narrator generates the final prose.\n\n"
    "The system is implemented as a full-stack application (Python/FastAPI backend with SQLite WAL "
    "and FAISS vector search; Next.js/React/TypeScript frontend). The codebase comprises 69 Python "
    "modules (10,910 lines), 221 automated tests, and integrates seven published frameworks "
    "(SENNA, MOOM, SCORE, CoDi, HaluMem, PAYADOR, and the Borawski et al. dependency-driven pipeline). "
    "Seven formal experimental runs validate the memory architecture and prompt engineering optimizations, "
    "providing a foundation for the TRPG-MemBench evaluation benchmark proposed in future work."
)

add_para(abstract_text)

add_page_break()
