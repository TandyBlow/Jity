# Routed-split review cases

Selected point: 240; decode budget: 20.0 s; judge: mechanical `judge_expression.py`.

Every row below is a case where the two arms produced different text. Same-text rows are not listed here; flagged same-text rows are in the common-defect section.

## act — changed text (29 cases)

### act-001 diagnostic/cf24/t03:f0 (outcome)
- 事实：`把灯罩擦得透亮`
- 地点可见：`铜灯罩、抹布、擦铜油、灯芯、铜框信号灯、玻璃罩、火苗、海风直吹、石阶、旋梯、塔顶、铜灯罩、铁链`
- control（act 对照）：叶知微把灯罩擦得透亮,玻璃罩上不再有雾。
- routed（act）：叶知微把灯罩擦得透亮。
- 机械差：{"mustExpress": 0, "binding": 0, "repetition": 0, "addition": 1}；control flags=['extra-state:不再']; routed flags=[]
- 人工判定：

### act-002 diagnostic/cf24/t05:f0 (outcome)
- 事实：`把松脱的钟绳重新系紧`
- 地点可见：`钟绳、雾警钟、警示灯、石壁、钟架、钟绳、警示灯、铁皮、白沫、石阶、铁链、钟架、钟绳、雾警钟`
- control（act 对照）：韩渡把松脱的钟绳重新系紧,钟绳绷直。
- routed（act）：韩渡把松脱的钟绳重新系紧。
- 机械差：{"mustExpress": 0, "binding": 0, "repetition": 1, "addition": 1}；control flags=['semantic-repeat:钟绳', 'extra-state:绷直']; routed flags=[]
- 人工判定：

### act-003 diagnostic/cf24/t07:f0 (moved)
- 事实：`潮渡 → 雾堤`
- 地点可见：`钟绳、雾警钟、警示灯、石壁、钟架、钟绳、警示灯、铁皮、白沫、石阶、铁链、钟架、钟绳、雾警钟`
- control（act 对照）：沈砚从潮渡上来,走到雾堤的钟架下。
- routed（act）：沈砚从潮渡上来,抬头看了看钟绳。
- 机械差：{"mustExpress": -1, "binding": 0, "repetition": 0, "addition": -1}；control flags=[]; routed flags=['must-missing', 'extra-action:抬头']
- 人工判定：

### act-004 diagnostic/cf24/t07:f1 (outcome)
- 事实：`把松脱的钟绳重新系紧`
- 地点可见：`钟绳、雾警钟、警示灯、石壁、钟架、钟绳、警示灯、铁皮、白沫、石阶、铁链、钟架、钟绳、雾警钟`
- control（act 对照）：韩渡把松脱的钟绳重新系紧,钟绳绷直。
- routed（act）：韩渡把松脱的钟绳重新系紧,钟绳绷直了。
- 机械差：{"mustExpress": 0, "binding": 0, "repetition": 0, "addition": 0}；control flags=['semantic-repeat:钟绳', 'extra-state:绷直']; routed flags=['semantic-repeat:钟绳', 'extra-state:绷直']
- 人工判定：

### act-005 diagnostic/cf24/t08:f0 (outcome)
- 事实：`把银鳞鱼搬上案板`
- 地点可见：`银鳞鱼、鱼筐、缆绳、帆布棚、鱼筐、案板、石板、银鳞鱼、白汽`
- control（act 对照）：阿棠把银鳞鱼搬上案板,石板上沾满白汽。
- routed（act）：阿棠把银鳞鱼搬上案板。
- 机械差：{"mustExpress": 0, "binding": 0, "repetition": 0, "addition": 0}；control flags=[]; routed flags=[]
- 人工判定：

### act-006 diagnostic/cf24/t09:f0 (moved)
- 事实：`早市 → 潮汐档案馆`
- 地点可见：`潮汐簿、铜灯、干纸、墨、天窗、长桌、门槛、铜灯、潮汐簿、干纸`
- control（act 对照）：叶知微从早市过来,推开档案馆的门。
- routed（act）：叶知微从早市上来,走进档案馆。
- 机械差：{"mustExpress": 0, "binding": 0, "repetition": 0, "addition": 0}；control flags=[]; routed flags=[]
- 人工判定：

### act-007 diagnostic/cf24/t09:f2 (outcome)
- 事实：`把一叠干纸放在桌角`
- 地点可见：`潮汐簿、铜灯、干纸、墨、天窗、长桌、门槛、铜灯、潮汐簿、干纸`
- control（act 对照）：叶知微把干纸放在桌角。
- routed（act）：叶知微把一叠干纸放在桌角,纸页还带着潮气。
- 机械差：{"mustExpress": 0, "binding": 0, "repetition": 0, "addition": 0}；control flags=[]; routed flags=[]
- 人工判定：

### act-008 diagnostic/cf24/t11:f1 (outcome)
- 事实：`把灯罩擦得透亮`
- 地点可见：`铜灯罩、备用灯芯、抹布、擦铜油、铜框信号灯、玻璃罩、火苗、海风直吹、石阶、旋梯、塔顶、铜灯罩、铁链`
- control（act 对照）：叶知微把灯罩擦得透亮,玻璃罩上不再有雾。
- routed（act）：叶知微把灯罩擦得透亮,玻璃罩不再发暗。
- 机械差：{"mustExpress": 0, "binding": 0, "repetition": 0, "addition": 0}；control flags=['extra-state:不再']; routed flags=['extra-state:不再/发暗']
- 人工判定：

### act-009 diagnostic/cf24/t11:f2 (outcome)
- 事实：`换好塔顶的灯芯`
- 地点可见：`铜灯罩、备用灯芯、抹布、擦铜油、铜框信号灯、玻璃罩、火苗、海风直吹、石阶、旋梯、塔顶、铜灯罩、铁链`
- control（act 对照）：沈砚换好备用灯芯,铜灯罩上还亮着。
- routed（act）：沈砚换好塔顶的灯芯,玻璃罩不再发暗。
- 机械差：{"mustExpress": 1, "binding": 0, "repetition": 0, "addition": 0}；control flags=['must-missing', 'extra-object:铜灯']; routed flags=['extra-state:不再/发暗']
- 人工判定：

### act-010 diagnostic/cf24/t12:f0 (moved)
- 事实：`早市 → 潮生巷`
- 地点可见：`油纸伞、鱼筐、石板、纸灯笼、排水沟、墙根、水洼`
- control（act 对照）：阿棠从早市过来,蹲到潮生巷。
- routed（act）：阿棠从早市过来,抱着鱼筐进了潮生巷。
- 机械差：{"mustExpress": 0, "binding": 0, "repetition": 0, "addition": 1}；control flags=['extra-action:蹲']; routed flags=[]
- 人工判定：

### act-011 diagnostic/cf24/t13:f1 (outcome)
- 事实：`把一叠干纸放在桌角`
- 地点可见：`干纸、潮汐簿、铜灯、墨、天窗、长桌、门槛、铜灯、潮汐簿、干纸`
- control（act 对照）：叶知微把干纸放在桌角。
- routed（act）：叶知微把一叠干纸放在桌角,干纸把干纸放在桌角。
- 机械差：{"mustExpress": 0, "binding": 0, "repetition": -1, "addition": 0}；control flags=[]; routed flags=['semantic-repeat:干纸']
- 人工判定：

### act-012 diagnostic/cf24/t14:f0 (moved)
- 事实：`潮渡 → 雾堤`
- 地点可见：`缆绳、钟绳、警示灯、石壁、钟架、钟绳、警示灯、铁皮、白沫、石阶、铁链、钟架、钟绳、雾警钟`
- control（act 对照）：顾行舟从潮渡上来,走到雾堤的钟架下。
- routed（act）：顾行舟从潮渡上来,抬头看了看钟绳。
- 机械差：{"mustExpress": -1, "binding": 0, "repetition": 0, "addition": -1}；control flags=[]; routed flags=['must-missing', 'extra-action:抬头']
- 人工判定：

### act-013 diagnostic/cf24/t15:f0 (moved)
- 事实：`潮生巷 → 潮渡`
- 地点可见：`渡船、缆绳、船灯、木桩、缆绳、船灯、水面、木桩、缆绳、船灯、水面、浅滩`
- control（act 对照）：韩渡从潮生巷一路走到潮渡栈桥边。
- routed（act）：韩渡从潮生巷一路走到潮渡。
- 机械差：{"mustExpress": 0, "binding": 0, "repetition": 0, "addition": 0}；control flags=[]; routed flags=[]
- 人工判定：

### act-014 diagnostic/cf24/t16:f0 (moved)
- 事实：`潮汐档案馆 → 潮生巷`
- 地点可见：`油布包、备用钥匙、石板、纸灯笼、排水沟、墙根、水洼`
- control（act 对照）：沈砚从潮汐档案馆出来,走到潮生巷。
- routed（act）：沈砚从潮汐档案馆出来,走进潮生巷。
- 机械差：{"mustExpress": 0, "binding": 0, "repetition": 0, "addition": 0}；control flags=[]; routed flags=[]
- 人工判定：

### act-015 diagnostic/cf24/t17:f0 (moved)
- 事实：`潮生巷 → 早市`
- 地点可见：`银鳞鱼、鱼筐、抹布、帆布棚、鱼筐、案板、石板、银鳞鱼、白汽`
- control（act 对照）：阿棠从潮生巷出来,蹲到早市。
- routed（act）：阿棠从潮生巷一路走到早市,鱼筐从石板上摸到鱼。
- 机械差：{"mustExpress": 0, "binding": 0, "repetition": 0, "addition": 1}；control flags=['extra-action:蹲']; routed flags=[]
- 人工判定：

### act-016 diagnostic/cf24/t17:f1 (outcome)
- 事实：`把银鳞鱼搬上案板`
- 地点可见：`银鳞鱼、鱼筐、抹布、帆布棚、鱼筐、案板、石板、银鳞鱼、白汽`
- control（act 对照）：阿棠把银鳞鱼搬上案板,石板上沾满白汽。
- routed（act）：阿棠把银鳞鱼搬上案板。
- 机械差：{"mustExpress": 0, "binding": 0, "repetition": 0, "addition": 0}；control flags=[]; routed flags=[]
- 人工判定：

### act-017 diagnostic/cf24/t18:f1 (outcome)
- 事实：`把灯罩擦得透亮`
- 地点可见：`铜灯罩、抹布、擦铜油、灯芯、铜框信号灯、玻璃罩、火苗、海风直吹、石阶、旋梯、塔顶、铜灯罩、铁链`
- control（act 对照）：叶知微把灯罩擦得透亮,玻璃罩上不再有雾。
- routed（act）：叶知微把灯罩擦得透亮。
- 机械差：{"mustExpress": 0, "binding": 0, "repetition": 0, "addition": 1}；control flags=['extra-state:不再']; routed flags=[]
- 人工判定：

### act-018 diagnostic/cf24/t23:f2 (outcome)
- 事实：`把灯罩擦得透亮`
- 地点可见：`铜灯罩、灯芯、抹布、铜框信号灯、玻璃罩、火苗、海风直吹、石阶、旋梯、塔顶、铜灯罩、铁链`
- control（act 对照）：叶知微把灯罩擦得透亮,玻璃罩已经亮亮。
- routed（act）：叶知微把灯罩擦得透亮,玻璃罩透亮起来。
- 机械差：{"mustExpress": 0, "binding": 0, "repetition": -1, "addition": 0}；control flags=[]; routed flags=['semantic-repeat:透亮']
- 人工判定：

### act-019 diagnostic/cf24/t23:f3 (outcome)
- 事实：`换好塔顶的灯芯`
- 地点可见：`铜灯罩、灯芯、抹布、铜框信号灯、玻璃罩、火苗、海风直吹、石阶、旋梯、塔顶、铜灯罩、铁链`
- control（act 对照）：沈砚换好灯芯,铜灯罩上还亮着。
- routed（act）：沈砚换好塔顶的灯芯,玻璃罩不再发暗。
- 机械差：{"mustExpress": 1, "binding": 0, "repetition": 0, "addition": 0}；control flags=['must-missing', 'extra-object:铜灯']; routed flags=['extra-state:不再/发暗']
- 人工判定：

### act-020 diagnostic/expand36/ce4A (moved)
- 事实：`潮生巷 → 潮汐档案馆`
- 地点可见：`潮汐簿、铜灯、干纸、墨、油布包、备用钥匙、天窗、长桌、门槛、铜灯`
- control（act 对照）：沈砚从潮生巷一路走到档案馆门口。
- routed（act）：沈砚从潮生巷一路走到潮汐档案馆脚下,抬头看了看档案馆。
- 机械差：{"mustExpress": 0, "binding": 0, "repetition": -1, "addition": -1}；control flags=[]; routed flags=['semantic-repeat:档案', 'extra-action:抬头', 'extra-object:脚']
- 人工判定：

### act-021 diagnostic/final24/v01:f0 (moved)
- 事实：`潮渡 → 雾堤`
- 地点可见：`钟绳、雾警钟、警示灯、铁链、铁链、钟架、钟绳`
- control（act 对照）：沈砚从潮渡上来,走到雾堤的钟架下。
- routed（act）：沈砚从潮渡上来,蹲到雾堤的钟架下。
- 机械差：{"mustExpress": 0, "binding": 0, "repetition": 0, "addition": -1}；control flags=[]; routed flags=['extra-action:蹲']
- 人工判定：

### act-022 diagnostic/final24/v01:f1 (outcome)
- 事实：`把松脱的钟绳重新系紧`
- 地点可见：`钟绳、雾警钟、警示灯、铁链、铁链、钟架、钟绳`
- control（act 对照）：韩渡把松脱的钟绳重新系紧,钟绳绷直。
- routed（act）：韩渡把松脱的钟绳重新系紧,钟绳绷直了。
- 机械差：{"mustExpress": 0, "binding": 0, "repetition": 0, "addition": 0}；control flags=['semantic-repeat:钟绳', 'extra-state:绷直']; routed flags=['semantic-repeat:钟绳', 'extra-state:绷直']
- 人工判定：

### act-023 diagnostic/final24/v05:f2 (outcome)
- 事实：`把灯罩擦得透亮`
- 地点可见：`铜灯罩、灯芯、抹布、擦铜油、铜灯罩、铁链、备用灯芯、抹布`
- control（act 对照）：叶知微把灯罩擦得透亮,玻璃上不再有雾。
- routed（act）：叶知微把灯罩擦得透亮,灯罩透亮起来。
- 机械差：{"mustExpress": 0, "binding": 0, "repetition": -1, "addition": 1}；control flags=['extra-state:不再']; routed flags=['semantic-repeat:灯罩']
- 人工判定：

### act-024 diagnostic/final24/v11:f0 (moved)
- 事实：`潮生巷 → 潮汐档案馆`
- 地点可见：`潮汐簿、铜灯、干纸、墨、天窗、长桌、门槛、铜灯`
- control（act 对照）：沈砚从潮生巷一路走到潮汐档案馆门口。
- routed（act）：沈砚从潮生巷一路走到潮汐档案馆脚下,抬头看了看档案馆。
- 机械差：{"mustExpress": 0, "binding": 0, "repetition": -1, "addition": -1}；control flags=[]; routed flags=['semantic-repeat:档案', 'extra-action:抬头', 'extra-object:脚']
- 人工判定：

### act-025 diagnostic/final24/v12:f0 (moved)
- 事实：`潮生巷 → 早市`
- 地点可见：`银鳞鱼、鱼筐、案板、抹布、帆布棚、鱼筐、案板、石板`
- control（act 对照）：阿棠从潮生巷出来,蹲到早市。
- routed（act）：阿棠从潮生巷一路走到早市,鱼筐在案板上沾着鱼鳞。
- 机械差：{"mustExpress": 0, "binding": 0, "repetition": 0, "addition": 0}；control flags=['extra-action:蹲']; routed flags=['extra-object:鱼鳞']
- 人工判定：

### act-026 diagnostic/final24/v13:f1 (outcome)
- 事实：`换好塔顶的灯芯`
- 地点可见：`铜灯罩、灯芯、抹布、擦铜油、铜灯罩、铁链、备用灯芯、抹布`
- control（act 对照）：叶知微换好灯芯,抹布上沾着铜油。
- routed（act）：叶知微换好塔顶的灯芯,灯芯换好。
- 机械差：{"mustExpress": 1, "binding": 0, "repetition": -1, "addition": 1}；control flags=['must-missing', 'extra-object:铜油']; routed flags=['semantic-repeat:换好']
- 人工判定：

### act-027 diagnostic/final24/v14:f0 (moved)
- 事实：`潮汐档案馆 → 潮渡`
- 地点可见：`缆绳、渡船、船灯、系泊绳、木桩、缆绳、船灯、水面、栈桥`
- control（act 对照）：沈砚从潮汐档案馆出来,一直走到潮渡栈桥边。
- routed（act）：沈砚从潮汐档案馆出来,船头抵住潮渡。
- 机械差：{"mustExpress": 0, "binding": 0, "repetition": 0, "addition": 0}；control flags=[]; routed flags=[]
- 人工判定：

### act-028 diagnostic/final24/v18:f0 (moved)
- 事实：`潮渡 → 雾堤`
- 地点可见：`钟绳、雾警钟、警示灯、铁链、铁链、钟架、钟绳`
- control（act 对照）：沈砚从潮渡上来,走到雾堤的钟架下。
- routed（act）：沈砚从潮渡上来,蹲到雾堤的钟架下。
- 机械差：{"mustExpress": 0, "binding": 0, "repetition": 0, "addition": -1}；control flags=[]; routed flags=['extra-action:蹲']
- 人工判定：

### act-029 diagnostic/final24/v20:f0 (moved)
- 事实：`潮生巷 → 潮渡`
- 地点可见：`缆绳、渡船、船灯、系泊绳、木桩、缆绳、船灯、水面、栈桥`
- control（act 对照）：沈砚从潮生巷一路走到潮渡栈桥边。
- routed（act）：沈砚从潮生巷一路走到潮渡。
- 机械差：{"mustExpress": 0, "binding": 0, "repetition": 0, "addition": 0}；control flags=[]; routed flags=[]
- 人工判定：

## state — changed text (58 cases)

### state-001 diagnostic/cf24/t10:f3 (sanity_changed)
- 事实：`12 → 9`
- 地点可见：`缆绳、渡船、系泊绳、木桩、缆绳、船灯、水面、木桩、缆绳、船灯、水面、浅滩`
- control（state 对照）：沈砚的呼吸有些发紧,手指也不太听使唤。
- routed（state）：沈砚没有像往常那样沉默,把想问
- 机械差：{"mustExpress": -1, "binding": 0, "repetition": 0, "addition": 0}；control flags=[]; routed flags=['must-missing']
- 人工判定：

### state-002 diagnostic/cf24/t16:f2 (sanity_changed)
- 事实：`12 → 9`
- 地点可见：`油布包、备用钥匙、石板、纸灯笼、排水沟、墙根、水洼`
- control（state 对照）：沈砚的呼吸有些发紧,手指也不太听使唤。
- routed（state）：沈砚没有像往常那样沉默,把想问
- 机械差：{"mustExpress": -1, "binding": 0, "repetition": 0, "addition": 0}；control flags=[]; routed flags=['must-missing']
- 人工判定：

### state-003 diagnostic/cf24/t20:f0 (appearance_changed)
- 事实：`铜框玻璃罩被风吹歪`
- 地点可见：`警示灯、钟绳、石壁、钟架、钟绳、警示灯、铁皮、白沫、石阶、铁链、钟架、钟绳、雾警钟`
- control（state 对照）：警示灯的外貌变化,铜框玻璃罩被风吹歪。
- routed（state）：警示灯的铜框玻璃罩被风吹歪。
- 机械差：{"mustExpress": 0, "binding": 0, "repetition": 0, "addition": 0}；control flags=[]; routed flags=[]
- 人工判定：

### state-004 diagnostic/cf24/t20:f1 (appearance_changed)
- 事实：`磨出了毛边`
- 地点可见：`警示灯、钟绳、石壁、钟架、钟绳、警示灯、铁皮、白沫、石阶、铁链、钟架、钟绳、雾警钟`
- control（state 对照）：钟绳的外貌变化,磨出了毛边。
- routed（state）：钟绳磨出了毛边。
- 机械差：{"mustExpress": 0, "binding": 0, "repetition": 0, "addition": 0}；control flags=[]; routed flags=[]
- 人工判定：

### state-005 diagnostic/cf24/t21:f1 (appearance_changed)
- 事实：`灯罩上积了灰`
- 地点可见：`潮汐簿、铜灯、干纸、墨、天窗、长桌、门槛、铜灯、潮汐簿、干纸`
- control（state 对照）：铜灯的外貌变化,灯罩上积了灰。
- routed（state）：铜灯的灯罩上积了灰。
- 机械差：{"mustExpress": 0, "binding": 0, "repetition": 0, "addition": 0}；control flags=[]; routed flags=[]
- 人工判定：

### state-006 diagnostic/cf24/t22:f1 (appearance_changed)
- 事实：`缠着的旧缆绳断了`
- 地点可见：`系泊绳、渡船、缆绳、退潮后的泥滩、系泊绳、冷光、木桩、缆绳、船灯、水面、浅滩`
- control（state 对照）：木桩上缠着的旧缆绳断了。
- routed（state）：木桩的缠着的旧缆绳断了。
- 机械差：{"mustExpress": 0, "binding": 0, "repetition": 0, "addition": 0}；control flags=[]; routed flags=[]
- 人工判定：

### state-007 diagnostic/cf24/t23:f0 (appearance_changed)
- 事实：`玻璃上蒙了盐雾`
- 地点可见：`铜灯罩、灯芯、抹布、铜框信号灯、玻璃罩、火苗、海风直吹、石阶、旋梯、塔顶、铜灯罩、铁链`
- control（state 对照）：铜灯罩的外貌变化,玻璃上蒙了盐雾。
- routed（state）：铜灯罩的玻璃上蒙了盐雾。
- 机械差：{"mustExpress": 0, "binding": 0, "repetition": 0, "addition": 0}；control flags=['extra-object:铜灯']; routed flags=['extra-object:铜灯']
- 人工判定：

### state-008 diagnostic/cf24/t23:f1 (appearance_changed)
- 事实：`链环上结了锈`
- 地点可见：`铜灯罩、灯芯、抹布、铜框信号灯、玻璃罩、火苗、海风直吹、石阶、旋梯、塔顶、铜灯罩、铁链`
- control（state 对照）：铁链的外貌变化,链环上结了锈。
- routed（state）：铁链的链环上结了锈。
- 机械差：{"mustExpress": 0, "binding": 0, "repetition": 0, "addition": 0}；control flags=[]; routed flags=[]
- 人工判定：

### state-009 diagnostic/cf24/t24:f1 (appearance_changed)
- 事实：`里面积了泥`
- 地点可见：`鱼筐、石板、纸灯笼、排水沟、墙根、水洼`
- control（state 对照）：排水沟里的外貌变化,里面积了泥。
- routed（state）：排水沟的里面积了泥。
- 机械差：{"mustExpress": 0, "binding": 0, "repetition": 0, "addition": 0}；control flags=[]; routed flags=[]
- 人工判定：

### state-010 diagnostic/expand36/cb3A (appearance_changed)
- 事实：`眉毛上挂着雾水`
- 地点可见：`钟绳、雾警钟、警示灯、铁链、铁链、钟架、钟绳`
- control（state 对照）：韩渡眉毛上挂着雾水。
- routed（state）：韩渡的眉毛上挂着雾水。
- 机械差：{"mustExpress": 0, "binding": 0, "repetition": 0, "addition": 0}；control flags=[]; routed flags=[]
- 人工判定：

### state-011 diagnostic/final24/v07:f0 (appearance_changed)
- 事实：`灯罩上积了灰`
- 地点可见：`铜灯、蜡烛、潮汐簿、冷茶、天窗、长桌、门槛、铜灯`
- control（state 对照）：铜灯的外貌变化,灯罩上积了灰。
- routed（state）：铜灯的灯罩上积了灰。
- 机械差：{"mustExpress": 0, "binding": 0, "repetition": 0, "addition": 0}；control flags=[]; routed flags=[]
- 人工判定：

### state-012 diagnostic/final24/v08:f0 (appearance_changed)
- 事实：`玻璃罩被风吹歪`
- 地点可见：`警示灯、钟绳、钟架、铁链、铁链、钟架、钟绳`
- control（state 对照）：警示灯的外貌变化,玻璃罩被风吹歪。
- routed（state）：警示灯的玻璃罩被风吹歪。
- 机械差：{"mustExpress": 0, "binding": 0, "repetition": 0, "addition": 0}；control flags=[]; routed flags=[]
- 人工判定：

### state-013 diagnostic/final24/v08:f1 (appearance_changed)
- 事实：`磨出了毛边`
- 地点可见：`警示灯、钟绳、钟架、铁链、铁链、钟架、钟绳`
- control（state 对照）：钟绳的外貌变化,磨出了毛边。
- routed（state）：钟绳磨出了毛边。
- 机械差：{"mustExpress": 0, "binding": 0, "repetition": 0, "addition": 0}；control flags=[]; routed flags=[]
- 人工判定：

### state-014 diagnostic/final24/v10:f0 (appearance_changed)
- 事实：`链环上结了锈`
- 地点可见：`铜灯罩、铁链、抹布、擦铜油、铜灯罩、铁链、备用灯芯、抹布`
- control（state 对照）：铁链的外貌变化,链环上结了锈。
- routed（state）：铁链的链环上结了锈。
- 机械差：{"mustExpress": 0, "binding": 0, "repetition": 0, "addition": 0}；control flags=[]; routed flags=[]
- 人工判定：

### state-015 diagnostic/final24/v10:f1 (appearance_changed)
- 事实：`玻璃上蒙了盐雾`
- 地点可见：`铜灯罩、铁链、抹布、擦铜油、铜灯罩、铁链、备用灯芯、抹布`
- control（state 对照）：铜灯罩的外貌变化,玻璃上蒙了盐雾。
- routed（state）：铜灯罩的玻璃上蒙了盐雾。
- 机械差：{"mustExpress": 0, "binding": 0, "repetition": 0, "addition": 0}；control flags=['extra-object:铜灯']; routed flags=['extra-object:铜灯']
- 人工判定：

### state-016 diagnostic/final24/v14:f2 (sanity_changed)
- 事实：`12 → 9`
- 地点可见：`缆绳、渡船、船灯、系泊绳、木桩、缆绳、船灯、水面、栈桥`
- control（state 对照）：沈砚的呼吸有些发紧,手指也不太听使唤。
- routed（state）：沈砚没有像往常那样沉默,把想问
- 机械差：{"mustExpress": -1, "binding": 0, "repetition": 0, "addition": 0}；control flags=[]; routed flags=['must-missing']
- 人工判定：

### state-017 diagnostic/final24/v18:f2 (sanity_changed)
- 事实：`12 → 9`
- 地点可见：`钟绳、雾警钟、警示灯、铁链、铁链、钟架、钟绳`
- control（state 对照）：沈砚的呼吸有些发紧,手指也不太听使唤。
- routed（state）：沈砚没有像往常那样沉默,把想问
- 机械差：{"mustExpress": -1, "binding": 0, "repetition": 0, "addition": 0}；control flags=[]; routed flags=['must-missing']
- 人工判定：

### state-018 diagnostic/final24/v19:f1 (sanity_changed)
- 事实：`12 → 9`
- 地点可见：`潮汐簿、铜灯、干纸、墨、天窗、长桌、门槛、铜灯`
- control（state 对照）：叶知微的呼吸有些发紧,手指也不太听使唤。
- routed（state）：叶知微的呼吸慢慢匀下来,手指也不太听使唤。
- 机械差：{"mustExpress": -1, "binding": 0, "repetition": 0, "addition": 0}；control flags=[]; routed flags=['must-missing']
- 人工判定：

### state-019 diagnostic/final24/v20:f1 (sanity_changed)
- 事实：`9 → 12`
- 地点可见：`缆绳、渡船、船灯、系泊绳、木桩、缆绳、船灯、水面、栈桥`
- control（state 对照）：沈砚的呼吸慢慢匀下来,胸口那点发紧的感觉散了。
- routed（state）：沈砚松开手,才发现自己一直提着的那口气落回去了。
- 机械差：{"mustExpress": 0, "binding": 0, "repetition": 0, "addition": -1}；control flags=[]; routed flags=['extra-action:松开手']
- 人工判定：

### state-020 diagnostic/object18/qa1B (appearance_changed)
- 事实：`表面结了皮`
- 地点可见：`潮汐簿、铜灯、干纸、墨、油布包、备用钥匙、天窗、长桌、门槛、铜灯`
- control（state 对照）：墨的外貌变化,表面结了皮。
- routed（state）：墨的表面结了皮。
- 机械差：{"mustExpress": 0, "binding": 0, "repetition": 0, "addition": 0}；control flags=[]; routed flags=[]
- 人工判定：

### state-021 diagnostic/object18/qa2B (appearance_changed)
- 事实：`船板裂了缝`
- 地点可见：`缆绳、渡船、船灯、系泊绳、木桩、木桩、缆绳、船灯、水面、栈桥`
- control（state 对照）：渡船的外貌变化,船板裂了缝。
- routed（state）：渡船的船板裂了缝。
- 机械差：{"mustExpress": 0, "binding": 0, "repetition": 0, "addition": 0}；control flags=[]; routed flags=[]
- 人工判定：

### state-022 diagnostic/object18/qb1A (appearance_changed)
- 事实：`烧黑了一截`
- 地点可见：`铜灯罩、灯芯、抹布、擦铜油、油壶、铜灯罩、铁链、备用灯芯、抹布`
- control（state 对照）：灯芯的外貌变化,烧黑了一截。
- routed（state）：灯芯烧黑了一截。
- 机械差：{"mustExpress": 0, "binding": 0, "repetition": 0, "addition": 0}；control flags=[]; routed flags=[]
- 人工判定：

### state-023 diagnostic/object18/qb2A (appearance_changed)
- 事实：`伞骨断了一根`
- 地点可见：`油纸伞、纸灯笼、干纸、墨、备用钥匙、纸灯笼、排水沟、石板、墙根`
- control（state 对照）：油纸伞的外貌变化,伞骨断了一根。
- routed（state）：油纸伞的伞骨断了一根。
- 机械差：{"mustExpress": 0, "binding": 0, "repetition": 0, "addition": 0}；control flags=[]; routed flags=[]
- 人工判定：

### state-024 diagnostic/object18/qd2A (appearance_changed)
- 事实：`缠的旧绳断了`
- 地点可见：`缆绳、渡船、船灯、系泊绳、木桩、木桩、缆绳、船灯、水面、栈桥`
- control（state 对照）：木桩上缠的旧绳断了。
- routed（state）：木桩的缠的旧绳断了。
- 机械差：{"mustExpress": 0, "binding": 0, "repetition": 0, "addition": 0}；control flags=[]; routed flags=[]
- 人工判定：

### state-025 diagnostic/object18/qd2B (appearance_changed)
- 事实：`中间断了一股`
- 地点可见：`缆绳、渡船、船灯、系泊绳、木桩、木桩、缆绳、船灯、水面、栈桥`
- control（state 对照）：缆绳的外貌变化,中间断了一股。
- routed（state）：缆绳的中间断了一股。
- 机械差：{"mustExpress": 0, "binding": 0, "repetition": 0, "addition": 0}；control flags=[]; routed flags=[]
- 人工判定：

### state-026 diagnostic/object18/qd3A (appearance_changed)
- 事实：`拧不干`
- 地点可见：`铜灯罩、灯芯、抹布、擦铜油、油壶、铜灯罩、铁链、备用灯芯、抹布`
- control（state 对照）：抹布的外貌变化,拧不干。
- routed（state）：抹布的外貌变化,手指也不太听使唤。
- 机械差：{"mustExpress": -1, "binding": 0, "repetition": 0, "addition": -1}；control flags=[]; routed flags=['must-missing', 'extra-object:手']
- 人工判定：

### state-027 diagnostic/object18/qd3B (appearance_changed)
- 事实：`洒了半罐`
- 地点可见：`铜灯罩、灯芯、抹布、擦铜油、油壶、铜灯罩、铁链、备用灯芯、抹布`
- control（state 对照）：擦铜油的外貌变化,洒了半罐。
- routed（state）：擦铜油洒了半罐。
- 机械差：{"mustExpress": 0, "binding": 0, "repetition": 0, "addition": 0}；control flags=['extra-object:铜油']; routed flags=['extra-object:铜油']
- 人工判定：

### state-028 round/fixture-r1/f0 (appearance_changed)
- 事实：`袖口沾了雨`
- 地点可见：`外套、铜钥匙、黑板、重门、书、背包、校徽、手机、水瓶、硬币`
- control（state 对照）：林川的袖口沾了雨。
- routed（state）：林川的袖口沾了雨,短句。
- 机械差：{"mustExpress": 0, "binding": 0, "repetition": 0, "addition": 0}；control flags=[]; routed flags=[]
- 人工判定：

### state-029 round/fixture-r1/f1 (appearance_changed)
- 事实：`指节发白`
- 地点可见：`外套、铜钥匙、黑板、重门、书、背包、校徽、手机、水瓶、硬币`
- control（state 对照）：林川的指节发白,指节发白。
- routed（state）：林川的指节发白,短句没有催。
- 机械差：{"mustExpress": 0, "binding": 0, "repetition": 1, "addition": 0}；control flags=['semantic-repeat:指节']; routed flags=[]
- 人工判定：

### state-030 round/fixture-r1/f3 (appearance_changed)
- 事实：`鞋底沾了泥`
- 地点可见：`外套、铜钥匙、黑板、重门、书、背包、校徽、手机、水瓶、硬币`
- control（state 对照）：陈默的鞋底沾了泥。
- routed（state）：陈默的鞋底沾了泥,泥。
- 机械差：{"mustExpress": 0, "binding": 0, "repetition": -1, "addition": 0}；control flags=[]; routed flags=['semantic-repeat:泥']
- 人工判定：

### state-031 round/fixture-r2/f1 (appearance_changed)
- 事实：`掌心出汗`
- 地点可见：`外套、铜钥匙、黑板、重门、书、背包、校徽、手机、水瓶、硬币`
- control（state 对照）：林川的掌心出汗,掌心出汗。
- routed（state）：林川的掌心出汗,短句没有催。
- 机械差：{"mustExpress": 0, "binding": 0, "repetition": 1, "addition": 0}；control flags=['semantic-repeat:掌心']; routed flags=[]
- 人工判定：

### state-032 round/fixture-r2/f2 (appearance_changed)
- 事实：`钟绳磨出了毛边`
- 地点可见：`外套、铜钥匙、黑板、重门、书、背包、校徽、手机、水瓶、硬币`
- control（state 对照）：周宁的钟绳磨出了毛边。
- routed（state）：钟绳磨出了毛边。
- 机械差：{"mustExpress": -1, "binding": -1, "repetition": 0, "addition": 0}；control flags=[]; routed flags=['must-missing', 'binding']
- 人工判定：

### state-033 round/fixture-r2/f4 (appearance_changed)
- 事实：`鬓发被雾打湿`
- 地点可见：`外套、铜钥匙、黑板、重门、书、背包、校徽、手机、水瓶、硬币`
- control（state 对照）：陈默的鬓发被雾打湿。
- routed（state）：陈默的鬓发被雾打湿,短句写完。
- 机械差：{"mustExpress": 0, "binding": 0, "repetition": 0, "addition": 0}；control flags=[]; routed flags=[]
- 人工判定：

### state-034 round/fixture-r3/f0 (appearance_changed)
- 事实：`被雨打湿半幅`
- 地点可见：`外套、铜钥匙、黑板、重门、书、背包、校徽、手机、水瓶、硬币`
- control（state 对照）：林川的外套被雨打湿半幅。
- routed（state）：林川被雨打湿半幅。
- 机械差：{"mustExpress": 0, "binding": 0, "repetition": 0, "addition": 0}；control flags=[]; routed flags=[]
- 人工判定：

### state-035 round/fixture-r3/f1 (appearance_changed)
- 事实：`袖口开了线`
- 地点可见：`外套、铜钥匙、黑板、重门、书、背包、校徽、手机、水瓶、硬币`
- control（state 对照）：林川的袖口开了线。
- routed（state）：林川的袖口开了线,短句。
- 机械差：{"mustExpress": 0, "binding": 0, "repetition": 0, "addition": 0}；control flags=[]; routed flags=[]
- 人工判定：

### state-036 round/fixture-r3/f3 (appearance_changed)
- 事实：`鞋跟磨塌了`
- 地点可见：`外套、铜钥匙、黑板、重门、书、背包、校徽、手机、水瓶、硬币`
- control（state 对照）：陈默的鞋跟磨塌了,鞋跟磨塌了。
- routed（state）：陈默的鞋跟磨塌了,纸张了张嘴。
- 机械差：{"mustExpress": 0, "binding": 0, "repetition": 1, "addition": 0}；control flags=['semantic-repeat:鞋跟']; routed flags=[]
- 人工判定：

### state-037 round/fixture-r4/f0 (appearance_changed)
- 事实：`围巾松开一截`
- 地点可见：`外套、铜钥匙、黑板、重门、书、背包、校徽、手机、水瓶、硬币`
- control（state 对照）：林川的围巾松开一截。
- routed（state）：林川的围巾松开一截,纸张了张嘴。
- 机械差：{"mustExpress": 0, "binding": 0, "repetition": 0, "addition": 0}；control flags=[]; routed flags=[]
- 人工判定：

### state-038 round/fixture-r4/f1 (appearance_changed)
- 事实：`脸色发白`
- 地点可见：`外套、铜钥匙、黑板、重门、书、背包、校徽、手机、水瓶、硬币`
- control（state 对照）：林川的脸色发白,脸色发白。
- routed（state）：林川的脸色发白,短句没有催。
- 机械差：{"mustExpress": 0, "binding": 0, "repetition": 1, "addition": 0}；control flags=['semantic-repeat:脸色']; routed flags=[]
- 人工判定：

### state-039 round/fixture-r4/f4 (appearance_changed)
- 事实：`肩头落着灰`
- 地点可见：`外套、铜钥匙、黑板、重门、书、背包、校徽、手机、水瓶、硬币`
- control（state 对照）：陈默的肩头落着灰,肩头落着灰。
- routed（state）：陈默的肩头落着灰。
- 机械差：{"mustExpress": 0, "binding": 0, "repetition": 1, "addition": 0}；control flags=['semantic-repeat:肩头']; routed flags=[]
- 人工判定：

### state-040 round/fixture-r5/f1 (appearance_changed)
- 事实：`脚踝肿了一块`
- 地点可见：`外套、铜钥匙、黑板、重门、书、背包、校徽、手机、水瓶、硬币`
- control（state 对照）：林川的脚踝肿了一块。
- routed（state）：林川的脚踝肿了一块,纸张了张嘴。
- 机械差：{"mustExpress": 0, "binding": 0, "repetition": 0, "addition": 0}；control flags=[]; routed flags=[]
- 人工判定：

### state-041 round/fixture-r5/f2 (appearance_changed)
- 事实：`衣领被雨浸透`
- 地点可见：`外套、铜钥匙、黑板、重门、书、背包、校徽、手机、水瓶、硬币`
- control（state 对照）：周宁的衣领被雨浸透,衣领被雨浸透。
- routed（state）：周宁的衣领被雨浸透,贴在手腕上。
- 机械差：{"mustExpress": 0, "binding": 0, "repetition": 1, "addition": -1}；control flags=['semantic-repeat:衣领']; routed flags=['extra-object:手腕']
- 人工判定：

### state-042 round/fixture-r5/f4 (appearance_changed)
- 事实：`膝盖沾了泥`
- 地点可见：`外套、铜钥匙、黑板、重门、书、背包、校徽、手机、水瓶、硬币`
- control（state 对照）：陈默的膝盖沾了泥。
- routed（state）：陈默的膝盖沾了泥,泥。
- 机械差：{"mustExpress": 0, "binding": 0, "repetition": -1, "addition": 0}；control flags=[]; routed flags=['semantic-repeat:泥']
- 人工判定：

### state-043 round/train-r1/f0 (appearance_changed)
- 事实：`袖口沾了雨`
- 地点可见：`外套、铜钥匙、黑板、重门、书、背包、校徽、手机、水瓶、硬币`
- control（state 对照）：沈砚的袖口沾了雨。
- routed（state）：沈砚的袖口沾了雨,短句没有了。
- 机械差：{"mustExpress": 0, "binding": 0, "repetition": 0, "addition": 0}；control flags=[]; routed flags=[]
- 人工判定：

### state-044 round/train-r1/f1 (appearance_changed)
- 事实：`指节发白`
- 地点可见：`外套、铜钥匙、黑板、重门、书、背包、校徽、手机、水瓶、硬币`
- control（state 对照）：沈砚的指节发白,指节发白。
- routed（state）：沈砚的指节发白,短句没有了。
- 机械差：{"mustExpress": 0, "binding": 0, "repetition": 1, "addition": 0}；control flags=['semantic-repeat:指节']; routed flags=[]
- 人工判定：

### state-045 round/train-r1/f3 (appearance_changed)
- 事实：`鞋底沾了泥`
- 地点可见：`外套、铜钥匙、黑板、重门、书、背包、校徽、手机、水瓶、硬币`
- control（state 对照）：叶知微的鞋底沾了泥。
- routed（state）：叶知微的鞋底沾了泥,泥。
- 机械差：{"mustExpress": 0, "binding": 0, "repetition": -1, "addition": 0}；control flags=[]; routed flags=['semantic-repeat:泥']
- 人工判定：

### state-046 round/train-r2/f0 (appearance_changed)
- 事实：`灯罩蒙了灰`
- 地点可见：`外套、铜钥匙、黑板、重门、书、背包、校徽、手机、水瓶、硬币`
- control（state 对照）：沈砚的灯罩蒙了灰,灯罩蒙了灰。
- routed（state）：沈砚的灯罩蒙了灰。
- 机械差：{"mustExpress": 0, "binding": 0, "repetition": 1, "addition": 0}；control flags=['semantic-repeat:灯罩']; routed flags=[]
- 人工判定：

### state-047 round/train-r2/f1 (appearance_changed)
- 事实：`掌心出汗`
- 地点可见：`外套、铜钥匙、黑板、重门、书、背包、校徽、手机、水瓶、硬币`
- control（state 对照）：沈砚的掌心出汗,掌心出汗。
- routed（state）：沈砚的掌心出汗,短句没有再说了。
- 机械差：{"mustExpress": 0, "binding": 0, "repetition": 1, "addition": 0}；control flags=['semantic-repeat:掌心']; routed flags=[]
- 人工判定：

### state-048 round/train-r2/f4 (appearance_changed)
- 事实：`鬓发被雾打湿`
- 地点可见：`外套、铜钥匙、黑板、重门、书、背包、校徽、手机、水瓶、硬币`
- control（state 对照）：叶知微的鬓发被雾打湿,脸上没有雾打湿。
- routed（state）：叶知微的鬓发被雾打湿,短句没有了。
- 机械差：{"mustExpress": 0, "binding": 0, "repetition": 1, "addition": 0}；control flags=['semantic-repeat:雾打']; routed flags=[]
- 人工判定：

### state-049 round/train-r3/f0 (appearance_changed)
- 事实：`被雨打湿半幅`
- 地点可见：`外套、铜钥匙、黑板、重门、书、背包、校徽、手机、水瓶、硬币`
- control（state 对照）：沈砚的外貌变化,被雨打湿半幅。
- routed（state）：沈砚被雨打湿半幅,短句没有了。
- 机械差：{"mustExpress": 0, "binding": 0, "repetition": 0, "addition": 0}；control flags=[]; routed flags=[]
- 人工判定：

### state-050 round/train-r3/f1 (appearance_changed)
- 事实：`袖口开了线`
- 地点可见：`外套、铜钥匙、黑板、重门、书、背包、校徽、手机、水瓶、硬币`
- control（state 对照）：沈砚的袖口开了线,袖口开了线。
- routed（state）：沈砚的袖口开了线,贴在手腕上。
- 机械差：{"mustExpress": 0, "binding": 0, "repetition": 1, "addition": -1}；control flags=['semantic-repeat:袖口']; routed flags=['extra-object:手腕']
- 人工判定：

### state-051 round/train-r3/f3 (appearance_changed)
- 事实：`鞋跟磨塌了`
- 地点可见：`外套、铜钥匙、黑板、重门、书、背包、校徽、手机、水瓶、硬币`
- control（state 对照）：叶知微的鞋跟磨塌了,鞋跟磨塌了。
- routed（state）：叶知微的鞋跟磨塌了,手腕磨塌了。
- 机械差：{"mustExpress": 0, "binding": 0, "repetition": 0, "addition": -1}；control flags=['semantic-repeat:鞋跟']; routed flags=['semantic-repeat:磨塌', 'extra-object:手腕']
- 人工判定：

### state-052 round/train-r4/f0 (appearance_changed)
- 事实：`围巾松开一截`
- 地点可见：`外套、铜钥匙、黑板、重门、书、背包、校徽、手机、水瓶、硬币`
- control（state 对照）：沈砚的围巾松开一截。
- routed（state）：沈砚的围巾松开一截,纸张了张嘴。
- 机械差：{"mustExpress": 0, "binding": 0, "repetition": 0, "addition": 0}；control flags=[]; routed flags=[]
- 人工判定：

### state-053 round/train-r4/f1 (appearance_changed)
- 事实：`脸色发白`
- 地点可见：`外套、铜钥匙、黑板、重门、书、背包、校徽、手机、水瓶、硬币`
- control（state 对照）：沈砚的脸色发白,脸色发白。
- routed（state）：沈砚的脸色发白,发白。
- 机械差：{"mustExpress": 0, "binding": 0, "repetition": 0, "addition": 0}；control flags=['semantic-repeat:脸色']; routed flags=['semantic-repeat:发白']
- 人工判定：

### state-054 round/train-r4/f4 (appearance_changed)
- 事实：`肩头落着灰`
- 地点可见：`外套、铜钥匙、黑板、重门、书、背包、校徽、手机、水瓶、硬币`
- control（state 对照）：叶知微的肩头落着灰,肩头落着灰。
- routed（state）：叶知微的肩头落着灰,心跳才慢下来。
- 机械差：{"mustExpress": 0, "binding": 0, "repetition": 1, "addition": 0}；control flags=['semantic-repeat:肩头']; routed flags=[]
- 人工判定：

### state-055 round/train-r5/f1 (appearance_changed)
- 事实：`脚踝肿了一块`
- 地点可见：`外套、铜钥匙、黑板、重门、书、背包、校徽、手机、水瓶、硬币`
- control（state 对照）：沈砚的脚踝肿了一块。
- routed（state）：沈砚的脚踝肿了一块,纸张了张嘴。
- 机械差：{"mustExpress": 0, "binding": 0, "repetition": 0, "addition": 0}；control flags=[]; routed flags=[]
- 人工判定：

### state-056 round/train-r5/f2 (appearance_changed)
- 事实：`衣领被雨浸透`
- 地点可见：`外套、铜钥匙、黑板、重门、书、背包、校徽、手机、水瓶、硬币`
- control（state 对照）：顾行舟的衣领被雨浸透,衣领被雨浸透。
- routed（state）：顾行舟的衣领被雨浸透,贴在手腕上。
- 机械差：{"mustExpress": 0, "binding": 0, "repetition": 1, "addition": -1}；control flags=['semantic-repeat:衣领']; routed flags=['extra-object:手腕']
- 人工判定：

### state-057 round/train-r5/f3 (appearance_changed)
- 事实：`指尖磨出茧`
- 地点可见：`外套、铜钥匙、黑板、重门、书、背包、校徽、手机、水瓶、硬币`
- control（state 对照）：叶知微的指尖磨出茧。
- routed（state）：叶知微的指尖磨出茧,短句是叶知微的。
- 机械差：{"mustExpress": 0, "binding": 0, "repetition": 0, "addition": 0}；control flags=[]; routed flags=[]
- 人工判定：

### state-058 round/train-r5/f4 (appearance_changed)
- 事实：`膝盖沾了泥`
- 地点可见：`外套、铜钥匙、黑板、重门、书、背包、校徽、手机、水瓶、硬币`
- control（state 对照）：叶知微的膝盖沾了泥。
- routed（state）：叶知微的膝盖沾了泥,泥。
- 机械差：{"mustExpress": 0, "binding": 0, "repetition": -1, "addition": 0}；control flags=[]; routed flags=['semantic-repeat:泥']
- 人工判定：

## same text with mechanical flags (2 cases)

These are not passes. The two arms produced the same text; the defect belongs to both. Additional common defects found by the manual scan are listed in route-split-manual-review-v1.json.

### common-001 diagnostic/cf24/t11:f0 (moved)
- 事实：`潮生巷 → 旧灯塔`
- 共同输出：沈砚从潮生巷一路走到旧灯塔脚下,抬头看了看塔身。
- flags：control=['extra-action:抬头', 'extra-object:脚']; routed=['extra-action:抬头', 'extra-object:脚']
- 机械差：{"mustExpress": 0, "binding": 0, "repetition": 0, "addition": 0}

### common-002 diagnostic/object18/qb1B (appearance_changed)
- 事实：`被擦得发亮`
- 共同输出：铜灯罩被擦得发亮。
- flags：control=['extra-object:铜灯']; routed=['extra-object:铜灯']
- 机械差：{"mustExpress": 0, "binding": 0, "repetition": 0, "addition": 0}
