/** Lineage comparison for progress snapshots.
 *
 * The server stores a DAG: every snapshot names its parents, content identity
 * is a payload hash, and the active head is a separate pointer. This function
 * compares two snapshot IDs without consulting timestamps, so a newer clock can
 * never make a branch look like an ancestor.
 */

import { ProgressSyncError } from './types';

export interface LineageNode {
  snapshotId: string;
  parentSnapshotIds: string[];
}

export interface LineageComparison {
  leftId: string;
  rightId: string;
  same: boolean;
  diverged: boolean;
  commonAncestor: string | null;
  /** Common ancestors ordered by closeness: smallest worst-case distance first. */
  commonAncestors: string[];
  leftIsAncestorOfRight: boolean;
  rightIsAncestorOfLeft: boolean;
  leftDistanceToCommon: number | null;
  rightDistanceToCommon: number | null;
  /** Root-to-common history ([] when the two nodes share no ancestor). */
  sharedHistory: string[];
  /** Ancestor-to-leaf nodes after the common ancestor, only on the left. */
  leftOnly: string[];
  /** Ancestor-to-leaf nodes after the common ancestor, only on the right. */
  rightOnly: string[];
}

type NodeMap = Map<string, LineageNode>;

function index(nodes: readonly LineageNode[]): NodeMap {
  const map: NodeMap = new Map();
  for (const node of nodes) map.set(node.snapshotId, node);
  return map;
}

function distances(start: string, map: NodeMap): Map<string, number> {
  const result = new Map<string, number>();
  const queue: Array<[string, number]> = [[start, 0]];
  while (queue.length) {
    const [current, distance] = queue.shift()!;
    const previous = result.get(current);
    if (previous !== undefined && previous <= distance) continue;
    result.set(current, distance);
    const node = map.get(current);
    if (!node) continue;
    for (const parent of node.parentSnapshotIds) queue.push([parent, distance + 1]);
  }
  return result;
}

/** Path from `start` up to `target`, returned start -> ... -> target. */
function pathTo(start: string, target: string, map: NodeMap): string[] | null {
  if (start === target) return [start];
  const stack = [start];
  const previous = new Map<string, string | null>([[start, null]]);
  while (stack.length) {
    const current = stack.pop()!;
    const node = map.get(current);
    if (!node) continue;
    // Sorted + reversed so the lexicographically smallest parent is visited
    // first while preserving deterministic output.
    for (const parent of [...node.parentSnapshotIds].sort().reverse()) {
      if (previous.has(parent)) continue;
      previous.set(parent, current);
      if (parent === target) {
        const path = [target];
        let cursor: string | null = current;
        while (cursor !== null) {
          path.push(cursor);
          cursor = previous.get(cursor) ?? null;
        }
        return path.reverse();
      }
      stack.push(parent);
    }
  }
  return null;
}

/** Farthest known ancestor, used only when two nodes share no ancestor. */
function rootOf(start: string, map: NodeMap, distance: Map<string, number>): string {
  let best = start;
  let bestDistance = -1;
  for (const [id, value] of distance) {
    if (value > bestDistance || (value === bestDistance && id < best)) {
      best = id;
      bestDistance = value;
    }
  }
  return best;
}

function rootTo(start: string, map: NodeMap, distance: Map<string, number>): string[] {
  const path = pathTo(start, rootOf(start, map, distance), map);
  if (!path) return [start];
  return path.reverse();
}

/**
 * Compare two snapshots in a lineage DAG.
 *
 * `leftOnly` and `rightOnly` exclude the shared ancestor and are ordered
 * ancestor -> leaf, which is the order a branch picker can display.
 */
export function compareLineage(
  leftId: string,
  rightId: string,
  nodes: readonly LineageNode[],
): LineageComparison {
  const map = index(nodes);
  if (!map.has(leftId)) {
    throw new ProgressSyncError(`unknown snapshot ${leftId}`, 'unknown_snapshot', 0);
  }
  if (!map.has(rightId)) {
    throw new ProgressSyncError(`unknown snapshot ${rightId}`, 'unknown_snapshot', 0);
  }

  const leftDistances = distances(leftId, map);
  const rightDistances = distances(rightId, map);
  const common = [...leftDistances.keys()].filter((id) => rightDistances.has(id));
  const ranked = common
    .map((id) => ({
      id,
      worst: Math.max(leftDistances.get(id)!, rightDistances.get(id)!),
      sum: leftDistances.get(id)! + rightDistances.get(id)!,
    }))
    .sort((a, b) => a.worst - b.worst || a.sum - b.sum || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));

  const commonAncestor = ranked.length ? ranked[0].id : null;
  const commonAncestors = ranked.map((entry) => entry.id);
  const leftIsAncestorOfRight = commonAncestor === leftId;
  const rightIsAncestorOfLeft = commonAncestor === rightId;

  const leftRootPath = rootTo(leftId, map, leftDistances);
  const rightRootPath = rootTo(rightId, map, rightDistances);
  let sharedHistory: string[] = [];
  let leftOnly: string[] = leftRootPath;
  let rightOnly: string[] = rightRootPath;
  if (commonAncestor) {
    const commonDistances = distances(commonAncestor, map);
    sharedHistory = rootTo(commonAncestor, map, commonDistances);
    const leftPath = pathTo(leftId, commonAncestor, map);
    const rightPath = pathTo(rightId, commonAncestor, map);
    if (leftPath) leftOnly = leftPath.reverse().slice(1);
    if (rightPath) rightOnly = rightPath.reverse().slice(1);
  }

  return {
    leftId,
    rightId,
    same: leftId === rightId,
    diverged: commonAncestor !== leftId && commonAncestor !== rightId,
    commonAncestor,
    commonAncestors,
    leftIsAncestorOfRight,
    rightIsAncestorOfLeft,
    leftDistanceToCommon: commonAncestor ? leftDistances.get(commonAncestor) ?? null : null,
    rightDistanceToCommon: commonAncestor ? rightDistances.get(commonAncestor) ?? null : null,
    sharedHistory,
    leftOnly,
    rightOnly,
  };
}

/** Build `LineageNode[]` from the graph response's node summaries. */
export function lineageNodes(nodes: ReadonlyArray<{ snapshotId: string; parentSnapshotIds: string[] }>): LineageNode[] {
  return nodes.map((node) => ({ snapshotId: node.snapshotId, parentSnapshotIds: [...node.parentSnapshotIds] }));
}
