from __future__ import annotations

import json
import re
import time
from typing import Any

import httpx

from app.config import Settings
from app.schemas import StoryOutput


class MissingAPIKeyError(RuntimeError):
    pass


class LLMClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def generate(
        self,
        prompt: str,
        model: str | None = None,
    ) -> tuple[StoryOutput, int]:
        if not self.settings.deepseek_api_key:
            raise MissingAPIKeyError("AI 生成需要配置 backend/.env 里的 DEEPSEEK_API_KEY。固定开场结束后不会再使用本地兜底剧情。")

        started = time.perf_counter()
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{self.settings.llm_base_url.rstrip('/')}/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.settings.deepseek_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model or self.settings.llm_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.35,
                    "max_tokens": 1200,
                },
            )
        latency_ms = int((time.perf_counter() - started) * 1000)
        response.raise_for_status()
        raw_text = response.json()["choices"][0]["message"]["content"]
        return StoryOutput.model_validate(self._normalize_output(self._parse_json(raw_text))), latency_ms

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any]:
        cleaned = re.sub(r"<think>[\s\S]*?</think>", "", text).strip()
        cleaned = cleaned.replace("```json", "").replace("```", "").strip()
        return json.loads(cleaned)

    @staticmethod
    def _normalize_output(payload: dict[str, Any]) -> dict[str, Any]:
        payload = dict(payload)
        payload["items_gained"] = LLMClient._normalize_named_objects(payload.get("items_gained", []), "description")
        payload["items_lost"] = LLMClient._normalize_named_objects(payload.get("items_lost", []), "description")
        payload["npcs_encountered"] = LLMClient._normalize_named_objects(payload.get("npcs_encountered", []), "notes")
        payload["quests_updated"] = LLMClient._normalize_named_objects(payload.get("quests_updated", []), "description")
        return payload

    @staticmethod
    def _normalize_named_objects(items: Any, detail_key: str) -> list[dict[str, Any]]:
        if not isinstance(items, list):
            return []

        normalized: list[dict[str, Any]] = []
        for item in items:
            if isinstance(item, dict):
                normalized.append(item)
            elif isinstance(item, str) and item.strip():
                normalized.append({"name": item.strip(), detail_key: "AI 生成记录"})
        return normalized

    @staticmethod
    def scripted_output(action: str, state: dict[str, Any]) -> StoryOutput | None:
        normalized_action = action.strip()
        turn = int(state.get("turn", 0))

        if turn == 0 and ("整蛊节目" in normalized_action):
            return LLMClient._fixed_story(
                narration="""
你下意识后退了半步。

行李箱终于从门槛缝里弹了出来，轮子在大理石地面上滑出一小段距离，撞到你的鞋跟。这个声音在大厅里显得特别清脆，像某种仪式开始前不小心敲响的铃。

诺诺挑了挑眉，像是很满意你终于开始怀疑现实。

她没有解释，只是把那张临时通行卡按进你手里。

卡片触到掌心的一瞬间，你感觉指腹被什么东西轻轻烫了一下。卡面上红色火漆般的纹路慢慢亮起，像某种活物在皮肤下面睁开眼睛。

远处的报到台后，投影屏闪烁了一下。

你的名字旁边出现了一枚细小的红色标记。

大厅外，雨声贴着彩窗滑落。那些彩色玻璃上画着古老的龙、长枪、燃烧的树和不知名的王冠。灯光穿过它们，落在你临时通行卡的边缘，像一圈很薄的血色。

你站在卡塞尔学院的入口。

手里的卡还带着火漆的温度。

下一句话，将决定这场入学调查从哪里开始。

状态更新
- 获得物品：临时通行卡
- 当前异常：通行卡发热
- 当前线索：新生名单上你的名字旁边出现红色标记
- 当前氛围：学院大厅 / 雨夜 / 报到异常
""",
                dialogue=[
                    ("诺诺", "整蛊节目可没有这么贵的水晶吊灯。\n\n欢迎来到卡塞尔，新生。\n\n这里的普通人通常活不过报到流程。"),
                    ("芬格尔", "师弟，别怕。\n\n这里不是整蛊节目。\n\n这里比整蛊节目贵多了，也危险多了。\n\n而且整蛊节目一般不会让你签生死免责协议。\n\n至少不会用拉丁文写。"),
                ],
                scene_prompt="gothic academy registration hall, red access card, rainy night",
                options=LLMClient._first_investigation_options(),
                current_location="卡塞尔学院报到大厅",
                items_gained=[{"name": "临时通行卡", "description": "卡面火漆纹路正在发热"}],
                npcs_encountered=LLMClient._opening_npcs(),
            )

        if turn == 0 and ("照片" in normalized_action):
            return LLMClient._fixed_story(
                narration="""
你本来只是想缓和一下气氛。

但话说出口以后，你才发现这个大厅里的空气似乎并不适合讲冷笑话。水晶吊灯下，每个人都像是被某种看不见的纪律校准过，连停顿都显得很专业。

诺诺笑了一声。

不是那种被逗乐的笑，更像是终于确认档案里的某个倒霉名字和现实中这个拖着旧箱子的男生对上了号。

她伸手一拽你的袖口，把你往报到台方向带去。你的行李箱在身后歪歪扭扭地跟着，轮子发出抗议般的声音。

周围穿深色制服的学生纷纷让开一条路。

不是礼貌地让。

更像是他们提前知道这条路上会发生点什么，没人愿意站得太近。

报到台后的投影屏正在刷新新生资料。照片栏里一闪而过的是你那张确实很丑的证件照，脸白得像被闪光灯当场击毙。下一秒，照片右下角浮现出一个红色边框。

边框里没有文字。

只有一枚像燃烧鳞片一样的标记。

你手心一热。

诺诺把一张临时通行卡塞给你。卡面上的火漆纹路微微发烫。

大厅外的雨声贴着彩窗滑落，你站在卡塞尔学院的入口，临时通行卡还带着火漆的温度。

下一句话，将决定这场入学调查从哪里开始。

状态更新
- 获得物品：临时通行卡
- 当前异常：证件照右下角出现红色边框
- 当前线索：燃烧鳞片状标记
- 当前关系：诺诺似乎知道你的档案内容，芬格尔正在用嘴降低你的求生欲
""",
                dialogue=[
                    ("诺诺", "放心，照片丑不是重点。\n\n重点是你本人看起来更适合被写进事故报告。\n\n而且是那种标题很长、结尾很短的事故报告。"),
                    ("芬格尔", "我作证，卡塞尔的照片系统很公平。\n\n大家都丑得各有特色。\n\n师弟你属于那种“还没入学就已经很像受害者”的风格，辨识度很高。"),
                ],
                scene_prompt="academy registration desk, freshman photo, red scale mark",
                options=[
                    "询问学院给出的三个预备任务：“事故报告先放一边……我到底要办什么入学手续？”",
                    "检查临时通行卡上的异常标记：“这张卡和投影屏上的红色标记是同一个东西吗？”",
                    "先观察大厅里执行部学生的动向：“为什么我一靠近报到台，他们就开始调整站位？”",
                ],
                current_location="卡塞尔学院报到大厅",
                items_gained=[{"name": "临时通行卡", "description": "卡面火漆纹路正在发热"}],
                npcs_encountered=LLMClient._opening_npcs(),
            )

        if turn == 0 and ("学姐好" in normalized_action or "不普通" in normalized_action):
            return LLMClient._fixed_story(
                narration="""
你决定先礼貌一点。

毕竟人在陌生环境里，礼貌通常是最便宜的护身符。虽然你怀疑在这个大厅里，护身符可能需要镀银、刻符文，还要经过校董会批准。

诺诺没有立刻回答。

她只是伸手替你把行李箱推离大厅中央。这个动作看起来很随意，却刚好让你避开了一束从穹顶落下的白光。下一秒，那束光照在你原本站着的位置，地面上的校徽纹路亮了一下，像扫描仪扫过一具嫌疑人的骨头。

你愣住。

诺诺却像什么都没发生，只是抬了抬下巴，示意你看报到台后的投影屏。

屏幕正在刷新新生名单。

你的名字在最下方出现，字体很普通，编号很普通，甚至连照片都普通得让人想替它道歉。

可你的名字旁边，多了一枚细小的红色标记。

那标记像一片烧红的鳞，贴在名字右侧，安静得令人不舒服。

就在它出现的那一刻，你手中的临时通行卡开始发热。

大厅里的雨声贴着彩窗滑落。

你站在卡塞尔学院的入口，临时通行卡还带着火漆的温度。

下一句话，将决定这场入学调查从哪里开始。

状态更新
- 获得物品：临时通行卡
- 当前异常：名字旁边出现红色标记
- 当前线索：大厅地面疑似存在扫描机制
- 当前风险：你可能被学院系统列为特殊新生
""",
                dialogue=[
                    ("诺诺", "不普通的地方很多。\n\n比如这里的规则通常写在事故报告里。\n\n比如新生报到有时候会触发警报。\n\n再比如——\n\n你已经被系统提前标出来了。"),
                    ("芬格尔", "师弟，我建议先深呼吸。\n\n卡塞尔的欢迎仪式一般不会致命。\n\n至少第一分钟不会。\n\n当然，学校对“第一分钟”的定义可能和正常人不太一样。"),
                ],
                scene_prompt="gothic academy hall, red mark on freshman list, scanning light",
                options=[
                    "询问学院给出的三个预备任务：“如果我已经被标出来了，那我现在应该先完成什么？”",
                    "检查临时通行卡上的异常标记：“这东西是在识别我，还是在警告别人离我远点？”",
                    "先观察大厅里执行部学生的动向：“那些学生是在保护大厅，还是在监视我？”",
                ],
                current_location="卡塞尔学院报到大厅",
                items_gained=[{"name": "临时通行卡", "description": "卡面火漆纹路正在发热"}],
                npcs_encountered=LLMClient._opening_npcs(),
            )

        if turn == 0 and ("报到大厅" in normalized_action or "报到处" in normalized_action or "走进" in normalized_action or "刷卡" in normalized_action):
            return LLMClient._fixed_story(
                narration="""
你决定先进去。

毕竟站在门口淋雨也不能解决问题，最多只能让你看起来更像一只被快递错寄到贵族学校的落水狗。

报到大厅的雨声贴着彩窗滑落。

你穿过主楼入口，临时通行卡在门禁上轻轻一震。那不是普通的电子识别声，更像有什么看不见的东西在你耳边低声确认了一遍你的名字。

门禁灯由白转红，又从红转回白。

这个过程只持续了半秒。

但你看见大厅里至少有三个人同时停下了动作。

一个正在整理新生资料的学生合上文件夹。

一个靠在柱子旁的男生把手伸进外套内侧。

还有一个站在二楼栏杆后的女生低头看向你，眼神像瞄准镜里的冷光。

诺诺站在报到台旁，似乎早就知道你会进来。她抱着手臂，红发在灯光下像一小团不肯熄灭的火。

芬格尔则从一堆新生资料后探出头，嘴里还叼着半根不知道从哪里来的薯条。他看见你，眼睛一亮，像终于等到了可以分摊厄运的人。

报到台后的投影屏刷新。

你的名字出现。

名字旁边，亮起一枚细小的红色标记。

你手里的临时通行卡微微发烫，像有人隔着纸片握住了你的手。

状态更新
- 当前位置：卡塞尔学院报到大厅
- 当前异常：门禁识别短暂变红
- 当前线索：二楼有人观察你
- 当前风险：执行部学生疑似进入戒备状态
- 获得物品：临时通行卡
""",
                dialogue=[
                    ("诺诺", "说吧，新生。\n\n你打算先相信规则，还是先相信直觉？\n\n友情提醒，在卡塞尔，两个都信的人通常会死得比较有层次感。"),
                    ("芬格尔", "我建议相信我。\n\n虽然这个建议本身风险很高。\n\n但从性价比来看，我至少比门禁系统像个人。"),
                ],
                scene_prompt="rainy gothic academy registration hall, red gate light, stained glass",
                options=LLMClient._first_investigation_options(),
                current_location="卡塞尔学院报到大厅",
                items_gained=[{"name": "临时通行卡", "description": "门禁识别时短暂变红"}],
                npcs_encountered=LLMClient._opening_npcs(),
            )

        if turn <= 1 and ("三个预备任务" in normalized_action or "入学手续" in normalized_action or "新生到底要干什么" in normalized_action):
            return LLMClient._fixed_story(
                narration="""
你决定先问清楚规则。

这是一个非常普通人的决定。普通人遇到陌生系统时，总觉得只要把说明书读完，就能安全通关。

卡塞尔学院显然不太赞同这种天真的生活态度。

诺诺从报到台上抽出一张折叠的任务单，纸张边缘带着淡淡的焦痕。她把任务单摊开，压在你面前。上面没有“欢迎新生”这种温暖废话，只有三行任务编号、地点和简短说明。

芬格尔凑过来看了一眼，表情从幸灾乐祸变成了更高级的幸灾乐祸。

你发现任务单右上角盖着一个红色印章：

临时评估：S级观察对象。

你不确定这个“S”是优秀的意思，还是“死得比较快”的意思。

三个预备任务

任务一：档案室核验
地点：主楼地下二层，旧档案室
任务说明：前往旧档案室，核验你的个人档案是否完整。
异常提示：你的纸质档案在三分钟前被人取走，但系统显示取件人是你本人。
可能方向：身份伪造、学院内部人员、隐藏档案、过去经历异常。

任务二：钟楼听证
地点：钟楼一层，临时听证室
任务说明：参加新生能力评估前的简短听证。
异常提示：听证名单上，你的名字被手写添加了两遍。第二遍的笔迹还没有干。
可能方向：教授团调查、能力测试、血统疑点、有人临时插手你的入学流程。

任务三：便利店取件
地点：校内24小时便利店
任务说明：取回一份寄给你的新生包裹。
异常提示：包裹寄件时间显示为三年前，收件人备注只有一句话：“别让他一个人去钟楼。”
可能方向：轻喜剧日常、隐藏警告、神秘寄件人、与普通物件相关的情绪线索。

状态更新
- 解锁任务：档案室核验
- 解锁任务：钟楼听证
- 解锁任务：便利店取件
- 当前主线疑点：有人正在干预你的入学流程
- 当前特殊标签：S级观察对象
""",
                dialogue=[
                    ("诺诺", "学院给了你三个预备任务。\n\n理论上，它们只是入学流程的一部分。\n\n实际上，它们通常会筛掉一批不适合活到开学典礼的人。\n\n三个任务都能开始调查。\n\n档案室最危险，钟楼最正式，便利店看起来最蠢。\n\n但在卡塞尔，看起来最蠢的那个经常最要命。"),
                    ("芬格尔", "师弟，你可以乐观点。\n\n能被筛掉，说明你至少参与过。\n\n很多人连任务单都摸不到，门禁那关就被送去心理辅导室喝热可可了。\n\n虽然热可可里可能也有镇定剂。\n\n我投便利店一票。\n\n不是因为安全。\n\n是因为那里有泡面。\n\n人在面对未知恐怖的时候，至少应该先吃点热的。"),
                ],
                scene_prompt="burned mission sheet, academy registration desk, red S rank stamp",
                options=[
                    "前往旧档案室，调查被取走的个人档案。",
                    "前往钟楼，参加临时听证。",
                    "前往便利店，取回三年前寄出的新生包裹。",
                    "追问诺诺：为什么我是“S级观察对象”？",
                    "询问芬格尔：哪个任务最适合活着回来？",
                ],
                current_location="卡塞尔学院报到大厅",
                quests_updated=[
                    {"name": "档案室核验", "status": "已解锁"},
                    {"name": "钟楼听证", "status": "已解锁"},
                    {"name": "便利店取件", "status": "已解锁"},
                ],
            )

        if turn <= 1 and ("检查临时通行卡" in normalized_action or "通行卡" in normalized_action or "发烫" in normalized_action or "红色标记" in normalized_action):
            return LLMClient._fixed_story(
                narration="""
你低头看向手里的临时通行卡。

卡片比普通校园卡略重，边缘镶着一圈暗金色细线。正面是你的名字、临时编号和卡塞尔学院的校徽。背面原本应该是磁条的位置，却嵌着一枚很细的红色纹路。

那纹路不是印上去的。

它像是从卡片内部慢慢浮出来的，细而弯曲，像一枚烧红的鳞片，也像一道还没愈合的伤口。

你用拇指轻轻擦了一下。

卡面发出极轻的“嗡”声。

下一秒，你的旧手机突然震动。

屏幕亮起。

没有号码，没有发件人。

只有一条短信。

不要把卡交给第一个向你索要它的人。
哪怕那个人穿着校服。

你抬头。

大厅里穿校服的人很多。

这句话等于什么都没说，又像是什么都说了。

可调查细节

细节一：卡面温度
卡片一直在发热，但温度没有继续升高。像是在等待某个特定地点或人物靠近。

细节二：红色鳞片纹路
纹路和投影屏上你名字旁边的红色标记相似。可能代表某种权限、警告，或监控标签。

细节三：旧手机短信
短信没有发送号码。你的手机明明已经欠费三天，却仍然收到了消息。

细节四：隐藏编号
你把卡片斜对着吊灯时，看见暗金边缘里浮出一串极浅的编号：
L-13 / TEMP / OBSERVE

状态更新
- 当前物品：临时通行卡
- 发现隐藏编号：L-13 / TEMP / OBSERVE
- 当前异常：旧手机收到匿名短信
- 当前警告：不要把卡交给第一个索要它的人
- 当前疑点：卡片可能并非普通门禁卡，而是观察装置或临时封印物
""",
                dialogue=[
                    ("诺诺", "别乱擦。\n\n那不是普通标记。\n\n至少不是给普通新生用的。"),
                    ("芬格尔", "师弟，恭喜你。\n\n一般新生的临时卡只负责开门、刷饭、欠费。\n\n你的这张看起来还兼职遗物、警报器和死亡预告。\n\n性价比非常高。"),
                ],
                scene_prompt="red marked access card, anonymous phone message, academy hall",
                options=[
                    "询问诺诺：这张卡到底是什么？",
                    "把短信内容给芬格尔看，观察他的反应。",
                    "检查大厅里是否有人正在盯着这张卡。",
                    "尝试用通行卡靠近报到台或门禁，看它是否再次发热。",
                    "暂时把卡藏进校服外套内侧，避免被人看见。",
                ],
                current_location="卡塞尔学院报到大厅",
                items_gained=[{"name": "临时通行卡", "description": "隐藏编号 L-13 / TEMP / OBSERVE"}],
            )

        if turn <= 1 and ("执行部" in normalized_action or "观察大厅" in normalized_action or "监视" in normalized_action or "站位" in normalized_action):
            return LLMClient._fixed_story(
                narration="""
你没有急着继续问。

人在完全不知道规则的时候，最好先看看别人怎么动。

这是你多年在网吧、课堂和亲戚饭局里总结出来的生存经验。虽然这些经验大概率无法应对卡塞尔学院，但至少能让你显得没有那么像待宰的鹅。

你假装整理行李箱拉杆，视线却从大厅边缘扫过去。

柱子旁站着两个穿深色制服的学生。他们没有交谈，目光却不断在报到台、二楼栏杆和大厅入口之间移动。左边那人袖口绣着银色暗纹，右手始终停在外套内侧。右边那人耳后贴着一个小型通讯器，红点每隔三秒闪一次。

二楼栏杆后，有人翻动文件夹。

报到台后方，原本正在整理新生资料的学生突然把你的那一页抽了出来，塞进一个黑色信封。

你看见信封封口处有蜡印。

和你临时通行卡上的火漆纹路很像。

就在这时，大厅角落的广播轻轻响了一下。

没有音乐。

只有一段短促的电流声。

然后，一个冷静的女声从广播里传出：

“执行部临时调度，编号L-13已进入大厅。保持观察，不得主动接触。”

大厅重新安静下来。

所有人都假装没有听见。

这比他们同时看向你更糟糕。

可观察到的线索

线索一：执行部站位
大厅内至少有四名执行部学生。他们分别控制入口、报到台、二楼视野和侧门通道。

线索二：黑色信封
你的新生资料被单独抽出，装入黑色信封。信封蜡印与临时通行卡上的火漆纹路相似。

线索三：广播编号
广播称你为：编号L-13。与临时通行卡隐藏编号可能一致。

线索四：不得主动接触
执行部目前只被允许观察你。说明他们要么在等待命令，要么在等待你触发某个条件。

状态更新
- 当前编号：L-13
- 当前风险：执行部正在观察你
- 当前线索：黑色信封、广播调度、四点站位
- 当前推测：你是某个临时监控或评估对象
- 当前优势：你已经意识到自己被监视
""",
                dialogue=[
                    ("诺诺", "你观察力还不错。\n\n至少比看起来强一点。\n\n不过在卡塞尔，发现别人盯着你，不代表你赢了。\n\n只代表他们懒得藏了。"),
                    ("芬格尔", "师弟，我有一个好消息和一个坏消息。\n\n好消息是，他们说不得主动接触。\n\n坏消息是，卡塞尔对“主动”的定义非常灵活。\n\n比如你自己摔过去，就不算他们主动。"),
                ],
                scene_prompt="academy security students observing, black envelope, gothic hall",
                options=[
                    "靠近报到台，要求查看那个黑色信封。",
                    "询问诺诺：L-13是什么意思？",
                    "假装没听见广播，反向观察二楼栏杆后的人。",
                    "向芬格尔打听执行部在新生报到时通常负责什么。",
                    "故意远离报到台，测试执行部是否会改变站位。",
                ],
                current_location="卡塞尔学院报到大厅",
            )

        if "前往旧档案室" in normalized_action or "调查被取走" in normalized_action or "档案室核验" in normalized_action:
            return LLMClient._fixed_story(
                narration="""
旧档案室在主楼地下二层。

电梯门合上的时候，报到大厅的灯光被切成一条细线，最后消失在你眼前。电梯里只有你、诺诺、芬格尔，还有你手里那张越来越热的临时通行卡。

地下二层没有雨声。

这里只有通风管道里低低的风声，像有人在很远的地方翻书。

档案室门口挂着一块铜牌：

学生档案封存区。

铜牌下面还有一行更小的字：

未经许可调阅者，后果自负。

芬格尔盯着那行字看了几秒。
""",
                dialogue=[
                    ("芬格尔", "师弟，你发现没有？\n\n学校连威胁人都很有文化。\n\n不像我，我一般只会说“快跑”。"),
                    ("诺诺", "准备好。\n\n如果系统显示档案是你自己取走的，那里面至少有一个人在冒充你。\n\n也可能是某个东西。"),
                ],
                scene_prompt="underground archive door, brass sign, dim academy corridor",
                options=[
                    "刷临时通行卡进入档案室。",
                    "先检查门锁和铜牌上的痕迹。",
                    "询问芬格尔：有没有人能伪造学院系统记录？",
                ],
                current_location="主楼地下二层旧档案室",
            )

        if "前往钟楼" in normalized_action or "参加临时听证" in normalized_action or "钟楼听证" in normalized_action:
            return LLMClient._fixed_story(
                narration="""
钟楼比你想象中更安静。

雨水顺着石阶往下流，像一条条细小的黑蛇。钟楼的大门半开着，里面没有灯，只有一张长桌、三把空椅子，以及桌面中央一盏亮着的台灯。

灯光照着一份名单。

你的名字被打印了一次。

又被人用黑色钢笔手写了一次。

第二遍墨迹还没完全干，纸面微微反光。

你忽然觉得那不像名字。

更像某种还没盖棺的判决。
""",
                dialogue=[
                    ("诺诺", "听证室一般不会这么空。\n\n除非有人提前清场。\n\n或者有人不希望太多人听见你接下来要说的话。"),
                    ("芬格尔", "从经验上讲，空房间、长桌、台灯、没干的墨水，这四样东西同时出现的时候，最好不要主动坐中间那把椅子。\n\n那把椅子通常属于倒霉蛋。"),
                ],
                scene_prompt="empty clock tower hearing room, wet ink, single desk lamp",
                options=[
                    "检查名单上两次名字的差异。",
                    "坐到长桌前，等待听证开始。",
                    "先绕到房间后方，查看是否有人隐藏在暗处。",
                ],
                current_location="钟楼一层临时听证室",
            )

        if "前往便利店" in normalized_action or "便利店取件" in normalized_action or "取回三年前寄出" in normalized_action:
            return LLMClient._fixed_story(
                narration="""
校内便利店亮着暖黄色的灯。

和报到大厅相比，这里简直像另一个世界。货架上摆着泡面、罐装咖啡、创可贴、能量棒，还有一排看起来不该出现在便利店里的银色急救箱。

收银台后，一个戴耳机的店员正在打瞌睡。

芬格尔一进门就像回到祖国母亲的怀抱，精准地走向泡面区。

你在取件柜前输入自己的名字。

柜门弹开。

里面放着一个很旧的纸箱。

纸箱边角磨损，封口胶带已经发黄。快递单上的寄件时间是三年前。收件人一栏写着你的名字，字迹很普通，普通得像从某个旧作业本上撕下来的。

备注栏只有一句话：

别让他一个人去钟楼。

你盯着那行字看了很久。

便利店冰柜发出轻微的嗡鸣。

窗外的雨把玻璃冲得模糊，灯光映在上面，像一小块不肯熄灭的黄昏。
""",
                dialogue=[
                    ("芬格尔", "师弟，我宣布这条线索非常严重。\n\n严重到我建议我们边吃泡面边分析。\n\n人类文明发展到今天，就是为了让侦探不用饿着肚子破案。"),
                    ("诺诺", "三年前寄出的包裹，现在才到你手里。\n\n这不是物流问题。\n\n这是有人算好了时间。"),
                ],
                scene_prompt="warm academy convenience store, old package, rainy window",
                options=[
                    "打开三年前寄出的包裹。",
                    "检查快递单上的寄件地址和字迹。",
                    "询问店员：这个包裹是谁放进取件柜的？",
                    "先买一桶泡面，边吃边整理线索。",
                ],
                current_location="校内24小时便利店",
                items_gained=[{"name": "三年前寄出的新生包裹", "description": "备注写着：别让他一个人去钟楼"}],
            )

        return None

    @staticmethod
    def _fixed_story(
        *,
        narration: str,
        dialogue: list[tuple[str, str]],
        scene_prompt: str,
        options: list[str],
        current_location: str,
        items_gained: list[dict[str, Any]] | None = None,
        quests_updated: list[dict[str, Any]] | None = None,
        npcs_encountered: list[dict[str, Any]] | None = None,
    ) -> StoryOutput:
        return StoryOutput(
            narration=narration.strip(),
            dialogue=[{"speaker": speaker, "text": text} for speaker, text in dialogue],
            scene_prompt=scene_prompt,
            sanity_delta=0,
            health_delta=0,
            options=options,
            current_location=current_location,
            items_gained=items_gained or [],
            quests_updated=quests_updated or [],
            npcs_encountered=npcs_encountered or [],
        )

    @staticmethod
    def _opening_npcs() -> list[dict[str, str]]:
        return [
            {"name": "诺诺", "disposition": "接应", "notes": "受古德里安教授委托接路明非报到，并暗示学院并不普通"},
            {"name": "芬格尔", "disposition": "搭话", "notes": "用玩笑缓和危险感，同时试探玩家反应"},
        ]

    @staticmethod
    def _first_investigation_options() -> list[str]:
        return [
            "询问学院给出的三个预备任务：“所以我现在应该做什么？你们总不能真的先让我写遗书吧？”",
            "检查临时通行卡上的异常标记：“这卡为什么在发烫？它刚才是不是亮了一下？”",
            "先观察大厅里执行部学生的动向：“等等，那些穿制服的人为什么一直在看报到台？”",
        ]
