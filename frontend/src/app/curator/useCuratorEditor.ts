"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { generateCampaign, generateFromNovel, getCampaign, listCampaigns, saveCampaign } from "@/lib/api";
import type { CampaignListItem, CampaignSchema } from "@/types";
import { useArcEditing } from "@/app/curator/useArcEditing";

export function emptyCampaign(): CampaignSchema {
  return {
    version: 3,
    title: "新战役",
    core_conflict: "",
    arcs: [],
    constraints: "",
    starting_state: {},
  };
}

export function useCuratorEditor() {
  const [campaigns, setCampaigns] = useState<CampaignListItem[]>([]);
  const [campaign, setCampaign] = useState<CampaignSchema>(emptyCampaign());
  const [filename, setFilename] = useState("new_campaign.json");
  const [genPrompt, setGenPrompt] = useState("");
  const [generating, setGenerating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState("");
  const [novelUploading, setNovelUploading] = useState(false);
  const [novelErrors, setNovelErrors] = useState<string[]>([]);

  useEffect(() => {
    listCampaigns().then((r) => setCampaigns(r.campaigns ?? [])).catch((err) => console.error("listCampaigns failed:", err));
  }, []);

  const handleLoad = useCallback((fname: string) => {
    getCampaign(fname).then((r) => {
      setCampaign(r.campaign as CampaignSchema);
      setFilename(fname);
    }).catch(() => setStatus("加载失败"));
  }, []);

  const handleNovelUpload = useCallback(async (file: File) => {
    setNovelUploading(true);
    setNovelErrors([]);
    setStatus("从小说生成战役中…");
    try {
      const data = await generateFromNovel(file);
      if (data.campaign) {
        setCampaign(data.campaign as CampaignSchema);
        setFilename(file.name.replace(/\.\w+$/, "") + "_campaign.json");
        setStatus("战役已生成，请审核后保存");
      }
      if (data.extraction_errors?.length) {
        setNovelErrors(data.extraction_errors);
      }
    } catch (e: unknown) {
      setStatus("生成失败: " + (e instanceof Error ? e.message : String(e)));
    } finally {
      setNovelUploading(false);
    }
  }, []);

  const handleGenerate = useCallback(async () => {
    if (!genPrompt.trim()) return;
    setGenerating(true);
    setStatus("生成中…");
    try {
      const data = await generateCampaign(genPrompt);
      if (data.campaign) {
        setCampaign(data.campaign as CampaignSchema);
        setFilename(data.saved_to?.split("/").pop() ?? "generated.json");
        setStatus("生成完成！请审查后保存。");
        listCampaigns().then((r) => setCampaigns(r.campaigns ?? [])).catch((err) => console.error("listCampaigns refresh failed:", err));
      } else {
        setStatus("生成失败：" + (data.detail ?? "未知错误"));
      }
    } catch (e) {
      setStatus("请求失败：" + (e instanceof Error ? e.message : String(e)));
    }
    setGenerating(false);
  }, [genPrompt]);

  const handleSave = useCallback(async () => {
    setSaving(true);
    setStatus("保存中…");
    try {
      const data = await saveCampaign(filename, campaign);
      if (data.status === "saved") {
        setStatus("已保存！");
        listCampaigns().then((r) => setCampaigns(r.campaigns ?? [])).catch((err) => console.error("listCampaigns refresh failed:", err));
      } else {
        setStatus("保存失败：" + (data.detail ?? ""));
      }
    } catch (e) {
      setStatus("请求失败：" + (e instanceof Error ? e.message : String(e)));
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

  // Memoize review panel computations
  const reviewStats = useMemo(() => {
    const totalSessions = campaign.arcs.reduce((s, a) => s + a.sessions.length, 0);
    const totalAnchors = campaign.arcs.reduce((s, a) => s + a.sessions.reduce((ss, ses) => ss + ses.anchor_events.length, 0), 0);
    const allAnchors = campaign.arcs.flatMap((a) => a.sessions.flatMap((s) => s.anchor_events));
    return { totalSessions, totalAnchors, allAnchors };
  }, [campaign]);

  const arcEditing = useArcEditing(setCampaign);

  return {
    ...arcEditing,
    campaigns, campaign, filename, setFilename, genPrompt, setGenPrompt,
    generating, saving, status, novelUploading, novelErrors, reviewStats,
    handleLoad, handleNovelUpload, handleGenerate, handleSave, handleDownload,
  };
}

export type CuratorEditor = ReturnType<typeof useCuratorEditor>;
