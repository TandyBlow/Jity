"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { getCampaign, listCampaigns } from "@/lib/api";
import type { CampaignArc, CampaignListItem, CampaignSchema } from "@/types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

function emptyCampaign(): CampaignSchema {
  return {
    version: 3,
    title: "新战役",
    core_conflict: "",
    arcs: [],
    constraints: "",
    starting_state: {},
  };
}

export default function CuratorPage() {
  const [campaigns, setCampaigns] = useState<CampaignListItem[]>([]);
  const [campaign, setCampaign] = useState<CampaignSchema>(emptyCampaign());
  const [filename, setFilename] = useState("new_campaign.json");
  const [genPrompt, setGenPrompt] = useState("");
  const [generating, setGenerating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState("");

  useEffect(() => {
    listCampaigns().then((r) => setCampaigns(r.campaigns ?? [])).catch(() => {});
  }, []);

  const handleLoad = useCallback((fname: string) => {
    getCampaign(fname).then((r) => {
      setCampaign(r.campaign as CampaignSchema);
      setFilename(fname);
    }).catch(() => setStatus("加载失败"));
  }, []);

  const handleGenerate = useCallback(async () => {
    if (!genPrompt.trim()) return;
    setGenerating(true);
    setStatus("生成中…");
    try {
      const res = await fetch(`${API_BASE}/campaigns/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt: genPrompt }),
      });
      const data = await res.json();
      if (data.campaign) {
        setCampaign(data.campaign as CampaignSchema);
        setFilename(data.saved_to?.split("/").pop() ?? "generated.json");
        setStatus("生成完成！请审查后保存。");
        // Refresh campaign list
        listCampaigns().then((r) => setCampaigns(r.campaigns ?? [])).catch(() => {});
      } else {
        setStatus("生成失败：" + (data.detail ?? "未知错误"));
      }
    } catch (e) {
      setStatus("请求失败：" + String(e));
    }
    setGenerating(false);
  }, [genPrompt]);

  const handleSave = useCallback(async () => {
    setSaving(true);
    setStatus("保存中…");
    try {
      const res = await fetch(`${API_BASE}/campaigns/save`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ filename, campaign }),
      });
      const data = await res.json();
      if (data.status === "saved") {
        setStatus("已保存！");
        listCampaigns().then((r) => setCampaigns(r.campaigns ?? [])).catch(() => {});
      } else {
        setStatus("保存失败：" + (data.detail ?? ""));
      }
    } catch (e) {
      setStatus("请求失败：" + String(e));
    }
    setSaving(false);
  }, [filename, campaign]);

  const handleDownload = useCallback(() => {
    const blob = new Blob([JSON.stringify(campaign, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  }, [campaign, filename]);

  // Arc/session/anchor editing helpers
  const updateField = (field: string, value: unknown) => {
    setCampaign((prev) => ({ ...prev, [field]: value }));
  };

  const updateArc = (ai: number, field: string, value: unknown) => {
    setCampaign((prev) => {
      const arcs = [...prev.arcs];
      arcs[ai] = { ...arcs[ai], [field]: value };
      return { ...prev, arcs };
    });
  };

  const addArc = () => {
    setCampaign((prev) => ({
      ...prev,
      arcs: [...prev.arcs, { name: "新弧", goal: "", sessions: [] }],
    }));
  };

  const addSession = (ai: number) => {
    setCampaign((prev) => {
      const arcs = [...prev.arcs];
      arcs[ai] = {
        ...arcs[ai],
        sessions: [...arcs[ai].sessions, { name: "新幕", opening_scene: "", anchor_events: [] }],
      };
      return { ...prev, arcs };
    });
  };

  const updateSession = (ai: number, si: number, field: string, value: unknown) => {
    setCampaign((prev) => {
      const arcs = [...prev.arcs];
      const sessions = [...arcs[ai].sessions];
      sessions[si] = { ...sessions[si], [field]: value };
      arcs[ai] = { ...arcs[ai], sessions };
      return { ...prev, arcs };
    });
  };

  const addAnchor = (ai: number, si: number) => {
    setCampaign((prev) => {
      const arcs = [...prev.arcs];
      const sessions = [...arcs[ai].sessions];
      sessions[si] = {
        ...sessions[si],
        anchor_events: [
          ...sessions[si].anchor_events,
          {
            id: `anchor-${Date.now()}`,
            name: "新锚点",
            description: "",
            priority: 3,
            trigger_conditions: {},
          },
        ],
      };
      arcs[ai] = { ...arcs[ai], sessions };
      return { ...prev, arcs };
    });
  };

  const updateAnchor = (ai: number, si: number, ani: number, field: string, value: unknown) => {
    setCampaign((prev) => {
      const arcs = [...prev.arcs];
      const sessions = [...arcs[ai].sessions];
      const anchors = [...sessions[si].anchor_events];
      anchors[ani] = { ...anchors[ani], [field]: value };
      sessions[si] = { ...sessions[si], anchor_events: anchors };
      arcs[ai] = { ...arcs[ai], sessions };
      return { ...prev, arcs };
    });
  };

  const removeArc = (ai: number) => {
    setCampaign((prev) => ({
      ...prev,
      arcs: prev.arcs.filter((_, i) => i !== ai),
    }));
  };

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
          {/* AI Generation */}
          <div className="clue-board" style={{ position: "static", marginBottom: 20 }}>
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
          </div>

          {/* Basic info */}
          <div style={{ marginBottom: 16 }}>
            <input
              className="textarea"
              style={{ height: 40, marginBottom: 8, fontSize: 20, fontWeight: 700 }}
              value={campaign.title}
              onChange={(e) => updateField("title", e.target.value)}
              placeholder="战役标题"
            />
            <div style={{ display: "flex", gap: 8, marginBottom: 8 }}>
              <input className="textarea" style={{ height: 36, flex: 1 }} value={filename} onChange={(e) => setFilename(e.target.value)} placeholder="文件名" />
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

          {/* Arcs */}
          {campaign.arcs.map((arc, ai) => (
            <details key={`arc-${ai}`} open style={{ marginBottom: 12 }}>
              <summary style={{ cursor: "pointer", fontWeight: 700, display: "flex", justifyContent: "space-between", padding: "8px 0" }}>
                <span>{arc.name || `弧 ${ai + 1}`}</span>
                <button className="icon-button" style={{ width: 28, height: 28 }} onClick={(e) => { e.preventDefault(); removeArc(ai); }}>✕</button>
              </summary>
              <div style={{ paddingLeft: 16 }}>
                <input className="textarea" style={{ height: 36, marginBottom: 8 }} value={arc.name} onChange={(e) => updateArc(ai, "name", e.target.value)} placeholder="弧名称" />
                <input className="textarea" style={{ height: 36, marginBottom: 8 }} value={arc.goal} onChange={(e) => updateArc(ai, "goal", e.target.value)} placeholder="弧目标" />

                {/* Sessions */}
                {arc.sessions.map((session, si) => (
                  <details key={`session-${si}`} open style={{ marginBottom: 8, marginLeft: 16 }}>
                    <summary style={{ cursor: "pointer", fontWeight: 600, padding: "4px 0" }}>{session.name || `幕 ${si + 1}`}</summary>
                    <div style={{ paddingLeft: 16 }}>
                      <input className="textarea" style={{ height: 36, marginBottom: 8 }} value={session.name} onChange={(e) => updateSession(ai, si, "name", e.target.value)} placeholder="幕名称" />
                      <textarea className="textarea small-textarea" value={session.opening_scene} onChange={(e) => updateSession(ai, si, "opening_scene", e.target.value)} placeholder="开场白 (opening_scene)" style={{ marginBottom: 8 }} />

                      {/* Anchors */}
                      {session.anchor_events.map((anchor, ani) => (
                        <div key={anchor.id} style={{ marginBottom: 8, marginLeft: 16, padding: "8px 12px", border: "1px solid var(--border)", borderRadius: 8 }}>
                          <div style={{ display: "flex", gap: 8, marginBottom: 4 }}>
                            <input className="textarea" style={{ height: 32, flex: 1 }} value={anchor.name} onChange={(e) => updateAnchor(ai, si, ani, "name", e.target.value)} placeholder="锚点名称" />
                            <input className="textarea" style={{ height: 32, width: 70 }} value={anchor.priority} onChange={(e) => updateAnchor(ai, si, ani, "priority", parseInt(e.target.value) || 3)} type="number" min={1} max={5} />
                          </div>
                          <input className="textarea" style={{ height: 32, marginBottom: 4 }} value={anchor.description} onChange={(e) => updateAnchor(ai, si, ani, "description", e.target.value)} placeholder="描述" />
                          <div style={{ display: "flex", gap: 6 }}>
                            <input className="textarea" style={{ height: 30, flex: 1, fontSize: 12 }} value={anchor.trigger_conditions?.location ?? ""} onChange={(e) => updateAnchor(ai, si, ani, "trigger_conditions", { ...anchor.trigger_conditions, location: e.target.value || null })} placeholder="地点" />
                            <input className="textarea" style={{ height: 30, flex: 1, fontSize: 12 }} value={anchor.trigger_conditions?.npc_present ?? ""} onChange={(e) => updateAnchor(ai, si, ani, "trigger_conditions", { ...anchor.trigger_conditions, npc_present: e.target.value || null })} placeholder="NPC" />
                            <input className="textarea" style={{ height: 30, flex: 1, fontSize: 12 }} value={anchor.trigger_conditions?.item_held ?? ""} onChange={(e) => updateAnchor(ai, si, ani, "trigger_conditions", { ...anchor.trigger_conditions, item_held: e.target.value || null })} placeholder="物品" />
                          </div>
                        </div>
                      ))}
                      <button className="primary-button" style={{ marginTop: 4, height: 32, fontSize: 12 }} onClick={() => addAnchor(ai, si)}>+ 添加锚点</button>
                    </div>
                  </details>
                ))}
                <button className="primary-button" style={{ marginTop: 4, height: 32, fontSize: 12 }} onClick={() => addSession(ai)}>+ 添加幕</button>
              </div>
            </details>
          ))}
          <button className="primary-button" style={{ height: 36 }} onClick={addArc}>+ 添加叙事弧</button>
        </div>

        {/* Review panel */}
        <div className="clue-board" style={{ position: "static" }}>
          <h2>审查摘要</h2>
          <div style={{ fontSize: 13, lineHeight: 1.8 }}>
            <div><strong>标题：</strong>{campaign.title || "未设置"}</div>
            <div><strong>版本：</strong>v{campaign.version}</div>
            <div><strong>叙事弧：</strong>{campaign.arcs.length}个</div>
            <div><strong>总幕数：</strong>{campaign.arcs.reduce((s, a) => s + a.sessions.length, 0)}</div>
            <div><strong>总锚点：</strong>{campaign.arcs.reduce((s, a) => s + a.sessions.reduce((ss, ses) => ss + ses.anchor_events.length, 0), 0)}</div>
            <div style={{ marginTop: 12 }}><strong>锚点：</strong></div>
            <ul style={{ paddingLeft: 18, margin: "4px 0" }}>
              {campaign.arcs.flatMap((a) => a.sessions.flatMap((s) => s.anchor_events)).slice(0, 15).map((a) => (
                <li key={a.id} style={{ fontSize: 12, color: "var(--muted)" }}>{a.name} (P{a.priority})</li>
              ))}
            </ul>
            {campaign.arcs.flatMap((a) => a.sessions.flatMap((s) => s.anchor_events)).length > 15 && (
              <div style={{ fontSize: 12, color: "var(--muted)" }}>…还有更多</div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
