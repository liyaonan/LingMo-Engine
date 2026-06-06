// encounter-card-factory.js
// 遭遇卡片通用工厂 — 封装卡片骨架、已使用状态管理、hover 动效、WS 消息发送
import { InteractionCardRegistry } from '/static/frontend-v2/plugins/interaction-registry.js';
import { AppState } from '/static/frontend-v2/state/app-state.js';
import { EventBus } from '/static/frontend-v2/event-bus.js';
import { i18n } from '/static/frontend-v2/shared/i18n.js';

// 会话状态追踪
const _sessionStates = new Map();

// 通用卡片骨架 CSS
const BASE_CSS = `
  .encounter-factory-card {
    padding: 12px 14px; background: var(--color-surface);
    border-radius: var(--radius-md);
  }
  .encounter-factory-card.used {
    opacity: 0.6;
  }
  .encounter-factory-header {
    font-family: var(--font-ui); font-size: var(--font-size-xs);
    letter-spacing: 1px; margin-bottom: var(--space-sm);
  }
  .encounter-factory-body {
    margin-bottom: var(--space-sm);
  }
  .encounter-factory-action {
    background: var(--color-surface-alt); border: 1px solid var(--color-border-light);
    border-radius: var(--radius-md); padding: 10px 14px; cursor: pointer;
    transition: border-color var(--transition-fast), background var(--transition-fast);
  }
  .encounter-factory-action:hover {
    background: rgba(201, 169, 97, 0.04);
  }
  .encounter-factory-action.disabled {
    cursor: default; pointer-events: none; opacity: 0.5;
  }
  .encounter-factory-action-hint {
    font-family: var(--font-ui); font-size: var(--font-size-xs);
    color: var(--color-text-muted); margin-top: var(--space-sm);
  }
`;

export class EncounterCardFactory {
  static register(config) {
    const {
      cardType, wsStart, css = '', title, titleUsed,
      borderColor, extractData, renderBody, extractParams,
      onClick, onFinish,
    } = config;

    InteractionCardRegistry.register(cardType, {
      css: BASE_CSS + css,

      createCard(msg, h) {
        const data = extractData(msg);
        if (!data) return null;

        const key = msg.id || '';
        const used = _sessionStates.get(key)?.used === true;

        const el = document.createElement('div');
        el.className = 'msg-block encounter-factory-card' + (used ? ' used' : '');
        if (borderColor) {
          el.style.border = `1px solid ${borderColor}`;
        } else {
          el.style.border = '1px solid var(--color-border-light)';
        }

        const header = document.createElement('div');
        header.className = 'encounter-factory-header';
        header.style.color = used ? 'var(--color-text-muted)' : (borderColor || 'var(--color-text-muted)');
        header.textContent = used ? titleUsed : title;
        el.appendChild(header);

        const body = document.createElement('div');
        body.className = 'encounter-factory-body';
        renderBody(data, body, h);
        el.appendChild(body);

        const action = document.createElement('div');
        action.className = 'encounter-factory-action' + (used ? ' disabled' : '');
        if (borderColor) {
          action.style.borderColor = borderColor;
        }
        const hint = document.createElement('div');
        hint.className = 'encounter-factory-action-hint';
        hint.textContent = used ? i18n.t('encounter_ended') : i18n.t('encounter_start');
        action.appendChild(hint);
        el.appendChild(action);

        if (!used) {
          action.addEventListener('click', () => {
            if (AppState.isBusy()) {
              EventBus.emit('toast:show', i18n.t('request_processing'));
              return;
            }
            if (onClick) {
              onClick(data, h);
            } else {
              h.sendMessage({ type: wsStart, ...extractParams(data, msg) });
            }
          });
        }

        const syncBusy = () => {
          const busy = AppState.isBusy();
          // 动态检测是否在最新页面：父容器中最后一个 page-view 即为最新页
          const pageView = el.closest('.page-view');
          let isLatest = true;
          if (pageView && pageView.parentElement) {
            const pages = pageView.parentElement.querySelectorAll(':scope > .page-view');
            isLatest = pages.length > 0 && pages[pages.length - 1] === pageView;
          }
          const disabled = used || busy || !isLatest;
          action.style.pointerEvents = disabled ? 'none' : '';
          action.style.opacity = disabled ? '0.5' : '';
        };
        syncBusy();
        EventBus.on('state:changed:ui', syncBusy);
        EventBus.on('narrative:page-changed', syncBusy);

        return el;
      },

      getCardData(msg) {
        const data = extractData(msg);
        return data ? { type: cardType, data } : null;
      },
    });
  }

  static registerReview(config) {
    const {
      cardType, css = '', parseRegex, getLabel, getModalTitle,
      themeColor, cardClassName = 'encounter-factory-action',
    } = config;

    InteractionCardRegistry.register(cardType, {
      css: BASE_CSS + css,

      createCard(msg, h) {
        if (!msg.content) return null;
        const m = msg.content.match(parseRegex);
        if (!m) return null;

        const label = getLabel(m);
        const modalTitle = getModalTitle(m);

        const wrapper = document.createElement('div');
        wrapper.style.cssText = 'display:flex;justify-content:flex-end';
        const card = document.createElement('div');
        card.className = cardClassName;
        card.style.textAlign = 'right';
        if (themeColor) {
          card.style.borderColor = themeColor;
        }
        card.innerHTML = `
          <div class="encounter-card-name">${label}</div>
          <div class="encounter-factory-action-hint">${i18n.t('encounter_view_detail')}</div>`;
        card.addEventListener('click', () => {
          const text = m[2] ? m[2].trim() : '';
          const overlay = document.createElement('div');
          overlay.className = 'combat-review-modal';
          overlay.innerHTML = `
            <div class="combat-review-modal-panel">
              <div class="combat-review-modal-header">
                <span>${modalTitle}</span>
                <button class="combat-review-modal-close">&times;</button>
              </div>
              <div class="combat-review-modal-body">${h.esc(text)}</div>
            </div>`;
          overlay.querySelector('.combat-review-modal-close')
            .addEventListener('click', () => overlay.remove());
          overlay.addEventListener('click', (e) => {
            if (e.target === overlay) overlay.remove();
          });
          h.shadowRoot.appendChild(overlay);
        });
        wrapper.appendChild(card);
        return wrapper;
      },

      getCardData(msg) {
        if (!msg.content) return null;
        const m = msg.content.match(parseRegex);
        return m ? { type: cardType, data: { result: m[1], text: m[2] } } : null;
      },
    });
  }

  static markUsed(msgId) {
    _sessionStates.set(msgId, { used: true });
  }

  static isUsed(msgId) {
    return _sessionStates.get(msgId)?.used === true;
  }
}
