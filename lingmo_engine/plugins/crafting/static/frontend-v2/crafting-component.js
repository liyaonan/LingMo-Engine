/**
 * 灵力封存物品制作面板
 */
import { ComponentBase } from '/static/frontend-v2/shared/component-base.js';
import { AppState } from '/static/frontend-v2/state/app-state.js';
import { WebSocketService } from '/static/frontend-v2/services/websocket.js';
import { EventBus } from '/static/frontend-v2/event-bus.js';

const CSS = `
  :host {
    display: block;
    padding: var(--space-md, 12px);
    overflow-y: auto;
    height: 100%;
    font-family: inherit;
    color: var(--color-text, #d4c5a0);
  }

  .craft-title {
    font-size: 1.4em;
    color: var(--color-primary, #c9a961);
    text-align: center;
    margin-bottom: var(--space-md, 12px);
    letter-spacing: 0.1em;
  }

  .theme-selector {
    display: flex;
    gap: var(--space-sm, 6px);
    justify-content: center;
    margin-bottom: var(--space-lg, 16px);
  }

  .theme-btn {
    padding: var(--space-xs, 4px) var(--space-md, 12px);
    border: 1px solid var(--color-border, #3a3550);
    border-radius: 4px;
    background: var(--color-surface, #12121f);
    color: var(--color-text, #d4c5a0);
    cursor: pointer;
    transition: all 0.2s;
    font-size: 0.95em;
  }

  .theme-btn:hover { border-color: var(--color-primary, #c9a961); }
  .theme-btn.active {
    background: var(--color-primary, #c9a961);
    color: var(--color-bg, #08080f);
    border-color: var(--color-primary, #c9a961);
    font-weight: bold;
  }

  .section-label {
    font-size: 0.9em;
    color: var(--color-primary, #c9a961);
    margin-bottom: var(--space-xs, 4px);
    letter-spacing: 0.05em;
  }

  .material-slots {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: var(--space-sm, 6px);
    margin-bottom: var(--space-lg, 16px);
  }

  .mat-slot {
    aspect-ratio: 1;
    border: 1px dashed var(--color-border, #3a3550);
    border-radius: 6px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    font-size: 0.8em;
    cursor: pointer;
    transition: all 0.2s;
    position: relative;
    min-height: 70px;
  }

  .mat-slot:hover { border-color: var(--color-primary, #c9a961); }
  .mat-slot.filled {
    border-style: solid;
    background: var(--color-surface, #12121f);
  }

  .mat-slot .mat-name { font-weight: bold; font-size: 0.85em; margin-top: 4px; }
  .mat-slot .mat-rarity { color: var(--color-primary, #c9a961); font-size: 0.75em; }
  .mat-slot .mat-tags { font-size: 0.7em; color: var(--color-text-dim, #8a8070); }
  .mat-slot .remove-btn {
    position: absolute;
    top: 2px;
    right: 4px;
    cursor: pointer;
    color: #e55;
    font-size: 0.9em;
  }

  .power-section { margin-bottom: var(--space-lg, 16px); }

  .power-slider {
    width: 100%;
    margin: var(--space-sm, 6px) 0;
    accent-color: var(--color-primary, #c9a961);
  }

  .power-info {
    display: flex;
    justify-content: space-between;
    font-size: 0.85em;
    color: var(--color-text-dim, #8a8070);
    flex-wrap: wrap;
    gap: 4px;
  }

  .power-info .highlight {
    color: var(--color-primary, #c9a961);
    font-weight: bold;
  }

  .preview-section {
    padding: var(--space-sm, 6px);
    border: 1px solid var(--color-border, #3a3550);
    border-radius: 6px;
    margin-bottom: var(--space-lg, 16px);
    font-size: 0.85em;
    line-height: 1.6;
  }

  .craft-btn {
    width: 100%;
    padding: var(--space-md, 12px);
    border: none;
    border-radius: 6px;
    background: var(--color-primary, #c9a961);
    color: var(--color-bg, #08080f);
    font-size: 1.1em;
    font-weight: bold;
    cursor: pointer;
    transition: opacity 0.2s;
    letter-spacing: 0.1em;
  }

  .craft-btn:hover { opacity: 0.85; }
  .craft-btn:disabled { opacity: 0.4; cursor: not-allowed; }

  .result-card {
    border: 2px solid var(--color-primary, #c9a961);
    border-radius: 12px;
    padding: var(--space-lg, 16px);
    text-align: center;
    margin-bottom: var(--space-lg, 16px);
  }

  .result-card .item-name {
    font-size: 1.3em;
    color: var(--color-primary, #c9a961);
    margin-bottom: var(--space-sm, 6px);
  }

  .result-card .item-desc {
    font-size: 0.85em;
    color: var(--color-text-dim, #8a8070);
    font-style: italic;
    margin-bottom: var(--space-md, 12px);
  }

  .result-card .item-tags {
    display: flex;
    gap: 4px;
    justify-content: center;
    flex-wrap: wrap;
    margin-bottom: var(--space-md, 12px);
  }

  .result-card .tag {
    padding: 2px 8px;
    border-radius: 3px;
    background: var(--color-bg, #08080f);
    font-size: 0.75em;
    border: 1px solid var(--color-border, #3a3550);
  }

  .result-card .effects {
    text-align: left;
    font-size: 0.85em;
    margin-bottom: var(--space-md, 12px);
  }

  .result-card .close-btn {
    padding: var(--space-sm, 6px) var(--space-lg, 16px);
    border: 1px solid var(--color-primary, #c9a961);
    border-radius: 4px;
    background: transparent;
    color: var(--color-primary, #c9a961);
    cursor: pointer;
  }

  .loading-spinner {
    text-align: center;
    padding: var(--space-lg, 16px);
    color: var(--color-primary, #c9a961);
  }

  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.4; }
  }

  .loading-spinner span { animation: pulse 1.5s infinite; }

  .error-msg {
    color: var(--color-danger, #e55);
    text-align: center;
    padding: var(--space-md, 12px);
    font-size: 0.9em;
  }
`;

export class CraftingPanel extends ComponentBase {
  static observedState = ['inventory'];

  constructor() {
    super();
    this._selectedTheme = '';
    this._selectedMaterials = [];
    this._spiritualPower = 0;
    this._maxSpiritualPower = 0;
    this._playerSpiritualPower = 0;
    this._preview = null;
    this._isCrafting = false;
    this._result = null;
    this._themes = [];
    this._inventory = [];
    this._playerSkills = {};
    this._selectedSlot = '';
    this._equipSlots = [];
    this._initialRequested = false;
  }

  _onStateChanged(key, data) {
    if (key === 'inventory' && data) {
      this._inventory = data.inventory || [];
      if (this._themes.length > 0) {
        this._renderAll();
      }
    }
  }

  connectedCallback() {
    super.connectedCallback();
    // 监听 crafting 相关的 WebSocket 响应（通过 MessageRouter default 分支以 ws: 前缀发出）
    this._unsubs = [
      EventBus.on('ws:crafting_state', (msg) => this._onCraftingState(msg)),
      EventBus.on('ws:crafting_preview_result', (msg) => this._onPreviewResult(msg)),
      EventBus.on('ws:crafting_result', (msg) => this._onCraftResult(msg)),
    ];
    this._fetchThemes();
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    if (this._unsubs) {
      this._unsubs.forEach(fn => fn());
    }
  }

  _onCraftingState(data) {
    this._themes = data.themes || [];
    this._playerSkills = data.player_skills || {};
    this._equipSlots = data.equip_slots || [];
    if (data.spiritual_power !== undefined) {
      this._playerSpiritualPower = data.spiritual_power;
    }
    this._renderAll();
  }

  _onPreviewResult(data) {
    if (data.success) {
      this._preview = data;
      if (data.max_spiritual_power !== undefined) {
        this._maxSpiritualPower = data.max_spiritual_power;
        if (this._spiritualPower > this._maxSpiritualPower) {
          this._spiritualPower = this._maxSpiritualPower;
        }
        if (this._spiritualPower === 0 && this._maxSpiritualPower > 0) {
          this._spiritualPower = Math.min(this._maxSpiritualPower, this._playerSpiritualPower || 9999);
        }
      }
    }
    this._renderAll();
  }

  _onCraftResult(data) {
    this._isCrafting = false;
    if (data.success) {
      this._result = data.data;
    }
    this._renderAll();
  }

  _fetchThemes() {
    if (this._initialRequested) return;
    this._initialRequested = true;
    WebSocketService.send({ type: 'crafting_open' });
  }

  _renderAll() {
    let html = `<style>${CSS}</style>`;

    if (this._result) {
      html += this._renderResult();
    } else if (this._isCrafting) {
      html += `<div class="loading-spinner"><span>灵力封存中...</span></div>`;
    } else if (this._themes.length === 0) {
      html += `<div class="loading-spinner"><span>加载中...</span></div>`;
    } else {
      html += this._renderCraftingUI();
    }

    this._renderHTML(html);
    setTimeout(() => this._bindEvents(), 0);
  }

  _renderCraftingUI() {
    const maxSlots = 6;
    let html = `<div class="craft-title">灵力封存·炼器台</div>`;

    // 题材选择
    html += `<div class="section-label">选择题材</div>`;
    html += `<div class="theme-selector">`;
    for (const t of this._themes) {
      const active = t.name === this._selectedTheme ? ' active' : '';
      const skillVal = this._playerSkills[t.bonus_skill] || 0;
      html += `<button class="theme-btn${active}" data-action="select-theme" data-theme="${t.name}">${t.name}<br><small>${skillVal}</small></button>`;
    }
    html += `</div>`;

    // 法宝题材的部位选择栏
    if (this._selectedTheme === '法宝' && this._equipSlots.length > 0) {
      html += `<div class="section-label">选择部位</div>`;
      html += `<div class="theme-selector" style="flex-wrap:wrap;">`;
      for (const s of this._equipSlots) {
        const active = s.id === this._selectedSlot ? ' active' : '';
        html += `<button class="theme-btn${active}" data-action="select-slot" data-slot="${s.id}" style="font-size:0.85em;padding:3px 10px;">${s.name}</button>`;
      }
      html += `</div>`;
    }

    // 材料槽位
    html += `<div class="section-label">材料槽位 (${this._selectedMaterials.length}/${maxSlots})</div>`;
    html += `<div class="material-slots">`;
    for (let i = 0; i < maxSlots; i++) {
      const mat = this._selectedMaterials[i];
      if (mat) {
        html += `<div class="mat-slot filled" data-index="${i}">
          <span class="remove-btn" data-action="remove-material" data-index="${i}">&times;</span>
          <span class="mat-name">${this._esc(mat.name)}</span>
          <span class="mat-rarity">★${mat.rarity}</span>
          <span class="mat-tags">${(mat.tags || []).join(', ')}</span>
        </div>`;
      } else if (i === this._selectedMaterials.length) {
        html += `<div class="mat-slot" data-action="add-material">+ 选材</div>`;
      } else {
        html += `<div class="mat-slot">空</div>`;
      }
    }
    html += `</div>`;

    // 灵力封存
    html += `<div class="power-section">`;
    html += `<div class="section-label">灵力封存 (角色: ${this._playerSpiritualPower || 0}, 材料上限: ${this._maxSpiritualPower})</div>`;
    const maxSlider = Math.max(1, Math.min(this._maxSpiritualPower, this._playerSpiritualPower || 9999));
    const canSlide = this._selectedMaterials.length > 0 && this._maxSpiritualPower > 0;
    html += `<input type="range" class="power-slider" min="1" max="${maxSlider}" value="${Math.min(this._spiritualPower, maxSlider)}" data-action="set-power" ${canSlide ? '' : 'disabled'} />`;
    html += `<div class="power-info">`;
    html += `<span>封入: <span class="highlight">${canSlide ? Math.min(this._spiritualPower, maxSlider) : 0}</span></span>`;
    if (this._preview) {
      html += `<span>损耗: <span class="highlight">${this._preview.loss_rate_percent}</span></span>`;
      html += `<span>有效: <span class="highlight">${this._preview.effective_power}</span></span>`;
      html += `<span>等级: <span class="highlight">${this._preview.level.label}</span></span>`;
    }
    html += `</div></div>`;

    // 预览区
    if (this._preview) {
      const tags = this._preview.material_tags || [];
      html += `<div class="preview-section">`;
      html += `材料Tag: ${tags.length > 0 ? tags.join(', ') : '无'}<br>`;
      html += `加成技能: ${this._preview.skill_used || '无'} (${this._preview.skill_value || 0})<br>`;
      html += `${this._preview.is_bonus ? '✓ 专业道加成' : '非对应道，标准损耗'}`;
      html += `</div>`;
    }

    // 炼制按钮
    const needSlot = this._selectedTheme === '法宝';
    const slotReady = !needSlot || this._selectedSlot !== '';
    const canCraft = this._selectedTheme && this._selectedMaterials.length > 0 && this._spiritualPower > 0 && slotReady;
    html += `<button class="craft-btn" data-action="start-craft" ${canCraft ? '' : 'disabled'}>开始炼制</button>`;

    return html;
  }

  _renderResult() {
    const item = this._result.crafted_item;
    const summary = this._result.craft_summary;
    if (!item) return '<div class="error-msg">炼制失败</div>';

    let html = `<div class="result-card">`;
    html += `<div class="item-name">【${this._esc(item.name)}】</div>`;
    html += `<div style="font-size:0.85em;margin-bottom:8px;">品质: ★${item.rarity} (${item.rarity_name || ''}) · 灵力: ${summary.effective_power} · 等级: ${summary.level.label}</div>`;
    html += `<div class="item-desc">"${this._esc(item.description || '')}"</div>`;
    html += `<div class="item-tags">`;
    for (const tag of (item.tags || [])) {
      html += `<span class="tag">${this._esc(tag)}</span>`;
    }
    html += `</div>`;

    if (item.effects && item.effects.length > 0) {
      html += `<div class="effects">效果:<br>`;
      for (const eff of item.effects) {
        html += `· ${this._esc(eff.type)}: ${eff.value || ''} (${eff.target || ''})<br>`;
      }
      html += `</div>`;
    }

    html += `<button class="close-btn" data-action="close-result">放入背包</button>`;
    html += `</div>`;
    return html;
  }

  _bindEvents() {
    const root = this.shadowRoot;
    if (!root) return;

    root.querySelectorAll('[data-action]').forEach(el => {
      el.addEventListener('click', (e) => {
        const action = el.dataset.action;
        e.stopPropagation();

        switch (action) {
          case 'select-theme':
            this._selectedTheme = el.dataset.theme;
            this._selectedSlot = '';
            this._selectedMaterials = [];
            this._preview = null;
            this._renderAll();
            break;

          case 'select-slot':
            this._selectedSlot = el.dataset.slot;
            this._renderAll();
            break;

          case 'add-material':
            this._showMaterialPicker();
            break;

          case 'remove-material':
            const idx = parseInt(el.dataset.index, 10);
            this._selectedMaterials.splice(idx, 1);
            this._requestPreview();
            break;

          case 'start-craft':
            this._doCraft();
            break;

          case 'close-result':
            this._result = null;
            this._selectedMaterials = [];
            this._preview = null;
            this._selectedSlot = '';
            this._renderAll();
            break;
        }
      });
    });

    const slider = root.querySelector('.power-slider');
    if (slider) {
      slider.addEventListener('input', () => {
        this._spiritualPower = parseInt(slider.value, 10);
        this._requestPreview();
      });
    }
  }

  _showMaterialPicker() {
    const materials = (this._inventory || []).filter(item =>
      item.category === 'material' &&
      !this._selectedMaterials.some(m => m.id === item.id)
    );

    if (materials.length === 0) return;

    const mat = materials[0];
    this._selectedMaterials.push({
      id: mat.id,
      name: mat.name || mat.id,
      rarity: mat.rarity || 1,
      tags: mat.tags || [],
    });
    this._requestPreview();
  }

  _requestPreview() {
    if (!this._selectedTheme) {
      this._renderAll();
      return;
    }
    WebSocketService.send({
      type: 'crafting_preview',
      theme: this._selectedTheme,
      material_ids: this._selectedMaterials.map(m => m.id),
      spiritual_power: this._spiritualPower,
    });
  }

  _doCraft() {
    this._isCrafting = true;
    this._renderAll();
    WebSocketService.send({
      type: 'crafting_execute',
      theme: this._selectedTheme,
      material_ids: this._selectedMaterials.map(m => m.id),
      spiritual_power: this._spiritualPower,
      equip_slot: this._selectedTheme === '法宝' ? this._selectedSlot : '',
    });
  }
}

customElements.define('crafting-panel', CraftingPanel);
