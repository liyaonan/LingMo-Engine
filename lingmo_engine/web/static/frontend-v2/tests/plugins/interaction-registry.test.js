import { describe, it, expect } from 'vitest';
import { InteractionCardRegistry } from '../../plugins/interaction-registry.js';

describe('InteractionCardRegistry', () => {
  it('register + getHandler 注册后取出 handler', () => {
    const handler = {
      css: '.test-interaction { color: red; }',
      createCard: (msg, h) => null,
      getCardData: (msg, h) => ({ type: 'test', data: null }),
    };
    InteractionCardRegistry.register('test_interaction', handler);
    expect(InteractionCardRegistry.getHandler('test_interaction')).toBe(handler);
  });

  it('hasType 存在返回 true，不存在返回 false', () => {
    InteractionCardRegistry.register('check_interaction', {});
    expect(InteractionCardRegistry.hasType('check_interaction')).toBe(true);
    expect(InteractionCardRegistry.hasType('missing_type')).toBe(false);
  });

  it('getRegisteredCSS 拼接所有 handler 的 CSS', () => {
    InteractionCardRegistry.register('css_type_a', { css: '.ia { color: red; }' });
    InteractionCardRegistry.register('css_type_b', { css: '.ib { color: blue; }' });
    const css = InteractionCardRegistry.getRegisteredCSS();
    expect(css).toContain('.ia { color: red; }');
    expect(css).toContain('.ib { color: blue; }');
  });

  it('无 css 的 handler 不加入 CSS 输出', () => {
    InteractionCardRegistry.register('no_css_type', { createCard: () => null });
    const css = InteractionCardRegistry.getRegisteredCSS();
    expect(css).not.toContain('no_css_type');
  });

  it('CSS 不重复注入同一 type', () => {
    InteractionCardRegistry.register('dup_type', { css: '.dup {}' });
    InteractionCardRegistry.register('dup_type', { css: '.dup {}' });
    const css = InteractionCardRegistry.getRegisteredCSS();
    const matches = css.match(/\.dup \{\}/g);
    expect(matches).toHaveLength(1);
  });
});
