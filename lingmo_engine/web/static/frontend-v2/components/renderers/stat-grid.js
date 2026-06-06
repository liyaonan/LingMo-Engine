// renderers/stat-grid.js
import { matchFilter, buildSectionCard } from './common.js';

export function renderStatGrid(section, data, esc) {
  const { character: c, attrsSchema } = data;
  if (!attrsSchema || !attrsSchema.attributes) return '';

  const filter = section.filter || {};
  const rendered = {};
  let items = '';

  for (const [key, def] of Object.entries(attrsSchema.attributes)) {
    if (rendered[key]) continue;
    if (def.combat_type === 'pool') continue;
    if (!matchFilter(def, filter)) continue;
    if (def.pair && !def.pair.startsWith('max_')) rendered[def.pair] = true;

    const val = c.attrs?.[key] ?? def.default;
    items += `<div class="stat-item"><span class="stat-label">${esc(def.label)}</span><span class="stat-val">${val}</span></div>`;
  }

  if (!items) return '';
  return buildSectionCard(section.title, `<div class="stat-grid">${items}</div>`);
}
