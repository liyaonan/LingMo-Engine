// plugins/combat/combat-content.js
// 战斗插件的内容类型注册 — 向 ContentRenderer 注册 combat_narrative、combat_log
// encounter 和 loot_card 已迁移到 InteractionCardRegistry（见 combat-interaction-cards.js）
import { ContentRenderer } from '/static/frontend-v2/plugins/content-renderer.js';

// ========== CSS（从 narrative-area 核心 CSS 中移出） ==========
const COMBAT_CSS = `
  .msg-block.combat-narrative {
    font-family: var(--font-narrative);
    font-size: var(--font-size-narrative); line-height: 2.0; color: var(--color-text);
    margin-bottom: 12px; padding-bottom: 12px;
    border-bottom: 1px solid var(--color-border);
  }
  .combat-narrative-label {
    font-family: var(--font-ui); font-size: var(--font-size-xs);
    color: var(--color-text-muted); letter-spacing: 1px;
    margin-bottom: var(--space-sm);
  }
  .msg-block.combat-log {
    font-family: var(--font-narrative);
    font-size: var(--font-size-base); line-height: 1.7; color: var(--color-text);
    margin-bottom: 12px; padding-bottom: 12px;
    border-bottom: 1px solid var(--color-border);
  }
  .combat-log .combat-line { padding: 1px 0; }
`;

// ========== 注册 combat_narrative ==========
ContentRenderer.register('combat_narrative', {
  css: COMBAT_CSS,

  createBlock(msg, h) {
    const el = document.createElement('div');
    el.className = 'msg-block combat-narrative';
    el.innerHTML = '<div class="combat-narrative-label">战斗记录</div>' +
                   h.formatNarrative(msg.content || '');
    return el;
  },

  getBlockData(msg) {
    return { type: 'combat_narrative', content: msg.content };
  },

  isDuplicate(last, msg) {
    return last.type === 'combat_narrative' && last.content === msg.content;
  },

  createStreamBlock(data, h) {
    const el = document.createElement('div');
    el.className = 'msg-block combat-narrative streaming';
    el.innerHTML = '<div class="combat-narrative-label">战斗记录</div>';
    return el;
  },

  flushStreamBlock(el, buffer, h) {
    el.innerHTML = '<div class="combat-narrative-label">战斗记录</div>' +
                   h.formatNarrative(buffer);
  },
});

// ========== 注册 combat_log ==========
ContentRenderer.register('combat', {
  css: COMBAT_CSS,

  createBlock(msg, h) {
    const el = document.createElement('div');
    el.className = 'msg-block combat-log';
    const lines = (msg.content || '').split('\n');
    let html = '';
    for (const line of lines) {
      if (!line.trim()) continue;
      html += `<div class="combat-log combat-line">${h.esc(line)}</div>`;
    }
    el.innerHTML = html
      .replace(/HP:\s*(\d+)/g, 'HP:<span style="color:var(--color-danger)">$1</span>')
      .replace(/(\d+)\s*伤害/g, '<span style="color:var(--color-danger)">$1</span> 伤害')
      .replace(/获得\s*(\d+)\s*经验/g, '获得 <span style="color:var(--color-primary)">$1</span> 经验');
    return el;
  },

  getBlockData(msg) {
    return { type: 'combat_log', content: msg.content };
  },
});

