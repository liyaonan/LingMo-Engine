import { describe, it, expect, beforeEach } from 'vitest';
import { createWorldSlice } from '../../../state/slices/world-slice.js';

describe('WorldSlice', () => {
  let slice;

  beforeEach(() => {
    slice = createWorldSlice();
  });

  it('初始状态 worldTitle 为默认值', () => {
    const state = slice.getState();
    expect(state.worldTitle).toBe('LingMo Engine');
    expect(state.location).toBeNull();
    expect(state.breadcrumb).toEqual([]);
  });

  it('getLocation() 返回 location', () => {
    expect(slice.getLocation()).toBeNull();
  });

  it('updateFromState 更新已识别字段', () => {
    slice.updateFromState({
      location: '埃尔林森林',
      breadcrumb: ['起点', '森林'],
      game_time: { display: '清晨', time_of_day: '上午' },
    });
    expect(slice.getLocation()).toBe('埃尔林森林');
    const state = slice.getState();
    expect(state.breadcrumb).toEqual(['起点', '森林']);
    expect(state.gameTime).toEqual({ display: '清晨', time_of_day: '上午' });
  });

  it('updateFromState 忽略未定义字段', () => {
    slice.updateFromState({ location: 'A' });
    slice.updateFromState({});
    expect(slice.getLocation()).toBe('A');
  });

  it('updateFromState 的 key 命名转换', () => {
    slice.updateFromState({ current_node: { id: 'n1' }, game_time: { display: '夜晚', time_of_day: '夜晚' } });
    const state = slice.getState();
    expect(state.currentNode).toEqual({ id: 'n1' });
    expect(state.gameTime).toEqual({ display: '夜晚', time_of_day: '夜晚' });
  });

  it('getState() 返回副本', () => {
    slice.updateFromState({ location: '原' });
    const state1 = slice.getState();
    state1.location = '改';
    expect(slice.getLocation()).toBe('原');
  });

  it('restore() 恢复状态', () => {
    slice.updateFromState({ location: 'A' });
    const snap = JSON.parse(JSON.stringify(slice.getState()));
    slice.updateFromState({ location: 'B' });
    slice.restore(snap);
    expect(slice.getLocation()).toBe('A');
  });
});
