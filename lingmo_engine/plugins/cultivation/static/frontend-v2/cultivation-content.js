// cultivation-content.js
// 修炼插件的内容渲染注册 — cultivation_narrative 注册到 ContentRenderer
import { ContentRenderer } from '/static/frontend-v2/plugins/content-renderer.js';

const CULTIVATION_CSS = `
  .cultivation-narrative {
    padding: 12px 14px;
    background: rgba(201, 169, 97, 0.04);
    border-left: 3px solid rgba(201, 169, 97, 0.3);
    border-radius: 0 var(--radius-md) var(--radius-md) 0;
    margin: var(--space-sm) 0;
  }
  .cultivation-narrative-label {
    font-family: var(--font-ui);
    font-size: var(--font-size-xs);
    color: var(--color-primary, #c9a961);
    letter-spacing: 1px;
    margin-bottom: var(--space-xs);
  }
  .cultivation-narrative.streaming {
    opacity: 0.7;
  }
`;

ContentRenderer.register('cultivation_narrative', {
  css: CULTIVATION_CSS,

  createBlock(msg, h) {
    const el = document.createElement('div');
    el.className = 'msg-block cultivation-narrative';
    el.innerHTML = '<div class="cultivation-narrative-label">修炼感悟</div>' +
                   h.formatNarrative(msg.content || '');
    return el;
  },

  getBlockData(msg) {
    return { type: 'cultivation_narrative', content: msg.content };
  },

  isDuplicate(last, msg) {
    return last.type === 'cultivation_narrative' && last.content === msg.content;
  },

  createStreamBlock(data, h) {
    const el = document.createElement('div');
    el.className = 'msg-block cultivation-narrative streaming';
    el.innerHTML = '<div class="cultivation-narrative-label">修炼感悟</div>';
    return el;
  },

  flushStreamBlock(el, buffer, h) {
    el.innerHTML = '<div class="cultivation-narrative-label">修炼感悟</div>' +
                   h.formatNarrative(buffer);
    el.classList.remove('streaming');
  },
});
