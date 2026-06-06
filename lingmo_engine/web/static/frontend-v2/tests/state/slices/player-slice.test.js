import { describe, it, expect, beforeEach } from 'vitest';
import { createPlayerSlice } from '../../../state/slices/player-slice.js';

describe('PlayerSlice', () => {
  let slice;

  beforeEach(() => {
    slice = createPlayerSlice();
  });

  it('初始状态 getPlayer() 返回 null', () => {
    expect(slice.getPlayer()).toBeNull();
  });

  it('updatePlayer 合并数据', () => {
    slice.updatePlayer({ name: '勇者', hp: 100 });
    expect(slice.getPlayer()).toMatchObject({ name: '勇者', hp: 100 });

    slice.updatePlayer({ mp: 50 });
    expect(slice.getPlayer()).toMatchObject({ name: '勇者', hp: 100, mp: 50 });
  });

  it('return 返回 "player"', () => {
    const key = slice.updatePlayer({ name: 'test' });
    expect(key).toBe('player');
  });

  it('setAttributesSchema 存储 schema', () => {
    const schema = { hp: { type: 'number', label: 'HP' } };
    slice.setAttributesSchema(schema);
    expect(slice.getSchema()).toEqual(schema);
  });

  it('setStateUpdate 同时更新 player 和 inventory', () => {
    slice.setStateUpdate({
      player: { name: '勇者' },
      inventory: [{ id: 'sword' }],
    });
    expect(slice.getPlayer()).toMatchObject({ name: '勇者' });
    expect(slice.getInventory()).toEqual([{ id: 'sword' }]);
  });

  it('setCharacterData 完整存储 4 个参数', () => {
    slice.setCharacterData(
      { name: 'char' },
      { panel: 'config' },
      { fireball: {} },
      { weapon: true }
    );
    const state = slice.getState();
    expect(state.characterData).toEqual({ name: 'char' });
    expect(state.panelConfig).toEqual({ panel: 'config' });
    expect(state.abilitiesData).toEqual({ fireball: {} });
    expect(state.equipmentExpanded).toEqual({ weapon: true });
  });

  it('getState() 返回副本，修改顶层属性不影响内部', () => {
    slice.updatePlayer({ name: '原' });
    const state1 = slice.getState();
    state1.characterData = '改';
    expect(slice.getState().characterData).toBeNull();
  });

  it('restore() 恢复状态', () => {
    slice.updatePlayer({ name: 'A', hp: 100 });
    const snap = JSON.parse(JSON.stringify(slice.getState()));
    slice.updatePlayer({ name: 'B' });
    slice.restore(snap);
    expect(slice.getPlayer().name).toBe('A');
    expect(slice.getPlayer().hp).toBe(100);
  });
});
