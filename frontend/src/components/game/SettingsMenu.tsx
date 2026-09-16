"use client";

import Link from "next/link";
import { ChevronDown, History, MapPin, PenTool, Plus, RefreshCw, Settings, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import type { GameSession } from "@/components/game/useGameSession";
import { formatSlotTime } from "@/lib/game/format";

export function SettingsMenu({ session }: { session: GameSession }) {
  const {
    sessionId, model, setModel, campaigns, selectedCampaign, handleCampaignChange,
    slots, selectedSlotId, handleSlotChange, handleCreateSlot, handleNewSession,
  } = session;
  const [isOpen, setIsOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isOpen) return;

    const closeOnOutsideClick = (event: MouseEvent) => {
      if (!menuRef.current?.contains(event.target as Node)) setIsOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setIsOpen(false);
    };

    document.addEventListener("mousedown", closeOnOutsideClick);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("mousedown", closeOnOutsideClick);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [isOpen]);

  const createSlot = () => {
    const name = window.prompt("新存档名称:");
    if (name?.trim()) handleCreateSlot(name.trim());
  };

  const campaignTitle = (filename?: string | null) => {
    if (!filename) return "自由模式";
    const found = campaigns.find((campaign) => campaign.filename === filename);
    return found?.title ?? filename;
  };

  return (
    <div className="settings-menu" ref={menuRef}>
      <button
        aria-expanded={isOpen}
        aria-haspopup="menu"
        className={`settings-trigger${isOpen ? " is-open" : ""}`}
        onClick={() => setIsOpen((open) => !open)}
        type="button"
      >
        {isOpen ? <X size={17} /> : <Settings size={17} />}
        <span>设置</span>
        <ChevronDown className="settings-chevron" size={15} />
      </button>

      {isOpen ? (
        <div aria-label="游戏设置" className="settings-dropdown" role="menu">
          <div className="settings-field-row">
            <label htmlFor="settings-model">模型</label>
            <select disabled={session.isLoading || !!session.pendingGenerate} id="settings-model" value={model} onChange={(event) => setModel(event.target.value)}>
              <option value="deepseek-v4-flash">deepseek-v4-flash</option>
              <option value="deepseek-reasoner">deepseek-reasoner</option>
            </select>
          </div>

          <div className="settings-field-row">
            <label htmlFor="settings-campaign">战役</label>
            <select
              id="settings-campaign"
              disabled={session.isLoading || !!session.pendingGenerate}
              value={selectedCampaign}
              onChange={(event) => handleCampaignChange(event.target.value)}
            >
              <option value="">自由模式（无预设战役）</option>
              {campaigns.map((campaign) => (
                <option key={campaign.filename} value={campaign.filename}>
                  {campaign.title}（{campaign.arc_count}弧）
                </option>
              ))}
            </select>
          </div>

          {sessionId ? (
            <div className="settings-field-row">
              <label htmlFor="settings-slot">存档</label>
              <div className="settings-slot-control">
                <select
                  id="settings-slot"
                  disabled={session.isLoading || !!session.pendingGenerate}
                  value={selectedSlotId}
                  onChange={(event) => handleSlotChange(Number(event.target.value))}
                >
                  {slots.length === 0 ? <option value="">无存档</option> : null}
                  {slots.length > 0 && selectedSlotId === "" ? <option value="">选择存档</option> : null}
                  {slots.map((slot) => (
                    <option key={slot.id} value={slot.id}>
                      {slot.slot_name} · {campaignTitle(slot.campaign_filename)} · A{slot.arc_index + 1}S{slot.session_index + 1} · {formatSlotTime(slot.last_played)}
                    </option>
                  ))}
                </select>
                <button aria-label="新增存档" className="settings-add-button" onClick={createSlot} type="button">
                  <Plus size={16} />
                </button>
              </div>
            </div>
          ) : null}

          <div className="settings-divider" />

          <Link
            className="settings-link-row"
            href={session.autoPlay.enabled ? session.autoPlay.timelineUrl : (sessionId ? `/timeline?session=${sessionId}` : "/timeline")}
            target={session.autoPlay.enabled ? "_blank" : undefined}
          >
            <MapPin size={17} />
            <span>{session.autoPlay.enabled ? "发现时间线（实时）" : "发现时间线"}</span>
          </Link>
          <Link className="settings-link-row" href="/curator">
            <PenTool size={17} />
            <span>战役编辑器</span>
          </Link>
          <Link className="settings-link-row" href="/dev-log">
            <History size={17} />
            <span>开发日志</span>
          </Link>

          <div className="settings-divider" />

          <button
            className="settings-link-row settings-new-session"
            disabled={session.isLoading || !!session.pendingGenerate}
            onClick={() => {
              setIsOpen(false);
              handleNewSession();
            }}
            type="button"
          >
            <RefreshCw size={17} />
            <span>新建会话</span>
          </button>
        </div>
      ) : null}
    </div>
  );
}
