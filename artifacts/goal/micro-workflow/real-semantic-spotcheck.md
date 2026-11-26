# Real semantic spot-check

Four states: present / absent / insufficient / conflict. conflict is the fix set; insufficient and conflict are not negative samples.

Counts: {"info:absent": 87, "env:insufficient": 23, "info:insufficient": 86, "env:absent": 82, "env:conflict": 19, "env:present": 52, "info:present": 3}

## sc01-dialogue-nono-neutrality (test, cache, scenario)
- action: 我向诺诺问清：现在红蓝两方各控制到哪里，我能不能不加入任何一方。
- state diff: {"known": false, "added": [], "removed": [], "changed": [], "env": []}
- info: absent proposed=False content='诺诺未答出红蓝控制区与能否中立' support='诺诺没有答出，路明非也问不出个所以然' evidence=settled|narrative
- env: insufficient proposed=False content='无环境状态实际改变' support='"env": []' evidence=settled|state

## sc02-conflict-yard-cover (test, cache, scenario)
- action: 我贴着服务巷的低墙绕到庭院西口，低身走进庭院，躲到南端石花槽后，朝倒放长椅后的唐骁举起空着的双手，喊林亦舟是真扭伤，医护白线内停火。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:lu", "before": {"position": {"containerId": "lane", "slotId": "slot_wall", "relativeTo": null}, "appearance": {}, "tasks": {"task_lu_match": "pending", "task_lu_choice": "pending", "task_lu_kit": "pending", "task_lu_goggles": "pending", "task_lu_route": "pending", "task_lu_ally": "pending", "task_lu_rules": "achieved"}}, "after": {"position": {"containerId": "yard", "slotId": "slot_south_cover", "relativeTo": null}, "appearanc
- info: insufficient proposed=True content='唐骁向路明非求助，事情办成了' support='唐骁向他求助，事情办成了' evidence=narrative
- env: absent proposed=False content='' support='' evidence=state

## sc03-move-shed (test, cache, scenario)
- action: 我沿庭院西侧退回服务巷，走进器材棚，到器材笼外找值班员秦越。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:lu", "before": {"position": {"containerId": "yard", "slotId": "slot_south_cover", "relativeTo": null}, "appearance": {}, "tasks": {"task_lu_match": "pending", "task_lu_choice": "pending", "task_lu_kit": "pending", "task_lu_goggles": "pending", "task_lu_route": "pending", "task_lu_ally": "pending", "task_lu_rules": "achieved"}}, "after": {"position": {"containerId": "shed", "slotId": "slot_cage", "relativeTo": null}, "appearanc
- info: insufficient proposed=True content='秦越和芬格尔在器材棚里。' support='秦越和他都在棚里' evidence=narrative
- env: absent proposed=False content='无环境或物品状态改变' support='"env": []' evidence=state

## sc04-item-magazine (test, cache, scenario)
- action: 我把通用短枪弹匣乙从开盖的弹药箱里取出来，塞进演习背心的胸袋。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "item:spare_mag2", "before": {"position": {"containerId": "ammo_box", "slotId": "slot_right", "relativeTo": null}, "appearance": {}}, "after": {"position": {"containerId": "jacket_lu", "slotId": "slot_chest", "relativeTo": null}, "appearance": {}}}], "env": []}
- info: insufficient proposed=True content='路明非将通用短枪弹匣乙从弹药箱取出塞进胸袋' support='从里面取出了通用短枪弹匣乙，塞进演习背心的胸袋' evidence=narrative
- env: absent proposed=False content='' support='' evidence=state

## sc05-move-hatch (test, cache, scenario)
- action: 我退出器材棚，沿服务巷走到服务巷检修口，停在拉环旁边。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:lu", "before": {"position": {"containerId": "shed", "slotId": "slot_cage", "relativeTo": null}, "appearance": {}, "tasks": {"task_lu_match": "pending", "task_lu_choice": "pending", "task_lu_kit": "pending", "task_lu_goggles": "pending", "task_lu_route": "pending", "task_lu_ally": "pending", "task_lu_rules": "achieved"}}, "after": {"position": {"containerId": "hatch", "slotId": null, "relativeTo": null}, "appearance": {}, "task
- info: absent proposed=True content='路明非移动至服务巷检修口，停在拉环旁' support='路明非走到服务巷检修口，停在拉环旁。' evidence=narrative
- env: absent proposed=False content='' support='' evidence=state

## sc06-env-hatch-route (test, cache, scenario)
- action: 我抓住检修盖的拉环把盖子提开，看见下面的短梯和通往钟楼的地下检修通道，决定就走这条有掩护的路线。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:lu", "before": {"position": {"containerId": "hatch", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"task_lu_match": "pending", "task_lu_choice": "pending", "task_lu_kit": "pending", "task_lu_goggles": "pending", "task_lu_route": "pending", "task_lu_ally": "pending", "task_lu_rules": "achieved"}}, "after": {"position": {"containerId": "hatch", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"
- info: insufficient proposed=True content='盖子没被掀开' support='盖子没被掀开' evidence=settled|narrative
- env: conflict proposed=False content='检修盖被掀开' support='盖子没被掀开' evidence=settled|narrative

## sc07-move-foyer (test, cache, scenario)
- action: 我离开检修口，沿服务巷绕到西侧，从西门进入门厅。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:lu", "before": {"position": {"containerId": "hatch", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"task_lu_match": "pending", "task_lu_choice": "pending", "task_lu_kit": "pending", "task_lu_goggles": "pending", "task_lu_route": "achieved", "task_lu_ally": "pending", "task_lu_rules": "achieved"}}, "after": {"position": {"containerId": "foyer", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {
- info: insufficient proposed=True content='钟楼门厅正门半开，木门后有弹着痕' support='钟楼门厅的正门半开着，木门背后有弹着痕' evidence=narrative
- env: absent proposed=False content='' support='' evidence=state

## sc08-env-foyer-table (test, cache, scenario)
- action: 我抬起压住桌腿的桌角，把门厅翻倒的长桌拖到侧墙，让出楼梯口。
- state diff: {"known": true, "added": [], "removed": [], "changed": [], "env": []}
- info: absent proposed=True content='路明非把长桌拖到侧墙' support='把长桌拖到侧墙' evidence=narrative
- env: conflict proposed=True content='门厅长桌区空出' support='门厅里又少了那块地' evidence=narrative

## sm-e-success-1 (train, cache, env_success)
- action: 我抓住检修盖的拉环，把服务巷检修盖提开，露出下面的短梯。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:caesar", "before": {"position": {"containerId": "red_rally", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"task_caesar_win": "pending", "task_caesar_contact": "pending", "task_caesar_bridge": "pending", "task_caesar_tang": "pending", "task_caesar_flag": "pending"}}, "after": {"position": {"containerId": "red_rally", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"task_caesar_win": "pending
- info: absent proposed=True content='路明非把服务巷检修盖提开，露出短梯（只完成一部分）' support='路明非抓住检修盖的拉环，把服务巷检修盖提开，露出下面的短梯。（只完成一部分）' evidence=settled
- env: present proposed=True content='hatch_cover:已被部分提开' support='hatch_cover:已被部分提开' evidence=settled

## sm-e-move-1 (train, cache, env_irrelevant_move)
- action: 我走进中央庭院。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:lu", "before": {"position": {"containerId": "lane", "slotId": "slot_wall", "relativeTo": null}, "appearance": {}, "tasks": {"task_lu_match": "pending", "task_lu_choice": "pending", "task_lu_kit": "pending", "task_lu_goggles": "pending", "task_lu_route": "pending", "task_lu_ally": "pending", "task_lu_rules": "achieved"}}, "after": {"position": {"containerId": "yard", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks
- info: absent proposed=True content='路明非走进中央庭院。' support='路明非走进中央庭院。（达到目的）；去向=lu:yard' evidence=settled
- env: absent proposed=False content='' support='' evidence=state

## sm-e-success-2 (train, cache, env_success)
- action: 我把庭院南端倒放的长椅拖开，让出石花槽后的通道。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "item:bench_cover", "before": {"position": {"containerId": "yard", "slotId": null, "relativeTo": null}, "appearance": {}}, "after": {"position": {"containerId": "yard", "slotId": null, "relativeTo": null}, "appearance": {"change_65": "已被部分拖开"}}}], "env": ["item:bench_cover"]}
- info: absent proposed=True content='路明非把庭院南端倒放的长椅拖开，只完成一部分' support='路明非把庭院南端倒放的长椅拖开，让出石花槽后的通道。（只完成一部分）' evidence=settled
- env: present proposed=True content='倒放的长椅已被部分拖开' support='已被部分拖开' evidence=state

## sm-e-transfer-1 (train, cache, env_item_transfer)
- action: 我把护目镜从胸前取下来，塞进背心的胸袋。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:caesar", "before": {"position": {"containerId": "red_rally", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"task_caesar_win": "pending", "task_caesar_contact": "pending", "task_caesar_bridge": "pending", "task_caesar_tang": "pending", "task_caesar_flag": "pending", "task_22": "pending", "task_23": "pending"}}, "after": {"position": {"containerId": "red_rally", "slotId": null, "relativeTo": null}, "appearance
- info: insufficient proposed=True content='路明非把护目镜从胸前取下塞进胸袋，仅部分完成' support='路明非把护目镜从胸前取下来，塞进背心的胸袋。（只完成一部分）' evidence=settled
- env: absent proposed=False content='' support='' evidence=

## sm-e-failure-1 (train, cache, env_failure)
- action: 我走进器材棚，用力推器材笼的挂锁，锁纹丝不动。
- state diff: {"known": true, "added": [], "removed": [], "changed": [], "env": []}
- info: absent proposed=True content='器材笼挂锁纹丝不动' support='锁纹丝不动' evidence=settled
- env: conflict proposed=False content='器材笼挂锁未变化' support='锁纹丝不动' evidence=settled

## sm-e-success-3 (train, cache, env_success)
- action: 我穿过庭院走进钟楼门厅，把虚掩的正门完全推开。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:lu", "before": {"position": {"containerId": "yard", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"task_lu_match": "pending", "task_lu_choice": "pending", "task_lu_kit": "achieved", "task_lu_goggles": "pending", "task_lu_route": "achieved", "task_lu_ally": "pending", "task_lu_rules": "achieved"}}, "after": {"position": {"containerId": "foyer", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {
- info: absent proposed=True content='路明非进入钟楼门厅并完全推开正门' support='路明非穿过庭院走进钟楼门厅，把虚掩的正门完全推开。（达到目的）' evidence=settled
- env: conflict proposed=True content='正门被完全推开' support='把虚掩的正门完全推开' evidence=settled

## sm-e-success-4 (train, cache, env_success)
- action: 我抬起压住桌腿的桌角，把门厅翻倒的长桌拖到侧墙，让出楼梯口。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:caesar", "before": {"position": {"containerId": "red_rally", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"task_caesar_win": "pending", "task_caesar_contact": "pending", "task_caesar_bridge": "pending", "task_caesar_tang": "pending", "task_caesar_flag": "pending", "task_22": "pending", "task_23": "pending", "task_92": "pending"}}, "after": {"position": {"containerId": "red_rally", "slotId": null, "relativeT
- info: absent proposed=True content='门厅里长桌被拖了一半，楼梯口还挤着那块板' support='门厅里长桌被拖了一半，楼梯口还挤着那块板' evidence=narrative
- env: present proposed=True content='门厅长桌已被部分拖开' support='环境=foyer_table:已被部分拖开' evidence=settled

## sm-e-partial-1 (train, cache, env_partial)
- action: 我抬起长桌的一端，只挪开一条能侧身过的缝，担架还是过不去。
- state diff: {"known": true, "added": [], "removed": [], "changed": [], "env": []}
- info: absent proposed=True content='路明非抬起长桌只挪开侧身缝，担架还是过不去' support='路明非抬起长桌的一端，只挪开一条能侧身过的缝，担架还是过不去' evidence=settled
- env: conflict proposed=False content='' support='' evidence=state

## sm-e-fail-2 (train, cache, env_failure)
- action: 我回身去拉钟楼地下检修门，门从里面插着门闩，拉不开。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:caesar", "before": {"position": {"containerId": "red_rally", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"task_caesar_win": "pending", "task_caesar_contact": "pending", "task_caesar_bridge": "pending", "task_caesar_tang": "pending", "task_caesar_flag": "pending", "task_22": "pending", "task_23": "pending", "task_92": "pending", "task_156": "pending"}}, "after": {"position": {"containerId": "red_rally", "sl
- info: absent proposed=True content='门从里面插着门闩，拉不开' support='门从里面插着门闩，拉不开' evidence=settled
- env: absent proposed=False content='' support='' evidence=

## sm-e-move-2 (train, cache, env_irrelevant_move)
- action: 我沿楼梯走上钟楼顶层。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:caesar", "before": {"position": {"containerId": "red_rally", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"task_caesar_win": "pending", "task_caesar_contact": "pending", "task_caesar_bridge": "pending", "task_caesar_tang": "pending", "task_caesar_flag": "pending", "task_22": "pending", "task_23": "pending", "task_92": "pending", "task_156": "pending", "task_198": "pending"}}, "after": {"position": {"contain
- info: absent proposed=True content='路明非沿楼梯走上钟楼顶层' support='路明非沿楼梯走上钟楼顶层。（达到目的）' evidence=settled
- env: absent proposed=False content='' support='' evidence=

## sm-e-success-5 (train, cache, env_success)
- action: 我推开顶层玻璃门，走到旗台外廊。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:lu", "before": {"position": {"containerId": "foyer", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"task_lu_match": "pending", "task_lu_choice": "pending", "task_lu_kit": "achieved", "task_lu_goggles": "pending", "task_lu_route": "achieved", "task_lu_ally": "pending", "task_lu_rules": "achieved"}}, "after": {"position": {"containerId": "balcony", "slotId": "slot_door", "relativeTo": null}, "appearance": {}, 
- info: insufficient proposed=True content='旗台外廊中立白旗卡在底座锁扣里，手动释放杆可见' support='钟楼旗台外廊里，中立白旗卡在底座锁扣里，侧面的手动释放杆可见' evidence=narrative
- env: conflict proposed=False content='' support='' evidence=

## sm-e-transfer-2 (train, cache, env_item_transfer)
- action: 我把中立白旗从旗座的插槽里取下来，卷好。
- state diff: {"known": true, "added": [], "removed": [], "changed": [], "env": []}
- info: absent proposed=True content='路明非把中立白旗从旗座的插槽里取下来，卷好。' support='路明非把中立白旗从旗座的插槽里取下来，卷好' evidence=settled
- env: insufficient proposed=True content='中立白旗从旗座插槽取下并卷好' support='路明非把中立白旗从旗座的插槽里取下来，卷好' evidence=settled

## sm-i-new-1 (train, cache, info_new)
- action: 我压低声音问诺诺：红方的人现在都控制着哪些方向？
- state diff: {"known": true, "added": [], "removed": [], "changed": [], "env": []}
- info: insufficient proposed=False content='未获得红方控制方向信息' support='路明非压低声音问对方：红方的人现在都控制着哪些方向？（只完成一部分）；涉及=nono' evidence=settled
- env: absent proposed=False content='无环境状态改变' support='"env": []' evidence=state

## sm-i-repeat-1 (train, cache, info_repeat)
- action: 我把同一个问题再问诺诺一遍：红方都控制着哪些方向？
- state diff: {"known": true, "added": [], "removed": [], "changed": [], "env": []}
- info: insufficient proposed=False content='未获得红方控制方向的信息' support='诺诺把问题又问了一遍，没有回答' evidence=narrative
- env: absent proposed=False content='无环境变化' support='' evidence=state

## sm-i-fail-1 (train, cache, info_failure)
- action: 我问诺诺：这次演习的口令是什么？
- state diff: {"known": true, "added": [], "removed": [], "changed": [], "env": []}
- info: absent proposed=False content='诺诺未答上口令' support='诺诺没有答上来' evidence=narrative
- env: absent proposed=False content='无环境状态变化' support='"env": []' evidence=state

## sm-i-partial-1 (train, cache, info_partial)
- action: 我问诺诺两件事：蓝方集结点在哪，口令是什么；她只答了蓝方集结点。
- state diff: {"known": true, "added": [], "removed": [], "changed": [], "env": []}
- info: absent proposed=True content='蓝方集结点' support='她只答了蓝方集结点' evidence=settled
- env: absent proposed=False content='' support='' evidence=state

## sm-i-irrelevant-1 (train, cache, info_irrelevant_known)
- action: 我把胸前的护目镜拿起来，翻看镜带有没有松。
- state diff: {"known": true, "added": [], "removed": [], "changed": [], "env": []}
- info: absent proposed=True content='路明非翻看镜带有没有松' support='路明非翻看镜带有没有松' evidence=settled
- env: absent proposed=False content='' support='' evidence=state

## sm-i-new-2 (train, cache, info_new)
- action: 我沿服务巷走进器材棚，到领用台前问芬格尔：器材笼的钥匙在谁手里？
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:lu", "before": {"position": {"containerId": "lane", "slotId": "slot_wall", "relativeTo": null}, "appearance": {}, "tasks": {"task_lu_match": "pending", "task_lu_choice": "pending", "task_lu_kit": "pending", "task_lu_goggles": "pending", "task_lu_route": "pending", "task_lu_ally": "pending", "task_lu_rules": "achieved"}}, "after": {"position": {"containerId": "shed", "slotId": "slot_counter", "relativeTo": null}, "appearance": 
- info: insufficient proposed=False content='未获得器材笼钥匙在谁手里的信息' support='路明非没有问出结果' evidence=narrative
- env: absent proposed=False content='无环境变化' support='' evidence=state

## sm-i-fail-2 (train, cache, info_failure)
- action: 我问芬格尔：地下检修通道里有没有埋伏？
- state diff: {"known": true, "added": [], "removed": [], "changed": [], "env": []}
- info: present proposed=True content='路明非问芬格尔地下检修通道里有没有埋伏（达到目的）' support='路明非问对方：地下检修通道里有没有埋伏？（达到目的）' evidence=settled
- env: absent proposed=False content='无环境状态改变' support='"env": []' evidence=state

## sm-i-irrelevant-2 (train, cache, info_irrelevant_known)
- action: 我低头核对演习背心胸袋里那只弹匣的位置。
- state diff: {"known": true, "added": [], "removed": [], "changed": [], "env": []}
- info: absent proposed=True content='路明非低头核对演习背心胸袋里那只弹匣的位置' support='路明非低头核对演习背心胸袋里那只弹匣的位置' evidence=settled
- env: absent proposed=False content='' support='' evidence=state

## sm-i-partial-2 (train, cache, info_partial)
- action: 我问秦越：器材笼里还有几副担架，笼门什么时候开；他只答了担架数量。
- state diff: {"known": true, "added": [], "removed": [], "changed": [], "env": []}
- info: absent proposed=True content='秦越只答了器材笼担架数量，未答笼门开启时间' support='他只答了担架数量' evidence=settled
- env: absent proposed=False content='无环境变化' support='"env": []' evidence=state

## sm-i-new-3 (train, cache, info_new)
- action: 我问秦越：演习结束后器材要怎么归还？
- state diff: {"known": true, "added": [], "removed": [], "changed": [], "env": []}
- info: absent proposed=False content='秦越没有回答器材归还方式' support='秦越没有立刻回答，先看了看周围' evidence=settled
- env: absent proposed=False content='' support='' evidence=state

## sm-i-repeat-2 (train, cache, info_repeat)
- action: 我再次问秦越：演习结束后器材要怎么归还？
- state diff: {"known": true, "added": [], "removed": [], "changed": [], "env": []}
- info: insufficient proposed=False content='秦越未回答器材归还方式，先看四周' support='秦越没有立刻回答，先看了看周围。' evidence=settled
- env: absent proposed=False content='无环境状态变化' support='"env": []' evidence=state

## sm-i-irrelevant-3 (train, cache, info_irrelevant_known)
- action: 我靠着领用台站了一会儿，听棚外的枪声。
- state diff: {"known": true, "added": [], "removed": [], "changed": [], "env": []}
- info: absent proposed=False content='听棚外的枪声没有成功' support='听棚外的枪声。（没有成功）' evidence=settled
- env: absent proposed=False content='无环境变化' support='"env": []' evidence=state

## sm2-e-success-1 (train, cache, env_success)
- action: 我走进器材棚，把开盖演习弹药箱的盖子完全掀开。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:lu", "before": {"position": {"containerId": "lane", "slotId": "slot_wall", "relativeTo": null}, "appearance": {}, "tasks": {"task_lu_match": "pending", "task_lu_choice": "pending", "task_lu_kit": "pending", "task_lu_goggles": "pending", "task_lu_route": "pending", "task_lu_ally": "pending", "task_lu_rules": "achieved"}}, "after": {"position": {"containerId": "shed", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks
- info: absent proposed=True content='路明非走进器材棚，把开盖演习弹药箱的盖子完全掀开' support='路明非走进器材棚，把开盖演习弹药箱的盖子完全掀开' evidence=settled
- env: present proposed=True content='开盖演习弹药箱已被掀开' support='已被掀开' evidence=state

## sm2-e-failure-1 (train, cache, env_failure)
- action: 我抓住器材笼的挂锁往下按，锁扣卡死，打不开。
- state diff: {"known": true, "added": [], "removed": [], "changed": [], "env": []}
- info: absent proposed=True content='器材笼挂锁锁扣卡死打不开' support='锁扣卡死，打不开' evidence=settled
- env: absent proposed=False content='' support='' evidence=

## sm2-e-success-2 (train, cache, env_success)
- action: 我把器材领用台推到墙边，腾出中间的过道。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:caesar", "before": {"position": {"containerId": "red_rally", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"task_caesar_win": "pending", "task_caesar_contact": "pending", "task_caesar_bridge": "pending", "task_caesar_tang": "pending", "task_caesar_flag": "pending"}}, "after": {"position": {"containerId": "red_rally", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"task_caesar_win": "pending
- info: absent proposed=True content='路明非把器材领用台推到墙边，腾出中间过道。' support='路明非把器材领用台推到墙边，腾出中间的过道。（达到目的）' evidence=settled
- env: present proposed=True content='器材领用台已被推开' support='环境=supply_counter:已被推开' evidence=settled

## sm2-e-success-3 (train, cache, env_success)
- action: 我走到东回廊，把遮光帘拉下一半，挡住半边窗口。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:lu", "before": {"position": {"containerId": "shed", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"task_lu_match": "pending", "task_lu_choice": "pending", "task_lu_kit": "pending", "task_lu_goggles": "pending", "task_lu_route": "pending", "task_lu_ally": "pending", "task_lu_rules": "achieved"}}, "after": {"position": {"containerId": "east_arcade", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks
- info: absent proposed=True content='路明非走到东回廊，把遮光帘拉下一半，挡住半边窗口' support='路明非走到东回廊，把遮光帘拉下一半，挡住半边窗口' evidence=settled
- env: present proposed=True content='遮光帘已被拉下' support='已被拉下' evidence=state

## sm2-e-move-1 (train, cache, env_irrelevant_move)
- action: 我走过跨溪小桥，进入钟楼门厅。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:lu", "before": {"position": {"containerId": "east_arcade", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"task_lu_match": "pending", "task_lu_choice": "pending", "task_lu_kit": "pending", "task_lu_goggles": "pending", "task_lu_route": "pending", "task_lu_ally": "pending", "task_lu_rules": "achieved"}}, "after": {"position": {"containerId": "foyer", "slotId": null, "relativeTo": null}, "appearance": {}, "task
- info: insufficient proposed=True content='路明非走到钟楼门厅，门半开，背后有弹着痕' support='路明非走到钟楼门厅，门半开，背后有弹着痕。' evidence=narrative
- env: absent proposed=False content='无' support='' evidence=state

## sm2-e-transfer-1 (train, cache, env_item_transfer)
- action: 我把通用短枪弹匣乙收进演习背心的胸袋。
- state diff: {"known": true, "added": [], "removed": [], "changed": [], "env": []}
- info: absent proposed=True content='路明非把通用短枪弹匣乙收进演习背心的胸袋（只完成一部分）' support='路明非把通用短枪弹匣乙收进演习背心的胸袋。（只完成一部分）' evidence=settled
- env: absent proposed=False content='' support='' evidence=state

## sm2-e-success-4 (train, cache, env_success)
- action: 我回身把门厅虚掩的正门关上。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "loc:foyer", "before": {"appearance": {}}, "after": {"appearance": {"change_141": "已被关上"}}}], "env": ["loc:foyer"]}
- info: absent proposed=True content='路明非回身把门厅虚掩的正门关上（达到目的）' support='路明非回身把门厅虚掩的正门关上。（达到目的）' evidence=settled
- env: present proposed=True content='门厅正门已被关上' support='环境=foyer:已被关上' evidence=settled

## sm2-e-failure-2 (train, cache, env_failure)
- action: 我用力拉钟楼地下检修门，门闩从里面插着，拉不开。
- state diff: {"known": true, "added": [], "removed": [], "changed": [], "env": []}
- info: absent proposed=True content='钟楼地下检修门门闩从里面插着，拉不开' support='门闩从里面插着，拉不开' evidence=settled
- env: absent proposed=False content='' support='' evidence=state

## sm4-e-success-1 (train, cache, env_success)
- action: 我走进器材棚，把弹药箱的盖子掀开，再把领用台推到墙边。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:lu", "before": {"position": {"containerId": "lane", "slotId": "slot_wall", "relativeTo": null}, "appearance": {}, "tasks": {"task_lu_match": "pending", "task_lu_choice": "pending", "task_lu_kit": "pending", "task_lu_goggles": "pending", "task_lu_route": "pending", "task_lu_ally": "pending", "task_lu_rules": "achieved"}}, "after": {"position": {"containerId": "shed", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks
- info: insufficient proposed=False content='' support='' evidence=settled
- env: present proposed=True content='弹药箱已被掀开，领用台已被推开' support='环境=ammo_box:已被掀开' evidence=settled

## sm4-e-failure-1 (train, cache, env_failure)
- action: 我把器材笼的挂锁往下按，锁扣卡死，打不开。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:caesar", "before": {"position": {"containerId": "red_rally", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"task_caesar_win": "pending", "task_caesar_contact": "pending", "task_caesar_bridge": "pending", "task_caesar_tang": "pending", "task_caesar_flag": "pending"}}, "after": {"position": {"containerId": "red_rally", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"task_caesar_win": "pending
- info: absent proposed=True content='器材笼挂锁锁扣卡死，无法打开' support='路明非尝试打开器材笼的挂锁，但锁扣卡死，无法打开' evidence=settled
- env: conflict proposed=True content='器材笼挂锁锁扣卡死' support='路明非尝试打开器材笼的挂锁，但锁扣卡死，无法打开' evidence=settled

## sm4-e-success-2 (train, cache, env_success)
- action: 我走到东回廊，把遮光帘拉下，再把低窗软垫拖到墙根。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:lu", "before": {"position": {"containerId": "shed", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"task_lu_match": "pending", "task_lu_choice": "pending", "task_lu_kit": "pending", "task_lu_goggles": "pending", "task_lu_route": "pending", "task_lu_ally": "pending", "task_lu_rules": "achieved"}}, "after": {"position": {"containerId": "east_arcade", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks
- info: insufficient proposed=False content='未获得新信息' support='想看变化，只看了一半' evidence=narrative
- env: present proposed=True content='遮光帘被拉下；低窗软垫被拖开' support='' evidence=state

## sm4-e-success-3 (train, cache, env_success)
- action: 我穿过小桥走进钟楼门厅，把长桌推到侧墙，再把正门关上。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:lu", "before": {"position": {"containerId": "east_arcade", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"task_lu_match": "pending", "task_lu_choice": "pending", "task_lu_kit": "pending", "task_lu_goggles": "pending", "task_lu_route": "pending", "task_lu_ally": "pending", "task_lu_rules": "achieved"}}, "after": {"position": {"containerId": "foyer", "slotId": null, "relativeTo": null}, "appearance": {}, "task
- info: insufficient proposed=False content='' support='' evidence=settled
- env: conflict proposed=False content='' support='' evidence=state

## sm4-e-failure-2 (train, cache, env_failure)
- action: 我把钟楼地下检修门拉开，门闩插着，拉不开。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "item:hatch_door", "before": {"position": {"containerId": "foyer", "slotId": null, "relativeTo": null}, "appearance": {}}, "after": {"position": {"containerId": "foyer", "slotId": null, "relativeTo": null}, "appearance": {"change_102": "已被拉开"}}}], "env": ["item:hatch_door"]}
- info: absent proposed=False content='' support='' evidence=settled
- env: conflict proposed=True content='钟楼地下检修门已被拉开' support='环境=hatch_door:已被拉开' evidence=settled

## sm4-e-success-4 (train, cache, env_success)
- action: 我走上顶层，把玻璃门推开，再把白旗从旗座拔出来。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:lu", "before": {"position": {"containerId": "foyer", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"task_lu_match": "pending", "task_lu_choice": "pending", "task_lu_kit": "pending", "task_lu_goggles": "pending", "task_lu_route": "pending", "task_lu_ally": "pending", "task_lu_rules": "achieved"}}, "after": {"position": {"containerId": "top", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"ta
- info: absent proposed=False content='' support='' evidence=settled
- env: present proposed=True content='顶层玻璃门已被推开' support='把玻璃门推开' evidence=settled

## sm4-e-success-5 (train, cache, env_success)
- action: 我把白旗重新插回旗座，再把玻璃门关上。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "item:balcony_door", "before": {"position": {"containerId": "top", "slotId": null, "relativeTo": null}, "appearance": {"change_123": "已被推开"}}, "after": {"position": {"containerId": "top", "slotId": null, "relativeTo": null}, "appearance": {"change_123": "已被推开", "change_144": "已被关上"}}}], "env": ["item:balcony_door"]}
- info: absent proposed=False content='' support='' evidence=settled
- env: conflict proposed=True content='玻璃门已被关上' support='玻璃门关上' evidence=narrative

## sm4-e-success-6 (train, cache, env_success)
- action: 我走下楼梯回到门厅，把正门重新打开。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:lu", "before": {"position": {"containerId": "top", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"task_lu_match": "pending", "task_lu_choice": "pending", "task_lu_kit": "pending", "task_lu_goggles": "pending", "task_lu_route": "pending", "task_lu_ally": "pending", "task_lu_rules": "achieved"}}, "after": {"position": {"containerId": "foyer", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"ta
- info: insufficient proposed=False content='' support='' evidence=settled
- env: conflict proposed=False content='' support='' evidence=settled

## sm4-e-success-7 (train, cache, env_success)
- action: 我走到庭院，把长椅扶正，再把石花槽搬回原位。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:lu", "before": {"position": {"containerId": "foyer", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"task_lu_match": "pending", "task_lu_choice": "pending", "task_lu_kit": "pending", "task_lu_goggles": "pending", "task_lu_route": "pending", "task_lu_ally": "pending", "task_lu_rules": "achieved"}}, "after": {"position": {"containerId": "yard", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"t
- info: absent proposed=False content='' support='' evidence=settled
- env: insufficient proposed=True content='庭院长椅被扶正，石花槽被搬回原位' support='把长椅扶正' evidence=settled

## sm4-e-move-1 (train, cache, env_irrelevant_move)
- action: 我戴上护目镜，沿着庭院西侧走回服务巷。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:lu", "before": {"position": {"containerId": "yard", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"task_lu_match": "pending", "task_lu_choice": "pending", "task_lu_kit": "pending", "task_lu_goggles": "pending", "task_lu_route": "pending", "task_lu_ally": "pending", "task_lu_rules": "achieved"}}, "after": {"position": {"containerId": "lane", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"ta
- info: absent proposed=False content='' support='' evidence=settled
- env: absent proposed=False content='' support='' evidence=state

## sm4-e-success-8 (train, cache, env_success)
- action: 我走到检修口，把检修盖盖回，再把手电收进包里。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:lu", "before": {"position": {"containerId": "lane", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"task_lu_match": "pending", "task_lu_choice": "pending", "task_lu_kit": "pending", "task_lu_goggles": "pending", "task_lu_route": "pending", "task_lu_ally": "pending", "task_lu_rules": "achieved"}}, "after": {"position": {"containerId": "hatch", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"t
- info: insufficient proposed=False content='' support='' evidence=settled
- env: present proposed=True content='检修盖已被盖回' support='已被盖回' evidence=settled

## sm4-e-success-9 (train, cache, env_success)
- action: 我把检修盖重新提开一条缝。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "item:hatch_cover", "before": {"position": {"containerId": "hatch", "slotId": null, "relativeTo": null}, "appearance": {"change_226": "已被盖回"}}, "after": {"position": {"containerId": "hatch", "slotId": null, "relativeTo": null}, "appearance": {"change_226": "已被盖回", "change_247": "已被提开"}}}], "env": ["item:hatch_cover"]}
- info: absent proposed=False content='' support='' evidence=settled
- env: present proposed=True content='检修盖被提开一条缝' support='路明非把检修盖重新提开一条缝' evidence=settled

## sm5-e-success-1 (train, cache, env_success)
- action: 我走进器材棚，把弹药箱的盖子掀开，再把领用台推到墙边。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:lu", "before": {"position": {"containerId": "lane", "slotId": "slot_wall", "relativeTo": null}, "appearance": {}, "tasks": {"task_lu_match": "pending", "task_lu_choice": "pending", "task_lu_kit": "pending", "task_lu_goggles": "pending", "task_lu_route": "pending", "task_lu_ally": "pending", "task_lu_rules": "achieved"}}, "after": {"position": {"containerId": "shed", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks
- info: insufficient proposed=False content='' support='' evidence=settled
- env: present proposed=True content='弹药箱已被掀开，领用台已被推开' support='环境=ammo_box:已被掀开' evidence=settled

## sm5-e-success-2 (train, cache, env_success)
- action: 我把器材领用簿翻开。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:fingel", "before": {"position": {"containerId": "shed", "slotId": "slot_counter", "relativeTo": null}, "appearance": {}, "tasks": {"task_fingel_deal": "pending", "task_fingel_map": "pending", "task_fingel_camera": "pending", "task_fingel_help": "pending", "task_fingel_soup": "pending"}}, "after": {"position": {"containerId": "shed", "slotId": "slot_counter", "relativeTo": null}, "appearance": {}, "tasks": {"task_fingel_deal": 
- info: absent proposed=False content='' support='' evidence=settled
- env: present proposed=True content='器材领用簿已被翻开' support='器材领用簿翻开' evidence=settled

## sm5-e-success-3 (train, cache, env_success)
- action: 我把笼门上的挂锁取下来，挂到墙钩上。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:nono", "before": {"position": {"containerId": "lane", "slotId": "slot_entry", "relativeTo": null}, "appearance": {}, "tasks": {"task_nono_squad": "pending", "task_nono_lu": "pending", "task_nono_battery": "pending", "task_nono_wounded": "pending", "task_nono_signal": "pending"}}, "after": {"position": {"containerId": "lane", "slotId": "slot_entry", "relativeTo": null}, "appearance": {}, "tasks": {"task_nono_squad": "achieved",
- info: absent proposed=False content='' support='' evidence=settled
- env: present proposed=True content='笼门挂锁已被挂到墙钩上' support='路明非把笼门上的挂锁取下来，挂到墙钩上' evidence=settled

## sm5-e-success-4 (train, cache, env_success)
- action: 我走进庭院，把倒放长椅扶正，再把石花槽搬到喷泉边。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:lu", "before": {"position": {"containerId": "shed", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"task_lu_match": "pending", "task_lu_choice": "pending", "task_lu_kit": "pending", "task_lu_goggles": "pending", "task_lu_route": "pending", "task_lu_ally": "pending", "task_lu_rules": "achieved"}}, "after": {"position": {"containerId": "yard", "slotId": "slot_east_cover", "relativeTo": null}, "appearance": {}, 
- info: insufficient proposed=False content='' support='' evidence=settled
- env: present proposed=True content='长椅已被扶正' support='已被扶正' evidence=settled

## sm5-e-success-5 (train, cache, env_success)
- action: 我把庭院空弹匣踢开，再把长椅拖到墙边。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:caesar", "before": {"position": {"containerId": "red_rally", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"task_caesar_win": "pending", "task_caesar_contact": "pending", "task_caesar_bridge": "pending", "task_caesar_tang": "pending", "task_caesar_flag": "pending", "task_42": "pending", "task_65": "pending"}}, "after": {"position": {"containerId": "red_rally", "slotId": null, "relativeTo": null}, "appearance
- info: absent proposed=False content='' support='' evidence=settled
- env: present proposed=True content='庭院空弹匣已被踢开，长椅已被拖开' support='路明非把庭院空弹匣踢开（达到目的）；环境=empty_magazine:已被踢开' evidence=settled

## sm5-e-success-6 (train, cache, env_success)
- action: 我走到东回廊，把遮光帘拉下，再把低窗软垫拖到墙根。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:lu", "before": {"position": {"containerId": "yard", "slotId": "slot_east_cover", "relativeTo": null}, "appearance": {}, "tasks": {"task_lu_match": "pending", "task_lu_choice": "pending", "task_lu_kit": "pending", "task_lu_goggles": "pending", "task_lu_route": "pending", "task_lu_ally": "pending", "task_lu_rules": "achieved"}}, "after": {"position": {"containerId": "east_arcade", "slotId": null, "relativeTo": null}, "appearance
- info: insufficient proposed=False content='' support='' evidence=settled
- env: present proposed=True content='东回廊遮光帘已被拉下' support='canvas_blind:已被拉下' evidence=settled

## sm5-e-success-7 (train, cache, env_success)
- action: 我把苏茜的备用弹匣收进背心，再把遮光帘拉上。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:caesar", "before": {"position": {"containerId": "red_rally", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"task_caesar_win": "pending", "task_caesar_contact": "pending", "task_caesar_bridge": "pending", "task_caesar_tang": "pending", "task_caesar_flag": "pending", "task_42": "pending", "task_65": "pending", "task_113": "pending"}}, "after": {"position": {"containerId": "red_rally", "slotId": null, "relative
- info: absent proposed=False content='' support='' evidence=settled
- env: present proposed=True content='东回廊遮光帘被拉起' support='' evidence=state

## sm5-e-success-8 (train, cache, env_success)
- action: 我走进钟楼门厅，把长桌推到侧墙，再把正门关上。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:lu", "before": {"position": {"containerId": "east_arcade", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"task_lu_match": "pending", "task_lu_choice": "pending", "task_lu_kit": "pending", "task_lu_goggles": "pending", "task_lu_route": "achieved", "task_lu_ally": "pending", "task_lu_rules": "achieved"}}, "after": {"position": {"containerId": "foyer", "slotId": null, "relativeTo": null}, "appearance": {}, "tas
- info: insufficient proposed=False content='' support='' evidence=settled
- env: conflict proposed=False content='' support='' evidence=state

## sm5-e-success-9 (train, cache, env_success)
- action: 我走上顶层，把玻璃门推开，再把蓝方信号旗从栏杆上解下来。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:lu", "before": {"position": {"containerId": "foyer", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"task_lu_match": "pending", "task_lu_choice": "pending", "task_lu_kit": "pending", "task_lu_goggles": "pending", "task_lu_route": "achieved", "task_lu_ally": "pending", "task_lu_rules": "achieved"}}, "after": {"position": {"containerId": "top", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"t
- info: absent proposed=False content='未获得新信息' support='路明非没有问出具体的答案' evidence=narrative
- env: present proposed=True content='顶层玻璃门已被推开' support='把玻璃门推开' evidence=settled

## sm5-e-success-10 (train, cache, env_success)
- action: 我走进医护处置室，把医护箱打开，再把伤情登记夹翻开。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:lu", "before": {"position": {"containerId": "top", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"task_lu_match": "pending", "task_lu_choice": "pending", "task_lu_kit": "pending", "task_lu_goggles": "pending", "task_lu_route": "achieved", "task_lu_ally": "pending", "task_lu_rules": "achieved"}}, "after": {"position": {"containerId": "aid", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"tas
- info: insufficient proposed=False content='未找到想要的记录' support='没有找到想要的记录' evidence=narrative
- env: present proposed=True content='医护箱被打开，登记夹被翻开' support='把医护箱打开' evidence=settled

## sm5-e-success-11 (train, cache, env_success)
- action: 我走进医护休息区，把保温毯叠好，再把沈澄的识别带挂到墙钩上。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:lu", "before": {"position": {"containerId": "aid", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"task_lu_match": "pending", "task_lu_choice": "pending", "task_lu_kit": "pending", "task_lu_goggles": "pending", "task_lu_route": "achieved", "task_lu_ally": "pending", "task_lu_rules": "achieved"}}, "after": {"position": {"containerId": "rest", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"ta
- info: insufficient proposed=False content='' support='' evidence=settled
- env: conflict proposed=False content='' support='' evidence=settled

## sm5-e-success-12 (train, cache, env_success)
- action: 我走进控制室，把安全事件记录单翻开，再把广播话筒推到桌角。
- state diff: {"known": true, "added": [], "removed": [], "changed": [], "env": []}
- info: insufficient proposed=False content='' support='' evidence=settled
- env: conflict proposed=False content='' support='' evidence=settled

## sm4-i-new-1 (train, cache, info_new)
- action: 我读服务巷右墙上的赛区路线图，确认地下检修通道的入口。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:caesar", "before": {"position": {"containerId": "red_rally", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"task_caesar_win": "pending", "task_caesar_contact": "pending", "task_caesar_bridge": "pending", "task_caesar_tang": "pending", "task_caesar_flag": "pending"}}, "after": {"position": {"containerId": "red_rally", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"task_caesar_win": "pending
- info: insufficient proposed=False content='路线图未确认入口' support='只完成一部分' evidence=settled
- env: absent proposed=False content='' support='' evidence=settled

## sm4-i-new-2 (train, cache, info_new)
- action: 我走到器材棚，翻看领用台上的器材领用簿，确认最后一条记录。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:lu", "before": {"position": {"containerId": "lane", "slotId": "slot_wall", "relativeTo": null}, "appearance": {}, "tasks": {"task_lu_match": "pending", "task_lu_choice": "pending", "task_lu_kit": "pending", "task_lu_goggles": "pending", "task_lu_route": "pending", "task_lu_ally": "pending", "task_lu_rules": "achieved"}}, "after": {"position": {"containerId": "shed", "slotId": "slot_counter", "relativeTo": null}, "appearance": 
- info: absent proposed=True content='确认领用簿最后一条记录' support='确认最后一条记录' evidence=settled
- env: absent proposed=False content='' support='' evidence=state

## sm4-i-irrelevant-1 (train, cache, info_irrelevant_known)
- action: 我查看器材笼里的折叠梯和安全绳。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:nono", "before": {"position": {"containerId": "lane", "slotId": "slot_entry", "relativeTo": null}, "appearance": {}, "tasks": {"task_nono_squad": "pending", "task_nono_lu": "pending", "task_nono_battery": "pending", "task_nono_wounded": "pending", "task_nono_signal": "pending"}}, "after": {"position": {"containerId": "lane", "slotId": "slot_entry", "relativeTo": null}, "appearance": {}, "tasks": {"task_nono_squad": "achieved",
- info: insufficient proposed=True content='器材笼里只有折叠梯和安全绳' support='器材笼里没有别的，只有折叠梯和安全绳' evidence=narrative
- env: absent proposed=False content='' support='' evidence=settled

## sm4-i-new-3 (train, cache, info_new)
- action: 我查看弹药箱里剩下的弹匣数量。
- state diff: {"known": true, "added": [], "removed": [], "changed": [], "env": []}
- info: insufficient proposed=False content='未获得弹匣数量信息' support='只数完了一部分' evidence=settled
- env: absent proposed=False content='' support='' evidence=state

## sm4-i-irrelevant-2 (train, cache, info_irrelevant_known)
- action: 我走到庭院，查看唐骁左臂上的红色识别带。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:lu", "before": {"position": {"containerId": "shed", "slotId": "slot_counter", "relativeTo": null}, "appearance": {}, "tasks": {"task_lu_match": "pending", "task_lu_choice": "pending", "task_lu_kit": "pending", "task_lu_goggles": "pending", "task_lu_route": "pending", "task_lu_ally": "pending", "task_lu_rules": "achieved"}}, "after": {"position": {"containerId": "yard", "slotId": null, "relativeTo": null}, "appearance": {}, "ta
- info: insufficient proposed=True content='路明非查看唐骁左臂红色识别带' support='路明非走到庭院，查看了唐骁左臂上的红色识别带' evidence=settled
- env: absent proposed=False content='' support='' evidence=settled

## sm4-i-new-4 (train, cache, info_new)
- action: 我查看喷泉池边新留下的弹着点。
- state diff: {"known": true, "added": [], "removed": [], "changed": [], "env": []}
- info: insufficient proposed=False content='未获得新信息' support='路明非查看喷泉池边新留下的弹着点。（只完成一部分）' evidence=settled
- env: absent proposed=False content='无环境变化' support='' evidence=state

## sm4-i-new-5 (train, cache, info_new)
- action: 我走进钟楼，沿楼梯到值钟间，读墙上的旗台机械检修图。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:lu", "before": {"position": {"containerId": "yard", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"task_lu_match": "pending", "task_lu_choice": "pending", "task_lu_kit": "pending", "task_lu_goggles": "pending", "task_lu_route": "pending", "task_lu_ally": "pending", "task_lu_rules": "achieved"}}, "after": {"position": {"containerId": "bell_room", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks":
- info: absent proposed=True content='路明非在值钟间查看旗台机械检修图' support='路明非走进钟楼，沿楼梯到值钟间，读墙上的旗台机械检修图' evidence=settled
- env: absent proposed=False content='' support='' evidence=settled

## sm4-i-new-6 (train, cache, info_new)
- action: 我回到西回廊，查看林亦舟扭伤的脚踝。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:lu", "before": {"position": {"containerId": "bell_room", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"task_lu_match": "pending", "task_lu_choice": "pending", "task_lu_kit": "pending", "task_lu_goggles": "pending", "task_lu_route": "pending", "task_lu_ally": "pending", "task_lu_rules": "achieved"}}, "after": {"position": {"containerId": "west_arcade", "slotId": null, "relativeTo": null}, "appearance": {}, "
- info: insufficient proposed=False content='未获得新信息' support='林亦舟的脚踝没有受伤' evidence=narrative
- env: absent proposed=False content='无环境变化' support='没有发现什么' evidence=narrative

## sm4-i-new-7 (train, cache, info_new)
- action: 我走到医护处置室，读登记台上的分诊夹板。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:lu", "before": {"position": {"containerId": "west_arcade", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"task_lu_match": "pending", "task_lu_choice": "pending", "task_lu_kit": "pending", "task_lu_goggles": "pending", "task_lu_route": "achieved", "task_lu_ally": "pending", "task_lu_rules": "achieved"}}, "after": {"position": {"containerId": "aid", "slotId": "slot_desk", "relativeTo": null}, "appearance": {},
- info: absent proposed=True content='路明非在医护处置室读分诊夹板' support='路明非走到医护处置室，读登记台上的分诊夹板' evidence=settled
- env: absent proposed=False content='' support='' evidence=state

## sm4-i-irrelevant-3 (train, cache, info_irrelevant_known)
- action: 我查看空床边的医疗箱。
- state diff: {"known": true, "added": [], "removed": [], "changed": [], "env": []}
- info: insufficient proposed=True content='医疗箱里没有东西' support='箱里没有东西' evidence=narrative
- env: absent proposed=False content='' support='' evidence=state

## sm4-i-new-8 (train, cache, info_new)
- action: 我走进控制室，听广播里宣布的剩余时间。
- state diff: {"known": true, "added": [], "removed": [], "changed": [], "env": []}
- info: absent proposed=True content='广播宣布剩余时间' support='听广播里宣布的剩余时间' evidence=settled
- env: absent proposed=False content='' support='' evidence=state

## sm4-i-irrelevant-4 (train, cache, info_irrelevant_known)
- action: 我整理背心的胸袋，确认弹匣还在。
- state diff: {"known": true, "added": [], "removed": [], "changed": [], "env": []}
- info: insufficient proposed=False content='' support='' evidence=settled
- env: absent proposed=False content='' support='' evidence=state

## sm5-i-fail-1 (train, cache, info_failure)
- action: 我问诺诺演习口令是什么。
- state diff: {"known": true, "added": [], "removed": [], "changed": [], "env": []}
- info: absent proposed=False content='诺诺未答出口令，未获得信息' support='诺诺没有答上来' evidence=narrative
- env: absent proposed=False content='' support='' evidence=state

## sm5-i-new-1 (train, cache, info_new)
- action: 我问诺诺红方控制哪个方向，她说了西侧。
- state diff: {"known": true, "added": [], "removed": [], "changed": [], "env": []}
- info: absent proposed=True content='诺诺告知红方控制西侧' support='她说了西侧' evidence=settled
- env: absent proposed=False content='' support='' evidence=settled

## sm5-i-repeat-1 (train, cache, info_repeat)
- action: 我重复问诺诺红方控制哪个方向，她再说一遍。
- state diff: {"known": true, "added": [], "removed": [], "changed": [], "env": []}
- info: insufficient proposed=True content='诺诺重复红方控制方向' support='诺诺又说了一遍' evidence=narrative
- env: absent proposed=False content='' support='' evidence=settled

## sm5-i-transfer-1 (train, cache, info_irrelevant_known)
- action: 我把护目镜递给诺诺。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "item:goggles_lu", "before": {"position": {"containerId": "lu", "slotId": "slot_body", "relativeTo": null}, "appearance": {}}, "after": {"position": {"containerId": "nono", "slotId": null, "relativeTo": null}, "appearance": {}}}], "env": []}
- info: absent proposed=False content='' support='' evidence=settled
- env: absent proposed=False content='' support='' evidence=state

## sm5-i-irrelevant-1 (train, cache, info_irrelevant_known)
- action: 我整理背心的胸袋，把弹匣按紧。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:nono", "before": {"position": {"containerId": "lane", "slotId": "slot_entry", "relativeTo": null}, "appearance": {}, "tasks": {"task_nono_squad": "pending", "task_nono_lu": "pending", "task_nono_battery": "pending", "task_nono_wounded": "pending", "task_nono_signal": "pending"}}, "after": {"position": {"containerId": "lane", "slotId": "slot_entry", "relativeTo": null}, "appearance": {}, "tasks": {"task_nono_squad": "achieved",
- info: absent proposed=False content='' support='' evidence=settled
- env: absent proposed=False content='' support='' evidence=state

## sm5-i-new-2 (train, cache, info_new)
- action: 我走到医护处置室，问顾岚空床还有几张，她答了。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:lu", "before": {"position": {"containerId": "lane", "slotId": "slot_wall", "relativeTo": null}, "appearance": {}, "tasks": {"task_lu_match": "pending", "task_lu_choice": "pending", "task_lu_kit": "pending", "task_lu_goggles": "pending", "task_lu_route": "pending", "task_lu_ally": "pending", "task_lu_rules": "achieved"}}, "after": {"position": {"containerId": "aid", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks"
- info: present proposed=True content='顾岚告知空床数量' support='问对方空床还有几张，她答了' evidence=settled
- env: absent proposed=False content='' support='' evidence=settled

## sm5-i-repeat-2 (train, cache, info_repeat)
- action: 我再问顾岚空床还有几张。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:caesar", "before": {"position": {"containerId": "red_rally", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"task_caesar_win": "pending", "task_caesar_contact": "pending", "task_caesar_bridge": "pending", "task_caesar_tang": "pending", "task_caesar_flag": "pending", "task_127": "pending"}}, "after": {"position": {"containerId": "red_rally", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"tas
- info: absent proposed=False content='顾岚未答空床数量，路明非未获新信息' support='顾岚没有答话' evidence=narrative
- env: absent proposed=False content='' support='' evidence=settled

## sm5-i-fail-2 (train, cache, info_failure)
- action: 我问顾岚演习口令。
- state diff: {"known": true, "added": [], "removed": [], "changed": [], "env": []}
- info: insufficient proposed=False content='未获得口令，仅开口询问' support='路明非想向顾岚问演习口令' evidence=narrative
- env: absent proposed=False content='' support='' evidence=state

## sm5-i-transfer-2 (train, cache, info_irrelevant_known)
- action: 我把桌上的水杯拿到手里。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:caesar", "before": {"position": {"containerId": "red_rally", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"task_caesar_win": "pending", "task_caesar_contact": "pending", "task_caesar_bridge": "pending", "task_caesar_tang": "pending", "task_caesar_flag": "pending", "task_127": "pending", "task_149": "pending", "task_150": "pending"}}, "after": {"position": {"containerId": "red_rally", "slotId": null, "relati
- info: absent proposed=False content='' support='' evidence=settled
- env: absent proposed=False content='' support='' evidence=settled

## sm5-i-repeat-3 (train, cache, info_repeat)
- action: 我问秦越器材笼里有什么，他重复了一遍。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:caesar", "before": {"position": {"containerId": "red_rally", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"task_caesar_win": "pending", "task_caesar_contact": "pending", "task_caesar_bridge": "pending", "task_caesar_tang": "pending", "task_caesar_flag": "pending", "task_127": "pending", "task_149": "achieved", "task_150": "pending", "task_200": "pending"}}, "after": {"position": {"containerId": "red_rally",
- info: insufficient proposed=False content='秦越未答出器材笼内容' support='他重复了一遍' evidence=settled
- env: absent proposed=False content='' support='' evidence=settled

## sm5-i-fail-3 (train, cache, info_failure)
- action: 我问秦越演习口令是什么。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:caesar", "before": {"position": {"containerId": "red_rally", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"task_caesar_win": "pending", "task_caesar_contact": "pending", "task_caesar_bridge": "pending", "task_caesar_tang": "pending", "task_caesar_flag": "pending", "task_127": "pending", "task_149": "achieved", "task_150": "pending", "task_200": "pending", "task_223": "pending"}}, "after": {"position": {"con
- info: insufficient proposed=False content='秦越未回答口令，路明非未获得信息' support='他问完，秦越没有回答' evidence=narrative
- env: absent proposed=False content='' support='' evidence=settled

## sm5-i-irrelevant-2 (train, cache, info_irrelevant_known)
- action: 我靠着墙听广播里的音乐。
- state diff: {"known": true, "added": [], "removed": [], "changed": [], "env": []}
- info: absent proposed=False content='' support='' evidence=settled
- env: absent proposed=False content='' support='' evidence=state

## sm6-e-success-1 (train, cache, env_success)
- action: 我走进值钟间，把工作台推到墙边，再把检修图展开。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:lu", "before": {"position": {"containerId": "lane", "slotId": "slot_wall", "relativeTo": null}, "appearance": {}, "tasks": {"task_lu_match": "pending", "task_lu_choice": "pending", "task_lu_kit": "pending", "task_lu_goggles": "pending", "task_lu_route": "pending", "task_lu_ally": "pending", "task_lu_rules": "achieved"}}, "after": {"position": {"containerId": "bell_room", "slotId": null, "relativeTo": null}, "appearance": {}, "
- info: insufficient proposed=False content='' support='' evidence=settled
- env: present proposed=True content='工作台被推到墙边，检修图被展开' support='把工作台推到墙边，把检修图展开' evidence=settled

## sm6-e-success-2 (train, cache, env_success)
- action: 我把检修图挂到墙上。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "item:maintenance_chart", "before": {"position": {"containerId": "bell_room", "slotId": null, "relativeTo": null}, "appearance": {"change_20": "已被展开"}}, "after": {"position": {"containerId": "bell_room", "slotId": null, "relativeTo": null}, "appearance": {"change_20": "已被展开", "change_41": "已被挂到"}}}], "env": ["item:maintenance_chart"]}
- info: absent proposed=False content='' support='' evidence=settled
- env: present proposed=True content='检修图已被挂到墙上' support='已被挂到' evidence=settled

## sm6-e-success-3 (train, cache, env_success)
- action: 我走进控制室，把记录单翻开，再把话筒推到桌角。
- state diff: {"known": true, "added": [], "removed": [], "changed": [], "env": []}
- info: insufficient proposed=False content='' support='' evidence=settled
- env: conflict proposed=False content='' support='' evidence=settled

## sm6-e-success-4 (train, cache, env_success)
- action: 我把记分面板转向窗口。
- state diff: {"known": true, "added": [], "removed": [], "changed": [], "env": []}
- info: absent proposed=False content='' support='' evidence=settled
- env: absent proposed=False content='' support='' evidence=state

## sm6-e-failure-1 (train, cache, env_failure)
- action: 我推控制室的门，门锁着，推不开。
- state diff: {"known": true, "added": [], "removed": [], "changed": [], "env": []}
- info: absent proposed=False content='' support='' evidence=settled
- env: conflict proposed=False content='' support='' evidence=settled

## sm6-e-success-5 (train, cache, env_success)
- action: 我走进医护处置室，把空床推到墙边，再把医护箱打开。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:lu", "before": {"position": {"containerId": "bell_room", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"task_lu_match": "pending", "task_lu_choice": "pending", "task_lu_kit": "pending", "task_lu_goggles": "pending", "task_lu_route": "pending", "task_lu_ally": "pending", "task_lu_rules": "achieved"}}, "after": {"position": {"containerId": "aid", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": 
- info: insufficient proposed=False content='未获得新信息' support='没有找到听的人' evidence=settled
- env: present proposed=True content='医护箱被打开，空床被推开' support='箱里的东西都倒在一边' evidence=state

## sm6-e-success-6 (train, cache, env_success)
- action: 我把分诊夹翻开。
- state diff: {"known": true, "added": [], "removed": [], "changed": [], "env": []}
- info: absent proposed=True content='路明非翻开分诊夹，只看到一部分内容' support='路明非把分诊夹翻开。（只完成一部分）' evidence=settled
- env: conflict proposed=False content='' support='' evidence=settled

## sm6-e-success-7 (train, cache, env_success)
- action: 我走进休息区，把保温毯叠好，再把识别带挂到墙钩上。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:lu", "before": {"position": {"containerId": "aid", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"task_lu_match": "pending", "task_lu_choice": "pending", "task_lu_kit": "achieved", "task_lu_goggles": "pending", "task_lu_route": "achieved", "task_lu_ally": "pending", "task_lu_rules": "achieved"}}, "after": {"position": {"containerId": "rest", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"t
- info: insufficient proposed=False content='' support='' evidence=settled
- env: present proposed=True content='保温毯已被叠好' support='把保温毯叠好' evidence=settled

## sm6-e-success-8 (train, cache, env_success)
- action: 我走进器材棚，把备用护目镜摆到台面，再把备用识别带挂回架子。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:lu", "before": {"position": {"containerId": "rest", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"task_lu_match": "pending", "task_lu_choice": "pending", "task_lu_kit": "achieved", "task_lu_goggles": "pending", "task_lu_route": "achieved", "task_lu_ally": "pending", "task_lu_rules": "achieved"}}, "after": {"position": {"containerId": "shed", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"
- info: insufficient proposed=False content='' support='' evidence=settled
- env: present proposed=True content='备用护目镜已被摆到台面' support='备用护目镜摆到台面' evidence=settled

## sm6-e-success-9 (train, cache, env_success)
- action: 我把领用簿合上。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:fingel", "before": {"position": {"containerId": "shed", "slotId": "slot_counter", "relativeTo": null}, "appearance": {}, "tasks": {"task_fingel_deal": "pending", "task_fingel_map": "pending", "task_fingel_camera": "pending", "task_fingel_help": "pending", "task_fingel_soup": "pending"}}, "after": {"position": {"containerId": "shed", "slotId": "slot_counter", "relativeTo": null}, "appearance": {}, "tasks": {"task_fingel_deal": 
- info: absent proposed=False content='未获得新信息' support='没有找到明显的变化' evidence=narrative
- env: present proposed=True content='领用簿已被合上' support='领用簿合上' evidence=settled

## sm6-e-success-10 (train, cache, env_success)
- action: 我把弹药箱盖子盖回。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:nono", "before": {"position": {"containerId": "lane", "slotId": "slot_entry", "relativeTo": null}, "appearance": {}, "tasks": {"task_nono_squad": "pending", "task_nono_lu": "pending", "task_nono_battery": "pending", "task_nono_wounded": "pending", "task_nono_signal": "pending"}}, "after": {"position": {"containerId": "lane", "slotId": "slot_entry", "relativeTo": null}, "appearance": {}, "tasks": {"task_nono_squad": "achieved",
- info: absent proposed=False content='' support='' evidence=settled
- env: present proposed=True content='弹药箱盖被盖回' support='弹药箱盖子盖回' evidence=settled

## sm6-e-success-11 (train, cache, env_success)
- action: 我走进庭院，把长椅拖到墙边，再把石花槽扶正。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:lu", "before": {"position": {"containerId": "shed", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"task_lu_match": "pending", "task_lu_choice": "pending", "task_lu_kit": "achieved", "task_lu_goggles": "pending", "task_lu_route": "achieved", "task_lu_ally": "pending", "task_lu_rules": "achieved"}}, "after": {"position": {"containerId": "yard", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"
- info: insufficient proposed=False content='' support='' evidence=settled
- env: present proposed=True content='长椅被拖开，石花槽被扶正' support='长椅拖到墙边' evidence=settled

## sm7-e-success-1 (train, cache, env_success)
- action: 我走进器材棚，把备用枪摆到台面，再把备用蓝带挂回架子。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:lu", "before": {"position": {"containerId": "lane", "slotId": "slot_wall", "relativeTo": null}, "appearance": {}, "tasks": {"task_lu_match": "pending", "task_lu_choice": "pending", "task_lu_kit": "pending", "task_lu_goggles": "pending", "task_lu_route": "pending", "task_lu_ally": "pending", "task_lu_rules": "achieved"}}, "after": {"position": {"containerId": "shed", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks
- info: insufficient proposed=False content='路明非未问出结果，无新信息' support='路明非没有问出结果' evidence=narrative
- env: present proposed=True content='备用蓝带已被挂回' support='' evidence=state

## sm7-e-success-2 (train, cache, env_success)
- action: 我把弹药箱盖子掀开。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "item:ammo_box", "before": {"position": {"containerId": "shed", "slotId": null, "relativeTo": null}, "appearance": {}}, "after": {"position": {"containerId": "shed", "slotId": null, "relativeTo": null}, "appearance": {"change_39": "已被掀开"}}}], "env": ["item:ammo_box"]}
- info: absent proposed=False content='' support='' evidence=settled
- env: present proposed=True content='弹药箱盖子已被掀开' support='路明非把弹药箱盖子掀开' evidence=settled

## sm7-e-success-3 (train, cache, env_success)
- action: 我走进庭院，把空弹匣踢开，再把长椅扶正。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:lu", "before": {"position": {"containerId": "shed", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"task_lu_match": "pending", "task_lu_choice": "pending", "task_lu_kit": "pending", "task_lu_goggles": "pending", "task_lu_route": "pending", "task_lu_ally": "pending", "task_lu_rules": "achieved"}}, "after": {"position": {"containerId": "yard", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"ta
- info: insufficient proposed=False content='' support='' evidence=settled
- env: present proposed=True content='空弹匣已被踢开，长椅已被扶正' support='' evidence=settled

## sm7-e-success-4 (train, cache, env_success)
- action: 我走到东回廊，把软垫拉回窗下，再把遮光帘拉起。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:lu", "before": {"position": {"containerId": "yard", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"task_lu_match": "pending", "task_lu_choice": "pending", "task_lu_kit": "pending", "task_lu_goggles": "pending", "task_lu_route": "pending", "task_lu_ally": "pending", "task_lu_rules": "achieved"}}, "after": {"position": {"containerId": "east_arcade", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks
- info: insufficient proposed=False content='' support='' evidence=settled
- env: present proposed=True content='软垫被拉回窗下，遮光帘被拉起' support='环境=window_pad:已被拉回；环境=canvas_blind:已被拉起' evidence=settled

## sm7-e-success-5 (train, cache, env_success)
- action: 我走进西回廊，把折断的蓝带挂到柱子上。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:lu", "before": {"position": {"containerId": "east_arcade", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"task_lu_match": "pending", "task_lu_choice": "pending", "task_lu_kit": "achieved", "task_lu_goggles": "pending", "task_lu_route": "pending", "task_lu_ally": "pending", "task_lu_rules": "achieved"}}, "after": {"position": {"containerId": "west_arcade", "slotId": null, "relativeTo": null}, "appearance": {}
- info: insufficient proposed=False content='' support='' evidence=settled
- env: present proposed=True content='折断的蓝带已被挂到西回廊柱子上' support='折断的蓝带挂到了柱子上' evidence=settled

## sm7-e-success-6 (train, cache, env_success)
- action: 我走进钟楼门厅，把长桌推到墙边。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:lu", "before": {"position": {"containerId": "west_arcade", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"task_lu_match": "pending", "task_lu_choice": "pending", "task_lu_kit": "achieved", "task_lu_goggles": "pending", "task_lu_route": "pending", "task_lu_ally": "pending", "task_lu_rules": "achieved"}}, "after": {"position": {"containerId": "foyer", "slotId": null, "relativeTo": null}, "appearance": {}, "tas
- info: insufficient proposed=False content='' support='' evidence=settled
- env: present proposed=True content='钟楼门厅长桌已被推到墙边' support='把长桌推到墙边' evidence=settled

## sm7-e-success-7 (train, cache, env_success)
- action: 我把钟楼地下检修门关上。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "item:hatch_door", "before": {"position": {"containerId": "foyer", "slotId": null, "relativeTo": null}, "appearance": {}}, "after": {"position": {"containerId": "foyer", "slotId": null, "relativeTo": null}, "appearance": {"change_149": "已被关上"}}}], "env": ["item:hatch_door"]}
- info: absent proposed=False content='' support='' evidence=settled
- env: present proposed=True content='钟楼地下检修门已被关上' support='钟楼地下检修门关闭，门闩插好' evidence=narrative

## sm7-e-success-8 (train, cache, env_success)
- action: 我走上顶层，把玻璃门拉开，再把蓝方信号旗挂到栏杆上。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:lu", "before": {"position": {"containerId": "foyer", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"task_lu_match": "pending", "task_lu_choice": "pending", "task_lu_kit": "achieved", "task_lu_goggles": "pending", "task_lu_route": "pending", "task_lu_ally": "pending", "task_lu_rules": "achieved"}}, "after": {"position": {"containerId": "top", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"t
- info: absent proposed=False content='' support='' evidence=settled
- env: present proposed=True content='顶层玻璃门已被拉开，蓝方信号旗已被挂到栏杆上' support='把玻璃门拉开（达到目的）；去向=lu:top；环境=balcony_door:已被拉开' evidence=settled

## sm7-e-success-9 (train, cache, env_success)
- action: 我走进医护处置室，把空床推到墙边，再把医护箱合上。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:lu", "before": {"position": {"containerId": "top", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"task_lu_match": "pending", "task_lu_choice": "pending", "task_lu_kit": "achieved", "task_lu_goggles": "pending", "task_lu_route": "pending", "task_lu_ally": "pending", "task_lu_rules": "achieved"}}, "after": {"position": {"containerId": "aid", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"tas
- info: insufficient proposed=False content='' support='' evidence=settled
- env: present proposed=True content='空床被推到墙边，医护箱被合上' support='把空床推到墙边' evidence=settled

## sm7-e-success-10 (train, cache, env_success)
- action: 我走进休息区，把保温毯挂到椅背上，再把识别带叠好。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:lu", "before": {"position": {"containerId": "aid", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"task_lu_match": "pending", "task_lu_choice": "pending", "task_lu_kit": "achieved", "task_lu_goggles": "pending", "task_lu_route": "achieved", "task_lu_ally": "pending", "task_lu_rules": "achieved"}}, "after": {"position": {"containerId": "rest", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"t
- info: insufficient proposed=False content='' support='' evidence=settled
- env: present proposed=True content='保温毯已被挂到椅背上' support='保温毯挂到椅背上' evidence=settled

## sm7-e-success-11 (train, cache, env_success)
- action: 我走进值钟间，把检修图叠好，再把工作台拉回原位。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:lu", "before": {"position": {"containerId": "rest", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"task_lu_match": "pending", "task_lu_choice": "pending", "task_lu_kit": "achieved", "task_lu_goggles": "pending", "task_lu_route": "achieved", "task_lu_ally": "pending", "task_lu_rules": "achieved"}}, "after": {"position": {"containerId": "bell_room", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks
- info: insufficient proposed=False content='' support='' evidence=settled
- env: present proposed=True content='检修图已被叠好，工作台已被拉回' support='检修图叠好' evidence=settled

## sm7-e-success-12 (train, cache, env_success)
- action: 我走进控制室，把记录单合上，再把话筒拉回桌中。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:caesar", "before": {"position": {"containerId": "red_rally", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"task_caesar_win": "pending", "task_caesar_contact": "pending", "task_caesar_bridge": "pending", "task_caesar_tang": "pending", "task_caesar_flag": "pending", "task_217": "pending", "task_240": "pending"}}, "after": {"position": {"containerId": "bell_room", "slotId": null, "relativeTo": null}, "appearan
- info: insufficient proposed=False content='' support='' evidence=settled
- env: absent proposed=False content='' support='' evidence=settled

## sm8-e-success-1 (train, cache, env_success)
- action: 我走进器材棚，把备用演习枪摆到台面，再把备用护目镜摆到台面。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:lu", "before": {"position": {"containerId": "lane", "slotId": "slot_wall", "relativeTo": null}, "appearance": {}, "tasks": {"task_lu_match": "pending", "task_lu_choice": "pending", "task_lu_kit": "pending", "task_lu_goggles": "pending", "task_lu_route": "pending", "task_lu_ally": "pending", "task_lu_rules": "achieved"}}, "after": {"position": {"containerId": "shed", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks
- info: insufficient proposed=False content='未获得新信息' support='路明非没有问出结果' evidence=narrative
- env: present proposed=True content='备用护目镜已被摆到台面' support='' evidence=state

## sm8-e-success-2 (train, cache, env_success)
- action: 我把备用红色识别带挂回架子，再把笼门上的挂锁挂到墙钩上。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "item:cage_lock", "before": {"position": {"containerId": "shed", "slotId": null, "relativeTo": null}, "appearance": {}}, "after": {"position": {"containerId": "shed", "slotId": null, "relativeTo": null}, "appearance": {"change_39": "已被部分挂到"}}}], "env": ["item:cage_lock"]}
- info: absent proposed=False content='' support='' evidence=settled
- env: present proposed=True content='笼门挂锁已被部分挂到墙钩上' support='把笼门上的挂锁挂到墙钩上。（只完成一部分）' evidence=settled

## sm8-e-success-3 (train, cache, env_success)
- action: 我把领用簿翻开，再把弹药箱盖子盖回。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "item:checkout_book", "before": {"position": {"containerId": "supply_counter", "slotId": "slot_top", "relativeTo": null}, "appearance": {}}, "after": {"position": {"containerId": "supply_counter", "slotId": "slot_top", "relativeTo": null}, "appearance": {"change_59": "已被翻开"}}}, {"key": "item:ammo_box", "before": {"position": {"containerId": "shed", "slotId": null, "relativeTo": null}, "appearance": {}}, "after": {"position": {"conta
- info: absent proposed=False content='' support='' evidence=settled
- env: present proposed=True content='领用簿已被翻开，弹药箱已被盖回' support='已被翻开' evidence=state

## sm8-e-success-4 (train, cache, env_success)
- action: 我走进庭院，把空弹匣踢开，再把长椅扶正。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:lu", "before": {"position": {"containerId": "shed", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"task_lu_match": "pending", "task_lu_choice": "pending", "task_lu_kit": "pending", "task_lu_goggles": "pending", "task_lu_route": "pending", "task_lu_ally": "pending", "task_lu_rules": "achieved"}}, "after": {"position": {"containerId": "yard", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"ta
- info: insufficient proposed=False content='' support='' evidence=settled
- env: present proposed=True content='空弹匣被踢开，长椅被扶正' support='' evidence=state

## sm8-e-success-5 (train, cache, env_success)
- action: 我走到东回廊，把遮光帘拉起，再把低窗软垫拖到墙根。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:lu", "before": {"position": {"containerId": "yard", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"task_lu_match": "pending", "task_lu_choice": "pending", "task_lu_kit": "pending", "task_lu_goggles": "pending", "task_lu_route": "pending", "task_lu_ally": "pending", "task_lu_rules": "achieved"}}, "after": {"position": {"containerId": "east_arcade", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks
- info: insufficient proposed=False content='' support='' evidence=settled
- env: present proposed=True content='东回廊遮光帘已被拉起' support='canvas_blind:已被拉起' evidence=settled

## sm8-e-success-6 (train, cache, env_success)
- action: 我走进钟楼门厅，把长桌推到侧墙，再把检修门关上。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:lu", "before": {"position": {"containerId": "east_arcade", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"task_lu_match": "pending", "task_lu_choice": "pending", "task_lu_kit": "pending", "task_lu_goggles": "pending", "task_lu_route": "pending", "task_lu_ally": "pending", "task_lu_rules": "achieved"}}, "after": {"position": {"containerId": "foyer", "slotId": null, "relativeTo": null}, "appearance": {}, "task
- info: insufficient proposed=False content='' support='' evidence=settled
- env: present proposed=True content='钟楼门厅长桌已被推到侧墙' support='把长桌推到侧墙' evidence=settled

## sm8-e-success-7 (train, cache, env_success)
- action: 我走上顶层，把玻璃门推开，再把蓝方信号旗挂到栏杆上。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:lu", "before": {"position": {"containerId": "foyer", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"task_lu_match": "pending", "task_lu_choice": "pending", "task_lu_kit": "pending", "task_lu_goggles": "pending", "task_lu_route": "pending", "task_lu_ally": "pending", "task_lu_rules": "achieved"}}, "after": {"position": {"containerId": "top", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"ta
- info: absent proposed=False content='' support='' evidence=settled
- env: present proposed=True content='顶层玻璃门已被推开，蓝方信号旗已被挂到栏杆上' support='' evidence=settled

## sm8-e-success-8 (train, cache, env_success)
- action: 我走进医护处置室，把空床推到墙边，再把医护箱打开。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:lu", "before": {"position": {"containerId": "top", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"task_lu_match": "pending", "task_lu_choice": "pending", "task_lu_kit": "pending", "task_lu_goggles": "pending", "task_lu_route": "pending", "task_lu_ally": "pending", "task_lu_rules": "achieved"}}, "after": {"position": {"containerId": "aid", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"task
- info: insufficient proposed=False content='未获得新信息' support='他没有打开医护箱' evidence=narrative
- env: present proposed=True content='空床被推开，医护箱被打开' support='环境=empty_bed:已被推开' evidence=settled

## sm8-e-success-9 (train, cache, env_success)
- action: 我把分诊夹翻开。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:caesar", "before": {"position": {"containerId": "east_arcade", "slotId": "slot_window", "relativeTo": null}, "appearance": {}, "tasks": {"task_caesar_win": "pending", "task_caesar_contact": "pending", "task_caesar_bridge": "pending", "task_caesar_tang": "pending", "task_caesar_flag": "pending", "task_107": "pending", "task_130": "pending", "task_154": "pending", "task_178": "pending"}}, "after": {"position": {"containerId": "e
- info: absent proposed=False content='未获得新信息' support='只把夹面翻了一下' evidence=settled
- env: conflict proposed=False content='无环境状态改变' support='楼里没有别的动静' evidence=narrative

## sm8-e-success-10 (train, cache, env_success)
- action: 我走进休息区，把保温毯叠好，再把识别带挂到墙钩上。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:lu", "before": {"position": {"containerId": "aid", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"task_lu_match": "pending", "task_lu_choice": "pending", "task_lu_kit": "pending", "task_lu_goggles": "pending", "task_lu_route": "pending", "task_lu_ally": "pending", "task_lu_rules": "achieved"}}, "after": {"position": {"containerId": "rest", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"tas
- info: insufficient proposed=False content='未获得新信息' support='路明非没有问出下一步' evidence=narrative
- env: present proposed=True content='保温毯已被叠好' support='把保温毯叠好' evidence=settled

## sm8-e-success-11 (train, cache, env_success)
- action: 我走进值钟间，把工作台推到墙边，再把检修图展开。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:lu", "before": {"position": {"containerId": "rest", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"task_lu_match": "pending", "task_lu_choice": "pending", "task_lu_kit": "achieved", "task_lu_goggles": "pending", "task_lu_route": "achieved", "task_lu_ally": "pending", "task_lu_rules": "achieved"}}, "after": {"position": {"containerId": "bell_room", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks
- info: insufficient proposed=False content='' support='' evidence=settled
- env: present proposed=True content='工作台被推到墙边，检修图已展开' support='把工作台推到墙边' evidence=settled

## sm8-e-success-12 (train, cache, env_success)
- action: 我走进控制室，把记录单翻开，再把话筒推到桌角。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:caesar", "before": {"position": {"containerId": "east_arcade", "slotId": "slot_window", "relativeTo": null}, "appearance": {}, "tasks": {"task_caesar_win": "pending", "task_caesar_contact": "pending", "task_caesar_bridge": "pending", "task_caesar_tang": "pending", "task_caesar_flag": "pending", "task_107": "pending", "task_130": "pending", "task_154": "pending", "task_178": "pending", "task_200": "pending", "task_223": "pendin
- info: absent proposed=False content='' support='' evidence=settled
- env: conflict proposed=False content='' support='' evidence=settled

## sm8-i-transfer-1 (train, cache, info_irrelevant_known)
- action: 我把护目镜递给诺诺。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "item:goggles_lu", "before": {"position": {"containerId": "lu", "slotId": "slot_body", "relativeTo": null}, "appearance": {}}, "after": {"position": {"containerId": "nono", "slotId": null, "relativeTo": null}, "appearance": {}}}], "env": []}
- info: absent proposed=False content='' support='' evidence=settled
- env: absent proposed=False content='' support='' evidence=state

## sm8-i-transfer-2 (train, cache, info_irrelevant_known)
- action: 我把弹匣塞进胸袋。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:caesar", "before": {"position": {"containerId": "red_rally", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"task_caesar_win": "pending", "task_caesar_contact": "pending", "task_caesar_bridge": "pending", "task_caesar_tang": "pending", "task_caesar_flag": "pending"}}, "after": {"position": {"containerId": "red_rally", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"task_caesar_win": "pending
- info: absent proposed=False content='' support='' evidence=settled
- env: absent proposed=False content='' support='' evidence=settled

## sm8-i-transfer-3 (train, cache, info_irrelevant_known)
- action: 我拿起领用台上的领用簿。
- state diff: {"known": true, "added": [], "removed": [], "changed": [], "env": []}
- info: absent proposed=False content='未获得新信息' support='' evidence=settled
- env: absent proposed=False content='领用簿未被拿起' support='' evidence=settled

## sm8-i-transfer-4 (train, cache, info_irrelevant_known)
- action: 我把水杯放到台面。
- state diff: {"known": true, "added": [], "removed": [], "changed": [], "env": []}
- info: absent proposed=False content='' support='' evidence=settled
- env: absent proposed=False content='' support='' evidence=settled

## sm8-i-irrelevant-1 (train, cache, info_irrelevant_known)
- action: 我整理背心的胸袋。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:caesar", "before": {"position": {"containerId": "red_rally", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"task_caesar_win": "pending", "task_caesar_contact": "pending", "task_caesar_bridge": "pending", "task_caesar_tang": "pending", "task_caesar_flag": "pending", "task_42": "pending"}}, "after": {"position": {"containerId": "red_rally", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"task
- info: absent proposed=False content='' support='' evidence=settled
- env: absent proposed=False content='' support='' evidence=state

## sm8-i-transfer-5 (train, cache, info_irrelevant_known)
- action: 我戴上护目镜。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:caesar", "before": {"position": {"containerId": "red_rally", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"task_caesar_win": "pending", "task_caesar_contact": "pending", "task_caesar_bridge": "pending", "task_caesar_tang": "pending", "task_caesar_flag": "pending", "task_42": "pending", "task_103": "pending"}}, "after": {"position": {"containerId": "bridge", "slotId": "slot_west_end", "relativeTo": null}, "a
- info: absent proposed=True content='路明非戴上护目镜并成功使用' support='路明非戴上护目镜并成功使用了物品' evidence=settled
- env: absent proposed=False content='' support='' evidence=settled

## sm8-i-transfer-6 (train, cache, info_irrelevant_known)
- action: 我把红色识别带缠到手臂上。
- state diff: {"known": true, "added": [], "removed": [], "changed": [], "env": []}
- info: absent proposed=False content='' support='' evidence=settled
- env: absent proposed=False content='' support='' evidence=settled

## sm8-i-transfer-7 (train, cache, info_irrelevant_known)
- action: 我把空弹匣踢到墙角。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:caesar", "before": {"position": {"containerId": "bridge", "slotId": "slot_west_end", "relativeTo": null}, "appearance": {}, "tasks": {"task_caesar_win": "pending", "task_caesar_contact": "pending", "task_caesar_bridge": "pending", "task_caesar_tang": "pending", "task_caesar_flag": "pending", "task_42": "pending", "task_103": "pending"}}, "after": {"position": {"containerId": "bridge", "slotId": "slot_west_end", "relativeTo": n
- info: absent proposed=False content='' support='' evidence=settled
- env: absent proposed=False content='' support='' evidence=settled

## sm8-i-irrelevant-2 (train, cache, info_irrelevant_known)
- action: 我靠着墙站着。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:nono", "before": {"position": {"containerId": "lane", "slotId": "slot_entry", "relativeTo": null}, "appearance": {}, "tasks": {"task_nono_squad": "pending", "task_nono_lu": "pending", "task_nono_battery": "pending", "task_nono_wounded": "pending", "task_nono_signal": "pending"}}, "after": {"position": {"containerId": "lane", "slotId": "slot_entry", "relativeTo": null}, "appearance": {}, "tasks": {"task_nono_squad": "achieved",
- info: absent proposed=False content='' support='' evidence=settled
- env: absent proposed=False content='' support='' evidence=settled

## sm8-i-irrelevant-3 (train, cache, info_irrelevant_known)
- action: 我蹲在掩体后等待。
- state diff: {"known": true, "added": [], "removed": [], "changed": [], "env": []}
- info: absent proposed=False content='' support='' evidence=settled
- env: absent proposed=False content='' support='' evidence=state

## sm8-i-irrelevant-4 (train, cache, info_irrelevant_known)
- action: 我把长椅扶正。
- state diff: {"known": true, "added": [], "removed": [], "changed": [], "env": []}
- info: absent proposed=False content='' support='' evidence=settled
- env: insufficient proposed=True content='长椅被扶正' support='路明非把长椅扶正' evidence=settled

## sm8-i-transfer-8 (train, cache, info_irrelevant_known)
- action: 我把保温毯叠好。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:caesar", "before": {"position": {"containerId": "bridge", "slotId": "slot_west_end", "relativeTo": null}, "appearance": {}, "tasks": {"task_caesar_win": "pending", "task_caesar_contact": "pending", "task_caesar_bridge": "achieved", "task_caesar_tang": "pending", "task_caesar_flag": "pending", "task_42": "pending", "task_103": "achieved", "task_164": "pending", "task_185": "pending"}}, "after": {"position": {"containerId": "bri
- info: absent proposed=False content='' support='' evidence=settled
- env: absent proposed=False content='' support='' evidence=settled

## sm9-e-move-1 (train, cache, env_irrelevant_move)
- action: 我走进中央庭院。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:lu", "before": {"position": {"containerId": "lane", "slotId": "slot_wall", "relativeTo": null}, "appearance": {}, "tasks": {"task_lu_match": "pending", "task_lu_choice": "pending", "task_lu_kit": "pending", "task_lu_goggles": "pending", "task_lu_route": "pending", "task_lu_ally": "pending", "task_lu_rules": "achieved"}}, "after": {"position": {"containerId": "yard", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks
- info: insufficient proposed=False content='' support='' evidence=settled
- env: absent proposed=False content='' support='' evidence=settled

## sm9-e-transfer-1 (train, cache, env_item_transfer)
- action: 我把护目镜递给诺诺。
- state diff: {"known": true, "added": [], "removed": [], "changed": [], "env": []}
- info: absent proposed=False content='' support='' evidence=settled
- env: absent proposed=False content='' support='' evidence=state

## sm9-e-move-2 (train, cache, env_irrelevant_move)
- action: 我沿着服务巷走回器材棚。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:lu", "before": {"position": {"containerId": "yard", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"task_lu_match": "pending", "task_lu_choice": "pending", "task_lu_kit": "pending", "task_lu_goggles": "pending", "task_lu_route": "pending", "task_lu_ally": "pending", "task_lu_rules": "achieved"}}, "after": {"position": {"containerId": "shed", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"ta
- info: absent proposed=False content='' support='' evidence=settled
- env: absent proposed=False content='' support='' evidence=state

## sm9-e-transfer-2 (train, cache, env_item_transfer)
- action: 我把弹匣塞进胸袋。
- state diff: {"known": true, "added": [], "removed": [], "changed": [], "env": []}
- info: absent proposed=False content='未获得明确信息' support='路明非没有找到明确的答案' evidence=narrative
- env: absent proposed=False content='' support='' evidence=state

## sm10-e-success-1 (train, cache, env_success)
- action: 我走进器材棚，把弹药箱盖子掀开。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:lu", "before": {"position": {"containerId": "lane", "slotId": "slot_wall", "relativeTo": null}, "appearance": {}, "tasks": {"task_lu_match": "pending", "task_lu_choice": "pending", "task_lu_kit": "pending", "task_lu_goggles": "pending", "task_lu_route": "pending", "task_lu_ally": "pending", "task_lu_rules": "achieved"}}, "after": {"position": {"containerId": "shed", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks
- info: insufficient proposed=True content='弹药箱内有两具短枪弹匣，各装八发演习弹' support='箱里有两具通用短枪弹匣，各装了八发演习弹' evidence=narrative
- env: present proposed=True content='弹药箱已被掀开' support='已被掀开' evidence=state

## sm10-e-success-2 (train, cache, env_success)
- action: 我把领用台推到墙边。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:fingel", "before": {"position": {"containerId": "shed", "slotId": "slot_counter", "relativeTo": null}, "appearance": {}, "tasks": {"task_fingel_deal": "pending", "task_fingel_map": "pending", "task_fingel_camera": "pending", "task_fingel_help": "pending", "task_fingel_soup": "pending"}}, "after": {"position": {"containerId": "shed", "slotId": "slot_counter", "relativeTo": null}, "appearance": {}, "tasks": {"task_fingel_deal": 
- info: absent proposed=False content='' support='' evidence=settled
- env: present proposed=True content='领用台已被推到墙边' support='领用台推到墙边' evidence=settled

## sm10-e-move-1 (train, cache, env_irrelevant_move)
- action: 我走进中央庭院。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:lu", "before": {"position": {"containerId": "shed", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"task_lu_match": "pending", "task_lu_choice": "pending", "task_lu_kit": "pending", "task_lu_goggles": "pending", "task_lu_route": "pending", "task_lu_ally": "pending", "task_lu_rules": "achieved"}}, "after": {"position": {"containerId": "yard", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"ta
- info: insufficient proposed=False content='' support='' evidence=settled
- env: absent proposed=False content='' support='' evidence=state

## sm10-e-transfer-1 (train, cache, env_item_transfer)
- action: 我把护目镜递给诺诺。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:caesar", "before": {"position": {"containerId": "red_rally", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"task_caesar_win": "pending", "task_caesar_contact": "pending", "task_caesar_bridge": "pending", "task_caesar_tang": "pending", "task_caesar_flag": "pending", "task_41": "pending"}}, "after": {"position": {"containerId": "red_rally", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"task
- info: absent proposed=False content='' support='' evidence=settled
- env: absent proposed=False content='' support='' evidence=state

## sm9-i-new-1 (train, cache, info_new)
- action: 我读服务巷规则牌上关于医护白线的条款。
- state diff: {"known": true, "added": [], "removed": [], "changed": [], "env": []}
- info: present proposed=True content='医护白线禁射' support='医护白线禁射' evidence=settled
- env: absent proposed=False content='' support='' evidence=settled

## sm9-i-new-2 (train, cache, info_new)
- action: 我读赛区地图上标注的地下通道入口位置。
- state diff: {"known": true, "added": [], "removed": [], "changed": [], "env": []}
- info: absent proposed=True content='路明非读到地下通道入口位置' support='路明非读赛区地图上标注的地下通道入口位置' evidence=settled
- env: absent proposed=False content='' support='' evidence=state

## sm9-i-new-3 (train, cache, info_new)
- action: 我查看唐骁左臂识别带的颜色。
- state diff: {"known": true, "added": [], "removed": [], "changed": [], "env": []}
- info: insufficient proposed=True content='唐骁左臂识别带为黑色' support='唐骁的识别带是黑色的' evidence=narrative
- env: absent proposed=False content='' support='' evidence=state

## sm9-i-new-4 (train, cache, info_new)
- action: 我走进值钟间，读检修图上关于旗台的说明。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:lu", "before": {"position": {"containerId": "lane", "slotId": "slot_wall", "relativeTo": null}, "appearance": {}, "tasks": {"task_lu_match": "pending", "task_lu_choice": "pending", "task_lu_kit": "pending", "task_lu_goggles": "pending", "task_lu_route": "pending", "task_lu_ally": "pending", "task_lu_rules": "achieved"}}, "after": {"position": {"containerId": "bell_room", "slotId": null, "relativeTo": null}, "appearance": {}, "
- info: absent proposed=True content='路明非在值钟间读检修图，了解旗台说明' support='路明非走进值钟间，读检修图上关于旗台的说明' evidence=settled
- env: absent proposed=False content='' support='' evidence=settled

## sm9-i-new-5 (train, cache, info_new)
- action: 我走进医护处置室，读分诊夹板上林亦舟的登记。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:lu", "before": {"position": {"containerId": "bell_room", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks": {"task_lu_match": "pending", "task_lu_choice": "pending", "task_lu_kit": "achieved", "task_lu_goggles": "pending", "task_lu_route": "achieved", "task_lu_ally": "pending", "task_lu_rules": "achieved"}}, "after": {"position": {"containerId": "aid", "slotId": null, "relativeTo": null}, "appearance": {}, "tasks"
- info: absent proposed=True content='路明非读分诊夹板，查林亦舟登记' support='读分诊夹板上林亦舟的登记' evidence=settled
- env: absent proposed=False content='' support='' evidence=state

## sm9-i-new-6 (train, cache, info_new)
- action: 我走进控制室，读记分面板上的比分。
- state diff: {"known": true, "added": [], "removed": [], "changed": [], "env": []}
- info: insufficient proposed=False content='未进入控制室，未读到比分' support='人却没有进到控制室' evidence=narrative
- env: absent proposed=False content='' support='' evidence=state

## sm9-i-new-7 (train, cache, info_new)
- action: 我读广播话筒旁贴的停赛时间。
- state diff: {"known": true, "added": [], "removed": [], "changed": [], "env": []}
- info: absent proposed=False content='停赛时间未读出' support='话没说完，就停住了' evidence=narrative
- env: absent proposed=False content='' support='' evidence=state

## sm9-i-irrelevant-1 (train, cache, info_irrelevant_known)
- action: 我查看唐骁的红色识别带。
- state diff: {"known": true, "added": [], "removed": [], "changed": [], "env": []}
- info: insufficient proposed=True content='路明非查看唐骁的红色识别带，未取下' support='路明非查了查唐骁的红色识别带，手停在那，没有取下来' evidence=narrative
- env: absent proposed=False content='' support='' evidence=settled

## sm9-i-irrelevant-2 (train, cache, info_irrelevant_known)
- action: 我查看护目镜镜片有没有裂纹。
- state diff: {"known": true, "added": [], "removed": [], "changed": [], "env": []}
- info: insufficient proposed=False content='' support='' evidence=settled
- env: absent proposed=False content='' support='' evidence=state

## sm9-i-fail-1 (train, cache, info_failure)
- action: 我问诺诺演习口令。
- state diff: {"known": true, "added": [], "removed": [], "changed": [], "env": []}
- info: insufficient proposed=False content='未获得口令信息' support='路明非问诺诺口令，问完一个，想问另一个，停在门口' evidence=narrative
- env: absent proposed=False content='' support='' evidence=state

## sm9-i-fail-2 (train, cache, info_failure)
- action: 我问顾岚演习口令。
- state diff: {"known": true, "added": [], "removed": [], "changed": [], "env": []}
- info: absent proposed=False content='顾岚未答出口令，路明非未获得信息' support='顾岚没有答上来' evidence=narrative
- env: absent proposed=False content='' support='' evidence=state

## sm9-i-irrelevant-3 (train, cache, info_irrelevant_known)
- action: 我整理背心胸袋。
- state diff: {"known": true, "added": [], "removed": [], "changed": [], "env": []}
- info: absent proposed=False content='' support='' evidence=settled
- env: absent proposed=False content='' support='' evidence=settled

## s01-act-move (train, cache, 20-input)
- action: 我沿着服务巷的墙根往器材棚方向走，脚步放轻，注意前面的门口。
- state diff: {"known": false, "added": [], "removed": [], "changed": [], "env": []}
- info: insufficient proposed=True content='诺诺在巷口，红色识别带缠左臂，短枪口朝下，无命中标记' support='诺诺在巷口，红发用发圈束在脑后，红色识别带缠在左臂。她手里的短枪枪口压向地面，身上没有本场命中标记' evidence=narrative
- env: insufficient proposed=False content='' support='' evidence=

## s02-act-observe (train, cache, 20-input)
- action: 我停在原地，观察器材棚门口进出的人，记下他们身上的识别带颜色。
- state diff: {"known": true, "added": [], "removed": [], "changed": [], "env": []}
- info: insufficient proposed=True content='诺诺的红色识别带在器材棚门口闪烁' support='诺诺的红色识别带在器材棚门口闪烁' evidence=settled
- env: insufficient proposed=False content='' support='' evidence=

## s03-act-talk (train, cache, 20-input)
- action: 我问器材棚门口的人，今天演习的红蓝两方各在哪些区域活动。
- state diff: {"known": true, "added": [], "removed": [], "changed": [], "env": []}
- info: insufficient proposed=True content='西回廊那边有路，你得小心' support='西回廊那边有路，你得小心' evidence=settled
- env: insufficient proposed=False content='' support='' evidence=state

## s04-act-wait (train, cache, 20-input)
- action: 我在墙边等一会儿，听远处的枪声间隔，估算时间过去了多久。
- state diff: {"known": true, "added": [], "removed": [], "changed": [], "env": []}
- info: insufficient proposed=True content='诺诺告知西回廊路线图在那边，需先确认钟楼路线' support='西回廊的路线图在那边，你得先确认钟楼的路线' evidence=settled
- env: insufficient proposed=False content='' support='' evidence=

## s05-act-inventory (train, cache, 20-input)
- action: 我低头检查护目镜、识别带和胸袋里的弹匣，确认都在。
- state diff: {"known": false, "added": [], "removed": [], "changed": [], "env": []}
- info: insufficient proposed=True content='诺诺低声问路明非是否愿意留下' support='低声问道：“路明非，你……是否愿意继续留在这里？”' evidence=settled
- env: insufficient proposed=True content='诺诺的红色识别带微微发烫' support='诺诺的红色识别带在胸前微微发烫' evidence=settled

## s06-legal-failure (train, cache, 20-input)
- action: 我把领用台上的红色电台递给阿豹，让他转交给裁判。
- state diff: {"known": true, "added": [], "removed": [], "changed": [], "env": []}
- info: insufficient proposed=True content='诺诺问路明非是否愿意和她一起' support='路明非，你……你愿意和我一起吗？' evidence=settled
- env: absent proposed=False content='' support='' evidence=

## s07-partial (train, cache, 20-input)
- action: 我试着把脚边的器材箱推到门口，但箱子很沉，只挪动了一点。
- state diff: {"known": true, "added": [], "removed": [], "changed": [], "env": []}
- info: insufficient proposed=True content='诺诺请求路明非恢复短讯机与凯撒联络' support='我需要你帮我把故障短讯机恢复到能与凯撒联络的状态' evidence=settled
- env: insufficient proposed=False content='' support='' evidence=

## s08-joint-move (train, cache, 20-input)
- action: 我跟门口的人说一起走，两人沿器材棚外侧快走到西回廊。
- state diff: {"known": true, "added": [], "removed": [], "changed": [], "env": []}
- info: insufficient proposed=True content='诺诺警惕地问西回廊路线图及钟楼附近听到什么' support='路明非，西回廊的路线图……我刚刚在钟楼附近听到什么？' evidence=settled
- env: insufficient proposed=False content='' support='' evidence=state

## s09-confront (train, cache, 20-input)
- action: 我举起手示意不介入，慢慢从对峙的两人中间走过去。
- state diff: {"known": false, "added": [], "removed": [], "changed": [], "env": []}
- info: insufficient proposed=True content='路明非将诺诺设为目标，诺诺也将路明非设为目标。' support='"targets": [{"targetId": "nono"}]}, {"task": "targets", "key": "nono", "kind": null, "text": null, "targets": [{"targetId": "lu"}]}' evidence=settled
- env: insufficient proposed=False content='' support='' evidence=state

## s10-strike (train, cache, 20-input)
- action: 我突然抬手向挡路的人挥拳，想把他逼退。
- state diff: {"known": true, "added": [], "removed": [], "changed": [], "env": []}
- info: insufficient proposed=True content='规则牌挡住拳风，他看懂了规则牌' support='被规则牌挡住。他看懂了规则牌' evidence=narrative
- env: insufficient proposed=False content='' support='' evidence=state

## s11-task-ask (train, cache, 20-input)
- action: 我问诺诺现在红蓝局势，以及我两边都不帮算不算违规。
- state diff: {"known": true, "added": [], "removed": [], "changed": [], "env": []}
- info: insufficient proposed=True content='诺诺说西回廊路线接近钟楼，需确认是否愿意' support='西回廊的路线图上……有条路接近钟楼，但需要你确认是否愿意' evidence=settled
- env: insufficient proposed=False content='本回合无环境或物品状态改变' support='"added": [], "removed": [], "changed": [], "env": []' evidence=state

## s12-climb (train, cache, 20-input)
- action: 我沿钟楼楼梯上到二层平台，蹲在栏杆边观察庭院。
- state diff: {"known": true, "added": [], "removed": [], "changed": [], "env": []}
- info: insufficient proposed=True content='诺诺在巷口，左臂缠着红色识别带，右袖上有红痕' support='诺诺在巷口，红发用发圈束在脑后，左臂缠着红色识别带，右袖上有红痕' evidence=narrative
- env: insufficient proposed=False content='' support='' evidence=state

## s13-already-acted (train, cache, 20-input)
- action: 等这一轮结束后，我再往前走一步，看看刚才同行的人有没有跟上来。
- state diff: {"known": true, "added": [], "removed": [], "changed": [], "env": []}
- info: insufficient proposed=True content='诺诺的识别带在护目镜上闪烁，拉住路明非问是否想让她成为帮手' support='诺诺的红色识别带在路明非的护目镜上闪烁了一下，随即拉住路明非的手，语气尖锐：“你……你是不是想让我成为你的帮手？”' evidence=settled
- env: insufficient proposed=False content='' support='' evidence=state

## s14-auto-chain (train, cache, 20-input)
- action: 我朝钟楼门厅方向跑过去，想赶在下一波枪声前进去。
- state diff: {"known": true, "added": [], "removed": [], "changed": [], "env": []}
- info: insufficient proposed=True content='路明非与诺诺互相设为目标' support='"targets": [{"targetId": "nono"}]}, {"task": "targets", "key": "nono", "kind": null, "text": null, "targets": [{"targetId": "lu"}]' evidence=settled
- env: insufficient proposed=False content='' support='' evidence=state

## s15-handback (train, cache, 20-input)
- action: 我站着不动，等这一轮结束，看看还有没有人行动。
- state diff: {"known": true, "added": [], "removed": [], "changed": [], "env": []}
- info: insufficient proposed=True content='诺诺本回合以路明非为目标' support='targets": [{"targetId": "lu"}]' evidence=settled
- env: insufficient proposed=False content='' support='' evidence=

## s16-time-check (train, cache, 20-input)
- action: 我再等一段时间，核对护目镜和识别带，记下演习还剩多久。
- state diff: {"known": true, "added": [], "removed": [], "changed": [], "env": []}
- info: insufficient proposed=True content='演习还剩十分钟' support='演习还剩十分钟，他记下了这个时间。' evidence=narrative
- env: insufficient proposed=False content='' support='' evidence=state

## g8-t1-look-lane (train, cache, 20-input)
- action: 我停在服务巷的墙边，先把领用台上那张演习规则牌看清楚，再抬头打量巷口和器材棚方向。
- state diff: {"known": false, "added": [], "removed": [], "changed": [], "env": []}
- info: insufficient proposed=True content='诺诺提醒路明非在墙边停留太久，需要确认。' support='你刚才在墙边停留的时间太久，我这边需要你确认一下' evidence=settled
- env: insufficient proposed=False content='' support='' evidence=state

## g8-t2-move-shed (train, cache, 20-input)
- action: 我贴着服务巷的低墙往器材棚走，进门后先看领用台后面有没有人，再找林亦舟。
- state diff: {"known": true, "added": [], "removed": [], "changed": [], "env": []}
- info: insufficient proposed=True content='诺诺问路明非是否愿意继续留在这里' support='路明非，你……是否愿意继续留在这里？' evidence=settled
- env: insufficient proposed=False content='' support='' evidence=state

## g8-t3-talk-lin (train, cache, 20-input)
- action: 我蹲下来问林亦舟脚踝怎么样，那条断掉的蓝布带是在哪儿弄断的。
- state diff: {"known": true, "added": [], "removed": [], "changed": [], "env": []}
- info: insufficient proposed=True content='断掉的蓝布带散开，露出新鲜弹痕' support='断掉的蓝布带在地面散开，露出那道新鲜的弹痕。' evidence=narrative
- env: insufficient proposed=False content='无环境或物品状态改变' support='"env": []' evidence=state

## g8-t4-joint-move (train, cache, 20-input)
- action: 我跟诺诺说一起走，两人沿着器材棚外侧低姿快走到西回廊，贴着廊柱停住。
- state diff: {"known": true, "added": [], "removed": [], "changed": [{"key": "char:lu", "before": {"position": {"containerId": "lane", "slotId": "slot_wall", "relativeTo": null}, "appearance": {}, "tasks": {"task_lu_match": "pending", "task_lu_choice": "pending", "task_lu_kit": "pending", "task_lu_goggles": "pending", "task_lu_route": "pending", "task_lu_ally": "pending", "task_lu_rules": "achieved"}}, "after": {"position": {"containerId": "west_arcade", "slotId": "slot_pillar3", "relativeTo": null}, "appear
- info: insufficient proposed=True content='林亦舟在第三根廊柱，左脚踝肿起' support='林亦舟背靠第三根廊柱，蓝色识别带沾着灰，左脚踝在鞋帮上方肿起' evidence=settled|narrative
- env: insufficient proposed=False content='' support='' evidence=settled|state
