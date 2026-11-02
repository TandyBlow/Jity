# Build the N4 fact-verbalizer corpus.
#
# One Chinese sentence per fact, hand-written. Input gives only the scene
# frame, the POV holder and the fact; output must bind the fact subject to
# its action/result. No task titles, numbers, durations or field names.
#
# Run: python -X utf8 experiments/world-components/n4_narrative_dev/write_verbalizer_corpus.py

import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
OUT_TRAIN = HERE / "verbalizer_pairs.jsonl"
OUT_HOLDOUT = HERE / "verbalizer_holdout.jsonl"

# signature -> list of hand-written clauses (cycled per occurrence)
VARIANTS = {
    # ---- moved: 沈砚 ----
    ("moved", "沈砚", "潮生巷", "旧灯塔"): [
        "沈砚沿着石阶走进旧灯塔，鞋底在潮气里打滑。",
        "沈砚从潮生巷一路走到旧灯塔脚下，抬头看了看塔身。",
        "沈砚推开旧灯塔的木门，潮生巷的雨声被关在身后。",
    ],
    ("moved", "沈砚", "潮生巷", "潮渡"): [
        "沈砚从潮生巷出来，在潮渡的栈桥边站住。",
        "沈砚沿着石阶下到潮渡，河风把外袍下摆吹起来。",
        "沈砚走到潮渡的木桩旁，雾从河面漫上栈桥。",
    ],
    ("moved", "沈砚", "潮生巷", "潮汐档案馆"): [
        "沈砚从潮生巷过来，推开档案馆的门。",
        "沈砚走到潮汐档案馆门口，把湿伞收在手里。",
        "沈砚进了潮汐档案馆，在长桌边停下。",
    ],
    ("moved", "沈砚", "潮生巷", "早市"): [
        "沈砚从潮生巷挤进早市，帆布棚下的白汽扑到脸上。",
        "沈砚走到早市的摊棚外，鱼鳞在石板上反光。",
        "沈砚穿过早市的人流，在鱼摊前站住。",
    ],
    ("moved", "沈砚", "潮生巷", "雾堤"): [
        "沈砚从潮生巷出来，一直走到雾堤脚下。",
        "沈砚沿着石阶上到雾堤，浪沫打在石壁上。",
        "沈砚到了雾堤，钟架在风里轻轻响。",
    ],
    ("moved", "沈砚", "潮渡", "雾堤"): [
        "沈砚从潮渡上来，扶着铁链走到雾堤的钟架旁。",
        "沈砚离开潮渡，沿着石阶上了雾堤。",
        "沈砚从潮渡一路走到雾堤，风把他的袖口吹得鼓起来。",
    ],
    ("moved", "沈砚", "潮渡", "旧灯塔"): [
        "沈砚从潮渡回来，走进旧灯塔的石阶。",
        "沈砚离开潮渡，沿着雾里的石阶上到旧灯塔。",
        "沈砚回到旧灯塔，扶手上一层潮气。",
    ],
    ("moved", "沈砚", "潮渡", "潮生巷"): [
        "沈砚从潮渡回来，走进潮生巷。",
        "沈砚离开潮渡，沿着墙根回到潮生巷。",
        "沈砚走回潮生巷，纸灯笼的光落在水洼里。",
    ],
    ("moved", "沈砚", "旧灯塔", "潮生巷"): [
        "沈砚从旧灯塔下来，回到潮生巷。",
        "沈砚离开旧灯塔，沿着墙根走进潮生巷。",
        "沈砚走回潮生巷，把灯塔的风声留在身后。",
    ],
    ("moved", "沈砚", "旧灯塔", "潮渡"): [
        "沈砚从旧灯塔下来，走到潮渡的栈桥边。",
        "沈砚离开旧灯塔，沿着石阶下到潮渡。",
        "沈砚回到潮渡，木桩上还挂着水珠。",
    ],
    ("moved", "沈砚", "潮汐档案馆", "雾堤"): [
        "沈砚从潮汐档案馆出来，一直走到雾堤。",
        "沈砚离开档案馆，沿着石阶上到雾堤。",
        "沈砚到了雾堤，档案馆的纸墨味还留在袖口。",
    ],
    ("moved", "沈砚", "潮汐档案馆", "潮生巷"): [
        "沈砚从潮汐档案馆出来，回到潮生巷。",
        "沈砚离开档案馆，沿着墙根走进潮生巷。",
        "沈砚走回潮生巷，雨已经小了些。",
    ],
    # ---- moved: others ----
    ("moved", "叶知微", "潮渡", "旧灯塔"): [
        "叶知微从潮渡上来，走进旧灯塔。",
        "叶知微离开潮渡，沿着石阶上到旧灯塔。",
        "叶知微到了旧灯塔，袖口带着铜油味。",
    ],
    ("moved", "顾行舟", "河心", "潮渡"): [
        "顾行舟把渡船从河心靠上潮渡的木桩。",
        "顾行舟从河心划过来，船头抵住潮渡的栈桥。",
        "顾行舟把船停在潮渡，缆绳在木桩上绕了两圈。",
    ],
    ("moved", "阿棠", "早市", "潮汐档案馆"): [
        "阿棠从早市过来，抱着一叠干纸进了档案馆。",
        "阿棠离开早市，把干纸送到潮汐档案馆。",
        "阿棠走进档案馆，鞋底在门槛上蹭了两下。",
    ],
    ("moved", "阿棠", "潮生巷", "早市"): [
        "阿棠从潮生巷走进早市，围裙上沾着鱼鳞。",
        "阿棠穿过潮生巷，到早市的鱼摊前停下。",
        "阿棠到了早市，把鱼筐放在案板边。",
    ],
    ("moved", "韩渡", "潮渡", "雾堤"): [
        "韩渡从潮渡上来，蹲到雾堤的钟架下。",
        "韩渡离开潮渡，沿着石阶上到雾堤。",
        "韩渡到了雾堤，眉毛上挂着雾水。",
    ],
    # ---- outcome ----
    ("outcome", "叶知微", "把灯罩擦得透亮"): [
        "叶知微把玻璃罩上的盐雾擦掉，灯罩透亮起来。",
        "叶知微用抹布把灯罩擦得透亮。",
        "叶知微把灯罩擦得透亮，玻璃上不再有雾。",
    ],
    ("outcome", "韩渡", "把松脱的钟绳重新系紧"): [
        "韩渡蹲下去，把松脱的钟绳一圈一圈重新系紧。",
        "韩渡把松脱的钟绳重新系紧，钟绳绷直了。",
        "韩渡把松脱的钟绳重新系紧，手背上沾着盐沫。",
    ],
    ("outcome", "阿棠", "把一叠干纸放在桌角"): [
        "阿棠把一叠干纸放在桌角，纸角被风掀起。",
        "阿棠把干纸放到桌角，又伸手按住。",
        "阿棠把一叠干纸放在桌角，纸页还带着潮气。",
    ],
    ("outcome", "阿棠", "把一筐银鳞鱼搬上案板"): [
        "阿棠把一筐银鳞鱼搬上案板，鱼尾拍得筐沿响。",
        "阿棠抱起鱼筐，放到案板上。",
        "阿棠把银鳞鱼搬上案板，水花溅到石板上。",
    ],
    ("outcome", "沈砚", "把潮汐簿缺的那页补全了"): [
        "沈砚照着旧墨迹，把潮汐簿缺的那页补全了。",
        "沈砚把潮汐簿缺的那页补全，合上了簿子。",
        "沈砚把潮汐簿缺的那页补全，指尖沾了墨。",
    ],
    ("outcome", "沈砚", "从抽屉底层翻出了备用钥匙"): [
        "沈砚从抽屉最底层翻出那把备用钥匙。",
        "沈砚掀开旧纸，从抽屉底下摸出备用钥匙。",
        "沈砚把备用钥匙从抽屉底层取出来。",
    ],
    ("outcome", "沈砚", "换好了塔顶的灯芯"): [
        "沈砚换好备用灯芯，火苗重新站稳。",
        "沈砚换好了塔顶的灯芯，铜灯罩不再发暗。",
        "沈砚换好了塔顶的灯芯，退开半步看火苗。",
    ],
    ("outcome", "沈砚", "把系泊绳从浅滩拖了回来"): [
        "沈砚把陷在泥里的系泊绳一寸一寸拖回岸上。",
        "沈砚把系泊绳从浅滩拖回来，外袍下摆沾满泥水。",
        "沈砚把系泊绳从浅滩拖了回来，绳子还在滴水。",
    ],
    ("outcome", "沈砚", "在潮渡等到了最后一班船"): [
        "沈砚在潮渡等到最后一班船，船灯从雾里透出来。",
        "沈砚在潮渡等到了最后一班渡船，船灯从雾里透出来。",
        "沈砚在潮渡等到了最后一班船，才向前走了一步。",
    ],
    ("outcome", "沈砚", "敲响了雾堤上的雾警钟"): [
        "沈砚抓住钟绳，把雾堤上的雾警钟敲响。",
        "沈砚一下一下拉动钟绳，雾警钟的声音撞进雾里。",
        "沈砚敲响雾警钟，钟声被海风撕碎。",
    ],
    ("outcome", "沈砚", "把被风吹歪的警示灯扶正"): [
        "沈砚伸手把被风吹歪的警示灯扶正。",
        "沈砚扶正警示灯，玻璃罩里的火苗晃了两下。",
        "沈砚把警示灯扳回原位，铁皮壳子还在响。",
    ],
    # ---- appearance ----
    ("appearance", "叶知微", "袖口沾了铜油"): [
        "叶知微的袖口沾了铜油，在灯影里发亮。",
        "叶知微擦完灯罩，袖口蹭上一道铜油。",
        "叶知微抬起手，袖口那片铜油很显眼。",
    ],
    ("appearance", "阿棠", "鞋底带着早市的泥水"): [
        "阿棠的鞋底带着早市的泥水，在门槛上蹭了两下。",
        "阿棠走进来，鞋底还沾着早市的泥水。",
        "阿棠在石地上留下几个泥水印子。",
    ],
    ("appearance", "韩渡", "眉毛上的雾水更重了"): [
        "韩渡直起身，眉毛上的雾水更重了。",
        "韩渡抬起头，眉毛上挂着的雾水往下滴。",
        "韩渡抹了一把眉毛，雾水还是留在上面。",
    ],
    ("appearance", "阿棠", "辫梢沾了白汽"): [
        "阿棠的辫梢沾了白汽，发梢微微发潮。",
        "阿棠从蒸汽里出来，辫梢挂着白汽。",
        "阿棠低头时，辫梢的白汽还没散。",
    ],
    ("appearance", "阿棠", "围裙上又添了一层银亮鱼鳞"): [
        "阿棠的围裙上又添了一层银亮鱼鳞。",
        "阿棠搬完鱼筐，围裙上多了一片鱼鳞。",
        "阿棠的围裙沾着鱼鳞，在光里发亮。",
    ],
    ("appearance", "顾行舟", "手上的茧被水泡得发白"): [
        "顾行舟直起身，手上的茧被水泡得发白。",
        "顾行舟摊开手，掌心的茧已经泡白。",
        "顾行舟把缆绳绕好，手上的茧泛着白。",
    ],
    ("appearance", "沈砚", "外袍下摆沾满泥水，边角结了一圈白盐"): [
        "沈砚的外袍下摆沾满泥水，边角结了一圈白盐。",
        "沈砚直起腰，外袍下摆的泥水已经结出白盐。",
        "沈砚抖了抖衣摆，边角的白盐簌簌往下掉。",
    ],
    ("appearance", "沈砚", "指尖沾了墨"): [
        "沈砚的指尖沾了墨，在纸边蹭了蹭。",
        "沈砚放下笔，指尖已经染上墨色。",
        "沈砚抬手看了看，指尖沾着一点墨。",
    ],
    ("appearance", "沈砚", "袖口蹭了一道墨"): [
        "沈砚的袖口蹭了一道墨。",
        "沈砚翻纸时，袖口蹭上一道墨痕。",
        "沈砚低头看见袖口那道墨，没有去擦。",
    ],
    ("appearance", "沈砚", "外袍下摆被雾水打湿"): [
        "沈砚的外袍下摆被雾水打湿，贴在腿上。",
        "沈砚走完石阶，外袍下摆已经湿透。",
        "沈砚停下来，外袍下摆的雾水顺着衣角往下滴。",
    ],
    ("appearance", "沈砚", "外袍下摆结了一层盐霜"): [
        "沈砚的外袍下摆结了一层盐霜。",
        "沈砚低头看，衣角已经泛出白色盐霜。",
        "沈砚的外袍下摆被海风一吹，结出薄薄一层盐霜。",
    ],
    ("appearance", "沈砚", "衣摆沾了鱼鳞和泥水"): [
        "沈砚的衣摆沾了鱼鳞和泥水。",
        "沈砚让开时，衣摆还是蹭上了鱼鳞和泥水。",
        "沈砚低头看了一眼衣摆，鱼鳞粘在上面。",
    ],
    ("appearance", "沈砚", "袖口沾了鱼腥水"): [
        "沈砚的袖口沾了鱼腥水。",
        "沈砚侧身让开，袖口还是溅上鱼腥水。",
        "沈砚抬起袖子，鱼腥味很重。",
    ],
    ("appearance", "沈砚", "指腹沾了薄灰"): [
        "沈砚的指腹沾了一层薄灰。",
        "沈砚捏着钥匙，指腹蹭上薄灰。",
        "沈砚摊开手，指腹上是抽屉里的灰。",
    ],
    ("appearance", "沈砚", "外袍下摆沾了泥水"): [
        "沈砚的外袍下摆沾了泥水。",
        "沈砚走过水洼，外袍下摆溅上泥水。",
        "沈砚低头看了一眼，衣摆的泥水还没干。",
    ],
    ("appearance", "沈砚", "外袍下摆被海风掀起"): [
        "沈砚的外袍下摆被海风掀起，衣角拍在腿上。",
        "海风把沈砚的外袍下摆吹得鼓起来。",
        "沈砚按住衣角，外袍下摆还在风里翻。",
    ],
    ("appearance", "沈砚", "袖口沾了铜油"): [
        "沈砚的袖口沾了铜油。",
        "沈砚扶过窗框，袖口蹭上铜油。",
        "沈砚闻了闻袖口，铜油味很重。",
    ],
    ("appearance", "沈砚", "袖口被河风打湿"): [
        "沈砚的袖口被河风打湿，贴在手腕上。",
        "沈砚在栈桥边站久了，袖口已经潮了。",
        "沈砚把手缩回袖子里，袖口湿得发凉。",
    ],
    ("appearance", "沈砚", "掌心被铁皮冰得发麻"): [
        "沈砚的掌心被铁皮冰得发麻。",
        "沈砚搓了搓手，掌心还是麻的。",
        "沈砚松开铁链，掌心上留着冰凉的印子。",
    ],
    ("appearance", "沈砚", "衣摆沾了泥水"): [
        "沈砚的衣摆沾了泥水，边角沉甸甸地垂着。",
        "沈砚挤过人流，衣摆沾上泥水。",
        "沈砚低头看着衣摆上的泥点，往旁边让了让。",
    ],
    ("appearance", "沈砚", "鞋底沾了湿石板的水"): [
        "沈砚的鞋底沾了湿石板的水，在身后留下浅印。",
        "沈砚走过水沟，鞋底带起一层水。",
        "沈砚停下来，鞋底的水印慢慢变浅。",
    ],
    # ---- personality ----
    ("personality", "沈砚", "开始愿意先开口"): [
        "沈砚本来想把话咽回去，这次却先开了口。",
        "沈砚没有像往常那样沉默，先问了一句。",
        "沈砚张了张嘴，把那句话说了出来。",
    ],
    ("personality", "沈砚", "不再把话咽回去"): [
        "沈砚没有再把话咽回去，直接问了出来。",
        "沈砚这一次没有沉默，把想问的说了。",
        "沈砚开口时没有停顿，话已经出口。",
    ],
    ("personality", "沈砚", "开始愿意等"): [
        "沈砚没有催，站在栈桥边等了下去。",
        "沈砚按住心里的急，慢慢等着。",
        "沈砚在木桩旁站定，愿意再等一会儿。",
    ],
    # ---- sanity ----
    ("sanity", "沈砚", "up"): [
        "沈砚的呼吸慢慢匀下来，胸口那点发紧的感觉散了。",
        "沈砚松开手，才发现自己一直提着的那口气落回去了。",
        "沈砚靠在墙边站了一会儿，心跳才慢下来。",
    ],
    ("sanity", "沈砚", "down"): [
        "沈砚的呼吸有些发紧，手指也不太听使唤。",
        "沈砚按住胸口，那阵闷意没有散。",
        "沈砚站住，听见自己的呼吸比刚才重。",
    ],
    # ---- no_change ----
    ("no_change",): [
        "周围没有别的动静，什么也没有再发生。",
        "他等了一会儿，场景里没有新的变化。",
        "四下安静，没有新的事情发生。",
    ],
}

HOLDOUT_VARIANTS = {
    ("moved", "陆行", "风口岭", "云关驿"): [
        "陆行从风口岭下来，推开云关驿结霜的木门。",
    ],
    ("moved", "陆行", "云关驿", "雪溪"): [
        "陆行从云关驿出来，走到雪溪的石桥上。",
    ],
    ("moved", "陆行", "云关驿", "风口岭"): [
        "陆行离开云关驿，沿着驿道走到风口岭。",
    ],
    ("moved", "阿洛", "云关驿", "风口岭"): [
        "阿洛从云关驿出来，一直走到风口岭的隘口。",
    ],
    ("moved", "石青", "云关驿", "望雪台"): [
        "石青从云关驿出来，沿着木梯上到望雪台。",
    ],
    ("moved", "石青", "望雪台", "云关驿"): [
        "石青从望雪台下来，推门进了云关驿。",
    ],
    ("outcome", "祁婶", "把炭盆添满了"): [
        "祁婶蹲在炭盆边，把最后一块炭添进去。",
    ],
    ("outcome", "阿洛", "把马灯点着了"): [
        "阿洛把马灯从门板上取下来，点着了。",
    ],
    ("outcome", "石青", "把铜铃挂到望雪台"): [
        "石青把铜铃挂回望雪台的铃架。",
    ],
    ("outcome", "陆行", "从客房里翻出旧地图"): [
        "陆行掀开枕头，从客房里翻出那张旧地图。",
    ],
    ("outcome", "陆行", "把药包送到马棚"): [
        "陆行把药包送到旧马棚，放在干草边。",
    ],
    ("outcome", "阿洛", "把驿道上的积雪清开"): [
        "阿洛把驿道上的积雪一锹一锹清到路边。",
    ],
    ("appearance", "祁婶", "围裙上沾了炭灰"): [
        "祁婶的围裙上沾了炭灰。",
    ],
    ("appearance", "阿洛", "手指沾了灯油"): [
        "阿洛的手指沾了灯油，在围裙上擦了擦。",
    ],
    ("appearance", "陆行", "外袍下摆结了一层薄冰"): [
        "陆行的外袍下摆结了一层薄冰。",
    ],
    ("appearance", "石青", "肩上落了一层雪"): [
        "石青的肩上落了一层雪。",
    ],
    ("personality", "陆行", "开始愿意先开口"): [
        "陆行本来想把话咽回去，却先问了一句。",
    ],
    ("sanity", "陆行", "up"): [
        "陆行的呼吸慢慢匀下来，胸口那点发紧散了。",
    ],
    ("sanity", "陆行", "down"): [
        "陆行的呼吸有些发紧，手指也冻得不听使唤。",
    ],
    ("no_change",): [
        "棚里没有别的动静，什么也没有再发生。",
    ],
}


def sig_of(fact):
    kind = fact["kind"]
    if kind == "moved":
        return (kind, fact["name"], fact["from"], fact["to"])
    if kind == "outcome":
        return (kind, fact["name"], fact["resultText"])
    if kind in ("appearance_changed", "personality_changed"):
        return (kind.replace("_changed", ""), fact["name"], fact["text"])
    if kind == "sanity_changed":
        return ("sanity", fact["name"],
                "up" if fact["to"] > fact["from"] else "down")
    if kind == "no_change":
        return ("no_change",)
    return None


def fact_line(fact):
    kind = fact["kind"]
    if kind == "moved":
        return f"{fact['name']}｜移动｜{fact['from']}→{fact['to']}"
    if kind == "outcome":
        return f"{fact['name']}｜结果｜{fact['resultText']}"
    if kind == "appearance_changed":
        return f"{fact['name']}｜外貌变化｜{fact['text']}"
    if kind == "personality_changed":
        return f"{fact['name']}｜性格变化｜{fact['text']}"
    if kind == "sanity_changed":
        return f"{fact['name']}｜状态变化｜{'放松' if fact['to'] > fact['from'] else '发紧'}"
    if kind == "no_change":
        return "场景｜无变化"
    return None


ELEVATION = json.loads((HERE / "scene_elevation.json").read_text(
    encoding="utf-8"))


def scene_props(world, root_id):
    loc = world["locations"][root_id]
    props = list(loc.get("features", []))
    for sub in loc.get("sublocations", []):
        props.append(sub["name"])
        props.extend(sub.get("features", []))
    sub_ids = {s["id"] for s in loc.get("sublocations", [])} | {root_id}
    for it in world["items"].values():
        if it.get("position", {}).get("containerId") in sub_ids:
            props.append(it["name"])
    seen, out = set(), []
    for item_name in props:
        if item_name not in seen:
            seen.add(item_name)
            out.append(item_name)
    return out


def direction_word(world, frm, to):
    table = ELEVATION.get(world["worldId"], {})
    a, b = table.get(frm), table.get(to)
    if a is None or b is None or a == b:
        return "平"
    return "上" if b > a else "下"


def build_input(case, fact, world):
    root = case["sceneState"]["locationPath"][0]
    loc = world["locations"][root]["name"]
    sc = case["sceneState"]
    pov = world["characters"][case["perspective"]["entityId"]]["name"]
    extra = ""
    if fact["kind"] == "moved":
        extra = "方向=" + direction_word(world, fact["from"], fact["to"])
    body = [
        "短句任务。",
        "地点=" + loc,
        "地点可见=" + "、".join(scene_props(world, root)),
        "场景=" + "；".join([sc["time"], sc["weather"], sc["wind"], sc["light"]]),
        "视角=" + pov + "；第三人称",
        "事实=" + fact_line(fact),
        extra,
        "要求：写一句话，把事实写成场景里可见的动作或状态；句中出现事实主体的名字；只用地点可见里的物件与场景给的现象；需要表示高低时用方向给的字；不写任务标题、数值、具体时长、字段名；不新增人物、物品、地点。",
        "短句：",
    ]
    return chr(10).join(x for x in body if x) + chr(10)


def main():
    world = json.loads((HERE / "world.json").read_text(encoding="utf-8"))
    seen = {}
    rows = []
    for name in ("corpus.jsonl", "corpus_v1.jsonl", "corpus_v2.jsonl"):
        for line in (HERE / name).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            case = json.loads(line)
            for fact in case["facts"]:
                sig = sig_of(fact)
                if sig is None:
                    continue
                variants = VARIANTS.get(sig)
                if not variants:
                    raise SystemExit(f"missing variants for {sig}")
                idx = seen.get(sig, 0)
                seen[sig] = idx + 1
                rows.append({
                    "pairId": f"vb:{case['id']}:{fact['factId']}",
                    "sourceId": case["id"], "factId": fact["factId"],
                    "signature": list(sig), "kind": fact["kind"],
                    "input": build_input(case, fact, world),
                    "target": variants[idx % len(variants)],
                    "split": "vb-train",
                })
    OUT_TRAIN.write_text("\n".join(json.dumps(r, ensure_ascii=False)
                                  for r in rows) + "\n",
                         encoding="utf-8", newline="\n")

    hw = json.loads((HERE / "holdout_world.json").read_text(encoding="utf-8"))
    seen_h = {}
    hrows = []
    for line in (HERE / "holdout_corpus.jsonl").read_text(
            encoding="utf-8").splitlines():
        if not line.strip():
            continue
        case = json.loads(line)
        for fact in case["facts"]:
            sig = sig_of(fact)
            if sig is None:
                continue
            variants = HOLDOUT_VARIANTS.get(sig)
            if not variants:
                raise SystemExit(f"missing holdout variants for {sig}")
            idx = seen_h.get(sig, 0)
            seen_h[sig] = idx + 1
            hrows.append({
                "pairId": f"vbh:{case['id']}:{fact['factId']}",
                "sourceId": case["id"], "factId": fact["factId"],
                "signature": list(sig), "kind": fact["kind"],
                "input": build_input(case, fact, hw),
                "target": variants[idx % len(variants)],
                "split": "vb-holdout",
            })
    OUT_HOLDOUT.write_text("\n".join(json.dumps(r, ensure_ascii=False)
                                     for r in hrows) + "\n",
                           encoding="utf-8", newline="\n")
    print(f"train pairs {len(rows)} (unique signatures {len(seen)}) -> {OUT_TRAIN}")
    print(f"holdout pairs {len(hrows)} (unique signatures {len(seen_h)}) -> {OUT_HOLDOUT}")
    train_sigs = {tuple(r["signature"]) for r in rows}
    hold_sigs = {tuple(r["signature"]) for r in hrows}
    print("signature overlap (same verb+entity names):",
          sorted(train_sigs & hold_sigs))


if __name__ == "__main__":
    main()
