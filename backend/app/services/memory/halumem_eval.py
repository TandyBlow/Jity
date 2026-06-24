"""HaluMem Evaluation Runner (Chen et al., 2025).

Operation-level hallucination evaluation for memory systems:
  1. Memory Extraction — accuracy and coverage (fabrication, error)
  2. Memory Updating — consistency (conflict, omission)
  3. Memory Question Answering — end-to-end hallucination detection

Evaluates the integrated memory system against ground-truth annotations
across three operational stages.

Usage:
    evaluator = HaluMemEvaluator(llm_client)
    findings = await evaluator.evaluate_extraction(
        extracted_memories=...,
        ground_truth=...,
    )
"""

import logging
from typing import Any

from app.schemas.agent_io import HallucinationFinding, HallucinationType
from app.services.llm_client import LLMClient

logger = logging.getLogger(__name__)

_EXTRACTION_EVAL_PROMPT = """你是记忆系统评测专家。对比"提取的记忆"和"标注的真值"，检测四类幻觉：

1. Fabrication（虚构）：提取的记忆包含标注中不存在的信息
2. Error（错误）：提取的记忆包含标注中存在但被错误记录的信息
3. Conflict（冲突）：同一实体的多条记忆相互矛盾
4. Omission（遗漏）：标注中存在但记忆系统未提取的关键信息

输出格式（严格JSON）：
{
  "findings": [
    {
      "hallucination_type": "fabrication|error|conflict|omission",
      "memory_id": "被评估的记忆ID",
      "description": "具体描述幻觉内容",
      "ground_truth": "正确的值（如已知）"
    }
  ]
}

只标记确实存在问题的记忆，不要为了找问题而找问题。"""

_UPDATE_EVAL_PROMPT = """你是记忆系统评测专家。对比"系统更新的记忆"和"标注的真值"，检测更新阶段的幻觉：

1. Conflict（冲突）：新记忆与旧记忆矛盾，但系统未正确处理
2. Omission（遗漏）：应该更新但未更新的记忆
3. Error（错误）：更新了但内容不正确

输出格式（严格JSON）：
{
  "findings": [
    {
      "hallucination_type": "conflict|omission|error",
      "memory_id": "被评估的记忆ID",
      "description": "具体描述更新问题",
      "ground_truth": "正确的值"
    }
  ]
}"""

_QA_EVAL_PROMPT = """你是记忆系统评测专家。对比"系统回答"和"标准答案"，检测记忆问答阶段的幻觉：

1. Fabrication（虚构）：回答中包含记忆中不存在的信息
2. Error（错误）：回答中引用了错误记忆
3. Conflict（冲突）：回答与已知记忆矛盾

输出格式（严格JSON）：
{
  "findings": [
    {
      "hallucination_type": "fabrication|error|conflict",
      "memory_id": "",
      "description": "具体描述幻觉内容",
      "ground_truth": "标准答案"
    }
  ]
}"""


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
        all_findings = extraction_findings + update_findings + qa_findings
        type_counts: dict[str, int] = {t.value: 0 for t in HallucinationType}
        stage_counts = {"extraction": len(extraction_findings),
                        "updating": len(update_findings),
                        "qa": len(qa_findings)}

        for f in all_findings:
            type_counts[f.hallucination_type.value] += 1

        return {
            "total_findings": len(all_findings),
            "extraction_findings": len(extraction_findings),
            "update_findings": len(update_findings),
            "qa_findings": len(qa_findings),
            "fabrications": type_counts["fabrication"],
            "errors": type_counts["error"],
            "conflicts": type_counts["conflict"],
            "omissions": type_counts["omission"],
            "hallucination_rate": (
                len(all_findings) / max(total_expected_memories, 1)
            ),
        }


def _parse_findings(data: dict[str, Any]) -> list[HallucinationFinding]:
    """Parse raw JSON into HallucinationFinding list."""
    items = data.get("findings", [])
    if not isinstance(items, list):
        return []

    findings: list[HallucinationFinding] = []
    for item in items:
        if not isinstance(item, dict) or "description" not in item:
            continue
        h_type = item.get("hallucination_type", "fabrication")
        try:
            ht = HallucinationType(h_type)
        except ValueError:
            ht = HallucinationType.FABRICATION

        findings.append(HallucinationFinding(
            hallucination_type=ht,
            memory_id=str(item.get("memory_id", "")),
            description=str(item["description"]),
            ground_truth=str(item.get("ground_truth", "")),
        ))
    return findings
