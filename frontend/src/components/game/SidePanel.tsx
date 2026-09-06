"use client";

import Link from "next/link";
import { History, Loader2, MapPin, PenTool, RefreshCw, Send } from "lucide-react";

import type { GameSession } from "@/components/game/useGameSession";

export function SidePanel({ session }: { session: GameSession }) {
  const {
    sessionId, model, setModel, campaigns, selectedCampaign, handleCampaignChange,
    slots, selectedSlotId, handleSlotChange, handleCreateSlot,
    action, setAction, isLoading, error, handleGenerate, handleNewSession,
  } = session;

  return (
    <aside className="side-panel">
      <div className="brand-row">
        <div>
          <div className="brand-mark">Jity</div>
          <div className="brand-subtitle">GM scenario console</div>
        </div>
        <div className="brand-actions">
          <Link
            className="icon-button"
            href={sessionId ? `/timeline?session=${sessionId}` : "/timeline"}
            title="发现时间线"
          >
            <MapPin size={17} />
          </Link>
          <Link className="icon-button" href="/curator" title="战役编辑器">
            <PenTool size={17} />
          </Link>
          <Link className="icon-button" href="/dev-log" title="开发日志">
            <History size={17} />
          </Link>
          <button className="icon-button" onClick={handleNewSession} title="新建会话" type="button">
            <RefreshCw size={17} />
          </button>
        </div>
      </div>

      <label className="label" htmlFor="model">
        模型
      </label>
      <select className="select" id="model" value={model} onChange={(event) => setModel(event.target.value)}>
        <option value="deepseek-v4-flash">deepseek-v4-flash</option>
        <option value="deepseek-reasoner">deepseek-reasoner</option>
      </select>

      <label className="label" htmlFor="campaign">
        战役
      </label>
      <select
        className="select"
        id="campaign"
        value={selectedCampaign}
        onChange={(e) => {
          handleCampaignChange(e.target.value);
        }}
      >
        <option value="">自由模式（无预设战役）</option>
        {campaigns.map((c) => (
          <option key={c.filename} value={c.filename}>
            {c.title}（{c.arc_count}弧）
          </option>
        ))}
      </select>

      <label className="label" htmlFor="action">
        玩家行动
      </label>
      {sessionId && (
        <SlotControls
          slots={slots}
          selectedSlotId={selectedSlotId}
          onSlotChange={handleSlotChange}
          onCreateSlot={handleCreateSlot}
        />
      )}
      <textarea
        className="textarea"
        id="action"
        value={action}
        onChange={(event) => setAction(event.target.value)}
        placeholder="输入玩家行动、当前场景或 GM 限制"
      />

      <button className="primary-button" disabled={isLoading || !sessionId} onClick={() => handleGenerate()} type="button">
        {isLoading ? <Loader2 size={17} /> : <Send size={17} />}
        {isLoading ? "生成中" : "生成下一幕"}
      </button>
      {error ? <div className="error">{error}</div> : null}
    </aside>
  );
}

function SlotControls({
  slots,
  selectedSlotId,
  onSlotChange,
  onCreateSlot,
}: {
  slots: GameSession["slots"];
  selectedSlotId: GameSession["selectedSlotId"];
  onSlotChange: (slotId: number) => void;
  onCreateSlot: (name: string) => void;
}) {
  return (
    <div style={{ marginBottom: 8, display: "flex", alignItems: "center", gap: 8, fontSize: "0.85rem" }}>
      <span>存档:</span>
      <select
        value={selectedSlotId}
        onChange={async (e) => {
          await onSlotChange(Number(e.target.value));
        }}
        style={{ padding: "2px 6px" }}
      >
        {slots.length === 0 && <option value="">无存档</option>}
        {slots.length > 0 && selectedSlotId === "" && <option value="">选择存档</option>}
        {slots.map(s => (
          <option key={s.id} value={s.id}>
            {s.slot_name} (A{s.arc_index + 1}S{s.session_index + 1} · T{s.turn_in_session})
          </option>
        ))}
      </select>
      <button onClick={async () => {
        const name = prompt("新存档名称:");
        if (name) onCreateSlot(name);
      }} style={{ padding: "2px 8px" }}>+</button>
    </div>
  );
}
