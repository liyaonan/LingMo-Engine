// components/app-shell.js
// AppShell 根布局组件 — flex column 对应旧 #app / #game-ui 结构
import { ComponentBase } from '../shared/component-base.js';

const CSS = `
  :host {
    display: flex;
    flex-direction: column;
    height: 100vh;
    height: 100dvh;
    width: 100%;
    max-width: 100%;
    margin: 0 auto;
    overflow: hidden;
    background: var(--color-bg);
    color: var(--color-text);
    font-family: var(--font-ui);
    font-size: var(--font-size-lg);
    line-height: 1.6;
  }

  /* 叙述区填充剩余空间 */
  :host > narrative-area {
    flex: 1;
    overflow: hidden;
  }

  /* 覆盖层组件 */
  :host > plugin-host,
  :host > save-panel,
  :host > settings-modal { position: fixed; top: 0; left: 0; width: 100%; height: 100%; z-index: 100; }

  :host > combat-ui { position: fixed; top: 0; height: 100%; z-index: 200; }

  :host.combat-blur > :not(combat-ui) {
    filter: blur(3px) brightness(0.3);
    pointer-events: none;
    user-select: none;
    overflow: hidden;
  }

  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  /* 桌面端：居中 + 边框 */
  @media (min-width: 640px) {
    :host {
      max-width: 700px;
      margin: 0 auto;
      border-left: 1px solid var(--color-border-light);
      border-right: 1px solid var(--color-border-light);
    }
  }
`;

export class AppShell extends ComponentBase {
  static get observedState() { return []; }

  _onStateChanged(key, data) {
    this._renderHTML(`<style>${CSS}</style><slot></slot>`);
    this._applyLayout();
  }

  connectedCallback() {
    super.connectedCallback();
    this._resizeHandler = () => this._applyLayout();
    window.addEventListener('resize', this._resizeHandler);
  }

  disconnectedCallback() {
    window.removeEventListener('resize', this._resizeHandler);
    super.disconnectedCallback();
  }

  _applyLayout() {
    const desktop = window.innerWidth >= 640;
    this.style.setProperty('width', '100%');
    this.style.setProperty('max-width', desktop ? '700px' : '100%');
    this.style.setProperty('margin', '0 auto');
  }
}

customElements.define('app-shell', AppShell);
