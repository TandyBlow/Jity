"use client";

import Link from "next/link";

import { ArcEditor } from "@/app/curator/ArcEditor";
import { GenerationPanel } from "@/app/curator/GenerationPanel";
import { ReviewPanel } from "@/app/curator/ReviewPanel";
import { useCuratorEditor } from "@/app/curator/useCuratorEditor";

export default function CuratorPage() {
  const editor = useCuratorEditor();
  const {
    campaigns, campaign, filename, setFilename, saving, status,
    handleLoad, handleSave, handleDownload, updateField,
  } = editor;

  return (
    <div className="timeline-shell">
      <div className="timeline-header">
        <div>
          <Link href="/" className="back-link">← 返回控制台</Link>
          <h1>战役策展编辑器</h1>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <select
            className="select"
            style={{ maxWidth: 260 }}
            value=""
            onChange={(e) => { if (e.target.value) handleLoad(e.target.value); }}
          >
            <option value="">加载已有战役…</option>
            {campaigns.map((c) => (
              <option key={c.filename} value={c.filename}>{c.title}</option>
            ))}
          </select>
          <button className="primary-button" style={{ width: "auto", margin: 0, padding: "0 16px" }} onClick={handleSave} disabled={saving}>
            {saving ? "保存中…" : "保存"}
          </button>
          <button className="icon-button" onClick={handleDownload} title="下载JSON">⬇</button>
        </div>
      </div>

      {status && (
        <div style={{ maxWidth: 1080, margin: "0 auto 16px" }} className={status.includes("失败") ? "error" : "meta"}>
          {status}
        </div>
      )}

      <div className="timeline-layout" style={{ maxWidth: 1080, margin: "0 auto" }}>
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
    <div style={{ marginBottom: 16 }}>
      <input
        className="textarea"
        style={{ height: 40, marginBottom: 8, fontSize: 20, fontWeight: 700 }}
        value={campaign.title}
        onChange={(e) => updateField("title", e.target.value)}
        placeholder="战役标题"
      />
      <div style={{ display: "flex", gap: 8, marginBottom: 8 }}>
        <input className="textarea" style={{ height: 36, flex: 1 }} value={filename} onChange={(e) => onFilenameChange(e.target.value)} placeholder="文件名" />
        <input className="textarea" style={{ height: 36, width: 80 }} value={campaign.version} onChange={(e) => updateField("version", parseInt(e.target.value) || 3)} placeholder="版本" type="number" />
      </div>
      <textarea
        className="textarea"
        placeholder="核心冲突 (core_conflict)"
        value={campaign.core_conflict}
        onChange={(e) => updateField("core_conflict", e.target.value)}
      />
      <textarea
        className="textarea small-textarea"
        placeholder="叙事约束 (constraints)"
        value={campaign.constraints}
        onChange={(e) => updateField("constraints", e.target.value)}
        style={{ marginTop: 8 }}
      />
    </div>
  );
}
