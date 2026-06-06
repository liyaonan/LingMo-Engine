// creation.js — 角色创建页面逻辑
import { i18n } from './shared/i18n.js';
import { WebSocketService } from './services/websocket.js';
import { EventBus } from './event-bus.js';

// 替换 data-i18n 元素
document.querySelectorAll('[data-i18n]').forEach(el => {
  el.textContent = i18n.t(el.dataset.i18n);
});
// 替换标题
const titleEl = document.querySelector('[data-i18n-title]');
if (titleEl) document.title = i18n.t(titleEl.dataset.i18nTitle) + ' — LingMo Engine';

const CreationScreen = {
  init() {
    WebSocketService.onMessage = (msg) => this.handleMessage(msg);
    WebSocketService.connect();
  },

  handleMessage(msg) {
    switch (msg.type) {
      case 'game_started':
        if (msg.data && msg.data.opening) {
          sessionStorage.setItem('opening_narrative', msg.data.opening);
        }
        window.location.href = '/game';
        break;

      case 'state_update':
        break;

      case 'character_creation':
        if (msg.html) {
          document.getElementById('creation-content').innerHTML = msg.html;
          this._bindFormEvents();
        }
        break;

      case 'error':
        if (msg.content) {
          document.getElementById('creation-content').innerHTML =
            '<p style="color: var(--color-danger); text-align:center;">' +
            this._escapeHtml(msg.content) + '</p>';
        }
        break;

      default:
        break;
    }
  },

  _bindFormEvents() {
    const container = document.getElementById('creation-content');
    container.querySelectorAll('button[data-action]').forEach(btn => {
      btn.addEventListener('click', () => {
        const action = btn.dataset.action;
        const payload = btn.dataset.payload ? JSON.parse(btn.dataset.payload) : {};
        WebSocketService.send({ type: 'creation_action', action, ...payload });
      });
    });
  },

  _escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  },
};

document.addEventListener('DOMContentLoaded', () => CreationScreen.init());
