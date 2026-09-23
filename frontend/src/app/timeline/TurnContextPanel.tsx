"use client";

import type { TurnContext } from "@/types";

const SECTION_LABELS: Record<string, string> = {
  campaign_context: "战役与记忆注入",
  system_prompt: "系统提示与状态快照",
  messages: "最近对话",
  rag_chunks: "RAG 检索",
  player_action: "玩家行动",
};

/**
 * What actually went into this turn's prompt.
 *
 * The prompt used to be assembled and discarded, so the only thing a finished
 * run could say about its context was which chunks were retrieved. Turns
 * stored before the prompt was persisted say so rather than showing zeros.
 */
export function TurnContextPanel({ context }: { context: TurnContext }) {
  if (!context.recorded) {
    return (
      <section className="turn-context">
        <h3>本轮注入的上下文</h3>
        <p className="meta">这一轮的 prompt 没有被记录：早于落盘，或是脚本开场。</p>
      </section>
    );
  }

  const sections = Object.entries(context.prompt_sections);

  return (
    <section className="turn-context">
      <h3>本轮注入的上下文</h3>
      <div className="turn-context-stats">
        <span>token {context.token_count}</span>
        <span>延迟 {context.latency_ms} ms</span>
        <span>正文 {context.word_count} 字</span>
        <span>检索命中 {context.retrieved_chunks.length}</span>
      </div>
      <div className="turn-context-sections">
        {sections.map(([name, text]) => (
          <div key={name}>
            <span>{SECTION_LABELS[name] ?? name}</span>
            <strong>{text.length} 字</strong>
          </div>
        ))}
      </div>
      {context.retrieved_chunks.length > 0 ? (
        <ul className="turn-context-chunks">
          {context.retrieved_chunks.map((chunk) => (
            <li key={chunk.id}>
              <span className="turn-context-score">{chunk.score.toFixed(3)}</span>
              <span>{chunk.title}</span>
              <span className="meta">{chunk.source_type}</span>
            </li>
          ))}
        </ul>
      ) : null}
      <details className="turn-context-prompt">
        <summary>实际发出的 prompt 全文</summary>
        <pre>{context.prompt_text}</pre>
      </details>
    </section>
  );
}
