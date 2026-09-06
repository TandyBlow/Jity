"""HaluMem Evaluation Runner (Chen et al., 2025).

Operation-level hallucination evaluation for memory systems:
  1. Memory Extraction — accuracy and coverage (fabrication, error)
  2. Memory Updating — consistency (conflict, omission)
  3. Memory Question Answering — end-to-end hallucination detection

Usage:
    evaluator = HaluMemEvaluator(llm_client)
    findings = await evaluator.evaluate_extraction(
        extracted_memories=...,
        ground_truth=...,
    )
"""

import logging
from typing import Any

from app.schemas.agent_io import HallucinationFinding
from app.services.llm_client import LLMClient

from app.services.memory.halumem_eval.parsing import _parse_findings, compute_metrics
from app.services.memory.halumem_eval.prompts import (
    _EXTRACTION_EVAL_PROMPT,
    _QA_EVAL_PROMPT,
    _UPDATE_EVAL_PROMPT,
)

logger = logging.getLogger(__name__)


class HaluMemEvaluator:
    """Operation-level hallucination evaluator for the memory system.

    Runs three evaluation tasks:
      - Memory Extraction: checks extracted memories against ground truth
      - Memory Updating: checks update consistency
      - Memory Question Answering: checks end-to-end hallucination
    """

    def __init__(self, llm_client: LLMClient) -> None:
        self._llm = llm_client

    async def evaluate_extraction(
        self,
        extracted_memories: list[dict[str, Any]],
        ground_truth: list[dict[str, Any]],
    ) -> list[HallucinationFinding]:
        """Evaluate memory extraction quality against ground truth annotations.

        Args:
            extracted_memories: Memories produced by the system (list of {id, content, ...}).
            ground_truth: Human-annotated correct memory points (list of {id, content, ...}).

        Returns:
            List of HallucinationFinding with fabrications, errors, conflicts, omissions.
        """
        extracted_text = "\n".join(
            f"[{m.get('id', '?')}]: {m.get('content', str(m))}"
            for m in extracted_memories[:50]
        )
        gt_text = "\n".join(
            f"[{g.get('id', '?')}]: {g.get('content', str(g))}"
            for g in ground_truth[:50]
        )

        prompt = (
            f"{_EXTRACTION_EVAL_PROMPT}\n\n"
            f"## 系统提取的记忆\n{extracted_text or '无'}\n\n"
            f"## 标注真值\n{gt_text or '无'}"
        )

        try:
            result = await self._llm.generate_json(
                prompt=prompt,
                model="deepseek-v4-flash",
                max_tokens=2000,
                temperature=0.1,
            )
            return _parse_findings(result)
        except Exception:
            logger.warning("HaluMem extraction evaluation failed", exc_info=True)
            return []

    async def evaluate_updating(
        self,
        old_memories: list[dict[str, Any]],
        new_memories: list[dict[str, Any]],
        ground_truth: list[dict[str, Any]],
    ) -> list[HallucinationFinding]:
        """Evaluate memory updating consistency.

        Checks whether the system correctly updated old memories with new
        information against the ground truth annotations.
        """
        old_text = "\n".join(
            f"[{m.get('id', '?')}]: {m.get('content', str(m))}"
            for m in old_memories[:30]
        )
        new_text = "\n".join(
            f"[{m.get('id', '?')}]: {m.get('content', str(m))}"
            for m in new_memories[:30]
        )
        gt_text = "\n".join(
            f"[{g.get('id', '?')}]: {g.get('content', str(g))}"
            for g in ground_truth[:30]
        )

        prompt = (
            f"{_UPDATE_EVAL_PROMPT}\n\n"
            f"## 旧记忆\n{old_text or '无'}\n\n"
            f"## 新记忆\n{new_text or '无'}\n\n"
            f"## 标注真值\n{gt_text or '无'}"
        )

        try:
            result = await self._llm.generate_json(
                prompt=prompt,
                model="deepseek-v4-flash",
                max_tokens=2000,
                temperature=0.1,
            )
            return _parse_findings(result)
        except Exception:
            logger.warning("HaluMem updating evaluation failed", exc_info=True)
            return []

    async def evaluate_qa(
        self,
        system_response: str,
        reference_answer: str,
        related_memories: list[dict[str, Any]],
    ) -> list[HallucinationFinding]:
        """Evaluate memory-based question answering for hallucination."""
        memories_text = "\n".join(
            f"[{m.get('id', '?')}]: {m.get('content', str(m))}"
            for m in related_memories[:10]
        )

        prompt = (
            f"{_QA_EVAL_PROMPT}\n\n"
            f"## 相关记忆\n{memories_text or '无'}\n\n"
            f"## 系统回答\n{system_response}\n\n"
            f"## 标准答案\n{reference_answer}"
        )

        try:
            result = await self._llm.generate_json(
                prompt=prompt,
                model="deepseek-v4-flash",
                max_tokens=1000,
                temperature=0.1,
            )
            return _parse_findings(result)
        except Exception:
            logger.warning("HaluMem QA evaluation failed", exc_info=True)
            return []

    def compute_metrics(
        self,
        extraction_findings: list[HallucinationFinding],
        update_findings: list[HallucinationFinding],
        qa_findings: list[HallucinationFinding],
        total_expected_memories: int = 1,
    ) -> dict[str, Any]:
        """Compute aggregate HaluMem metrics from findings.

        Returns:
            Dict with hallucination rates per type and per stage.
        """
        return compute_metrics(
            extraction_findings, update_findings, qa_findings, total_expected_memories
        )
