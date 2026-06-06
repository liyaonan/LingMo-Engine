// components/toast-container.js
// 轻量 toast 通知容器 — 页面底部浮动提示，自动消失
import { EventBus } from '../event-bus.js';

const CSS = `
  :host {
    position: fixed;
    bottom: 80px;
    left: 50%;
    transform: translateX(-50%);
    z-index: 300;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 6px;
    pointer-events: none;
  }
  .toast {
    padding: 10px 22px;
    background: rgba(30, 28, 40, 0.95);
    border: 1px solid var(--color-primary);
    color: var(--color-primary);
    border-radius: var(--radius-md);
    font-family: var(--font-ui);
    font-size: var(--font-size-sm);
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.5);
    animation: toastIn 0.25s ease, toastOut 0.3s ease 2.2s forwards;
    pointer-events: auto;
  }
  @keyframes toastIn {
    from { opacity: 0; transform: translateY(12px); }
    to { opacity: 1; transform: translateY(0); }
  }
  @keyframes toastOut {
    from { opacity: 1; }
    to { opacity: 0; transform: translateY(-8px); }
  }
`;

export class ToastContainer extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this.shadowRoot.innerHTML = `<style>${CSS}</style>`;
  }

  connectedCallback() {
    EventBus.on('toast:show', (msg) => this._show(msg));
  }

  _show(message) {
    const el = document.createElement('div');
    el.className = 'toast';
    el.textContent = message;
    this.shadowRoot.appendChild(el);
    setTimeout(() => { if (el.parentNode) el.remove(); }, 2600);
  }
}

customElements.define('toast-container', ToastContainer);
