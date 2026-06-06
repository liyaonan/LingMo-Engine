// plugins/combat/abilities-component.js — 技能面板独立组件
import { ComponentBase } from '/static/frontend-v2/shared/component-base.js';
import { AppState } from '/static/frontend-v2/state/app-state.js';
import { WebSocketService } from '/static/frontend-v2/services/websocket.js';
import { CombatAllies } from '/static/plugins/combat/frontend-v2/combat-allies.js';

const CSS = `
  :host { display: block; height: 100%; overflow-y: auto; scrollbar-width: none; }
  :host::-webkit-scrollbar { display: none; }

  .ab-header-row {
    display: flex; justify-content: space-between; align-items: center;
    padding: 12px 14px; border-bottom: 1px solid var(--color-border-light);
  }
  .ab-header-left { display: flex; align-items: center; gap: 10px; }
  .ab-header-icon {
    width: 36px; height: 36px; border-radius: var(--radius-md);
    background: var(--color-surface-alt); border: 1px solid var(--color-border-strong);
    display: flex; align-items: center; justify-content: center;
    color: var(--color-primary); font-size: calc(14px * var(--font-scale)); flex-shrink: 0;
  }
  .ab-header-row .ab-title { font-family: var(--font-narrative); font-size: var(--font-size-narrative); color: var(--color-primary); font-weight: 600; }
  .ab-header-row .ab-count { font-size: var(--font-size-xs); color: var(--color-text-dim); }
  .ab-header-tags { display: flex; gap: var(--space-xs); flex-wrap: wrap; }

  .ab-cat-bar { display: flex; gap: 10px; margin: 0 14px var(--space-md); padding-bottom: var(--space-sm); border-bottom: 1px solid var(--color-border); }
  .ab-cat-tab { font-size: var(--font-size-xs); color: var(--color-text-dim); cursor: pointer; padding: 2px 0; border-bottom: 1px solid transparent; transition: all 0.2s; }
  .ab-cat-tab:hover { color: var(--color-text); }
  .ab-cat-tab.active { color: var(--color-primary); border-bottom-color: var(--color-primary); }

  .ab-item-list { margin: 0 14px; }
  .ab-item-row {
    display: flex; align-items: center; padding: 7px 10px;
    border-bottom: 1px solid var(--color-border); cursor: pointer;
    transition: background 0.15s; border-radius: var(--radius-sm); font-size: var(--font-size-xs);
  }
  .ab-item-row:hover { background: var(--color-primary-bg); }
  .ab-item-row.selected { background: rgba(201,169,97,0.06); border-radius: var(--radius-sm) var(--radius-sm) 0 0; }
  .ab-item-row .ab-item-name { width: 100px; font-size: var(--font-size-sm); font-weight: 600; flex-shrink: 0; }
  .ab-item-row .ab-item-cat { width: 50px; font-size: var(--font-size-2xs); color: var(--color-text-dim); flex-shrink: 0; }
  .ab-item-row .ab-item-desc { flex: 1; font-size: var(--font-size-2xs); color: var(--color-text-muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .ab-item-row .ab-item-slot-tag { margin-left: var(--space-xs); font-size: var(--font-size-2xs); color: var(--color-primary); background: var(--color-primary-bg); padding: 1px 4px; border-radius: var(--radius-sm); flex-shrink: 0; }

  .ab-expand {
    background: var(--color-surface-alt); border: 1px solid var(--color-border-light);
    border-top: none; border-radius: 0 0 var(--radius-md) var(--radius-md);
    padding: var(--space-sm) var(--space-lg); margin-bottom: 2px;
  }
  .ab-expand .ab-expand-meta { font-size: var(--font-size-2xs); color: var(--color-text-dim); margin-bottom: 3px; }
  .ab-expand .ab-expand-costs { font-size: var(--font-size-xs); color: var(--color-mana); margin-bottom: 3px; }
  .ab-expand .ab-expand-effects { font-size: var(--font-size-xs); color: var(--color-secondary); margin-bottom: 3px; }
  .ab-expand .ab-expand-desc { font-size: var(--font-size-xs); color: var(--color-text); line-height: 1.5; margin-bottom: var(--space-xs); }
  .ab-expand .ab-expand-btns { display: flex; gap: var(--space-sm); justify-content: flex-end; margin-top: var(--space-xs); }
  .ab-expand .ab-expand-btns button { padding: 5px 14px; border-radius: 4px; font-size: var(--font-size-xs); font-family: var(--font-ui); cursor: pointer; transition: all 0.2s; }
  .ab-expand .ab-expand-btns .ab-btn-action { background: rgba(201,169,97,0.1); border: 1px solid rgba(201,169,97,0.15); color: var(--color-primary); }
  .ab-expand .ab-expand-btns .ab-btn-action:hover { background: rgba(201,169,97,0.2); }
  .ab-expand .ab-expand-btns .ab-btn-forget { background: transparent; border: 1px solid var(--color-border-light); color: var(--color-text-dim); }
  .ab-expand .ab-expand-btns .ab-btn-forget:hover { color: var(--color-danger); border-color: var(--color-danger); }

  .ab-empty { color: var(--color-text-muted); font-size: var(--font-size-xs); text-align: center; padding: 20px; }
`;

export class AbilitiesPanel extends ComponentBase {
  static get observedState() { return ['abilities']; }

  constructor() {
    super();
    this._abSelectedCategory = null;
    this._abSelectedAbility = null;
  }

  connectedCallback() {
    super.connectedCallback();
    // 首次加载时请求技能数据
    const abData = AppState.getAbilities();
    if (!abData || !(abData.abilities && abData.abilities.length)) {
      WebSocketService.send({ type: 'abilities_open' });
    }
  }

  _onStateChanged(key, data) {
    this._render();
  }

  // ==================== 主渲染 ====================

  _render() {
    const data = AppState.getAbilities();
    if (!data) {
      this._renderHTML(`<style>${CSS}</style><div class="ab-empty">加载中...</div>`);
      return;
    }

    if (this._abSelectedCategory === undefined) {
      this._abSelectedCategory = null;
    }

    const totalAbilities = (data.abilities || []).length;
    const maxAbilities = data.max_abilities || 20;

    let html = '';

    // Header
    html += '<div class="ab-header-row">';
    html += '<div class="ab-header-left">';
    html += '<div class="ab-header-icon">技</div>';
    html += '<div>';
    html += '<span class="ab-title">技能</span>';
    html += '</div>';
    html += '</div>';
    html += '</div>';

    html += this._renderCategoryBar(data);
    html += this._renderAbilityList(data);

    this._renderHTML(`<style>${CSS}</style>${html}`);
    setTimeout(() => this._bindEvents(), 0);
  }

  // ==================== 分类标签栏 ====================

  _renderCategoryBar(data) {
    let h = '<div class="ab-cat-bar">';
    const allActive = !this._abSelectedCategory;
    h += `<span class="ab-cat-tab${allActive ? ' active' : ''}" data-cat="">全部</span>`;
    const shuActive = this._abSelectedCategory === 'shufa';
    h += `<span class="ab-cat-tab${shuActive ? ' active' : ''}" data-cat="shufa">术法</span>`;
    const shenActive = this._abSelectedCategory === 'divine';
    h += `<span class="ab-cat-tab${shenActive ? ' active' : ''}" data-cat="divine">神通</span>`;
    h += '</div>';
    return h;
  }

  // ==================== 技能列表（含行内展开详情） ====================

  _renderAbilityList(data) {
    const abilities = data.abilities || [];

    // 按分类过滤：术法=非divine，神通=仅divine
    let items = abilities;
    if (this._abSelectedCategory === 'divine') {
      items = abilities.filter(a => a.category === 'divine');
    } else if (this._abSelectedCategory === 'shufa') {
      items = abilities.filter(a => a.category !== 'divine');
    }

    if (items.length === 0) {
      return '<div class="ab-empty">暂无技能</div>';
    }

    let h = '<div class="ab-item-list">';
    for (const ability of items) {
      const isSelected = this._abSelectedAbility && this._abSelectedAbility.id === ability.id;
      const rarity = ability.rarity_info || this._getRarity(data, ability.rarity);
      const cls = 'ab-item-row' + (isSelected ? ' selected' : '');

      h += `<div class="${cls}" data-ability="${this._esc(ability.id)}">`;
      h += `<span class="ab-item-name" style="color:${rarity.color}">${this._esc(ability.name)}</span>`;
      h += `<span class="ab-item-cat">${this._esc(this._getCategoryName(data, ability.category))}</span>`;
      h += `<span class="ab-item-desc">${this._esc(ability.description || '')}</span>`;
      h += '</div>';

      // 行内展开详情
      if (isSelected) {
        h += this._renderExpandDetail(ability, data);
      }
    }
    h += '</div>';
    return h;
  }

  _renderExpandDetail(ability, data) {
    const rarity = ability.rarity_info || this._getRarity(data, ability.rarity);

    let h = '<div class="ab-expand">';

    // 分类 · 稀有度 · 冷却
    let metaParts = [this._getCategoryName(data, ability.category), rarity.name];
    if (ability.cooldown !== undefined && ability.cooldown !== null) {
      metaParts.push('冷却: ' + (ability.cooldown > 0 ? ability.cooldown + '回合' : '无'));
    }
    h += `<div class="ab-expand-meta">${this._esc(metaParts.join(' · '))}</div>`;

    // 消耗
    if (ability.costs && ability.costs.length) {
      h += `<div class="ab-expand-costs">消耗: ${this._formatCostsFull(ability.costs)}</div>`;
    }

    // 效果
    if (ability.effects && ability.effects.length) {
      const fxText = ability.effects.map(e => this._formatEffectText(e)).join('；');
      h += `<div class="ab-expand-effects">${fxText}</div>`;
    }

    // 描述
    if (ability.description) {
      h += `<div class="ab-expand-desc">${this._esc(ability.description)}</div>`;
    }

    // 操作按钮：仅遗忘（装备技能不可遗忘）
    h += '<div class="ab-expand-btns">';
    if (ability.id !== 'basic_attack' && ability.source !== 'equipment') {
      h += `<button class="ab-btn-forget" data-action="forget" data-ability="${this._esc(ability.id)}">遗忘</button>`;
    }
    h += '</div>';

    h += '</div>';
    return h;
  }

  // ==================== 事件绑定 ====================

  _bindEvents() {
    const root = this.shadowRoot;
    if (!root) return;

    // 分类标签
    root.querySelectorAll('.ab-cat-tab').forEach(el => {
      el.addEventListener('click', () => {
        const cat = el.dataset.cat || null;
        this._abSelectedCategory = cat;
        this._abSelectedAbility = null;
        this._render();
      });
    });

    // 技能行点击（再次点击折叠）
    root.querySelectorAll('.ab-item-row').forEach(el => {
      el.addEventListener('click', (e) => {
        if (e.target.dataset.action) return;
        const abilityId = el.dataset.ability;
        if (this._abSelectedAbility && this._abSelectedAbility.id === abilityId) {
          this._abSelectedAbility = null;
        } else {
          const data = AppState.getAbilities();
          const abilities = (data && data.abilities) || [];
          const ability = abilities.find(a => a.id === abilityId);
          if (ability) {
            this._abSelectedAbility = ability;
          }
        }
        this._render();
      });
    });

    // 操作按钮：仅遗忘
    root.querySelectorAll('[data-action="forget"]').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        if (confirm('确定遗忘该技能？此操作不可撤销。')) {
          WebSocketService.send({
            type: 'ability_action',
            action: 'forget',
            ability_id: btn.dataset.ability,
          });
          this._abSelectedAbility = null;
          this._render();
        }
      });
    });
  }

  // ==================== 格式化辅助 ====================

  /** 获取技能分类名称 */
  _getCategoryName(data, catId) {
    const cats = data.categories || [];
    for (const c of cats) { if (c.id === catId) return c.name; }
    return catId;
  }

  /** 根据稀有度数值获取稀有度信息 */
  _getRarity(data, rarityVal) {
    const rarities = data.rarities || [];
    for (const r of rarities) {
      if (rarityVal >= r.min && rarityVal <= r.max) return r;
    }
    return { name: '普通', color: '#a0a0a0' };
  }

  /** 获取资源名称（通过属性schema查找） */
  _getResourceLabel(resourceId) {
    const playerSlice = AppState.getSlice('player');
    const schema = (playerSlice && playerSlice.attributesSchema
      && playerSlice.attributesSchema.attributes) || {};
    const def = schema[resourceId];
    return (def && def.label) || resourceId;
  }

  /** 格式化消耗（简短形式，用于槽位展示） */
  _formatCostsShort(costs) {
    const parts = [];
    for (const c of costs) {
      parts.push(CombatAllies.fmtNum(c.amount) + ' ' + this._getResourceLabel(c.resource));
    }
    return parts.join(' ');
  }

  /** 格式化消耗（完整形式，用于详情卡片） */
  _formatCostsFull(costs) {
    const parts = [];
    for (const c of costs) {
      parts.push(this._getResourceLabel(c.resource) + ' ' + CombatAllies.fmtNum(c.amount));
    }
    return parts.join('，');
  }

  /** 格式化技能效果文本 */
  _formatEffectText(e) {
    const elemMap = {
      fire: '火', ice: '冰', thunder: '雷', wind: '风',
      earth: '土', light: '光', dark: '暗',
      neural: '神经', plasma: '等离子', thermal: '热能',
    };
    const statusMap = { frozen: '冻结', stunned: '眩晕', poisoned: '中毒', burned: '灼烧' };
    let text = '';

    if (e.type === 'damage') {
      text = '造成 ';
      if (e.power && e.power !== 1.0) text += (e.power * 100).toFixed(0) + '% ';
      if (e.element) text += (elemMap[e.element] || e.element) + ' ';
      text += '伤害';
    } else if (e.type === 'fixed_damage') {
      const fdVal = e.display_value || e.value;
      if (fdVal) text = '造成 ' + CombatAllies.fmtNum(fdVal) + ' 点真实伤害';
      else text = '造成真实伤害';
    } else if (e.type === 'heal') {
      text = '恢复 ';
      if (e.value) text += e.value + ' 点';
      else if (e.power && e.power !== 1.0) text += (e.power * 100).toFixed(0) + '% ';
      text += '生命值';
    } else if (e.type === 'buff' || e.type === 'debuff') {
      if (e.status) {
        text = '附加 ' + (e.name || statusMap[e.status] || e.status);
      } else {
        const statName = this._getResourceLabel(e.stat) || '属性';
        if (e.modifier !== undefined && e.modifier !== null) {
          const pct = Math.abs(e.modifier * 100).toFixed(0);
          const sign = e.modifier > 0 ? '+' : '-';
          text = statName + ' ' + sign + pct + '%';
        } else {
          text = (e.type === 'buff' ? '附加增益' : '附加减益');
          if (e.stat) text += '（' + statName + '）';
        }
      }
      if (e.duration > 0) text += '，持续' + e.duration + '回合';
    } else if (e.type === 'dot') {
      text = '持续伤害';
      if (e.element) text += '（' + (elemMap[e.element] || e.element) + '）';
      if (e.duration > 0) text += '，持续' + e.duration + '回合';
    } else if (e.type === 'fixed_dot') {
      text = '持续真实伤害';
      const dotVal = e.display_value || e.value;
      if (dotVal) text += '（' + CombatAllies.fmtNum(dotVal) + '/回合）';
      if (e.element) text += '（' + (elemMap[e.element] || e.element) + '）';
      if (e.duration > 0) text += '，持续' + e.duration + '回合';
    } else if (e.type === 'stun') {
      text = '附加 ' + (e.name || statusMap.stunned || '眩晕');
      if (e.chance) text += '（' + (e.chance * 100).toFixed(0) + '%概率）';
      if (e.duration > 0) text += '，持续' + e.duration + '回合';
    } else if (e.type === 'shield') {
      text = '获得 ';
      if (e.power && e.power !== 1.0) text += (e.power * 100).toFixed(0) + '% ';
      text += '护盾';
      if (e.duration > 0) text += '，持续' + e.duration + '回合';
    } else if (e.type === 'dispel') {
      const modeMap = { all: '所有效果', buff: '增益', debuff: '减益' };
      text = '驱散' + (e.count ? ' ' + e.count + '个' : '') + '（' + (modeMap[e.mode] || '效果') + '）';
    } else if (e.type === 'lifesteal') {
      text = '吸血';
      if (e.ratio) text += '（' + (e.ratio * 100).toFixed(0) + '%转化）';
    } else {
      text = e.type;
    }

    const targetMap = {
      enemy: '单个敌人', self: '自身',
      all_enemy: '全体敌人', all_ally: '全体友方',
    };
    if (e.target) text += ' [' + (targetMap[e.target] || e.target) + ']';

    return text;
  }
}

customElements.define('abilities-panel', AbilitiesPanel);
