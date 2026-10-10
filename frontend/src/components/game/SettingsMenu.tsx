"use client";

import Link from "next/link";
import { ChevronDown, History, MapPin, PenTool, Plus, RefreshCw, Settings, Trash2, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import type { GameSession } from "@/components/game/useGameSession";
import { formatSlotTime } from "@/lib/game/format";

export function SettingsMenu({ session }: { session: GameSession }) {
  const {
    sessionId, model, setModel, campaigns, selectedCampaign, handleCampaignChange,
    slots, selectedSlotId, handleSlotChange, handleCreateSlot, handleDeleteSlot, handleNewSession,
  } = session;
  const [isOpen, setIsOpen] = useState(false);
  const [addingSlot, setAddingSlot] = useState(false);
  const [slotName, setSlotName] = useState("");
  const [slotError, setSlotError] = useState("");
  const menuRef = useRef<HTMLDivElement>(null);
  const deleting = useRef(false);
  const [managingSlots, setManagingSlots] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<number | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [deleteError, setDeleteError] = useState("");
  const busy = session.isLoading || !!session.pendingGenerate || deletingId !== null;

  // Reopening the menu must not resurrect a half-typed name.
  useEffect(() => {
    if (isOpen) return;
    setAddingSlot(false);
    setSlotName("");
    setSlotError("");
    setConfirmDelete(null);
    setManagingSlots(false);
    if (!deleting.current) setDeleteError("");
  }, [isOpen]);

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

  const cancelSlot = () => {
    setAddingSlot(false);
    setSlotName("");
    setSlotError("");
  };

  const submitSlot = async () => {
    const name = slotName.trim();
    if (!name) return;
    const error = await handleCreateSlot(name);
    if (error) {
      setSlotError(error);
      return;
    }
    cancelSlot();
  };

  const campaignTitle = (filename?: string | null) => {
    if (!filename) return "未关联战役";
    const found = campaigns.find((campaign) => campaign.filename === filename);
    return found?.title ?? filename;
  };

  const removeSlot = async (id: number) => {
    if (busy || deleting.current || slots.find((slot) => slot.id === id)?.is_active) return;
    deleting.current = true;
    setDeletingId(id);
    setDeleteError("");
    try {
      const error = await handleDeleteSlot(id);
      if (error) setDeleteError(error);
      else setConfirmDelete(null);
    } finally {
      deleting.current = false;
      setDeletingId(null);
    }
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
            <select disabled={busy} id="settings-model" value={model} onChange={(event) => setModel(event.target.value)}>
              <option value="deepseek-v4-flash">deepseek-v4-flash</option>
              <option value="deepseek-reasoner">deepseek-reasoner</option>
            </select>
          </div>

          <div className="settings-field-row">
            <label htmlFor="settings-campaign">战役</label>
            <select
              id="settings-campaign"
              disabled={busy}
              value={selectedCampaign}
              onChange={(event) => handleCampaignChange(event.target.value)}
            >
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
              {addingSlot ? (
                <div className="settings-slot-form">
                  <input
                    aria-label="新存档名称"
                    autoFocus
                    onChange={(event) => setSlotName(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter") {
                        event.preventDefault();
                        void submitSlot();
                      } else if (event.key === "Escape") {
                        // Cancel the form, not the menu behind it.
                        event.stopPropagation();
                        cancelSlot();
                      }
                    }}
                    placeholder="存档名称"
                    value={slotName}
                  />
                  <button onClick={() => void submitSlot()} type="button">确定</button>
                  <button onClick={cancelSlot} type="button">取消</button>
                  {slotError ? <p className="settings-slot-error" role="alert">{slotError}</p> : null}
                </div>
              ) : (
                <div className="settings-slot-control">
                  <select
                    id="settings-slot"
                    disabled={busy}
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
                  <button aria-label="新增存档" className="settings-add-button" disabled={busy} onClick={() => setAddingSlot(true)} type="button">
                    <Plus size={16} />
                  </button>
                </div>
              )}
            </div>
          ) : null}

          {sessionId ? (
            <section className="settings-slot-manager" aria-label="存档管理">
              <button className="settings-link-row" aria-expanded={managingSlots} onClick={() => setManagingSlots((value) => !value)} type="button">
                <Trash2 size={17} /><span>管理存档</span>
              </button>
              {managingSlots ? (
                <div className="settings-slot-list">
                  <p className="settings-slot-hint">删除只移除该存档槽，不会删除会话或共享剧情节点。各会话的活动存档不可删除。</p>
                  {slots.map((slot) => (
                    <div className="settings-slot-entry" data-testid={`slot-${slot.id}`} key={slot.id}>
                      <div><strong>{slot.slot_name}</strong>{slot.is_active ? <span> · 活动中</span> : null}</div>
                      <p>{campaignTitle(slot.campaign_filename)} · A{slot.arc_index + 1}S{slot.session_index + 1}</p>
                      <p>#{slot.id} · {formatSlotTime(slot.last_played)}</p>
                      {confirmDelete === slot.id ? (
                        <div className="settings-delete-confirm">
                          <p>确定删除“{slot.slot_name}”（#{slot.id}）？此存档槽不可恢复。</p>
                          <button disabled={busy || slot.is_active} onClick={() => void removeSlot(slot.id)} type="button">{deletingId === slot.id ? "删除中…" : "确认删除"}</button>
                          <button disabled={deletingId !== null} onClick={() => { setConfirmDelete(null); setDeleteError(""); }} type="button">取消</button>
                        </div>
                      ) : (
                        <button disabled={busy || slot.is_active} onClick={() => { setConfirmDelete(slot.id); setDeleteError(""); }} type="button">删除</button>
                      )}
                    </div>
                  ))}
                  {slots.length === 0 ? <p>无存档</p> : null}
                </div>
              ) : null}
              {deleteError ? <p className="settings-slot-error" role="alert">{deleteError}</p> : null}
            </section>
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
            disabled={busy}
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
