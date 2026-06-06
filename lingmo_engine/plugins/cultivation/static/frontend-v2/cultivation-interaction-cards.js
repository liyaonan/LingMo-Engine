// cultivation-interaction-cards.js
// 修炼插件交互卡 — 通过 EncounterCardFactory 注册
import { EncounterCardFactory } from '/static/frontend-v2/plugins/encounter-card-factory.js';
import { AppState } from '/static/frontend-v2/state/app-state.js';

const THEME_COLOR = 'rgba(201, 169, 97, 0.3)';

// ========== 修炼机缘卡片 ==========

EncounterCardFactory.register({
  cardType: 'cultivation_opportunity',
  wsStart: 'cultivation_start_session',
  title: '✦ 修炼机缘',
  titleUsed: '修炼已结束',
  borderColor: THEME_COLOR,
  css: `
    .cultivation-hint {
      font-family: var(--font-narrative); font-size: var(--font-size-base);
      color: var(--color-text, #e0e0e0); line-height: 1.6;
      margin-bottom: var(--space-sm);
    }
    .cultivation-info {
      font-family: var(--font-ui); font-size: var(--font-size-sm);
      color: var(--color-text-dim, #999);
    }
  `,

  extractData(msg) {
    if (msg.data && msg.data.cultivation_opportunity) return msg.data;
    if (msg.content_blocks) {
      for (const cb of msg.content_blocks) {
        if (cb.type === 'cultivation_opportunity' && cb.data) return cb.data;
      }
    }
    return null;
  },

  renderBody(data, el, h) {
    const hint = document.createElement('div');
    hint.className = 'cultivation-hint';
    hint.textContent = data.narrative_hint || '你发现了一处适合修炼的场所。';
    el.appendChild(hint);

    const info = document.createElement('div');
    info.className = 'cultivation-info';
    info.textContent = `境界：${data.stage_name || '未知'} ／ 灵力：${data.spiritual_power || 0}` +
      (data.next_threshold > 0 ? `／${data.next_threshold}` : '');
    el.appendChild(info);
  },

  extractParams(data) {
    return { qi_bonus: data.qi_bonus || 1.0, narrative_hint: data.narrative_hint || '' };
  },

  onClick(data, h) {
    h.sendMessage({
      type: 'cultivation_start_session',
      qi_bonus: data.qi_bonus || 1.0,
      narrative_hint: data.narrative_hint || '',
    });
    AppState.setActivePlugin('cultivation');
  },
});

// ========== 修炼回顾卡片 ==========

const CULTIVATION_REVIEW_RE = /^（修炼回顾\|(.+?)）([\s\S]*)$/;

export function parseCultivationReview(content) {
  if (!content) return null;
  const m = content.match(CULTIVATION_REVIEW_RE);
  if (!m) return null;
  return { result: m[1], text: m[2].trim() };
}

EncounterCardFactory.registerReview({
  cardType: 'cultivation_review',
  css: `
    .cultivation-review-card {
      background: var(--color-surface-alt);
      border: 1px solid rgba(201, 169, 97, 0.3);
      border-radius: var(--radius-md); padding: 10px 14px; cursor: pointer;
      transition: border-color var(--transition-fast), background var(--transition-fast);
      text-align: right;
    }
    .cultivation-review-card:hover {
      border-color: rgba(201, 169, 97, 0.7);
      background: rgba(201, 169, 97, 0.04);
    }
    .cultivation-review-card .encounter-card-name {
      color: var(--color-primary, #c9a961);
    }
  `,
  parseRegex: CULTIVATION_REVIEW_RE,
  getLabel(m) {
    if (m[1] === '突破成功') return '突破成功';
    if (m[1] === '突破失败') return '突破失败';
    return '修炼结束';
  },
  getModalTitle() { return '修炼感悟'; },
  themeColor: THEME_COLOR,
  cardClassName: 'cultivation-review-card',
});
