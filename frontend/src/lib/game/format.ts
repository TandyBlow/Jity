import type { ItemMemory, NPCMemory, QuestMemory, StoryOutput, WorldFactMemory } from "@/types";

export function quoteDialogue(text: string) {
  const trimmed = text.trim();
  if (!trimmed) return "";
  if (trimmed.startsWith("“") && trimmed.endsWith("”")) return trimmed;
  return `“${trimmed}”`;
}

export function sourceTypeLabel(sourceType: string) {
  const labels: Record<string, string> = {
    npc: "NPC",
    npc_profile: "NPC",
    location: "地点",
    quest: "任务",
    quest_template: "任务",
    rule: "规则",
    world_lore: "世界观",
  };
  return labels[sourceType] ?? sourceType;
}

export function shorten(text: string, limit: number) {
  const compact = text.replace(/\s+/g, " ").trim();
  if (compact.length <= limit) return compact;
  return `${compact.slice(0, limit)}...`;
}

export function buildStatusDeltaHints(output: StoryOutput) {
  return [
    {
      label: "血统稳定",
      delta: output.sanity_delta,
      kind: output.sanity_delta < 0 ? "loss" : "gain",
      message: output.sanity_delta < 0 ? "龙文、异常信息或精神压力造成了影响。" : "你暂时稳住了精神压力。",
    },
    {
      label: "体力",
      delta: output.health_delta,
      kind: output.health_delta < 0 ? "loss" : "gain",
      message: output.health_delta < 0 ? "这次行动带来了身体损耗。" : "身体状态有所恢复。",
    },
  ].filter((hint) => hint.delta !== 0);
}

export function formatDelta(delta: number) {
  return `${delta > 0 ? "+" : ""}${delta}`;
}

export function memoryDetail(
  item: ItemMemory | NPCMemory | QuestMemory | WorldFactMemory,
  kind: "item" | "npc" | "quest" | "world_fact",
) {
  if (kind === "npc") {
    const npc = item as NPCMemory;
    return [npc.relationship, npc.current_location, npc.description, npc.notes].filter(Boolean).join(" · ") || "已记录";
  }
  if (kind === "quest") {
    const quest = item as QuestMemory;
    return [quest.objective, quest.description, quest.notes].filter(Boolean).join(" · ") || "已记录";
  }
  if (kind === "world_fact") {
    const fact = item as WorldFactMemory;
    return [fact.description, fact.source, fact.notes].filter(Boolean).join(" · ") || "已记录";
  }
  const itemMemory = item as ItemMemory;
  return [itemMemory.description, itemMemory.location, itemMemory.notes].filter(Boolean).join(" · ") || "已记录";
}
