'use client';

/** The reading surface. It renders exactly the text handed in by the page and
 * distinguishes idle / streaming / accepted / failed without inventing prose.
 * Streaming updates are announced once per phase through a polite live region;
 * the article itself sets aria-busy so assistive tech knows it is still moving. */
import { useId } from 'react';

import type { NarrationPhase, NarrationViewProps } from './types';
import { formatElapsed, splitNarration } from './view-model';
import styles from './world-local.module.css';

const PHASE_LABELS: Record<NarrationPhase, string> = {
  idle: '等待行动',
  streaming: '正在生成',
  accepted: '已接受',
  failed: '生成失败',
};

function liveMessage(phase: NarrationPhase, text: string): string {
  if (phase === 'streaming') return '正在生成本轮正文。';
  if (phase === 'accepted') return `本轮正文已生成，共 ${text.replace(/\s/g, '').length} 字。`;
  if (phase === 'failed') return '本轮正文生成失败。';
  return '';
}

export function NarrationView({
  state,
  title = '本轮正文',
  idleHint = '提交行动后，正文会显示在这里。',
  onRegenerate,
  regenerateDisabledReason,
}: NarrationViewProps) {
  const baseId = useId().replace(/[^a-zA-Z0-9_-]/g, '');
  const headingId = `${baseId}-title`;
  const paragraphs = splitNarration(state.text);
  const previous = splitNarration(state.previousText ?? '');
  const streaming = state.phase === 'streaming';
  const failed = state.phase === 'failed';
  const regenerateDisabled = !onRegenerate || Boolean(regenerateDisabledReason);
  const regenerateReason = regenerateDisabled
    ? (regenerateDisabledReason ?? '当前会话尚未接入正文重生成')
    : null;
  const emptyLabel = state.phase === 'streaming'
    ? '模型正在起笔…'
    : failed
      ? '本次没有可显示的正文。'
      : state.phase === 'accepted'
        ? '本轮正文为空。'
        : idleHint;

  return (
    <section
      aria-labelledby={headingId}
      className={styles.narrationCard}
      data-state={state.phase}
      data-testid="narration-view"
    >
      <header className={styles.cardHeader}>
        <div>
          <h2 className={styles.cardTitle} id={headingId}>{title}</h2>
          {state.pointId ? <p className={styles.cardSubtle}>时间点 {state.pointId}</p> : null}
        </div>
        <div className={styles.statusCluster}>
          <span className={styles.badge} data-tone={state.phase} data-testid="narration-status">
            {PHASE_LABELS[state.phase]}
          </span>
          {streaming || state.phase === 'accepted' ? (
            <span className={styles.statusMeta}>
              {streaming ? '生成中' : '已写入'}
              {state.elapsedMs != null ? ` · ${formatElapsed(state.elapsedMs)}` : ''}
              {` · ${state.text.replace(/\s/g, '').length} 字`}
            </span>
          ) : null}
        </div>
      </header>

      <p aria-live="polite" className={styles.srOnly} data-testid="narration-live" role="status">
        {liveMessage(state.phase, state.text)}
      </p>

      {failed ? (
        <div className={styles.failureBox} data-testid="narration-failure" role="alert">
          <p className={styles.failureTitle}>本次正文未通过</p>
          <p className={styles.failureDetail}>{state.failureReason ?? '生成失败，未提供原因。'}</p>
          <button
            className={styles.button}
            data-testid="narration-regenerate"
            disabled={regenerateDisabled}
            onClick={() => onRegenerate?.()}
            title={regenerateReason ?? undefined}
            type="button"
          >
            重新生成正文
          </button>
          {regenerateReason ? (
            <p className={styles.disabledReason} data-testid="narration-regenerate-reason" role="note">
              {regenerateReason}
            </p>
          ) : null}
        </div>
      ) : null}

      {state.alignmentNote ? (
        <div className={styles.warningBox} data-testid="narration-warning" role="note">
          <strong>事实校验提示</strong>
          <span>{state.alignmentNote}</span>
          <span>正文已保留，可继续阅读；该提示会作为质量缺陷记录。</span>
        </div>
      ) : null}

      <article
        aria-busy={streaming}
        aria-label="正文内容"
        className={styles.narrationText}
        data-testid="narration-content"
        tabIndex={0}
      >
        {paragraphs.length > 0 ? (
          paragraphs.map((paragraph, index) => <p key={index}>{paragraph}</p>)
        ) : (
          <p className={styles.emptyText}>{emptyLabel}</p>
        )}
        {streaming ? <span aria-hidden="true" className={styles.caret} /> : null}
      </article>

      {failed && previous.length > 0 ? (
        <details className={styles.previousBox}>
          <summary>查看上一次已接受的正文</summary>
          <div className={styles.narrationText}>
            {previous.map((paragraph, index) => <p key={index}>{paragraph}</p>)}
          </div>
        </details>
      ) : null}
    </section>
  );
}
