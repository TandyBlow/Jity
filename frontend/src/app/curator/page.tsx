"use client";

import Link from "next/link";

import { ArcEditor } from "@/app/curator/ArcEditor";
import { GenerationPanel } from "@/app/curator/GenerationPanel";
import { ReviewPanel } from "@/app/curator/ReviewPanel";
import { useCuratorEditor } from "@/app/curator/useCuratorEditor";

export default function CuratorPage() {
  const editor = useCuratorEditor();
  const {
    campaigns, campaignsError, filename, setFilename, saving, status,
    handleLoad, handleSave, handleDownload,
  } = editor;

  return (
    <div className="timeline-shell">
      <div className="timeline-header">
        <div>
          <Link href="/" className="back-link">← 返回控制台</Link>
          <h1>战役策展编辑器</h1>
        </div>
        <div className="curator-header-actions">
          <select
            className="select"
            value=""
            onChange={(e) => { if (e.target.value) handleLoad(e.target.value); }}
          >
            <option value="">加载已有战役…</option>
            {campaigns.map((c) => (
              <option key={c.filename} value={c.filename}>{c.title}</option>
            ))}
          </select>
          <button className="primary-button fitted" onClick={handleSave} disabled={saving}>
            {saving ? "保存中…" : "保存"}
          </button>
          <button className="icon-button" onClick={handleDownload} title="下载JSON">⬇</button>
        </div>
      </div>

      {campaignsError ? <p className="load-error" role="alert">{campaignsError}</p> : null}

      {status && (
        <div className={`curator-status ${status.includes("失败") ? "error" : "meta"}`}>
          {status}
        </div>
      )}

      <div className="timeline-layout">
        {/* Main editor */}
        <div>
          <GenerationPanel editor={editor} />

          <BasicInfo editor={editor} filename={filename} onFilenameChange={setFilename} />

          <ArcEditor editor={editor} />
        </div>

        {/* Review panel */}
        <ReviewPanel editor={editor} />
      </div>
    </div>
  );
}

function BasicInfo({
  editor,
  filename,
  onFilenameChange,
}: {
  editor: ReturnType<typeof useCuratorEditor>;
  filename: string;
  onFilenameChange: (filename: string) => void;
}) {
  const { campaign, updateField } = editor;

  return (
    <div className="curator-section">
      <input
        className="textarea curator-title-input"
        value={campaign.title}
        onChange={(e) => updateField("title", e.target.value)}
        placeholder="战役标题"
      />
      <div className="curator-field-row">
        <input className="textarea curator-grow" value={filename} onChange={(e) => onFilenameChange(e.target.value)} placeholder="文件名" />
        <input className="textarea" value={campaign.version} onChange={(e) => updateField("version", parseInt(e.target.value) || 3)} placeholder="版本" type="number" />
      </div>
      <textarea
        className="textarea"
        placeholder="核心冲突 (core_conflict)"
        value={campaign.core_conflict}
        onChange={(e) => updateField("core_conflict", e.target.value)}
      />
      <textarea
        className="textarea small-textarea curator-follow"
        placeholder="叙事约束 (constraints)"
        value={campaign.constraints}
        onChange={(e) => updateField("constraints", e.target.value)}
      />
    </div>
  );
}
