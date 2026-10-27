/** Page-level world reads. list_points serves ascending sequence pages; the
 * true head is the last point of the LAST page — rendering from a single
 * page shows stale state for any world past one page. */
import type { WorldTransport } from '../transport';
import type { DataMap, Id } from '../types';

export type PointSummary = DataMap['list_points']['points'][number];

export async function readAllPoints(transport: WorldTransport, worldId: Id, pageSize = 100): Promise<PointSummary[]> {
  const points: PointSummary[] = [];
  let after: number | null = null;
  for (;;) {
    const page: PointSummary[] = (await transport.execute('list_points', { after, limit: pageSize }, { worldId })).data.points;
    if (page.length === 0) break;
    const last = points.at(-1)?.sequence ?? null;
    if (last != null && page[0].sequence <= last) throw new Error('list_points_page_makes_no_progress');
    points.push(...page);
    if (page.length < pageSize) break;
    after = page[page.length - 1].sequence;
  }
  return points;
}
