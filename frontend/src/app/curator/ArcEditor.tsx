"use client";

import type { CampaignSchema } from "@/types";
import type { CuratorEditor } from "@/app/curator/useCuratorEditor";

type Arc = CampaignSchema["arcs"][number];

export function ArcEditor({ editor }: { editor: CuratorEditor }) {
  const { campaign, addArc } = editor;

  return (
    <div>
      {campaign.arcs.map((arc, ai) => (
        <ArcBlock key={`arc-${ai}`} arc={arc} ai={ai} editor={editor} />
      ))}
      <button className="primary-button" style={{ height: 36 }} onClick={addArc}>+ 添加叙事弧</button>
    </div>
  );
}

function ArcBlock({ arc, ai, editor }: { arc: Arc; ai: number; editor: CuratorEditor }) {
  const { updateArc, addSession, removeArc } = editor;

  return (
    <details open style={{ marginBottom: 12 }}>
      <summary style={{ cursor: "pointer", fontWeight: 700, display: "flex", justifyContent: "space-between", padding: "8px 0" }}>
        <span>{arc.name || `弧 ${ai + 1}`}</span>
        <button className="icon-button" style={{ width: 28, height: 28 }} onClick={(e) => { e.preventDefault(); removeArc(ai); }}>✕</button>
      </summary>
      <div style={{ paddingLeft: 16 }}>
        <input className="textarea" style={{ height: 36, marginBottom: 8 }} value={arc.name} onChange={(e) => updateArc(ai, "name", e.target.value)} placeholder="弧名称" />
        <input className="textarea" style={{ height: 36, marginBottom: 8 }} value={arc.goal} onChange={(e) => updateArc(ai, "goal", e.target.value)} placeholder="弧目标" />

        {arc.sessions.map((session, si) => (
          <SessionBlock key={`session-${si}`} session={session} ai={ai} si={si} editor={editor} />
        ))}
        <button className="primary-button" style={{ marginTop: 4, height: 32, fontSize: 12 }} onClick={() => addSession(ai)}>+ 添加幕</button>
      </div>
    </details>
  );
}

function SessionBlock({
  session,
  ai,
  si,
  editor,
}: {
  session: Arc["sessions"][number];
  ai: number;
  si: number;
  editor: CuratorEditor;
}) {
  const { updateSession, addAnchor } = editor;

  return (
    <details open style={{ marginBottom: 8, marginLeft: 16 }}>
      <summary style={{ cursor: "pointer", fontWeight: 600, padding: "4px 0" }}>{session.name || `幕 ${si + 1}`}</summary>
      <div style={{ paddingLeft: 16 }}>
        <input className="textarea" style={{ height: 36, marginBottom: 8 }} value={session.name} onChange={(e) => updateSession(ai, si, "name", e.target.value)} placeholder="幕名称" />
        <textarea className="textarea small-textarea" value={session.opening_scene} onChange={(e) => updateSession(ai, si, "opening_scene", e.target.value)} placeholder="开场白 (opening_scene)" style={{ marginBottom: 8 }} />

        {session.anchor_events.map((anchor, ani) => (
          <AnchorBlock key={anchor.id} anchor={anchor} ai={ai} si={si} ani={ani} editor={editor} />
        ))}
        <button className="primary-button" style={{ marginTop: 4, height: 32, fontSize: 12 }} onClick={() => addAnchor(ai, si)}>+ 添加锚点</button>
      </div>
    </details>
  );
}

function AnchorBlock({
  anchor,
  ai,
  si,
  ani,
  editor,
}: {
  anchor: Arc["sessions"][number]["anchor_events"][number];
  ai: number;
  si: number;
  ani: number;
  editor: CuratorEditor;
}) {
  const { updateAnchor } = editor;

  return (
    <div style={{ marginBottom: 8, marginLeft: 16, padding: "8px 12px", border: "1px solid var(--border)", borderRadius: 8 }}>
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
  );
}
