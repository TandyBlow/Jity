'use client';

/** Player actions. The textarea only edits a draft; every button forwards to a
 * callback supplied by the page. When a callback is absent the button stays
 * disabled and a visible reason says what is not wired yet. */
import { useId } from 'react';

import type { GameControlsProps } from './types';
import { controlAvailability, controlPhaseLabel, isSubmitShortcut } from './view-model';
import styles from './world-local.module.css';

export function GameControls({
  value,
  onChange,
  onSubmit,
  phase = 'ready',
  busy = false,
  paused = false,
  submitDisabledReason = null,
  onPause,
  onResume,
  onCancel,
  pauseDisabledReason = null,
  resumeDisabledReason = null,
  cancelDisabledReason = null,
  placeholder = '输入你要做的事，例如：我沿着车道向西回廊快走，贴着墙，注意听枪声。',
  hint = '模型只读取已结算的状态',
  disabled = false,
  disabledReason = null,
}: GameControlsProps) {
  const baseId = useId().replace(/[^a-zA-Z0-9_-]/g, '');
  const inputId = `${baseId}-action`;
  const availability = controlAvailability({
    value,
    phase,
    busy,
    paused,
    disabled,
    disabledReason,
    submitDisabledReason,
    pauseDisabledReason,
    resumeDisabledReason,
    cancelDisabledReason,
    hasPause: Boolean(onPause),
    hasResume: Boolean(onResume),
    hasCancel: Boolean(onCancel),
  });

  const submit = () => {
    const text = value.trim();
    if (!availability.canSubmit) return;
    onSubmit(text);
  };

  // Wiring defects and state reasons worth spelling out. Empty input and
  // "not running yet" are conveyed by the disabled control itself, so the note
  // list stays focused on reasons the player cannot infer from context.
  const notes: { label: string; reason: string }[] = [];
  const pushNote = (label: string, reason: string | null) => {
    if (!reason) return;
    if (notes.some((note) => note.label === label && note.reason === reason)) return;
    notes.push({ label, reason });
  };
  if (disabled) pushNote('行动', disabledReason ?? availability.submitReason);
  if (submitDisabledReason) pushNote('行动', submitDisabledReason);
  if (availability.submitReason && (busy || paused || phase === 'loading' || phase === 'thinking' || phase === 'streaming')) {
    pushNote('行动', availability.submitReason);
  }
  if (!onPause && !paused) pushNote('暂停', availability.pauseReason);
  if (paused && !onResume) pushNote('继续', availability.resumeReason);
  if (pauseDisabledReason) pushNote('暂停', pauseDisabledReason);
  if (resumeDisabledReason) pushNote('继续', resumeDisabledReason);
  if (!onCancel) pushNote('取消本轮', availability.cancelReason);
  if (cancelDisabledReason) pushNote('取消本轮', cancelDisabledReason);

  return (
    <form
      aria-label="玩家操作"
      className={styles.controls}
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
    >
      <div className={styles.controlsHeader}>
        <h2 className={styles.cardTitle}>行动</h2>
        <span className={styles.badge} data-tone={paused ? 'paused' : phase}>
          {controlPhaseLabel(phase, paused)}
        </span>
      </div>

      <label className={styles.srOnly} htmlFor={inputId}>输入你的行动</label>
      <textarea
        aria-keyshortcuts="Control+Enter Meta+Enter"
        className={styles.textarea}
        data-testid="action-input"
        disabled={!availability.canEdit}
        id={inputId}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={(event) => {
          if (!isSubmitShortcut(event)) return;
          if (!availability.canSubmit) return;
          event.preventDefault();
          submit();
        }}
        placeholder={placeholder}
        rows={3}
        value={value}
      />

      <div className={styles.controlRow}>
        <span className={styles.hint}>Ctrl/⌘ + Enter 提交 · {hint}</span>
        <div className={styles.buttonGroup}>
          {paused ? (
            <button
              className={styles.button}
              data-testid="resume-action"
              disabled={!availability.canResume}
              onClick={() => onResume?.()}
              title={availability.resumeReason ?? undefined}
              type="button"
            >
              继续
            </button>
          ) : (
            <button
              className={styles.button}
              data-testid="pause-action"
              disabled={!availability.canPause}
              onClick={() => onPause?.()}
              title={availability.pauseReason ?? undefined}
              type="button"
            >
              暂停
            </button>
          )}
          <button
            className={styles.button}
            data-testid="cancel-action"
            disabled={!availability.canCancel}
            onClick={() => onCancel?.()}
            title={availability.cancelReason ?? undefined}
            type="button"
          >
            取消本轮
          </button>
          <button
            className={`${styles.button} ${styles.primaryButton}`}
            data-testid="submit-action"
            disabled={!availability.canSubmit}
            title={availability.submitReason ?? undefined}
            type="submit"
          >
            {busy ? '结算中…' : '提交行动'}
          </button>
        </div>
      </div>

      {notes.length > 0 ? (
        <ul aria-label="不可用操作的原因" aria-live="polite" className={styles.controlNotes} data-testid="controls-notes">
          {notes.map((note) => (
            <li key={`${note.label}-${note.reason}`}>
              <strong>{note.label}</strong>：{note.reason}
            </li>
          ))}
        </ul>
      ) : null}
    </form>
  );
}
