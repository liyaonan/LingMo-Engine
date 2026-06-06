import { ComponentBase } from '../shared/component-base.js';
import { AppState } from '../state/app-state.js';
import { MessageRouter } from '../services/message-router.js';
import { WebSocketService } from '../services/websocket.js';
import { EventBus } from '../event-bus.js';
import { i18n } from '../shared/i18n.js';

const CSS = `
  :host {
    display: flex; align-items: center;
    padding: 10px var(--space-xl);
    background: rgba(14, 14, 22, 0.95);
    border-top: 1px solid rgba(201, 169, 97, 0.06);
    gap: var(--space-sm); flex-shrink: 0;
  }
  .input-wrapper { display: flex; flex: 1; gap: var(--space-sm); max-width: 100%; margin: 0 auto; }
  input {
    flex: 1; padding: 8px 12px;
    background: var(--color-surface); border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-sm); color: var(--color-text);
    font-family: var(--font-ui); font-size: var(--font-size-md); outline: none;
    transition: border-color var(--transition-fast);
  }
  input:focus { border-color: var(--color-primary); }
  input::placeholder { color: var(--color-text-muted); }
  input:disabled {
    cursor: not-allowed;
    border-color: var(--color-border-strong);
    animation: pulse-border 1.5s ease-in-out infinite;
    background: var(--color-surface);
  }
  @keyframes pulse-border {
    0%, 100% { border-color: var(--color-border-strong); box-shadow: 0 0 0 0 rgba(201, 169, 97, 0.1); }
    50% { border-color: rgba(201, 169, 97, 0.35); box-shadow: 0 0 8px 1px rgba(201, 169, 97, 0.08); }
  }
  button {
    padding: 8px 20px;
    background: rgba(201, 169, 97, 0.12);
    border: 1px solid rgba(201, 169, 97, 0.25);
    color: var(--color-primary);
    border-radius: var(--radius-sm);
    cursor: pointer; font-size: var(--font-size-sm); font-family: var(--font-ui);
    white-space: nowrap; transition: all var(--transition-fast);
  }
  button:hover {
    background: rgba(201, 169, 97, 0.2);
    border-color: var(--color-primary);
  }
  button:disabled {
    cursor: not-allowed;
    opacity: 0.5;
    animation: btn-loading 1s ease-in-out infinite;
  }
  @keyframes btn-loading {
    0%, 100% { opacity: 0.5; }
    50% { opacity: 0.3; }
  }
`;

export class InputArea extends ComponentBase {
  static get observedState() { return ['ui']; }

  _onStateChanged(key, data) { this._render(); }

  _render() {
    const ui = AppState.getUI();
    const enabled = !ui.isBusy && !ui.combatActive;
    const placeholder = enabled ? i18n.t('input_placeholder') : i18n.t('input_busy');
    const wrapperClass = ui.isBusy ? 'input-wrapper loading' : 'input-wrapper';

    this._renderHTML(`
      <style>${CSS}</style>
      <div class="${wrapperClass}">
        <input type="text" id="player-input" placeholder="${placeholder}" ${enabled ? '' : 'disabled'}>
        <button id="send-btn" ${enabled ? '' : 'disabled'}>${enabled ? i18n.t('send') : '...'}</button>
      </div>
    `);
    this.style.setProperty('padding', '10px var(--space-xl)');

    const input = this.shadowRoot.getElementById('player-input');
    const btn = this.shadowRoot.getElementById('send-btn');
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); this._send(); }
    });
    btn.addEventListener('click', () => this._send());
  }

  _send() {
    const input = this.shadowRoot.getElementById('player-input');
    if (!input) return;
    const text = input.value.trim();
    if (!text) return;
    if (AppState.isBusy()) {
      EventBus.emit('toast:show', i18n.t('request_processing'));
      return;
    }

    if (text === '/debug' || text.startsWith('/debug ')) {
      AppState.setInputEnabled(false);
      EventBus.emit('action:debug-text', text);
      WebSocketService.send({ type: 'player_input', content: text });
      input.value = '';
      return;
    }

    AppState.setInputEnabled(false);
    MessageRouter.sendUserInput(text);
    input.value = '';
  }
}

customElements.define('input-area', InputArea);
