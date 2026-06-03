const Game = {

  state: {
    sanity: CONFIG.INITIAL_SANITY,
    health: CONFIG.INITIAL_HEALTH,
    history: [],
    isProcessing: false,
    currentImageUrl: null,
    turn: 0,
    // === L0 增强状态 ===
    items: [],           // 物品清单 [{name, description}]
    npcs: [],            // 活跃NPC [{name, disposition, notes}]
    quests: [],          // 任务 [{name, status, description}]
    recentEvents: [],    // 最近关键事件 (最多5条)
    currentLocation: "未知",
  },

  // L0 模式开关（实验用）
  l0Mode: false,

  buildSystemPrompt() {
    let prompt = `你是一个克苏鲁神话风格的TRPG游戏主持人（KP）。用中文进行第一人称叙事。

当前状态：SAN ${this.state.sanity}/100 | HP ${this.state.health}/100 | 第${this.state.turn}回合

叙事风格：
- 阴暗压抑，充满未知恐惧，描写细腻，善用感官细节制造不安
- 第一人称视角（"你"）
- SAN低于40时，叙事中出现幻觉与错乱

数值规则：
- sanity_delta：-20 到 +5，多数情况为负
- health_delta：-30 到 0，非战斗为0
- scene_prompt：英文，不超过30词
`;

    // L0 状态卡片 — 底部注入（实验验证：底部优于顶部 33pp）
    if (this.l0Mode) {
      prompt += `
【当前状态 — 必须遵守】
位置：${this.state.currentLocation}
物品：${this.state.items.length > 0 ? this.state.items.map(i => i.name).join("、") : "无"}
NPC：${this.state.npcs.length > 0 ? this.state.npcs.map(n => `${n.name}(${n.disposition})`).join("、") : "无"}
任务：${this.state.quests.length > 0 ? this.state.quests.map(q => `${q.name}[${q.status}]`).join("、") : "无"}
最近：${this.state.recentEvents.length > 0 ? this.state.recentEvents.slice(-5).map((e, i) => `${i + 1}. ${e}`).join("；") : "游戏开始"}
`;
    }

    // JSON 格式
    prompt += `
严格返回以下JSON格式，不得有任何额外内容：
{
  "narration": "第一人称叙事，2-4句",
  "dialogue": [{"speaker": "角色名", "text": "对话内容"}],
  "scene_prompt": "English scene description, max 30 words",
  "sanity_delta": 0,
  "health_delta": 0,
  "options": ["选项1", "选项2", "选项3"],
  "game_over": false,
  "game_over_reason": "",
  "current_location": ""`;

    if (this.l0Mode) {
      prompt += `,
  "items_gained": [],
  "items_lost": [],
  "npcs_encountered": [],
  "quests_updated": []`;
    }

    prompt += `
}
dialogue可为空数组[]。game_over仅在SAN归零或角色死亡时为true。`;

    if (this.l0Mode) {
      prompt += `
items_gained/lost、npcs_encountered、quests_updated为可选字段，仅在状态变化时填写。`;
    }

    return prompt;
  },

  // 更新 L0 状态
  updateL0State(result) {
    if (!this.l0Mode) return;

    // 物品变更
    (result.items_gained || []).forEach(item => {
      if (!this.state.items.find(i => i.name === item.name)) {
        this.state.items.push(item);
      }
    });
    (result.items_lost || []).forEach(lost => {
      this.state.items = this.state.items.filter(i => i.name !== lost.name);
    });

    // NPC 变更
    (result.npcs_encountered || []).forEach(npc => {
      const existing = this.state.npcs.find(n => n.name === npc.name);
      if (existing) {
        if (npc.disposition) existing.disposition = npc.disposition;
        if (npc.notes) existing.notes = npc.notes;
      } else {
        this.state.npcs.push({
          name: npc.name,
          disposition: npc.disposition || "中立",
          notes: npc.notes || ""
        });
      }
    });

    // 任务变更
    (result.quests_updated || []).forEach(quest => {
      const existing = this.state.quests.find(q => q.name === quest.name);
      if (existing) {
        if (quest.status) existing.status = quest.status;
        if (quest.description) existing.description = quest.description;
      } else {
        this.state.quests.push({
          name: quest.name,
          status: quest.status || "进行中",
          description: quest.description || ""
        });
      }
    });

    // 位置变更
    if (result.current_location) {
      this.state.currentLocation = result.current_location;
    }

    // 最近事件
    if (result.narration) {
      this.state.recentEvents.push(result.narration.slice(0, 80));
      if (this.state.recentEvents.length > 5) {
        this.state.recentEvents = this.state.recentEvents.slice(-5);
      }
    }
  },

  async start() {
    this.state.history = [];
    this.state.turn = 0;
    this.state.sanity = CONFIG.INITIAL_SANITY;
    this.state.health = CONFIG.INITIAL_HEALTH;
    this.state.items = [];
    this.state.npcs = [];
    this.state.quests = [];
    this.state.recentEvents = [];
    this.state.currentLocation = "未知";

    this.state.history.push({
      role: "user",
      content: "游戏开始。请生成一个克苏鲁风格的开场场景，我站在某条城市街道上，感到有些不对劲。"
    });

    await this.processAndRender();
  },

  async playerAction(input) {
    if (this.state.isProcessing) return;

    this.state.history.push({
      role: "user",
      content: input
    });

    await this.processAndRender();
  },

  async processAndRender() {
    this.state.isProcessing = true;
    UI.setLoading(true);

    try {
      const geminiPromise = API.callLLM(
        this.buildSystemPrompt(),
        this.state.history
      );

      const result = await geminiPromise;

      const imagePromise = API.generateImage(result.scene_prompt).catch(err => {
        console.warn("图片生成失败，跳过：", err);
        return null;
      });

      this.state.history.push({
        role: "model",
        content: JSON.stringify(result)
      });

      this.state.sanity = Math.max(0, Math.min(100, this.state.sanity + (result.sanity_delta || 0)));
      this.state.health = Math.max(0, Math.min(100, this.state.health + (result.health_delta || 0)));
      this.state.turn++;

      // 位置追踪（所有模式均更新）
      if (result.current_location) {
        this.state.currentLocation = result.current_location;
      }
      // L0 状态更新
      this.updateL0State(result);

      UI.renderNarration(result.narration);
      UI.renderDialogue(result.dialogue || []);
      UI.updateStats(this.state.sanity, this.state.health);

      UI.setImageLoading(true);
      const imageUrl = await imagePromise;
      if (imageUrl) {
        UI.setBackground(imageUrl);
        if (this.state.currentImageUrl) {
          URL.revokeObjectURL(this.state.currentImageUrl);
        }
        this.state.currentImageUrl = imageUrl;
      }
      UI.setImageLoading(false);

      if (result.game_over || this.state.sanity <= 0 || this.state.health <= 0) {
        UI.renderGameOver(result.game_over_reason || (this.state.sanity <= 0 ? "你的理智已彻底崩溃……" : "你死了。"));
        return;
      }

      UI.renderOptions(result.options || []);

    } catch (err) {
      UI.renderError(err.message);
      console.error(err);
    } finally {
      this.state.isProcessing = false;
      UI.setLoading(false);
    }
  }

};
