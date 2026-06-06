import { ComponentBase } from '/static/frontend-v2/shared/component-base.js';
import { AppState } from '/static/frontend-v2/state/app-state.js';
import { WebSocketService } from '/static/frontend-v2/services/websocket.js';

const CSS = `
  :host { display: block; overflow-y: auto; height: 100%; scrollbar-width: none; }
  :host::-webkit-scrollbar { display: none; }

  .cult-header {
    display: flex; justify-content: space-between; align-items: center;
    padding: 12px 14px; border-bottom: 1px solid var(--color-border-light);
  }
  .cult-header-left { display: flex; align-items: center; gap: 10px; }
  .cult-header-icon {
    width: 36px; height: 36px; border-radius: var(--radius-md);
    background: var(--color-surface-alt); border: 1px solid var(--color-border-strong);
    display: flex; align-items: center; justify-content: center;
    color: var(--color-primary); font-size: calc(14px * var(--font-scale)); flex-shrink: 0;
  }
  .cult-title { font-family: var(--font-narrative); font-size: var(--font-size-narrative); color: var(--color-primary); font-weight: 600; }
  .cult-subtitle { font-size: var(--font-size-xs); color: var(--color-text-dim); }

  .panel-body { padding: 10px var(--space-xl) var(--space-xxl); }

  .section-card {
    background: var(--color-surface-alt); border: 1px solid var(--color-border);
    border-radius: var(--radius-md); padding: 10px var(--space-lg); margin-bottom: var(--space-lg);
  }
  .section-title {
    font-family: var(--font-narrative); font-size: var(--font-size-sm); font-weight: 600;
    color: var(--color-primary); letter-spacing: 2px; margin-bottom: var(--space-md);
    display: flex; align-items: center; gap: var(--space-sm);
  }
  .section-title::after {
    content: ''; flex: 1; height: 1px;
    background: linear-gradient(90deg, var(--color-border-strong), transparent);
  }

  .stat-row { display: flex; justify-content: space-between; margin: var(--space-xs) 0; }
  .stat-label { font-size: var(--font-size-xs); color: var(--color-text-dim); }
  .stat-value { font-size: var(--font-size-xs); color: var(--color-text); font-weight: 600; }

  .progress-bar {
    height: 5px; background: rgba(255,255,255,0.04);
    border-radius: var(--radius-sm); margin: var(--space-xs) 0; overflow: hidden;
  }
  .progress-fill {
    height: 100%; border-radius: var(--radius-sm); transition: width 0.3s ease;
  }

  .btn-row { display: flex; gap: var(--space-sm); margin: var(--space-sm) 0; flex-wrap: wrap; }
  .btn {
    padding: 5px 14px; border: 1px solid var(--color-border-light);
    background: rgba(201,169,97,0.1); color: var(--color-primary);
    border-radius: 4px; cursor: pointer; font-size: var(--font-size-xs);
    font-family: var(--font-ui); transition: all 0.2s;
  }
  .btn:hover { background: rgba(201,169,97,0.2); border-color: var(--color-primary); }
  .btn.active { background: var(--color-primary); color: var(--color-bg); border-color: var(--color-primary); }
  .btn:disabled { opacity: 0.4; cursor: not-allowed; }
  .btn-highlight {
    padding: 5px 14px; border: 1px solid rgba(255,152,0,0.4);
    background: rgba(255,152,0,0.15); color: #ff9800;
    border-radius: 4px; cursor: pointer; font-size: var(--font-size-xs);
    font-family: var(--font-ui); font-weight: 700; transition: all 0.2s;
  }
  .btn-highlight:hover { background: rgba(255,152,0,0.25); }

  .breakthrough-section { border: 1px solid rgba(255,152,0,0.3); border-radius: var(--radius-md); padding: var(--space-lg); }

  .success-rate { font-size: var(--font-size-xl); font-weight: 700; text-align: center; margin: var(--space-sm) 0; }
  .rate-high { color: var(--color-heal); }
  .rate-mid { color: #ff9800; }
  .rate-low { color: var(--color-danger); }

  .stone-input {
    width: 120px; padding: 4px 8px; background: var(--color-surface);
    border: 1px solid var(--color-border-light); border-radius: var(--radius-sm);
    color: var(--color-text); font-family: var(--font-ui); font-size: var(--font-size-xs);
    outline: none; -moz-appearance: textfield;
  }
  .stone-input:focus { border-color: var(--color-primary); }
  .stone-input::-webkit-inner-spin-button,
  .stone-input::-webkit-outer-spin-button { -webkit-appearance: none; margin: 0; }
  .stone-row { display: flex; gap: var(--space-sm); align-items: center; margin-top: var(--space-sm); }

  .result-msg {
    margin: var(--space-lg) 0 0; padding: 10px var(--space-lg);
    border-radius: var(--radius-md); font-size: var(--font-size-xs); line-height: 1.6;
  }
  .result-msg.success { background: rgba(90,158,143,0.1); color: var(--color-heal); border-left: 3px solid var(--color-heal); }
  .result-msg.failure { background: rgba(224,80,80,0.08); color: var(--color-danger); border-left: 3px solid var(--color-danger); }

  .cooldown-badge {
    display: inline-block; padding: 2px 8px;
    background: rgba(224,80,80,0.12); color: var(--color-danger);
    border-radius: var(--radius-sm); font-size: var(--font-size-2xs);
  }

  .cultivate-slider { width: 100%; margin: var(--space-sm) 0; accent-color: var(--color-primary); cursor: pointer; }
  .slider-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--space-xs); }
  .slider-duration { font-size: var(--font-size-lg); font-weight: 700; color: var(--color-primary); }
  .slider-marker { font-size: var(--font-size-2xs); color: var(--color-text-dim); }
  .slider-marker.over { color: var(--color-danger); }

  .preview-box {
    background: var(--color-surface); border-radius: var(--radius-md);
    padding: var(--space-sm) 10px; margin: var(--space-sm) 0;
    font-size: var(--font-size-xs); line-height: 1.8;
  }
  .preview-box .primary { color: var(--color-text); }
  .preview-box .secondary { color: var(--color-text-dim); font-size: var(--font-size-2xs); }

  .cultivate-actions { display: flex; gap: var(--space-sm); margin-top: var(--space-sm); }
  .cultivate-actions .btn { flex: 1; text-align: center; }

  .threshold-mark { position: relative; height: 4px; margin-top: -2px; }
  .threshold-mark-bar { position: absolute; height: 4px; background: #ff9800; border-radius: 2px; }
  .threshold-mark-label { position: absolute; top: 6px; font-size: var(--font-size-2xs); color: #ff9800; transform: translateX(-50%); white-space: nowrap; }

  .cultivation-log {
    margin-top: var(--space-md); max-height: 200px; overflow-y: auto;
    background: var(--color-surface); border-radius: var(--radius-md);
    padding: var(--space-sm) 10px; font-size: var(--font-size-2xs); line-height: 1.8;
    scrollbar-width: none;
  }
  .cultivation-log::-webkit-scrollbar { display: none; }
  .cultivation-log-entry { color: var(--color-text-dim); }
  .cultivation-log-entry.milestone { color: #ff9800; }
  .cultivation-log-entry.breakthrough { color: var(--color-heal); font-weight: 600; }
  .cultivation-log-entry.breakthrough.fail { color: var(--color-danger); }

  .finish-section { margin-top: var(--space-md); text-align: center; }

  .req-section {
    margin-bottom: var(--space-lg); padding: var(--space-lg);
    background: var(--color-surface-alt); border-radius: var(--radius-md);
    border: 1px solid var(--color-border);
  }
  .req-section .section-title { color: #ff9800; }
  .req-item { display: flex; align-items: center; gap: var(--space-sm); margin: var(--space-sm) 0; font-size: var(--font-size-xs); }
  .req-icon { font-size: var(--font-size-xs); width: 18px; text-align: center; }
  .req-icon.ok { color: var(--color-heal); }
  .req-icon.fail { color: var(--color-danger); }
  .req-bar {
    flex: 1; height: 6px; background: rgba(255,255,255,0.04);
    border-radius: var(--radius-sm); overflow: hidden;
  }
  .req-bar-fill { height: 100%; border-radius: var(--radius-sm); transition: width 0.3s; }
  .req-bar-fill.ok { background: var(--color-heal); }
  .req-bar-fill.fail { background: var(--color-danger); }
  .req-hint { font-size: var(--font-size-2xs); color: var(--color-text-muted); margin-top: var(--space-sm); line-height: 1.6; }
`;

const YEAR = 365;
const MONTH = 30;

/** 天数 → 友好文字（30天=1月, 365天=1年） */
function fmtDuration(days) {
  if (days < MONTH) return `${days}天`;
  if (days < YEAR) {
    const m = Math.floor(days / MONTH);
    const d = days % MONTH;
    return d > 0 ? `${m}个月${d}天` : `${m}个月`;
  }
  const y = Math.floor(days / YEAR);
  const rem = days % YEAR;
  if (rem === 0) return y >= 10000 ? `${(y / 10000).toFixed(1)}万年` : `${y}年`;
  const m = Math.floor(rem / MONTH);
  return m > 0 ? `${y}年${m}个月` : `${y}年${rem}天`;
}

/** 根据目标天数自适应计算滑条参数 */
function sliderScale(daysToThreshold, lifespanDays) {
  const target = Math.max(daysToThreshold, YEAR);
  const rawMax = Math.min(lifespanDays, target * 2);
  let step, max;
  if (target < YEAR) {
    step = 1; max = Math.min(rawMax, YEAR * 2);
  } else if (target < YEAR * 10) {
    step = 7; max = rawMax;
  } else if (target < YEAR * 100) {
    step = MONTH; max = rawMax;
  } else if (target < YEAR * 1000) {
    step = Math.floor(YEAR / 2); max = rawMax;
  } else {
    step = YEAR; max = rawMax;
  }
  // 确保步进对齐
  max = Math.max(step, Math.floor(max / step) * step);
  return { step, max };
}

export class CultivationPanel extends ComponentBase {
  static get observedState() { return ['cultivation']; }

  constructor() {
    super();
    this._stoneAmount = '';
    this._sliderDays = 0;
  }

  connectedCallback() {
    super.connectedCallback();
    WebSocketService.send({ type: 'cultivation_open' });
  }

  disconnectedCallback() {
    // 若有修炼日志，关闭面板等同于结束修炼，触发后端总结叙事
    const state = this._getCultivation();
    if (state && state.session_active
        && state.cultivation_log && state.cultivation_log.length > 0) {
      WebSocketService.send({ type: 'cultivation_finish' });
    }
    super.disconnectedCallback();
  }

  _onStateChanged(key, data) {
    this._renderAll();
  }

  _renderAll() {
    const state = this._getCultivation();
    if (!state) { this._renderHTML(`<style>${CSS}</style><p>加载中...</p>`); return; }

    const spPct = state.next_threshold > 0 ? Math.min(100, (state.spiritual_power / state.next_threshold) * 100) : 0;
    const lifePct = state.lifespan_total > 0 ? (state.lifespan_remaining / state.lifespan_total) * 100 : 0;

    let html = `<style>${CSS}</style>`;
    // 统一面板头部
    html += `<div class="cult-header"><div class="cult-header-left">`;
    html += `<div class="cult-header-icon">修</div>`;
    html += `<div><div class="cult-title">修炼</div>`;
    html += `<div class="cult-subtitle">${this._esc(state.stage_name)} · ${this._esc(state.substage_name || state.substage)}</div>`;
    html += `</div></div></div>`;
    html += '<div class="panel-body">';

    // A. 状态展示区
    html += `<div class="section-card">
      <div class="section-title">境界信息</div>
      ${state.path_name ? `<div class="stat-row"><span class="stat-label">主修</span><span class="stat-value">${this._esc(state.path_name)}</span></div>` : ''}
      <div class="stat-row"><span class="stat-label">灵力</span><span class="stat-value">${state.spiritual_power}${state.next_threshold > 0 ? ' / ' + state.next_threshold : ''}</span></div>
      <div class="progress-bar"><div class="progress-fill" style="width:${spPct}%"></div></div>
      <div class="stat-row"><span class="stat-label">寿元</span><span class="stat-value">${state.lifespan_remaining}年 (共${state.lifespan_total}年)</span></div>
      <div class="progress-bar"><div class="progress-fill" style="width:${lifePct}%;background:var(--color-heal)"></div></div>
      <div class="stat-row"><span class="stat-label">灵根</span><span class="stat-value">${this._esc(state.root_quality_name || state.root_quality)} ×${state.root_modifier}</span></div>
      <div class="stat-row"><span class="stat-label">灵气</span><span class="stat-value">${this._esc(state.qi_level_name)} (${state.qi_density}) ×${state.qi_modifier}</span></div>
      <div class="stat-row"><span class="stat-label">道韵</span><span class="stat-value">${state.dao_rhyme}${state.dao_rhyme_threshold > 0 ? ' / ' + state.dao_rhyme_threshold : ''}</span></div>
      ${state.breakthrough_cooldown > 0 ? `<div class="stat-row"><span class="stat-label">突破冷却</span><span class="cooldown-badge">${state.breakthrough_cooldown}天</span></div>` : ''}
    </div>`;

    // B. 突破条件面板（有下一境界但未就绪时显示）
    const _spGap = Math.max(0, state.next_threshold - state.spiritual_power);
    const _daysToTh = state.daily_meditation > 0 && _spGap > 0 ? Math.ceil(_spGap / state.daily_meditation) : 0;
    if (!state.breakthrough_ready && state.next_threshold > 0 && state.next_stage_name) {
      const spOk = state.spiritual_power >= state.next_threshold;
      const rhymeOk = state.dao_rhyme >= state.dao_rhyme_threshold;
      const cdActive = state.breakthrough_cooldown > 0;
      const spPct2 = Math.min(100, (state.spiritual_power / state.next_threshold) * 100);
      const rhPct = state.dao_rhyme_threshold > 0 ? Math.min(100, (state.dao_rhyme / state.dao_rhyme_threshold) * 100) : 100;

      html += `<div class="req-section">
        <div class="section-title">突破条件 → ${this._esc(state.next_stage_name)}</div>
        <div class="req-item">
          <span class="req-icon ${spOk ? 'ok' : 'fail'}">${spOk ? '✓' : '✗'}</span>
          <span>灵力</span>
          <span style="margin-left:auto;font-size:12px;color:${spOk ? 'var(--color-heal)' : 'var(--color-danger)'}">${state.spiritual_power} / ${state.next_threshold}</span>
        </div>
        <div class="req-bar"><div class="req-bar-fill ${spOk ? 'ok' : 'fail'}" style="width:${spPct2}%"></div></div>
        <div class="req-item" style="margin-top:8px">
          <span class="req-icon ${rhymeOk ? 'ok' : 'fail'}">${rhymeOk ? '✓' : '✗'}</span>
          <span>道韵</span>
          <span style="margin-left:auto;font-size:12px;color:${rhymeOk ? 'var(--color-heal)' : 'var(--color-danger)'}">${state.dao_rhyme} / ${state.dao_rhyme_threshold}</span>
        </div>
        <div class="req-bar"><div class="req-bar-fill ${rhymeOk ? 'ok' : 'fail'}" style="width:${rhPct}%"></div></div>
        ${cdActive ? `<div class="req-item" style="margin-top:6px"><span class="req-icon fail">✗</span><span>冷却中 ${state.breakthrough_cooldown}天</span></div>` : ''}
        <div class="req-hint">${!rhymeOk ? '道韵需通过战斗胜利、探索秘境、参悟功法获得，修炼不加道韵。' : ''}${!spOk && _spGap > 0 ? `灵力不足，继续修炼约 ${fmtDuration(_daysToTh)} 可达标。` : ''}</div>
      </div>`;
    }

    // C. 修炼操作区
    const lifespanDays = Math.max(1, state.lifespan_remaining * YEAR);
    const spGap = Math.max(0, state.next_threshold - state.spiritual_power);
    const daysToThreshold = state.daily_meditation > 0 && spGap > 0
      ? Math.ceil(spGap / state.daily_meditation) : 0;
    const { step, max: sliderMax } = sliderScale(daysToThreshold, lifespanDays);

    // 初始化滑条值（首次或重置时）
    if (!this._sliderDays || this._sliderDays > sliderMax || this._sliderDays < step) {
      this._sliderDays = Math.min(
        daysToThreshold > 0 ? Math.ceil(daysToThreshold / step) * step : step,
        sliderMax
      );
    }
    const days = this._sliderDays;
    const medSP = Math.round(state.daily_meditation * days * 100) / 100;

    // 突破所需标记位置
    const markPct = daysToThreshold > 0 && daysToThreshold <= sliderMax
      ? (daysToThreshold / sliderMax * 100).toFixed(1) : null;
    const markOver = daysToThreshold > lifespanDays;

    // 缓存修炼参数供滑条实时更新用
    this._cultivParams = { step, sliderMax, daily_meditation: state.daily_meditation };

    html += `<div class="section-card">
      <div class="section-title">修炼</div>
      <div class="stat-row"><span class="stat-label">打坐效率</span><span class="stat-value">${state.daily_meditation} 灵力/天</span></div>
      <div class="slider-header">
        <span class="slider-duration" data-live="duration">${fmtDuration(days)}</span>
        <span class="slider-marker">${daysToThreshold > 0 ? (markOver ? '<span class="over">突破所需超出寿元</span>' : `突破需 ${fmtDuration(daysToThreshold)}`) : ''}</span>
      </div>
      <input type="range" class="cultivate-slider" min="${step}" max="${sliderMax}" step="${step}" value="${days}" data-input="slider">
      ${markPct ? `<div class="threshold-mark"><div class="threshold-mark-bar" style="left:0;width:${markPct}%"></div><div class="threshold-mark-label" style="left:${markPct}%">突破</div></div>` : ''}
      <div class="preview-box">
        <div class="primary" data-live="med-preview">打坐：预计 +${medSP} 灵力</div>
      </div>
      <div class="cultivate-actions">
        <button class="btn" data-action="meditation" data-days="${days}" data-live="med-btn">打坐 ${fmtDuration(days)}</button>
      </div>
      <div style="margin-top:12px">
        <span class="stat-label">灵石转化 (${state.stone_rate}灵石=1灵力)</span>
        <div class="stone-row">
          <input class="stone-input" type="number" placeholder="灵石数量" value="${this._esc(this._stoneAmount)}" data-input="stones">
          <button class="btn" data-action="convert">转化</button>
        </div>
      </div>
    </div>`;

    // C. 突破界面区（仅灵力达标时显示）
    if (state.breakthrough_ready && state.next_threshold > 0) {
      const rates = state.breakthrough_rates || {};
      const currentRate = rates.natural;
      const rateLabel = currentRate != null ? `${Math.round(currentRate * 100)}%` : '计算中';
      const rateClass = currentRate >= 0.7 ? 'rate-high' : currentRate >= 0.4 ? 'rate-mid' : 'rate-low';

      html += `<div class="section-card breakthrough-section">
        <div class="section-title">★ 可尝试突破 → ${this._esc(state.next_stage_name || '下一境界')} ★</div>
        <div class="success-rate ${rateClass}">成功率：${rateLabel}</div>
        <div class="btn-row">
          <button class="btn-highlight" data-action="breakthrough">开始突破</button>
        </div>
      </div>`;
    }

    // D. 突破结果展示区
    if (state.action_result) {
      const ar = state.action_result;
      const isSuccess = ar.success;
      const cls = isSuccess ? 'success' : 'failure';
      const icon = isSuccess ? '✦' : '✗';
      let detail = '';
      if (ar.data) {
        if (isSuccess) {
          const parts = [];
          if (ar.data.new_stage_name) parts.push(`晋升 ${ar.data.new_stage_name}`);
          if (ar.data.is_great_success) parts.push('大成突破！');
          if (ar.data.lifespan_gain > 0) parts.push(`寿元 +${ar.data.lifespan_gain}年`);
          if (ar.data.roll != null) parts.push(`掷骰 ${ar.data.roll}`);
          if (ar.data.success_rate != null) parts.push(`成功率 ${Math.round(ar.data.success_rate * 100)}%`);
          detail = parts.join(' ｜ ');
        } else {
          const parts = [];
          if (ar.data.severity) parts.push(`${ar.data.severity}失败`);
          if (ar.data.sp_loss_ratio != null) parts.push(`灵力损失 ${Math.round(ar.data.sp_loss_ratio * 100)}%`);
          if (ar.data.cooldown_days) parts.push(`冷却 ${ar.data.cooldown_days} 天`);
          if (ar.data.roll != null) parts.push(`掷骰 ${ar.data.roll}`);
          if (ar.data.success_rate != null) parts.push(`成功率 ${Math.round(ar.data.success_rate * 100)}%`);
          detail = parts.join(' ｜ ');
        }
      }
      html += `<div class="result-msg ${cls}">
        <strong>${icon} ${this._esc(ar.log || (isSuccess ? '突破成功' : '突破失败'))}</strong>
        ${detail ? `<br><span style="font-size:12px;opacity:0.85">${detail}</span>` : ''}
      </div>`;
    }

    // E. 修炼日志区（仅会话中显示）
    if (state.session_active && state.cultivation_log && state.cultivation_log.length > 0) {
      html += `<div class="section-card">
        <div class="section-title">修炼日志</div>
        <div class="cultivation-log">`;
      for (const entry of state.cultivation_log) {
        let cls = 'cultivation-log-entry';
        if (entry.type === 'milestone') cls += ' milestone';
        else if (entry.type === 'breakthrough') cls += (entry.success ? ' breakthrough' : ' breakthrough fail');
        html += `<div class="${cls}">${this._esc(entry.text || '')}</div>`;
      }
      html += `</div></div>`;
    }

    // F. 结束修炼按钮（仅会话中显示）
    if (state.session_active) {
      html += `<div class="finish-section">
        <button class="btn-highlight" data-action="finish">结束修炼</button>
      </div>`;
    }

    html += '</div>'; // close panel-body
    this._renderHTML(html);
    this._bindEvents();
  }

  _bindEvents() {
    const root = this.shadowRoot;

    // 滑条拖动（只更新文字，不重建 DOM）
    const slider = root.querySelector('[data-input="slider"]');
    if (slider) {
      slider.addEventListener('input', () => {
        const days = parseInt(slider.value, 10);
        this._sliderDays = days;
        const p = this._cultivParams;
        if (!p) return;
        const dur = fmtDuration(days);
        const medSP = Math.round(p.daily_meditation * days * 100) / 100;
        const el = (sel) => root.querySelector(sel);
        const durationEl = el('[data-live="duration"]');
        if (durationEl) durationEl.textContent = dur;
        const medPreview = el('[data-live="med-preview"]');
        if (medPreview) medPreview.textContent = `打坐：预计 +${medSP} 灵力`;
        const medBtn = el('[data-live="med-btn"]');
        if (medBtn) { medBtn.dataset.days = days; medBtn.textContent = `打坐 ${dur}`; }
      });
    }

    // 操作按钮
    root.querySelectorAll('[data-action]').forEach(btn => {
      btn.addEventListener('click', () => {
        const action = btn.dataset.action;
        const days = parseInt(btn.dataset.days || this._sliderDays || '1', 10);
        if (action === 'meditation') {
          WebSocketService.send({ type: 'cultivation_action', action: 'start_meditation', days });
        } else if (action === 'convert') {
          const input = root.querySelector('[data-input="stones"]');
          const amount = parseInt(input?.value || '0', 10);
          if (amount > 0) {
            WebSocketService.send({ type: 'cultivation_action', action: 'convert_stones', amount });
          }
        } else if (action === 'breakthrough') {
          WebSocketService.send({ type: 'cultivation_action', action: 'attempt_breakthrough' });
        } else if (action === 'finish') {
          WebSocketService.send({ type: 'cultivation_finish' });
          AppState.setActivePlugin(null);
        }
      });
    });

    // 突破操作无需额外事件绑定（单按钮直发）

    const stoneInput = root.querySelector('[data-input="stones"]');
    if (stoneInput) {
      stoneInput.addEventListener('input', () => { this._stoneAmount = stoneInput.value; });
    }
  }

  _getCultivation() {
    if (typeof AppState !== 'undefined' && AppState.getCultivation) {
      return AppState.getCultivation();
    }
    return null;
  }
}

customElements.define('cultivation-panel', CultivationPanel);
