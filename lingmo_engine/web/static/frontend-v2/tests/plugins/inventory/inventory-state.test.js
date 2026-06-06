import { describe, it, expect, beforeEach } from 'vitest';
import { createInventoryState } from '/static/plugins/inventory/frontend-v2/inventory-state.js';

describe('InventoryState', () => {
  let slice;

  beforeEach(() => {
    slice = createInventoryState();
  });

  it('初始状态为默认值', () => {
    const state = slice.getState();
    expect(state.inventory).toEqual([]);
    expect(state.equipment).toEqual({});
    expect(state.gold).toBe(0);
    expect(state.max_slots).toBe(30);
  });

  it('updateFullState 完整赋值', () => {
    slice.updateFullState({
      inventory: [{ id: 'sword' }],
      equipment: { weapon: 'sword' },
      categories: ['武器'],
      rarities: ['common'],
      slots: ['weapon'],
      gold: 100,
      max_slots: 40,
      player_name: '勇者',
    });
    const state = slice.getState();
    expect(state.inventory).toEqual([{ id: 'sword' }]);
    expect(state.equipment).toEqual({ weapon: 'sword' });
    expect(state.gold).toBe(100);
    expect(state.max_slots).toBe(40);
    expect(state.player_name).toBe('勇者');
  });

  it('updateFullState({}) 容错使用默认值', () => {
    slice.updateFullState({});
    const state = slice.getState();
    expect(state.inventory).toEqual([]);
    expect(state.gold).toBe(0);
    expect(state.max_slots).toBe(30);
    expect(state.player_name).toBe('');
  });

  it('update 部分合并', () => {
    slice.update({ gold: 200 });
    expect(slice.getState().gold).toBe(200);
  });

  it('getState() 返回副本（浅拷贝）', () => {
    const state1 = slice.getState();
    const state2 = slice.getState();
    // 返回的是不同对象引用（不是同一个 _state）
    expect(state1).not.toBe(state2);
    expect(state1).toEqual(state2);
  });

  it('restore() 恢复状态', () => {
    slice.updateFullState({ gold: 500, player_name: 'A' });
    const snap = JSON.parse(JSON.stringify(slice.getState()));
    slice.updateFullState({ gold: 0, player_name: 'B' });
    slice.restore(snap);
    expect(slice.getState().gold).toBe(500);
    expect(slice.getState().player_name).toBe('A');
  });
});
