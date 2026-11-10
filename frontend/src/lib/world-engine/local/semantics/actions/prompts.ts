/** Prompts for the three action-family tasks.
 *
 * Design rules, all of them learned from the small-model runs in this repo:
 *  - the model owns the semantic decision; the prompt says *what to judge*,
 *    never *who to pick*;
 *  - being named by the player is explicitly stated to be neither necessary
 *    nor sufficient — a character may act from its own tasks, and doing
 *    nothing is a legal answer;
 *  - every allowed entity is listed with its id, and absent entities are
 *    listed separately as distractors, so "不在场" is information the model
 *    can use instead of a rule hidden in code;
 *  - the output contract matches structured-output.ts exactly;
 *  - reaction is a TEXT task: no JSON contract (it poisons small-model prose).
 */
import type { ActionScene, SceneCharacter } from './scene';

function clip(text: string, max: number): string {
  const chars = [...text.trim()];
  return chars.length <= max ? text.trim() : `${chars.slice(0, max).join('')}…`;
}

function characterLine(character: SceneCharacter, detailed: boolean): string {
  const pending = character.tasks.filter((task) => task.status === 'pending');
  const tasks = (pending.length ? pending : character.tasks).slice(0, 2)
    .map((task) => `${task.id}=${clip(task.goal, 40)}`).join('；') || '无';
  if (!detailed) return `- ${character.name}（id=${character.id}）位置=${character.position}；精神=${character.sanity}；待办=${tasks}`;
  return `- ${character.name}（id=${character.id}）位置=${character.position}；精神=${character.sanity}/100；个性=${character.personality.map((part) => clip(part, 60)).join('；')}；待办=${tasks}`;
}

function taskLines(scene: ActionScene): string {
  const pending = scene.actor.tasks.filter((task) => task.status === 'pending');
  if (!pending.length) return '（没有待办任务）';
  return pending.slice(0, 6).map((task) => `- ${task.id}：${clip(task.goal, 60)}`).join('\n');
}

function absentLines(scene: ActionScene): string {
  if (!scene.absent.length) return '（没有其他登记角色）';
  return scene.absent.slice(0, 12).map((character) => `- ${character.name}（id=${character.id}）在${character.roomName}`).join('\n');
}

function itemLines(scene: ActionScene): string {
  if (!scene.items.length) return '（本地点没有登记物品）';
  return scene.items.slice(0, 8).map((item) => `- ${item.name}（id=${item.id}）位置=${item.position}`).join('\n');
}

function eventLines(scene: ActionScene): string {
  if (!scene.recentEvents.length) return '（无）';
  return scene.recentEvents.map((event) => `- ${clip(event, 80)}`).join('\n');
}

function placeLine(scene: ActionScene): string {
  return `${scene.roomName}（${scene.roomChain.slice(1).join(' < ') || '最高层'}）；时间 ${scene.time}`;
}

export function actionPrompt(scene: ActionScene): string {
  const playerLine = scene.isProtagonist
    ? `主角上一步的命令（已经执行过；只判断这件事是否还需要主角继续做下一步，不能改做别的事，不能复述原话）：${scene.playerInput ?? '（无）'}`
    : scene.sameRoomAsProtagonist
      // The player's exact sentence is deliberately not quoted here. In the
      // 16:46 product run the small model copied it as nono's action on all
      // three attempts ("我沿着服务巷往里走，先看清…"), so every repair failed.
      // What happened is carried by 「本回合已发生的事」; a targeted character
      // still gets the exact action in the reaction task.
      ? '主角也在同一地点；他刚做了什么或接下来要做什么，以「本回合已发生的事」为准（没有记录就是还没发生）。这是现场，不是给你的命令；只写这个角色自己的行动，不要复述或替主角行动。'
      : `主角不在这里（主角在${scene.protagonistRoomName}）；你看不到、也回应不了主角，只按本地点的情况和自己的任务判断。`;
  return [
    '你是中文跑团游戏的角色行动判断器。只输出 JSON。',
    '你要独立判断：下面这个角色此刻会不会自行行动、做什么。被玩家点名不是行动前提——角色会按自己的待办任务、职责、个性、精神状态和现场变化决定；没有理由的角色可以不行动，也没有必要人人都动。',
    '判断依据按优先级：1) 待办任务里有没有现在就该做的一步；2) 现场刚发生的事是否逼他表态、自保或阻止别人；3) 他能看见的人和物；4) 精神值和个性让他积极、犹豫还是只顾眼前。',
    '行动写成第三人称一句话，只写这个角色自己做的事，不写结果成败（结算层会判定）。不要替主角做决定，不要复述或改写玩家原话，不要用“我”自称，不要新增未登记的人物、地点、物品、往事、线索。',
    '待办任务只是方向，不是行动句：不要照抄，也不要复述目标里的连续 8 个字；写这个角色此刻具体做的这一步。例：目标“确认对方是否需要医护帮助” → 行动：她蹲下，掀开对方的袖口看伤口。不要复述或改写主角做过的事；写这个角色自己的行动。角色开口说话时写成带引号的台词，例如：诺诺回答：“我叫诺诺。”',
    scene.isProtagonist
      ? '只写主角下一步的具体动作或一句对白，不要写任务目标、计划或心理总结。输出只能是 {"kind":"act","text":"一句话行动"}（延续同一件事）或 {"kind":"skip"}（这件事不需要主角再动）。'
      : '输出只能是 {"kind":"act","text":"一句话行动"} 或 {"kind":"skip"}（这个角色此刻不行动）。',
    '',
    `【本次判断的角色】${characterLine(scene.actor, true)}`,
    `【角色待办任务】\n${taskLines(scene)}`,
    `【同地点可见人物】\n${scene.visible.length ? scene.visible.slice(0, 8).map((character) => characterLine(character, false)).join('\n') : '（只有他自己）'}`,
    `【同地点可见物品（含各人身上物品）】\n${itemLines(scene)}`,
    `【不在场角色（不能当作现场人物）】\n${absentLines(scene)}`,
    `【${playerLine}】`,
    `【本回合已发生的事】\n${eventLines(scene)}`,
    `【地点】${placeLine(scene)}`,
  ].join('\n');
}

export function targetsPrompt(scene: ActionScene, actionText: string, maxTargets: number): string {
  const candidates = scene.visible.slice(0, 8);
  return [
    '你是中文跑团游戏的牵连判断器。只输出 JSON。',
    '给定一条已经确认的行动，判断它直接牵连同地点里的哪些角色：只有会被这条行动直接触及、必须立刻做出回应的角色才算。',
    '指代按现场判断：行动里的“他/她/对方/那个人”指的是谁，由你根据在场人物、位置和刚发生的事决定，不要因为没写名字就当成没有人。',
    '行动点名的人如果不在场，不能选；名单里另列了不在场角色。行动里明确点名、要求其回应的人通常都要列入；行动只写移动、观察或对物品操作时，返回空数组。',
    '不要替行动者补写行动，不要新增人物；只输出被牵连角色的 id。',
    // Show a real registered id, never a literal like "id"/"角色id": a small
    // model copies the example and the id then fails to resolve (the 13:21Z
    // run produced a literal `id` in the updates output).
    `最多 ${maxTargets} 人。输出 {"targets":[{"targetId":"${(candidates.find((character) => character.id !== scene.actor.id) ?? candidates[0])?.id ?? scene.actor.id}"}]}；没有就是 {"targets":[]}。`,
    '',
    `【行动者】${characterLine(scene.actor, false)}`,
    `【行动】${clip(actionText, 160)}`,
    `【同地点人物】\n${candidates.length ? candidates.map((character) => characterLine(character, true)).join('\n') : '（没有其他人）'}`,
    `【不在场角色（不可选）】\n${absentLines(scene)}`,
    `【同地点物品（不是人物）】\n${itemLines(scene)}`,
    `【本回合已发生的事】\n${eventLines(scene)}`,
    `【地点】${placeLine(scene)}`,
  ].join('\n');
}

export function reactionPrompt(scene: ActionScene, source: SceneCharacter, sourceActionText: string): string {
  return [
    '你是中文跑团游戏的反应生成器。只输出正文，不要 JSON、不要解释、不要标题。',
    '写被牵连角色的即时反应：一两句第三人称，写清他/她针对发起者这条行动的反应。',
    '必须和这条威胁有因果关系；不得替发起者或主角行动；不得复述或引用发起者的原话；不得新增人物、地点、物品、往事、线索；不写结果成败（结算层会判定）。',
    '只写这个角色自己的动作、表情或对白；不要让物品凭空发光、响动或改变状态；不要照抄任务目标。',
    '',
    `【被牵连角色】${characterLine(scene.actor, true)}`,
    `【发起者】${characterLine(source, false)}`,
    `【发起者的行动】${clip(sourceActionText, 160)}`,
    `【同地点人物】\n${scene.visible.length ? scene.visible.map((character) => characterLine(character, false)).join('\n') : '（没有其他人）'}`,
    `【同地点物品】\n${itemLines(scene)}`,
    `【本回合已发生的事】\n${eventLines(scene)}`,
    `【地点】${placeLine(scene)}`,
    '反应：',
  ].join('\n');
}
