/** Shared micro-model asset cache. The tokenizer file is the same for every
 * port; fetching it once per session removes N duplicate vocabulary loads. */
import { createBertTokenizer, type BertTokenizer } from './tokenizer';

const tokenizers = new Map<string, Promise<BertTokenizer>>();

export function getMicroTokenizer(vocabUrl = '/micro/minirbt-vocab.txt'): Promise<BertTokenizer> {
  let pending = tokenizers.get(vocabUrl);
  if (!pending) {
    pending = (async () => {
      const response = await fetch(vocabUrl);
      if (!response.ok) throw new Error('micro_vocab_fetch_failed');
      return createBertTokenizer(await response.text());
    })();
    tokenizers.set(vocabUrl, pending);
    pending.catch(() => tokenizers.delete(vocabUrl));
  }
  return pending;
}
