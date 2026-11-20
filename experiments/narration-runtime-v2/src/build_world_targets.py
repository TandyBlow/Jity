# -*- coding: utf-8 -*-
"""Lane-10 authored short targets for the product world's beats.

Why this file exists: the 199 frozen rows are a library world and the 7B teacher
wrote cliché, sometimes invented prose. The browser page narrates the Dragon
Raja free-day world, and its 78 beat prompts had no hand-written supervision at
all. These 78 short targets are written here, one per beat, each 20-70 chars,
each realising exactly the beat's fact and no other event.

They are lane-10 supervision, not lane 01/05 prose; `authoredBy` records that.
The checks in `src/check_beats.py` run over every target and any failure is
printed, not hidden.

    python src/build_world_targets.py
"""

from __future__ import annotations

import io
import json
import os
import sys
from typing import Any, Dict, List

HERE = os.path.dirname(os.path.abspath(__file__))
V2 = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
import check_beats as C  # noqa: E402

BEATS = os.path.join(V2, "data", "beats-v1.jsonl")
OUT = os.path.join(V2, "data", "world-targets-v1.jsonl")

TARGETS: Dict[str, str] = {
    "world-lu-move-west": "路明非从西侧服务巷走进西侧器材区，鞋底在放下的黄黑绳上蹭了一下。",
    "world-lu-task-task_lu_match": "路明非把参赛的选择定下来，当着诺诺的面做了一次有效行动，随后安全离开演习区。",
    "world-lu-task-task_lu_choice": "路明非问清了红蓝两方现在的局势，也问清自己能不能保持中立。",
    "world-lu-trait": "路明非把到嘴边的话咽回去，这一次不替别人做决定。",
    "world-lu-sanity": "路明非攥着赛区图，指尖发白，精神值从43落到38。",
    "world-nono-move-west": "诺诺从西侧服务巷走到西侧器材区，在器材棚门口停了一步。",
    "world-nono-task-task_nono_squad": "诺诺把旗台行动的掩护安排成可执行的一条，没有把路明非算作诱饵。",
    "world-nono-task-task_nono_lu": "诺诺问清了路明非的参赛意愿，又把三条接近钟楼的路线说了一遍。",
    "world-nono-trait": "诺诺把护目镜推上额头，没有再摘下来。",
    "world-nono-sanity": "诺诺把护目镜擦了擦，呼吸稳下来，精神值从58回到63。",
    "world-fingel-move-cage": "芬格尔从器材棚退进器材笼内，顺手把笼门带上。",
    "world-fingel-move-west": "芬格尔从器材棚出来，绕到西侧器材区。",
    "world-fingel-task-task_fingel_deal": "芬格尔用路线情报换到了拍摄演习照片的机会，自己也没有被淘汰。",
    "world-fingel-task-task_fingel_map": "芬格尔把检修门从里面插闩的事，告诉了准备走地下路线的人。",
    "world-fingel-trait": "交火还没停，芬格尔先开了口，声音不大，却没有退。",
    "world-fingel-sanity": "芬格尔靠着器材架笑了一声，肩膀松下来，精神值从51回到56。",
    "world-chu-task-task_chu_hold": "楚子航守住了钟楼旗台，也让蓝方真正受伤的人先撤了下去。",
    "world-chu-task-task_chu_lin": "楚子航查明了林亦舟的扭伤不妨碍行走，决定不派人接应。",
    "world-chu-trait": "楚子航没有再追问诺诺为什么留下。",
    "world-chu-sanity": "楚子航在平台边站定，肩背的力道松了些，精神值从72升到77。",
    "world-caesar-move-campus": "凯撒从红方集结点走进卡塞尔学院演习区。",
    "world-caesar-task-task_caesar_win": "凯撒在15:45停赛前把旗台控制权拿到手，红方的人能确认这一点。",
    "world-caesar-task-task_caesar_contact": "凯撒重新联络上诺诺，确认她愿意负责服务巷方向。",
    "world-caesar-trait": "凯撒没有接芬格尔的玩笑，转身去看旗台。",
    "world-caesar-sanity": "凯撒把领口拉开，长长出了一口气，精神值从76升到81。",
    "world-su-move-campus": "苏茜从东回廊下到卡塞尔学院演习区。",
    "world-su-task-task_su_watch": "苏茜守住了东回廊对钟楼的接近线，蓝方的信息仍然可信。",
    "world-su-task-task_su_report": "苏茜向楚子航报告了跨溪小桥的人员和松动的护栏。",
    "world-su-trait": "苏茜把后背交给刚认识的人，自己盯着前面的走廊。",
    "world-su-sanity": "苏茜靠着回廊的墙，握枪的手稳住了，精神值从67升到72。",
    "world-lin-move-campus": "林亦舟从西回廊走进卡塞尔学院演习区，脚步放得很慢。",
    "world-lin-task-task_lin_leave": "林亦舟没有加重脚踝的伤，一步步走到了演习医护处置室。",
    "world-lin-task-task_lin_call": "林亦舟向能听见的人说明，这是实际扭伤，不是弗里嘉弹造成的暂时失能。",
    "world-lin-trait": "林亦舟先看清地上的弹壳，才迈出下一步。",
    "world-lin-sanity": "林亦舟按住脚踝，额上冒汗，精神值从29掉到24。",
    "world-tang-move-fountain": "唐骁从中央庭院走到停水喷泉池边。",
    "world-tang-move-campus": "唐骁穿过中央庭院，进了卡塞尔学院演习区。",
    "world-tang-task-task_tang_push": "唐骁把红方接近钟楼正门的掩护做实了，正面的人能借着它往前。",
    "world-tang-task-task_tang_ammo": "唐骁退回来换掉空弹匣，没有把空枪当成掩护火力。",
    "world-tang-trait": "唐骁先问了输赢，才想起旁边还站着同伴。",
    "world-tang-sanity": "唐骁把空弹匣攥在手里，呼吸乱了，精神值从38降到33。",
    "world-zhou-task-task_zhou_guard": "周映守住了旗台，需要的时候她把信号旗安全地升降了一次。",
    "world-zhou-task-task_zhou_rope": "周映在靠近外廊边缘前扣好安全绳，又确认另一端固定住了。",
    "world-zhou-trait": "周映开口承认自己害怕，声音没有抖。",
    "world-zhou-sanity": "周映看着外廊下面，手心发凉，精神值从46降到41。",
    "world-qin-move-cage": "秦越从器材棚走进器材笼内，回过身点了一遍架子。",
    "world-qin-move-west": "秦越从器材棚走到西侧器材区。",
    "world-qin-task-task_qin_gear": "秦越把演习器材一件件登记发放，伤员搬运优先。",
    "world-qin-task-task_qin_stretcher": "秦越接到真实扭伤报告后开笼放行担架，把搬运者的名字登记下来。",
    "world-qin-trait": "秦越先看见别人手上的伤，才去搬那箱器材。",
    "world-qin-sanity": "秦越把登记本合上，肩膀卸了劲，精神值从61升到66。",
    "world-doctor-move-annex": "顾岚从演习医护处置室走到医护附楼。",
    "world-doctor-task-task_doctor_treat": "顾岚接诊了实际受伤的人，医护区没有倒向任何一方。",
    "world-doctor-task-task_doctor_prepare": "顾岚留出一张空床和冷敷材料，给可能送来的脚踝扭伤者。",
    "world-doctor-trait": "顾岚听见枪声，没有再装作听不见。",
    "world-doctor-sanity": "顾岚处理完伤口，手不再抖，精神值从81升到86。",
    "world-shen-move-annex": "沈澄从医护休息区走到医护附楼。",
    "world-shen-task-task_shen_recover": "沈澄在医护休息区缓了过来，能给出的帮助没有违反退出规则。",
    "world-shen-task-task_shen_symptom": "沈澄向顾岚说明手指的麻感有没有减轻。",
    "world-shen-trait": "沈澄没有退，这一次她决定不躲，站在原地把话说完。",
    "world-shen-sanity": "沈澄靠在休息区的椅背上，眼前一阵发灰，精神值从41降到36。",
    "world-tomiyama-move-annex": "富山雅史从医护休息区走进医护附楼。",
    "world-tomiyama-task-task_tomiyama_support": "富山雅史让退出演习的学生稳定下来，把实际伤情及时交给顾岚。",
    "world-tomiyama-task-task_tomiyama_shen": "富山雅史问清沈澄醒来后的状态，听明白她担心的是麻感还是拖累队友。",
    "world-tomiyama-trait": "富山雅史没有替沈澄做决定，只把选择摆在她面前。",
    "world-tomiyama-sanity": "富山雅史把听诊器放回桌上，呼吸顺了，精神值从79升到84。",
    "world-manstein-move-campus": "曼施坦因从演习观察席走下看台，进了卡塞尔学院演习区。",
    "world-manstein-task-task_manstein_order": "曼施坦因让自由一日按中立规则结束，真实伤情都得到了处置。",
    "world-manstein-task-task_manstein_clock": "曼施坦因在15:45发布停赛通知，又核对过旗台的最终状态。",
    "world-manstein-trait": "曼施坦因把护目镜收进自己的口袋，没有还回去。",
    "world-manstein-sanity": "曼施坦因把观察记录合上，眉头松开，精神值从84升到89。",
    "world-time-1-minute": "一分钟过去，西侧服务巷里只有放下的黄黑绳贴着地面。",
    "world-time-2-minute": "两分钟过去，巷口没有人再来，墙上的赛区图被风吹得翻起一角。",
    "world-time-3-minute": "三分钟过去，器材棚里只剩架子偶尔碰响的声音。",
    "world-time-5-minute": "五分钟过去，钟楼二层平台上的风一直没停。",
    "world-time-10-minute": "十分钟过去，红方集结点那边没有人再说话。",
    "world-time-15-minute": "十五分钟过去，东回廊的窗一直亮着。",
    "world-time-1-hour": "一个小时过去，西回廊的影子挪到了墙根。",
}


def main() -> int:
    beats: Dict[str, Dict[str, Any]] = {}
    with io.open(BEATS, encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            beat = json.loads(line)
            if beat.get("source") == "world":
                beats[beat["id"]] = beat
    missing = sorted(set(beats) - set(TARGETS))
    extra = sorted(set(TARGETS) - set(beats))
    rows: List[Dict[str, Any]] = []
    failures: List[Dict[str, Any]] = []
    for beat_id, beat in sorted(beats.items()):
        target = TARGETS[beat_id]
        verdict = C.check(beat, target, None)
        rows.append({"id": beat_id, "kind": beat["fact"]["kind"],
                     "split": beat["split"], "target": target,
                     "authoredBy": "lane-10",
                     "checks": verdict["issues"]})
        if not verdict["ok"]:
            failures.append({"id": beat_id, "issues": verdict["issues"],
                             "target": target})
    with io.open(OUT, "w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    summary = {"beats": len(beats), "authored": len(rows),
               "missing": missing, "extra": extra, "failing": failures,
               "out": OUT}
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0 if not missing and not extra and not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
