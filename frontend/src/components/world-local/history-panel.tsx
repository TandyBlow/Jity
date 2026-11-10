'use client';

/** Committed points only. Selecting an entry asks the page to show that point;
 * a missing or failed narration offers a regeneration request. The panel never
 * fetches a point, reads a cache or writes a snapshot itself. */
import { useId } from 'react';

import type { HistoryPanelProps } from './types';
import { historyKindLabel, narrationStatusLabel } from './view-model';
import styles from './world-local.module.css';

function statusTone(status: HistoryPanelProps['entries'][number]['status']): string {
  if (status === 'ready') return 'ready';
  if (status === 'pending') return 'pending';
  if (status === 'failed') return 'failed';
  if (status === 'missing') return 'missing';
  return 'unknown';
}

export function HistoryPanel({
  entries,
  headPointId,
  selectedPointId,
  onSelect,
  onRegenerate,
  regenerateDisabledReason,
  loading = false,
  emptyHint = '本局还没有已提交的时间点。',
}: HistoryPanelProps) {
  const baseId = useId().replace(/[^a-zA-Z0-9_-]/g, '');
  const headingId = `${baseId}-title`;
  const ordered = [...entries].sort((left, right) => right.sequence - left.sequence);
  const needsRegeneration = ordered.filter((entry) => entry.status === 'missing' || entry.status === 'failed');
  const regenerateDisabled = !onRegenerate || Boolean(regenerateDisabledReason);
  const regenerateReason = regenerateDisabled
    ? (regenerateDisabledReason ?? (!onRegenerate ? '当前会话尚未接入正文重生成' : null))
    : null;

  return (
    <section aria-labelledby={headingId} className={styles.panel} data-testid="history-panel">
      <header className={styles.cardHeader}>
        <h2 className={styles.cardTitle} id={headingId}>历史时间点</h2>
        <span className={styles.count}>{ordered.length} 个</span>
      </header>
      <p className={styles.panelHint}>只列出已经提交的时间点。正文缺失或失败时，可以请求重新生成。</p>

      {loading ? (
        <p className={styles.panelHint} role="status">正在读取已提交时间点…</p>
      ) : ordered.length === 0 ? (
        <p className={styles.emptyText}>{emptyHint}</p>
      ) : (
        <ol className={styles.historyList}>
          {ordered.map((entry) => {
            const isHead = entry.pointId === headPointId;
            const isSelected = entry.pointId === selectedPointId;
            const tone = statusTone(entry.status);
            const selectable = Boolean(onSelect);
            return (
              <li className={styles.historyItem} data-status={tone} key={entry.pointId}>
                <button
                  aria-current={isHead ? 'true' : undefined}
                  aria-disabled={selectable ? undefined : 'true'}
                  aria-pressed={isSelected}
                  className={styles.historyButton}
                  data-testid={`history-${entry.pointId}`}
                  onClick={selectable ? () => onSelect?.(entry.pointId) : undefined}
                  type="button"
                >
                  <span className={styles.historySeq}>#{entry.sequence}</span>
                  <span className={styles.historyMain}>
                    <span className={styles.historyTitle}>
                      {entry.command?.trim() || (entry.kind === 'root' ? '开局' : '已提交行动')}
                    </span>
                    <span className={styles.historyMeta}>
                      {historyKindLabel(entry.kind)}
                      {entry.timeLabel ? ` · ${entry.timeLabel}` : ''}
                      {isHead ? ' · 当前' : ''}
                    </span>
                  </span>
                  <span className={styles.historyStatus} data-tone={tone}>{narrationStatusLabel(entry.status)}</span>
                </button>
                {entry.status === 'missing' || entry.status === 'failed' ? (
                  <div className={styles.historyRecovery}>
                    <button
                      className={styles.smallButton}
                      data-testid={`regenerate-${entry.pointId}`}
                      disabled={regenerateDisabled}
                      onClick={() => onRegenerate?.(entry.pointId)}
                      title={regenerateReason ?? undefined}
                      type="button"
                    >
                      {entry.status === 'missing' ? '重新生成正文' : '重试生成正文'}
                    </button>
                  </div>
                ) : null}
              </li>
            );
          })}
        </ol>
      )}

      {needsRegeneration.length > 0 && regenerateReason ? (
        <p className={styles.disabledReason} data-testid="history-regenerate-reason" role="note">
          {regenerateReason}
        </p>
      ) : null}
    </section>
  );
}
