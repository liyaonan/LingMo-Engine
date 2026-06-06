// plugins/interaction-registry.js
// 交互卡片注册表 — 插件通过此注册表向 narrative-area 注册交互卡片的渲染逻辑
// 与 ContentRenderer 平行，ContentRenderer 处理内容流渲染，本模块处理交互卡（遭遇、战利品、战斗回顾等）
// 交互卡固定显示在每页视图的尾部插槽

const _handlers = new Map(); // interactionType → handler
const _cssBlocks = [];        // 已注册的 CSS 块（避免重复注入）

export const InteractionCardRegistry = {
  /**
   * 注册交互卡片处理器
   * @param {string} interactionType — 交互卡片类型标识
   * @param {object} handler
   * @param {string} [handler.css] — CSS 样式（注入到 narrative-area shadow DOM）
   * @param {function} handler.createCard — (msg, helpers) → HTMLElement | null
   * @param {function} handler.getCardData — (msg, helpers) → {type, content?, data?}
   */
  register(interactionType, handler) {
    _handlers.set(interactionType, handler);
    if (handler.css && !_cssBlocks.includes(interactionType)) {
      _cssBlocks.push(interactionType);
    }
  },

  /** 获取所有已注册的 CSS（由 narrative-area 注入） */
  getRegisteredCSS() {
    let css = '';
    for (const type of _cssBlocks) {
      const h = _handlers.get(type);
      if (h && h.css) css += h.css;
    }
    return css;
  },

  /** 根据 interactionType 获取处理器 */
  getHandler(type) {
    return _handlers.get(type);
  },

  /** 检查是否有处理该 interactionType 的注册 */
  hasType(type) {
    return _handlers.has(type);
  },

  /** 调试：列出所有已注册的交互类型 */
  getRegisteredTypes() {
    return Array.from(_handlers.keys());
  },
};
