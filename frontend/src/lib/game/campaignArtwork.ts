import type { CampaignListItem } from "@/types";

export const CAMPAIGN_ARTWORK: Record<string, { image: string; subtitle: string; description: string }> = {
  "default_campaign.json": { image: "cassell", subtitle: "CASSELL COLLEGE · ADMISSION ARCHIVE", description: "世界树下，一封录取通知书，开启属于你的命运。" },
  "龙族Ⅰ_火之晨曦_campaign.json": { image: "bronze", subtitle: "DRAGON RAJA I · DAWN OF FIRE", description: "青铜城深处，古老的火焰仍在等待一个答案。" },
  "龙族Ⅱ_悼亡者之瞳_campaign.json": { image: "rain", subtitle: "DRAGON RAJA II · EYES OF THE MOURNER", description: "穿过雨夜的都市，走向尼伯龙根的另一端。" },
  "龙族Ⅲ_黑月之潮_campaign.json": { image: "tokyo", subtitle: "DRAGON RAJA III · BLACK MOON TIDE", description: "樱花落入黑潮，在东京的尽头改写命运。" },
};

// A usable catalog while loading/offline; the server remains authoritative.
export const BUILTIN_CAMPAIGNS: CampaignListItem[] = [
  { filename: "default_campaign.json", title: "卡塞尔入学档案", version: 4, arc_count: 0 },
  { filename: "龙族Ⅰ_火之晨曦_campaign.json", title: "龙族·火之晨曦", version: 4, arc_count: 0 },
  { filename: "龙族Ⅱ_悼亡者之瞳_campaign.json", title: "龙族Ⅱ·悼亡者之瞳", version: 4, arc_count: 0 },
  { filename: "龙族Ⅲ_黑月之潮_campaign.json", title: "龙族Ⅲ·黑月之潮", version: 4, arc_count: 0 },
];
