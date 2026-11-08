"use client";

import Link from "next/link";
import { ArrowRight, BookOpen, FolderOpen, History, PenTool, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { createSession, deleteSlot, listCampaigns, listSlots, loadSlot } from "@/lib/api";
import { BUILTIN_CAMPAIGNS, CAMPAIGN_ARTWORK } from "@/lib/game/campaignArtwork";
import { formatSlotTime } from "@/lib/game/format";
import { useModalFocus } from "./useModalFocus";
import type { SavePurpose, SaveSlot, SessionResponse } from "@/types";

const SAVE_PURPOSES: { value: SavePurpose; label: string }[] = [
  { value: "user", label: "游玩存档" },
  { value: "development", label: "开发存档" },
  { value: "test", label: "测试存档" },
  { value: "legacy", label: "历史未分类" },
];

export function StartScreen({ onEnter }: { onEnter: (session: SessionResponse) => void }) {
  const [campaigns, setCampaigns] = useState(BUILTIN_CAMPAIGNS);
  const [selected, setSelected] = useState("default_campaign.json");
  const [turns, setTurns] = useState(50);
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);
  const [error, setError] = useState("");
  const [catalogError, setCatalogError] = useState("");
  const [slots, setSlots] = useState<SaveSlot[]>([]);
  const [slotError, setSlotError] = useState("");
  const [slotsLoading, setSlotsLoading] = useState(false);
  const [savePurpose, setSavePurpose] = useState<SavePurpose>("user");
  const slotRequest = useRef(0);
  const [dialog, setDialog] = useState<"load" | "manage" | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<number | null>(null);
  const closeDialog = () => { if (!inFlight.current) { slotRequest.current++; setDialog(null); setConfirmDelete(null); } };
  const modalRef = useModalFocus(!!dialog, closeDialog);
  const campaign = campaigns.find((item) => item.filename === selected);
  const artwork = CAMPAIGN_ARTWORK[selected] ?? CAMPAIGN_ARTWORK["default_campaign.json"];

  useEffect(() => {
    let cancelled = false;
    listCampaigns().then(({ campaigns: available }) => {
      if (cancelled) return;
      setCampaigns(available);
      if (!available.some((item) => item.filename === "default_campaign.json")) setSelected(available[0]?.filename ?? "");
    }).catch(() => { if (!cancelled) setCatalogError("战役列表暂时无法连接，仍可预览内置档案。开始游戏时将重新连接。"); });
    return () => { cancelled = true; };
  }, []);

  async function refreshSlots(purpose: SavePurpose = savePurpose) {
    const requestId = ++slotRequest.current;
    setSavePurpose(purpose);
    setSlots([]);
    setConfirmDelete(null);
    setSlotsLoading(true);
    setSlotError("");
    try {
      const result = await listSlots(undefined, purpose);
      if (requestId === slotRequest.current) setSlots(result.slots ?? []);
    }
    catch (err) { if (requestId === slotRequest.current) setSlotError(err instanceof Error ? err.message : "读取存档失败"); }
    finally { if (requestId === slotRequest.current) setSlotsLoading(false); }
  }

  function openSlots(mode: "load" | "manage") {
    setDialog(mode);
    setConfirmDelete(null);
    void refreshSlots("user");
  }

  async function enter(slotId?: number) {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setError("");
    setSlotError("");
    try {
      const session = slotId === undefined
        ? await createSession(undefined, { campaignFilename: selected, maxTurnsPerCampaign: turns })
        : (await loadSlot(slotId)).session;
      onEnter(session);
    } catch (err) {
      const message = err instanceof Error ? err.message : "进入游戏失败，请重试。";
      if (slotId === undefined) setError(message); else setSlotError(message);
    } finally { inFlight.current = false; setBusy(false); }
  }

  async function removeSlot(slot: SaveSlot) {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setSlotError("");
    try {
      await deleteSlot(slot.id);
      setSlots((current) => current.filter((item) => item.id !== slot.id));
      setConfirmDelete(null);
    } catch (err) { setSlotError(err instanceof Error ? err.message : "删除失败"); }
    finally { inFlight.current = false; setBusy(false); }
  }

  return (
    <main className="start-screen">
      <div className="start-artwork" aria-hidden="true">
        {Object.entries(CAMPAIGN_ARTWORK).map(([filename, art]) => (
          // Preload all four local assets so changing campaigns never calls image generation.
          // eslint-disable-next-line @next/next/no-img-element
          <img key={filename} src={`/images/campaigns/${art.image}.webp`} alt="" className={art.image === artwork.image ? "is-selected" : ""} />
        ))}
      </div>
      <header className="start-header">
        <Link href="/" className="start-brand" aria-label="Jity 首页">Jity<span>交互叙事档案</span></Link>
        <nav aria-label="主导航">
          <Link href="/dev-log"><History size={15} />开发日志</Link>
          <Link href="/curator"><PenTool size={15} />战役编辑器</Link>
          <button type="button" onClick={() => openSlots("manage")} disabled={busy}><FolderOpen size={15} />存档管理</button>
        </nav>
      </header>
      <section className="start-controls" aria-label="开始游戏设置">
        <p className="start-eyebrow"><span /> YOUR STORY BEGINS HERE</p>
        <p className="start-edition">{artwork.subtitle}</p>
        <h1>{campaign?.title ?? "选择你的战役"}</h1>
        <p className="start-description">{artwork.description}</p>
        <form onSubmit={(event) => { event.preventDefault(); void enter(); }}>
          <label className="start-field" htmlFor="start-campaign"><span>战役档案 <small>CAMPAIGN</small></span>
            <select id="start-campaign" value={selected} disabled={busy} onChange={(event) => { setSelected(event.target.value); setError(""); }}>
              {campaigns.map((item, index) => <option key={item.filename} value={item.filename}>{String(index + 1).padStart(2, "0")} / {item.title}</option>)}
            </select>
          </label>
          <fieldset className="start-length" disabled={busy}>
            <legend>本次游戏长度 <small>回合</small></legend>
            <div className="start-length-options">
              {[20, 30, 50].map((value) => <button key={value} type="button" aria-pressed={turns === value} onClick={() => setTurns(value)}>{value}<span>{value === 20 ? "短篇" : value === 30 ? "标准" : "完整"}</span></button>)}
              <label className="start-custom">自定义<input aria-label="自定义回合数" type="number" min={1} max={50} step={1} required value={Number.isNaN(turns) ? "" : turns} onChange={(event) => setTurns(event.target.valueAsNumber)} /></label>
            </div>
          </fieldset>
          <p className="start-length-hint">默认 50 回合 · 可选 1–50 回合，仅用于新游戏</p>
          <div className="start-actions">
            <button className="start-primary" type="submit" disabled={busy || !selected}><BookOpen size={18} /><span>{busy ? "正在进入…" : "开始游戏"}</span><ArrowRight size={18} /></button>
            <button className="start-secondary" type="button" disabled={busy} onClick={() => openSlots("load")}><FolderOpen size={17} />加载存档</button>
          </div>
          {catalogError ? <p className="start-notice" role="status">{catalogError}</p> : null}
          {error ? <p className="start-error" role="alert">{error}</p> : null}
        </form>
      </section>
      <footer className="start-footer">JITY <span>/</span> 每一次选择，都将留下回响。</footer>
      {dialog ? <div className="start-modal-backdrop" onClick={(event) => { if (event.target === event.currentTarget) closeDialog(); }}>
        <section className="start-modal" ref={modalRef} role="dialog" aria-modal="true" aria-labelledby="save-dialog-title" tabIndex={-1}>
          <div className="start-modal-heading"><div><p className="start-edition">SAVED STORIES</p><h2 id="save-dialog-title">{dialog === "load" ? "加载之前的战役" : "存档管理"}</h2></div><button type="button" aria-label="关闭存档窗口" onClick={closeDialog} disabled={busy}><X size={20} /></button></div>
          <p className="start-save-hint">继续存档将保留原有剧情进度与游戏长度。删除存档需确认，活动存档也可删除。</p>
          <div className="start-save-filters" role="group" aria-label="存档用途">
            {SAVE_PURPOSES.map(({ value, label }) => <button key={value} type="button" aria-pressed={savePurpose === value} disabled={busy} onClick={() => void refreshSlots(value)}>{label}</button>)}
          </div>
          <p className="start-save-hint">旧版本存档保留在“历史未分类”中。</p>
          {slotsLoading ? <p role="status">正在读取存档…</p> : slots.length === 0 && !slotError ? <p className="start-empty">此分类下还没有存档。</p> : null}
          {slotError ? <p className="start-error" role="alert">{slotError}<button type="button" onClick={() => void refreshSlots()} disabled={busy || slotsLoading}>重新读取</button></p> : null}
          <div className="start-save-list">{slots.map((slot) => <article key={slot.id} className="start-save">
            <strong>{slot.slot_name}</strong><p>{campaigns.find((item) => item.filename === slot.campaign_filename)?.title ?? slot.campaign_filename ?? "历史战役"}</p>
            <small>第 {slot.arc_index + 1} 幕 · 第 {slot.session_index + 1} 节 · {formatSlotTime(slot.last_played)}{slot.is_active ? " · 活动存档" : ""}</small>
            <div className="start-save-actions"><button type="button" onClick={() => void enter(slot.id)} disabled={busy || slotsLoading}>继续此存档 <ArrowRight size={14} /></button>
              {confirmDelete === slot.id ? <><span>确定删除？不可恢复。</span><button type="button" onClick={() => void removeSlot(slot)} disabled={busy || slotsLoading}>确认删除</button><button type="button" onClick={() => setConfirmDelete(null)} disabled={busy}>取消</button></> : <button type="button" onClick={() => setConfirmDelete(slot.id)} disabled={busy || slotsLoading}>删除</button>}
            </div>
          </article>)}</div>
        </section>
      </div> : null}
    </main>
  );
}
