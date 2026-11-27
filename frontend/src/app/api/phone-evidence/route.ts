import { mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

export const runtime = 'nodejs';

/** Dev-only sink for the phone evidence panel: the phone POSTs its compact
 * turn JSON here and the acceptance session reads it from artifacts/. */
export async function POST(request: Request): Promise<Response> {
  const text = await request.text();
  if (text.length > 65_536) return new Response('too large', { status: 413 });
  try {
    JSON.parse(text);
  } catch {
    return new Response('not json', { status: 400 });
  }
  const dir = join(process.cwd(), '..', 'artifacts', 'goal', 'micro-workflow', 'phone-evidence');
  mkdirSync(dir, { recursive: true });
  const stamp = new Date().toISOString().replace(/[:.]/g, '-');
  writeFileSync(join(dir, `phone-${stamp}.json`), text, 'utf8');
  return Response.json({ ok: true });
}
