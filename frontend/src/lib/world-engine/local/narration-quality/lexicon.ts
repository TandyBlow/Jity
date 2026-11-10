/** Rule vocabulary for the independent review.
 *
 * Every list here is a review heuristic, not a fact source. A hit is only a
 * finding when the scene projection does not license it; see review.ts.
 */

/** Location-changing verbs. A sentence with one of these plus a settled place
 * name asserts a move and must match a committed move fact. */
export const MOVE_VERBS = [
  '走进', '走入', '走到', '走向', '走回', '走上来', '走下去', '走过去', '走开',
  '跑进', '跑向', '跑到', '冲进', '冲出', '闯进', '闯出', '退回', '退到', '退进',
  '进入', '进来', '进来', '出去', '出来', '上来', '下来', '回来', '回到',
  '离开', '起身离开', '赶到', '来到', '抵达', '登上', '爬上', '翻过', '跨过',
] as const;

/** Plot-changing events. Narration using one needs a settled fact, a licensed
 * player action, a completed task that names the action, or a negated form. */
export const EVENT_VERBS = [
  '递给', '交给', '塞给',
  '敲门', '砸门',
  '躲到', '藏进', '砸碎', '摔碎', '撕开',
  '攻击', '开枪', '射击', '投掷', '扔出', '踢倒', '推倒', '背起', '扶起',
  '拖走', '拖到', '架起', '拦住', '挡在', '抢过', '夺过', '夺下',
  '吃掉', '喝掉', '喝下', '包扎',
] as const;

/** Door / container / body handling. Allowed as a micro-action; hard only when
 * it contradicts a settled item state (checked separately). */
export const SOFT_EVENT_VERBS = [
  '推开', '踢开', '踹开', '拉开', '拽开', '关上', '锁上', '插上', '拔下', '拔出',
  '打开', '开启', '掀开', '揭开', '捡起', '拾起', '拿起', '抓住', '攥住', '拽住',
  '拉住', '按住', '解开', '拿出', '取出', '抽出', '翻开', '合上', '扣上', '系上',
  '推回', '拉上', '盖上', '揣进', '搬到', '挪到', '摆正', '贴正', '压实',
  '塞进', '放进', '掏出', '抱起', '点着', '点燃', '熄灭', '挡住', '咬住', '绑上',
] as const;

/** Everyday prop handling. The product boundary allows this as a micro-action,
 * so it is a review item unless it changes a settled item state. */
export const PROP_VERBS = [
  '捡起', '拾起', '拿起', '放下', '拿出', '取出', '抽出', '掏出', '翻开', '合上',
  '扣上', '系上', '推回', '拉上', '盖上', '抓住', '攥住', '拽住', '拉住',
  '揣进', '塞进衣袋', '抱在', '搬到', '挪到', '摆正', '贴正', '压实',
] as const;

/** Perception events. A sound the viewpoint hears is an event: it needs a
 * source (a settled mover, or the word already in the settled description). */
export const SOUND_WORDS = [
  '脚步声', '枪声', '铃声', '钟声', '回声', '低语声', '呼喊声', '喊声', '惨叫',
  '咳嗽声', '呼吸声', '爆裂声', '碎裂声', '撞击声', '摩擦声', '沙沙声', '嗡嗡声',
] as const;

/** Strong past-event references. Allowed only when the same word appears in
 * the settled input (task, personality or description). */
export const PAST_MARKERS = [
  '小时候', '当年', '从前', '十年前', '那年', '上次', '以前', '当初', '那晚',
  '那天晚上', '记得那', '还记得',
] as const;

export const PROMISE_VERBS = [
  '保证', '答应', '承诺', '发誓', '说好', '约好', '一定会', '绝不', '担保',
] as const;

/** Interiority: only the viewpoint character may be narrated with these. */
export const INTERIOR = [
  '心想', '暗想', '心里', '心中', '内心', '心底', '暗自', '默默', '感到', '觉得',
  '意识到', '明白', '盘算', '打算', '决定', '希望', '害怕', '担心', '后悔', '犹豫',
  '想起', '记起', '回忆起', '以为', '猜', '知道',
] as const;

/** Body micro-actions. Allowed as narration, never as settled state. */
export const BODY_ACTIONS = [
  '抬起', '举起', '抬手', '低头', '抬头', '抬头', '转头', '回头', '后退', '上前',
  '靠近', '退开', '侧身', '弯腰', '摇头', '点头', '叹气', '皱眉', '咬了咬', '抿嘴',
  '缩肩', '屏住', '深吸', '呼出', '避开视线', '别过脸',
] as const;

/** Posture / body state. The product boundary allows un-settled micro
 * postures, so these are review items, never fact errors by themselves. */
export const POSTURE = [
  '站在', '站着', '坐着', '蹲在', '蹲下', '蹲着', '躺在', '躺着', '跪着', '靠在',
  '靠着', '坐下', '站起', '起身', '倚着', '趴着',
] as const;

/** State-panel vocabulary: prose that names a field instead of writing a scene. */
export const FIELD_WORDS = [
  '精神值', '理智值', '任务状态', '个性变化', '外貌变化', '当前状态', '状态栏',
  '这一回合', '本回合', '回合结算', '任务进度',
] as const;

export const COMPLETION_VERBS = ['办完', '做完', '完成', '搞定', '达成', '办妥', '了结', '办了', '做了'] as const;

export const CHANGE_MARKERS = [
  '比刚才', '比平时', '下来', '起来', '少了', '多了', '慢', '快', '浅', '沉', '稳',
  '轻', '紧', '松', '抬', '垂', '移开', '停', '颤', '不再', '第一次', '这次', '顿了顿',
  '停了停', '忽然', '终于',
] as const;

export const BODY_REACTION = [
  '呼吸', '手指', '声音', '视线', '肩', '脸色', '脚步', '膝盖', '背', '眼', '喉',
  '胸口', '心跳', '沉默', '扶', '攥', '捏', '握', '松开', '垂下', '抬起', '移开',
  '闭', '睁', '笑', '皱眉', '指尖', '手掌', '脖颈', '手腕',
] as const;

export const SANITY_UP = ['稳', '轻', '松', '暖', '亮', '快', '强', '舒', '匀', '平静', '缓', '直', '好', '清明'] as const;
export const SANITY_DOWN = ['沉', '低', '乱', '紧', '冷', '抖', '弱', '慢', '重', '浅', '急', '暗', '退', '缩', '空', '木'] as const;

/** Item-state verbs that change an object's state. */
export const ITEM_STATE_VERBS = [
  '打开', '开启', '掀开', '揭开', '锁上', '摔碎', '撕开', '点燃', '熄灭',
  '吃掉', '喝掉', '递给', '交给', '拆开',
  '拿出', '取出', '抽出', '放进', '塞进', '装上', '卸下',
] as const;

/** Item verbs that only move an object between hands. They need a review
 * unless the object ends up with someone else. */
export const ITEM_HANDLING_VERBS = ['拿出', '取出', '抽出', '放进', '塞进', '装上', '卸下'] as const;

export const NEGATION = '(?:没有|没|未|不曾|并未|未曾|并不|别|不必)';

export const TERMINAL_PUNCTUATION = /[\u3002\uff01\uff1f!?\u2026\u201d\u300d\u300f.~～)\uff09]$/u;

export const CLOSURE = /(故事|这一天|这一夜|今晚|一切|夜色|人群|喧闹)[^。！？]{0,12}(结束|落幕|告一段落|过去|平静|散去|画上)/u;
export const FAREWELL = /(后来|从此)[，,]?[^。！？]{0,12}(没有|不再|归于)/u;

/** Fields that carry a person's name in appearance text, e.g. 诺诺's
 * `手里的短枪枪口压向地面`. Used to learn who holds what. */
export const HOLD_MARKERS = ['手里的', '手中的', '掌心的', '手心里的', '肩上', '腰上', '腰间的', '背上的', '胸前的', '腕上的', '颈后的'] as const;

export const POSSESSION_VERBS = ['握着', '拿着', '攥着', '端着', '提着', '抱着', '揣着', '扶着', '举着', '抱在', '拿在', '握在', '攥在', '揣在', '端在'] as const;
