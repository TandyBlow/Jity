# Real semantic spot-check

Four states: present / absent / insufficient / conflict. conflict is the fix set; insufficient and conflict are not negative samples.

Counts: {"info:absent": 1, "env:insufficient": 6, "info:insufficient": 3, "info:present": 3, "env:conflict": 1}

## sc01-dialogue-nono-neutrality (test, cache)
- action: 我向诺诺问清：现在红蓝两方各控制到哪里，我能不能不加入任何一方。
- state diff: {"known": false, "added": [], "removed": []}
- info: absent proposed=False content='诺诺未答出红蓝控制区和可否中立' support='诺诺没有答出，路明非也问不出个所以然' evidence=
- env: insufficient proposed=False content='' support='' evidence=

## sc02-conflict-yard-cover (test, cache)
- action: 我贴着服务巷的低墙绕到庭院西口，低身走进庭院，躲到南端石花槽后，朝倒放长椅后的唐骁举起空着的双手，喊林亦舟是真扭伤，医护白线内停火。
- state diff: {"known": true, "added": [], "removed": []}
- info: insufficient proposed=True content='唐骁向路明非求助，事情办成了' support='唐骁向他求助，事情办成了' evidence=
- env: insufficient proposed=True content='从西侧服务巷进入中央庭院，躲到南端石花槽后' support='我贴着服务巷的低墙绕到庭院西口，低身走进庭院，躲到南端石花槽后' evidence=

## sc03-move-shed (test, cache)
- action: 我沿庭院西侧退回服务巷，走进器材棚，到器材笼外找值班员秦越。
- state diff: {"known": true, "added": [], "removed": []}
- info: present proposed=True content='秦越和芬格尔都在器材棚；芬格尔相机还在脖子上，右臂无布带。' support='芬格尔的相机还在脖子上，右臂没有布带。秦越和他都在棚里。' evidence=
- env: insufficient proposed=True content='路明非进入器材棚。' support='路明非想往服务巷走，先进了器材棚。' evidence=

## sc04-item-magazine (test, cache)
- action: 我把通用短枪弹匣乙从开盖的弹药箱里取出来，塞进演习背心的胸袋。
- state diff: {"known": true, "added": [], "removed": []}
- info: insufficient proposed=True content='芬格尔查完并把器材棚变化记下来' support='芬格尔查完，把器材棚里的变化记下来' evidence=
- env: insufficient proposed=True content='通用短枪弹匣乙被放入演习背心胸袋' support='路明非拿起开盖的弹药箱，从里面取出了通用短枪弹匣乙，塞进演习背心的胸袋' evidence=

## sc05-move-hatch (test, cache)
- action: 我退出器材棚，沿服务巷走到服务巷检修口，停在拉环旁边。
- state diff: {"known": true, "added": [], "removed": []}
- info: present proposed=True content='检修口拉环朝上，盖下有短梯，路明非手不够且未动' support='他停在检修口边，拉环朝上。盖下有短梯，他握着枪，想把梯子带下去，手不够。路明非没有动' evidence=
- env: insufficient proposed=True content='路明非从器材棚移动到服务巷检修口，停在拉环旁' support='我退出器材棚，沿服务巷走到服务巷检修口，停在拉环旁边' evidence=

## sc06-env-hatch-route (test, cache)
- action: 我抓住检修盖的拉环把盖子提开，看见下面的短梯和通往钟楼的地下检修通道，决定就走这条有掩护的路线。
- state diff: {"known": true, "added": [], "removed": []}
- info: insufficient proposed=True content='路明非完成选择有掩护路线，决定走地下检修通道' support='路明非完成了「在庭院正路、西回廊和地下检修通道之间选择一条有掩护的路线」' evidence=
- env: conflict proposed=False content='' support='' evidence=

## sc07-move-foyer (test, cache)
- action: 我离开检修口，沿服务巷绕到西侧，从西门进入门厅。
- state diff: {"known": true, "added": [], "removed": []}
- info: present proposed=True content='钟楼门厅正门半开，门后有弹着痕' support='钟楼门厅的正门半开着，木门背后有弹着痕' evidence=
- env: insufficient proposed=True content='路明非从西门进入门厅' support='从西门进入门厅' evidence=
