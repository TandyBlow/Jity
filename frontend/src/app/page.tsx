"use client";

import { BookOpen, History, Loader2, RefreshCw, Send, Sparkles } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { createSession, generateScene } from "@/lib/api";
import type { GameState, GenerateResponse, ItemMemory, NPCMemory, QuestMemory, RetrievedChunk, StoryOutput, WorldFactMemory } from "@/types";

const initialOutput: StoryOutput = {
  narration: `雨是在你下车后三分钟开始变大的。

你拖着那只从婶婶家带来的旧行李箱，站在卡塞尔学院报到处大厅门口。箱轮卡在门槛细缝里，发出一声很丢人的“咔哒”。你低头用力拽了两下，没拽动。

大厅里没人笑。

这反而更可怕。

头顶的水晶吊灯亮得像某种审判现场，光落在黑色大理石地面上，碎成一片片冰冷的白。周围来来往往的学生都穿着深色制服，肩线挺拔，步伐安静，眼神锐利得不像是在上大学，更像是刚从某个不许写进新闻里的军事训练基地出来。

你看见一个男生手里拎着小提琴盒，盒角却露出金属锁扣。另一个女生路过报到台时，袖口下方闪过一枚细小的银色徽章。投影屏正在滚动新生名单，你的名字混在一串英文、编号和血红色的校徽之间，像一只误入狼群的土狗。

你咽了口唾沫。

你本来想找个角落站着，先装作自己只是来送外卖的。可就在这时，身后有人轻轻拍了拍你的肩膀。

你回头，看见一个红发女孩站在雨幕和大厅灯光交界的地方。她的校服外套随意搭在肩上，手里捏着一张临时通行卡，卡面上的火漆纹路像刚被点燃过。

她看了看你，又看了看你那个旧行李箱。

她的表情像是在确认一件快递有没有送错地址。`,
  dialogue: [
    {
      speaker: "诺诺",
      text: `路明非对吧？

古德里安教授让我来接你。

不过说实话，你看起来比档案里还要……朴素一点。

没人告诉过你，这里不是普通大学吗？`,
    },
  ],
  scene_prompt: "dark gothic academy registration hall, nervous freshman, crystal chandelier",
  sanity_delta: 0,
  health_delta: 0,
  options: [
    "愣住两秒，然后硬着头皮打招呼：“学姐好……那个，这里到底有什么不普通的？”",
    "下意识后退半步，抓紧行李箱拉杆：“等等，你怎么知道我的名字？这是什么整蛊节目吗？”",
    "试图挤出个笑脸，但声音有点抖：“照片？什么照片？我那张高考准考证上的照片可丑了……”",
  ],
  game_over: false,
  game_over_reason: "",
  current_location: "卡塞尔学院报到处大厅",
};

const DEFAULT_STORY_STYLE = "黑暗学院奇幻，带一点黑色幽默，强调 NPC 反应。";
const DEFAULT_CONSTRAINTS = "关键 NPC 不能突然死亡；不要跳出当前入学调查。";
const INITIAL_ACTION = "愣住两秒，然后硬着头皮打招呼：“学姐好……那个，这里到底有什么不普通的？”";

export default function Home() {
  const [sessionId, setSessionId] = useState("");
  const [model, setModel] = useState("deepseek-chat");
  const [state, setState] = useState<GameState | null>(null);
  const [output, setOutput] = useState<StoryOutput>(initialOutput);
  const [outputSource, setOutputSource] = useState<GenerateResponse["source"]>("scripted");
  const [chunks, setChunks] = useState<RetrievedChunk[]>([]);
  const [action, setAction] = useState(INITIAL_ACTION);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let mounted = true;
    createSession(model)
      .then((session) => {
        if (!mounted) return;
        setSessionId(session.session_id);
        setState(session.state);
        setModel(session.model);
      })
      .catch((err: Error) => setError(err.message));
    return () => {
      mounted = false;
    };
  }, []);

  async function handleGenerate(nextAction = action) {
    if (!sessionId || !nextAction.trim()) return;
    setIsLoading(true);
    setError("");
    try {
      const response: GenerateResponse = await generateScene({
        sessionId,
        playerAction: nextAction,
        model,
        style: DEFAULT_STORY_STYLE,
        constraints: DEFAULT_CONSTRAINTS,
      });
      setOutput(response.output);
      setOutputSource(response.source);
      setState(response.state);
      setChunks(response.retrieved_chunks);
      setModel(response.used_model);
      setAction("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "生成失败");
    } finally {
      setIsLoading(false);
    }
  }

  async function handleNewSession() {
    setIsLoading(true);
    setError("");
    try {
      const session = await createSession(model);
      setSessionId(session.session_id);
      setState(session.state);
      setOutput(initialOutput);
      setOutputSource("scripted");
      setChunks([]);
      setAction(INITIAL_ACTION);
    } catch (err) {
      setError(err instanceof Error ? err.message : "创建会话失败");
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <main className="app-shell">
      <aside className="side-panel">
        <div className="brand-row">
          <div>
            <div className="brand-mark">Jity</div>
            <div className="brand-subtitle">GM scenario console</div>
          </div>
          <div className="brand-actions">
            <Link className="icon-button" href="/dev-log" title="开发日志">
              <History size={17} />
            </Link>
            <button className="icon-button" onClick={handleNewSession} title="新建会话" type="button">
              <RefreshCw size={17} />
            </button>
          </div>
        </div>

        <label className="label" htmlFor="model">
          模型
        </label>
        <select className="select" id="model" value={model} onChange={(event) => setModel(event.target.value)}>
          <option value="deepseek-chat">deepseek-chat</option>
          <option value="deepseek-reasoner">deepseek-reasoner</option>
        </select>

        <label className="label" htmlFor="action">
          玩家行动
        </label>
        <textarea
          className="textarea"
          id="action"
          value={action}
          onChange={(event) => setAction(event.target.value)}
          placeholder="输入玩家行动、当前场景或 GM 限制"
        />

        <button className="primary-button" disabled={isLoading || !sessionId} onClick={() => handleGenerate()} type="button">
          {isLoading ? <Loader2 size={17} /> : <Send size={17} />}
          {isLoading ? "生成中" : "生成下一幕"}
        </button>
        {error ? <div className="error">{error}</div> : null}
      </aside>

      <section className="story-panel">
        <div className="toolbar-row">
          <div className="meta">Session {sessionId ? sessionId.slice(0, 8) : "initializing"}</div>
          <div className="meta">Turn {state?.turn ?? 0}</div>
          <div className={`source-pill ${outputSource}`}>{outputSource === "scripted" ? "Scripted opening" : "LLM generated"}</div>
        </div>

        <article className="scene-output">
          <div className="narration">{output.narration}</div>
          <div className="dialogue-list">
            {output.dialogue.map((line, index) => (
              <div className="dialogue-line" key={`${line.speaker}-${index}`}>
                <span className="speaker">{line.speaker}：</span>
                <span className="dialogue-text">{quoteDialogue(line.text)}</span>
              </div>
            ))}
          </div>
          <div className="option-list">
            {output.options.map((option) => (
              <button className="option-button" key={option} onClick={() => handleGenerate(option)} type="button">
                {option}
              </button>
            ))}
          </div>
        </article>
      </section>

      <aside className="memory-panel">
        <div className="section-title">
          <span>Context Memory</span>
          <Sparkles size={16} />
        </div>

        <MemorySection
          title="当前状态"
          items={[
            `地点：${state?.current_location ?? output.current_location}`,
            `状态：${state?.player_status?.condition ?? "新生报到中"}`,
            `危险等级：${state?.player_status?.danger_level ?? "medium"}`,
            `当前目标：${state?.player_status?.current_goal ?? "完成卡塞尔学院入学报到"}`,
          ]}
        />

        <div className="stat-block">
          <div className="stat-row">
            <span>血统稳定</span>
            <strong>{state?.sanity ?? 80}</strong>
          </div>
          <div className="bar">
            <div className="bar-fill" style={{ width: `${state?.sanity ?? 80}%` }} />
          </div>
        </div>
        <div className="stat-block">
          <div className="stat-row">
            <span>体力</span>
            <strong>{state?.health ?? 100}</strong>
          </div>
          <div className="bar">
            <div className="bar-fill health" style={{ width: `${state?.health ?? 100}%` }} />
          </div>
        </div>

        <MemoryObjects title="同伴与 NPC" items={state?.npcs ?? []} kind="npc" />
        <MemoryObjects title="关键物品" items={state?.items ?? []} kind="item" />
        <MemoryObjects title="任务" items={state?.quests ?? []} kind="quest" />
        <MemoryObjects title="长期事实" items={state?.world_facts ?? []} kind="world_fact" />
        <MemorySection title="最近事件" items={state?.recent_events ?? []} />

        <div className="section-title">
          <span>RAG Hits</span>
          <BookOpen size={16} />
        </div>
        <div className="chunk-list">
          {chunks.length ? (
            chunks.map((chunk) => (
              <div className="chunk-item" key={chunk.id}>
                <div className="chunk-head">
                  <span className={`chunk-badge ${chunk.source_type}`}>{sourceTypeLabel(chunk.source_type)}</span>
                  <span className="chunk-score">score {chunk.score.toFixed(2)}</span>
                </div>
                <div className="chunk-title">{chunk.title}</div>
                <p>{shorten(chunk.content, 120)}</p>
                {chunk.keywords?.length ? (
                  <div className="keyword-row">
                    {chunk.keywords.slice(0, 4).map((keyword) => (
                      <span className="keyword-chip" key={`${chunk.id}-${keyword}`}>
                        {keyword}
                      </span>
                    ))}
                  </div>
                ) : null}
              </div>
            ))
          ) : (
            <div className="memory-item">首次生成后会显示检索命中的规则、NPC 和地点资料。</div>
          )}
        </div>
      </aside>
    </main>
  );
}

function quoteDialogue(text: string) {
  const trimmed = text.trim();
  if (!trimmed) return "";
  if (trimmed.startsWith("“") && trimmed.endsWith("”")) return trimmed;
  return `“${trimmed}”`;
}

function sourceTypeLabel(sourceType: string) {
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

function shorten(text: string, limit: number) {
  const compact = text.replace(/\s+/g, " ").trim();
  if (compact.length <= limit) return compact;
  return `${compact.slice(0, limit)}...`;
}

function MemorySection({ title, items }: { title: string; items: string[] }) {
  return (
    <>
      <div className="section-title">{title}</div>
      <div className="memory-list">
        {items.filter(Boolean).length ? (
          items.filter(Boolean).map((item) => (
            <div className="memory-item" key={item}>
              {item}
            </div>
          ))
        ) : (
          <div className="memory-item">暂无记录</div>
        )}
      </div>
    </>
  );
}

function MemoryObjects({
  title,
  items,
  kind,
}: {
  title: string;
  items: Array<ItemMemory | NPCMemory | QuestMemory | WorldFactMemory>;
  kind: "item" | "npc" | "quest" | "world_fact";
}) {
  return (
    <>
      <div className="section-title">{title}</div>
      <div className="memory-list">
        {items.length ? (
          items.map((item, index) => (
            <div className="memory-item" key={`${item.name}-${index}`}>
              <div className="memory-head">
                <strong>{item.name ?? "未命名"}</strong>
                {item.status ? <span className="memory-status">{item.status}</span> : null}
              </div>
              <div className="meta">{memoryDetail(item, kind)}</div>
            </div>
          ))
        ) : (
          <div className="memory-item">暂无记录</div>
        )}
      </div>
    </>
  );
}

function memoryDetail(item: ItemMemory | NPCMemory | QuestMemory | WorldFactMemory, kind: "item" | "npc" | "quest" | "world_fact") {
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
