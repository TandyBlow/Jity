"use client";

import type { CuratorEditor } from "@/app/curator/useCuratorEditor";

export function GenerationPanel({ editor }: { editor: CuratorEditor }) {
  const {
    genPrompt, setGenPrompt, generating, handleGenerate,
    novelUploading, novelErrors, handleNovelUpload,
  } = editor;

  return (
    <div className="clue-board curator-panel">
      <h2>AI 生成战役</h2>
      <textarea
        className="textarea small-textarea curator-gen-input"
        placeholder="描述你想创建的战役，例如：1920s 上海超自然侦探，调查外滩连环失踪案…"
        value={genPrompt}
        onChange={(e) => setGenPrompt(e.target.value)}
      />
      <button className="primary-button curator-gen-submit" onClick={handleGenerate} disabled={generating || !genPrompt.trim()}>
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
    <div className="curator-upload-card">
      <h3>从小说 TXT 生成</h3>
      <input
        type="file"
        accept=".txt"
        disabled={uploading}
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) onUpload(f);
        }}
      />
      {uploading && <span>正在分析小说…（约30-60秒）</span>}
      {errors.length > 0 && (
        <div className="curator-upload-errors">
          <strong>以下章节提取失败，需人工标注：</strong>
          <ul>{errors.map((e, i) => <li key={i}>{e}</li>)}</ul>
        </div>
      )}
    </div>
  );
}
