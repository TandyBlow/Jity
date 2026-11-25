/** Reaction micro workflow: trigger class -> intent candidates -> three judges.
 *
 * The judges reuse the existing task/personality/scene heads. The program owns
 * trigger understanding and a rationality gate: a threat response must avoid/
 * guard/observe, an offer must accept/hesitate, a question must answer/evade,
 * a move must yield/notice. A low-confidence or ambiguous reaction returns
 * null and the LLM writes it as before.
 */
import type { ActionScene, SceneCharacter } from '../semantics/actions/scene';
import type { MicroReactionFn, MicroReactionRequest } from '../semantics/actions/types';
import type { JudgeScores } from './judges';
import { judgeContext } from './judges';
import { longestSharedSpan } from '../semantics/actions/text';

export type ReactionTrigger = 'threat' | 'offer' | 'question' | 'move' | 'other';

export interface ReactionIntent {
  intent: string;
  category: 'hide' | 'guard' | 'observe' | 'assist' | 'communicate' | 'move';
  text: string;
  rational: boolean;
}

const OFFER = ['递给', '交给', '塞给', '递到', '送给', '递上'];
const QUESTION = ['问', '说', '喊', '告诉', '报告', '回答', '解释', '是否', '要不要', '能不能', '求助'];
const THREAT = ['枪', '开火', '射击', '攻击', '扑', '抓', '拦', '挡', '抢', '推', '撞', '挥', '踢', '威胁', '逼近', '冲', '打'];
const MOVE = ['走向', '走进', '走入', '进入', '离开', '退到', '退回', '赶到', '回到', '跑到', '冲到', '过来', '靠近'];

export function reactionTrigger(text: string): ReactionTrigger {
  const value = text.normalize('NFC');
  if (OFFER.some((word) => value.includes(word))) return 'offer';
  if (QUESTION.some((word) => value.includes(word))) return 'question';
  if (THREAT.some((word) => value.includes(word))) return 'threat';
  if (MOVE.some((word) => value.includes(word))) return 'move';
  return 'other';
}

export function reactionCandidates(scene: ActionScene, source: SceneCharacter, trigger: ReactionTrigger): ReactionIntent[] {
  const name = scene.actorName;
  const src = source.name;
  if (trigger === 'threat') {
    return [
      { intent: 'avoid', category: 'hide', text: `${name}迅速侧身避开，目光盯住${src}。`, rational: true },
      { intent: 'guard', category: 'guard', text: `${name}向后退半步，抬手护住要害。`, rational: true },
      { intent: 'observe', category: 'observe', text: `${name}蹲下寻找掩体，同时观察${src}的下一步。`, rational: true },
    ];
  }
  if (trigger === 'offer') {
    return [
      { intent: 'accept', category: 'assist', text: `${name}伸手接过，点了点头。`, rational: true },
      { intent: 'hesitate', category: 'observe', text: `${name}没有马上接，先看了看${src}。`, rational: true },
    ];
  }
  if (trigger === 'question') {
    return [
      { intent: 'answer', category: 'communicate', text: `${name}简短地回答了一句。`, rational: true },
      { intent: 'evade', category: 'observe', text: `${name}没有立刻回答，先看了看周围。`, rational: true },
    ];
  }
  if (trigger === 'move') {
    return [
      { intent: 'yield', category: 'move', text: `${name}侧身让开。`, rational: true },
      { intent: 'notice', category: 'observe', text: `${name}抬头看向${src}。`, rational: true },
    ];
  }
  return [
    { intent: 'notice', category: 'observe', text: `${name}看向${src}，没有立刻行动。`, rational: true },
  ];
}

export type ReactionJudgeFn = (
  pairs: Array<{ context: string; text: string }>,
) => Promise<JudgeScores[] | null> | JudgeScores[] | null;

export interface MicroReactionOptions {
  judge?: ReactionJudgeFn;
  threshold?: { task?: number; scene?: number; margin?: number };
  onStats?: (record: {
    candidates: number; pairs: number; inferences: number; headOutputs: number;
    ms: number; source: 'micro' | 'abstain'; reason?: string;
  }) => void;
}

export function createMicroReaction(options: MicroReactionOptions = {}): MicroReactionFn {
  return async (request: MicroReactionRequest): Promise<string | null> => {
    const started = performance.now();
    if (!options.judge) {
      options.onStats?.({
        candidates: 0, pairs: 0, inferences: 0, headOutputs: 0,
        ms: Math.round(performance.now() - started), source: 'abstain', reason: 'no_judge',
      });
      return null;
    }
    const trigger = reactionTrigger(request.sourceActionText);
    const candidates = reactionCandidates(request.scene, request.source, trigger);
    const goal = request.scene.actor.tasks.find((task) => task.status === 'pending')?.goal ?? '';
    // Keep the trained scene flags first; append the real trigger so the
    // judge sees what the reaction is responding to, not only scene booleans.
    const context = `${judgeContext({
      item: false, target: true, blocked: false, repeated: false,
      task: goal, personality: request.scene.actor.personality.join('，'),
      actor: request.scene.actorName, room: request.scene.roomName,
    })}；触发行动：${request.sourceActionText.slice(0, 100)}；发起者：${request.source.name}`;
    let scores: JudgeScores[] | null;
    try {
      scores = await options.judge(candidates.map((candidate) => ({ context, text: candidate.text })));
    } catch {
      scores = null;
    }
    if (!scores || scores.length !== candidates.length) {
      options.onStats?.({
        candidates: candidates.length, pairs: candidates.length, inferences: 0, headOutputs: 0,
        ms: Math.round(performance.now() - started), source: 'abstain', reason: 'judge_failed',
      });
      return null;
    }
    const ranked = candidates.map((candidate, index) => {
      const score = scores[index];
      return { candidate, score, total: score.task + score.personality + score.scene + (candidate.rational ? 0.6 : -0.6) };
    }).sort((left, right) => right.total - left.total);
    const best = ranked[0];
    const second = ranked[1];
    const threshold = {
      task: options.threshold?.task ?? 0.5,
      scene: options.threshold?.scene ?? 0.5,
      margin: options.threshold?.margin ?? 0,
    };
    const passed = best.candidate.rational
      && best.score.task >= threshold.task
      && best.score.scene >= threshold.scene
      && (!second || best.total - second.total >= threshold.margin)
      && longestSharedSpan(best.candidate.text, request.sourceActionText).length < 8;
    options.onStats?.({
      candidates: candidates.length, pairs: candidates.length, inferences: 0, headOutputs: 0,
      ms: Math.round(performance.now() - started), source: passed ? 'micro' : 'abstain',
      ...(passed ? {} : { reason: 'low_confidence' }),
    });
    return passed ? best.candidate.text : null;
  };
}

