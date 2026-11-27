'use client';

/** Phone evidence panel (`?phoneEvidence=1`): a compact, copyable JSON of the
 * turn records the page already mirrors on window.__worldTurns. It exists for
 * real-device runs where no CDP endpoint is available (WebView browsers). */
import { useEffect, useRef, useState } from 'react';
import styles from './page.module.css';

interface TurnLike {
  index?: number; input?: string;
  acceptedMs?: number | null; draftMs?: number | null;
  source?: string | null;
  clocks?: { firstReadableAtMs?: number | null; firstAcceptedAtMs?: number | null; pointCommittedAtMs?: number | null; inputAt?: string };
  microStats?: Array<Record<string, unknown>>;
  semanticCalls?: Array<{ task?: string; ms?: number; fallback?: boolean }>;
  narration?: { text?: string } | null;
  points?: Array<{ text?: string; source?: string }>;
  modelId?: string | null;
}

export default function PhoneEvidencePanel() {
  const [enabled, setEnabled] = useState(false);
  const [text, setText] = useState('');
  const [copied, setCopied] = useState(false);
  const [uploaded, setUploaded] = useState<string | null>(null);
  const lastUploaded = useRef('');
  useEffect(() => {
    if (typeof window === 'undefined') return;
    if (new URLSearchParams(window.location.search).get('phoneEvidence') !== '1') return;
    setEnabled(true);
    const timer = setInterval(() => {
      const turns = ((window as unknown as { __worldTurns?: TurnLike[] }).__worldTurns ?? []).slice(-8);
      const compact = turns.map((turn) => {
        const micro: Record<string, number> = {};
        for (const row of turn.microStats ?? []) {
          const port = String(row.port ?? '?');
          const count = Number(row.inferences ?? row.calls ?? row.pairs ?? 1);
          micro[port] = (micro[port] ?? 0) + count;
        }
        const calls: Record<string, number> = {};
        for (const call of turn.semanticCalls ?? []) {
          const task = String(call.task ?? '?');
          calls[task] = (calls[task] ?? 0) + 1;
        }
        const prose = (turn.narration?.text ?? turn.points?.map((p) => p.text ?? '').join('') ?? '');
        return {
          index: turn.index ?? null,
          input: (turn.input ?? '').slice(0, 60),
          firstReadableMs: turn.clocks?.firstReadableAtMs ?? null,
          firstAcceptedMs: turn.clocks?.firstAcceptedAtMs ?? null,
          pointCommittedMs: turn.clocks?.pointCommittedAtMs ?? null,
          draftMs: turn.draftMs ?? null,
          acceptedMs: turn.acceptedMs ?? null,
          source: turn.source ?? null,
          proseChars: prose.length,
          micro,
          semanticCalls: calls,
          modelId: turn.modelId ?? null,
        };
      });
      setText(JSON.stringify({ at: new Date().toISOString(), ua: navigator.userAgent, turns: compact }, null, 1));
    }, 2000);
    return () => clearInterval(timer);
  }, []);
  useEffect(() => {
    if (!enabled || !text || text === lastUploaded.current) return;
    const timer = setTimeout(() => {
      lastUploaded.current = text;
      fetch('/api/phone-evidence', { method: 'POST', headers: { 'content-type': 'application/json' }, body: text })
        .then((response) => setUploaded(response.ok ? new Date().toLocaleTimeString() : '失败'))
        .catch(() => setUploaded('失败'));
    }, 1500);
    return () => clearTimeout(timer);
  }, [enabled, text]);
  if (!enabled) return null;
  return (
    <div className={styles.phoneEvidence}>
      <div className={styles.phoneEvidenceHeader}>
        <span>手机证据{uploaded ? ` · 已回传 ${uploaded}` : ''}</span>
        <button type="button" onClick={() => { void navigator.clipboard?.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 1500); }}>
          {copied ? '已复制' : '复制'}
        </button>
      </div>
      <textarea readOnly value={text} onFocus={(event) => event.currentTarget.select()}
        className={styles.phoneEvidenceText} />
    </div>
  );
}
