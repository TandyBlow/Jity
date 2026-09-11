"""Thesis section: REFERENCES. Appends to the shared document on import."""
from thesis.document import (
    add_heading,
    add_page_break,
    add_para,
    doc,
)

# ============================================================
# REFERENCES
# ============================================================

add_heading('References', level=1)

references = [
    '[1] H. Zhao et al., "A Survey of Context Engineering for Large Language Models," arXiv:2507.13334, 2025.',
    '[2] C. Packer et al., "MemGPT: Towards LLMs as Operating Systems," arXiv:2310.08560, 2024.',
    '[3] J. Chen et al., "MOOM: Memory Management in Ultra-Long Role-Playing Dialogues," arXiv:2509.11860, 2025.',
    '[4] R. Yi et al., "SCORE: Structured Memory and Retrieval for Item State Tracking in Long-Form Narratives," arXiv:2503.23512, 2025.',
    '[5] M. Jorgensen et al., "Guiding, Not Railroading: Design and Evaluation of a Multi-Agent System for Narrative Redirection in Role-playing Games," ACM IUI, 2026. DOI: 10.1145/3742413.3789218.',
    '[6] CoDi, "Goal-Driven Interactive Story Generation via Director-Actor Framework," AAAI AIIDE, 2025. DOI: 10.1609/aiide.v21i1.36811.',
    '[7] J. Chen et al., "HaluMem: Hallucination Detection and Evaluation in Memory-Augmented LLM Systems," arXiv:2511.03506, 2025.',
    '[8] M. Borawski et al., "From World-Gen to Quest-Line: A Dependency-Driven Prompt Pipeline for Coherent RPG Generation," arXiv:2604.25482, 2026.',
    '[9] PAYADOR, "Minimalist Grounding of LLM Output on Structured Data for Text Adventure Games," arXiv:2504.07304, 2025.',
    '[10] Z. Jiang et al., "LLMLingua: Compressing Prompts for Accelerated Inference of Large Language Models," EMNLP, 2023.',
    '[11] Z. Jiang et al., "LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression," ACL, 2024.',
    '[12] 500xCompressor, "Generalized Prompt Compression for Large Language Models," ACL, 2025.',
    '[13] J. Chen et al., "RocketKV: Accelerating Long-Context LLM Inference via Two-Stage KV Cache Compression," ICML, 2025.',
    '[14] DynamicKV, "Task-Aware Adaptive KV Cache Compression for Long LLM Contexts," arXiv:2412.14838, 2024.',
    '[15] ZSMerge, "Zero-Shot KV Cache Compression for Memory-Efficient Long-Context LLMs," arXiv:2503.10714, 2025.',
    '[16] EverMemOS, "Bionic 4-layer Architecture for Long-Term Conversational Memory," LoCoMo 92.3%, 2025.',
    '[17] Zep, "Temporal Knowledge Graph Architecture for Agent Memory," arXiv:2501.13956, 2025.',
    '[18] Memoria, "Scalable Agentic Memory Framework for LLMs," arXiv:2512.12686, 2025.',
    '[19] SGMem, "Sentence Graph Memory for Conversational Agents," arXiv:2509.21212, 2025.',
    '[20] Y. Song et al., "Enhancing AI Game Masters with Function Calling," ACL Wordplay, 2024.',
    '[21] A. Zhu et al., "CALYPSO: LLMs as Dungeon Masters\' Assistants," AIIDE, 2023.',
    '[22] "Static vs. Agentic Game Master AI: Comparative Study of Single-Model vs Multi-Agent DM Architectures," ACM CUI, 2025.',
    '[23] PANGeA, "Procedural Narrative Using Generative AI with Validation," AIIDE, 2024.',
    '[24] "Codifying Character Logic in Role-Playing: Compiling Character Rules into Executable Functions," NeurIPS, 2025.',
    '[25] STORY2GAME, "Generating Everything in Interactive Fiction Games," Georgia Tech, arXiv:2505.03547, 2025.',
    '[26] SNAP, "Plan-Driven Framework for Controllable Narrative Generation," arXiv:2601.11529, 2025.',
    '[27] LongMemEval, "Benchmarking Long-Term Interactive Memory for LLMs," ICLR, 2025.',
    '[28] LoCoMo, "Evaluating Very Long-Term Conversational Memory of LLM Agents," arXiv, 2024.',
    '[29] RPGBENCH, "Evaluating LLMs as Role-Playing Game Engines," ICML, 2025. arXiv:2502.00595.',
    '[30] CharacterBench, "Bilingual Character Consistency Benchmark (22,859 Samples, 11 Dimensions)," arXiv, 2024–2025.',
    '[31] CharacterEval, "Chinese Role-Play Evaluation Benchmark (1,785 Dialogues, 11,376 Samples)," arXiv, 2024.',
    '[32] RoleRMBench & RoleRM, "Reward Modeling for Role-Play Evaluation (7 Dimensions, 88.3% Accuracy)," arXiv:2512.10575, 2025.',
    '[33] PingPong, "Benchmarking Role-Playing Consistency of 40+ LLMs," arXiv:2409.06820, 2024.',
    '[34] Theanine, "Timeline-based Memory Management for Conversational Agents," arXiv:2406.10996, 2024.',
    '[35] PREMem, "Pre-Storage Reasoning for Episodic Memory in LLM Agents," arXiv, 2025.',
    '[36] RMM, "Reflective Memory Management for Conversational Agents," arXiv, 2025.',
    '[37] LiCoMemory, "CogniGraph Hierarchical Memory for LLMs," arXiv, 2025.',
    '[38] ENGRAM, "Lightweight Memory Orchestrator for LLM Agents," arXiv, 2025.',
    '[39] Y. Guo et al., "PA-RAG: RAG Alignment via Knowledge Injection with Diverse Augmentation," NAACL, 2025.',
    '[40] RuAG, "Learned-Rule-Augmented Generation for Large Language Models," arXiv:2411.03349, 2024.',
    '[41] KG-RAG at Adobe, "Incremental Knowledge Graph from 17K+ Documents, 51.9% Reduction in Irrelevant Answers," FSE, 2025.',
    '[42] SPIRES, "Structured Prompt Interrogation for Recursive Knowledge Extraction," arXiv, 2025.',
    '[43] OntoRAG, "Automated Ontology Derivation from Unstructured Knowledge Bases, 85% Win Rate vs Standard RAG," arXiv:2506.00664, 2025.',
    '[44] GoGs, "Goal-Oriented Graphs for Game Knowledge Retrieval," arXiv:2505.18607, 2025.',
    '[45] Knowledge Retrieval in LLM Gaming, "Knowledge Retrieval for LLM-Based Game Agents," arXiv:2505.18607, 2025.',
    '[46] ST-RPG Chatbot, "Two-LLM Architecture for State Tracking in Role-Playing Games (86% Token Saving)," GitHub, 2025.',
    '[47] LL-DM, "LLM-Powered Dungeon Master with SQL+LLM Long Memory for D&D," UC Berkeley MIDS Capstone, 2024.',
    '[48] BERALL, "Retrieval-Augmented State-based Interactive Fiction Games," UMBC, 2024.',
    '[49] ITMO-Agentic-AI, "8-Agent Multi-Agent DM Architecture via LangGraph," ai-dungeon-master, GitHub, 2025.',
    '[50] ai_rpg, "Complete Single-Player TRPG Framework with NPC Memory, Skill Checks, Scene Summaries," GitHub, 2024–2026.',
    '[51] StruQ, "Defending Against Prompt Injection with Structured Queries," arXiv:2402.06363, 2024.',
    '[52] Instructional Segment Embedding, "Improving LLM Safety via Instruction Hierarchy," arXiv:2410.09102, 2024.',
    '[53] Jodie Prompt, "Grounding LLMs to In-prompt Instructions (+28% Accuracy)," LREC-COLING, 2024.',
    '[54] NeverEndingQuest, "Hub-and-Spoke Modular Architecture for RPG Memory (85–92% Token Compression)," GitHub, 2025.',
    '[55] Chasm, "Vector DB for Persistent World State with Character Events and Dialogue," GitHub, 2024–2025.',
    '[56] SillyTavern Memory Books (STMB), "Multi-Layer Memory Integration (Scene→Arc→Chapter→Book→Epic)," GitHub, 2025.',
    '[57] NemoLore, "Intelligent Memory Management for SillyTavern (Auto-Summary + Core Memory + Vector Retrieval)," GitHub, 2025.',
    '[58] Timeline Memory, "Agentic Tool-Calling Memory with Autonomous Lore Editing for SillyTavern," GitHub, 2025.',
    '[59] Vending-Bench, ">20M Token Tests: Strategy and Error-Accumulation as Main Cause of Long-Term Derailment," Andon Labs, arXiv:2502.15840, 2025.',
    '[60] "Lost in the Middle Revisited: U-shaped Curve as Emergent Property from Pretraining Competition Demands," Rutgers, arXiv:2510.10276, 2025.',
    '[61] "Found in the Middle: Calibrating Positional Attention Bias (+15pp RAG Task Improvement)," ACL Findings, arXiv:2406.16008, 2024.',
    '[62] "LLM Game Agents Survey: Systematic Survey of Memory/Reasoning/IO Architectures," Georgia Tech, arXiv:2404.02039, 2024.',
    '[63] Latitude Voyage, "Deterministic World Engine alongside LLM Tracking Thousands of Turns," GamesBeat Interview, Industry, 2024.',
    '[64] Wayfarer-12B, "Fine-tuned Model for Text Adventure Games," Latitude Games, HuggingFace, 2024.',
    '[65] Evo-Memory, "Streaming Benchmark for Self-Evolving Memory in LLM Agents," arXiv, 2025.',
    '[66] DZ-TDPO, "State Inertia" Phenomenon in Mutable State Tracking, arXiv:2512.03704, 2025.',
    '[67] Adaptive Focus Memory, "Early High-Impact Constraints Drift Out of Context in Long-Context LLMs," arXiv:2511.12712, 2025.',
    '[68] Multi-Turn RL Persona, "3 Drift Metrics (P2L/L2L/Q&A Consistency), RL Reduces Inconsistency 55%+," arXiv:2511.00222, 2025.',
    '[69] Event-Centric Memory, "Heterogeneous Graph Approach for Long-Term Conversational Memory," arXiv:2511.17208, 2025.',
    '[70] State-Update Prompting, "32.6% Information Filtering Improvement for Long-Context LLMs," BUPT, arXiv:2509.17766, 2025.',
]

for ref in references:
    add_para(ref, font_size=10, spacing_after=2)

add_para('')
add_para(
    '*注：参考文献格式遵循IEEE引用规范。部分条目为预印本（arXiv）或开源项目（GitHub），以可获得的最新版本为准。',
    font_size=10
)
