import { describe, it, expect, beforeEach } from 'vitest';
import { createUISlice } from '../../../state/slices/ui-slice.js';

describe('UISlice', () => {
  let slice;

  beforeEach(() => {
    slice = createUISlice();
  });

  it('初始默认值', () => {
    expect(slice.getInputEnabled()).toBe(true);
    expect(slice.isBusy()).toBe(false);
    expect(slice.isCombatActive()).toBe(false);
    expect(slice.getActivePlugin()).toBe(null);
  });

  it('setInputEnabled(false) 联动 isBusy=true', () => {
    slice.setInputEnabled(false);
    expect(slice.getInputEnabled()).toBe(false);
    expect(slice.isBusy()).toBe(true);
  });

  it('setInputEnabled(true) 恢复', () => {
    slice.setInputEnabled(false);
    slice.setInputEnabled(true);
    expect(slice.isBusy()).toBe(false);
  });

  it('setActivePlugin 设置插件名', () => {
    slice.setActivePlugin('inventory');
    expect(slice.getState().activePlugin).toBe('inventory');
  });

  it('setActivePlugin(null) 关闭', () => {
    slice.setActivePlugin('character');
    slice.setActivePlugin(null);
    expect(slice.getState().activePlugin).toBe(null);
  });

  it('setActivePlugin 切换不同插件', () => {
    slice.setActivePlugin('character');
    slice.setActivePlugin('inventory');
    expect(slice.getState().activePlugin).toBe('inventory');
  });

  it('toggleSavePanel 无参 toggle', () => {
    expect(slice.getState().savePanelOpen).toBe(false);
    slice.toggleSavePanel();
    expect(slice.getState().savePanelOpen).toBe(true);
    slice.toggleSavePanel();
    expect(slice.getState().savePanelOpen).toBe(false);
  });

  it('toggleSavePanel 有参直接设值', () => {
    slice.toggleSavePanel(true);
    expect(slice.getState().savePanelOpen).toBe(true);
    slice.toggleSavePanel(false);
    expect(slice.getState().savePanelOpen).toBe(false);
  });

  it('setCombatActive(true) 后 getInputEnabled 返回 false', () => {
    slice.setCombatActive(true);
    expect(slice.getInputEnabled()).toBe(false);
  });

  it('setCombatActive(false) 后 getInputEnabled 以 inputEnabled 为准', () => {
    slice.setCombatActive(true);
    slice.setCombatActive(false);
    expect(slice.getInputEnabled()).toBe(true);
  });

  it('getState() 返回副本', () => {
    const state1 = slice.getState();
    state1.inputEnabled = false;
    expect(slice.getState().inputEnabled).toBe(true);
  });

  it('restore() 恢复状态', () => {
    slice.setInputEnabled(false);
    slice.setActivePlugin('character');
    const snap = JSON.parse(JSON.stringify(slice.getState()));
    slice.setInputEnabled(true);
    slice.setActivePlugin(null);
    slice.restore(snap);
    expect(slice.getState().inputEnabled).toBe(false);
    expect(slice.getState().activePlugin).toBe('character');
  });
});
