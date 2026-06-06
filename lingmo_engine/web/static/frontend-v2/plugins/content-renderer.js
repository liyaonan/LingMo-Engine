// plugins/content-renderer.js
// 内容类型渲染注册表 — 插件通过此注册表向 narrative-area 注册自定义内容类型的 DOM 渲染逻辑
// 避免核心组件硬编码插件特有的内容类型（如 combat_narrative, encounter 等）

const _handlers = new Map(); // role → handler
const _cssBlocks = [];        // 已注册的 CSS 块

export const ContentRenderer = {
  /**
   * 注册内容类型处理器
   * @param {string} role — 消息 role 字段值
   * @param {object} handler
   * @param {string} handler.css — CSS 样式（注入到 narrative-area shadow DOM）
   * @param {function} handler.createBlock — (msg, helpers) → HTMLElement | null
   * @param {function} handler.getBlockData — (msg, helpers) → {type, content?, data?}
   * @param {function} [handler.createStreamBlock] — (data, helpers) → HTMLElement | null，流式渲染
   * @param {function} [handler.flushStream] — (el, buffer, helpers) → void，刷新流式内容
   */
  register(role, handler) {
    _handlers.set(role, handler);
    if (handler.css && !_cssBlocks.includes(role)) {
      _cssBlocks.push(role);
    }
  },

  /** 获取所有已注册的 CSS（由 narrative-area 注入） */
  getRegisteredCSS() {
    let css = '';
    for (const role of _cssBlocks) {
      const h = _handlers.get(role);
      if (h && h.css) css += h.css;
    }
    return css;
  },

  /** 根据 role 获取处理器 */
  getHandler(role) {
    return _handlers.get(role);
  },

  /** 检查是否有处理该 role 的注册 */
  hasRole(role) {
    return _handlers.has(role);
  },

  /** 调试：列出所有已注册的 role */
  getRegisteredRoles() {
    return Array.from(_handlers.keys());
  },
};
