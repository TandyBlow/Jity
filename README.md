# Jity

AI 驱动文字跑团游戏。LLM 推动叙事，玩家通过自由输入或选择选项推进剧情。

## 快速开始

```bash
cp config.example.js config.js
# 编辑 config.js，填入你的 API Key
# 用任意静态文件服务打开 index.html
python -m http.server 8080
# 浏览器打开 http://localhost:8080
```

也可以直接双击 `index.html` 在浏览器中打开。

## 架构

纯前端 vanilla JS，零依赖，无构建步骤。`index.html` 按顺序加载四个 JS 文件：

| 文件 | 全局变量 | 职责 |
|------|----------|------|
| `config.js` | `CONFIG` | API Key、模型名、初始数值、生图风格 |
| `api.js` | `API` | 调用 LLM 和图片生成接口，解析 JSON 响应 |
| `game.js` | `Game` | 状态机 — 管理 SAN/HP/历史/回合，构建 system prompt，编排 LLM + 图片调用 |
| `ui.js` | `UI` | 打字机叙事、对话淡入、选项按钮、状态条、背景图片过渡、加载遮罩 |

## 游戏循环

1. 玩家输入文字或点击选项 → `Game.playerAction(text)`
2. `Game.processAndRender()` 用当前状态 + 完整对话历史构建 system prompt，调用 `API.callLLM()`
3. LLM 返回结构化 JSON：
   - `narration` — 第一人称叙事
   - `dialogue[]` — NPC 对话
   - `scene_prompt` — 英文场景描述（用于生图）
   - `sanity_delta` / `health_delta` — 数值变化
   - `options[]` — 可选行动
   - `game_over` — 游戏结束标志
4. 数值钳制到 [0, 100]，同时用 `scene_prompt` 生成背景图片
5. `game_over` 为 true 或数值归零时触发结局

## 特色机制

**SAN 值驱动叙事。** SAN < 40 时叙事中出现幻觉与错乱，游戏机制实时反馈到 LLM 的叙事策略。

**分层记忆系统（L0）。** 将物品、NPC、任务、位置、近期事件结构化压缩为状态卡片注入 LLM 上下文，解决长对话中的状态遗忘问题。

## API

LLM 和图片生成均通过 SiliconFlow。模型配置见 `config.js`。

LLM 响应要求为纯 JSON，代码会清洗 ` ```json ` 围栏和 `<think>` 块后再解析。

## License

MIT
