"use client";

import { BookOpen, Loader2, RefreshCw, Send, Sparkles } from "lucide-react";
import { useEffect, useState } from "react";

import { createSession, generateScene } from "@/lib/api";
import type { GameState, GenerateResponse, RetrievedChunk, StoryOutput } from "@/types";

const initialOutput: StoryOutput = {
  narration: "报到大厅的雨声贴着彩窗滑落。你站在卡塞尔学院的入口，临时通行卡还带着火漆的温度，下一句话就会决定这场入学调查从哪里裂开。",
  dialogue: [
    { speaker: "诺诺", text: "说吧，新生。你打算先相信规则，还是先相信直觉？" },
    { speaker: "芬格尔", text: "我建议相信我，虽然这个建议本身风险很高。" },
  ],
  scene_prompt: "rainy gothic academy registration hall, cinematic fantasy investigation",
  sanity_delta: 0,
  health_delta: 0,
  options: ["询问学院给出的三个预备任务", "检查临时通行卡上的异常标记", "先观察大厅里执行部学生的动向"],
  game_over: false,
  game_over_reason: "",
  current_location: "卡塞尔学院新生报到处",
};

export default function Home() {
  const [sessionId, setSessionId] = useState("");
  const [model, setModel] = useState("deepseek-chat");
  const [state, setState] = useState<GameState | null>(null);
  const [output, setOutput] = useState<StoryOutput>(initialOutput);
  const [chunks, setChunks] = useState<RetrievedChunk[]>([]);
  const [action, setAction] = useState("玩家决定先检查临时通行卡，确认它是否记录了异常权限。");
  const [narrativeProfile, setNarrativeProfile] = useState("longzu_youth");
  const [style, setStyle] = useState("黑暗学院奇幻，带一点黑色幽默，强调 NPC 反应。");
  const [constraints, setConstraints] = useState("关键 NPC 不能突然死亡；不要跳出当前入学调查。");
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
        narrativeProfile,
        style,
        constraints,
      });
      setOutput(response.output);
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
      setChunks([]);
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
          <button className="icon-button" onClick={handleNewSession} title="新建会话" type="button">
            <RefreshCw size={17} />
          </button>
        </div>

        <label className="label" htmlFor="model">
          模型
        </label>
        <select className="select" id="model" value={model} onChange={(event) => setModel(event.target.value)}>
          <option value="deepseek-chat">deepseek-chat</option>
          <option value="deepseek-reasoner">deepseek-reasoner</option>
        </select>

        <label className="label" htmlFor="narrative-profile">
          叙事模式
        </label>
        <select
          className="select"
          id="narrative-profile"
          value={narrativeProfile}
          onChange={(event) => setNarrativeProfile(event.target.value)}
        >
          <option value="longzu_youth">龙族式少年感</option>
          <option value="default">默认 RPG</option>
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

        <label className="label" htmlFor="style">
          故事风格
        </label>
        <textarea
          className="textarea small-textarea"
          id="style"
          value={style}
          onChange={(event) => setStyle(event.target.value)}
        />

        <label className="label" htmlFor="constraints">
          特殊限制
        </label>
        <textarea
          className="textarea small-textarea"
          id="constraints"
          value={constraints}
          onChange={(event) => setConstraints(event.target.value)}
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
        </div>

        <article className="scene-output">
          <div className="narration">{output.narration}</div>
          <div className="dialogue-list">
            {output.dialogue.map((line, index) => (
              <div className="dialogue-line" key={`${line.speaker}-${index}`}>
                <span className="speaker">{line.speaker}：</span>
                {line.text}
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

        <MemorySection title="地点" items={[state?.current_location ?? output.current_location]} />
        <MemorySection title="近期事件" items={state?.recent_events ?? []} />
        <MemoryObjects title="NPC" items={state?.npcs ?? []} />
        <MemoryObjects title="任务" items={state?.quests ?? []} />

        <div className="section-title">
          <span>RAG Hits</span>
          <BookOpen size={16} />
        </div>
        <div className="chunk-list">
          {chunks.length ? (
            chunks.map((chunk) => (
              <div className="chunk-item" key={chunk.id}>
                <div className="chunk-title">{chunk.title}</div>
                <div className="chunk-type">
                  {chunk.source_type} · score {chunk.score}
                </div>
                <p>{chunk.content}</p>
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

function MemoryObjects({ title, items }: { title: string; items: Array<Record<string, string>> }) {
  return (
    <>
      <div className="section-title">{title}</div>
      <div className="memory-list">
        {items.length ? (
          items.map((item, index) => (
            <div className="memory-item" key={`${item.name}-${index}`}>
              <strong>{item.name ?? "未命名"}</strong>
              <div className="meta">{item.status ?? item.disposition ?? item.description ?? item.notes ?? "已记录"}</div>
            </div>
          ))
        ) : (
          <div className="memory-item">暂无记录</div>
        )}
      </div>
    </>
  );
}
