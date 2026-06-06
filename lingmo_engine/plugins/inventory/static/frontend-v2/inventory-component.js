import { ComponentBase } from '/static/frontend-v2/shared/component-base.js';
import { AppState } from '/static/frontend-v2/state/app-state.js';
import { WebSocketService } from '/static/frontend-v2/services/websocket.js';
import { i18n } from '/static/frontend-v2/shared/i18n.js';
import { CombatAllies } from '/static/plugins/combat/frontend-v2/combat-allies.js';

const CSS = `
  :host { display: block; overflow-y: auto; height: 100%; scrollbar-width: none; }
  :host::-webkit-scrollbar { display: none; }

  .inv-header-row {
    display: flex; justify-content: space-between; align-items: center;
    padding: 12px 14px; border-bottom: 1px solid var(--color-border-light);
  }
  .inv-header-left { display: flex; align-items: center; gap: 10px; }
  .inv-header-icon {
    width: 36px; height: 36px; border-radius: var(--radius-md);
    background: var(--color-surface-alt); border: 1px solid var(--color-border-strong);
    display: flex; align-items: center; justify-content: center;
    color: var(--color-primary); font-size: calc(14px * var(--font-scale)); flex-shrink: 0;
  }
  .inv-header-row .inv-title { font-family: var(--font-narrative); font-size: var(--font-size-narrative); color: var(--color-primary); font-weight: 600; }
  .inv-header-row .inv-count { font-size: var(--font-size-xs); color: var(--color-text-dim); }
  .inv-header-tags { display: flex; gap: var(--space-xs); flex-wrap: wrap; }

  .inv-equip-grid { display: flex; gap: var(--space-sm); flex-wrap: wrap; margin: var(--space-lg) 14px; }
  .inv-equip-slot {
    background: var(--color-surface-alt); padding: var(--space-sm) 10px;
    border-radius: var(--radius-md); border: 1px solid var(--color-border-light);
    cursor: pointer; transition: all 0.2s; flex: 1; min-width: 0;
    height: 94px; display: flex; flex-direction: column; justify-content: center;
    overflow: hidden;
  }
  .inv-equip-slot:hover { border-color: var(--color-primary); }
  .inv-equip-slot.selected { border-color: var(--color-primary); background: var(--color-primary-bg); }
  .inv-equip-slot .inv-slot-label { font-size: var(--font-size-2xs); color: var(--color-text-muted); }
  .inv-equip-slot .inv-slot-name { font-size: var(--font-size-sm); }
  .inv-equip-slot .inv-slot-bonus { font-size: var(--font-size-2xs); color: var(--color-secondary); margin-left: var(--space-sm); }
  .inv-equip-slot .inv-slot-narrative { font-size: var(--font-size-2xs); color: var(--color-text-muted); margin-left: var(--space-sm); font-style: italic; }
  .inv-equip-slot.empty .inv-slot-name { color: var(--color-text-dim); }

  .inv-cat-bar { display: flex; gap: 10px; margin: 0 14px var(--space-md); padding-bottom: var(--space-sm); border-bottom: 1px solid var(--color-border); }
  .inv-cat-tab { font-size: var(--font-size-xs); color: var(--color-text-dim); cursor: pointer; padding: 2px 0; border-bottom: 1px solid transparent; transition: all 0.2s; }
  .inv-cat-tab:hover { color: var(--color-text); }
  .inv-cat-tab.active { color: var(--color-primary); border-bottom-color: var(--color-primary); }

  .inv-item-list { margin: 0 14px; }
  .inv-item-row {
    display: flex; align-items: center; padding: 7px 10px;
    border-bottom: 1px solid var(--color-border); cursor: pointer;
    transition: background 0.15s; border-radius: var(--radius-sm); font-size: var(--font-size-xs);
  }
  .inv-item-row:hover { background: var(--color-primary-bg); }
  .inv-item-row.selected { background: rgba(201,169,97,0.06); border-bottom-color: var(--color-border-light); }
  .inv-item-row .inv-item-name { width: 100px; font-size: var(--font-size-sm); font-weight: 600; flex-shrink: 0; }
  .inv-item-row .inv-item-cat { width: 50px; font-size: var(--font-size-2xs); color: var(--color-text-dim); flex-shrink: 0; }
  .inv-item-row .inv-item-desc { flex: 1; font-size: var(--font-size-2xs); color: var(--color-text-muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .inv-item-row .inv-item-qty { margin-left: var(--space-sm); font-size: var(--font-size-2xs); flex-shrink: 0; }
  .inv-item-row .inv-item-actions { margin-left: var(--space-sm); display: flex; gap: 5px; font-size: var(--font-size-2xs); flex-shrink: 0; }
  .inv-item-row .inv-item-actions span { color: var(--color-primary); cursor: pointer; }
  .inv-item-row .inv-item-actions span:hover { text-decoration: underline; }
  .inv-item-row .inv-item-actions span.danger { color: var(--color-danger); }

  .inv-detail-card {
    margin: var(--space-lg) 14px 0; padding: 10px var(--space-lg);
    background: var(--color-surface-alt); border-radius: var(--radius-md); border: 1px solid var(--color-border-light);
  }
  .inv-detail-card .inv-detail-name { font-size: var(--font-size-md); font-weight: 600; margin-bottom: var(--space-xs); }
  .inv-detail-card .inv-detail-meta { font-size: var(--font-size-xs); color: var(--color-text-dim); margin-bottom: var(--space-xs); }
  .inv-detail-card .inv-detail-desc { font-size: var(--font-size-xs); color: var(--color-text); line-height: 1.6; }
  .inv-detail-card .inv-detail-btns { display: flex; gap: var(--space-sm); margin-top: var(--space-sm); justify-content: flex-end; }
  .inv-detail-card .inv-detail-btns button { padding: 5px 14px; border-radius: 4px; font-size: var(--font-size-xs); font-family: var(--font-ui); cursor: pointer; transition: all 0.2s; }
  .inv-detail-card .inv-detail-btns .inv-btn-action { background: rgba(201,169,97,0.1); border: 1px solid rgba(201,169,97,0.15); color: var(--color-primary); }
  .inv-detail-card .inv-detail-btns .inv-btn-action:hover { background: rgba(201,169,97,0.2); }
  .inv-detail-card .inv-detail-btns .inv-btn-drop { background: transparent; border: 1px solid var(--color-border-light); color: var(--color-text-dim); }
  .inv-detail-card .inv-detail-btns .inv-btn-drop:hover { color: var(--color-danger); border-color: var(--color-danger); }

  .inv-empty { color: var(--color-text-muted); font-size: var(--font-size-xs); text-align: center; padding: 20px; }
  .inv-item-tags { display: inline-flex; gap: 3px; flex-shrink: 0; }
  .inv-tag { font-size: var(--font-size-2xs); padding: 1px 4px; background: rgba(126,184,218,0.1); color: var(--color-mana); border-radius: var(--radius-sm); }
  .inv-detail-req { font-size: var(--font-size-xs); margin-bottom: var(--space-xs); color: var(--color-secondary); }

  .inv-expand {
    background: var(--color-surface-alt); border: 1px solid var(--color-border-light);
    border-top: none; border-radius: 0 0 var(--radius-md) var(--radius-md);
    padding: var(--space-sm) var(--space-lg); margin-bottom: 2px;
  }
  .inv-expand .inv-expand-meta { font-size: var(--font-size-2xs); color: var(--color-text-dim); margin-bottom: 3px; }
  .inv-expand .inv-expand-effects { font-size: var(--font-size-xs); color: var(--color-mana); margin-bottom: 3px; }
  .inv-expand .inv-expand-bonus { font-size: var(--font-size-xs); color: var(--color-secondary); margin-bottom: 3px; }
  .inv-expand .inv-expand-desc { font-size: var(--font-size-xs); color: var(--color-text); line-height: 1.5; margin-bottom: var(--space-xs); }
  .inv-expand .inv-expand-btns { display: flex; gap: var(--space-sm); justify-content: flex-end; margin-top: var(--space-xs); }
  .inv-expand .inv-expand-btns button { padding: 5px 14px; border-radius: 4px; font-size: var(--font-size-xs); font-family: var(--font-ui); cursor: pointer; transition: all 0.2s; }
  .inv-expand .inv-expand-btns .inv-btn-action { background: rgba(201,169,97,0.1); border: 1px solid rgba(201,169,97,0.15); color: var(--color-primary); }
  .inv-expand .inv-expand-btns .inv-btn-action:hover { background: rgba(201,169,97,0.2); }
  .inv-expand .inv-expand-btns .inv-btn-drop { background: transparent; border: 1px solid var(--color-border-light); color: var(--color-text-dim); }
  .inv-expand .inv-expand-btns .inv-btn-drop:hover { color: var(--color-danger); border-color: var(--color-danger); }
`;

export class InventoryPanel extends ComponentBase {
  static get observedState() { return ['inventory']; }

  constructor() {
    super();
    this._invSelectedSlot = null;
    this._invSelectedCategory = null;
    this._invSelectedItem = null;
    this._initialRequested = false;
  }

  _onStateChanged(key, data) {
    this._renderAll();
  }

  // ==================== 主渲染 ====================

  _renderAll() {
    const data = AppState.getInventory();
    if (!data) {
      this._renderHTML(`<style>${CSS}</style><div class="inv-empty">加载中...</div>`);
      // 首次挂载时请求背包数据
      if (!this._initialRequested) {
        this._initialRequested = true;
        WebSocketService.send({ type: 'inventory_open' });
      }
      return;
    }

    // 如果数据不完整（例如没有槽位定义），请求完整数据
    if (!(data.slots && data.slots.length) && !this._initialRequested) {
      this._initialRequested = true;
      WebSocketService.send({ type: 'inventory_open' });
    }

    // 初始化默认分类
    this._invSelectedCategory = this._invSelectedCategory || (data.categories && data.categories[0] && data.categories[0].id);

    const usedSlots = (data.inventory || []).reduce((s, i) => s + (i.quantity || 1), 0);
    const totalSlots = data.max_slots || 30;

    let html = '';

    // 标题行
    html += '<div class="inv-header-row">';
    html += '<div class="inv-header-left">';
    html += '<div class="inv-header-icon">包</div>';
    html += '<div>';
    html += '<span class="inv-title">背包</span>';
    html += '</div>';
    html += '</div>';
    html += '</div>';

    // 金币显示
    if (data.gold > 0) {
      html += `<div style="font-size:var(--font-size-xs);color:var(--color-primary);margin-bottom:10px;">金币 ${data.gold}</div>`;
    }

    // 装备槽位网格
    html += this._renderEquipGrid(data);

    // 分类标签栏
    html += this._renderCategoryBar(data);

    // 物品列表
    html += this._renderItemList(data);

    this._renderHTML(`<style>${CSS}</style>${html}`);

    // DOM 更新后绑定事件
    setTimeout(() => this._bindInventoryEvents(), 0);
  }

  // ==================== 装备槽位网格 ====================

  _renderEquipGrid(data) {
    const slots = data.slots || [];
    const equipment = data.equipment || {};
    let h = '<div class="inv-equip-grid">';
    for (const slot of slots) {
      const item = equipment[slot.id];
      const hasItem = !!item;
      const isSelected = this._invSelectedSlot === slot.id;
      const cls = 'inv-equip-slot' + (isSelected ? ' selected' : '') + (!hasItem ? ' empty' : '');
      h += `<div class="${cls}" data-slot="${this._esc(slot.id)}">`;
      h += `<div class="inv-slot-label">${this._esc(slot.name)}</div>`;
      if (hasItem) {
        const rarity = item.rarity_info || this._getRarity(item.rarity);
        h += `<div class="inv-slot-name" style="color:${rarity.color}">${this._esc(item.name)}</div>`;
        // 优先显示叙事效果，无叙事效果时回退显示属性加成
        if (item.narrative_effects && Object.keys(item.narrative_effects).length) {
          const firstEffect = Object.values(item.narrative_effects)[0];
          const truncated = firstEffect.length > 20 ? firstEffect.substring(0, 20) + '…' : firstEffect;
          h += `<div class="inv-slot-narrative">${this._esc(truncated)}</div>`;
        } else if (item.stat_bonus && Object.keys(item.stat_bonus).length) {
          h += `<span class="inv-slot-bonus">${this._formatStatBonusShort(item.stat_bonus)}</span>`;
        }
      } else {
        h += '<div class="inv-slot-name">—</div>';
      }
      h += '</div>';
    }
    h += '</div>';
    return h;
  }

  // ==================== 分类标签栏 ====================

  _renderCategoryBar(data) {
    const cats = data.categories || [];
    let h = '<div class="inv-cat-bar">';
    for (const c of cats) {
      const isActive = this._invSelectedCategory === c.id;
      h += `<span class="inv-cat-tab${isActive ? ' active' : ''}" data-cat="${this._esc(c.id)}">${this._esc(c.name)}</span>`;
    }
    h += '</div>';
    return h;
  }

  // ==================== 物品列表 ====================

  _renderItemList(data) {
    const inventory = data.inventory || [];

    let items = [];
    if (this._invSelectedSlot) {
      // 按装备槽位过滤
      items = inventory.filter(e => e.category === 'equipment' && e.equip_slot === this._invSelectedSlot);
    } else if (this._invSelectedCategory && this._invSelectedCategory !== 'all') {
      // 按分类过滤（"全部"不过滤）
      items = inventory.filter(e => e.category === this._invSelectedCategory);
    } else {
      // 全部
      items = inventory;
    }

    if (items.length === 0) {
      return '<div class="inv-empty">暂无物品</div>';
    }

    let h = '<div class="inv-item-list">';
    for (const item of items) {
      const isSelected = this._invSelectedItem && this._invSelectedItem.id === item.id;
      const rarity = item.rarity_info || this._getRarity(item.rarity);
      const cls = 'inv-item-row' + (isSelected ? ' selected' : '');

      h += `<div class="${cls}" data-item="${this._esc(item.id)}">`;
      h += `<span class="inv-item-name" style="color:${rarity.color}">${this._esc(item.name)}</span>`;
      h += `<span class="inv-item-cat">${this._esc(this._getCategoryName(data, item.category))}</span>`;
      h += `<span class="inv-item-desc">${this._esc(item.description || '')}</span>`;
      if (item.tags && item.tags.length) {
        h += '<span class="inv-item-tags">';
        h += item.tags.map(t => `<span class="inv-tag">${this._esc(t)}</span>`).join('');
        h += '</span>';
      }
      h += `<span class="inv-item-qty" style="color:${rarity.color}">x${item.quantity || 1}</span>`;
      h += '</div>';

      // 行内展开详情
      if (isSelected) {
        h += this._renderItemExpand(item, data);
      }
    }
    h += '</div>';
    return h;
  }

  // ==================== 物品详情卡片 ====================

  _renderItemExpand(item, data) {
    const rarity = item.rarity_info || this._getRarity(item.rarity);

    let h = '<div class="inv-expand">';

    // 分类 · 稀有度 · 槽位
    let metaParts = [this._getCategoryName(data, item.category), rarity.name];
    if (item.equip_slot) metaParts.push(item.equip_slot);
    h += `<div class="inv-expand-meta">${this._esc(metaParts.join(' · '))}</div>`;

    // 属性加成
    if (item.stat_bonus && Object.keys(item.stat_bonus).length) {
      h += `<div class="inv-expand-bonus">${this._formatStatBonusFull(item.stat_bonus)}</div>`;
    }

    // 效果文本
    if (item.effects && item.effects.length) {
      const fxText = item.effects.map(e => this._formatEffectText(e)).join('；');
      h += `<div class="inv-expand-effects">${fxText}</div>`;
    }

    // 描述
    if (item.description) {
      h += `<div class="inv-expand-desc">${this._esc(item.description)}</div>`;
    }

    // 操作按钮
    h += '<div class="inv-expand-btns">';
    const equipment = data.equipment || {};
    let equippedSlot = null;
    for (const slotId in equipment) {
      if (equipment[slotId] && equipment[slotId].id === item.id) {
        equippedSlot = slotId;
        break;
      }
    }
    if (equippedSlot) {
      h += `<button class="inv-btn-action" data-action="unequip" data-slot="${this._esc(equippedSlot)}">卸下</button>`;
    } else if (item.is_equipment) {
      h += `<button class="inv-btn-action" data-action="equip" data-item="${this._esc(item.id)}" data-slot="${this._esc(item.equip_slot || '')}">装备</button>`;
    }
    if (item.is_consumable && !item.combat_only) {
      h += `<button class="inv-btn-action" data-action="use" data-item="${this._esc(item.id)}">使用</button>`;
    }
    if (!item.is_key_item) {
      h += `<button class="inv-btn-drop" data-action="drop" data-item="${this._esc(item.id)}">丢弃</button>`;
    }
    h += '</div>';

    h += '</div>';
    return h;
  }

  // ==================== 事件绑定 ====================

  _bindInventoryEvents() {
    const root = this.shadowRoot;
    if (!root) return;

    // 装备槽位点击 → 按槽位过滤物品列表
    root.querySelectorAll('.inv-equip-slot').forEach(el => {
      el.addEventListener('click', () => {
        this._invSelectedSlot = el.dataset.slot;
        this._invSelectedItem = null;
        this._renderAll();
      });
    });

    // 分类标签点击 → 按分类过滤物品列表
    root.querySelectorAll('.inv-cat-tab').forEach(el => {
      el.addEventListener('click', () => {
        this._invSelectedCategory = el.dataset.cat;
        this._invSelectedSlot = null;
        this._invSelectedItem = null;
        this._renderAll();
      });
    });

    // 物品行点击 → 选中物品并显示详情卡片
    root.querySelectorAll('.inv-item-row').forEach(el => {
      el.addEventListener('click', (e) => {
        // 如果点击的是操作按钮，不触发物品选中
        if (e.target.dataset.action) return;
        const itemId = el.dataset.item;
        const inv = (AppState.getInventory() || {}).inventory || [];
        const item = inv.find(it => it.id === itemId);
        if (item) {
          this._invSelectedItem = item;
          this._invSelectedSlot = null;
          this._renderAll();
        }
      });
    });

    // 操作按钮（装备/使用/丢弃/卸下）
    root.querySelectorAll('[data-action]').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const action = btn.dataset.action;
        if (action === 'equip') {
          WebSocketService.send({ type: 'inventory_action', action: 'equip', item_id: btn.dataset.item, slot_id: btn.dataset.slot });
        } else if (action === 'unequip') {
          WebSocketService.send({ type: 'inventory_action', action: 'unequip', slot_id: btn.dataset.slot });
        } else if (action === 'use') {
          WebSocketService.send({ type: 'inventory_action', action: 'use', item_id: btn.dataset.item });
        } else if (action === 'drop') {
          if (confirm('确定丢弃该物品？')) {
            WebSocketService.send({ type: 'inventory_action', action: 'drop', item_id: btn.dataset.item, quantity: 1 });
          }
        }
      });
    });
  }

  // ==================== 格式化辅助方法 ====================

  /** 简短属性加成文本: +5 攻伐 +3 御守 */
  _formatStatBonusShort(bonus) {
    if (!bonus) return '';
    const parts = [];
    for (const k in bonus) { parts.push('+' + bonus[k] + ' ' + this._getAttrLabel(k)); }
    return parts.join(' ');
  }

  /** 完整属性加成文本: 攻伐 +5，御守 +3 */
  _formatStatBonusFull(bonus) {
    if (!bonus) return '';
    const parts = [];
    for (const k in bonus) { parts.push(this._getAttrLabel(k) + ' +' + bonus[k]); }
    return parts.join('，');
  }

  /** 格式化效果文本为中文 */
  _formatEffectText(e) {
    const elemMap = { fire:'火', ice:'冰', thunder:'雷', wind:'风', earth:'土', light:'光', dark:'暗' };
    const statusMap = { frozen:'冻结', stunned:'眩晕', poisoned:'中毒', burned:'灼烧' };
    let text = '';
    if (e.type === 'damage') {
      text = '造成 ';
      if (e.scale_stat) text += this._getAttrLabel(e.scale_stat) + '×';
      if (e.power && e.power !== 1.0) text += (e.power * 100).toFixed(0) + '% ';
      if (e.element) text += (elemMap[e.element] || e.element) + ' ';
      text += '伤害';
    } else if (e.type === 'fixed_damage') {
      text = '造成 ';
      const fdVal = e.display_value || e.value;
      if (fdVal) text += CombatAllies.fmtNum(fdVal) + ' 点';
      text += '真实伤害';
    } else if (e.type === 'heal') {
      text = '恢复 ';
      if (e.value) text += e.value + ' 点';
      else if (e.power && e.power !== 1.0) text += (e.power * 100).toFixed(0) + '% ';
      text += this._getAttrLabel(e.stat) || '生命值';
    } else if (e.type === 'buff') {
      if (e.status) {
        text = '附加 ' + (e.name || statusMap[e.status] || e.status);
      } else {
        const statName = this._getAttrLabel(e.stat) || '属性';
        if (e.modifier !== undefined && e.modifier !== null) {
          const pct = Math.abs(e.modifier * 100).toFixed(0);
          const sign = e.modifier > 0 ? '+' : '-';
          text = statName + ' ' + sign + pct + '%';
        } else if (e.value) {
          text = statName + ' ' + (e.value > 0 ? '+' : '') + e.value;
        } else {
          text = statName + '变化';
        }
      }
      if (e.duration > 0) text += '，持续' + e.duration + '回合';
    } else if (e.type === 'debuff') {
      if (e.status) {
        text = '附加 ' + (e.name || statusMap[e.status] || e.status);
      } else {
        const statName = this._getAttrLabel(e.stat) || '属性';
        if (e.modifier !== undefined && e.modifier !== null) {
          const pct = Math.abs(e.modifier * 100).toFixed(0);
          const sign = e.modifier > 0 ? '+' : '-';
          text = statName + ' ' + sign + pct + '%';
        } else if (e.value) {
          text = statName + ' ' + (e.value > 0 ? '+' : '') + e.value;
        } else {
          text = statName + '变化';
        }
      }
      if (e.duration > 0) text += '，持续' + e.duration + '回合';
    } else if (e.type === 'dot') {
      text = '持续伤害';
      if (e.power && e.power !== 1.0) text += '（' + (e.power * 100).toFixed(0) + '%）';
      if (e.element) text += '（' + (elemMap[e.element] || e.element) + '）';
      if (e.duration > 0) text += '，持续' + e.duration + '回合';
    } else if (e.type === 'fixed_dot') {
      text = '持续真实伤害';
      const dotVal = e.display_value || e.value;
      if (dotVal) text += '（' + CombatAllies.fmtNum(dotVal) + '/回合）';
      if (e.element) text += '（' + (elemMap[e.element] || e.element) + '）';
      if (e.duration > 0) text += '，持续' + e.duration + '回合';
    } else if (e.type === 'stun') {
      text = e.name || '眩晕';
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

  /** 获取属性的中文标签（从 player schema 查找） */
  _getAttrLabel(attrId) {
    const playerSlice = AppState.getSlice('player');
    const schema = (playerSlice && playerSlice.attributesSchema && playerSlice.attributesSchema.attributes) || {};
    const def = schema[attrId];
    return (def && def.label) || attrId;
  }

  /** 根据稀有度数值获取稀有度信息 */
  _getRarity(rarityVal) {
    const data = AppState.getInventory() || {};
    const rarities = data.rarities || [];
    for (const r of rarities) {
      if (rarityVal >= r.min && rarityVal <= r.max) return r;
    }
    return { name: '普通', color: '#a0a0a0' };
  }

  /** 根据分类ID获取分类名称 */
  _getCategoryName(data, catId) {
    const cats = data.categories || [];
    for (const c of cats) { if (c.id === catId) return c.name; }
    return catId;
  }
}

customElements.define('inventory-panel', InventoryPanel);
