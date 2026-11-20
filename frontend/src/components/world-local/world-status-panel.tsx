'use client';

/** Read-only sidebar. Every value comes from `WorldStatusView`, which the page
 * derives from the committed state; this component holds no copy of the state. */
import { useId } from 'react';

import type { WorldStatusPanelProps } from './types';
import styles from './world-local.module.css';

function clampSanity(value: number): number {
  if (!Number.isFinite(value)) return 0;
  return Math.max(0, Math.min(100, Math.round(value)));
}

export function WorldStatusPanel({ status, pendingTaskLimit = 6 }: WorldStatusPanelProps) {
  const baseId = useId().replace(/[^a-zA-Z0-9_-]/g, '');
  const headingId = `${baseId}-title`;
  const pending = status.tasks.filter((task) => !task.done);
  const achieved = status.tasks.filter((task) => task.done);
  const shownPending = pending.slice(0, Math.max(0, pendingTaskLimit));
  const hiddenPending = pending.length - shownPending.length;
  const sanity = status.sanity == null ? null : clampSanity(status.sanity);

  return (
    <section aria-labelledby={headingId} className={styles.panel} data-testid="world-status">
      <header className={styles.cardHeader}>
        <h2 className={styles.cardTitle} id={headingId}>世界状态</h2>
        <span className={styles.panelHint}>已提交状态</span>
      </header>

      <div className={styles.identity}>
        <h3 className={styles.identityName}>{status.name}</h3>
        {sanity == null ? (
          <p className={styles.cardSubtle}>精神值未记录</p>
        ) : (
          <>
            <div
              aria-label="精神值"
              aria-valuemax={100}
              aria-valuemin={0}
              aria-valuenow={sanity}
              aria-valuetext={`${sanity} / 100`}
              className={styles.meter}
              role="meter"
            >
              <span className={styles.meterFill} style={{ width: `${sanity}%` }} />
            </div>
            <p className={styles.cardSubtle}>精神值 {sanity} / 100</p>
          </>
        )}
      </div>

      <dl className={styles.facts}>
        <div>
          <dt>时间</dt>
          <dd>{status.timeLabel || '未知'}</dd>
        </div>
        <div>
          <dt>地点</dt>
          <dd>{status.locationLabel || '未知'}</dd>
        </div>
      </dl>

      {status.personality ? (
        <p className={styles.personality}>{status.personality}</p>
      ) : null}

      <div className={styles.block}>
        <h3 className={styles.blockTitle}>附近的人</h3>
        {status.nearby.length > 0 ? (
          <ul className={styles.tagList}>
            {status.nearby.map((person) => (
              <li className={styles.tag} key={person.id}>{person.name}</li>
            ))}
          </ul>
        ) : (
          <p className={styles.emptyText}>附近没有其他人。</p>
        )}
      </div>

      <div className={styles.block}>
        <h3 className={styles.blockTitle}>任务</h3>
        {status.tasks.length > 0 ? (
          <ul className={styles.taskList}>
            {shownPending.map((task) => (
              <li className={styles.task} data-done="false" key={task.id}>
                <span className={styles.taskFlag}>待办</span>
                <span>{task.goal}</span>
              </li>
            ))}
            {hiddenPending > 0 ? (
              <li className={styles.taskMore}>另有 {hiddenPending} 个待办任务未展开</li>
            ) : null}
            {achieved.map((task) => (
              <li className={styles.task} data-done="true" key={task.id}>
                <span className={styles.taskFlag}>已完成</span>
                <span className={styles.taskGoalDone}>{task.goal}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className={styles.emptyText}>没有记录任务。</p>
        )}
      </div>

      {status.items && status.items.length > 0 ? (
        <div className={styles.block}>
          <h3 className={styles.blockTitle}>附近的物</h3>
          <ul className={styles.tagList}>
            {status.items.map((item) => (
              <li className={styles.tag} key={item.id}>{item.name}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}
