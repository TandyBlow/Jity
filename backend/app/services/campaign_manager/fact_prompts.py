"""Fact-extraction prompt templates (sole consumer: CampaignManager)."""

_FACT_EXTRACTION_PROMPT = """你是一个TRPG叙事分析系统。从以下最近5个回合的叙事内容中提取新发现的世界事实。

要求：
1. 只提取本轮新发现的事实——不要重复已经知道的信息
2. 每个事实包含：name（简短名称）、description（详细描述）、status（已知known/推测suspected/确认resolved）
3. 如果未发现新事实，返回空数组
4. 关注异常、悬疑、重要叙事元素

输出格式（严格的JSON数组）：
[
  {"name": "事实名", "description": "详细描述", "status": "known"}
]"""


def build_fact_extraction(narration_text: str, recent_events: list[str]) -> str:
    """Build prompt for batch fact extraction from recent turns."""
    events_text = "\n".join(f"- {e}" for e in recent_events[-5:])
    return (
        f"{_FACT_EXTRACTION_PROMPT}\n\n"
        f"## 最近事件\n{events_text}\n\n"
        f"## 最新叙事\n{narration_text}"
    )
