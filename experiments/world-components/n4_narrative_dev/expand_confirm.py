"""Confirmation pairs (4 per category = 40 units); shares fact helpers with expand_data."""
from expand_data import oc, ap, mv, nc

CONFIRM = [
    ("ca1", "action_actor", "FERRY", "沈砚", oc("沈砚", "把船灯的灯罩扣回去"),
     oc("顾行舟", "把船灯的灯罩扣回去")),
    ("ca2", "action_actor", "LIGHT", "叶知微", oc("叶知微", "把擦铜油放回油壶边"),
     oc("沈砚", "把擦铜油放回油壶边")),
    ("ca3", "action_actor", "WALL", "沈砚", oc("沈砚", "把铁链绕回钟架上"),
     oc("韩渡", "把铁链绕回钟架上")),
    ("ca4", "action_actor", "MARKET", "阿棠", oc("阿棠", "把案板擦干净"),
     oc("顾行舟", "把案板擦干净")),

    ("cb1", "owner", "FERRY", "沈砚", ap("顾行舟", "袖口沾了盐沫"),
     ap("沈砚", "袖口沾了盐沫")),
    ("cb2", "owner", "ARCH", "沈砚", ap("叶知微", "指尖沾了干纸的毛边"),
     ap("沈砚", "指尖沾了干纸的毛边")),
    ("cb3", "owner", "WALL", "韩渡", ap("韩渡", "眉毛上挂着雾水"),
     ap("沈砚", "眉毛上挂着雾水")),
    ("cb4", "owner", "LIGHT", "叶知微", ap("叶知微", "围裙上沾了铜油"),
     ap("沈砚", "围裙上沾了铜油")),

    ("cc1", "container", "ARCH", "沈砚", oc("沈砚", "把湿伞塞进门槛下的空隙"),
     oc("沈砚", "把湿伞立在门槛外")),
    ("cc2", "container", "ARCH", "沈砚", oc("沈砚", "把旧纸压进潮汐簿里"),
     oc("沈砚", "把旧纸摊在潮汐簿上")),
    ("cc3", "container", "MARKET", "阿棠", oc("阿棠", "把抹布塞进鱼筐底下"),
     oc("阿棠", "把抹布铺在鱼筐上面")),
    ("cc4", "container", "FERRY", "顾行舟", oc("顾行舟", "把船灯挂在栈桥的托架下"),
     oc("顾行舟", "把船灯摆在栈桥的托架上")),

    ("cd1", "binding", "ARCH", "沈砚", oc("沈砚", "把冷茶放在门槛边"),
     oc("沈砚", "把冷茶放在长桌尽头")),
    ("cd2", "binding", "FERRY", "顾行舟", oc("顾行舟", "把缆绳绕在栈桥的木桩上"),
     oc("顾行舟", "把缆绳绕在石阶的栏杆上")),
    ("cd3", "binding", "MARKET", "阿棠", oc("阿棠", "把鱼筐放在案板边上"),
     oc("阿棠", "把鱼筐放在帆布棚外")),
    ("cd4", "binding", "LIGHT", "叶知微", oc("叶知微", "把擦铜油放回梯脚"),
     oc("叶知微", "把擦铜油放在长桌上")),

    ("ce1", "change_nochange", "LIGHT", "叶知微", ap("叶知微", "指尖沾了铜油"), nc()),
    ("ce2", "change_nochange", "WALL", "沈砚", oc("沈砚", "把钟绳绕回钟架上"), nc()),
    ("ce3", "change_nochange", "FERRY", "顾行舟", oc("顾行舟", "把船灯挂回托架上"), nc()),
    ("ce4", "change_nochange", "ARCH", "沈砚", mv("沈砚", "潮生巷", "潮汐档案馆"), nc()),
]

NO_CHANGE_TARGETS = [
    "周围的一切都还是原样，没有新的变化。",
    "他站了一会儿，这里没有新的变化。",
    "场景没有新的变化，东西都还在原处。",
    "四下里静着，没有新的变化发生。",
]
