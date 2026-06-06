// renderers/keyed-list.js
import { matchFilter, getNestedValue, buildSectionCard } from './common.js';

export function renderKeyedList(section, data, esc) {
  const { character: c, displayValues: dv, attrsSchema } = data;
  const lines = [];

  for (const field of (section.fields || [])) {
    let value;
    if (field.source === 'resolved') {
      value = dv ? dv[field.key] : null;
    } else if (field.field_path) {
      value = getNestedValue(c, field.field_path);
    } else {
      value = c[field.key] || (c.extra ? c.extra[field.key] : null);
    }
    if (value === null || value === undefined || value === '' || value === false) continue;
    if (Array.isArray(value) && value.length === 0) continue;

    const displayVal = Array.isArray(value) ? value.join(' · ') : String(value);

    if (field.merge_parent && lines.length > 0) {
      lines[lines.length - 1].val += ' ' + displayVal;
      continue;
    }
    lines.push({
      key: field.label || '',
      val: displayVal,
      highlight: field.highlight || false,
    });
  }

  const extraFilter = section.extra_attributes;
  if (extraFilter && attrsSchema && attrsSchema.attributes) {
    for (const [key, def] of Object.entries(attrsSchema.attributes)) {
      if (!matchFilter(def, extraFilter)) continue;
      const val = c.attrs?.[key] ?? def.default;
      if (!val || val <= 0) continue;
      lines.push({ key: def.label, val: String(val), highlight: false });
    }
  }

  const pathFilter = section.path_attributes;
  if (pathFilter && attrsSchema && attrsSchema.attributes) {
    const { show_nonzero_only, ...pathMatchFilter } = pathFilter;
    for (const [key, def] of Object.entries(attrsSchema.attributes)) {
      if (!matchFilter(def, pathMatchFilter)) continue;
      const val = c.attrs?.[key] ?? def.default;
      if (show_nonzero_only && (!val || val <= 0)) continue;
      lines.push({ key: def.label, val: String(val), highlight: false });
    }
  }

  if (lines.length === 0) return '';

  let innerHtml = '';
  for (const line of lines) {
    const cls = line.highlight ? ' highlight' : '';
    innerHtml += `<div class="cult-line"><span class="cult-key">${esc(line.key)}</span><span class="cult-val${cls}">${esc(line.val)}</span></div>`;
  }
  return buildSectionCard(section.title, innerHtml);
}
