import { ComponentBase } from '../shared/component-base.js';
import { AppState } from '../state/app-state.js';
import { PluginRegistry } from '../plugins/plugin-registry.js';
import { i18n } from '../shared/i18n.js';

const CSS = `
  :host { display: none; }

  .overlay-backdrop {
    position: fixed; inset: 0;
    background: var(--color-bg);
    z-index: 200;
  }

  .panel-backdrop {
    position: fixed; inset: 0;
    background: rgba(0,0,0,0.45);
    z-index: 50;
  }

  .panel-container {
    position: fixed;
    top: 0; bottom: 0;
    left: 50%;
    transform: translateX(-50%);
    width: 100%; max-width: 700px;
    background: var(--color-bg);
    z-index: 50;
    display: flex; flex-direction: column;
    overflow: hidden;
  }

  .panel-header {
    display: flex; justify-content: space-between; align-items: center;
    padding: 10px var(--space-xl);
    border-bottom: 1px solid var(--color-border-light);
    background: rgba(14, 14, 22, 0.95);
    flex-shrink: 0;
  }

  .panel-title {
    font-family: var(--font-narrative);
    font-size: var(--font-size-narrative);
    color: var(--color-primary);
    font-weight: 600;
  }

  .panel-close {
    background: none;
    border: 1px solid var(--color-border-light);
    color: var(--color-text-dim);
    cursor: pointer;
    font-size: var(--font-size-base);
    padding: 2px 10px;
    border-radius: var(--radius-sm);
    font-family: var(--font-ui);
    transition: all var(--transition-fast);
  }

  .panel-close:hover {
    color: var(--color-danger);
    border-color: var(--color-danger);
  }

  .panel-content {
    flex: 1; overflow-y: auto;
    padding: var(--space-xl);
  }
  .panel-content::-webkit-scrollbar { width: 4px; }
  .panel-content::-webkit-scrollbar-track { background: transparent; }
  .panel-content::-webkit-scrollbar-thumb { background: var(--color-border); border-radius: 2px; }
`;

export class PluginHost extends ComponentBase {
  static get observedState() { return ['ui']; }

  constructor() {
    super();
    this._currentPlugin = null;
    this._currentEl = null;
  }

  async _onStateChanged(key, data) {
    const ui = AppState.getUI();
    const active = ui.activePlugin;
    if (active === this._currentPlugin) return;

    // Clean up previous UI
    this._cleanup();

    if (!active || !PluginRegistry.has(active)) {
      this.style.display = 'none';
      this._currentPlugin = active;
      return;
    }

    const plugin = PluginRegistry.get(active);
    if (!plugin || !plugin.ui) {
      this.style.display = 'none';
      this._currentPlugin = active;
      return;
    }

    this._currentPlugin = active;

    switch (plugin.ui.mode) {
      case 'overlay':
        await this._mountOverlay(plugin);
        break;
      case 'panel':
        await this._mountPanel(plugin);
        break;
      case 'custom':
      default:
        // custom mode: plugin manages its own DOM
        this.style.display = 'block';
        await this._ensurePluginElement(plugin);
        this.shadowRoot.appendChild(this._currentEl);
        break;
    }
  }

  _cleanup() {
    // 清除 shadow DOM 内容，从之前的挂载中清理
    this.shadowRoot.innerHTML = '';
    this._currentEl = null;
    this.style.display = 'none';
  }

  async _ensurePluginElement(plugin) {
    // Dynamic import component if specified (backward compat with old register() API)
    if (plugin.component) {
      await plugin.component();
    }
    this._currentEl = document.createElement(plugin.ui.tagName);
  }

  async _mountOverlay(plugin) {
    this.style.display = 'block';
    this._renderHTML(`<style>${CSS}</style><slot></slot>`);

    const wrapper = document.createElement('div');
    wrapper.className = 'overlay-backdrop';
    this.shadowRoot.appendChild(wrapper);

    await this._ensurePluginElement(plugin);
    wrapper.appendChild(this._currentEl);
  }

  async _mountPanel(plugin) {
    this.style.display = 'block';
    this._renderHTML(`<style>${CSS}</style><slot></slot>`);

    // Backdrop (click to close)
    const backdrop = document.createElement('div');
    backdrop.className = 'panel-backdrop';
    backdrop.addEventListener('click', () => {
      AppState.setActivePlugin(null);
    });
    this.shadowRoot.appendChild(backdrop);

    // Panel container
    const container = document.createElement('div');
    container.className = 'panel-container';
    container.addEventListener('click', (e) => e.stopPropagation());

    // Header
    const header = document.createElement('div');
    header.className = 'panel-header';
    const iconHtml = plugin.button && plugin.button.icon ? plugin.button.icon : '';
    header.innerHTML = `
      <span class="panel-title">${iconHtml} ${plugin.button ? plugin.button.label : plugin.name}</span>
      <button class="panel-close">${i18n.t('panel_close')}</button>
    `;
    header.querySelector('.panel-close').addEventListener('click', () => {
      AppState.setActivePlugin(null);
    });
    container.appendChild(header);

    // Content area
    const content = document.createElement('div');
    content.className = 'panel-content';

    await this._ensurePluginElement(plugin);
    content.appendChild(this._currentEl);
    container.appendChild(content);

    this.shadowRoot.appendChild(container);
  }
}

customElements.define('plugin-host', PluginHost);
