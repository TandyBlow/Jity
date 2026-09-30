import type { StoryOutput } from "@/types";

export const CAMPAIGN_STORY_STYLE = "延续当前战役的叙事风格、时代背景和人物处境。";
export const CAMPAIGN_CONSTRAINTS = "遵循当前战役及本幕设定，承接最近剧情和玩家行动，保持人物与物品连续。";
export const loadingOutput: StoryOutput = {
  narration: "正在读取当前剧情……",
  dialogue: [], scene_prompt: "", options: [],
  sanity_delta: 0, health_delta: 0,
  game_over: false, game_over_reason: "", current_location: "",
};
export const SLOT_DEFAULT = "default" as const;
export const ENTRY_ACTION = "（入场）环顾四周，了解当前处境。";
