# Story families for the N4 v2 grouped-interface corpus (commit 2).
#
# Isolation by construction: every name below is NEW relative to (a) the
# old flat-input corpus pool (陈舟/苏晚/周砚/沈青/洛之衡/温以宁/白桦/祁霖/
# 阮秋/薛映/贺清言/宋知远/岑野/林望/顾一帆 + 东门/侧院/南渡口/断碑崖/
# 旧灯房/洗砚池/灰墙巷/石桥/碑亭/竹径/柴房/水房/钟楼), (b) the D2 dev-set
# pool (裴行舟/沈拾/岑半夏/顾知白/陆停云/白蘅 + 半窗书舍/竹影茶棚/西栅桥/
# 瓦窑/旧钟铺/石阶码头), and (c) B's frozen calibration corpus —
# check_isolation_v2.py enforces this string-level against the actual
# files, not just this comment. Train/dev live in families A and B; the
# frozen test set lives ONLY in family C (a world the training never saw).

# gender: "male" | "female" | "unknown" — the hint map N3 uses for
# pronominalisation; entities without an entry fall back to their name
# (the safe fallback), "unknown" renders TA.

FAMILY_A = {
    "familyId": "v2-a-quay",
    "protagonistId": "a_gubeiting",
    "locations": [
        {"id": "a_quay", "name": "咸水澳"},
        {"id": "a_lamp", "name": "灯寮"},
        {"id": "a_fishshop", "name": "鱼行"},
        {"id": "a_stilt", "name": "高脚棚"},
        {"id": "a_dryyard", "name": "晒场"},
    ],
    "characters": [
        {"id": "a_gubeiting", "name": "顾北汀", "gender": "male",
         "home": "a_quay", "sanity": 10, "personality": "持重",
         "tasks": [{"id": "a_t1", "goal": "熬一锅灯油", "ownerId": "a_gubeiting"},
                   {"id": "a_t2", "goal": "补好第三号帆", "ownerId": "a_gubeiting"}]},
        {"id": "a_ahe", "name": "阿禾", "gender": "female",
         "home": "a_fishshop", "sanity": 12, "personality": "爽利",
         "tasks": [{"id": "a_t3", "goal": "清点鲞货", "ownerId": "a_ahe"},
                   {"id": "a_t4", "goal": "把鱼行门板卸下", "ownerId": "a_ahe"}]},
        {"id": "a_shuisheng", "name": "水生", "gender": "unknown",
         "home": "a_stilt", "sanity": 9, "personality": "寡言",
         "tasks": [{"id": "a_t5", "goal": "修高脚棚的梯子", "ownerId": "a_shuisheng"}]},
        # the family's same-name pair: two DIFFERENT people, one name
        {"id": "a_chenjiu_a", "name": "陈九", "gender": "male",
         "home": "a_quay", "sanity": 11, "personality": "急躁",
         "tasks": [{"id": "a_t6", "goal": "把咸鱼坯搬上晒场", "ownerId": "a_chenjiu_a"}]},
        {"id": "a_chenjiu_b", "name": "陈九", "gender": "male",
         "home": "a_dryyard", "sanity": 13, "personality": "沉稳",
         "tasks": [{"id": "a_t7", "goal": "翻晒场上的鱼干", "ownerId": "a_chenjiu_b"}]},
        {"id": "a_yuwan", "name": "渔丸", "gender": "female",
         "home": "a_dryyard", "sanity": 10, "personality": "好奇",
         "tasks": [{"id": "a_t8", "goal": "缝补晒场的苫布", "ownerId": "a_yuwan"}]},
        {"id": "a_haiman", "name": "海满", "gender": "male",
         "home": "a_lamp", "sanity": 12, "personality": "固执",
         "tasks": [{"id": "a_t9", "goal": "给灯寮换灯芯", "ownerId": "a_haiman"}]},
    ],
    "items": [
        {"id": "a_lamp_oil", "name": "灯油瓮", "home": "a_lamp"},
        {"id": "a_net", "name": "三号帆", "home": "a_stilt"},
    ],
}

FAMILY_B = {
    "familyId": "v2-b-post",
    "protagonistId": "b_shenshubai",
    "locations": [
        {"id": "b_post", "name": "青枫驿"},
        {"id": "b_backhill", "name": "后山道"},
        {"id": "b_kitchen", "name": "茶灶房"},
        {"id": "b_stable", "name": "马厩"},
        {"id": "b_pass", "name": "碑坳"},
    ],
    "characters": [
        {"id": "b_shenshubai", "name": "沈书白", "gender": "male",
         "home": "b_post", "sanity": 10, "personality": "谨细",
         "tasks": [{"id": "b_t1", "goal": "封发驿传文书", "ownerId": "b_shenshubai"},
                   {"id": "b_t2", "goal": "换左辕马的掌", "ownerId": "b_shenshubai"}]},
        {"id": "b_guyu", "name": "谷雨", "gender": "female",
         "home": "b_kitchen", "sanity": 14, "personality": "温吞",
         "tasks": [{"id": "b_t3", "goal": "烫一壶接风酒", "ownerId": "b_guyu"},
                   {"id": "b_t4", "goal": "烘干辣椒", "ownerId": "b_guyu"}]},
        {"id": "b_weituo", "name": "魏驼", "gender": "male",
         "home": "b_stable", "sanity": 8, "personality": "暴烈",
         "tasks": [{"id": "b_t5", "goal": "铡足三日草料", "ownerId": "b_weituo"}]},
        {"id": "b_shuangxi", "name": "双喜", "gender": "unknown",
         "home": "b_post", "sanity": 12, "personality": "机灵",
         "tasks": [{"id": "b_t6", "goal": "扫净正堂灯火", "ownerId": "b_shuangxi"}]},
        {"id": "b_liujin_a", "name": "刘金", "gender": "male",
         "home": "b_stable", "sanity": 11, "personality": "少言",
         "tasks": [{"id": "b_t7", "goal": "钉牢马厩门轴", "ownerId": "b_liujin_a"}]},
        {"id": "b_liujin_b", "name": "刘金", "gender": "male",
         "home": "b_pass", "sanity": 9, "personality": "多疑",
         "tasks": [{"id": "b_t8", "goal": "清点碑坳的路签", "ownerId": "b_liujin_b"}]},
        {"id": "b_yanqi", "name": "雁七", "gender": "female",
         "home": "b_pass", "sanity": 11, "personality": "警觉",
         "tasks": [{"id": "b_t9", "goal": "核对碑坳的路条", "ownerId": "b_yanqi"}]},
        {"id": "b_douzi", "name": "豆子", "gender": "male",
         "home": "b_backhill", "sanity": 13, "personality": "憨直",
         "tasks": [{"id": "b_t10", "goal": "背柴到后山道茶灶", "ownerId": "b_douzi"}]},
    ],
    "items": [
        {"id": "b_saddle", "name": "旧鞍鞯", "home": "b_stable"},
        {"id": "b_kettle", "name": "铜汤婆子", "home": "b_kitchen"},
    ],
}

# the FROZEN TEST family — never used for training rows
FAMILY_C = {
    "familyId": "v2-c-salt",
    "protagonistId": "c_wenrenjing",
    "locations": [
        {"id": "c_flats", "name": "老盐滩"},
        {"id": "c_shed", "name": "团盐棚"},
        {"id": "c_windmill", "name": "风车埠"},
        {"id": "c_granary", "name": "官仓"},
        {"id": "c_wharf", "name": "盐埠头"},
    ],
    "characters": [
        {"id": "c_wenrenjing", "name": "闻人镜", "gender": "male",
         "home": "c_flats", "sanity": 10, "personality": "冷峻",
         "tasks": [{"id": "c_t1", "goal": "收拢三畦盐卤", "ownerId": "c_wenrenjing"},
                   {"id": "c_t2", "goal": "封存团盐棚的盐垛", "ownerId": "c_wenrenjing"}]},
        {"id": "c_liufuyi", "name": "柳拂衣", "gender": "female",
         "home": "c_shed", "sanity": 13, "personality": "利落",
         "tasks": [{"id": "c_t3", "goal": "苫盖盐垛的草席", "ownerId": "c_liufuyi"},
                   {"id": "c_t4", "goal": "过秤今日的盐包", "ownerId": "c_liufuyi"}]},
        {"id": "c_xiaoman", "name": "小满", "gender": "unknown",
         "home": "c_windmill", "sanity": 11, "personality": "胆小",
         "tasks": [{"id": "c_t5", "goal": "给风车上油", "ownerId": "c_xiaoman"}]},
        {"id": "c_qinshu_a", "name": "秦叔", "gender": "male",
         "home": "c_granary", "sanity": 12, "personality": "固执",
         "tasks": [{"id": "c_t6", "goal": "盘点官仓的存盐", "ownerId": "c_qinshu_a"}]},
        {"id": "c_qinshu_b", "name": "秦叔", "gender": "male",
         "home": "c_wharf", "sanity": 9, "personality": "和气",
         "tasks": [{"id": "c_t7", "goal": "码好盐埠头的盐包", "ownerId": "c_qinshu_b"}]},
        {"id": "c_yanbo", "name": "盐伯", "gender": "male",
         "home": "c_windmill", "sanity": 10, "personality": "沉默",
         "tasks": [{"id": "c_t8", "goal": "查看风车叶片", "ownerId": "c_yanbo"}]},
        {"id": "c_akui", "name": "阿葵", "gender": "female",
         "home": "c_wharf", "sanity": 12, "personality": "爽快",
         "tasks": [{"id": "c_t9", "goal": "数清盐埠头的筐", "ownerId": "c_akui"}]},
    ],
    "items": [
        {"id": "c_scale", "name": "官秤", "home": "c_shed"},
        {"id": "c_mat", "name": "旧苫席", "home": "c_shed"},
    ],
}

FAMILIES = {"train_a": FAMILY_A, "train_b": FAMILY_B, "test_c": FAMILY_C}


def gender_hints(family: dict) -> dict:
    return {c["id"]: c["gender"] for c in family["characters"]}


def family_names(family: dict) -> list:
    names = [loc["name"] for loc in family["locations"]]
    names += [c["name"] for c in family["characters"]]
    names += [i["name"] for i in family.get("items") or []]
    return names
