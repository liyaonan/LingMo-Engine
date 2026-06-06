// components/status-bar.js
import { ComponentBase } from '../shared/component-base.js';
import { AppState } from '../state/app-state.js';
import { i18n } from '../shared/i18n.js';

const CSS = `
  :host {
    display: flex;
    flex-direction: column;
    padding: var(--space-md) var(--space-xl);
    background: linear-gradient(180deg, rgba(20,20,30,0.95), rgba(14,14,22,0.95));
    border-bottom: 1px solid var(--color-border-light);
    gap: 4px;
    font-size: var(--font-size-xs);
    flex-shrink: 0;
  }
  .title-row {
    font-family: var(--font-narrative);
    font-size: var(--font-size-lg);
    color: var(--color-primary);
    font-weight: 600;
    text-shadow: 0 0 8px rgba(201, 169, 97, 0.3);
  }
  .cult-info {
    display: flex;
    gap: 12px;
    font-size: var(--font-size-xs);
    align-items: center;
    flex-wrap: wrap;
  }
  .cult-stat { display: flex; align-items: center; gap: 2px; white-space: nowrap; }
  .cult-label { color: var(--color-text-muted); }
  .cult-value { color: var(--color-primary); font-weight: 500; }
  .cult-stat.power .cult-value { color: var(--color-mana); }
  .stats {
    display: flex;
    gap: 14px;
    font-size: var(--font-size-xs);
    flex-wrap: wrap;
    align-items: center;
  }
  .stat { display: flex; align-items: center; gap: 2px; white-space: nowrap; }
  .stat-label { color: var(--color-text-muted); }
  .stat-value { color: var(--color-text); }
  .stat.hp, .stat.hp .stat-value { color: var(--color-danger); }
  .stat.mp, .stat.mp .stat-value { color: var(--color-mana); }
  .stat.level, .stat.level .stat-value { color: var(--color-primary); }
  .exp-bar-wrapper { width: 120px; flex-shrink: 0; margin-top: 2px; }
  .exp-bar {
    height: 3px;
    background: rgba(201, 169, 97, 0.1);
    border-radius: 2px;
    overflow: hidden;
  }
  .exp-fill {
    height: 100%;
    background: var(--color-primary);
    border-radius: 2px;
    transition: width var(--transition-normal);
  }
`;

export class StatusBar extends ComponentBase {
  static get observedState() { return ['player', 'world', 'cultivation']; }

  _onStateChanged(key, data) {
    this._render();
  }

  /** 数字缩写：≥1万显示"xx万"，≥1亿显示"xx亿" */
  _fmtNum(n) {
    const abs = Math.abs(n);
    if (abs < 10000) return '' + n;
    if (abs < 100000000) {
      const w = abs / 10000;
      return (n < 0 ? '-' : '') + (w % 1 === 0 ? w.toFixed(0) : w.toFixed(1)) + i18n.t('unit_wan');
    }
    const y = abs / 100000000;
    return (n < 0 ? '-' : '') + (y % 1 === 0 ? y.toFixed(0) : y.toFixed(1)) + i18n.t('unit_yi');
  }

  _render() {
    const schema = AppState.getAttributesSchema();
    const player = AppState.getPlayer();
    const world = AppState.getWorld();
    const cultivation = AppState.getCultivation();

    if (!schema || !schema.attributes) {
      this._renderFallback(player, world, cultivation);
      return;
    }

    const order = schema.status_bar_order || [];
    const attrs = schema.attributes;

    let statsHtml = '';
    for (const key of order) {
      const def = attrs[key];
      if (!def) continue;
      const value = player && player[key] !== undefined ? player[key] : def.default;
      const maxKey = (def && def.pair) ? def.pair : null;
      const maxVal = maxKey ? (
        player && player[maxKey] !== undefined ? player[maxKey]
        : (attrs[maxKey] ? attrs[maxKey].default : null)
      ) : null;

      let cls = 'stat';
      if (def.combat_type === 'pool') {
        if (key === 'hp' || key === 'health') cls = 'stat hp';
        else if (key === 'mp' || key === 'mana' || key === 'spirit') cls = 'stat mp';
      }

      if (maxVal !== null) {
        statsHtml += `<span class="${cls}"><span class="stat-label">${this._esc(def.label)}</span> <span class="stat-value">${this._fmtNum(value)}</span>/<span class="stat-value">${this._fmtNum(maxVal)}</span></span>`;
      } else {
        statsHtml += `<span class="${cls}"><span class="stat-label">${this._esc(def.label)}</span> <span class="stat-value">${this._fmtNum(value)}</span></span>`;
      }
    }
    statsHtml += `<span class="stat location"><span class="stat-value">${world && world.location ? this._esc(world.location) : '-'}</span></span>`;

    const expPct = (player && player.exp_to_level > 0) ? (player.exp / player.exp_to_level * 100) : 0;

    // 修炼信息：从 schema.status_bar_cultivation 配置动态渲染
    const cultHtml = this._renderCultivation(schema, cultivation);

    this._renderHTML(`
      <style>${CSS}</style>
      <div class="title-row">${world && world.worldTitle ? this._esc(world.worldTitle) : 'LingMo Engine'}</div>
      ${cultHtml}
      <div class="stats">${statsHtml}</div>
      <div class="exp-bar-wrapper">
        <div class="exp-bar"><div class="exp-fill" style="width:${expPct}%"></div></div>
      </div>
    `);
    this.style.setProperty('padding', 'var(--space-md) var(--space-xl)');
  }

  _renderFallback(player, world, cultivation) {
    const p = player || {};
    const cultHtml = this._renderCultivation(null, cultivation);

    this._renderHTML(`
      <style>${CSS}</style>
      <div class="title-row">${(world && world.worldTitle) || 'LingMo Engine'}</div>
      ${cultHtml}
      <div class="stats">
        <span class="stat hp"><span class="stat-label">${i18n.t('hp')}</span> <span class="stat-value">${this._fmtNum(p.hp || 100)}</span>/<span class="stat-value">${this._fmtNum(p.max_hp || 100)}</span></span>
        <span class="stat mp"><span class="stat-label">${i18n.t('mp')}</span> <span class="stat-value">${this._fmtNum(p.mp || 50)}</span>/<span class="stat-value">${this._fmtNum(p.max_mp || 50)}</span></span>
        <span class="stat location"><span class="stat-value">${world && world.location ? this._esc(world.location) : '-'}</span></span>
      </div>
    `);
    this.style.setProperty('padding', 'var(--space-md) var(--space-xl)');
  }

  /** 根据 schema.status_bar_cultivation 配置动态渲染修炼信息 */
  _renderCultivation(schema, cultivation) {
    const cultFields = (schema && schema.status_bar_cultivation) || [];
    if (!cultFields.length || !cultivation) return '';

    const parts = [];
    for (const field of cultFields) {
      const raw = cultivation[field.key];
      if (raw === undefined || raw === null || raw === '') continue;
      const value = field.fmt === 'number' ? this._fmtNum(raw) : this._esc(String(raw));
      const cls = field.style === 'power' ? 'cult-stat power' : 'cult-stat';
      parts.push(`<span class="${cls}"><span class="cult-label">${this._esc(field.label)}</span> <span class="cult-value">${value}</span></span>`);
    }
    return parts.length ? `<div class="cult-info">${parts.join('')}</div>` : '';
  }
}

customElements.define('status-bar', StatusBar);
