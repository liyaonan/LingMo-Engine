import { describe, it, expect, beforeEach, vi } from 'vitest';
import { EventBus } from '../../event-bus.js';
import { AppState } from '../../state/app-state.js';

// AppState 是单例，测试间需要恢复干净状态
const initialSnapshot = AppState.snapshot();

describe('AppState', () => {
  beforeEach(() => {
    AppState.restore(initialSnapshot);
  });

  it('初始化注册 4 个内置 slice', () => {
    expect(AppState.getSlice('player')).not.toBeNull();
    expect(AppState.getSlice('world')).not.toBeNull();
    expect(AppState.getSlice('narrative')).not.toBeNull();
    expect(AppState.getSlice('ui')).not.toBeNull();
  });

  it('getSlice 不存在的 slice 返回 null', () => {
    expect(AppState.getSlice('nonexistent')).toBeNull();
  });

  it('updatePlayer 触发 state:changed:player 事件', () => {
    const spy = vi.spyOn(EventBus, 'emit');
    AppState.updatePlayer({ name: '测试' });
    expect(spy).toHaveBeenCalledWith(
      'state:changed:player',
      expect.objectContaining({ player: expect.any(Object) })
    );
    spy.mockRestore();
  });

  it('_call 方法不存在时 warn', () => {
    const spy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    AppState._call('player', 'nonExistentMethod', 'arg');
    expect(spy).toHaveBeenCalled();
    spy.mockRestore();
  });

  it('setInputEnabled(false) → isBusy() 返回 true', () => {
    AppState.setInputEnabled(false);
    expect(AppState.isBusy()).toBe(true);
  });

  it('snapshot() 导出所有已注册 slice 状态', () => {
    const snap = AppState.snapshot();
    expect(snap).toHaveProperty('player');
    expect(snap).toHaveProperty('world');
    expect(snap).toHaveProperty('narrative');
    expect(snap).toHaveProperty('ui');
  });

  it('restore() 恢复完整状态', () => {
    AppState.setInputEnabled(false);
    const snap = AppState.snapshot();
    AppState.setInputEnabled(true);
    AppState.restore(snap);
    expect(AppState.isBusy()).toBe(true);
  });

  it('registerSlice 注册插件 slice', () => {
    const factory = () => ({
      name: 'testPlugin',
      _state: { value: 42 },
      getState() { return { ...this._state }; },
      restore(s) { Object.assign(this._state, s); },
      getValue() { return this._state.value; },
    });
    AppState.registerSlice(factory);
    expect(AppState.getSlice('testPlugin')).toEqual({ value: 42 });
  });

  it('getPlayer() 调用 player slice 的 getPlayer', () => {
    AppState.updatePlayer({ name: '英雄' });
    expect(AppState.getPlayer()).toMatchObject({ name: '英雄' });
  });

  it('getCombat 和 getAbilities 未注册时返回 null', () => {
    expect(AppState.getCombat()).toBeNull();
    expect(AppState.getAbilities()).toBeNull();
  });

  it('updateCombat 终端阶段 (victory) 调用 setCombatActive(false)', () => {
    // 确保 combat slice 已注册（内联工厂）
    if (!AppState.getSlice('combat')) {
      AppState.registerSlice(() => ({
        name: 'combat',
        _state: { active: false },
        getState() { return { ...this._state }; },
        restore(s) { Object.assign(this._state, s); },
        show(s) { this._state.active = true; Object.assign(this._state, s); return 'combat'; },
        updateState(s) { Object.assign(this._state, s); return 'combat'; },
        hide() { this._state.active = false; return 'combat'; },
      }));
    }
    AppState.startCombat({ phase: 'start' });
    expect(AppState.isCombatActive()).toBe(true);

    AppState.updateCombat({ phase: 'victory' });
    expect(AppState.isCombatActive()).toBe(false);
  });

  it('updateCombat 非终端阶段不调用 setCombatActive', () => {
    AppState.startCombat({ phase: 'start' });
    AppState.updateCombat({ phase: 'player_turn' });
    expect(AppState.isCombatActive()).toBe(true);
  });

  it('endCombat 调用 hide 且不恢复输入', () => {
    AppState.startCombat({ phase: 'start' });
    AppState.endCombat();
    // endCombat() 不调用 setCombatActive(false)（仅 updateCombat 终端阶段才调用），
    // 也不恢复输入（setInputEnabled），因此 isBusy 保持为 true
    expect(AppState.isCombatActive()).toBe(true);
    expect(AppState.isBusy()).toBe(true);
  });
});
