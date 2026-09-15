import type { StoryOutput } from "@/types";

/** Fixed scripted opening and defaults for the game console. */
export const initialOutput: StoryOutput = {
  narration: `雨是在你下车后三分钟开始变大的。

你拖着那只从婶婶家带来的旧行李箱，站在卡塞尔学院报到处大厅门口。箱轮卡在门槛细缝里，发出一声很丢人的"咔哒"。你低头用力拽了两下，没拽动。

大厅里没人笑。

这反而更可怕。

头顶的水晶吊灯亮得像某种审判现场，光落在黑色大理石地面上，碎成一片片冰冷的白。周围来来往往的学生都穿着深色制服，肩线挺拔，步伐安静，眼神锐利得不像是在上大学，更像是刚从某个不许写进新闻里的军事训练基地出来。

你看见一个男生手里拎着小提琴盒，盒角却露出金属锁扣。另一个女生路过报到台时，袖口下方闪过一枚细小的银色徽章。投影屏正在滚动新生名单，你的名字混在一串英文、编号和血红色的校徽之间，像一只误入狼群的土狗。

你咽了口唾沫。

你本来想找个角落站着，先装作自己只是来送外卖的。可就在这时，身后有人轻轻拍了拍你的肩膀。

你回头，看见一个红发女孩站在雨幕和大厅灯光交界的地方。她的校服外套随意搭在肩上，手里捏着一张临时通行卡，卡面上的火漆纹路像刚被点燃过。

她看了看你，又看了看你那个旧行李箱。

她的表情像是在确认一件快递有没有送错地址。`,
  dialogue: [
    {
      speaker: "诺诺",
      text: `路明非对吧？

古德里安教授让我来接你。

不过说实话，你看起来比档案里还要……朴素一点。

没人告诉过你，这里不是普通大学吗？`,
    },
  ],
  scene_prompt: "dark gothic academy registration hall, nervous freshman, crystal chandelier",
  sanity_delta: 0,
  health_delta: 0,
  options: [
    `愣住两秒，然后硬着头皮打招呼："学姐好……那个，这里到底有什么不普通的？"`,
    `下意识后退半步，抓紧行李箱拉杆："等等，你怎么知道我的名字？这是什么整蛊节目吗？"`,
    `试图挤出个笑脸，但声音有点抖："照片？什么照片？我那张高考准考证上的照片可丑了……"`,
  ],
  game_over: false,
  game_over_reason: "",
  current_location: "卡塞尔学院报到处大厅",
};

export const DEFAULT_STORY_STYLE = "黑暗学院奇幻，带一点黑色幽默，强调 NPC 反应。";
export const DEFAULT_CONSTRAINTS = "关键 NPC 不能突然死亡；不要跳出当前入学调查。";
export const CAMPAIGN_STORY_STYLE = "延续当前战役的叙事风格、时代背景和人物处境。";
export const CAMPAIGN_CONSTRAINTS = "遵循当前战役及本幕设定，承接最近剧情和玩家行动，保持人物与物品连续。";
export const loadingOutput: StoryOutput = {
  narration: "正在读取当前剧情……",
  dialogue: [], scene_prompt: "", options: [],
  sanity_delta: 0, health_delta: 0,
  game_over: false, game_over_reason: "", current_location: "",
};
export const INITIAL_ACTION = `愣住两秒，然后硬着头皮打招呼："学姐好……那个，这里到底有什么不普通的？"`;
export const SLOT_DEFAULT = "default" as const;
export const ENTRY_ACTION = "（入场）环顾四周，了解当前处境。";
export const STATE_COMMIT_DELAY = 100;
