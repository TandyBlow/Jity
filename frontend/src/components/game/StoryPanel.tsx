"use client";

import { Dices, GitBranch, Image as ImageIcon, Loader2, Send } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { MainCheckOverlay, type MainCheckCommit } from "@/components/game/MainCheckOverlay";
import type { GameSession } from "@/components/game/useGameSession";
import { defineCheck, type CheckSpec } from "@/components/dice-demo/dice-rules";
import { formatDelta, quoteDialogue } from "@/lib/game/format";
import type { StoryOptionCheck } from "@/types";

type PendingCheck = {
  action: string;
  check: CheckSpec;
};

function toCheckSpec(metadata: StoryOptionCheck): CheckSpec | null {
  if (metadata.requires_check === false) return null;

  // The payload's own target is ignored: difficulty and the skill value decide
  // the threshold, so a hard check cannot advertise a normal success rate.
  return defineCheck({
    name: metadata.name ?? "行动检定",
    skill: metadata.skill ?? "行动",
    system: metadata.system ?? "通用 d20",
    normalTarget: metadata.normal_target ?? metadata.target ?? 12,
    difficulty: metadata.difficulty ?? "普通",
    stakes: metadata.stakes ?? "成功会推进当前行动，失败会带来相应后果。",
  });
}

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

  function handleOption(option: string, index: number) {
    if (!sessionId || isLoading || session.pendingGenerate) return;

    const metadata = output.option_checks?.[index];
    const check = metadata ? toCheckSpec(metadata) : null;
    if (check) {
      setCheckingAction({ action: option, check });
      return;
    }

    void handleGenerate(option);
  }

  async function commitCheck(result: MainCheckCommit) {
    if (!checkingAction) return;
    const actionWithResult = `${checkingAction.action}\n\n[行动判定] ${checkingAction.check.system} ${checkingAction.check.expression}，骰面 ${result.roll}/20，${result.degree}。`;
    await handleGenerate(actionWithResult);
    setCheckingAction(null);
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

            return (
              <button
                className="option-button"
                disabled={isLoading || !!session.pendingGenerate || !sessionId}
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
              </button>
            );
          })}
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
          <button disabled={isLoading || !!session.pendingGenerate || !sessionId} onClick={() => handleGenerate()} type="button">
            {isLoading ? <Loader2 className="spin-icon" size={18} /> : <Send size={18} />}
            <span>{isLoading ? "生成中" : "生成下一幕"}</span>
          </button>
        </div>
        {error ? <div className="error">{error}</div> : null}
        <div className="player-controls-hint">Ctrl / ⌘ + Enter 快速生成</div>
      </div>
      {checkingAction ? (
        <MainCheckOverlay
          action={checkingAction.action}
          check={checkingAction.check}
          busy={isLoading}
          onCancel={() => setCheckingAction(null)}
          onCommit={commitCheck}
        />
      ) : null}
    </section>
  );
}
