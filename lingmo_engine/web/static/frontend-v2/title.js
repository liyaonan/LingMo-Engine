// title.js — 标题屏幕逻辑
import { i18n } from './shared/i18n.js';
import './components/save-panel.js';
import './components/settings-modal.js';
import { AppState } from './state/app-state.js';
import { WebSocketService } from './services/websocket.js';
import { MessageRouter } from './services/message-router.js';
import { EventBus } from './event-bus.js';

// 替换带 data-i18n 属性的元素文本
document.querySelectorAll('[data-i18n]').forEach(el => {
  el.textContent = i18n.t(el.dataset.i18n);
});

const TitleScreen = {
  init() {
    document.getElementById('btn-new-game').addEventListener('click', () => {
      window.location.href = '/creation';
    });

    document.getElementById('btn-load-game').addEventListener('click', () => {
      AppState.toggleSavePanel(true);
    });

    document.getElementById('btn-settings').addEventListener('click', () => {
      AppState.toggleSettings(true);
      WebSocketService.send({ type: 'config_get' });
    });

    WebSocketService.onMessage = (msg) => {
      if (msg.type === 'game_started') {
        if (msg.data && msg.data.opening) {
          sessionStorage.setItem('opening_narrative', msg.data.opening);
        }
        window.location.href = '/game';
        return;
      }
      if (msg.type === 'game_loaded') {
        sessionStorage.setItem('game_loaded', '1');
        window.location.href = '/game';
        return;
      }
      if (msg.type === 'save_list') {
        EventBus.emit('action:save_list', msg);
      } else if (msg.type === 'save_result') {
        EventBus.emit('action:save_result', msg);
      } else if (msg.type === 'export_ready') {
        EventBus.emit('action:export_ready', msg);
      } else if (msg.type === 'delete_result') {
        EventBus.emit('action:delete_result', msg);
      } else if (msg.type === 'config_data') {
        EventBus.emit('action:config_data', msg);
      } else if (msg.type === 'config_saved') {
        EventBus.emit('action:config_saved', msg);
      } else if (msg.type === 'config_test_result') {
        EventBus.emit('action:config_test_result', msg);
      } else if (msg.type === 'config_models_result') {
        EventBus.emit('action:config_models_result', msg);
      }
      MessageRouter.handleMessage(msg);
    };

    WebSocketService.connect();
  },
};

document.addEventListener('DOMContentLoaded', () => TitleScreen.init());
