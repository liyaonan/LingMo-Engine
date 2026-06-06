import { describe, it, expect } from 'vitest';
import { ContentRenderer } from '../../plugins/content-renderer.js';

describe('ContentRenderer', () => {
  it('register + getHandler 注册后取出 handler', () => {
    const handler = {
      css: '.test { color: red; }',
      createBlock: () => null,
    };
    ContentRenderer.register('test_role', handler);
    expect(ContentRenderer.getHandler('test_role')).toBe(handler);
  });

  it('hasRole 存在返回 true，不存在返回 false', () => {
    ContentRenderer.register('check_role', {});
    expect(ContentRenderer.hasRole('check_role')).toBe(true);
    expect(ContentRenderer.hasRole('missing_role')).toBe(false);
  });

  it('getRegisteredCSS 拼接多个 handler 的 CSS', () => {
    ContentRenderer.register('role_a', { css: '.a { color: red; }' });
    ContentRenderer.register('role_b', { css: '.b { color: blue; }' });
    const css = ContentRenderer.getRegisteredCSS();
    expect(css).toContain('.a { color: red; }');
    expect(css).toContain('.b { color: blue; }');
  });

  it('无 css 的 handler 不加入 CSS 输出', () => {
    ContentRenderer.register('no_css_role', { createBlock: () => null });
    const css = ContentRenderer.getRegisteredCSS();
    expect(css).not.toContain('no_css_role');
  });

  it('getRegisteredRoles 返回所有已注册 role 名', () => {
    ContentRenderer.register('role_list_a', {});
    ContentRenderer.register('role_list_b', {});
    const roles = ContentRenderer.getRegisteredRoles();
    expect(roles).toContain('role_list_a');
    expect(roles).toContain('role_list_b');
  });

  it('CSS 不重复注入同一 role', () => {
    ContentRenderer.register('dup_role', { css: '.x {}' });
    ContentRenderer.register('dup_role', { css: '.x {}' });
    const css = ContentRenderer.getRegisteredCSS();
    const matches = css.match(/\.x \{\}/g);
    expect(matches).toHaveLength(1);
  });
});
