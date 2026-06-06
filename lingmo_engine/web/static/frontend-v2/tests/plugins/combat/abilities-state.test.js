import { describe, it, expect, beforeEach } from 'vitest';
import { createAbilitiesState } from '/static/plugins/combat/frontend-v2/abilities-state.js';

describe('AbilitiesState', () => {
  let slice;

  beforeEach(() => {
    slice = createAbilitiesState();
  });

  it('初始状态为默认值', () => {
    const state = slice.getState();
    expect(state.abilities).toEqual([]);
    expect(state.categories).toEqual([]);
    expect(state.rarities).toEqual([]);
    expect(state.max_abilities).toBe(20);
    expect(state.player_name).toBe('');
  });

  it('updateFullState 完整赋值', () => {
    slice.updateFullState({
      abilities: [{ id: 'fireball', name: '火球术' }],
      categories: ['攻击'],
      rarities: ['rare'],
      max_abilities: 10,
      player_name: '法师',
    });
    const state = slice.getState();
    expect(state.abilities).toHaveLength(1);
    expect(state.categories).toEqual(['攻击']);
    expect(state.max_abilities).toBe(10);
    expect(state.player_name).toBe('法师');
  });

  it('updateFullState({}) 容错使用默认值', () => {
    slice.updateFullState({});
    const state = slice.getState();
    expect(state.abilities).toEqual([]);
    expect(state.max_abilities).toBe(20);
    expect(state.player_name).toBe('');
  });

  it('getState() 返回新对象（浅拷贝）', () => {
    slice.updateFullState({ player_name: '原版' });
    const state1 = slice.getState();
    state1.player_name = '改过';
    // 顶层字段不受外部修改影响（浅拷贝特性）
    expect(slice.getState().player_name).toBe('原版');
  });

  it('restore() 恢复状态', () => {
    slice.updateFullState({ max_abilities: 5, player_name: 'A' });
    const snap = JSON.parse(JSON.stringify(slice.getState()));
    slice.updateFullState({ max_abilities: 99, player_name: 'B' });
    slice.restore(snap);
    expect(slice.getState().max_abilities).toBe(5);
    expect(slice.getState().player_name).toBe('A');
  });
});
