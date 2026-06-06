// plugins/combat/combat-panels.js
// 技能/物品选择子面板 — 从旧前端 CombatUI 子面板方法移植
import { CombatAllies } from '/static/plugins/combat/frontend-v2/combat-allies.js';

export const CombatPanels = {
  /** 渲染技能列表 */
  renderAbilityList(state, targeter, esc, getRarityInfo) {
    const abilities = state.available_abilities || [];
    const pAttrs = (state.player && state.player.attrs) || {};
    const pHp = (state.player && state.player.vitality) || 0;
    const pools = state.pool_attrs || [];
    const cooldowns = (state.player && state.player.cooldowns) || {};

    const labelMap = {};
    for (const pool of pools) labelMap[pool.name] = pool.label;
    const attrLabels = state.attr_labels || {};
    for (const k in attrLabels) labelMap[k] = attrLabels[k];

    let html = '<div class="combat-sub-title">选择技能<span class="combat-sub-close" data-action="close-panel">&times;</span></div>';
    html += '<div class="combat-sub-scroll"><div class="combat-sub-list">';

    if (abilities.length === 0) {
      html += '<div style="color:var(--color-text-dim);text-align:center;padding:10px;font-size:var(--font-size-xs)">没有可用技能</div>';
    } else {
      for (const s of abilities) {
        html += this._buildAbilityRow(s, labelMap, pAttrs, pHp, cooldowns, targeter, esc, getRarityInfo);
      }
    }

    html += '</div></div>';
    html += '<div class="combat-sub-hint">' + this._getHintText(targeter) + '</div>';
    return html;
  },

  /** 渲染物品列表 */
  renderItemList(state, targeter, esc) {
    const items = state.available_items || [];
    const pools = state.pool_attrs || [];
    const labelMap = {};
    for (const pool of pools) labelMap[pool.name] = pool.label;
    const attrLabels = state.attr_labels || {};
    for (const k in attrLabels) labelMap[k] = attrLabels[k];

    let html = '<div class="combat-sub-title">选择物品<span class="combat-sub-close" data-action="close-panel">&times;</span></div>';
    html += '<div class="combat-sub-scroll"><div class="combat-sub-list">';

    if (items.length === 0) {
      html += '<div style="color:var(--color-text-dim);text-align:center;padding:10px;font-size:var(--font-size-xs)">没有可用物品</div>';
    } else {
      for (const item of items) {
        html += this._buildItemRow(item, labelMap, targeter, esc);
      }
    }

    html += '</div></div>';
    html += '<div class="combat-sub-hint">' + this._getHintText(targeter) + '</div>';
    return html;
  },

  /** 获取稀有度信息 */
  getRarityInfo(rarityInt, abilityRarities) {
    const rarities = (abilityRarities && abilityRarities.rarities) || [];
    for (const r of rarities) {
      if (rarityInt >= r.min && rarityInt <= r.max) return r;
    }
    return { id: 'common', name: '普通', color: '#9e9e9e' };
  },

  /** 格式化效果文本 */
  formatEffectText(e, getAttrLabel) {
    const elemMap = { fire: '火', ice: '冰', thunder: '雷', wind: '风', earth: '土', light: '光', dark: '暗' };
    const statusMap = { frozen: '冻结', stunned: '眩晕', poisoned: '中毒', burned: '灼烧' };
    let text = '';

    if (e.type === 'damage') {
      text = '造成 ';
      if (e.scale_stat) text += getAttrLabel(e.scale_stat) + '×';
      if (e.power && e.power !== 1.0) text += (e.power * 100).toFixed(0) + '% ';
      if (e.element) text += (elemMap[e.element] || e.element) + ' ';
      text += '伤害';
    } else if (e.type === 'fixed_damage') {
      text = '造成 ';
      const fdVal = e.display_value || e.value;
      if (fdVal) text += CombatAllies.fmtNum(fdVal) + ' 点';
      text += '真实伤害';
    } else if (e.type === 'fixed_dot') {
      text = '持续真实伤害';
      const dotVal = e.display_value || e.value;
      if (dotVal) text += '（' + CombatAllies.fmtNum(dotVal) + '/回合）';
      if (e.duration > 0) text += '，持续' + e.duration + '回合';
    } else if (e.type === 'heal') {
      text = '恢复 ';
      if (e.value) {
        text += e.value + ' 点';
      } else if (e.power && e.power !== 1.0) {
        text += (e.power * 100).toFixed(0) + '% ';
      }
      text += getAttrLabel(e.stat) || '生命值';
    } else if (e.type === 'buff' || e.type === 'debuff') {
      if (e.status) {
        text = '附加 ' + (e.name || statusMap[e.status] || e.status);
      } else {
        const statName = getAttrLabel(e.stat) || '属性';
        if (e.modifier !== undefined && e.modifier !== null) {
          const pct = Math.abs(e.modifier * 100).toFixed(0);
          const sign = e.modifier > 0 ? '+' : '-';
          text = statName + ' ' + sign + pct + '%';
        } else if (e.value) {
          const sign = e.value > 0 ? '+' : '';
          text = statName + ' ' + sign + e.value;
        } else {
          text = statName + '变化';
        }
      }
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
  },

  // ========== 内部方法 ==========

  _buildAbilityRow(s, labelMap, pAttrs, pHp, cooldowns, targeter, esc, getRarityInfo) {
    const costs = s.costs || [];
    let canUse = true;
    if (cooldowns[s.id] > 0) canUse = false;
    const costParts = [];
    for (const cost of costs) {
      const cur = (cost.resource === 'vitality') ? pHp : (pAttrs[cost.resource] || 0);
      if (cur < cost.amount) canUse = false;
      const label = labelMap[cost.resource] || cost.resource;
      costParts.push(label + ' ' + CombatAllies.fmtNum(cost.amount));
    }
    if (costParts.length === 0) costParts.push('无消耗');

    const isSelected = targeter.selectedAbilityId === s.id;
    let itemClass = 'combat-sub-item';
    if (isSelected) itemClass += ' selected';
    if (!canUse) itemClass += ' disabled';

    let reasons = [];
    if (cooldowns[s.id] > 0) reasons.push('冷却' + cooldowns[s.id]);
    let costInsufficient = false;
    for (const cost of costs) {
      const cur2 = (cost.resource === 'hp') ? pHp : (pAttrs[cost.resource] || 0);
      if (cur2 < cost.amount) { costInsufficient = true; break; }
    }
    if (costInsufficient) reasons.push('不足');
    let costText = costParts.join(' ');
    if (reasons.length > 0) costText += ' (' + reasons.join('+') + ')';

    const rarityInfo = getRarityInfo(s.rarity || 0);
    const rarityColor = rarityInfo.color || '#9e9e9e';
    const rarityClass = 'combat-sub-rarity--' + (rarityInfo.id || 'common');

    return '<div class="' + itemClass + ' ' + rarityClass + '" data-ability-id="' + esc(s.id) + '"' +
      (canUse ? '' : ' style="pointer-events:none"') + '>' +
      '<span class="combat-sub-item-name">' +
      '<span class="combat-sub-rarity-dot" style="background:' + rarityColor + ';"></span>' +
      esc(s.name) + '</span>' +
      '<span class="combat-sub-item-desc">' + esc(s.description || '') + '</span>' +
      '<span class="combat-sub-item-cost">' + costText + '</span>' +
      '</div>';
  },

  _buildItemRow(item, labelMap, targeter, esc) {
    const name = item.name || item.item_id;
    const qty = item.quantity || 1;
    let costText = '-';
    if (item.costs && item.costs.length > 0) {
      const parts = item.costs.map(c => {
        const label = (labelMap && labelMap[c.resource]) || c.resource;
        return label + ' ' + CombatAllies.fmtNum(c.amount);
      });
      costText = parts.join(' ');
    } else if (item.mp_cost) {
      const mpLabel = (labelMap && labelMap['mp']) || 'MP';
      costText = mpLabel + ' ' + item.mp_cost;
    }

    const isSelected = targeter.selectedItemId === item.item_id;
    let itemClass = 'combat-sub-item';
    if (isSelected) itemClass += ' selected';

    return '<div class="' + itemClass + '" data-item-id="' + esc(item.item_id) + '">' +
      '<span class="combat-sub-item-name">' + esc(name) + '</span>' +
      '<span class="combat-sub-item-desc">' + esc(item.description || '') + '</span>' +
      '<span class="combat-sub-item-cost">' + costText + '</span>' +
      '<span class="combat-sub-item-qty">x' + qty + '</span>' +
      '</div>';
  },

  _getHintText(targeter) {
    if (targeter.selectedAction === 'ability') {
      if (targeter.targetingMode) {
        const word = '施放';
        if (targeter.targetingType === 'single_enemy') return '点击目标敌人确认' + word;
        else if (targeter.targetingType === 'all_enemy') return '点击全体敌人外框确认' + word;
        else if (targeter.targetingType === 'self') return '点击玩家状态栏确认' + word;
      }
      return '选择技能后确认目标施放';
    } else if (targeter.selectedAction === 'item') {
      if (targeter.targetingMode) {
        const word = '使用';
        if (targeter.targetingType === 'single_enemy') return '点击目标敌人确认' + word;
        else if (targeter.targetingType === 'all_enemy') return '点击全体敌人外框确认' + word;
        else if (targeter.targetingType === 'self') return '点击玩家状态栏确认' + word;
      }
      return '选择物品后确认目标使用';
    }
    return '';
  },

  /** 获取属性标签（从 schema） */
  getAttrLabel(attrId, schema) {
    const attrs = (schema && schema.attributes) || {};
    const def = attrs[attrId];
    return (def && def.label) || attrId;
  },
};
