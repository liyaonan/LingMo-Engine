import { describe, it, expect, beforeEach } from 'vitest';
import { PluginRegistry } from '../../plugins/plugin-registry.js';

describe('PluginRegistry', () => {
  beforeEach(() => {
    // PluginRegistry 是单例，通过注册新值覆盖旧值
  });

  it('register + get 注册后取出 config（旧 API 兼容）', () => {
    PluginRegistry.register('test', {
      tagName: 'test-component',
      stateSlice: { name: 'test' },
    });
    const config = PluginRegistry.get('test');
    expect(config.name).toBe('test');
    // 旧 register() 将 tagName 归一化到 ui.tagName
    expect(config.ui.tagName).toBe('test-component');
    expect(config.ui.mode).toBe('overlay');
  });

  it('registerPlugin + getPlugin 注册后取出完整 config', () => {
    PluginRegistry.registerPlugin({
      name: 'test-plugin',
      button: { label: '测试', icon: null },
      ui: { mode: 'panel', tagName: 'test-panel' },
    });
    const config = PluginRegistry.getPlugin('test-plugin');
    expect(config.name).toBe('test-plugin');
    expect(config.button.label).toBe('测试');
    expect(config.ui.mode).toBe('panel');
    expect(config.ui.tagName).toBe('test-panel');
  });

  it('has 存在返回 true，不存在返回 false', () => {
    PluginRegistry.register('test', { tagName: 't' });
    expect(PluginRegistry.has('test')).toBe(true);
    expect(PluginRegistry.has('nonexistent')).toBe(false);
  });

  it('list 返回所有已注册名称', () => {
    PluginRegistry.register('a', { tagName: 'a' });
    PluginRegistry.register('b', { tagName: 'b' });
    const names = PluginRegistry.list();
    expect(names).toContain('a');
    expect(names).toContain('b');
  });

  it('覆盖注册 — 同名再次 register 覆盖旧值', () => {
    PluginRegistry.register('test', { tagName: 'old' });
    PluginRegistry.register('test', { tagName: 'new' });
    expect(PluginRegistry.get('test').ui.tagName).toBe('new');
  });

  it('get 不存在的返回 null', () => {
    expect(PluginRegistry.get('nonexistent')).toBeNull();
  });

  it('listAll 按顺序：左系统 → 插件 → 右系统', () => {
    PluginRegistry.registerPlugin({
      name: 'sys-left', system: true, position: 'left',
      button: { label: 'L', icon: null },
      ui: { mode: 'panel', tagName: 'left-panel' },
    });
    PluginRegistry.registerPlugin({
      name: 'plugin-mid',
      button: { label: 'M', icon: null },
      ui: { mode: 'panel', tagName: 'mid-panel' },
    });
    PluginRegistry.registerPlugin({
      name: 'sys-right', system: true, position: 'right',
      button: { label: 'R', icon: null },
      ui: { mode: 'panel', tagName: 'right-panel' },
    });
    const all = PluginRegistry.listAll();
    const names = all.map(p => p.name);
    const leftIdx = names.indexOf('sys-left');
    const midIdx = names.indexOf('plugin-mid');
    const rightIdx = names.indexOf('sys-right');
    // 左系统在最前，插件在中间，右系统在最后
    expect(leftIdx).toBeLessThan(midIdx);
    expect(midIdx).toBeLessThan(rightIdx);
  });
});
