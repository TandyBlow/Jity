# L3 第三步：90 张来源卡的覆盖计划

日期：2026-10-31。来源卡草稿，未冻结、未运行；标签配额核对不证明场景语义已覆盖。

开发 44 组（四任务各 10 + 短链 4）；封存候选 46 组（四任务各 10 + 短链 6）。
90 是拟议来源组/基础卡数；可执行 case 数和调用数仍未知。骰点派生必须留在同组同 split。
新卡本人初审 0/90；原 42 题意见不迁入。B/C、D 内部及跨 split 的语义同源复核均待完成。

| 卡片 | 用途 | 场景 | 计划覆盖标签 |
|---|---|---|---|
| r1-dev-d02-01 | 开发 | 剧场字幕纠错 | protagonist, pending, act, executable_input |
| r1-dev-d02-02 | 开发 | 菜圃覆盖播种线 | protagonist, pending, act, executable_input |
| r1-dev-d02-03 | 开发 | 无电的录音请求 | protagonist, pending, skip, infeasible_input |
| r1-dev-d02-04 | 开发 | 熟读不等于会解密 | protagonist, pending, skip, infeasible_input |
| r1-dev-d02-05 | 开发 | 旧取件命令后的错放货签 | protagonist, consumed, act, autonomous_task |
| r1-dev-d02-06 | 开发 | 停演后的灯光值守 | protagonist, expired, skip, legitimate_no_action |
| r1-dev-d02-07 | 开发 | 水族箱保温片脱落 | npc, consumed, act, npc_autonomy |
| r1-dev-d02-08 | 开发 | 乐器库湿度提示 | npc, expired, act, personality_motivation |
| r1-dev-d02-09 | 开发 | 装配员等待固化 | npc, consumed, skip, npc_legitimate_no_action |
| r1-dev-d02-10 | 开发 | 棋赛记录员休局 | npc, expired, skip, npc_legitimate_no_action |
| r1-sealed-d02-01 | 封存候选（未冻结） | 制图员重新对齐比例尺 | protagonist, pending, act, executable_input |
| r1-sealed-d02-02 | 封存候选（未冻结） | 茶席换置杯垫 | protagonist, pending, act, executable_input |
| r1-sealed-d02-03 | 封存候选（未冻结） | 字幕员不会凭空翻译 | protagonist, pending, skip, infeasible_input |
| r1-sealed-d02-04 | 封存候选（未冻结） | 潮沟中的无底踏板 | protagonist, pending, skip, infeasible_input |
| r1-sealed-d02-05 | 封存候选（未冻结） | 借书之后的页码争议 | protagonist, consumed, act, autonomous_task |
| r1-sealed-d02-06 | 封存候选（未冻结） | 摄影棚背景检查完成 | protagonist, expired, skip, legitimate_no_action |
| r1-sealed-d02-07 | 封存候选（未冻结） | 救生衣编号冲突 | npc, consumed, act, npc_autonomy |
| r1-sealed-d02-08 | 封存候选（未冻结） | 花粉采样标签受遮挡 | npc, expired, act, personality_motivation |
| r1-sealed-d02-09 | 封存候选（未冻结） | 裁判等候双方就位 | npc, consumed, skip, npc_legitimate_no_action |
| r1-sealed-d02-10 | 封存候选（未冻结） | 广播员静默检修段 | npc, expired, skip, npc_legitimate_no_action |
| r1-dev-d03-01 | 开发 | 个人算式草稿 | empty_targets, private_action |
| r1-dev-d03-02 | 开发 | 自用相册翻页 | empty_targets, nearby_unaffected |
| r1-dev-d03-03 | 开发 | 独立沙盘定位 | empty_targets, remote_unaffected |
| r1-dev-d03-04 | 开发 | 共享气路切换 | multiple_targets, downstream_dependency |
| r1-dev-d03-05 | 开发 | 舞台活动隔墙 | multiple_targets, indirect_effect |
| r1-dev-d03-06 | 开发 | 共同号码牌被收回 | multiple_targets, future_admission_hidden |
| r1-dev-d03-07 | 开发 | 已行动者的工具被挪 | one_target, already_acted |
| r1-dev-d03-08 | 开发 | 反应拉动传动带 | one_target, reaction_as_source, chain |
| r1-dev-d03-09 | 开发 | 回拉两端牵绳 | one_target, cycle |
| r1-dev-d03-10 | 开发 | 同一调音员再受干扰 | one_target, same_target_multiple_sources |
| r1-sealed-d03-01 | 封存候选（未冻结） | 个人袖扣复位 | empty_targets, private_action |
| r1-sealed-d03-02 | 封存候选（未冻结） | 无人的微缩转盘 | empty_targets, nearby_unaffected |
| r1-sealed-d03-03 | 封存候选（未冻结） | 隔声舱内的口型练习 | empty_targets, remote_unaffected |
| r1-sealed-d03-04 | 封存候选（未冻结） | 冷柜分区板被抽离 | multiple_targets, downstream_dependency |
| r1-sealed-d03-05 | 封存候选（未冻结） | 队列入口标识调转 | multiple_targets, indirect_effect |
| r1-sealed-d03-06 | 封存候选（未冻结） | 共用听音线被拔 | multiple_targets, future_admission_hidden |
| r1-sealed-d03-07 | 封存候选（未冻结） | 已行动者支撑面受压 | one_target, already_acted |
| r1-sealed-d03-08 | 封存候选（未冻结） | 躲避中碰到脚踏开关 | one_target, reaction_as_source, chain |
| r1-sealed-d03-09 | 封存候选（未冻结） | 共用门扇反推 | one_target, cycle |
| r1-sealed-d03-10 | 封存候选（未冻结） | 两路光源照向同一操作者 | one_target, same_target_multiple_sources |
| r1-dev-d04-01 | 开发 | 滚筒边的围巾 | callable, frozen_threat, personality |
| r1-dev-d04-02 | 开发 | 滑轨上的量杯 | callable, dice_contrast, constrained_response |
| r1-dev-d04-03 | 开发 | 拉开挡风片的后续影响 | callable, admitted_chain |
| r1-dev-d04-04 | 开发 | 曾经跳过的检票员 | callable, skipped_not_acted |
| r1-dev-d04-05 | 开发 | 双向推来的空架 | callable, multiple_frozen_threats |
| r1-dev-d04-06 | 开发 | 拿着玻璃尺的迟疑者 | callable, task_personality |
| r1-dev-d04-07 | 开发 | 没有准入的引导员 | guard, not_admitted |
| r1-dev-d04-08 | 开发 | 已冻结的拧紧动作 | guard, already_acted_reuse |
| r1-dev-d04-09 | 开发 | 来源原文传输缺损 | guard, missing_frozen_source_text |
| r1-dev-d04-10 | 开发 | 准入记录缺规则值 | guard, missing_judgment |
| r1-sealed-d04-01 | 封存候选（未冻结） | 拓印石旁的袖口 | callable, frozen_threat, personality |
| r1-sealed-d04-02 | 封存候选（未冻结） | 升降篮中的湿泥板 | callable, dice_contrast, constrained_response |
| r1-sealed-d04-03 | 封存候选（未冻结） | 向侧边移动的检修梯 | callable, admitted_chain |
| r1-sealed-d04-04 | 封存候选（未冻结） | 静候者遭遇落下的帘杆 | callable, skipped_not_acted |
| r1-sealed-d04-05 | 封存候选（未冻结） | 两人挪动共同桌板 | callable, multiple_frozen_threats |
| r1-sealed-d04-06 | 封存候选（未冻结） | 护住未干的签名 | callable, task_personality |
| r1-sealed-d04-07 | 封存候选（未冻结） | 未通过的乐谱翻页者 | guard, not_admitted |
| r1-sealed-d04-08 | 封存候选（未冻结） | 已行动的托盘持有人 | guard, already_acted_reuse |
| r1-sealed-d04-09 | 封存候选（未冻结） | 冻结动作只有标题 | guard, missing_frozen_source_text |
| r1-sealed-d04-10 | 封存候选（未冻结） | 关系判定缺目标身份 | guard, missing_judgment |
| r1-dev-d05-01 | 开发 | 同一槽位的两枚印章 | callable, conflicting_actions |
| r1-dev-d05-02 | 开发 | 三人共持折叠屏 | callable, multi_member |
| r1-dev-d05-03 | 开发 | 三端绳结的回牵 | callable, cycle, multiple_sources |
| r1-dev-d05-04 | 开发 | 已扶住物件的人再受冲击 | callable, already_acted_judgment |
| r1-dev-d05-05 | 开发 | 未准入者所在的承重面 | callable, denied_relation |
| r1-dev-d05-06 | 开发 | 滑动标本盒的点数对照 | callable, dice_contrast |
| r1-dev-d05-07 | 开发 | 窄柜中的折扇无法全开 | callable, partial_failure |
| r1-dev-d05-08 | 开发 | 缺失闭组成员动作 | guard, missing_member_action |
| r1-dev-d05-09 | 开发 | 缺少交叉关系骰点 | guard, missing_judgment |
| r1-dev-d05-10 | 开发 | 尚有待查的传送带源 | guard, group_not_closed |
| r1-sealed-d05-01 | 封存候选（未冻结） | 单一方向的旋转按钮 | callable, conflicting_actions |
| r1-sealed-d05-02 | 封存候选（未冻结） | 四人调整悬挂画布 | callable, multi_member, multiple_sources |
| r1-sealed-d05-03 | 封存候选（未冻结） | 环形传递的连杆 | callable, cycle |
| r1-sealed-d05-04 | 封存候选（未冻结） | 已拉紧的缆线遭横推 | callable, already_acted_judgment |
| r1-sealed-d05-05 | 封存候选（未冻结） | 被撤去的垫块 | callable, denied_relation |
| r1-sealed-d05-06 | 封存候选（未冻结） | 墨辊压力的点数对照 | callable, dice_contrast |
| r1-sealed-d05-07 | 封存候选（未冻结） | 绕不开的行程限位 | callable, partial_failure |
| r1-sealed-d05-08 | 封存候选（未冻结） | 登记成员不在动作表 | guard, missing_member_action |
| r1-sealed-d05-09 | 封存候选（未冻结） | 同一关系的重复判定 | guard, missing_judgment, duplicate_judgment |
| r1-sealed-d05-10 | 封存候选（未冻结） | 待确认空目标的尾源 | guard, group_not_closed, empty_target_confirmation |
| r1-dev-chain-01 | 开发 | 独立封装标签的一次行动 | action_empty_targets |
| r1-dev-chain-02 | 开发 | 滑动托架的三级影响 | admission_reaction_targets, chain |
| r1-dev-chain-03 | 开发 | 两端扭动的框架 | cycle_termination |
| r1-dev-chain-04 | 开发 | 冻结后暂停的支撑板 | freeze_cancel_resume |
| r1-sealed-chain-01 | 封存候选（未冻结） | 两路推送同一接收者 | same_target_multiple_sources |
| r1-sealed-chain-02 | 封存候选（未冻结） | 已稳定的图板再被移动 | already_acted_judgment |
| r1-sealed-chain-03 | 封存候选（未冻结） | 先等待后收到共同任务 | skip_then_reaction |
| r1-sealed-chain-04 | 封存候选（未冻结） | 共用标尺上的冲突要求 | conflicting_joint_result |
| r1-sealed-chain-05 | 封存候选（未冻结） | 短时间段内未完成的工序 | segment_linked_boundary |
| r1-sealed-chain-06 | 封存候选（未冻结） | 主角之前的NPC先行动 | g03_npc_before_protagonist |

未完成：完整实体/任务/个性原文、阶段投影、骰点身份与同源派生、D02 缺输入/取消探针、短链运行器、人审和来源回执。
这些卡片不能传给候选模型或用于训练；正式筛选仍需完整协议与独立核验。
