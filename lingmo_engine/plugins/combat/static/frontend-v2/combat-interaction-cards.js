// combat-interaction-cards.js
// 战斗插件交互卡
import { InteractionCardRegistry } from '/static/frontend-v2/plugins/interaction-registry.js';
import { AppState } from '/static/frontend-v2/state/app-state.js';
import { EventBus } from '/static/frontend-v2/event-bus.js';

// ========== 共用卡片样式 ==========

const CARD_CSS = `
  .encounter-cards {
    padding: 12px 14px; background: var(--color-surface);
    border-radius: var(--radius-md); border: 1px solid var(--color-border-light);
  }
  .encounter-header {
    font-family: var(--font-ui); font-size: var(--font-size-xs);
    color: var(--color-text-muted); letter-spacing: 1px; margin-bottom: var(--space-sm);
  }
  .encounter-grid { display: flex; flex-wrap: wrap; gap: var(--space-sm); }
  .encounter-card {
    background: var(--color-surface-alt); border: 1px solid var(--color-border-light);
    border-radius: var(--radius-md); padding: 10px 14px; cursor: pointer;
    transition: border-color var(--transition-fast), background var(--transition-fast);
    width: 200px; flex-shrink: 0;
  }
  .encounter-card:hover { border-color: var(--color-primary); background: rgba(201,169,97,0.04); }
  .encounter-card-name { font-family: var(--font-ui); font-size: var(--font-size-base); font-weight: 600; color: var(--color-text); margin-bottom: var(--space-xs); }
  .encounter-card-enemies { font-family: var(--font-ui); font-size: var(--font-size-sm); color: var(--color-text-dim); }
  .encounter-card-hint { font-family: var(--font-ui); font-size: var(--font-size-xs); color: var(--color-text-muted); margin-top: var(--space-sm); }
  .encounter-card.result-胜利 { border-color: rgba(76, 175, 80, 0.4); }
  .encounter-card.result-胜利:hover { border-color: rgba(76, 175, 80, 0.7); background: rgba(76, 175, 80, 0.04); }
  .encounter-card.result-胜利 .encounter-card-name { color: #81c784; }
  .encounter-card.result-败北 { border-color: rgba(244, 67, 54, 0.4); }
  .encounter-card.result-败北:hover { border-color: rgba(244, 67, 54, 0.7); background: rgba(244, 67, 54, 0.04); }
  .encounter-card.result-败北 .encounter-card-name { color: #ef9a9a; }
  .encounter-card.result-逃跑 { border-color: rgba(158, 158, 158, 0.4); }
  .encounter-card.result-逃跑:hover { border-color: rgba(158, 158, 158, 0.7); background: rgba(158, 158, 158, 0.04); }
  .encounter-card.result-逃跑 .encounter-card-name { color: #bdbdbd; }
  .combat-review-modal {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.7);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 200;
    animation: fadeIn 0.2s ease;
  }
  .combat-review-modal-panel {
    background: var(--color-surface, #1a1a2e);
    border: 1px solid var(--color-border-strong, #333);
    border-radius: 8px;
    width: 90%;
    max-width: 500px;
    max-height: 70vh;
    display: flex;
    flex-direction: column;
    box-shadow: 0 8px 32px rgba(0,0,0,0.5);
  }
  .combat-review-modal-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px 16px;
    border-bottom: 1px solid var(--color-border-light, #222);
    font-family: var(--font-ui);
    font-size: var(--font-size-lg);
    font-weight: 600;
  }
  .combat-review-modal-close {
    background: none;
    border: none;
    color: var(--color-text-muted, #888);
    cursor: pointer;
    font-size: var(--font-size-xl);
    padding: 0 4px;
    line-height: 1;
  }
  .combat-review-modal-close:hover { color: var(--color-text, #eee); }
  .combat-review-modal-body {
    padding: 16px;
    overflow-y: auto;
    font-family: var(--font-narrative);
    font-size: var(--font-size-lg);
    line-height: 1.8;
    color: var(--color-text, #ddd);
    white-space: pre-wrap;
    word-break: break-word;
  }
`;

// ========== encounter 交互卡 ==========

function extractEncounterGroups(msg) {
  if (!msg.content_blocks) return [];
  let groups = [];
  for (const cb of msg.content_blocks) {
    if (cb.type === 'encounter_card' && cb.data && cb.data.groups) {
      groups = groups.concat(cb.data.groups);
    }
  }
  return groups;
}

InteractionCardRegistry.register('encounter', {
  css: CARD_CSS,

  createCard(msg, h) {
    const groups = extractEncounterGroups(msg);
    if (groups.length === 0) return null;
    const wrapper = document.createElement('div');
    let html = '<div class="msg-block encounter-cards">' +
      '<div class="encounter-header">遭遇敌人</div><div class="encounter-grid">';
    for (let i = 0; i < groups.length; i++) {
      const g = groups[i];
      const enemyNames = g.enemies.map(e => e.name + (e.count > 1 ? ' x' + e.count : '')).join('、');
      html += `<div class="encounter-card" data-group="${i}">
        <div class="encounter-card-name">${h.esc(g.name)}</div>
        <div class="encounter-card-enemies">${h.esc(enemyNames)}</div>
        <div class="encounter-card-hint">点击进入战斗</div>
      </div>`;
    }
    html += '</div></div>';
    wrapper.innerHTML = html;
    const el = wrapper.firstElementChild;
    if (el) {
      const cards = el.querySelectorAll('.encounter-card');
      for (const card of cards) {
        card.addEventListener('click', () => {
          if (AppState.isBusy()) {
            EventBus.emit('toast:show', '请求处理中，请等待完成后再试');
            return;
          }
          const groupIndex = card.getAttribute('data-group');
          if (groupIndex !== null) {
            h.sendMessage({ type: 'trigger_combat', group_id: parseInt(groupIndex, 10) });
          }
          const allCards = el.querySelectorAll('.encounter-card');
          for (const c of allCards) {
            c.style.pointerEvents = 'none';
            c.style.opacity = '0.5';
          }
          // 点击后立即触发一次状态同步（AppState.isBusy 会在 sendMessage 后变为 true）
          syncCardState();
        });
      }
      const syncCardState = () => {
        const busy = AppState.isBusy();
        // 动态检测是否在最新页面：父容器中最后一个 page-view 即为最新页
        const pageView = el.closest('.page-view');
        let isLatest = true;
        if (pageView && pageView.parentElement) {
          const pages = pageView.parentElement.querySelectorAll(':scope > .page-view');
          isLatest = pages.length > 0 && pages[pages.length - 1] === pageView;
        }
        const disabled = busy || !isLatest;
        el.querySelectorAll('.encounter-card').forEach(c => {
          c.style.pointerEvents = disabled ? 'none' : '';
          c.style.opacity = disabled ? '0.5' : '';
        });
      };
      syncCardState();
      EventBus.on('state:changed:ui', syncCardState);
      EventBus.on('narrative:page-changed', syncCardState);
    }
    return el;
  },

  getCardData(msg) {
    return { type: 'encounter_cards', data: extractEncounterGroups(msg) };
  },
});

// ========== combat_review（战斗回顾） ==========

const COMBAT_REVIEW_RE = /^（战斗回顾\|(.+?)）([\s\S]*)$/;
const COMBAT_REVIEW_LABELS = { '胜利': '战斗胜利', '败北': '战斗失败', '逃跑': '脱离战斗' };

export function parseCombatReview(content) {
  if (!content) return null;
  const m = content.match(COMBAT_REVIEW_RE);
  if (!m) return null;
  return { result: m[1], text: m[2].trim() };
}

InteractionCardRegistry.register('combat_review', {
  css: CARD_CSS,

  createCard(msg, h) {
    const review = parseCombatReview(msg.content);
    if (!review) return null;
    const label = COMBAT_REVIEW_LABELS[review.result] || '战斗回顾';

    const wrapper = document.createElement('div');
    wrapper.style.cssText = 'display:flex;justify-content:flex-end';
    const card = document.createElement('div');
    card.className = `encounter-card result-${review.result}`;
    card.style.textAlign = 'right';
    card.innerHTML = `
      <div class="encounter-card-name">${label}</div>
      <div class="encounter-card-hint">点击查看详情</div>`;
    card.addEventListener('click', () => {
      const overlay = document.createElement('div');
      overlay.className = 'combat-review-modal';
      overlay.innerHTML = `
        <div class="combat-review-modal-panel">
          <div class="combat-review-modal-header">
            <span>${label}</span>
            <button class="combat-review-modal-close">&times;</button>
          </div>
          <div class="combat-review-modal-body">${h.esc(review.text)}</div>
        </div>`;
      overlay.querySelector('.combat-review-modal-close').addEventListener('click', () => overlay.remove());
      overlay.addEventListener('click', (e) => { if (e.target === overlay) overlay.remove(); });
      h.shadowRoot.appendChild(overlay);
    });
    wrapper.appendChild(card);
    return wrapper;
  },

  getCardData(msg) {
    const review = parseCombatReview(msg.content);
    return review ? { type: 'combat_review', data: review } : null;
  },
});
