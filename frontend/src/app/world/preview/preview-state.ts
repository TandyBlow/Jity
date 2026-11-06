/** 预览区的状态判定：事实、尚未展示、无法恢复三者互斥优先。
 * 判断只依赖适配器返回的字段，不猜测缺失内容。 */

export interface PreviewFact { kind: string; sentence: string }
export interface PreviewGap { gap: string; replayFailure?: string | null }
export interface PreviewInput {
  facts: PreviewFact[];
  gaps: PreviewGap[];
  notDisplayed: { reason: string }[];
  delta: unknown;
}

export interface PreviewView {
  sentences: string[];
  band: 'gap' | 'unshown' | 'facts' | 'empty';
  gapMessages: string[];
  unshownReason: string | null;
  /** 恢复失败时不得出现任何“没有变化”的措辞 */
  quietPoint: boolean;
}

const EMPTY_DELTA = (delta: unknown): boolean => {
  if (delta === null || delta === undefined) return true;
  if (typeof delta === 'object' && !Array.isArray(delta)) return Object.keys(delta as object).length === 0;
  return false;
};

export function describePreview(input: PreviewInput): PreviewView {
  const sentences = input.facts.map((fact) => fact.sentence);
  const gapMessages = input.gaps.map((gap) => (
    gap.replayFailure === 'ledger'
      ? `${gap.gap}（重放发现摘要不一致，未用检查点兜底）`
      : gap.gap
  ));
  if (input.gaps.length > 0) {
    return { sentences, band: 'gap', gapMessages, unshownReason: null, quietPoint: false };
  }
  if (input.notDisplayed.length > 0) {
    return {
      sentences, band: 'unshown', gapMessages, unshownReason: input.notDisplayed[0].reason, quietPoint: false,
    };
  }
  if (sentences.length > 0) {
    return { sentences, band: 'facts', gapMessages, unshownReason: null, quietPoint: false };
  }
  return {
    sentences,
    band: 'empty',
    gapMessages,
    unshownReason: null,
    quietPoint: EMPTY_DELTA(input.delta),
  };
}
