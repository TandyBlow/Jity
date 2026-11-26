# Real semantic spot-check

Four states: present / absent / insufficient / conflict. conflict is the fix set; insufficient and conflict are not negative samples.

Counts: {"info:absent": 1, "env:insufficient": 27, "info:insufficient": 2, "info:present": 25, "env:conflict": 1}

## sc01-dialogue-nono-neutrality (test, cache)
- action: 我向诺诺问清：现在红蓝两方各控制到哪里，我能不能不加入任何一方。
- state diff: {"known": false, "added": [], "removed": [], "changed": [], "env": []}
- info: absent proposed=False content='诺诺未答出红蓝控制区与能否中立' support='诺诺没有答出，路明非也问不出个所以然' evidence=settled|narrative
- env: insufficient proposed=False content='无环境状态实际改变' support='"env": []' evidence=settled|state

## sc02-conflict-yard-cover (test, model)
- action: 我贴着服务巷的低墙绕到庭院西口，低身走进庭院，躲到南端石花槽后，朝倒放长椅后的唐骁举起空着的双手，喊林亦舟是真扭伤，医护白线内停火。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:lu", "before": {"position": {"containerId": "lane", "slotId": "slot_wall", "relativeTo": null}, "appearance": {}, "tasks": {"task_lu_match": "pending", "task_lu_choice": "pending", "task_lu_kit": "pending", "task_lu_goggles": "pending", "task_lu_route": "pending", "task_lu_ally": "pending", "task_lu_rules": "achieved"}}, "after": {"position": {"containerId": "yard", "slotId": "slot_south_cover", "relativeTo": null}, "appearanc
- info: insufficient proposed=True content='唐骁向路明非求助，事情办成了' support='唐骁向他求助，事情办成了' evidence=narrative
- env: insufficient proposed=False content='' support='' evidence=state

## sc03-move-shed (test, model)
- action: 我沿庭院西侧退回服务巷，走进器材棚，到器材笼外找值班员秦越。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:lu", "before": {"position": {"containerId": "yard", "slotId": "slot_south_cover", "relativeTo": null}, "appearance": {}, "tasks": {"task_lu_match": "pending", "task_lu_choice": "pending", "task_lu_kit": "pending", "task_lu_goggles": "pending", "task_lu_route": "pending", "task_lu_ally": "pending", "task_lu_rules": "achieved"}}, "after": {"position": {"containerId": "shed", "slotId": "slot_cage", "relativeTo": null}, "appearanc
- info: present proposed=True content='秦越和芬格尔在器材棚里。' support='秦越和他都在棚里' evidence=narrative
- env: insufficient proposed=False content='无环境或物品状态改变' support='"env": []' evidence=state

## sc04-item-magazine (test, model)
- action: 我把通用短枪弹匣乙从开盖的弹药箱里取出来，塞进演习背心的胸袋。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "item:spare_mag2", "before": {"position": {"containerId": "ammo_box", "slotId": "slot_right", "relativeTo": null}, "appearance": {}}, "after": {"position": {"containerId": "jacket_lu", "slotId": "slot_chest", "relativeTo": null}, "appearance": {}}}], "env": []}
- info: insufficient proposed=True content='路明非将通用短枪弹匣乙从弹药箱取出塞进胸袋' support='从里面取出了通用短枪弹匣乙，塞进演习背心的胸袋' evidence=narrative
- env: insufficient proposed=False content='' support='' evidence=state

## sc05-move-hatch (test, model)
- action: 我退出器材棚，沿服务巷走到服务巷检修口，停在拉环旁边。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:lu", "before": {"position": {"containerId": "shed", "slotId": "slot_cage", "relativeTo": null}, "appearance": {}, "tasks": {"task_lu_match": "pending", "task_lu_choice": "pending", "task_lu_kit": "pending", "task_lu_goggles": "pending", "task_lu_route": "pending", "task_lu_ally": "pending", "task_lu_rules": "achieved"}}, "after": {"position": {"containerId": "hatch", "slotId": null, "relativeTo": null}, "appearance": {}, "task
- info: present proposed=True content='路明非移动至服务巷检修口，停在拉环旁' support='路明非走到服务巷检修口，停在拉环旁。' evidence=narrative
- env: insufficient proposed=False content='' support='' evidence=state

## sc06-env-hatch-route (test, model)
- action: 我抓住检修盖的拉环把盖子提开，看见下面的短梯和通往钟楼的地下检修通道，决定就走这条有掩护的路线。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:lu", "before": {"position": {"containerId": "hatch", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"task_lu_match": "pending", "task_lu_choice": "pending", "task_lu_kit": "pending", "task_lu_goggles": "pending", "task_lu_route": "pending", "task_lu_ally": "pending", "task_lu_rules": "achieved"}}, "after": {"position": {"containerId": "hatch", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"
- info: present proposed=True content='盖子没被掀开' support='盖子没被掀开' evidence=settled|narrative
- env: insufficient proposed=False content='检修盖被掀开' support='盖子没被掀开' evidence=settled|narrative

## sc07-move-foyer (test, model)
- action: 我离开检修口，沿服务巷绕到西侧，从西门进入门厅。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:lu", "before": {"position": {"containerId": "hatch", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"task_lu_match": "pending", "task_lu_choice": "pending", "task_lu_kit": "pending", "task_lu_goggles": "pending", "task_lu_route": "achieved", "task_lu_ally": "pending", "task_lu_rules": "achieved"}}, "after": {"position": {"containerId": "foyer", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {
- info: present proposed=True content='钟楼门厅正门半开，木门后有弹着痕' support='钟楼门厅的正门半开着，木门背后有弹着痕' evidence=narrative
- env: insufficient proposed=False content='' support='' evidence=state

## sc08-env-foyer-table (test, model)
- action: 我抬起压住桌腿的桌角，把门厅翻倒的长桌拖到侧墙，让出楼梯口。
- state diff: {"known": true, "added": [], "removed": [], "changed": [], "env": []}
- info: present proposed=True content='路明非把长桌拖到侧墙' support='把长桌拖到侧墙' evidence=narrative
- env: conflict proposed=True content='门厅长桌区空出' support='门厅里又少了那块地' evidence=narrative

## s01-act-move (train, model)
- action: 我沿着服务巷的墙根往器材棚方向走，脚步放轻，注意前面的门口。
- state diff: {"known": false, "added": [], "removed": [], "changed": [], "env": []}
- info: present proposed=True content='诺诺在巷口，红色识别带缠左臂，短枪口朝下，无命中标记' support='诺诺在巷口，红发用发圈束在脑后，红色识别带缠在左臂。她手里的短枪枪口压向地面，身上没有本场命中标记' evidence=narrative
- env: insufficient proposed=False content='' support='' evidence=

## s02-act-observe (train, model)
- action: 我停在原地，观察器材棚门口进出的人，记下他们身上的识别带颜色。
- state diff: {"known": true, "added": [], "removed": [], "changed": [], "env": []}
- info: present proposed=True content='诺诺的红色识别带在器材棚门口闪烁' support='诺诺的红色识别带在器材棚门口闪烁' evidence=settled
- env: insufficient proposed=False content='' support='' evidence=

## s03-act-talk (train, model)
- action: 我问器材棚门口的人，今天演习的红蓝两方各在哪些区域活动。
- state diff: {"known": true, "added": [], "removed": [], "changed": [], "env": []}
- info: present proposed=True content='西回廊那边有路，你得小心' support='西回廊那边有路，你得小心' evidence=settled
- env: insufficient proposed=False content='' support='' evidence=state

## s04-act-wait (train, model)
- action: 我在墙边等一会儿，听远处的枪声间隔，估算时间过去了多久。
- state diff: {"known": true, "added": [], "removed": [], "changed": [], "env": []}
- info: present proposed=True content='诺诺告知西回廊路线图在那边，需先确认钟楼路线' support='西回廊的路线图在那边，你得先确认钟楼的路线' evidence=settled
- env: insufficient proposed=False content='' support='' evidence=

## s05-act-inventory (train, model)
- action: 我低头检查护目镜、识别带和胸袋里的弹匣，确认都在。
- state diff: {"known": false, "added": [], "removed": [], "changed": [], "env": []}
- info: present proposed=True content='诺诺低声问路明非是否愿意留下' support='低声问道：“路明非，你……是否愿意继续留在这里？”' evidence=settled
- env: insufficient proposed=True content='诺诺的红色识别带微微发烫' support='诺诺的红色识别带在胸前微微发烫' evidence=settled

## s06-legal-failure (train, model)
- action: 我把领用台上的红色电台递给阿豹，让他转交给裁判。
- state diff: {"known": true, "added": [], "removed": [], "changed": [], "env": []}
- info: present proposed=True content='诺诺问路明非是否愿意和她一起' support='路明非，你……你愿意和我一起吗？' evidence=settled
- env: insufficient proposed=False content='' support='' evidence=

## s07-partial (train, model)
- action: 我试着把脚边的器材箱推到门口，但箱子很沉，只挪动了一点。
- state diff: {"known": true, "added": [], "removed": [], "changed": [], "env": []}
- info: present proposed=True content='诺诺请求路明非恢复短讯机与凯撒联络' support='我需要你帮我把故障短讯机恢复到能与凯撒联络的状态' evidence=settled
- env: insufficient proposed=False content='' support='' evidence=

## s08-joint-move (train, model)
- action: 我跟门口的人说一起走，两人沿器材棚外侧快走到西回廊。
- state diff: {"known": true, "added": [], "removed": [], "changed": [], "env": []}
- info: present proposed=True content='诺诺警惕地问西回廊路线图及钟楼附近听到什么' support='路明非，西回廊的路线图……我刚刚在钟楼附近听到什么？' evidence=settled
- env: insufficient proposed=False content='' support='' evidence=state

## s09-confront (train, model)
- action: 我举起手示意不介入，慢慢从对峙的两人中间走过去。
- state diff: {"known": false, "added": [], "removed": [], "changed": [], "env": []}
- info: present proposed=True content='路明非将诺诺设为目标，诺诺也将路明非设为目标。' support='"targets": [{"targetId": "nono"}]}, {"task": "targets", "key": "nono", "kind": null, "text": null, "targets": [{"targetId": "lu"}]}' evidence=settled
- env: insufficient proposed=False content='' support='' evidence=state

## s10-strike (train, model)
- action: 我突然抬手向挡路的人挥拳，想把他逼退。
- state diff: {"known": true, "added": [], "removed": [], "changed": [], "env": []}
- info: present proposed=True content='规则牌挡住拳风，他看懂了规则牌' support='被规则牌挡住。他看懂了规则牌' evidence=narrative
- env: insufficient proposed=False content='' support='' evidence=state

## s11-task-ask (train, model)
- action: 我问诺诺现在红蓝局势，以及我两边都不帮算不算违规。
- state diff: {"known": true, "added": [], "removed": [], "changed": [], "env": []}
- info: present proposed=True content='诺诺说西回廊路线接近钟楼，需确认是否愿意' support='西回廊的路线图上……有条路接近钟楼，但需要你确认是否愿意' evidence=settled
- env: insufficient proposed=False content='本回合无环境或物品状态改变' support='"added": [], "removed": [], "changed": [], "env": []' evidence=state

## s12-climb (train, model)
- action: 我沿钟楼楼梯上到二层平台，蹲在栏杆边观察庭院。
- state diff: {"known": true, "added": [], "removed": [], "changed": [], "env": []}
- info: present proposed=True content='诺诺在巷口，左臂缠着红色识别带，右袖上有红痕' support='诺诺在巷口，红发用发圈束在脑后，左臂缠着红色识别带，右袖上有红痕' evidence=narrative
- env: insufficient proposed=False content='' support='' evidence=state

## s13-already-acted (train, model)
- action: 等这一轮结束后，我再往前走一步，看看刚才同行的人有没有跟上来。
- state diff: {"known": true, "added": [], "removed": [], "changed": [], "env": []}
- info: present proposed=True content='诺诺的识别带在护目镜上闪烁，拉住路明非问是否想让她成为帮手' support='诺诺的红色识别带在路明非的护目镜上闪烁了一下，随即拉住路明非的手，语气尖锐：“你……你是不是想让我成为你的帮手？”' evidence=settled
- env: insufficient proposed=False content='' support='' evidence=state

## s14-auto-chain (train, model)
- action: 我朝钟楼门厅方向跑过去，想赶在下一波枪声前进去。
- state diff: {"known": true, "added": [], "removed": [], "changed": [], "env": []}
- info: present proposed=True content='路明非与诺诺互相设为目标' support='"targets": [{"targetId": "nono"}]}, {"task": "targets", "key": "nono", "kind": null, "text": null, "targets": [{"targetId": "lu"}]' evidence=settled
- env: insufficient proposed=False content='' support='' evidence=state

## s15-handback (train, model)
- action: 我站着不动，等这一轮结束，看看还有没有人行动。
- state diff: {"known": true, "added": [], "removed": [], "changed": [], "env": []}
- info: present proposed=True content='诺诺本回合以路明非为目标' support='targets": [{"targetId": "lu"}]' evidence=settled
- env: insufficient proposed=False content='' support='' evidence=

## s16-time-check (train, model)
- action: 我再等一段时间，核对护目镜和识别带，记下演习还剩多久。
- state diff: {"known": true, "added": [], "removed": [], "changed": [], "env": []}
- info: present proposed=True content='演习还剩十分钟' support='演习还剩十分钟，他记下了这个时间。' evidence=narrative
- env: insufficient proposed=False content='' support='' evidence=state

## g8-t1-look-lane (train, model)
- action: 我停在服务巷的墙边，先把领用台上那张演习规则牌看清楚，再抬头打量巷口和器材棚方向。
- state diff: {"known": false, "added": [], "removed": [], "changed": [], "env": []}
- info: present proposed=True content='诺诺提醒路明非在墙边停留太久，需要确认。' support='你刚才在墙边停留的时间太久，我这边需要你确认一下' evidence=settled
- env: insufficient proposed=False content='' support='' evidence=state

## g8-t2-move-shed (train, model)
- action: 我贴着服务巷的低墙往器材棚走，进门后先看领用台后面有没有人，再找林亦舟。
- state diff: {"known": true, "added": [], "removed": [], "changed": [], "env": []}
- info: present proposed=True content='诺诺问路明非是否愿意继续留在这里' support='路明非，你……是否愿意继续留在这里？' evidence=settled
- env: insufficient proposed=False content='' support='' evidence=state

## g8-t3-talk-lin (train, model)
- action: 我蹲下来问林亦舟脚踝怎么样，那条断掉的蓝布带是在哪儿弄断的。
- state diff: {"known": true, "added": [], "removed": [], "changed": [], "env": []}
- info: present proposed=True content='断掉的蓝布带散开，露出新鲜弹痕' support='断掉的蓝布带在地面散开，露出那道新鲜的弹痕。' evidence=narrative
- env: insufficient proposed=False content='无环境或物品状态改变' support='"env": []' evidence=state

## g8-t4-joint-move (train, model)
- action: 我跟诺诺说一起走，两人沿着器材棚外侧低姿快走到西回廊，贴着廊柱停住。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:lu", "before": {"position": {"containerId": "lane", "slotId": "slot_wall", "relativeTo": null}, "appearance": {}, "tasks": {"task_lu_match": "pending", "task_lu_choice": "pending", "task_lu_kit": "pending", "task_lu_goggles": "pending", "task_lu_route": "pending", "task_lu_ally": "pending", "task_lu_rules": "achieved"}}, "after": {"position": {"containerId": "west_arcade", "slotId": "slot_pillar3", "relativeTo": null}, "appear
- info: present proposed=True content='林亦舟在第三根廊柱，左脚踝肿起' support='林亦舟背靠第三根廊柱，蓝色识别带沾着灰，左脚踝在鞋帮上方肿起' evidence=settled|narrative
- env: insufficient proposed=False content='' support='' evidence=settled|state
