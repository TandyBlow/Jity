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
      <button className="primary-button" style={{ height: "var(--control-h-md)" }} onClick={addArc}>+ 添加叙事弧</button>
    </div>
  );
}

function ArcBlock({ arc, ai, editor }: { arc: Arc; ai: number; editor: CuratorEditor }) {
  const { updateArc, addSession, removeArc } = editor;

  return (
    <details open className="curator-block">
      <summary className="curator-summary">
        <span>{arc.name || `弧 ${ai + 1}`}</span>
        <button className="icon-button" onClick={(e) => { e.preventDefault(); removeArc(ai); }}>✕</button>
      </summary>
      <div className="curator-indent">
        <input className="textarea curator-field" value={arc.name} onChange={(e) => updateArc(ai, "name", e.target.value)} placeholder="弧名称" />
        <input className="textarea curator-field" value={arc.goal} onChange={(e) => updateArc(ai, "goal", e.target.value)} placeholder="弧目标" />

        {arc.sessions.map((session, si) => (
          <SessionBlock key={`session-${si}`} session={session} ai={ai} si={si} editor={editor} />
        ))}
        <button className="primary-button compact" onClick={() => addSession(ai)}>+ 添加幕</button>
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
    <details open className="curator-subblock">
      <summary className="curator-subsummary">{session.name || `幕 ${si + 1}`}</summary>
      <div className="curator-indent">
        <input className="textarea curator-field" value={session.name} onChange={(e) => updateSession(ai, si, "name", e.target.value)} placeholder="幕名称" />
        <textarea className="textarea small-textarea curator-scene-input" value={session.opening_scene} onChange={(e) => updateSession(ai, si, "opening_scene", e.target.value)} placeholder="开场白 (opening_scene)" />

        {session.anchor_events.map((anchor, ani) => (
          <AnchorBlock key={anchor.id} anchor={anchor} ai={ai} si={si} ani={ani} editor={editor} />
        ))}
        <button className="primary-button compact" onClick={() => addAnchor(ai, si)}>+ 添加锚点</button>
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
    <div className="curator-anchor-card">
      <div className="curator-name-row">
        <input className="textarea" value={anchor.name} onChange={(e) => updateAnchor(ai, si, ani, "name", e.target.value)} placeholder="锚点名称" />
        <input className="textarea curator-priority" value={anchor.priority} onChange={(e) => updateAnchor(ai, si, ani, "priority", parseInt(e.target.value) || 3)} type="number" min={1} max={5} />
      </div>
      <input className="textarea curator-anchor-desc" value={anchor.description} onChange={(e) => updateAnchor(ai, si, ani, "description", e.target.value)} placeholder="描述" />
      <div className="curator-trigger-row">
        <input className="textarea" value={anchor.trigger_conditions?.location ?? ""} onChange={(e) => updateAnchor(ai, si, ani, "trigger_conditions", { ...anchor.trigger_conditions, location: e.target.value || null })} placeholder="地点" />
        <input className="textarea" value={anchor.trigger_conditions?.npc_present ?? ""} onChange={(e) => updateAnchor(ai, si, ani, "trigger_conditions", { ...anchor.trigger_conditions, npc_present: e.target.value || null })} placeholder="NPC" />
        <input className="textarea" value={anchor.trigger_conditions?.item_held ?? ""} onChange={(e) => updateAnchor(ai, si, ani, "trigger_conditions", { ...anchor.trigger_conditions, item_held: e.target.value || null })} placeholder="物品" />
      </div>
    </div>
  );
}
