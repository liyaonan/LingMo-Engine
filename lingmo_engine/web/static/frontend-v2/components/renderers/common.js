// renderers/common.js
// 通用渲染器工具函数

/**
 * 根据 filter 条件匹配属性定义
 * @param {Object} def - schema 中的属性定义
 * @param {Object} filter - 过滤条件对象
 *   value 以 "!" 开头: 排除匹配（def[key] !== 去掉!后的值）
 *   value 为 false: 匹配字段不存在或为 falsy
 *   其他: 精确匹配
 * @returns {boolean}
 */
export function matchFilter(def, filter) {
  if (!filter) return false;
  for (const [key, expected] of Object.entries(filter)) {
    const actual = def[key];
    if (typeof expected === 'string' && expected.startsWith('!')) {
      if (actual === expected.slice(1)) return false;
    } else if (expected === false) {
      if (actual) return false;
    } else {
      if (actual !== expected) return false;
    }
  }
  return true;
}

/**
 * 从对象中按点分路径取值
 */
export function getNestedValue(obj, path) {
  if (!path || !obj) return undefined;
  const parts = path.split('.');
  let current = obj;
  for (const p of parts) {
    if (current == null) return undefined;
    current = current[p];
  }
  return current;
}

/**
 * 构建带标题的 section card 容器
 */
export function buildSectionCard(title, innerHtml) {
  const titleHtml = title
    ? `<div class="section-title">${title}</div>`
    : '';
  return `<div class="section-card">${titleHtml}${innerHtml}</div>`;
}

/**
 * 轻量颜色变亮（hex → 稍亮 hex）
 */
export function lightenColor(hex, amount = 0.2) {
  if (!hex || !hex.startsWith('#')) return hex;
  let r = parseInt(hex.slice(1, 3), 16);
  let g = parseInt(hex.slice(3, 5), 16);
  let b = parseInt(hex.slice(5, 7), 16);
  r = Math.min(255, Math.round(r + (255 - r) * amount));
  g = Math.min(255, Math.round(g + (255 - g) * amount));
  b = Math.min(255, Math.round(b + (255 - b) * amount));
  return `#${r.toString(16).padStart(2, '0')}${g.toString(16).padStart(2, '0')}${b.toString(16).padStart(2, '0')}`;
}
