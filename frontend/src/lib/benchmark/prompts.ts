/**
 * Synthetic sectioned prompts for the benchmark, mirroring the shape of the
 * production PromptBuilder output (campaign context → state header → memory
 * injection → recent dialogue → player action) so prefill timing is
 * representative of a real component call.
 *
 * Token budgets cannot be hit exactly without running the model's tokenizer,
 * and wllama does not expose one. Every measured run therefore records the
 * ACTUAL prompt_tokens from the completion response; `charRatio` (chars per
 * token, calibrated per model by the runner) only brings the request close to
 * the nominal档位.
 *
 * The budget is a hard cap, not a minimum: when the nominal档位 is smaller
 * than the fixed sections, every section is clipped proportionally down to a
 * small floor, so a 64-token prompt measures like a 64-token prompt instead
 * of silently staying at the skeleton size.
 */

export type PromptSection = { name: string; text: string };

const FILLER_SENTENCES = [
  "图书馆高窗外的云影缓缓掠过石质书架，尘埃在斜照的光柱里浮动。",
  "走廊尽头的挂钟停在三点半，齿轮上覆着一层没有人擦拭过的灰。",
  "他用指尖抚过摊开的地图，纸页边缘已经被人反复翻阅得起了毛。",
  "远处的操场传来隐约的哨声，随即又被风声揉碎在楼宇之间。",
  "她把校徽翻转过来，背面刻着的编号在灯光下几乎看不清楚。",
  "地下室的水管发出规律的滴答声，像某种耐心的倒计时。",
  "名单上的第三个名字被红笔划掉了，划痕深得几乎穿透纸背。",
  "楼梯间的灯又熄了一盏，黑暗从顶层开始一段一段地漫下来。",
  "信封里只有半张车票，撕口整齐得像是有人用尺子比着裁开的。",
  "教室后排的椅子上放着一本没人认领的笔记本，扉页写着日期。",
  "雨点开始敲打天窗，节奏忽快忽慢，盖过了大厅里的交谈声。",
  "他数过门廊的立柱，一共十四根，但照片里明显只有十三根。",
  "风吹动布告栏里的传单，露出下面一层更旧的、已经褪色的通知。",
  "控制室的仪表指针停在绿色区域边缘，偶尔朝红色轻轻颤动一下。",
  "她记得那扇门原本朝东，可现在它开在了走廊的另一侧。",
  "咖啡凉透了，杯壁上的口红印旁边多出一枚陌生的指纹。",
  "广播里的女声念到一半忽然中断，只剩下十几秒空白的电流杂音。",
  "盆栽的叶片全部朝向同一个方向，尽管窗户在房间的另一头。",
  "值班室的登记簿最后一页被人撕去了，装订线上还留着纸茬。",
  "暮色降临后，教学楼里的每一扇亮着的窗都像一次无声的点名。",
];

/** Deterministic PRNG so a given seed always rebuilds the same prompt. */
function mulberry32(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) | 0;
    let t = Math.imul(state ^ (state >>> 15), 1 | state);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export type PromptParams = {
  totalTokens: number;
  memoryTokens: number;
  nonce: number;
  /** chars per token; calibrated against the loaded model. Default 1.0. */
  charRatio?: number;
};

export const sectionChars = (text: string): number => [...text].length;

/** Clip to a character budget, marking the cut so clipped prompts are visible. */
function clipChars(text: string, maxChars: number): string {
  if (maxChars <= 0) return "";
  if (sectionChars(text) <= maxChars) return text;
  return `${[...text].slice(0, maxChars - 1).join("")}…`;
}

function fillerLines(charBudget: number, rand: () => number, tag: string): string {
  const lines: string[] = [];
  let used = 0;
  let index = 0;
  while (used < charBudget) {
    const sentence = FILLER_SENTENCES[Math.floor(rand() * FILLER_SENTENCES.length)];
    const line = `- ${sentence}（${tag}${index}）`;
    lines.push(line);
    used += sectionChars(line) + 1;
    index += 1;
  }
  return lines.join("\n");
}

/** Per-section character floors: what survives even at the smallest档位. */
const SECTION_FLOORS: Record<string, number> = {
  campaign_context: 24,
  system_state: 20,
  messages: 16,
  player_action: 24,
};

/**
 * Distribute `budget` chars across sections proportional to their full size,
 * never below each floor. When floors bind, the largest allocations are
 * shaved first.
 */
function allocate(fullLens: number[], floors: number[], budget: number): number[] {
  const totalFull = fullLens.reduce((sum, len) => sum + len, 0);
  if (budget >= totalFull) return fullLens.slice();

  const alloc = fullLens.map((len, index) =>
    Math.max(floors[index], Math.round(len * (budget / totalFull))),
  );
  const shavable = alloc
    .map((value, index) => ({ index, slack: value - floors[index] }))
    .filter((entry) => entry.slack > 0)
    .sort((a, b) => b.slack - a.slack);

  let sum = alloc.reduce((sum, value) => sum + value, 0);
  let cursor = 0;
  while (sum > budget && shavable.length > 0) {
    const entry = shavable[cursor % shavable.length];
    if (alloc[entry.index] > floors[entry.index]) {
      alloc[entry.index] -= 1;
      sum -= 1;
    }
    cursor += 1;
    if (cursor > budget + totalFull) break; // safety valve, floors always fit
  }
  return alloc;
}

/**
 * Build one sectioned prompt. `totalTokens` and `memoryTokens` are nominal;
 * the runner records the tokenizer's actual count for every run.
 */
export function buildSections(params: PromptParams): PromptSection[] {
  const charRatio = params.charRatio ?? 1.0;
  const totalChars = Math.max(24, Math.round(params.totalTokens * charRatio));
  const memoryChars = Math.min(
    Math.round(params.memoryTokens * charRatio),
    Math.floor(totalChars * 0.9),
  );
  const rand = mulberry32(params.nonce);

  const fullSections: Array<{ name: string; text: string }> = [
    {
      name: "campaign_context",
      // The nonce leads the VERY first token so llama.cpp's prefix cache
      // cannot hit across runs — a hit would understate prefill. Any shared
      // characters before the first divergence are reused as cached tokens.
      text: `（样本${params.nonce}）## 战役上下文\n当前战役：黑月之潮。当前章节：龙族Ⅲ — 高天原的阴影。章节目标：查明蛇岐八家的真正目的。\n锚点进度：2/9 已揭示。人物关系变化：绘梨衣 信任上升(+2)，源稚生 中性(+0)。`,
    },
    {
      name: "system_state",
      text: `## 当前状态\n当前地点：卡塞尔学院图书馆。血统稳定：72/100。体力：88/100。回合：${17 + (params.nonce % 7)}。\n玩家状态：调查中 · danger_level=medium · 当前目标：找到那本被撕掉登记页的值班记录。`,
    },
    {
      name: "messages",
      text: `## 最近对话历史\n[玩家]: 我要查阅上周的值班登记簿。\n[主持人]: 管理员说登记簿就在值班室，但当你翻开时，最后一页已经被撕掉了。\n[玩家]: 询问管理员谁最后接触过登记簿。\n[主持人]: 管理员想了想，说深夜只有巡夜的学生来过（样本${params.nonce}）。`,
    },
    {
      name: "player_action",
      text: `## 玩家行动\n我去调查巡夜学生的名单，并核对当晚的出入记录（样本${params.nonce}）。`,
    },
  ];

  const memoryHeader = "## 长期叙事记忆";
  const memoryBody = clipChars(fillerLines(memoryChars, rand, "记忆"), memoryChars);
  const memoryText = clipChars(
    memoryBody ? `${memoryHeader}\n${memoryBody}` : memoryHeader,
    memoryChars,
  );

  const fullLens = fullSections.map((section) => sectionChars(section.text));
  const floors = fullSections.map((section) => SECTION_FLOORS[section.name] ?? 12);
  const remaining = Math.max(0, totalChars - sectionChars(memoryText));
  const alloc = allocate(fullLens, floors, remaining);

  const clipped = fullSections.map((section, index) => ({
    name: section.name,
    text: clipChars(section.text, alloc[index]),
  }));

  // Rules filler takes whatever the allocation did not spend.
  const usedChars =
    sectionChars(memoryText) + clipped.reduce((sum, section) => sum + sectionChars(section.text), 0);
  const leftover = totalChars - usedChars;
  const withRules: PromptSection[] =
    leftover > 40
      ? [
          clipped[0],
          clipped[1],
          { name: "memory_injection", text: memoryText },
          {
            name: "style_rules",
            text: `## 生成规则（节选）\n${fillerLines(leftover, rand, "规则")}`,
          },
          clipped[2],
          clipped[3],
        ]
      : [
          clipped[0],
          clipped[1],
          { name: "memory_injection", text: memoryText },
          clipped[2],
          clipped[3],
        ];
  return withRules;
}

export function sectionsToPrompt(sections: PromptSection[]): string {
  return sections.map((section) => section.text).join("\n\n");
}

export function buildPrompt(params: PromptParams): string {
  return sectionsToPrompt(buildSections(params));
}

/** Total characters of a prompt, the basis for ratio calibration. */
export function promptChars(prompt: string): number {
  return [...prompt].length;
}

/**
 * Recalibrate chars-per-token from one probe: we built for `targetTokens`
 * using `charRatio`, and the tokenizer counted `measuredTokens`. One direct
 * correction is enough because the filler dominates and scales linearly.
 */
export function adjustCharRatio(
  charRatio: number,
  measuredTokens: number,
  targetTokens: number,
): number {
  if (measuredTokens <= 0 || targetTokens <= 0) return charRatio;
  const next = (charRatio * targetTokens) / measuredTokens;
  return Math.min(4.0, Math.max(0.5, Math.round(next * 1000) / 1000));
}
