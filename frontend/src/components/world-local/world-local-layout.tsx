'use client';

/** Composable shell for the browser-local game page. The page keeps every
 * stateful piece and all session calls; this component only arranges the
 * reading column, the status/history column and the page notices. */
import type { WorldLocalLayoutProps } from './types';
import styles from './world-local.module.css';

export function WorldLocalLayout({
  title,
  subtitle,
  meta,
  banner,
  narration,
  controls,
  status,
  progress,
  history,
  footer,
}: WorldLocalLayoutProps) {
  return (
    <div className={styles.page} data-testid="world-local-layout">
      <header className={styles.pageHeader}>
        <div>
          <h1 className={styles.pageTitle}>{title}</h1>
          {subtitle ? <p className={styles.pageSubtitle}>{subtitle}</p> : null}
        </div>
        {meta ? <div className={styles.pageMeta}>{meta}</div> : null}
      </header>

      {banner ? <div className={styles.bannerSlot}>{banner}</div> : null}

      <div className={styles.layout}>
        <main aria-label="叙事与操作" className={styles.mainColumn}>
          {narration}
          {controls}
        </main>
        <aside aria-label="世界状态与进度" className={styles.sideColumn}>
          {status}
          {history}
          {progress}
        </aside>
      </div>

      {footer ? <footer className={styles.pageFooter}>{footer}</footer> : null}
    </div>
  );
}
