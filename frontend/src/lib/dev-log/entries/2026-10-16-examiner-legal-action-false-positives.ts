import type { DevLogEntry } from "@/lib/dev-log/types";

export const entry: DevLogEntry = {
  id: "2026-10-16-examiner-legal-action-false-positives",
  date: "2026-10-16",
  title: "修复 Examiner 对合法行动的误判",
  summary: "收紧中文物品使用语句的识别边界，区分背包物品、身体部位与普通叙事短语，避免合法行动被错误拦截并消耗剧情节奏。",
  developer: "tobi",
  areas: ["backend", "examiner", "campaign", "narrative", "tests"],
  changes: [
    "修复裸词‘用’的匹配边界：不再把‘利用’‘备用’‘采用’末尾的‘用’识别为物品使用动作，避免‘寻找备用通道’被错误解析成‘使用物品：通道’。",
    "保留‘使用’‘拿出’‘掏出’‘举起’‘装备’等明确物品动作的严格库存校验，同时继续排除‘用力’‘用心’‘用尽’等状态或程度表达。",
    "将掌心、手指、伤口、血液、目光和身体等具身资源视为场景中天然可用的行动条件，不再要求它们预先登记为背包物品；实际效果仍由叙事模型和检定决定。",
    "放行‘用的是哪一类工具’等询问与判断句，避免把被询问对象误当作玩家声称持有的道具。",
    "幕间转场的首个行动不再被 Examiner 用上一幕的地点与物品状态提前否决，玩家选择会先与下一幕开场事实融合，再进入正常规则判定。",
    "Examiner 拦截结果不再推进 turns_total、turn_in_session 或 session_closing，解析误判和确实非法的尝试都不会挤占有效叙事回合预算。",
    "新增中文边界、具身行动、询问句与回合预算回归用例；全量后端测试 634 项通过。",
  ],
  relatedFiles: [
    "backend/app/services/agents/examiner.py",
    "backend/app/services/scenario_generator/agent_pipeline.py",
    "backend/app/services/scenario_generator/post_generation.py",
    "backend/tests/test_local_examiner.py",
    "backend/tests/test_campaign_budget_edges.py",
    "backend/tests/test_turn_commit_consistency.py",
  ],
  nextSteps: [
    "继续从真实游玩日志补充中文动作语料，重点覆盖复合句、省略主语、场景临时物和身体状态的表达。",
    "为 Examiner 增加结构化解析诊断，记录命中的动词、候选物品与放行原因，方便定位新的误判。",
    "统一自动跑剧情的尝试次数与有效战役回合展示，避免被拦截行动造成两个计数并存。",
  ],
};
