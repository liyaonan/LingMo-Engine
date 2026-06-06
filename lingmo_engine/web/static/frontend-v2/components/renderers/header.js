// renderers/header.js
import { getNestedValue } from './common.js';
import { i18n } from '../../shared/i18n.js';

export function renderHeader(section, data, esc) {
  const { character: c, displayValues: dv } = data;
  const fields = section.fields || [];

  let avatarHtml;
  if (c.avatar) {
    avatarHtml = `<div class="char-avatar"><img src="${esc(c.avatar)}" alt="${esc(c.name)}" onerror="this.parentElement.textContent='${esc(c.name.charAt(0))}'"></div>`;
  } else {
    avatarHtml = `<div class="char-avatar">${esc(c.name ? c.name.charAt(0) : '?')}</div>`;
  }

  const metaParts = [];
  let daoNameHtml = '';
  let stageHtml = '';
  const tags = [];

  for (const field of fields) {
    const value = getFieldDisplayValue(field, c, dv);

    if (field.style === 'subtitle' && value) {
      daoNameHtml = `<div class="char-dao-name">「${esc(value)}」</div>`;
    } else if (field.style === 'stage') {
      // 境界独立渲染：合并境界+子境界
      const stageVal = value || '';
      const substageField = fields.find(f => f.merge_parent_stage);
      const substageVal = substageField ? getFieldDisplayValue(substageField, c, dv) : '';
      const fullStage = [stageVal, substageVal].filter(Boolean).join(' ');
      if (fullStage) {
        stageHtml = `<div class="char-stage-divider"></div><div class="char-stage">${esc(fullStage)}</div><div class="char-stage-divider"></div>`;
      }
    } else if (field.style === 'location') {
      // 位置单独渲染
      if (value) {
        metaParts.push(`<span class="char-location">${esc(value)}</span>`);
      }
    } else if (field.style === 'gender') {
      const genderMap = { male: i18n.t('male'), female: i18n.t('female') };
      const mapped = genderMap[value] || null;
      if (mapped) metaParts.push(esc(mapped));
    } else if (field.style === 'age') {
      if (value && value > 0) metaParts.push(esc(value) + i18n.t('years_old'));
    } else if (field.style === 'meta' && value) {
      metaParts.push(esc(value));
    } else if (field.style === 'tags') {
      const tagList = Array.isArray(value) ? value : [];
      for (const t of tagList) tags.push(t);
    }
  }

  const metaHtml = metaParts.length > 0
    ? `<div class="char-meta">${metaParts.join('<span class="dot">·</span>')}</div>`
    : '';
  const tagsHtml = tags.length > 0
    ? `<div class="char-tags">${tags.map(t => `<span class="char-tag">${esc(t)}</span>`).join('')}</div>`
    : '';

  return `<div class="char-header"><div class="char-header-left">${avatarHtml}<div><div class="char-name">${esc(c.name)}</div>${daoNameHtml}${metaHtml}</div></div></div>${stageHtml}${tagsHtml}`;
}

function getFieldDisplayValue(field, character, displayValues) {
  if (field.source === 'resolved') {
    return displayValues ? (displayValues[field.key] || null) : null;
  }
  if (field.field_path) {
    return getNestedValue(character, field.field_path);
  }
  return character[field.key] || (character.extra ? character.extra[field.key] : null) || null;
}
