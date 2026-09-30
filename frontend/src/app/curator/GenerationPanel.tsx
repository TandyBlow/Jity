"use client";

import type { CuratorEditor } from "@/app/curator/useCuratorEditor";

export function GenerationPanel({ editor }: { editor: CuratorEditor }) {
  const {
    genPrompt, setGenPrompt, generating, handleGenerate,
    novelUploading, novelErrors, handleNovelUpload,
  } = editor;

  return (
    <div className="clue-board" style={{ marginBottom: "var(--space-6)" }}>
      <h2>AI 生成战役</h2>
      <textarea
        className="textarea small-textarea"
        placeholder="描述你想创建的战役，例如：1920s 上海超自然侦探，调查外滩连环失踪案…"
        value={genPrompt}
        onChange={(e) => setGenPrompt(e.target.value)}
        style={{ marginBottom: 8 }}
      />
      <button className="primary-button" style={{ marginTop: 0 }} onClick={handleGenerate} disabled={generating || !genPrompt.trim()}>
        {generating ? "生成中…" : "生成战役"}
      </button>

      <NovelUpload uploading={novelUploading} errors={novelErrors} onUpload={handleNovelUpload} />
    </div>
  );
}

function NovelUpload({
  uploading,
  errors,
  onUpload,
}: {
  uploading: boolean;
  errors: string[];
  onUpload: (file: File) => void;
}) {
  return (
    <div style={{ marginTop: 16, padding: 12, border: "1px solid var(--color-border)", borderRadius: "var(--radius-sm)" }}>
      <h3 style={{ margin: "0 0 8px 0", fontSize: "var(--fs-lg)" }}>从小说 TXT 生成</h3>
      <input
        type="file"
        accept=".txt"
        disabled={uploading}
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) onUpload(f);
        }}
        style={{ fontSize: "var(--fs-md)" }}
      />
      {uploading && <span style={{ marginLeft: 8, fontSize: "var(--fs-md)" }}>正在分析小说…（约30-60秒）</span>}
      {errors.length > 0 && (
        <div style={{ marginTop: 8, padding: 8, background: "color-mix(in srgb, var(--color-danger) 18%, var(--color-bg))", borderRadius: 4, fontSize: "var(--fs-md)" }}>
          <strong>以下章节提取失败，需人工标注：</strong>
          <ul style={{ margin: "4px 0 0 16px" }}>{errors.map((e, i) => <li key={i}>{e}</li>)}</ul>
        </div>
      )}
    </div>
  );
}
