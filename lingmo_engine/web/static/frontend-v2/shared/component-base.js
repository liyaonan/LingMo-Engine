// shared/component-base.js
import { EventBus } from '../event-bus.js';

export class ComponentBase extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this._listeners = [];
  }

  connectedCallback() {
    const keys = this.constructor.observedState || [];
    for (const k of keys) {
      const event = `state:changed:${k}`;
      const cb = (data) => this._onStateChanged(k, data);
      EventBus.on(event, cb);
      this._listeners.push({ event, cb });
    }
    // Also listen for bulk state changes (save/load)
    if (keys.length > 0) {
      const bulkCb = (data) => this._onBulkStateChanged(data);
      EventBus.on('state:changed:bulk', bulkCb);
      this._listeners.push({ event: 'state:changed:bulk', cb: bulkCb });
    }
    this._onStateChanged('*', null);
  }

  disconnectedCallback() {
    for (const { event, cb } of this._listeners) {
      EventBus.off(event, cb);
    }
    this._listeners = [];
  }

  /** Override in subclass — respond to a single state key change */
  _onStateChanged(key, data) {}

  /** Override in subclass — respond to bulk restore (save/load) */
  _onBulkStateChanged(data) {
    this._onStateChanged('*', null);
  }

  /** Helper: safely set innerHTML */
  _renderHTML(html) {
    this.shadowRoot.innerHTML = html;
  }

  /** Helper: HTML escape */
  _esc(text) {
    if (!text && text !== 0) return '';
    const div = document.createElement('div');
    div.textContent = String(text);
    return div.innerHTML;
  }
}
