# Extra scene-sentence variants for the high-frequency combos.
#
# The original corpus had only 2 variants per combo, so the 17-occurrence
# archive-rain combo cycled the same sentences 8 times. These additions give
# the top combos 6 variants and the rest 3, without adding new scene data.
#
# Run: python -X utf8 experiments/world-components/n4_narrative_dev/expand_scene_variants.py

import importlib.util
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent

EXTRA = {
    "loc_archive|午后|雨，天窗漏雨|无（室内）|铜灯": [
        "天窗漏下的雨敲在石地上，铜灯的光晕里浮着细尘。",
        "午后屋里很暗，只有铜灯照着一桌摊开的纸页。",
        "雨声从屋顶压下来，纸页的边角被潮气泡得发软。",
        "铜灯的火苗很稳，天窗那一片玻璃全是水痕。",
    ],
    "loc_seawall|黄昏|雾，浪大|高（迎海风）|警示灯": [
        "黄昏的雾贴着堤面走，警示灯的光被浪沫打散。",
        "浪一阵阵撞上石壁，白沫落在脚边的石阶上。",
        "海风很硬，堤上的警示灯一直在晃。",
        "雾里看不清远处的浪，只听见石壁被撞得发闷。",
    ],
    "loc_lighthouse|夜|海雾，海风|高（塔顶海风直吹）|铜框信号灯": [
        "塔顶的雾被海风吹得一阵一阵，灯罩里全是水汽。",
        "铜框信号灯亮着，光只落在脚边一小片石地上。",
        "夜里的海风很硬，塔顶的灯罩一直嗡嗡响。",
        "雾贴着塔身往上爬，塔下的海面看不见了。",
    ],
    "loc_ferry|黎明|雾，低潮|中（河口风）|船灯": [
        "黎明的水汽贴着栈桥，船灯在雾里只剩一点黄。",
        "低潮的木桩露出湿泥，水面上浮着一层薄雾。",
        "河口的雾还没散，栈桥的木板上结着水珠。",
        "船灯的光落在水面上，被雾揉成一小团。",
    ],
    "loc_market|清晨|白汽，人流|低（棚下）|帆布棚下": [
        "清晨的棚下全是蒸汽，人影在雾里挤来挤去。",
        "鱼鳞粘在湿石板上，被来往的鞋底踩得发亮。",
        "帆布棚顶被蒸汽熏得发亮，鱼腥味很重。",
        "早市的水声、脚步声和蒸汽混在一起。",
    ],
    "loc_lighthouse|黄昏|海雾，湿冷|高（塔顶海风直吹）|铜框窗": [
        "黄昏的雾从窄窗渗进来，铜框上全是水汽。",
        "旋梯里的擦铜油味很重，墙上的油痕发暗。",
        "窄窗只透进一线灰光，石阶上湿得打滑。",
        "海雾贴在半层的窗上，铜框冰凉。",
    ],
    "loc_ferry|黎明|低潮，海风，湿冷|中（河口风）|退潮后的冷光": [
        "退潮后的泥滩泛着冷光，海风吹得人发僵。",
        "浅滩上留着水痕，泥腥味被风送过来。",
        "天刚亮，滩面的水光一片一片地亮起来。",
        "低潮的栈桥露出发黑的木头，湿冷从脚底上来。",
    ],
    "loc_alley|夜|雨，潮气重|低（窄巷挡风）|蜡烛": [
        "夜里的巷子很潮，蜡烛的火苗照不亮墙角。",
        "雨声压在瓦上，屋里的木头泛着湿气。",
        "潮气从门缝钻进来，烛火晃了两下又稳住。",
        "窗外的雨不急不缓，屋里的光很小。",
    ],
    "loc_alley|入夜|小雨，湿冷|低（窄巷挡风）|纸灯笼": [
        "入夜的雨细得听不见，灯笼的光落在水洼里。",
        "窄巷挡着风，湿冷从石板下面透上来。",
        "纸灯笼一盏接一盏亮着，雨水顺着墙往下淌。",
        "巷子里没有人，只有灯笼和水声。",
    ],
    "loc_lighthouse|黎明|海雾，湿冷|高（塔顶海风直吹）|雾里的塔身": [
        "黎明的雾把塔身裹住，只露出上半截石壁。",
        "石阶上全是雾水，铁链摸上去冰凉。",
        "天刚亮，海雾还没退，塔下的路看不清。",
        "雾水顺着石壁往下流，台阶滑得厉害。",
    ],
    "loc_alley|午后|晴，石板半干|低（窄巷挡风）|纸灯笼": [
        "午后的光斜进巷子，石板上的水痕慢慢变浅。",
        "纸灯笼在墙上晃，水沟里的积水映着一片光。",
        "雨停后的巷子很静，墙根的青苔发暗。",
        "午后的风很轻，灯笼的影子落在湿石板上。",
    ],
    "loc_lighthouse|夜|夜雾，海风|塔顶海风直吹|塔顶铜灯已点亮": [
        "夜雾贴着塔顶，铜灯的光晕里全是水汽。",
        "海风从塔顶刮过，灯罩一直嗡嗡响。",
    ],
    "loc_ferry|黎明|低潮，海风，湿冷|河口风|天刚亮": [
        "天刚亮，滩面露出来，木桩上挂着水珠。",
        "河口的湿冷贴在脸上，栈桥的木头发黑。",
    ],
    "loc_ferry|黄昏|雾，河面低|河口风|船灯": [
        "黄昏的雾压着河面，船灯在水汽里发黄。",
        "河风很轻，栈桥的木板上全是水光。",
    ],
    "loc_ferry|黄昏|雾，河面低|中（河口风）|船灯": [
        "雾从河面漫上来，船灯只剩一团模糊的光。",
        "黄昏的水汽很重，木桩上缠着湿缆绳。",
    ],
    "loc_archive|午后|雨|无（室内）|铜灯": [
        "雨点落在天窗上，屋里的纸墨味很重。",
        "午后光线很暗，铜灯照着长桌一角。",
    ],
    "loc_seawall|夜|大雾，浪高|迎海风|无（雾中）": [
        "大雾把石堤吞掉，浪声一阵比一阵近。",
        "夜里的雾很重，白沫翻上堤面就看不见了。",
    ],
    "loc_alley|夜|雨|低（室内）|蜡烛": [
        "雨声压在窗外，蜡烛烧得只剩半截。",
        "屋里的潮气很重，火苗照不亮桌面。",
    ],
    "loc_archive|夜|雨渐匀|无（室内）|铜灯": [
        "夜里的雨声匀下来，铜灯照着一桌纸页。",
        "天窗还在滴水，屋里的潮气没有散。",
    ],
    "loc_market|清晨|潮湿，白汽|低（棚下）|棚下散光": [
        "清晨的棚下很潮，蒸汽把棚布熏得发亮。",
        "鱼鳞在湿石板上闪着碎光，水汽很重。",
    ],
    "loc_lighthouse|傍晚|海风|旋梯口海风|海光从窄窗照进来": [
        "傍晚的海光斜进窄窗，旋梯的木梯发暗。",
        "海风从旋梯口灌进来，墙上的油痕很深。",
    ],
    "loc_alley|夜|雨渐小|低（窄巷）|纸灯笼": [
        "雨小了些，灯笼的光落在湿石板上。",
        "巷子里只剩水声，墙根的水洼映着光。",
    ],
    "loc_seawall|夜|雾，风横，浪高|迎海风|警示灯": [
        "雾里只有警示灯亮着，横风从堤面扫过。",
        "浪头撞上石壁，白沫被风吹得四散。",
    ],
    "loc_ferry|夜|雾|河口风|船灯": [
        "夜里雾更重，船灯只剩一点黄。",
        "河风把雾推来推去，木桩上挂着水珠。",
    ],
    "loc_lighthouse|夜|海雾，海风|高（塔顶海风直吹）|铜框信号灯还亮着": [
        "海雾围着塔顶，铜框信号灯还亮着。",
        "塔顶的风很硬，灯罩在雾里发白。",
    ],
    "loc_seawall|夜|雾，海风|高（迎海风）|警示灯": [
        "夜里的雾压着海堤，警示灯的光很散。",
        "海风从石壁另一侧灌过来，钟架轻轻响。",
    ],
    "loc_market|上午|晴，白汽散了一半|低（棚下）|帆布棚下": [
        "上午的白汽散了一半，棚下只剩空筐。",
        "日头照进早市，石板上还留着水光。",
    ],
    "loc_lighthouse|夜|海雾，湿冷|高（塔顶海风直吹）|塔顶灯火": [
        "海雾贴着塔身，塔顶的灯火发白。",
        "夜里的风又湿又冷，石阶上全是水光。",
    ],
    "loc_ferry|清晨|雾，水汽重|中（河口风）|船灯": [
        "清晨的水汽很重，船灯只透出一点黄。",
        "雾还没散，栈桥的木板上滑得很。",
    ],
    "loc_archive|午后|雨刚停|无（室内）|铜灯": [
        "雨刚停，天窗上还挂着水珠。",
        "门槛外还有滴水声，屋里的纸墨味很重。",
    ],
    "loc_archive|午后|细雨，天窗漏雨|无（室内）|铜灯": [
        "细雨落在天窗上，铜灯的光很稳。",
        "屋外的雨很细，天窗只漏下几滴水。",
    ],
    "loc_market|清晨|白汽，湿冷|低（棚下）|帆布棚下": [
        "清晨的湿冷混着白汽，棚下全是水光。",
        "鱼鳞粘在石板上，棚布被蒸汽熏得发潮。",
    ],
    "loc_ferry|夜|雾，水汽重|中（河口风）|船灯": [
        "夜里的水汽压在河面上，船灯发暗。",
        "雾漫上栈桥，脚下的木板又湿又滑。",
    ],
}


def main():
    spec = importlib.util.spec_from_file_location(
        "write_scene_corpus", HERE / "write_scene_corpus.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    merged = 0
    for key, extra in EXTRA.items():
        if key not in mod.SCENES:
            raise SystemExit(f"unknown scene key: {key}")
        before = len(mod.SCENES[key])
        for t in extra:
            if t not in mod.SCENES[key]:
                mod.SCENES[key].append(t)
                merged += 1
        print(f"{key}: {before} -> {len(mod.SCENES[key])}")
    mod.SCENES = mod.SCENES
    # rewrite the SCENES literal in write_scene_corpus.py
    path = HERE / "write_scene_corpus.py"
    text = path.read_text(encoding="utf-8")
    start = text.index("SCENES = {")
    end = text.index("HOLDOUT = {")
    body = json.dumps(mod.SCENES, ensure_ascii=False, indent=4)
    body = body.replace("true", "True").replace("false", "False")
    new = "SCENES = " + body + chr(10) + chr(10)
    path.write_text(text[:start] + new + text[end:], encoding="utf-8",
                    newline=chr(10))
    print("merged variants:", merged)
    print("rewrote", path)


if __name__ == "__main__":
    main()
