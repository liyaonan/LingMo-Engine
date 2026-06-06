import { ComponentBase } from '../shared/component-base.js';
import { AppState } from '../state/app-state.js';
import { PluginRegistry } from '../plugins/plugin-registry.js';
import { WebSocketService } from '../services/websocket.js';

const CSS = `
  :host {
    display: flex; justify-content: center; gap: 1px;
    padding: var(--space-sm) var(--space-xl);
    background: rgba(14, 14, 22, 0.95);
    border-top: 1px solid var(--color-border-light);
    flex-shrink: 0;
  }
  button {
    position: relative;
    display: flex; align-items: center; gap: 4px;
    background: none; color: var(--color-text-dim);
    border: none;
    border-radius: var(--radius-sm);
    padding: 5px 16px; font-size: var(--font-size-xs); cursor: pointer; white-space: nowrap;
    font-family: var(--font-ui);
    transition: all var(--transition-fast);
  }
  button:hover,
  button.active {
    color: var(--color-primary);
    background: rgba(201, 169, 97, 0.06);
  }
  .plugin-icon {
    width: 16px; height: 16px; display: inline-flex; align-items: center;
  }
  .plugin-icon svg { width: 100%; height: 100%; }
`;

export class QuickBar extends ComponentBase {
  static get observedState() { return ['ui']; }

  _onStateChanged(key, data) { this._render(); }

  _render() {
    const ui = AppState.getUI();
    const activeName = ui.activePlugin;

    const allButtons = PluginRegistry.listAll().filter(p => !p.hidden);

    let html = `<style>${CSS}</style>`;

    allButtons.forEach(plugin => {
      // save/settings 使用独立的开关状态
      let isActive = activeName === plugin.name;
      if (plugin.name === 'save') isActive = ui.savePanelOpen;
      if (plugin.name === 'settings') isActive = ui.settingsOpen;
      const iconHtml = plugin.button && plugin.button.icon
        ? `<span class="plugin-icon">${plugin.button.icon}</span>`
        : '';
      html += `
        <button data-plugin="${plugin.name}"
                class="${isActive ? 'active' : ''}">
          ${iconHtml}${plugin.button ? plugin.button.label : plugin.name}
        </button>`;
    });

    this._renderHTML(html);

    this.shadowRoot.querySelectorAll('button[data-plugin]').forEach(btn => {
      btn.addEventListener('click', () => {
        const name = btn.dataset.plugin;
        // 角色按钮：先请求主角数据再打开面板
        if (name === 'character') {
          WebSocketService.send({ type: 'get_character', id: 0 });
          AppState.setActivePlugin('character');
          return;
        }
        // 存档/系统使用原生 toggle，不经过 plugin-host
        if (name === 'save') {
          AppState.toggleSavePanel();
          return;
        }
        if (name === 'settings') {
          AppState.toggleSettings();
          return;
        }
        const current = AppState.getUI().activePlugin;
        // Toggle: click again to close
        if (current === name) {
          AppState.setActivePlugin(null);
        } else {
          AppState.setActivePlugin(name);
        }
      });
    });
  }
}

customElements.define('quick-bar', QuickBar);
