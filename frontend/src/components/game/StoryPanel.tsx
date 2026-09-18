"use client";

import { Dices, GitBranch, Image as ImageIcon, Loader2, Send } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { MainCheckOverlay, type MainCheckCommit } from "@/components/game/MainCheckOverlay";
import type { GameSession } from "@/components/game/useGameSession";
import type { CheckSpec, Outcome } from "@/lib/dice/rules";
import { formatActionWithCheckResult, outcomeTone, toCheckSpec } from "@/lib/game/checks";
import { formatDelta, quoteDialogue } from "@/lib/game/format";

type PendingCheck = {
  action: string;
  index: number;
  check: CheckSpec;
};

type PendingSweep = {
  index: number;
  outcome: Outcome;
  action: string;
};

function narrationParagraphs(narration: string): string[] {
  const explicitParagraphs = narration
    .split(/\n+/)
    .map((paragraph) => paragraph.trim())
    .filter(Boolean);

  if (explicitParagraphs.length > 1 || narration.length < 180) return explicitParagraphs;

  const sentences = narration.match(/[^。！？!?…]+(?:[。！？!?…]+|$)/g) ?? [narration];
  const paragraphs: string[] = [];
  let paragraph = "";

  for (const sentence of sentences) {
    paragraph += sentence.trim();
    if (paragraph.length >= 120) {
      paragraphs.push(paragraph);
      paragraph = "";
    }
  }
  if (paragraph) paragraphs.push(paragraph);

  return paragraphs;
}

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
  const [checkingAction, setCheckingAction] = useState<PendingCheck | null>(null);
  const [sweep, setSweep] = useState<PendingSweep | null>(null);

  function handleOption(option: string, index: number) {
    if (!sessionId || isLoading || session.pendingGenerate || sweep) return;

    const metadata = output.option_checks?.[index];
    const check = metadata ? toCheckSpec(metadata) : null;
    if (check) {
      setCheckingAction({ action: option, index, check });
      return;
    }

    void handleGenerate(option);
  }

  function commitCheck(result: MainCheckCommit) {
    if (!checkingAction) return;
    const { action, check, index } = checkingAction;
    setCheckingAction(null);
    setSweep({
      index,
      outcome: result.outcome,
      action: formatActionWithCheckResult(action, check, result),
    });
  }

  // The fill stays on the chosen option until the next scene replaces the list.
  useEffect(() => {
    setSweep(null);
  }, [output]);

  // An ended campaign must not leave the dice overlay on top of the ending card.
  useEffect(() => {
    if (output.game_over) setCheckingAction(null);
  }, [output.game_over]);

  useEffect(() => {
    if (error) setSweep(null);
  }, [error]);

  /** The sweep's own animation decides when the next scene is generated. */
  function completeSweep(action: string) {
    void handleGenerate(action);
  }

  return (
    <section className="story-panel">
      <div className="toolbar-row">
        <div className="meta">Session {sessionId ? sessionId.slice(0, 8) : "initializing"}</div>
        <div className="meta">Turn {state?.turn ?? 0}</div>
        {sessionId && session.activeTurnId ? (
          <Link className="story-rewind-link" href={`/timeline?session=${sessionId}&back=1`}>
            <GitBranch size={13} />
            回溯上一步
          </Link>
        ) : null}
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
        {session.autoPlay.enabled ? (
          <div className={`autoplay-banner ${session.autoPlay.status}`}>
            <div>
              <strong>自动跑剧情 · {session.autoPlay.currentTurn}/{session.autoPlay.targetTurns}</strong>
              <span>当前目标：{session.autoPlay.goals.join("；") || "跟随主线推进"}</span>
              {session.autoPlay.selectedAction ? <span>下一步：{session.autoPlay.selectedAction}</span> : null}
              {session.autoPlay.selectionReason ? <small>{session.autoPlay.selectionReason}</small> : null}
            </div>
            {session.autoPlay.status !== "complete" ? (
              <button onClick={() => session.autoPlay.setPaused(!session.autoPlay.paused)} type="button">
                {session.autoPlay.paused ? "继续" : "暂停"}
              </button>
            ) : <span className="autoplay-complete">已完成</span>}
          </div>
        ) : null}
        <div className="narration">
          {narrationParagraphs(output.narration).map((paragraph, index) => (
            <p key={`${index}-${paragraph.slice(0, 20)}`}>{paragraph}</p>
          ))}
        </div>
        {output.game_over ? (
          <div className="ending-card" role="status">
            <strong>战役结束</strong>
            <span>{output.game_over_reason}</span>
          </div>
        ) : null}
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
          {output.options.map((option, index) => {
            const metadata = output.option_checks?.[index];
            const check = metadata ? toCheckSpec(metadata) : null;
            const sweeping = sweep?.index === index ? sweep : null;

            return (
              <button
                className="option-button"
                disabled={output.game_over || isLoading || !!session.pendingGenerate || !sessionId}
                key={`${option}-${index}`}
                onClick={() => handleOption(option, index)}
                type="button"
              >
                <span className="option-button-label">{option}</span>
                {check ? (
                  <span className="option-check-badge">
                    <Dices size={14} />需判定
                  </span>
                ) : null}
                {sweeping ? (
                  <span
                    className={`option-sweep ${outcomeTone(sweeping.outcome)}`}
                    aria-hidden="true"
                    onAnimationEnd={() => completeSweep(sweeping.action)}
                  />
                ) : null}
              </button>
            );
          })}
        </div>
      </article>

      <div className={`player-controls${output.game_over ? " is-ended" : ""}`}>
        <label className="player-controls-label" htmlFor="action">你的行动</label>
        <div className="player-controls-row">
          <textarea
            id="action"
            disabled={output.game_over}
            value={action}
            onChange={(event) => setAction(event.target.value)}
            onKeyDown={(event) => {
              if ((event.metaKey || event.ctrlKey) && event.key === "Enter" && !isLoading && sessionId) {
                handleGenerate();
              }
            }}
            placeholder={output.game_over ? "该战役已经结束" : "输入玩家行动、当前场景或 GM 限制"}
          />
          <button disabled={output.game_over || isLoading || !!session.pendingGenerate || !sessionId} onClick={() => handleGenerate()} type="button">
            {isLoading ? <Loader2 className="spin-icon" size={18} /> : <Send size={18} />}
            <span>{output.game_over ? "战役已结束" : isLoading ? "生成中" : "生成下一幕"}</span>
          </button>
        </div>
        {error ? <div className="error">{error}</div> : null}
        <div className="player-controls-hint">Ctrl / ⌘ + Enter 快速生成</div>
      </div>
      {checkingAction ? (
        <MainCheckOverlay
          action={checkingAction.action}
          check={checkingAction.check}
          onCancel={() => setCheckingAction(null)}
          onCommit={commitCheck}
        />
      ) : null}
    </section>
  );
}
