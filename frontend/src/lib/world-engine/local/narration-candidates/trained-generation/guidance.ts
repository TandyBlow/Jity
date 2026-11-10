/** Grounded repair guidance for the bounded retry.
 *
 * Guidance is built ONLY from committed fact phrases, the ledger's licensed
 * vocabulary and the verifier's issue kinds. It never quotes hidden knowledge
 * (that would leak the secret), never contains a finished paragraph and never
 * claims that a retry fixed anything. Every attempt that consumes it is timed
 * in the end-to-end result.
 */
import type { NarrationFact } from '../../../runtime/committed-narration';
import { factPhrases } from '../../../runtime/committed-narration';
import type { NarrationIssue, NarrationLedger, NarrationPolicy } from './types';

const UNIT_CN: Record<string, string> = { second: '秒', minute: '分钟', hour: '小时', day: '天', month: '个月', year: '年' };

const FACT_ISSUES = new Set<NarrationIssue['kind']>([
  'fact_omitted', 'fact_actor_swap', 'fact_direction_reversed', 'fact_wrong_number',
  'fact_wrong_time', 'fact_task_claimed', 'fact_movement_claimed', 'fact_position_claimed',
  'fact_event_added',
]);

export function buildRevisionGuidance(
  issues: readonly NarrationIssue[],
  ledger: NarrationLedger,
  policy: NarrationPolicy,
): string {
  if (!issues.length) return '';
  const kinds = new Set(issues.map((issue) => issue.kind));
  const lines: string[] = [];

  const omitted = issues.filter((issue) => issue.kind === 'fact_omitted').map((issue) => issue.detail);
  if ([...kinds].some((kind) => FACT_ISSUES.has(kind))) {
    const required = omitted.length ? omitted : guidancePhrases(ledger.mandatory);
    if (required.length) lines.push(`已结算的事实只能这样写：${required.slice(0, 3).join('；')}。`);
  }
  if (kinds.has('fact_event_added') || kinds.has('fact_movement_claimed') || kinds.has('fact_position_claimed')) {
    lines.push('不要写输入里没有发生的动作、站位或移动。');
  }
  if (kinds.has('fact_actor_swap')) lines.push('每个动作和结果只能写在它本来就属于的那个人身上。');
  if (kinds.has('fact_wrong_number') || kinds.has('fact_wrong_time')) lines.push('数字和时间必须和输入完全一致。');
  if (kinds.has('time_missing') && ledger.time) {
    lines.push(`要写出时间过去了约${ledger.time.duration.amount}${UNIT_CN[ledger.time.duration.unit] ?? ledger.time.duration.unit}。`);
  }
  if (kinds.has('perspective_leak')) {
    lines.push(`只写${ledger.viewpoint?.name ?? '主角'}能看到、能知道的内容，不要写其他人物的内心。`);
  }
  if (kinds.has('knowledge_leak')) lines.push('不要写输入里没有的信息。');
  if (kinds.has('promise_without_fact')) lines.push('不要新增输入里没有的承诺。');
  if (kinds.has('past_without_fact')) lines.push('不要补写输入里没有的往事。');
  if (kinds.has('unlicensed_entity')) lines.push('只使用输入里出现的人名、地点和物品。');
  if (kinds.has('echo_prior') || kinds.has('loop_repeated_sentence') || kinds.has('loop_repeated_clause')) {
    lines.push('不要重复上一段或本段已经出现的句子，用新的写法。');
  }
  if (kinds.has('too_short') || kinds.has('premature_closure')) {
    lines.push(`篇幅写到约${policy.targetChars ?? 260}字，不要提前收尾。`);
  }
  if (kinds.has('empty_narration')) lines.push('上一稿是空的，这次写出正文。');
  if (kinds.has('truncated')) lines.push('上一稿被截断，这次要写完整。');
  if (kinds.has('prompt_echo')) lines.push('不要复述写作要求，只写正文。');
  return lines.length ? ['【本次写作要求】', ...lines].join('\n') : '';
}

function guidancePhrases(facts: readonly NarrationFact[]): string[] {
  return facts.slice(0, 3).map((fact) => factPhrases(fact)[0]);
}
