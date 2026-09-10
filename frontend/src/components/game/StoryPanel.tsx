"use client";

import { Image as ImageIcon, Loader2, Send } from "lucide-react";

import type { GameSession } from "@/components/game/useGameSession";
import { formatDelta, quoteDialogue } from "@/lib/game/format";

export function StoryPanel({ session }: { session: GameSession }) {
  const {
    sessionId,
    state,
    output,
    outputSource,
    statusDeltaHints,
    action,
    setAction,
    handleGenerate,
    isLoading,
    error,
    isBackgroundLoading,
    backgroundError,
    retryBackground,
  } = session;

  return (
    <section className="story-panel">
      <div className="toolbar-row">
        <div className="meta">Session {sessionId ? sessionId.slice(0, 8) : "initializing"}</div>
        <div className="meta">Turn {state?.turn ?? 0}</div>
        {isBackgroundLoading ? (
          <div className="background-status">
            <ImageIcon size={13} />
            场景绘制中
          </div>
        ) : null}
        {backgroundError ? (
          <button
            className="background-button has-error"
            disabled={isBackgroundLoading || !output.scene_prompt}
            onClick={retryBackground}
            title={backgroundError}
            type="button"
          >
            <ImageIcon size={14} />
            <span>重试背景</span>
          </button>
        ) : null}
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

      <div className="player-controls">
        <label className="player-controls-label" htmlFor="action">你的行动</label>
        <div className="player-controls-row">
          <textarea
            id="action"
            value={action}
            onChange={(event) => setAction(event.target.value)}
            onKeyDown={(event) => {
              if ((event.metaKey || event.ctrlKey) && event.key === "Enter" && !isLoading && sessionId) {
                handleGenerate();
              }
            }}
            placeholder="输入玩家行动、当前场景或 GM 限制"
          />
          <button disabled={isLoading || !sessionId} onClick={() => handleGenerate()} type="button">
            {isLoading ? <Loader2 className="spin-icon" size={18} /> : <Send size={18} />}
            <span>{isLoading ? "生成中" : "生成下一幕"}</span>
          </button>
        </div>
        {error ? <div className="error">{error}</div> : null}
        <div className="player-controls-hint">Ctrl / ⌘ + Enter 快速生成</div>
      </div>
    </section>
  );
}
