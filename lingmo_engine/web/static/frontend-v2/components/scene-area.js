// components/scene-area.js
import { ComponentBase } from '../shared/component-base.js';
import { AppState } from '../state/app-state.js';
import { i18n } from '../shared/i18n.js';

const CSS = `
  :host {
    display: none;
    padding: 14px var(--space-xl) 10px;
    background: var(--color-bg);
    border-bottom: 1px solid rgba(201, 169, 97, 0.06);
    font-size: var(--font-size-xs);
    flex-shrink: 0;
  }
  :host(.visible) { display: block; }
  .breadcrumb {
    font-size: var(--font-size-xs);
    color: var(--color-text-muted);
    letter-spacing: 2px;
    margin-bottom: var(--space-xs);
  }
  .main-row {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    margin: 2px 0 4px;
  }
  .location-name {
    font-family: var(--font-narrative);
    font-size: var(--font-size-xl);
    font-weight: 600;
    color: var(--color-text);
  }
  .location-type {
    font-size: var(--font-size-xs);
    color: var(--color-text-dim);
    margin-left: var(--space-md);
  }
  .scene-time { text-align: right; }
  .time-display { font-size: var(--font-size-xs); color: var(--color-text-dim); }
  .time-phase { font-size: var(--font-size-xs); color: var(--color-text-muted); margin-left: 6px; }
  .description {
    font-size: var(--font-size-sm);
    color: var(--color-text-dim);
    line-height: 1.6;
    font-style: italic;
    border-left: 2px solid var(--color-border-strong);
    padding-left: 10px;
    margin-bottom: var(--space-sm);
    display: none;
  }
  .description.visible { display: block; }
  .links {
    display: flex;
    gap: var(--space-sm);
    font-size: var(--font-size-xs);
    flex-wrap: wrap;
    margin-top: var(--space-xs);
  }
  .scene-link {
    padding: 2px 8px;
    border: 1px solid var(--color-border-light);
    border-radius: var(--radius-sm);
    font-size: var(--font-size-xs);
    cursor: pointer;
    transition: all var(--transition-fast);
    background: none;
    font-family: var(--font-ui);
    color: var(--color-text-dim);
  }
  .scene-link:hover {
    border-color: var(--color-primary);
    color: var(--color-primary);
    background: rgba(201, 169, 97, 0.06);
  }
  .scene-link.parent { color: var(--color-text-dim); }
  .scene-link.children { color: var(--color-primary); }
  .scene-link.connections { color: var(--color-mana); }
  .scene-link-prefix {
    font-size: var(--font-size-2xs);
    color: var(--color-text-dim);
    margin-right: 2px;
  }
`;

export class SceneArea extends ComponentBase {
  static get observedState() { return ['world']; }

  _onStateChanged(key, data) { this._render(); }

  _render() {
    const world = AppState.getWorld();
    if (!world || !world.currentNode) {
      this._renderHTML(`<style>${CSS}</style>`);
      return;
    }

    const d = world;
    const breadcrumb = (d.breadcrumb && d.breadcrumb.length > 0)
      ? d.breadcrumb.map(b => this._esc(b.name)).join(' · ') : '';

    const locName = d.currentNode ? d.currentNode.name : (d.location || '-');
    const locType = d.currentNode ? (d.currentNode.type || '') : '';
    const timeDisplay = d.gameTime ? this._esc(d.gameTime.display || '') : '';
    const timePhase = d.gameTime ? this._esc(d.gameTime.time_of_day || '') : '';

    const desc = (d.currentNode && d.currentNode.description) ? this._esc(d.currentNode.description) : '';
    const descClass = desc ? 'visible' : '';

    const _formatType = (type) => {
      if (!type || type === 'default') return '';
      const colonIdx = type.indexOf(':');
      return colonIdx >= 0 ? type.substring(colonIdx + 1) : type;
    };

    let linksHtml = '';
    if (d.parent && d.parent.id) {
      const pType = _formatType(d.parent.type);
      linksHtml += `<span class="scene-link parent">${pType ? `<span class="scene-link-prefix">${this._esc(pType)}</span>` : ''}${this._esc(d.parent.name)}</span>`;
    }
    for (const child of (d.children || [])) {
      const cType = _formatType(child.type);
      linksHtml += `<span class="scene-link children">${cType ? `<span class="scene-link-prefix">${this._esc(cType)}</span>` : ''}${this._esc(child.name)}</span>`;
    }
    for (const conn of (d.connections || [])) {
      const cnType = _formatType(conn.type);
      linksHtml += `<span class="scene-link connections">${cnType ? `<span class="scene-link-prefix">${this._esc(cnType)}</span>` : ''}${this._esc(conn.name)}</span>`;
    }

    this._renderHTML(`
      <style>${CSS} :host { display: block; }</style>
      <div class="breadcrumb">${breadcrumb}</div>
      <div class="main-row">
        <div class="scene-location">
          <span class="location-name">${this._esc(locName)}</span>
          ${locType ? `<span class="location-type">${this._esc(locType)}</span>` : ''}
        </div>
        <div class="scene-time">
          <span class="time-display">${timeDisplay}</span>
          <span class="time-phase">${timePhase}</span>
        </div>
      </div>
      <div class="description ${descClass}">${desc}</div>
      ${linksHtml ? `<div class="links">${linksHtml}</div>` : ''}
    `);
    this.style.setProperty('padding', '14px var(--space-xl) 10px');
  }
}

customElements.define('scene-area', SceneArea);
