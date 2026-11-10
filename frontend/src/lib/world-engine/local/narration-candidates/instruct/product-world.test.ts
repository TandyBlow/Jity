/** Projection against the SHIPPED free-day world, not a fixture. It proves the
 * candidate reads the real static world (rooms, carried items, off-screen
 * characters) and that the opening prompt never prints a character the
 * viewpoint cannot see. No model is called. */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import type { InitialState } from '../../../types';
import { buildInitialState } from '../../state';
import { buildProjection } from './projection';
import { buildSceneUserPrompt } from './prompt';

const worldPath = resolve(process.cwd(), 'public/worlds/dragon-raja-free-day.world.json');
const world = JSON.parse(readFileSync(worldPath, 'utf8')) as {
  worldId: string;
  initial: Omit<InitialState, 'worldId'>;
};

const state = buildInitialState({ ...world.initial, worldId: world.worldId });

describe('shipped free-day world projection', () => {
  it('sees the service lane from the protagonist and nothing else', () => {
    const projection = buildProjection({ state });
    expect(projection.viewpoint.name).toBe('路明非');
    expect(projection.place.name).toBe('西侧服务巷');
    expect(projection.characters.map((entry) => entry.name)).toEqual(['路明非', '诺诺']);
    expect(projection.positions.map((entry) => entry.name)).toEqual(['路明非', '诺诺']);
    expect(projection.facts).toEqual([]);
    expect(projection.time).toContain('15:20');
  });

  it('licenses the room props and the protagonist inventory, not the shed', () => {
    const projection = buildProjection({ state });
    const items = projection.items.map((item) => item.name);
    expect(items).toContain('赛区路线图');
    expect(items).toContain('演习规则牌');
    expect(items).toContain('路明非的护目镜');
    expect(items).toContain('路明非的演习背心');
    expect(items).not.toContain('器材笼挂锁');
  });

  it('does not print an off-screen character or their knowledge in the opening prompt', () => {
    const projection = buildProjection({ state });
    const prompt = buildSceneUserPrompt(projection, {});
    expect(prompt).toContain('诺诺');
    expect(prompt).toContain('【此刻站位】');
    expect(prompt).not.toContain('芬格尔');
    expect(prompt).not.toContain('楚子航');
    expect(prompt).not.toContain('凯撒');
    expect(prompt).not.toContain('检修门');
    expect(prompt).not.toContain('【本段必须写到】');
  });
});
