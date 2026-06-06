import { describe, it, expect, beforeEach } from 'vitest';
import { createCombatState } from '/static/plugins/combat/frontend-v2/combat-state.js';

describe('CombatState', () => {
  let slice;

  beforeEach(() => {
    slice = createCombatState();
  });

  it('初始状态 active 为 false', () => {
    const state = slice.getState();
    expect(state.active).toBe(false);
  });

  it('show() 设置 active=true 并合并字段', () => {
    slice.show({
      round: 3,
      phase: 'player_turn',
      enemies: [{ id: 'e1', name: '哥布林' }],
      player: { hp: 80 },
      pool_attrs: ['hp', 'mp'],
      log: ['战斗开始'],
    });
    const state = slice.getState();
    expect(state.active).toBe(true);
    expect(state.round).toBe(3);
    expect(state.phase).toBe('player_turn');
    expect(state.enemies).toHaveLength(1);
    expect(state.player).toEqual({ hp: 80 });
    expect(state.poolAttrs).toEqual(['hp', 'mp']);
    expect(state.log).toEqual(['战斗开始']);
  });

  it('show() 空对象使用默认值', () => {
    slice.show({});
    const state = slice.getState();
    expect(state.active).toBe(true);
    expect(state.round).toBe(1);
    expect(state.enemies).toEqual([]);
  });

  it('updateState() 增量更新不覆盖未传字段', () => {
    slice.show({ round: 3, phase: 'player_turn', enemies: [{ id: 'e1' }] });
    slice.updateState({ phase: 'enemy_turn' });
    const state = slice.getState();
    expect(state.phase).toBe('enemy_turn');
    expect(state.round).toBe(3);
    expect(state.enemies).toHaveLength(1);
  });

  it('hide() 设 active=false，其他字段不变', () => {
    slice.show({ round: 2, enemies: [{ id: 'e1' }] });
    slice.hide();
    const state = slice.getState();
    expect(state.active).toBe(false);
    expect(state.round).toBe(2);
  });

  it('clear() 重置 enemies/player/log', () => {
    slice.show({ enemies: [{ id: 'e1' }], player: { hp: 100 }, log: ['a'] });
    slice.clear();
    const state = slice.getState();
    expect(state.active).toBe(false);
    expect(state.enemies).toEqual([]);
    expect(state.player).toBeNull();
    expect(state.log).toEqual([]);
  });

  it('getState() 返回副本', () => {
    slice.show({ round: 1 });
    const state1 = slice.getState();
    state1.round = 999;
    expect(slice.getState().round).toBe(1);
  });

  it('restore() 恢复状态', () => {
    slice.show({ round: 5, phase: 'player_turn' });
    const snap = JSON.parse(JSON.stringify(slice.getState()));
    slice.show({ round: 10, phase: 'enemy_turn' });
    slice.restore(snap);
    expect(slice.getState().round).toBe(5);
    expect(slice.getState().phase).toBe('player_turn');
  });
});
