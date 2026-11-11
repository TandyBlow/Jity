"use client";

import { Dices, GitBranch, Image as ImageIcon, Loader2, Send, Sparkles } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState, type CSSProperties } from "react";

import { MainCheckOverlay, type MainCheckCommit } from "@/components/game/MainCheckOverlay";
import { ActionGateTrack } from "@/components/game/ActionGateTrack";
import { useActionGate } from "@/components/game/useActionGate";
import type { GameSession } from "@/components/game/useGameSession";
import { fetchCampaignProgress, hasCampaignTurnBudget } from "@/lib/api";
import type { CampaignProgressSummary } from "@/types";
import type { CheckSpec, Outcome } from "@/lib/dice/rules";
import { selectGateCast } from "@/lib/game/actionGate";
import { outcomeTone, toActionCheckSubmission, toCheckSpec } from "@/lib/game/checks";
import { formatDelta, formatEndingTitle, quoteDialogue } from "@/lib/game/format";
import { useTypewriter } from "@/lib/game/useTypewriter";

/** Mirrors the narrator prompt budget: ~200 words ≈ 200–300 Chinese characters. */
const NARRATION_CHAR_BUDGET = 300;

type PendingCheck = {
  action: string;
  index: number | null;
  check: CheckSpec;
};

type PendingSweep = {
  index: number;
  outcome: Outcome;
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

export function StoryPanel({
  session,
  onOpenMemory,
}: {
  session: GameSession;
  onOpenMemory: () => void;
}) {
  const {
    sessionId,
    activeTurnId,
    restoreVersion,
    selectedSlot,
    state,
    output,
    outputSource,
    statusDeltaHints,
    action,
    setAction,
    handleGenerate,
    handlePrepareCheck,
    isLoading,
    error,
    isBackgroundLoading,
    backgroundError,
    retryBackground,
  } = session;
  const [checkingAction, setCheckingAction] = useState<PendingCheck | null>(null);
  const [sweep, setSweep] = useState<PendingSweep | null>(null);
  const preparingAction = useRef(false);
  const checkTrigger = useRef<HTMLElement | null>(null);
  const [isPreparingCheck, setIsPreparingCheck] = useState(false);
  const sceneRef = useRef<HTMLElement>(null);
  const [hasMoreBelow, setHasMoreBelow] = useState(false);
  const hasAction = action.trim().length > 0;
  const busy = isLoading || isPreparingCheck || !!session.pendingGenerate;

  // Turn order: the previous scene stays on screen while the request is in
  // flight, the freshly generated text is held back, the gate walks the cast,
  // and only then does the typewriter reveal the new narration.
  const gate = useActionGate();
  const gateBlocking = gate.blocking;

  const [committedNarration, setCommittedNarration] = useState(output.narration);
  const commitNarration = useCallback((next: string) => {
    setCommittedNarration((previous) => (previous === next ? previous : next));
  }, []);

  const typewriter = useTypewriter(committedNarration);
  const narrationText = typewriter.text;
  const narrationReady = !gateBlocking && typewriter.done;
  const isTyping = !gateBlocking && typewriter.isTyping;

  const stateRef = useRef(state);
  stateRef.current = state;
  const gateCastRef = useRef<string[]>([]);
  const gatePendingRef = useRef(false);
  const lastOutputRef = useRef(output);
  // The text the gate is holding back. Kept in a ref so a "done" phase left
  // over from a previous turn can never commit the turn that is still running.
  const heldNarrationRef = useRef<string | null>(null);

  // A new output is either a finished user turn (hold it, run the track) or a
  // restore/initial load (commit straight away, no track).
  useEffect(() => {
    if (lastOutputRef.current === output) return;
    lastOutputRef.current = output;

    if (!gatePendingRef.current) {
      commitNarration(output.narration);
      return;
    }
    gatePendingRef.current = false;

    const animated = gate.begin(gateCastRef.current);
    if (animated) {
      // The check runs on a cleared stage: no story text while the chips walk.
      heldNarrationRef.current = output.narration;
      commitNarration("");
      // Silent correction only: trim bodies the new turn no longer has. Chips
      // that already walked stay, and nothing is inserted mid-animation.
      gate.noteOutput(selectGateCast(stateRef.current?.npcs, output));
    } else {
      heldNarrationRef.current = null;
      commitNarration(output.narration);
    }
  }, [output, gate.begin, gate.noteOutput, commitNarration]);

  // The track finished → release the held text and retire the track at once,
  // so the chips are never parked on the left while the scene types.
  useEffect(() => {
    if (gate.phase !== "done") return;
    const held = heldNarrationRef.current;
    heldNarrationRef.current = null;
    if (held !== null) commitNarration(held);
    gate.finishNarration();
  }, [gate.phase, gate.finishNarration, commitNarration]);

  // A failed request must never leave the hold active.
  useEffect(() => {
    if (!error) return;
    gatePendingRef.current = false;
    heldNarrationRef.current = null;
    gate.reset();
  }, [error, gate.reset]);

  // Loading another save/turn is not a new check: end the track immediately
  // instead of making the restored scene wait for a stale animation.
  useEffect(() => {
    gatePendingRef.current = false;
    gate.reset();
  }, [selectedSlot, gate.reset]);

  // The scene clips silently: scrollbars are hidden app-wide and a single turn
  // can run past the viewport, so the options at the end are off-screen with
  // nothing saying so. While typing, "at the bottom" also means "keep following
  // the cursor"; scrolling up by hand stops the follow until the user returns.
  const followSceneRef = useRef(true);
  const didTypeRef = useRef(false);
  const updateOverflow = useCallback(() => {
    const scene = sceneRef.current;
    if (!scene) return;
    followSceneRef.current = scene.scrollTop + scene.clientHeight >= scene.scrollHeight - 40;
    setHasMoreBelow(scene.scrollTop + scene.clientHeight < scene.scrollHeight - 8);
  }, []);

  // A new turn replaces the whole scene. Without this the scroll position
  // carries over, so the next turn opens part-way through its own narration.
  useEffect(() => {
    sceneRef.current?.scrollTo({ top: 0 });
    followSceneRef.current = true;
    didTypeRef.current = false;
    // Measure once the new scene has been laid out, not before it is painted.
    const frame = requestAnimationFrame(updateOverflow);
    return () => cancelAnimationFrame(frame);
  }, [output, updateOverflow]);

  // Follow the growing text only while it is actually being typed, and only
  // while the reader has not scrolled away from the bottom.
  useEffect(() => {
    if (isTyping) didTypeRef.current = true;
  }, [isTyping]);

  useEffect(() => {
    const scene = sceneRef.current;
    if (!scene || !isTyping || !followSceneRef.current) return;
    scene.scrollTop = scene.scrollHeight;
  }, [narrationText, isTyping]);

  // Once the text is complete, reveal the options and dialogue, then keep them
  // in view. Skipped when the text was never animated (reduced motion, tests),
  // so the old "open at the top" behaviour is preserved there.
  useEffect(() => {
    const scene = sceneRef.current;
    if (!scene || !narrationReady || !didTypeRef.current) return;
    didTypeRef.current = false;
    if (followSceneRef.current) {
      scene.scrollTop = scene.scrollHeight;
      updateOverflow();
    }
  }, [narrationReady, updateOverflow]);

  // Server-side budget safety net. The prompt already asks for 200 words; when
  // a turn still overruns we record it and keep the whole text — cutting a
  // sentence in half would be worse than a slightly long scene.
  useEffect(() => {
    const chars = Array.from(output.narration).length;
    if (chars > NARRATION_CHAR_BUDGET) {
      console.warn(
        `[jity] 旁白 ${chars} 字，超过 ${NARRATION_CHAR_BUDGET} 字预算；仅记录告警，不截断。`,
      );
    }
  }, [output.narration]);

  async function prepareAction(nextAction: string, optionIndex?: number) {
    if (!sessionId || busy || gateBlocking || isTyping || checkingAction || preparingAction.current || !nextAction.trim() || output.game_over) return;
    checkTrigger.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    preparingAction.current = true;
    setIsPreparingCheck(true);
    try {
      const preview = await handlePrepareCheck(nextAction, optionIndex);
      if (!preview) return;
      const check = preview.check ? toCheckSpec(preview.check) : null;
      if (check) {
        setCheckingAction({ action: nextAction, index: preview.option_index, check });
      } else {
        gateCastRef.current = selectGateCast(stateRef.current?.npcs, output);
        gatePendingRef.current = true;
        await handleGenerate(nextAction, undefined, undefined, preview.option_index ?? undefined);
      }
    } finally {
      preparingAction.current = false;
      setIsPreparingCheck(false);
    }
  }

  function cancelCheck() {
    setCheckingAction(null);
    // The preflight temporarily disables its trigger. Restore focus after it
    // is enabled again, including when the trigger was the custom-action box.
    requestAnimationFrame(() => checkTrigger.current?.focus());
  }

  async function commitCheck(result: MainCheckCommit) {
    if (!checkingAction) return;
    const { action, index } = checkingAction;
    if (index !== null) setSweep({ index, outcome: result.outcome });
    gateCastRef.current = selectGateCast(stateRef.current?.npcs, output);
    gatePendingRef.current = true;
    await handleGenerate(action, undefined, toActionCheckSubmission(result.roll, index), index ?? undefined);
  }

  // Keep the rolled result while a failed request is retried. Replacing the
  // scene (including a stale-turn refresh or save load) invalidates the check.
  useEffect(() => {
    setSweep(null);
    setCheckingAction(null);
  }, [output, sessionId, activeTurnId]);

  // An ended campaign must not leave the dice overlay on top of the ending card.
  useEffect(() => {
    if (output.game_over) setCheckingAction(null);
  }, [output.game_over]);

  useEffect(() => {
    if (error) setSweep(null);
  }, [error]);

  // Whole-campaign strip: live values ride each generate response; a page
  // (re)load or save restore fetches the persisted counter once instead.
  const [loadedProgress, setLoadedProgress] = useState<{
    sessionId: string;
    activeTurnId: number | null;
    slotName: string;
    restoreVersion: number;
    progress: CampaignProgressSummary | null;
  } | null>(null);
  useEffect(() => {
    let cancelled = false;
    if (!sessionId) {
      setLoadedProgress(null);
      return;
    }
    fetchCampaignProgress(sessionId)
      .then((progress) => {
        if (!cancelled) setLoadedProgress({ sessionId, activeTurnId, slotName: selectedSlot, restoreVersion, progress });
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [sessionId, activeTurnId, selectedSlot, restoreVersion]);
  const cachedProgress = loadedProgress?.sessionId === sessionId
    && loadedProgress.activeTurnId === activeTurnId
    && loadedProgress.slotName === selectedSlot
    && loadedProgress.restoreVersion === restoreVersion
      ? loadedProgress.progress
      : null;
  const campaignProgress =
    hasCampaignTurnBudget(session.campaignProgress)
      ? session.campaignProgress
      : hasCampaignTurnBudget(cachedProgress)
        ? cachedProgress
        : null;

  return (
    <section className="story-panel">
      <div className="toolbar-row">
        <div className="meta">Session {sessionId ? sessionId.slice(0, 8) : "initializing"}</div>
        <div className="meta">
          {campaignProgress
            ? `第 ${campaignProgress.turns_total} / ${campaignProgress.max_turns_per_campaign} 回合`
            : `Turn ${state?.turn ?? 0}`}
        </div>
        {campaignProgress ? (
          <div className="meta campaign-strip">
            {campaignProgress.arc_name ? (
              <span>
                {campaignProgress.arc_name}
                {campaignProgress.session_name ? `·${campaignProgress.session_name}` : ""}
              </span>
            ) : null}
            {campaignProgress.current_goal ? <span>目标：{campaignProgress.current_goal}</span> : null}
          </div>
        ) : null}
        {sessionId && session.activeTurnId ? (
          <Link className="story-rewind-link" href={`/timeline?session=${sessionId}&back=1`}>
            <GitBranch size={13} />
            回溯上一步
          </Link>
        ) : null}
        {/* Only visible below 1100px, where the docked memory column is hidden. */}
        <button className="memory-drawer-trigger" onClick={onOpenMemory} type="button">
          <Sparkles size={13} />
          记忆面板
        </button>
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

      <ActionGateTrack
        activeIndex={gate.activeIndex}
        chips={gate.chips}
        phase={gate.phase}
        revealedCount={gate.revealedCount}
      />

      <article
        className="scene-output"
        data-more={hasMoreBelow ? "true" : "false"}
        onScroll={updateOverflow}
        ref={sceneRef}
      >
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
        <div
          aria-busy={isTyping || undefined}
          className={`narration${isTyping ? " is-typing" : ""}`}
        >
          {narrationText ? (
            narrationParagraphs(narrationText).map((paragraph, index) => (
              // Stable key: the paragraph list is append-only while typing, so
              // a text-derived key would remount (and flicker) every frame.
              <p key={index}>{paragraph}</p>
            ))
          ) : (
            // Keeps one line reserved before the first character lands, so the
            // scene does not collapse the moment the turn starts.
            <p className="narration-pending" aria-hidden="true">&nbsp;</p>
          )}
        </div>
        {narrationReady && output.game_over ? (
          <div className="ending-card" role="status">
            <strong>终章</strong>
            <span>{formatEndingTitle(output.game_over_reason)}</span>
          </div>
        ) : null}
        {narrationReady ? (
          <div className="dialogue-list">
            {output.dialogue.map((line, index) => (
              <div
                className="dialogue-line"
                key={`${line.speaker}-${index}`}
                style={{ "--i": index } as CSSProperties}
              >
                <span className="speaker">{line.speaker}：</span>
                <span className="dialogue-text">{quoteDialogue(line.text)}</span>
              </div>
            ))}
          </div>
        ) : null}
        {narrationReady && statusDeltaHints.length ? (
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
        {narrationReady ? (
          <div className="option-list">
            {output.options.map((option, index) => {
              const metadata = output.option_checks?.[index];
              const check = metadata ? toCheckSpec(metadata) : null;
              const sweeping = sweep?.index === index ? sweep : null;

              return (
                <button
                  className="option-button"
                  disabled={output.game_over || busy || !!checkingAction || !sessionId}
                  key={`${option}-${index}`}
                  onClick={() => void prepareAction(option, index)}
                  style={{ "--i": index } as CSSProperties}
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
                    />
                  ) : null}
                </button>
              );
            })}
          </div>
        ) : null}
      </article>

      <div className={`player-controls${output.game_over ? " is-ended" : ""}`}>
        <label className="player-controls-label" htmlFor="action">你的行动</label>
        <div className="player-controls-row">
          <textarea
            id="action"
            disabled={output.game_over || busy || isTyping || gateBlocking || !!checkingAction}
            value={action}
            onChange={(event) => setAction(event.target.value)}
            onKeyDown={(event) => {
              if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
                event.preventDefault();
                void prepareAction(action);
              }
            }}
            placeholder={output.game_over ? "该战役已经结束" : "输入玩家行动、当前场景或 GM 限制"}
          />
          <button disabled={output.game_over || busy || isTyping || gateBlocking || !!checkingAction || !sessionId || !hasAction} onClick={() => void prepareAction(action)} type="button">
            {busy ? <Loader2 className="spin-icon" size={18} /> : <Send size={18} />}
            <span>{output.game_over ? "战役已结束" : isTyping ? "叙述中" : isPreparingCheck ? "检查行动中" : isLoading ? "生成中" : "生成下一幕"}</span>
          </button>
        </div>
        {error ? <div className="error">{error}</div> : null}
        <div className="player-controls-hint">
          {gateBlocking ? "行动检查中，请稍候" : isTyping ? "叙述中，完成后可继续行动" : hasAction ? "Ctrl / ⌘ + Enter 快速生成" : "先输入行动，或直接点上方选项"}
        </div>
      </div>
      {checkingAction ? (
        <MainCheckOverlay
          action={checkingAction.action}
          check={checkingAction.check}
          busy={isLoading}
          submitError={error}
          onCancel={cancelCheck}
          onCommit={commitCheck}
        />
      ) : null}
    </section>
  );
}
