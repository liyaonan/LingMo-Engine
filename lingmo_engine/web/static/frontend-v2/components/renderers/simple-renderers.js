// renderers/simple-renderers.js
import { getNestedValue, buildSectionCard } from './common.js';
import { i18n } from '../../shared/i18n.js';

export function renderText(section, data, esc) {
  const { character: c } = data;
  let value;
  if (section.field_path) {
    value = getNestedValue(c, section.field_path);
  } else if (section.key) {
    value = c[section.key] || (c.extra ? c.extra[section.key] : null);
  }
  if (!value) {
    return buildSectionCard(section.title, `<div class="text-block" style="color:var(--text-muted)">${i18n.t('no_data')}</div>`);
  }
  return buildSectionCard(section.title, `<div class="text-block">${esc(value)}</div>`);
}

export function renderList(section, data, esc) {
  const { character: c, equipment: eq } = data;

  if (section.data_source === 'equipment_expanded') {
    const slots = eq ? Object.keys(eq) : [];
    if (slots.length === 0) {
      return buildSectionCard(section.title, `<div class="text-block" style="color:var(--text-muted)">${i18n.t('no_equipment')}</div>`);
    }
    let inner = '';
    for (const slot of slots) {
      inner += `<div class="equip-item"><span class="equip-slot-label">${esc(slot)}</span><span class="equip-name">${esc(eq[slot])}</span></div>`;
    }
    return buildSectionCard(section.title, inner);
  }

  let items;
  if (section.field_path) {
    items = getNestedValue(c, section.field_path);
  } else if (section.key) {
    items = c[section.key] || (c.extra ? c.extra[section.key] : null);
  }
  if (!items || !Array.isArray(items) || items.length === 0) return '';
  let inner = '';
  for (const item of items) {
    inner += `<div class="affair-item">${esc(item)}</div>`;
  }
  return buildSectionCard(section.title, inner);
}

export function renderTagList(section, data, esc) {
  const { character: c, abilities } = data;
  const abilityIds = c.abilities || [];
  let inner = '<div class="skill-list">';
  if (abilityIds.length === 0) {
    inner += `<span class="skill-chip" style="opacity:0.4">${i18n.t('no_skills')}</span>`;
  } else {
    for (const id of abilityIds) {
      const def = abilities ? abilities[id] : null;
      inner += `<span class="skill-chip">${esc(def ? def.name : id)}</span>`;
    }
  }
  inner += '</div>';
  return buildSectionCard(section.title, inner);
}

export function renderMemoryList(section, data, esc) {
  const { memories } = data;
  let inner = '';
  if (!memories) {
    inner = `<div class="text-block" style="color:var(--text-muted)">${i18n.t('no_memories')}</div>`;
  } else {
    if (memories.shared_experiences) {
      inner += `<div class="memory-item"><div class="memory-label">${i18n.t('memory_shared_experiences')}</div>${esc(memories.shared_experiences)}</div>`;
    }
    if (memories.personal_events) {
      inner += `<div class="memory-item"><div class="memory-label">${i18n.t('memory_personal_events')}</div>${esc(memories.personal_events)}</div>`;
    }
    if (memories.opinions) {
      inner += `<div class="memory-item"><div class="memory-label">${i18n.t('memory_opinions')}</div>${esc(memories.opinions)}</div>`;
    }
  }
  return buildSectionCard(section.title, inner);
}

export function renderRelationshipList(section, data, esc) {
  const { relationships } = data;
  let inner = '';
  if (!relationships || relationships.length === 0) {
    inner = `<div class="text-block" style="color:var(--text-muted)">${i18n.t('no_relationships')}</div>`;
  } else {
    const labelClass = {
      '师徒': 'rel-mentor', '同门': 'rel-mentor', '传道': 'rel-mentor',
      '血亲': 'rel-mentor', '姻亲': 'rel-love', '道侣': 'rel-love',
      '好感': 'rel-love', '暗恋': 'rel-love', '心慕': 'rel-love', '挚爱': 'rel-love',
      '结义': 'rel-friend', '挚友': 'rel-friend', '故交': 'rel-friend',
      '主仆': 'rel-faction', '同僚': 'rel-faction', '盟友': 'rel-faction',
      '仇敌': 'rel-hostile', '宿敌': 'rel-hostile', '嫌隙': 'rel-hostile',
      '恩人': 'rel-grace', '受恩': 'rel-grace',
      '守护': 'rel-special', '监视': 'rel-special', '棋子': 'rel-special',
      '崇拜': 'rel-emotion', '敬畏': 'rel-emotion', '愧疚': 'rel-emotion',
    };
    for (const r of relationships) {
      const cls = labelClass[r.label] || 'rel-neutral';
      const descPart = r.desc ? `<span class="relation-desc">${esc(r.desc)}</span>` : '';
      inner += `<div class="relation-item"><span class="relation-name">${esc(r.name)}</span><span class="relation-val ${cls}">${esc(r.label)}</span>${descPart}</div>`;
    }
  }
  return buildSectionCard(section.title, inner);
}

export function renderLootList(section, data, esc) {
  const { character: c } = data;
  let lootTable;
  if (section.field_path) {
    lootTable = getNestedValue(c, section.field_path);
  } else if (section.key) {
    lootTable = c[section.key];
  }
  if (!lootTable || !Array.isArray(lootTable) || lootTable.length === 0) return '';
  let inner = '';
  for (const item of lootTable) {
    const name = item.name || item.id || i18n.t('unknown');
    const chance = item.chance ? ` (${item.chance}%)` : '';
    inner += `<div class="affair-item">${esc(name)}${chance}</div>`;
  }
  return buildSectionCard(section.title, inner);
}
