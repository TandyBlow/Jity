'use client';

/** Local save + optional progress sync + branch choice. The panel reports the
 * states the page hands in. A missing sync client or branch callback is shown
 * as disabled with a reason; nothing here fakes a successful upload. */
import { useId } from 'react';

import type { ForkOption, ProgressStatusProps, SaveState, SyncState } from './types';
import styles from './world-local.module.css';

const SAVE_LABELS: Record<SaveState, string> = {
  idle: '尚未写入存档',
  saving: '正在保存',
  saved: '已保存',
  failed: '保存失败',
};

const SYNC_LABELS: Record<SyncState, string> = {
  'local-only': '仅本机保存',
  offline: '离线等待',
  syncing: '同步中',
  synced: '已同步',
  failed: '同步失败',
  conflict: '分叉待选择',
};

function saveTone(state: SaveState): string {
  if (state === 'failed') return 'failed';
  if (state === 'saving') return 'pending';
  if (state === 'saved') return 'ready';
  return 'unknown';
}

function syncTone(state: SyncState): string {
  if (state === 'failed' || state === 'conflict') return 'failed';
  if (state === 'syncing') return 'pending';
  if (state === 'synced') return 'ready';
  return 'unknown';
}

function forkLabel(fork: ForkOption, active: boolean): string {
  return `${fork.savedAtLabel} · 保存 revision ${fork.revision}${active ? ' · 当前分支' : ''}`;
}

export function ProgressStatus({
  online,
  save,
  sync,
  forks = [],
  activeForkId,
  onChooseFork,
  chooseForkDisabledReason = null,
}: ProgressStatusProps) {
  const baseId = useId().replace(/[^a-zA-Z0-9_-]/g, '');
  const headingId = `${baseId}-title`;
  const forkName = `${baseId}-fork`;
  const retryDisabled = !save.onRetry || Boolean(save.retryDisabledReason);
  const retryReason = retryDisabled
    ? (save.retryDisabledReason ?? (!save.onRetry ? '当前会话尚未接入保存重试' : null))
    : null;
  const effectiveSync = !online && sync && sync.state !== 'local-only' ? 'offline' : sync?.state ?? null;
  const syncBlocked = Boolean(sync) && (
    !sync?.onSync
    || !online
    || sync.state === 'offline'
    || sync.state === 'syncing'
    || sync.state === 'conflict'
    || Boolean(sync.syncDisabledReason)
  );
  const syncReason = !sync
    ? null
    : !sync.onSync
      ? '同步服务尚未接通'
      : !online
        ? '当前离线，恢复网络后才能同步'
        : sync.state === 'offline'
          ? '同步连接尚未恢复'
          : sync.state === 'syncing'
            ? '同步正在进行'
            : sync.state === 'conflict'
              ? '先选择活跃分叉再同步'
              : sync.syncDisabledReason ?? null;
  const forkBlocked = !onChooseFork || Boolean(chooseForkDisabledReason);

  return (
    <section aria-labelledby={headingId} className={styles.panel} data-testid="progress-status">
      <header className={styles.cardHeader}>
        <h2 className={styles.cardTitle} id={headingId}>本地进度</h2>
        <span className={styles.badge} data-tone={saveTone(save.state)} data-testid="save-state">
          {SAVE_LABELS[save.state]}
        </span>
      </header>

      {!online ? (
        <div className={styles.offlineBox} data-testid="offline-banner" role="status">
          <strong>当前离线</strong>
          <span>本地游玩与本地保存继续；进度同步暂停。</span>
        </div>
      ) : null}

      <dl className={styles.facts}>
        <div>
          <dt>保存位置</dt>
          <dd>这台设备的浏览器</dd>
        </div>
        {save.savedAtLabel ? (
          <div>
            <dt>最近保存</dt>
            <dd>{save.savedAtLabel}</dd>
          </div>
        ) : null}
        {save.detail ? (
          <div>
            <dt>说明</dt>
            <dd>{save.detail}</dd>
          </div>
        ) : null}
      </dl>

      {save.state === 'failed' ? (
        <div className={styles.failureBox} role="alert">
          <p className={styles.failureTitle}>本地保存失败</p>
          <p className={styles.failureDetail}>{save.error ?? '未提供错误信息。'}</p>
          <button
            className={styles.smallButton}
            data-testid="save-retry"
            disabled={retryDisabled}
            onClick={() => save.onRetry?.()}
            title={retryReason ?? undefined}
            type="button"
          >
            重试保存
          </button>
          {retryReason ? <p className={styles.disabledReason} role="note">{retryReason}</p> : null}
        </div>
      ) : null}

      <div className={styles.syncBlock}>
        <div className={styles.controlsHeader}>
          <h3 className={styles.blockTitle}>进度同步</h3>
          {sync ? (
            <span className={styles.badge} data-tone={effectiveSync ? syncTone(effectiveSync) : 'unknown'} data-testid="sync-state">
              {effectiveSync ? SYNC_LABELS[effectiveSync] : SYNC_LABELS['local-only']}
            </span>
          ) : null}
        </div>

        {!sync ? (
          <>
            <p className={styles.panelHint}>同步服务尚未接通：进度只保存在这台设备的浏览器里。</p>
            <button className={styles.smallButton} data-testid="sync-action" disabled title="同步服务尚未接通" type="button">
              立即同步
            </button>
            <p className={styles.disabledReason} data-testid="sync-reason" role="note">同步尚未接线，当前不会上传进度。</p>
          </>
        ) : (
          <>
            {sync.lastSyncedAtLabel ? <p className={styles.panelHint}>上次同步：{sync.lastSyncedAtLabel}</p> : null}
            {sync.state === 'failed' && sync.error ? (
              <p className={styles.failureDetail} role="alert">同步失败：{sync.error}</p>
            ) : null}
            {sync.state === 'conflict' ? (
              <p className={styles.panelHint}>服务器上有两条以上分支，选择下方的活跃分支。</p>
            ) : null}
            <button
              className={styles.smallButton}
              data-testid="sync-action"
              disabled={syncBlocked}
              onClick={() => sync.onSync?.()}
              title={syncReason ?? undefined}
              type="button"
            >
              {sync.state === 'syncing' ? '同步中…' : '立即同步'}
            </button>
            {syncReason ? <p className={styles.disabledReason} data-testid="sync-reason" role="note">{syncReason}</p> : null}
          </>
        )}
      </div>

      {forks.length > 0 ? (
        <fieldset className={styles.forks} data-testid="fork-group">
          <legend className={styles.blockTitle}>分叉</legend>
          <p className={styles.panelHint}>保留的每一份快照都可恢复。选择只切换活跃分支，不会合并游戏事实。</p>
          {forks.map((fork) => {
            const active = fork.snapshotId === activeForkId;
            return (
              <label className={styles.forkOption} data-active={active} key={fork.snapshotId}>
                <input
                  checked={active}
                  data-testid={`fork-${fork.snapshotId}`}
                  disabled={active || forkBlocked}
                  name={forkName}
                  onChange={() => onChooseFork?.(fork.snapshotId)}
                  type="radio"
                />
                <span className={styles.forkMain}>
                  <span className={styles.forkTitle}>{forkLabel(fork, active)}</span>
                  <span className={styles.historyMeta}>
                    {fork.parentSnapshotIds.length > 0
                      ? `父快照：${fork.parentSnapshotIds.join('、')}`
                      : '根快照'}
                  </span>
                  {fork.summary ? <span className={styles.forkSummary}>{fork.summary}</span> : null}
                </span>
              </label>
            );
          })}
          {forkBlocked ? (
            <p className={styles.disabledReason} data-testid="fork-reason" role="note">
              {chooseForkDisabledReason ?? '分叉选择尚未接线：这里只展示元数据，不会切换状态。'}
            </p>
          ) : null}
        </fieldset>
      ) : null}
    </section>
  );
}
