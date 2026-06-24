"use client";

import { BookOpen, History, Loader2, MapPin, PenTool, RefreshCw, Send, Sparkles } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { createSession, createSlot, generateScene, getSessionHistory, listCampaigns, listSlots, loadSlot } from "@/lib/api";
import type { CampaignListItem, GameState, GenerateResponse, ItemMemory, NPCMemory, QuestMemory, RetrievedChunk, SaveSlot, StoryOutput, WorldFactMemory } from "@/types";

const initialOutput: StoryOutput = {
  narration: `雨是在你下车后三分钟开始变大的。

你拖着那只从婶婶家带来的旧行李箱，站在卡塞尔学院报到处大厅门口。箱轮卡在门槛细缝里，发出一声很丢人的"咔哒"。你低头用力拽了两下，没拽动。

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
    `愣住两秒，然后硬着头皮打招呼："学姐好……那个，这里到底有什么不普通的？"`,
    `下意识后退半步，抓紧行李箱拉杆："等等，你怎么知道我的名字？这是什么整蛊节目吗？"`,
    `试图挤出个笑脸，但声音有点抖："照片？什么照片？我那张高考准考证上的照片可丑了……"`,
  ],
  game_over: false,
  game_over_reason: "",
  current_location: "卡塞尔学院报到处大厅",
};

const DEFAULT_STORY_STYLE = "黑暗学院奇幻，带一点黑色幽默，强调 NPC 反应。";
const DEFAULT_CONSTRAINTS = "关键 NPC 不能突然死亡；不要跳出当前入学调查。";
const INITIAL_ACTION = `愣住两秒，然后硬着头皮打招呼："学姐好……那个，这里到底有什么不普通的？"`;
const SLOT_DEFAULT = "default" as const;
const ENTRY_ACTION = "（入场）环顾四周，了解当前处境。";
const STATE_COMMIT_DELAY = 100;

export default function Home() {
  const [sessionId, setSessionId] = useState("");
  const [model, setModel] = useState("deepseek-v4-flash");
  const [state, setState] = useState<GameState | null>(null);
  const [output, setOutput] = useState<StoryOutput>(initialOutput);
  const [outputSource, setOutputSource] = useState<GenerateResponse["source"]>("scripted");
  const [chunks, setChunks] = useState<RetrievedChunk[]>([]);
  const [action, setAction] = useState(INITIAL_ACTION);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");
  const [slots, setSlots] = useState<SaveSlot[]>([]);
  const [selectedSlot, setSelectedSlot] = useState<string>(SLOT_DEFAULT);
  const [selectedSlotId, setSelectedSlotId] = useState<number | "">("");
  const [campaigns, setCampaigns] = useState<CampaignListItem[]>([]);
  const [selectedCampaign, setSelectedCampaign] = useState("");
  const [pendingGenerate, setPendingGenerate] = useState<string | null>(null);

  const statusDeltaHints = useMemo(() => buildStatusDeltaHints(output), [output]);

  // ── Session init ──
  useEffect(() => {
    let mounted = true;

    let campaignOpts: { campaignFilename?: string; arcIndex?: number; sessionIndex?: number } | undefined;
    try {
      const entryJson = sessionStorage.getItem("campaign_entry");
      if (entryJson) {
        const entry = JSON.parse(entryJson);
        sessionStorage.removeItem("campaign_entry");
        campaignOpts = {
          campaignFilename: entry.campaignFilename,
          arcIndex: entry.arcIndex,
          sessionIndex: entry.sessionIndex,
        };
      }
    } catch {
      // Ignore parse errors
    }

    createSession(model, campaignOpts)
      .then(async (session) => {
        if (!mounted) return;
        setSessionId(session.session_id);
        setState(session.state);
        setModel(session.model);
        setSelectedSlot(SLOT_DEFAULT);
        setSelectedSlotId("");
        refreshSlots(session.session_id, SLOT_DEFAULT).catch((err) => console.error("refreshSlots failed:", err));
        if (campaignOpts?.campaignFilename && (campaignOpts.arcIndex || 0) > 0) {
          setPendingGenerate(ENTRY_ACTION);
        }
      })
      .catch((err: Error) => setError(err.message));
    return () => { mounted = false; };
  }, []);

  // ── Load campaigns ──
  useEffect(() => {
    listCampaigns()
      .then((r) => {
        setCampaigns(r.campaigns ?? []);
        try {
          const entryJson = sessionStorage.getItem("campaign_entry");
          if (entryJson) {
            const entry = JSON.parse(entryJson);
            if (entry.campaignFilename) setSelectedCampaign(entry.campaignFilename);
          }
        } catch { /* ignore */ }
      })
      .catch((err) => console.error("listCampaigns failed:", err));
  }, []);

  // ── Load save slots ──
  useEffect(() => {
    if (!sessionId) {
      setSlots([]);
      setSelectedSlot(SLOT_DEFAULT);
      setSelectedSlotId("");
      return;
    }
    listSlots(sessionId).then(r => {
      const nextSlots = (r.slots ?? []).filter((slot) => slot.campaign_id === sessionId);
      setSlots(nextSlots);
      const active = nextSlots.find((slot) => slot.is_active)
        ?? nextSlots.find((slot) => slot.slot_name === selectedSlot);
      if (active) {
        setSelectedSlot(active.slot_name);
        setSelectedSlotId(active.id);
      } else {
        setSelectedSlot(SLOT_DEFAULT);
        setSelectedSlotId("");
      }
    }).catch((err) => console.error("listSlots failed:", err));
  /* selectedSlot intentionally excluded: changing preferred slot name while
     session stays the same should not reload the list — only a new session does */
  }, [sessionId]);

  // ── Auto-generate after session created for mid-campaign entry ──
  useEffect(() => {
    if (!pendingGenerate || !sessionId) return;
    const action = pendingGenerate;
    setPendingGenerate(null);
    handleGenerate(action);
  }, [pendingGenerate, sessionId]);

  async function refreshSlots(currentSessionId = sessionId, preferredSlotName = selectedSlot) {
    if (!currentSessionId) {
      setSlots([]);
      setSelectedSlot(SLOT_DEFAULT);
      setSelectedSlotId("");
      return;
    }
    const updated = await listSlots(currentSessionId);
    const nextSlots = (updated.slots ?? []).filter((slot) => slot.campaign_id === currentSessionId);
    setSlots(nextSlots);
    const active = nextSlots.find((slot) => slot.slot_name === preferredSlotName)
      ?? nextSlots.find((slot) => slot.is_active);
    if (active) {
      setSelectedSlot(active.slot_name);
      setSelectedSlotId(active.id);
    } else {
      setSelectedSlot(SLOT_DEFAULT);
      setSelectedSlotId("");
    }
  }

  async function restoreLastOutput(nextSessionId: string) {
    try {
      const history = await getSessionHistory(nextSessionId);
      const lastAssistant = [...history.messages].reverse().find((message) => message.role === "assistant");
      if (lastAssistant) {
        setOutput(JSON.parse(lastAssistant.content) as StoryOutput);
        setOutputSource("llm");
      } else {
        setOutput(initialOutput);
        setOutputSource("scripted");
      }
    } catch (err) {
      console.error("restoreLastOutput failed:", err);
      setOutput(initialOutput);
      setOutputSource("scripted");
    }
  }

  const handleGenerate = useCallback(async (nextAction = action, overrideSessionId?: string) => {
    const sid = overrideSessionId ?? sessionId;
    if (!sid || !nextAction.trim()) return;
    setIsLoading(true);
    setError("");
    try {
      const response: GenerateResponse = await generateScene({
        sessionId: sid,
        playerAction: nextAction,
        model,
        style: DEFAULT_STORY_STYLE,
        constraints: DEFAULT_CONSTRAINTS,
        slotName: selectedSlot,
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
  }, [sessionId, action, model, selectedSlot]);

  const handleNewSession = useCallback(async () => {
    setIsLoading(true);
    setError("");
    try {
      const campaignOpts = selectedCampaign
        ? { campaignFilename: selectedCampaign, arcIndex: 0, sessionIndex: 0, slotName: SLOT_DEFAULT }
        : undefined;
      const session = await createSession(model, campaignOpts);
      setSessionId(session.session_id);
      setState(session.state);
      setOutput(initialOutput);
      setOutputSource("scripted");
      setChunks([]);
      setAction(INITIAL_ACTION);
      setSelectedSlot(SLOT_DEFAULT);
      setSelectedSlotId("");
      await refreshSlots(session.session_id, SLOT_DEFAULT);
      if (campaignOpts) {
        setPendingGenerate(ENTRY_ACTION);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "创建会话失败");
    } finally {
      setIsLoading(false);
    }
  }, [model, selectedCampaign]);

  return (
    <main className="app-shell">
      <aside className="side-panel">
        <div className="brand-row">
          <div>
            <div className="brand-mark">Jity</div>
            <div className="brand-subtitle">GM scenario console</div>
          </div>
          <div className="brand-actions">
            <Link
              className="icon-button"
              href={sessionId ? `/timeline?session=${sessionId}` : "/timeline"}
              title="发现时间线"
            >
              <MapPin size={17} />
            </Link>
            <Link className="icon-button" href="/curator" title="战役编辑器">
              <PenTool size={17} />
            </Link>
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
          <option value="deepseek-v4-flash">deepseek-v4-flash</option>
          <option value="deepseek-reasoner">deepseek-reasoner</option>
        </select>

        <label className="label" htmlFor="campaign">
          战役
        </label>
        <select
          className="select"
          id="campaign"
          value={selectedCampaign}
          onChange={(e) => {
            const val = e.target.value;
            setSelectedCampaign(val);
            setError("");
            const opts = val
              ? { campaignFilename: val, arcIndex: 0, sessionIndex: 0, slotName: SLOT_DEFAULT }
              : undefined;
            createSession(model, opts)
              .then((s) => {
                setSessionId(s.session_id);
                setState(s.state);
                setOutput(initialOutput);
                setOutputSource("scripted");
                setChunks([]);
                setAction(INITIAL_ACTION);
                setSelectedSlot(SLOT_DEFAULT);
                setSelectedSlotId("");
                refreshSlots(s.session_id, SLOT_DEFAULT).catch((err) => console.error("refreshSlots failed:", err));
                setPendingGenerate(ENTRY_ACTION);
              })
              .catch((err: Error) => setError(err.message));
          }}
        >
          <option value="">自由模式（无预设战役）</option>
          {campaigns.map((c) => (
            <option key={c.filename} value={c.filename}>
              {c.title}（{c.arc_count}弧）
            </option>
          ))}
        </select>

        <label className="label" htmlFor="action">
          玩家行动
        </label>
        {sessionId && (
          <div style={{ marginBottom: 8, display: "flex", alignItems: "center", gap: 8, fontSize: "0.85rem" }}>
            <span>存档:</span>
            <select
              value={selectedSlotId}
              onChange={async (e) => {
                const slotId = Number(e.target.value);
                if (!slotId) return;
                setError("");
                try {
                  const loaded = await loadSlot(slotId);
                  setSelectedSlotId(slotId);
                  setSelectedSlot(loaded.slot.slot_name);
                  setSessionId(loaded.session.session_id);
                  setState(loaded.session.state);
                  setModel(loaded.session.model);
                  setChunks([]);
                  if (loaded.slot.campaign_filename) setSelectedCampaign(loaded.slot.campaign_filename);
                  await restoreLastOutput(loaded.session.session_id);
                  await refreshSlots(loaded.session.session_id, loaded.slot.slot_name);
                } catch (err) {
                  setError(err instanceof Error ? err.message : "加载存档失败");
                }
              }}
              style={{ padding: "2px 6px" }}
            >
              {slots.length === 0 && <option value="">无存档</option>}
              {slots.length > 0 && selectedSlotId === "" && <option value="">选择存档</option>}
              {slots.map(s => (
                <option key={s.id} value={s.id}>
                  {s.slot_name} (A{s.arc_index + 1}S{s.session_index + 1} · T{s.turn_in_session})
                </option>
              ))}
            </select>
            <button onClick={async () => {
              const name = prompt("新存档名称:");
              if (name) {
                try {
                  await createSlot(name, sessionId, selectedSlot);
                  await refreshSlots(sessionId, name);
                } catch (e: unknown) {
                  alert(e instanceof Error ? e.message : String(e));
                }
              }
            }} style={{ padding: "2px 8px" }}>+</button>
          </div>
        )}
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
          {statusDeltaHints.length ? (
            <div className="status-hint-list" aria-label="状态变化提示">
              {statusDeltaHints.map((hint) => (
                <div className={`status-hint ${hint.kind}`} key={hint.label}>
                  <span>{hint.label}</span>
                  <strong>{formatDelta(hint.delta)}</strong>
                  <span>{hint.message}</span>
                </div>
              ))}
            </div>
          ) : null}
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

function buildStatusDeltaHints(output: StoryOutput) {
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

function formatDelta(delta: number) {
  return `${delta > 0 ? "+" : ""}${delta}`;
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
