// plugins/character/static/frontend-v2/character-component.js
// 角色面板 Web Component — Schema 驱动渲染
import { ComponentBase } from '/static/frontend-v2/shared/component-base.js';
import { AppState } from '/static/frontend-v2/state/app-state.js';
import { RENDERERS } from '/static/frontend-v2/components/renderers/registry.js';

const CSS = `
  @import url('https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@400;600;700&family=Noto+Sans+SC:wght@300;400;500;700&display=swap');

  :host {
    display: block; overflow-y: auto; height: 100%;
    scrollbar-width: none;
  }
  :host::-webkit-scrollbar { display: none; }

  .char-stage {
    font-family: var(--font-narrative);
    font-size: var(--font-size-lg);
    font-weight: 700;
    color: var(--color-primary);
    letter-spacing: 4px;
    text-shadow: 0 0 12px rgba(201,169,97,0.3);
    margin: 8px 0;
    padding: 0 18px;
  }
  .char-stage-divider {
    height: 1px;
    margin: 0 var(--space-xl);
    background: linear-gradient(90deg, transparent, var(--color-border-strong), transparent);
  }
  .char-location {
    font-size: var(--font-size-2xs);
    color: var(--color-text-muted);
    margin-top: var(--space-sm);
  }

  .char-header {
    padding: 12px var(--space-xl); display: flex; align-items: center;
    border-bottom: 1px solid var(--color-border-light);
  }
  .char-header-left { display: flex; align-items: center; gap: 10px; flex: 1; }
  .char-avatar {
    width: 36px; height: 36px; border-radius: var(--radius-md);
    border: 1px solid var(--color-border-strong); flex-shrink: 0;
    background: var(--color-surface-alt); display: flex; align-items: center; justify-content: center;
    font-family: var(--font-narrative); font-size: calc(14px * var(--font-scale)); color: var(--color-primary);
    overflow: hidden;
  }
  .char-avatar img { width: 100%; height: 100%; object-fit: cover; }
  .char-name {
    font-family: var(--font-narrative); font-size: var(--font-size-narrative); font-weight: 600;
    color: var(--color-primary);
  }
  .char-dao-name {
    font-size: var(--font-size-xs);
    color: var(--color-text-dim); margin-top: 1px;
  }
  .char-meta {
    font-size: var(--font-size-xs); color: var(--color-text-dim);
    margin-top: var(--space-xs);
  }
  .char-meta .dot { color: var(--color-text-muted); margin: 0 4px; font-size: calc(6px * var(--font-scale)); vertical-align: middle; }
  .char-tags { display: flex; gap: var(--space-xs); flex-wrap: wrap; padding: 0 var(--space-xl) 8px; }
  .char-tag {
    font-size: var(--font-size-2xs); padding: 2px 8px; border-radius: var(--radius-sm);
    color: var(--color-primary); background: var(--color-primary-bg); border: 1px solid var(--color-border-light);
  }

  .panel-body { padding: 10px var(--space-xl) var(--space-xxl); }

  .section-card {
    background: var(--color-surface-alt); border: 1px solid var(--color-border);
    border-radius: var(--radius-md); padding: 10px var(--space-lg); margin-bottom: var(--space-lg);
    transition: border-color 0.2s;
  }
  .section-card:hover { border-color: var(--color-border-strong); }
  .section-title {
    font-family: var(--font-narrative); font-size: var(--font-size-sm); font-weight: 600;
    color: var(--color-primary); letter-spacing: 2px; margin-bottom: var(--space-md);
    display: flex; align-items: center; gap: var(--space-sm);
  }
  .section-title::after {
    content: ''; flex: 1; height: 1px;
    background: linear-gradient(90deg, var(--color-border-strong), transparent);
  }

  .pool-row { display: flex; align-items: center; gap: var(--space-sm); margin-bottom: var(--space-sm); }
  .pool-row:last-child { margin-bottom: 0; }
  .pool-label { width: 28px; font-size: var(--font-size-xs); text-align: right; flex-shrink: 0; }
  .pool-track {
    flex: 1; height: 5px; background: rgba(255,255,255,0.04);
    border-radius: var(--radius-sm); overflow: hidden;
  }
  .pool-fill {
    height: 100%; border-radius: var(--radius-sm); transition: width 0.3s ease;
  }
  .pool-val {
    width: 48px; font-size: var(--font-size-xs); color: var(--color-text-dim);
    text-align: right; font-variant-numeric: tabular-nums;
  }
  .pool-hp .pool-label { color: var(--color-danger); }
  .pool-hp .pool-fill { background: var(--color-danger); }
  .pool-mp .pool-label { color: var(--color-mana); }
  .pool-mp .pool-fill { background: var(--color-mana); }
  .pool-sp .pool-label { color: var(--color-heal); }
  .pool-sp .pool-fill { background: var(--color-heal); }

  .stat-grid { display: flex; gap: var(--space-xs); flex-wrap: wrap; }
  .stat-item {
    display: flex; align-items: center; gap: 4px;
    padding: 5px 10px; border-radius: var(--radius-sm); background: var(--color-surface-alt);
    border: 1px solid var(--color-border); transition: background 0.15s; flex: 1; min-width: 0;
  }
  .stat-item:hover { background: rgba(255,255,255,0.04); }
  .stat-label { font-size: var(--font-size-xs); color: var(--color-text-dim); }
  .stat-val {
    font-size: var(--font-size-md); font-weight: 500; color: var(--color-text);
    font-variant-numeric: tabular-nums;
  }

  .cult-line {
    display: flex; justify-content: space-between; align-items: center;
    padding: var(--space-xs) 0; font-size: var(--font-size-sm); border-bottom: 1px solid var(--color-border);
  }
  .cult-line:last-child { border-bottom: none; }
  .cult-key { color: var(--color-text-dim); }
  .cult-val { color: var(--color-text); font-weight: 500; }
  .cult-val.highlight { color: var(--color-primary); }

  .equip-item {
    display: flex; align-items: center; gap: var(--space-sm);
    padding: var(--space-sm) 0; border-bottom: 1px solid var(--color-border);
  }
  .equip-item:last-child { border-bottom: none; }
  .equip-slot-label {
    font-size: var(--font-size-2xs); color: var(--color-text-muted);
    width: 32px; flex-shrink: 0; text-align: right;
  }
  .equip-name { font-size: var(--font-size-sm); color: var(--color-text); }

  .skill-list { display: flex; flex-wrap: wrap; gap: var(--space-sm); }
  .skill-chip {
    font-size: var(--font-size-xs); padding: 3px 12px; border-radius: 4px;
    background: var(--color-primary-bg); color: var(--color-primary); border: 1px solid var(--color-border-light);
    cursor: default; transition: all 0.15s;
  }
  .skill-chip:hover { background: rgba(201,169,97,0.18); }

  .text-block { font-size: var(--font-size-sm); color: var(--color-text-dim); line-height: 1.7; }

  .affair-item {
    font-size: var(--font-size-xs); color: var(--color-text-dim);
    padding: 3px 0 3px 12px; position: relative;
  }
  .affair-item::before {
    content: ''; position: absolute; left: 0; top: 50%;
    width: 4px; height: 4px; border-radius: 50%;
    background: var(--color-primary-dim); transform: translateY(-50%);
  }

  .memory-item {
    font-size: var(--font-size-xs); color: var(--color-text-dim);
    padding: 5px 0; border-bottom: 1px solid var(--color-border); line-height: 1.5;
  }
  .memory-item:last-child { border-bottom: none; }
  .memory-label {
    font-size: var(--font-size-2xs); color: var(--color-primary); opacity: 0.7;
    margin-bottom: 2px; font-weight: 500;
  }

  .relation-item {
    display: flex; align-items: center; gap: var(--space-sm); padding: var(--space-xs) 0; font-size: var(--font-size-xs);
  }
  .relation-name { color: var(--color-text); }
  .relation-val {
    margin-left: auto; font-size: var(--font-size-2xs); padding: 1px 8px; border-radius: var(--radius-sm);
  }
  .rel-friendly { background: rgba(90,158,143,0.12); color: var(--color-heal); }
  .rel-cold { background: rgba(255,255,255,0.05); color: var(--color-text-muted); }
  .rel-neutral { background: rgba(255,255,255,0.05); color: var(--color-text-dim); }
  .rel-hostile { background: rgba(224,80,80,0.12); color: var(--color-danger); }
`;

export class CharacterPanel extends ComponentBase {
  static get observedState() { return ['player']; }

  connectedCallback() {
    super.connectedCallback();
  }

  _onStateChanged(key, data) {
    this._renderAll();
  }

  _getPlayerState() {
    const state = AppState.getSlice('player');
    if (!state) return {};
    return {
      character: state.characterData,
      panelConfig: state.panelConfig,
      panelSchema: state.panelSchema,
      displayValues: state.displayValues,
      attrsSchema: state.attributesSchema,
      abilitiesData: state.abilitiesData,
      equipmentExpanded: state.equipmentExpanded,
      memories: state.memories,
      relationships: state.relationshipsResolved,
    };
  }

  _renderAll() {
    const s = this._getPlayerState();
    const character = s.character;

    if (!character) {
      this._renderHTML(`<style>${CSS}</style><div style="color:var(--color-text-dim);padding:20px;font-family:var(--font-ui)">加载中...</div>`);
      return;
    }

    if (s.panelSchema && Object.keys(s.panelSchema).length > 0) {
      this._renderSchemaDriven(s);
    } else {
      this._renderFallback(s);
    }
  }

  _renderSchemaDriven(s) {
    const data = {
      character: s.character,
      displayValues: s.displayValues || {},
      attrsSchema: s.attrsSchema || {},
      abilities: s.abilitiesData,
      equipment: s.equipmentExpanded,
      memories: s.memories,
      relationships: s.relationships,
    };

    const sections = (s.panelConfig && s.panelConfig.show_sections) || [];
    let headerHtml = '';
    let bodyHtml = '';

    for (const sectionKey of sections) {
      const sectionDef = s.panelSchema[sectionKey];
      if (!sectionDef) continue;
      const renderer = RENDERERS[sectionDef.renderer];
      if (renderer) {
        const rendered = renderer(sectionDef, data, this._esc.bind(this));
        if (sectionKey === 'header') {
          headerHtml += rendered;
        } else {
          bodyHtml += rendered;
        }
      }
    }

    this._renderHTML(`<style>${CSS}</style>${headerHtml}<div class="panel-body">${bodyHtml}</div>`);
  }

  _renderFallback(s) {
    const c = s.character;
    const schema = s.attrsSchema;
    const panelConfig = s.panelConfig;
    const abilitiesData = s.abilitiesData;
    const equipmentExpanded = s.equipmentExpanded;
    const memories = s.memories;
    const relationships = s.relationships;

    const sections = (panelConfig && panelConfig.show_sections) || [];

    let headerHtml = '';
    if (sections.includes('header')) headerHtml = this._renderHeader(c, schema);

    let bodyHtml = '';
    if (sections.includes('vitals') && schema && schema.attributes) bodyHtml += this._renderVitals(c, schema);
    if (sections.includes('stats') && schema && schema.attributes) bodyHtml += this._renderStats(c, schema);
    if (sections.includes('cultivation')) bodyHtml += this._renderCultivation(c, schema);
    if (sections.includes('equipment')) bodyHtml += this._renderEquipment(c, equipmentExpanded);
    if (sections.includes('abilities')) bodyHtml += this._renderAbilities(c, abilitiesData);
    if (sections.includes('personality')) {
      bodyHtml += this._renderTextSection('性情', c.personality);
    }
    if (sections.includes('appearance')) {
      bodyHtml += this._renderTextSection('外貌', c.extra?.appearance);
    }
    if (sections.includes('clothing')) {
      bodyHtml += this._renderTextSection('衣着', c.extra.clothing);
    }
    if (sections.includes('background')) {
      bodyHtml += this._renderTextSection('身世', c.background);
    }
    if (sections.includes('affairs')) {
      bodyHtml += this._renderAffairs(c.current_affairs || []);
    }
    if (sections.includes('memories')) {
      bodyHtml += this._renderMemories(memories);
    }
    if (sections.includes('relationships')) {
      bodyHtml += this._renderRelationships(relationships);
    }
    if (sections.includes('loot') && c.loot_table) {
      bodyHtml += this._renderLoot(c.loot_table);
    }

    this._renderHTML(`<style>${CSS}</style>${headerHtml}<div class="panel-body">${bodyHtml}</div>`);
  }

  // ── 旧渲染方法（fallback 用）──────────────────────

  _renderHeader(c, schema) {
    let avatarHtml;
    if (c.avatar) {
      avatarHtml = `<div class="char-avatar"><img src="${this._esc(c.avatar)}" alt="${this._esc(c.name)}" onerror="this.parentElement.textContent='${this._esc(c.name.charAt(0))}'"></div>`;
    } else {
      avatarHtml = `<div class="char-avatar">${this._esc(c.name ? c.name.charAt(0) : '?')}</div>`;
    }
    const daoNameHtml = c.dao_name ? `<div class="char-dao-name">「${this._esc(c.dao_name)}」</div>` : '';

    // 境界独立展示
    const stageText = [c.extra?.cultivation_stage || '', c.extra?.cultivation_substage || ''].filter(Boolean).join(' ');
    const stageHtml = stageText
      ? `<div class="char-stage-divider"></div><div class="char-stage">${this._esc(stageText)}</div><div class="char-stage-divider"></div>`
      : '';

    // meta 行：性别·年龄·方向·势力（不含境界）
    const metaParts = [];
    const genderMap = { male: '男', female: '女' };
    if (c.gender && genderMap[c.gender]) metaParts.push(genderMap[c.gender]);
    if (c.age && c.age > 0) metaParts.push(this._esc(c.age) + '岁');
    if (c.extra?.cultivation_path) metaParts.push(this._esc(c.extra.cultivation_path));
    if (c.faction) metaParts.push(this._esc(c.faction));
    const metaHtml = metaParts.length > 0 ? `<div class="char-meta">${metaParts.join('<span class="dot">·</span>')}</div>` : '';

    const locationHtml = c.location ? `<div class="char-location">${this._esc(c.location)}</div>` : '';
    const tags = (c.tags || []).map(t => `<span class="char-tag">${this._esc(t)}</span>`).join('');
    const tagsHtml = tags ? `<div class="char-tags">${tags}</div>` : '';

    // 左侧：头像 + 名字/道号/meta/位置（水平 flex 布局）
    const headerLeft = `<div class="char-header-left">${avatarHtml}<div><div class="char-name">${this._esc(c.name)}</div>${daoNameHtml}${metaHtml}${locationHtml}</div></div>`;
    return `${stageHtml}<div class="char-header">${headerLeft}</div>${tagsHtml}`;
  }

  _renderVitals(c, schema) {
    let html = '<div class="section-card"><div class="section-title">生机</div>';
    const poolClasses = { hp: 'pool-hp', divine_sense: 'pool-mp', stamina: 'pool-sp' };
    for (const [key, def] of Object.entries(schema.attributes)) {
      if (def.combat_type !== 'pool') continue;
      const pair = def.pair || '';
      if (!pair.startsWith('max_')) continue;
      const maxKey = pair;
      const val = (c.attrs && c.attrs[key] !== undefined) ? c.attrs[key] : (def.default || 0);
      const maxDef = schema.attributes[maxKey];
      const maxVal = (c.attrs && c.attrs[maxKey] !== undefined) ? c.attrs[maxKey] : (maxDef ? maxDef.default : val);
      const pct = maxVal > 0 ? Math.min(val / maxVal * 100, 100) : 0;
      const cls = poolClasses[key] || 'pool-hp';
      html += `<div class="pool-row ${cls}"><span class="pool-label">${this._esc(def.label)}</span><div class="pool-track"><div class="pool-fill" style="width:${pct}%"></div></div><span class="pool-val">${val}/${maxVal}</span></div>`;
    }
    html += '</div>';
    return html;
  }

  _renderStats(c, schema) {
    let items = '';
    const rendered = {};
    for (const [key, def] of Object.entries(schema.attributes)) {
      if (rendered[key]) continue;
      if (def.combat_type === 'pool') continue;
      if (!def.innate) continue;
      if (def.pair && !def.pair.startsWith('max_')) rendered[def.pair] = true;
      const val = (c.attrs && c.attrs[key] !== undefined) ? c.attrs[key] : def.default;
      items += `<div class="stat-item"><span class="stat-label">${this._esc(def.label)}</span><span class="stat-val">${val}</span></div>`;
    }
    return items ? `<div class="section-card"><div class="section-title">先天根骨</div><div class="stat-grid">${items}</div></div>` : '';
  }

  _renderCultivation(c, schema) {
    const lines = [];
    const path = c.extra?.cultivation_path || '';
    const secondary = c.extra?.secondary_path || '';
    let pathText = path;
    if (secondary) pathText += ` · 辅修${secondary}`;
    if (pathText) lines.push({ key: '修炼方向', val: pathText });
    const roots = c.spiritual_roots || [];
    if (roots.length > 0) lines.push({ key: '灵根', val: roots.join(' · ') });
    if (schema && schema.attributes) {
      for (const [key, def] of Object.entries(schema.attributes)) {
        if (def.display_section !== 'cultivation') continue;
        const val = (c.attrs && c.attrs[key] !== undefined) ? c.attrs[key] : def.default;
        if (!val || val <= 0) continue;
        lines.push({ key: def.label, val: String(val) });
      }
      for (const [key, def] of Object.entries(schema.attributes)) {
        if (!def.cultivation_path_attr) continue;
        const val = (c.attrs && c.attrs[key] !== undefined) ? c.attrs[key] : def.default;
        if (val > 0) lines.push({ key: def.label, val: String(val) });
      }
    }
    if (lines.length === 0) return '';
    let html = '<div class="section-card"><div class="section-title">修行</div>';
    for (const line of lines) {
      const cls = line.highlight ? ' highlight' : '';
      html += `<div class="cult-line"><span class="cult-key">${this._esc(line.key)}</span><span class="cult-val${cls}">${this._esc(line.val)}</span></div>`;
    }
    html += '</div>';
    return html;
  }

  _renderEquipment(c, eqExpanded) {
    const slots = Object.keys(eqExpanded);
    if (slots.length === 0) return '<div class="section-card"><div class="section-title">装备</div><div class="text-block" style="color:var(--color-text-muted)">无装备</div></div>';
    let html = '<div class="section-card"><div class="section-title">装备</div>';
    for (const slot of slots) {
      html += `<div class="equip-item"><span class="equip-slot-label">${this._esc(slot)}</span><span class="equip-name">${this._esc(eqExpanded[slot])}</span></div>`;
    }
    html += '</div>';
    return html;
  }

  _renderAbilities(c, abilitiesData) {
    const abilities = c.abilities || [];
    let html = '<div class="section-card"><div class="section-title">技能</div><div class="skill-list">';
    if (abilities.length === 0) {
      html += '<span class="skill-chip" style="opacity:0.4">无技能</span>';
    } else {
      for (const abilityId of abilities) {
        const def = abilitiesData[abilityId];
        html += `<span class="skill-chip">${this._esc(def ? def.name : abilityId)}</span>`;
      }
    }
    html += '</div></div>';
    return html;
  }

  _renderTextSection(title, text) {
    const content = text
      ? `<div class="text-block">${this._esc(text)}</div>`
      : '<div class="text-block" style="color:var(--color-text-muted)">暂无</div>';
    return `<div class="section-card"><div class="section-title">${this._esc(title)}</div>${content}</div>`;
  }

  _renderAffairs(affairs) {
    if (!affairs || affairs.length === 0) return '';
    let html = '<div class="section-card"><div class="section-title">当前事务</div>';
    for (const item of affairs) {
      html += `<div class="affair-item">${this._esc(item)}</div>`;
    }
    html += '</div>';
    return html;
  }

  _renderMemories(memories) {
    let html = '<div class="section-card"><div class="section-title">记忆</div>';
    if (!memories) {
      html += '<div class="text-block" style="color:var(--color-text-muted)">暂无记忆</div>';
    } else {
      if (memories.shared_experiences) html += `<div class="memory-item"><div class="memory-label">共同经历</div>${this._esc(memories.shared_experiences)}</div>`;
      if (memories.personal_events) html += `<div class="memory-item"><div class="memory-label">个人大事</div>${this._esc(memories.personal_events)}</div>`;
      if (memories.opinions) html += `<div class="memory-item"><div class="memory-label">内心真实想法</div>${this._esc(memories.opinions)}</div>`;
    }
    html += '</div>';
    return html;
  }

  _renderRelationships(relationships) {
    let html = '<div class="section-card"><div class="section-title">人脉</div>';
    if (!relationships || relationships.length === 0) {
      html += '<div class="text-block" style="color:var(--color-text-muted)">暂无人脉</div>';
    } else {
      const attClass = { '友善': 'rel-friendly', '中立': 'rel-neutral', '冷淡': 'rel-cold', '敌对': 'rel-hostile', '无交集': 'rel-neutral' };
      for (const r of relationships) {
        const cls = attClass[r.attitude] || 'rel-neutral';
        html += `<div class="relation-item"><span class="relation-name">${this._esc(r.name)}</span><span class="relation-val ${cls}">${this._esc(r.attitude)}</span></div>`;
      }
    }
    html += '</div>';
    return html;
  }

  _renderLoot(lootTable) {
    if (!lootTable || lootTable.length === 0) return '';
    let html = '<div class="section-card"><div class="section-title">掉落</div>';
    for (const item of lootTable) {
      const name = item.name || item.id || '未知';
      const chance = item.chance ? ` (${item.chance}%)` : '';
      html += `<div class="affair-item">${this._esc(name)}${chance}</div>`;
    }
    html += '</div>';
    return html;
  }
}

customElements.define('character-panel', CharacterPanel);
