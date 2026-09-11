"""HaluMem evaluation prompt templates."""

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
