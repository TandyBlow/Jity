"use client";

import type { GameSession } from "@/components/game/useGameSession";
import { formatDelta, quoteDialogue } from "@/lib/game/format";

export function StoryPanel({ session }: { session: GameSession }) {
  const { sessionId, state, output, outputSource, statusDeltaHints, handleGenerate } = session;

  return (
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
  );
}
