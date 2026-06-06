// plugins/combat/combat-allies.js
// 友方区域渲染 — 多单位横向卡片
import { i18n } from '/static/frontend-v2/shared/i18n.js';

export const CombatAllies = {
  /** 数字缩写：<1万原样，≥1万用"万"，≥1亿用"亿" */
  fmtNum(n) {
    const abs = Math.abs(n);
    if (abs < 10000) return '' + n;
    if (abs < 100000000) {
      const w = abs / 10000;
      return (n < 0 ? '-' : '') + (w % 1 === 0 ? w.toFixed(0) : w.toFixed(1)) + '万';
    }
    const y = abs / 100000000;
    return (n < 0 ? '-' : '') + (y % 1 === 0 ? y.toFixed(0) : y.toFixed(1)) + '亿';
  },

  /** 根据 level 获取边框颜色 */
  getLevelColor(level, levelColors) {
    const colors = levelColors || [];
    for (const c of colors) {
      if (level >= c.min && level <= c.max) return c.color;
    }
    return '#a0a0a0';
  },

  /** 渲染属性行：HP血量条 + 神识/体力文字 + 灵力单值 */
  renderAttrs(unit, pools, esc, prevState) {
    let html = '';
    const attrs = unit.attrs || {};

    // HP 血量条（如果有旧状态且HP有变化，用旧值渲染，等延迟动画切到新值）
    const hpCur = unit.vitality != null ? unit.vitality : 0;
    const hpMax = unit.max_vitality || 1;
    let hpPct;
    if (prevState && prevState.hp !== hpCur) {
      hpPct = Math.round(prevState.hp / Math.max(prevState.maxHp, 1) * 100);
    } else {
      hpPct = hpMax > 0 ? Math.round(hpCur / hpMax * 100) : 0;
    }
    html += '<div class="combat-hp-bar"><div class="combat-hp-fill" style="width:' + hpPct + '%"></div></div>';
    html += '<div class="combat-hp-text">' + this.fmtNum(hpCur) + ' / ' + this.fmtNum(hpMax) + '</div>';

    // 神识/体力 — 同行迷你条（无文字），悬停显示详情
    const poolParts = [];
    const tipParts = [];
    if (attrs.divine_sense != null) {
      const maxDs = attrs.max_divine_sense || 1;
      const pct = Math.round(attrs.divine_sense / maxDs * 100);
      poolParts.push('<div class="combat-pool-track"><div class="combat-pool-fill" style="width:' + pct + '%;background:rgba(142,68,173,0.5)"></div></div>');
      tipParts.push('<span style="color:rgba(142,68,173,0.7)">神识 ' + this.fmtNum(attrs.divine_sense) + '/' + this.fmtNum(maxDs) + '</span>');
    }
    if (attrs.stamina != null) {
      const maxSt = attrs.max_stamina || 1;
      const pct = Math.round(attrs.stamina / maxSt * 100);
      poolParts.push('<div class="combat-pool-track"><div class="combat-pool-fill" style="width:' + pct + '%;background:rgba(39,174,96,0.5)"></div></div>');
      tipParts.push('<span style="color:rgba(39,174,96,0.7)">体力 ' + this.fmtNum(attrs.stamina) + '/' + this.fmtNum(maxSt) + '</span>');
    }
    if (poolParts.length > 0) {
      const sep = poolParts.length > 1 ? '<div class="combat-pool-sep"></div>' : '';
      html += '<div class="combat-pool-row">'
        + poolParts.join(sep)
        + '<div class="combat-pool-tip">' + tipParts.join('<br/>') + '</div>'
        + '</div>';
    }
    if (attrs.spiritual_power != null) {
      html += '<div class="combat-sp-row" style="color:rgba(52,152,219,0.6)">灵力 ' + this.fmtNum(attrs.spiritual_power) + '</div>';
    }
    return html;
  },

  /** 将 buff 列表按 source_key 分组 */
  groupBuffs(buffs) {
    const groups = [];
    const keyMap = new Map();
    for (const b of buffs) {
      const key = b.source_key || null;
      if (!key) {
        groups.push({ key: null, name: '', buffs: [b] });
      } else if (keyMap.has(key)) {
        keyMap.get(key).buffs.push(b);
      } else {
        const g = { key, name: b.source_name || '', buffs: [b] };
        keyMap.set(key, g);
        groups.push(g);
      }
    }
    return groups;
  },

  /** 渲染 Buff 标签（按技能分组，每组一个可点击标签） */
  renderBuffs(buffs, esc, buffTagText) {
    const all = buffs || [];
    if (all.length === 0) return '<div class="combat-tags"></div>';
    const groups = this.groupBuffs(all);
    const MAX_VISIBLE = 3;
    const visGroups = groups.slice(-MAX_VISIBLE);
    const hidden = groups.length - visGroups.length;
    let html = '<div class="combat-tags">';
    for (const g of visGroups) {
      if (g.key) {
        let sum = 0;
        for (const b of g.buffs) sum += (b.modifier || 0);
        let cls = 'combat-tag clickable';
        if (sum > 0) cls += ' buff';
        else if (sum < 0) cls += ' debuff';
        else cls += ' status';
        html += '<span class="' + cls + '" data-source-key="' + esc(g.key) + '">' + esc(g.name) + '</span>';
      } else {
        for (const b of g.buffs) {
          let cls = 'combat-tag';
          if (b.modifier > 0) cls += ' buff';
          else if (b.modifier < 0) cls += ' debuff';
          else cls += ' status';
          const text = buffTagText ? buffTagText(b) : (b.name || b.status || '');
          html += '<span class="' + cls + '">' + esc(text) + '</span>';
        }
      }
    }
    if (hidden > 0) {
      html += '<span class="combat-tag more">+' + hidden + '</span>';
    }
    html += '</div>';
    return html;
  },

  /** 渲染整个友方区域 */
  render(state, esc, buffTagText, targeter, prevAllyState) {
    const allies = state.allies || [];
    const player = state.player;
    const levelColors = state.level_colors || [];

    // 构建旧HP映射，用于友方血条初始渲染为旧值（延迟动画切到新值）
    const prevHpMap = {};
    if (prevAllyState) {
      for (const p of prevAllyState) prevHpMap[p.name] = p;
    }

    // 判断自身目标选择模式
    const isSelfTarget = targeter && targeter.targetingMode && targeter.targetingType === 'self';

    // 将 player 加入友方列表显示
    const units = player ? [player, ...allies] : [...allies];

    let html = '<div class="combat-allies">';
    for (const unit of units) {
      const level = unit.level || 1;
      const color = this.getLevelColor(level, levelColors);
      let cardClass = 'combat-ally-card';
      if (isSelfTarget) cardClass += ' selectable';
      html += '<div class="' + cardClass + '" style="border-color:' + color + '" data-unit-name="' + esc(unit.name) + '">';
      html += '<div class="combat-card-name">' + esc(unit.name) + '</div>';
      html += '<div class="combat-card-lvl" style="background:' + color + '14;color:' + color + '99">Lv.' + level + '</div>';
      html += this.renderAttrs(unit, state.poolAttrs || [], esc, prevHpMap[unit.name]);
      html += this.renderBuffs(unit.buffs, esc, buffTagText);
      html += '</div>';
    }
    html += '</div>';
    return html;
  },
};