import { describe, expect, it } from 'vitest';
import type { WorldState } from '../../../types';
import { informationHint, readInformations } from './fact-informations';

const state = {
  initial: {
    characters: {
      lu: { name: '路明非' },
      nono: { name: '诺诺' },
      tang: { name: '唐骁', initialAppearance: '红色识别带勒在肩上，护目镜完好。' },
    },
    items: {
      rules: { name: '演习规则牌', initialAppearance: '牌面写明：使用弗里嘉演习弹；护目镜必须戴好；医护白线禁射；15:45停赛。' },
      map: { name: '赛区路线图', initialAppearance: '图上画出庭院、东西回廊；地下检修通道用虚线标注。' },
      camera: { name: '芬格尔的相机', initialAppearance: '镜头盖已经取下；电池图标只剩一格。' },
    },
    locations: { lane: { name: '服务巷', slots: [] }, shed: { name: '器材棚', slots: [] } },
  },
  characters: {
    lu: { position: { containerId: 'lane' } },
    nono: { position: { containerId: 'shed' } },
    tang: { position: { containerId: 'lane' } },
  },
  items: {
    rules: { position: { containerId: 'lane' } },
    map: { position: { containerId: 'shed' } },
    camera: { position: { containerId: 'shed' } },
  },
  locations: { lane: {}, shed: {} },
} as unknown as WorldState;

describe('information hints', () => {
  it('reads the appearance clause that shares the action topic', () => {
    const hint = informationHint('我读服务巷规则牌上关于医护白线的条款', ['rules'], state, 'achieved', 'lu');
    expect(hint).toEqual({ entityId: 'rules', text: '医护白线禁射' });
  });
  it('extracts a longer shared term from another document', () => {
    const hint = informationHint('我查看图上地下检修通道的标注', ['map'], state, 'partial', 'nono');
    expect(hint?.text).toBe('地下检修通道用虚线标注');
  });
  it('abstains when the action names no topic from the appearance', () => {
    expect(informationHint('我看看规则牌', ['rules'], state, 'achieved', 'lu')).toBeNull();
  });
  it('does not carry the registered name itself as a topic', () => {
    expect(informationHint('我查看芬格尔的相机', ['camera'], state, 'achieved', 'nono')).toBeNull();
  });
  it('requires the reader and the item in the same room', () => {
    expect(informationHint('我读服务巷规则牌上关于医护白线的条款', ['rules'], state, 'achieved', 'nono')).toBeNull();
  });
  it('uses the arrival room of a compound move', () => {
    const hint = informationHint('我读服务巷规则牌上关于医护白线的条款', ['rules'], state, 'achieved', 'nono', 'lane');
    expect(hint?.text).toBe('医护白线禁射');
  });
  it('uses the sub-action destination of a move-and-read action', () => {
    const hint = informationHint('我走进服务巷，读规则牌上关于医护白线的条款', ['rules'], state, 'achieved', 'nono', 'shed', { containerId: 'lane' });
    expect(hint?.text).toBe('医护白线禁射');
  });
  it('reads a character appearance clause the same way', () => {
    const hint = informationHint('我查看唐骁左臂识别带的颜色', ['tang'], state, 'achieved', 'lu');
    expect(hint?.text).toBe('红色识别带勒在肩上');
  });
  it('requires one item and an achieved or partial action', () => {
    expect(informationHint('我读规则牌上关于医护白线的条款', ['rules', 'map'], state, 'achieved', 'lu')).toBeNull();
    expect(informationHint('我读规则牌上关于医护白线的条款', ['rules'], state, 'blocked', 'lu')).toBeNull();
  });
});

describe('information tags', () => {
  it('parses the micro tag out of a settled fact', () => {
    expect(readInformations(['路明非读规则牌（达到目的）；信息=rules:医护白线禁射；涉及=nono']))
      .toEqual([{ entityId: 'rules', text: '医护白线禁射' }]);
  });
});
