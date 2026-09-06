"""Parsing and metrics helpers for HaluMem evaluation."""

from typing import Any

from app.schemas.agent_io import HallucinationFinding, HallucinationType


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


def compute_metrics(
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
