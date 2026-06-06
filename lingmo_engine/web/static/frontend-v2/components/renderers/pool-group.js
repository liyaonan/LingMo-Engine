// renderers/pool-group.js
import { buildSectionCard, lightenColor } from './common.js';

export function renderPoolGroup(section, data, esc) {
  const { character: c, attrsSchema } = data;
  if (!attrsSchema || !attrsSchema.attributes) return '';

  let rowsHtml = '';

  for (const [key, def] of Object.entries(attrsSchema.attributes)) {
    if (def.combat_type !== 'pool') continue;
    // 只从 current 端渲染（pair 指向 max 端，如 hp.pair = max_hp）
    if (!def.pair || !def.pair.startsWith('max_')) continue;
    const maxKey = def.pair;
    const maxDef = attrsSchema.attributes[maxKey];
    if (!maxDef) continue;

    const val = c.attrs?.[key] ?? def.default ?? 0;
    const maxVal = c.attrs?.[maxKey] ?? maxDef.default ?? val;
    const pct = maxVal > 0 ? Math.min(val / maxVal * 100, 100) : 0;
    const color = def.color || '#888888';
    const lightColor = lightenColor(color, 0.2);

    rowsHtml += `
      <div class="pool-row">
        <span class="pool-label" style="color:${color}">${esc(def.label)}</span>
        <div class="pool-track" style="box-shadow: inset 0 0 6px ${color}22">
          <div class="pool-fill" style="width:${pct}%; background: linear-gradient(90deg, ${color}, ${lightColor})"></div>
        </div>
        <span class="pool-val">${val}/${maxVal}</span>
      </div>`;
  }

  if (!rowsHtml) return '';
  return buildSectionCard(section.title, rowsHtml);
}
