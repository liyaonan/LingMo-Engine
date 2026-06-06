// plugins/combat/combat-component.js
// 战斗 UI 主框架 — 四段式布局：敌方→友方→日志→操作
import { ComponentBase } from '/static/frontend-v2/shared/component-base.js';
import { AppState } from '/static/frontend-v2/state/app-state.js';
import { i18n } from '/static/frontend-v2/shared/i18n.js';
import { CombatAllies } from '/static/plugins/combat/frontend-v2/combat-allies.js';
import { CombatTargeting } from '/static/plugins/combat/frontend-v2/combat-targeting.js';
import { CombatPanels } from '/static/plugins/combat/frontend-v2/combat-panels.js';

const CSS = `
  :host {
    position: fixed; top: 0; bottom: 0; left: 50%;
    transform: translateX(-50%);
    width: 100%; max-width: 700px;
    background: var(--color-bg);
    z-index: 200;
    display: none;
    flex-direction: column;
    overflow: hidden;
  }
  :host(.active) { display: flex; }

  @media (min-width: 640px) {
    :host { border-left: 1px solid var(--color-border-light); border-right: 1px solid var(--color-border-light); }
  }

  /* 标题栏 */
  .combat-header {
    display: flex; justify-content: space-between; align-items: center; flex-shrink: 0;
    padding: 12px 14px;
    background: var(--color-surface);
    border-bottom: 1px solid var(--color-border-light);
  }
  .combat-header-left { display: flex; align-items: center; gap: 10px; }
  .combat-header-icon {
    width: 36px; height: 36px; border-radius: var(--radius-md);
    background: var(--color-surface-alt); border: 1px solid var(--color-border-strong);
    display: flex; align-items: center; justify-content: center;
    color: var(--color-primary); font-size: calc(14px * var(--font-scale)); flex-shrink: 0;
  }
  .combat-header-title { font-family: var(--font-narrative); font-size: var(--font-size-narrative); color: var(--color-primary); font-weight: 600; }
  .combat-header-sub { font-size: var(--font-size-xs); color: var(--color-text-dim); }
  .combat-header-tags { display: flex; gap: var(--space-xs); flex-wrap: wrap; }

  /* 区域标签 */
  .combat-section-label {
    font-family: 'Noto Serif SC', var(--font-narrative);
    font-size: var(--font-size-2xs); letter-spacing: 3px;
    color: rgba(201,169,97,0.5);
    padding: 4px 14px 2px; flex-shrink: 0;
    text-align: center;
  }

  /* ===== 敌方区域 ===== */
  .combat-enemies {
    display: flex; justify-content: center;
    gap: 7px; padding: 6px 10px 10px;
    overflow-x: auto; flex-shrink: 0;
    scrollbar-width: none; -ms-overflow-style: none;
  }
  .combat-enemies::-webkit-scrollbar { display: none; }

  .combat-enemy-card {
    width: 108px; flex-shrink: 0;
    background: var(--color-surface-alt);
    border-radius: var(--radius-md); border: 2px solid transparent;
    padding: 6px 8px; text-align: center;
    transition: border-color 0.2s;
    position: relative;
  }
  .combat-enemy-card.boss {
    width: 134px;
    border-color: rgba(155,89,182,0.45);
    box-shadow: 0 0 12px rgba(155,89,182,0.15), inset 0 0 15px rgba(155,89,182,0.05);
    position: relative;
  }
  .combat-enemy-card.boss::before {
    content: ''; position: absolute; top: -2px; left: 20%; right: 20%; height: 1px;
    background: linear-gradient(90deg, transparent, rgba(155,89,182,0.6), transparent);
  }
  .combat-enemy-card.defeated { opacity: 0.2; pointer-events: none; }

  /* 可选态金色脉冲 */
  @keyframes cardGlow {
    0%, 100% { box-shadow: 0 0 4px rgba(201,169,97,0.25); }
    50% { box-shadow: 0 0 10px rgba(201,169,97,0.55), 0 0 20px rgba(201,169,97,0.15); }
  }
  .combat-enemy-card.selectable {
    border-color: #c9a84c !important;
    background: rgba(201,169,97,0.06) !important;
    animation: cardGlow 1.0s ease-in-out infinite;
    cursor: pointer;
  }

  /* 敌人外框（全体敌人选择态） */
  .combat-enemy-cards-wrapper {
    border: 2px solid transparent; border-radius: 6px;
    padding: 4px 6px; display: flex; justify-content: center;
    gap: 7px; flex-wrap: wrap; width: 100%;
    position: relative; z-index: 50;
  }
  .combat-enemy-cards-wrapper.selectable {
    border-color: #c9a84c; background: rgba(201,169,97,0.04);
    animation: cardGlow 1.0s ease-in-out infinite;
    cursor: pointer;
  }

  /* 受击/治疗闪烁 */
  @keyframes damageFlash {
    0% { background-color: rgba(220,55,55,0.4); }
    35% { background-color: rgba(220,55,55,0.1); }
    100% { background-color: transparent; }
  }
  @keyframes healFlash {
    0% { background-color: rgba(80,200,130,0.3); }
    100% { background-color: transparent; }
  }
  .combat-enemy-card.damage-flash { animation: damageFlash 0.45s ease-out; }
  .combat-enemy-card.heal-flash { animation: healFlash 0.4s ease-out; }

  /* 行动回放 — 主动作者高亮 */
  @keyframes activeTurnPulse {
    0%, 100% { box-shadow: 0 0 6px rgba(201,169,97,0.3); }
    50% { box-shadow: 0 0 16px rgba(201,169,97,0.6), 0 0 30px rgba(201,169,97,0.2); }
  }
  .active-turn { animation: activeTurnPulse 0.6s ease-in-out infinite; }

  /* ===== 卡片共用样式（敌/友统一） ===== */
  .combat-card-name {
    font-size: var(--font-size-xs); font-weight: 600;
    color: var(--color-text); margin-bottom: 2px;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    max-width: 100%;
  }
  .combat-enemy-card.boss .combat-card-name {
    font-size: var(--font-size-md); color: var(--color-danger);
  }
  .combat-card-lvl {
    display: inline-block; font-size: var(--font-size-2xs); padding: 1px 4px;
    border-radius: 2px; margin-bottom: 4px;
  }

  /* HP 血量条 */
  .combat-hp-bar {
    height: 5px; background: rgba(255,255,255,0.05);
    border-radius: 2px; overflow: hidden; margin-bottom: 2px;
  }
  .combat-hp-fill {
    height: 100%; border-radius: 2px;
    background: var(--color-danger);
    transition: width 0.35s ease-out;
  }
  .combat-hp-text {
    font-size: var(--font-size-2xs); color: var(--color-text-muted); margin-bottom: 2px;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }

  /* 属性行 — 神识/体力迷你条（同行，无文字） */
  .combat-pool-row {
    display: flex; align-items: center; gap: 3px;
    margin-bottom: 2px; cursor: pointer; position: relative;
  }
  .combat-pool-track {
    flex: 1; height: 4px; background: rgba(255,255,255,0.05);
    border-radius: 2px; overflow: hidden; position: relative;
  }
  .combat-pool-fill {
    height: 100%; border-radius: 2px;
    transition: width 0.35s ease-out;
  }
  .combat-pool-sep { width: 2px; flex-shrink: 0; }
  /* 迷你条 tooltip */
  .combat-pool-tip {
    display: none; position: absolute; bottom: calc(100% + 4px);
    left: 50%; transform: translateX(-50%);
    background: rgba(20,18,16,0.95); border: 1px solid rgba(201,169,97,0.2);
    border-radius: 4px; padding: 3px 8px; white-space: nowrap;
    font-size: var(--font-size-2xs); z-index: 30;
    pointer-events: none;
    box-shadow: 0 2px 8px rgba(0,0,0,0.5);
  }
  .combat-pool-tip::after {
    content: ''; position: absolute; top: 100%; left: 50%; transform: translateX(-50%);
    border: 4px solid transparent; border-top-color: rgba(20,18,16,0.95);
  }
  .combat-pool-row:hover .combat-pool-tip { display: block; }

  /* 灵力行 */
  .combat-sp-row {
    font-size: var(--font-size-2xs); text-align: center;
    margin-bottom: 1px; white-space: nowrap;
  }

  /* 标签区（Buff） */
  .combat-tags {
    display: flex; align-items: flex-start; justify-content: center;
    gap: 3px; flex-wrap: wrap; min-height: 32px; margin-top: 3px;
  }
  .combat-tag.more { background: rgba(255,255,255,0.06); color: rgba(255,255,255,0.4); cursor: pointer; }
  .combat-tag.clickable { cursor: pointer; transition: background 0.15s; }
  .combat-tag.clickable:hover { filter: brightness(1.3); }
  .combat-tag {
    font-size: var(--font-size-2xs); padding: 1px 4px; border-radius: 2px;
    background: rgba(126,184,218,0.1); color: var(--color-mana);
  }
  .combat-tag.buff { background: rgba(201,169,97,0.1); color: var(--color-primary); }
  .combat-tag.debuff { background: rgba(224,80,80,0.08); color: var(--color-danger); }
  .combat-tag.status { background: rgba(126,184,218,0.08); color: rgba(126,184,218,0.7); }
  .combat-tag.more { background: rgba(255,255,255,0.06); color: rgba(255,255,255,0.4); }

  /* Buff 详情弹出面板（fixed定位，不受父级overflow影响） */
  .buff-detail-popup {
    min-width: 120px; max-width: 180px; padding: 6px 8px;
    background: var(--color-surface-alt); border: 1px solid rgba(201,169,97,0.25);
    border-radius: var(--radius-md); z-index: 500; pointer-events: auto;
    box-shadow: 0 4px 16px rgba(0,0,0,0.6);
  }
  .buff-detail-popup::after {
    content: ''; position: absolute; top: 100%; left: 50%; transform: translateX(-50%);
    border: 5px solid transparent; border-top-color: var(--color-surface-alt);
  }
  .buff-detail-popup.below::after {
    top: auto; bottom: 100%;
    border-top-color: transparent; border-bottom-color: var(--color-surface-alt);
  }
  .buff-detail-title {
    font-size: var(--font-size-2xs); color: rgba(201,169,97,0.7); text-align: center;
    padding-bottom: 4px; margin-bottom: 4px;
    border-bottom: 1px solid rgba(201,169,97,0.15);
  }
  .buff-detail-row {
    font-size: var(--font-size-2xs); padding: 2px 0; white-space: nowrap;
  }
  .buff-detail-row.buff { color: var(--color-primary); }
  .buff-detail-row.debuff { color: var(--color-danger); }
  .buff-detail-row.status { color: rgba(126,184,218,0.8); }
  .buff-detail-row.shield-row { color: rgba(52,152,219,0.9); }

  /* ===== 友方区域 ===== */
  .combat-allies {
    display: flex; flex-wrap: wrap; justify-content: center;
    gap: 7px; padding: 4px 10px 8px;
    flex-shrink: 0;
  }
  .combat-ally-card {
    width: 108px; flex-shrink: 0;
    background: var(--color-surface-alt);
    border-radius: var(--radius-md); border: 2px solid rgba(100,100,100,0.3);
    padding: 6px 8px; text-align: center;
    transition: border-color 0.2s;
    position: relative;
  }
  .combat-ally-card.selectable {
    border-color: #c9a84c !important;
    background: rgba(201,169,97,0.06) !important;
    animation: cardGlow 1.0s ease-in-out infinite;
    cursor: pointer;
  }
  .combat-ally-card.damage-flash { animation: damageFlash 0.45s ease-out; }
  .combat-ally-card.heal-flash { animation: healFlash 0.4s ease-out; }

  /* ===== 日志区 ===== */
  .combat-log {
    flex: 1; padding: 10px 14px;
    overflow-y: auto; overflow-x: hidden;
    font-size: var(--font-size-sm); color: var(--color-text-dim);
    line-height: 2.1;
    scrollbar-width: none; -ms-overflow-style: none;
    scroll-behavior: smooth;
  }
  .combat-log::-webkit-scrollbar { display: none; }

  /* ===== 操作栏 ===== */
  .combat-actions {
    display: flex; flex-wrap: wrap; justify-content: center;
    gap: 6px; padding: 10px 14px;
    border-top: 1px solid rgba(201,169,97,0.12);
    background: var(--color-surface);
    flex-shrink: 0;
  }
  .combat-action-btn {
    flex: 1; max-width: 140px; text-align: center;
    padding: 10px; font-size: var(--font-size-base);
    font-family: var(--font-ui); cursor: pointer;
    border-radius: 4px;
    border: 1px solid var(--color-border-light);
    background: rgba(201,169,97,0.04);
    color: var(--color-text);
    transition: all 0.2s;
  }
  .combat-action-btn:hover { color: var(--color-primary); border-color: var(--color-primary); }
  .combat-action-btn.active { color: var(--color-bg); background: var(--color-primary); border-color: var(--color-primary); font-weight: 600; }
  .combat-action-btn.flee { color: var(--color-text-dim); background: transparent; }
  .combat-action-btn.flee:hover { color: var(--color-text); }

  /* ===== 子面板（技能/物品选择） ===== */
  .combat-sub-panel {
    position: absolute; bottom: 0; left: 0; right: 0;
    max-height: 55%; display: none; flex-direction: column;
    background: var(--color-surface);
    border-top: 1px solid rgba(201,169,97,0.15);
    overflow: hidden;
    z-index: 10;
  }
  .combat-sub-panel.show {
    display: flex;
  }
  .combat-sub-panel.show.slide-in {
    animation: slideUp 0.25s ease-out;
  }
  @keyframes slideUp {
    from { transform: translateY(20px); opacity: 0; }
    to { transform: translateY(0); opacity: 1; }
  }

  .combat-sub-title {
    font-size: var(--font-size-xs); color: var(--color-text-muted);
    letter-spacing: 1px; padding: 10px 14px 6px;
    display: flex; justify-content: space-between; align-items: center;
  }
  .combat-sub-close {
    font-size: var(--font-size-lg); color: var(--color-text-dim); cursor: pointer;
    line-height: 1; padding: 2px 6px; border-radius: 3px;
    transition: color 0.15s, background 0.15s;
  }
  .combat-sub-close:hover { color: var(--color-text); background: rgba(201,169,97,0.1); }
  .combat-sub-scroll {
    flex: 1; padding: 4px 14px; overflow-y: auto;
    scrollbar-width: none; -ms-overflow-style: none;
  }
  .combat-sub-scroll::-webkit-scrollbar { display: none; }
  .combat-sub-list { display: flex; flex-direction: column; gap: 2px; }
  .combat-sub-item {
    display: flex; align-items: center;
    padding: 10px 12px;
    border-bottom: 1px solid rgba(201,169,97,0.04);
    cursor: pointer; transition: background 0.15s;
    font-size: var(--font-size-xs); gap: 10px;
  }
  .combat-sub-item:hover { background: rgba(201,169,97,0.03); }
  .combat-sub-item.selected { background: rgba(201,169,97,0.06); border: 1px solid rgba(201,169,97,0.2); border-radius: 4px; }
  .combat-sub-item.selected .combat-sub-item-name { color: var(--color-primary); }
  .combat-sub-item.disabled { opacity: 0.35; cursor: not-allowed; }
  .combat-sub-item-name {
    flex: 2; font-size: var(--font-size-md); color: var(--color-text); font-weight: 600;
    min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    display: flex; align-items: center; gap: 6px;
  }
  .combat-sub-rarity-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
  .combat-sub-item-desc { flex: 3; font-size: var(--font-size-xs); color: var(--color-text-dim); min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .combat-sub-item-cost { flex: 0 0 80px; font-size: var(--font-size-2xs); color: var(--color-text-dim); text-align: right; white-space: nowrap; }
  .combat-sub-item-qty { flex: 0 0 50px; font-size: var(--font-size-2xs); color: var(--color-text-dim); text-align: right; white-space: nowrap; }
  .combat-sub-expand {
    margin: 0 0 2px; padding: 10px 12px;
    background: var(--color-surface-alt);
    border-left: 2px solid var(--color-primary);
    border-radius: 0 3px 3px 0;
  }
  .combat-sub-expand .expand-effects { font-size: var(--font-size-xs); color: var(--color-mana); margin-bottom: 4px; line-height: 1.5; }
  .combat-sub-expand .expand-meta { font-size: var(--font-size-2xs); color: var(--color-text-muted); margin-bottom: 4px; }
  .combat-sub-expand .expand-desc { font-size: var(--font-size-2xs); color: var(--color-text-dim); line-height: 1.5; }
  .combat-sub-hint {
    flex-shrink: 0; text-align: center; font-size: var(--font-size-2xs);
    color: var(--color-text-muted); padding: 8px 14px 4px;
  }

  /* ===== 伤害数字：水墨飞溅 ===== */
  .dmg-num {
    position: absolute;
    font-family: 'Noto Serif SC', serif;
    font-weight: 900;
    font-size: calc(24px * var(--font-scale));
    pointer-events: none;
    z-index: 20;
    animation: inkSplash 1.2s ease-out forwards;
    white-space: nowrap;
  }
  .dmg-num.damage {
    color: #c43a3a;
    text-shadow: 0 0 6px rgba(196,58,58,0.4), 0 1px 3px rgba(0,0,0,0.9);
  }
  .dmg-num.heal {
    color: #5a9e8f;
    text-shadow: 0 0 6px rgba(90,158,143,0.4), 0 1px 3px rgba(0,0,0,0.9);
  }
  .dmg-num.crit {
    font-size: calc(20px * var(--font-scale));
    color: #ffd700;
    text-shadow: 0 0 10px rgba(255,215,0,0.5), 0 0 4px rgba(255,180,0,0.8), 0 2px 4px rgba(0,0,0,0.9);
  }
  .dmg-num.pursuit {
    font-size: var(--font-size-xl);
    color: #ff8c00;
    text-shadow: 0 0 8px rgba(255,140,0,0.5), 0 0 3px rgba(255,120,0,0.7), 0 2px 4px rgba(0,0,0,0.9);
  }
  .dmg-num.shield {
    font-size: calc(20px * var(--font-scale));
    color: #4a9eff;
    text-shadow: 0 0 6px rgba(74,158,255,0.4), 0 1px 3px rgba(0,0,0,0.9);
  }
  .dmg-num.buff {
    font-size: calc(16px * var(--font-scale));
    color: #c9a961;
    text-shadow: 0 0 4px rgba(201,169,97,0.4), 0 1px 3px rgba(0,0,0,0.9);
  }
  .dmg-num.debuff {
    font-size: calc(16px * var(--font-scale));
    color: #b066ff;
    text-shadow: 0 0 4px rgba(176,102,255,0.4), 0 1px 3px rgba(0,0,0,0.9);
  }
  .dmg-num.stun {
    font-size: var(--font-size-xl);
    color: #ffd700;
    text-shadow: 0 0 6px rgba(255,215,0,0.5), 0 1px 3px rgba(0,0,0,0.9);
  }
  .dmg-num.dot {
    font-size: calc(20px * var(--font-scale));
    color: #e07040;
    text-shadow: 0 0 6px rgba(224,112,64,0.5), 0 1px 3px rgba(0,0,0,0.9);
  }
  .dmg-num.dispel {
    font-size: calc(16px * var(--font-scale));
    color: #b066ff;
    text-shadow: 0 0 4px rgba(176,102,255,0.4), 0 1px 3px rgba(0,0,0,0.9);
  }
  .dmg-num::before {
    content: '';
    position: absolute;
    top: 50%; left: 50%;
    width: 50px; height: 50px;
    margin: -25px 0 0 -25px;
    border-radius: 50%;
    pointer-events: none;
    animation: inkBlob 0.7s ease-out forwards;
  }
  .dmg-num.damage::before {
    background: radial-gradient(circle, rgba(196,58,58,0.3) 0%, transparent 70%);
  }
  .dmg-num.heal::before {
    background: radial-gradient(circle, rgba(90,158,143,0.25) 0%, transparent 70%);
  }
  .dmg-num.crit::before {
    width: 70px; height: 70px; margin: -35px 0 0 -35px;
    background: radial-gradient(circle, rgba(255,215,0,0.35) 0%, transparent 70%);
    animation: inkBlobCrit 0.8s ease-out forwards;
  }
  @keyframes inkSplash {
    0%   { opacity: 0; transform: translateY(6px) scale(0.5); filter: blur(2px); }
    12%  { opacity: 1; transform: translateY(-4px) scale(1.1); filter: blur(0); }
    25%  { transform: translateY(-14px) scale(1); }
    100% { opacity: 0; transform: translateY(-48px) scale(0.75); filter: blur(1px); }
  }
  @keyframes inkBlob {
    0%   { transform: scale(0); opacity: 1; }
    35%  { transform: scale(1.1); opacity: 0.7; }
    100% { transform: scale(1.8); opacity: 0; }
  }
  @keyframes inkBlobCrit {
    0%   { transform: scale(0); opacity: 1; }
    30%  { transform: scale(1.4); opacity: 0.8; }
    100% { transform: scale(2.2); opacity: 0; }
  }

  /* ===== 结果覆盖层 ===== */
  .combat-result-overlay {
    position: fixed; inset: 0;
    background: rgba(0,0,0,0.85);
    display: flex; align-items: center; justify-content: center;
    z-index: 210;
  }
  .combat-result-overlay.hidden { display: none; }
  .combat-result-box {
    background: var(--color-surface);
    border: 1px solid var(--color-border-strong);
    border-radius: 6px; padding: 32px 40px;
    text-align: center; max-width: 400px; width: 90%;
  }
  .combat-result-title {
    font-family: var(--font-narrative); font-size: calc(22px * var(--font-scale));
    font-weight: 700; margin-bottom: 12px;
  }
  .combat-result-title.victory { color: var(--color-primary); }
  .combat-result-title.defeat { color: var(--color-danger); }
  .combat-result-detail { font-size: var(--font-size-md); color: var(--color-text-dim); margin-bottom: 20px; line-height: 1.8; }
  .combat-result-btn {
    padding: 10px 32px;
    background: rgba(201,169,97,0.12);
    border: 1px solid var(--color-primary);
    color: var(--color-primary); border-radius: 4px;
    cursor: pointer; font-size: var(--font-size-base);
    font-family: var(--font-ui); transition: all 0.2s;
  }
  .combat-result-btn:hover { background: var(--color-primary); color: var(--color-bg); }
`;

export class CombatUI extends ComponentBase {
  static get observedState() { return ['combat']; }

  constructor() {
    super();
    this._targeter = CombatTargeting.create();
    this._prevEnemyState = null;
    this._prevAllyState = null;
    this._replayConsumed = false;
    this._prevSubPanelOpen = false;
    this._hpPoolLabel = '生命';
    this._hpPoolColor = 'var(--color-danger)';
    this._disableActions = false;
    this._resultTimer = null;
  }

  connectedCallback() {
    super.connectedCallback();
    // 全局事件：结果弹窗"继续"按钮
    this.shadowRoot.addEventListener('click', (e) => {
      if (e.target.classList.contains('combat-result-btn')) {
        this._closeResult();
      }
    });
    // 全局点击关闭 buff 弹窗（注册一次，不随渲染重复绑定）
    this._docClickListener = (e) => {
      if (!e.target.closest('.buff-detail-popup') && !e.target.closest('.combat-tag.clickable') && !e.target.closest('.combat-tag.more')) {
        this._closeBuffDetail();
      }
    };
    document.addEventListener('click', this._docClickListener);
  }

  _onStateChanged(key, data) {
    const cmb = AppState.getCombat();
    if (!cmb || !cmb.active) {
      this.classList.remove('active');
      this._removeBlur();
      return;
    }
    this.classList.add('active');
    this._addBlur();
    this._cachePoolInfo(cmb);

    // 新状态到达，重置弹字消费标记
    this._replayConsumed = false;

    this._renderAll();

    // 检查是否战斗结束（phase 为 victory/defeat/flee）
    if (cmb.phase === 'victory' || cmb.phase === 'defeat' || cmb.phase === 'flee') {
      this._disableActions = true;
      // 等最后一击的伤害动画(1.2s)和弹字(敌方延迟0.8s+1.2s)播完再出结算
      if (this._resultTimer) clearTimeout(this._resultTimer);
      this._resultTimer = setTimeout(() => {
        this._resultTimer = null;
        this.showResult(cmb.phase, cmb.rewards);
      }, 2200);
    }
  }

  _addBlur() {
    const shell = document.querySelector('app-shell');
    if (shell && !shell.classList.contains('combat-blur')) {
      shell.classList.add('combat-blur');
    }
  }

  _removeBlur() {
    const shell = document.querySelector('app-shell');
    if (shell) shell.classList.remove('combat-blur');
  }

  _cachePoolInfo(cmb) {
    const pools = cmb.poolAttrs || [];
    for (const pool of pools) {
      if (pool.name === 'vitality') {
        this._hpPoolLabel = pool.label || '生命';
        this._hpPoolColor = pool.color || 'var(--color-danger)';
        return;
      }
    }
  }

  _renderAll() {
    const cmb = AppState.getCombat();
    if (!cmb) return;

    // 保存旧 HP 用于动画比较
    const prevEnemyState = this._prevEnemyState;
    const prevAllyState = this._prevAllyState;

    const phaseLabels = { player_turn: '玩家行动', enemy_turn: '敌人行动中...', resolving: '结算中...' };

    // 判断子面板是否展开
    const showSubPanel = this._targeter.selectedAction === 'ability' || this._targeter.selectedAction === 'item';

    this._renderHTML(`
      <style>${CSS}</style>
      <div class="combat-header">
        <div class="combat-header-left">
          <div class="combat-header-icon">⚔</div>
          <div>
            <span class="combat-header-title">战斗</span>
            <span class="combat-header-sub">回合 ${cmb.round} · ${phaseLabels[cmb.phase] || cmb.phase}</span>
          </div>
        </div>
      </div>
      <div class="combat-section-label">敌 方</div>
      <div class="combat-enemies">
        ${this._renderEnemies(cmb)}
      </div>
      <div class="combat-section-label">我 方</div>
      ${CombatAllies.render(cmb, this._esc.bind(this), (buff) => this._buffTagText(buff, cmb.poolAttrs || [], cmb.attr_labels || {}), this._targeter, prevAllyState)}
      <div class="combat-log">
        ${this._renderLogContent(cmb)}
      </div>
      ${this._renderActions(cmb)}
      ${this._renderSubPanel(cmb, showSubPanel)}
      ${this._renderResultOverlay()}
    `);
    this._animateHpChanges(cmb, prevEnemyState, prevAllyState);
    this._spawnPopups(cmb);
    this._bindEvents();

    // 自动滚动日志到底部
    const logEl = this.shadowRoot.querySelector('.combat-log');
    if (logEl) logEl.scrollTop = logEl.scrollHeight;
  }

  /** 渲染日志内容（子面板展开时隐藏） */
  _renderLogContent(cmb) {
    const logs = (cmb.log || []).slice(-20);
    return logs.map(l => '<div class="log-entry">' + this._esc(l) + '</div>').join('');
  }

  /** 渲染子面板（绝对定位覆盖日志区） */
  _renderSubPanel(cmb, showSubPanel) {
    if (!showSubPanel) {
      this._prevSubPanelOpen = false;
      return '';
    }

    // 仅首次展开时播放滑入动画
    const animateCls = this._prevSubPanelOpen ? '' : ' slide-in';
    this._prevSubPanelOpen = true;

    let subHtml = '';
    if (this._targeter.selectedAction === 'ability') {
      subHtml = CombatPanels.renderAbilityList(
        cmb, this._targeter, this._esc.bind(this),
        (rarityInt) => this._getRarityInfo(rarityInt)
      );
    } else if (this._targeter.selectedAction === 'item') {
      subHtml = CombatPanels.renderItemList(cmb, this._targeter, this._esc.bind(this));
    }

    return '<div class="combat-sub-panel show' + animateCls + '">' + subHtml + '</div>';
  }

  /** 切换 Buff 详情弹出面板 */
  _toggleBuffDetail(unitName, tagsEl, sourceKey) {
    this._closeBuffDetail();
    const card = tagsEl.closest('[data-unit-name]');
    if (!card) return;
    const popup = this._buildBuffPopup(unitName, sourceKey);
    if (!popup) return;
    const isEnemy = card.classList.contains('combat-enemy-card');
    // 挂载到 body，使用 fixed 定位彻底脱离 shadow DOM 的 overflow 裁剪
    popup.style.position = 'fixed';
    popup.style.zIndex = '9999';
    document.body.appendChild(popup);
    // 先渲染获取尺寸，再精确定位
    const cardRect = card.getBoundingClientRect();
    const popRect = popup.getBoundingClientRect();
    const cx = cardRect.left + cardRect.width / 2 - popRect.width / 2;
    if (isEnemy) {
      popup.style.top = (cardRect.bottom + 6) + 'px';
    } else {
      popup.style.top = (cardRect.top - popRect.height - 6) + 'px';
    }
    popup.style.left = Math.max(4, Math.min(cx, window.innerWidth - popRect.width - 4)) + 'px';
  }

  _closeBuffDetail() {
    const old = document.querySelector('.buff-detail-popup');
    if (old) old.remove();
  }

  /** 构建 Buff 详情弹出面板（支持按分组或全部汇总） */
  _buildBuffPopup(unitName, sourceKey) {
    const cmb = AppState.getCombat();
    if (!cmb) return null;
    const units = [];
    if (cmb.player) units.push(cmb.player);
    if (cmb.allies) units.push(...cmb.allies);
    if (cmb.enemies) units.push(...cmb.enemies);
    const unit = units.find(u => u.name === unitName);
    let buffs = unit && unit.buffs;
    if (!buffs || buffs.length === 0) return null;

    // 按 sourceKey 筛选
    if (sourceKey) {
      buffs = buffs.filter(b => (b.source_key || '') === sourceKey);
      if (buffs.length === 0) return null;
    }

    const labels = cmb.attr_labels || {};
    const statusMap = { frozen: '冻结', stunned: '眩晕', poisoned: '中毒', burned: '灼烧' };

    // 分组弹出：显示技能名下的每个子效果
    if (sourceKey) {
      const groupName = buffs[0].source_name || '';
      let html = '<div class="buff-detail-popup" style="min-width:120px;max-width:180px;padding:6px 8px;'
        + 'background:var(--color-surface-alt);border:1px solid rgba(201,169,97,0.25);border-radius:6px;'
        + 'box-shadow:0 4px 16px rgba(0,0,0,0.6);font-family:inherit;">';
      if (groupName) {
        html += '<div style="font-size:var(--font-size-2xs);color:rgba(201,169,97,0.9);text-align:center;padding-bottom:4px;'
          + 'margin-bottom:4px;border-bottom:1px solid rgba(201,169,97,0.15);">' + this._esc(groupName) + '</div>';
      }
      for (const b of buffs) {
        const line = this._buffEffectLine(b, labels, statusMap);
        if (line) html += line;
      }
      html += '</div>';
      const div = document.createElement('div');
      div.innerHTML = html;
      return div.firstElementChild;
    }

    // 全部汇总弹出（点击 +N 时）
    const statMods = {};
    const statuses = [];
    const shields = [];
    let buffCount = 0, debuffCount = 0;
    for (const b of buffs) {
      if (b.effect_type === 'shield') {
        shields.push(b);
      } else if (b.status) {
        statuses.push({ name: b.name || statusMap[b.status] || b.status, remaining: b.remaining });
      } else if (b.stat) {
        if (!statMods[b.stat]) statMods[b.stat] = 0;
        statMods[b.stat] += (b.modifier || 0);
      }
      if ((b.modifier || 0) > 0) buffCount++;
      else if ((b.modifier || 0) < 0) debuffCount++;
    }

    const parts = [];
    if (buffCount > 0) parts.push(buffCount + '增益');
    if (debuffCount > 0) parts.push(debuffCount + '减益');
    const titleText = parts.length > 0 ? parts.join(' / ') : '效果总览';
    let html = '<div class="buff-detail-popup" style="min-width:120px;max-width:180px;padding:6px 8px;'
      + 'background:rgba(20,18,16,0.96);border:1px solid rgba(201,169,97,0.25);border-radius:5px;'
      + 'box-shadow:0 4px 16px rgba(0,0,0,0.6);font-family:inherit;">'
      + '<div style="font-size:var(--font-size-2xs);color:rgba(201,169,97,0.7);text-align:center;padding-bottom:4px;'
      + 'margin-bottom:4px;border-bottom:1px solid rgba(201,169,97,0.15);">' + titleText + '</div>';
    for (const [stat, mod] of Object.entries(statMods)) {
      if (mod === 0) continue;
      const label = labels[stat] || stat;
      const sign = mod > 0 ? '+' : '';
      const pct = (mod * 100).toFixed(0);
      const color = mod > 0 ? 'var(--color-primary,#c9a961)' : 'var(--color-danger,#e05050)';
      html += '<div style="font-size:var(--font-size-2xs);padding:2px 0;white-space:nowrap;color:' + color + ';">'
        + label + ' ' + sign + pct + '%</div>';
    }
    for (const s of statuses) {
      html += '<div style="font-size:var(--font-size-2xs);padding:2px 0;white-space:nowrap;color:rgba(126,184,218,0.8);">'
        + s.name + ' (' + s.remaining + '回合)</div>';
    }
    for (const s of shields) {
      html += '<div style="font-size:var(--font-size-2xs);padding:2px 0;white-space:nowrap;color:rgba(52,152,219,0.9);">'
        + '护盾 (' + s.remaining + '回合)</div>';
    }
    html += '</div>';
    const div = document.createElement('div');
    div.innerHTML = html;
    return div.firstElementChild;
  }

  /** 单个 buff 效果的弹出面板行 */
  _buffEffectLine(buff, labels, statusMap) {
    if (buff.effect_type === 'shield') {
      return '<div style="font-size:var(--font-size-2xs);padding:2px 0;white-space:nowrap;color:rgba(52,152,219,0.9);">'
        + '护盾 (' + buff.remaining + '回合)</div>';
    }
    if (buff.status) {
      const name = buff.name || statusMap[buff.status] || buff.status;
      return '<div style="font-size:var(--font-size-2xs);padding:2px 0;white-space:nowrap;color:rgba(126,184,218,0.8);">'
        + this._esc(name) + ' (' + buff.remaining + '回合)</div>';
    }
    if (buff.stat && buff.modifier !== undefined && buff.modifier !== 0) {
      const label = labels[buff.stat] || buff.stat;
      const sign = buff.modifier > 0 ? '+' : '';
      const pct = Math.abs(buff.modifier * 100).toFixed(0);
      const color = buff.modifier > 0 ? 'var(--color-primary,#c9a961)' : 'var(--color-danger,#e05050)';
      return '<div style="font-size:var(--font-size-2xs);padding:2px 0;white-space:nowrap;color:' + color + ';">'
        + this._esc(label) + ' ' + sign + pct + '%</div>';
    }
    // dot / fixed_dot
    const dotTypes = { dot: '持续伤害', fixed_dot: '持续真实伤害' };
    if (dotTypes[buff.effect_type]) {
      let dotText = dotTypes[buff.effect_type];
      if (buff.value) dotText += ' ' + CombatAllies.fmtNum(Math.abs(buff.value)) + '/回合';
      return '<div style="font-size:var(--font-size-2xs);padding:2px 0;white-space:nowrap;color:rgba(224,112,64,0.9);">'
        + dotText + ' (' + buff.remaining + '回合)</div>';
    }
    return '';
  }

  _getRarityInfo(rarityInt) {
    const cmb = AppState.getCombat();
    return CombatPanels.getRarityInfo(rarityInt, cmb ? cmb.ability_rarities : {});
  }

  /** 将 buff 列表按 source_key 分组 */
  _groupBuffs(buffs) {
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
  }

  /** 分组标签 CSS 类 */
  _groupTagClass(group) {
    let sum = 0;
    for (const b of group.buffs) sum += (b.modifier || 0);
    let cls = 'combat-tag clickable';
    if (sum > 0) cls += ' buff';
    else if (sum < 0) cls += ' debuff';
    else cls += ' status';
    return cls;
  }

  /** Buff 标签 CSS 类 */
  _buffTagClass(buff) {
    let cls = 'combat-tag';
    if (buff.modifier > 0) cls += ' buff';
    else if (buff.modifier < 0) cls += ' debuff';
    else cls += ' status';
    return cls;
  }

  /** Buff 标签文本 — 翻译 status 名、显示 stat 修正值 */
  _buffTagText(buff, pools, attrLabels) {
    const statusMap = { frozen: '冻结', stunned: '眩晕', poisoned: '中毒', burned: '灼烧' };
    const effectTypeMap = { fixed_dot: '持续伤害', dot: '持续伤害', shield: '护盾', lifesteal: '吸血', dispel: '驱散' };
    // buff.name 优先
    if (buff.name) return buff.name;
    // status → 中文
    if (buff.status) return statusMap[buff.status] || buff.status;
    // stat modifier → 显示属性+数值
    if (buff.stat && buff.modifier !== undefined && buff.modifier !== 0) {
      const label = pools.find(p => p.name === buff.stat)?.label
        || (attrLabels && attrLabels[buff.stat]) || buff.stat;
      const sign = buff.modifier > 0 ? '+' : '';
      const pct = Math.abs(buff.modifier * 100).toFixed(0);
      return label + ' ' + sign + pct + '%';
    }
    return effectTypeMap[buff.effect_type] || buff.effect_type || '';
  }

  _renderEnemies(cmb) {
    const enemies = cmb.enemies || [];
    const levelColors = cmb.level_colors || [];

    const self = this;
    let cardsHtml = enemies.map(function(enemy, i) {
      const isDefeated = enemy.vitality <= 0;
      const isSingleSelect = self._targeter.targetingMode && self._targeter.targetingType === 'single_enemy' && !isDefeated;
      const isSelected = self._targeter.selectedTargetIndex === i;

      let cardClass = 'combat-enemy-card';
      if (isSelected) cardClass += ' target';
      if (isDefeated) cardClass += ' defeated';
      if (isSingleSelect) cardClass += ' selectable';

      // Level 配色边框
      const level = enemy.level || 1;
      const borderColor = CombatAllies.getLevelColor(level, levelColors);

      const hpCur = enemy.vitality != null ? enemy.vitality : 0;
      const hpMax = enemy.max_vitality || 1;
      const hpPct = Math.round(hpMax > 0 ? (hpCur / hpMax * 100) : 0);

      let html = '<div class="' + cardClass + '" data-enemy-index="' + i + '" data-unit-name="' + self._esc(enemy.name) + '" style="border-color:' + borderColor + '">';
      html += '<div class="combat-card-name">' + self._esc(enemy.name) + '</div>';
      html += '<div class="combat-card-lvl" style="background:' + borderColor + '14;color:' + borderColor + '99">Lv.' + level + '</div>';

      // HP 血量条
      html += '<div class="combat-hp-bar"><div class="combat-hp-fill" style="width:' + hpPct + '%"></div></div>';
      html += '<div class="combat-hp-text">' + CombatAllies.fmtNum(hpCur) + ' / ' + CombatAllies.fmtNum(hpMax) + '</div>';

      // 神识/体力 — 同行迷你条（无文字），点击显示详情
      const attrs = enemy.attrs || {};
      const poolParts = [];
      const tipParts = [];
      if (attrs.divine_sense != null) {
        const maxDs = attrs.max_divine_sense || 1;
        const pct = Math.round(attrs.divine_sense / maxDs * 100);
        poolParts.push('<div class="combat-pool-track"><div class="combat-pool-fill" style="width:' + pct + '%;background:rgba(142,68,173,0.5)"></div></div>');
        tipParts.push('<span style="color:rgba(142,68,173,0.7)">神识 ' + CombatAllies.fmtNum(attrs.divine_sense) + '/' + CombatAllies.fmtNum(maxDs) + '</span>');
      }
      if (attrs.stamina != null) {
        const maxSt = attrs.max_stamina || 1;
        const pct = Math.round(attrs.stamina / maxSt * 100);
        poolParts.push('<div class="combat-pool-track"><div class="combat-pool-fill" style="width:' + pct + '%;background:rgba(39,174,96,0.5)"></div></div>');
        tipParts.push('<span style="color:rgba(39,174,96,0.7)">体力 ' + CombatAllies.fmtNum(attrs.stamina) + '/' + CombatAllies.fmtNum(maxSt) + '</span>');
      }
      if (poolParts.length > 0) {
        const sep = poolParts.length > 1 ? '<div class="combat-pool-sep"></div>' : '';
        html += '<div class="combat-pool-row">'
          + poolParts.join(sep)
          + '<div class="combat-pool-tip">' + tipParts.join('<br/>') + '</div>'
          + '</div>';
      }
      if (attrs.spiritual_power != null) {
        html += '<div class="combat-sp-row" style="color:rgba(52,152,219,0.6)">灵力 ' + CombatAllies.fmtNum(attrs.spiritual_power) + '</div>';
      }

      // 标签区（按技能分组，每组一个标签，点击展开详情）
      const buffs = enemy.buffs || [];
      const groups = self._groupBuffs(buffs);
      const MAX_VISIBLE = 3;
      html += '<div class="combat-tags">';
      if (groups.length > 0) {
        const visGroups = groups.slice(-MAX_VISIBLE);
        const hiddenCount = groups.length - visGroups.length;
        for (const g of visGroups) {
          if (g.key) {
            const tagClass = self._groupTagClass(g);
            const tagText = g.name || self._buffTagText(g.buffs[0], cmb.poolAttrs || [], cmb.attr_labels || {});
            html += '<span class="' + tagClass + '" data-source-key="' + self._esc(g.key) + '">' + self._esc(tagText) + '</span>';
          } else {
            for (const b of g.buffs) {
              const tagClass = self._buffTagClass(b);
              const tagText = self._buffTagText(b, cmb.poolAttrs || [], cmb.attr_labels || {});
              html += '<span class="' + tagClass + '">' + self._esc(tagText) + '</span>';
            }
          }
        }
        if (hiddenCount > 0) {
          html += '<span class="combat-tag more">+' + hiddenCount + '</span>';
        }
      }
      html += '</div>';
      html += '</div>';
      return html;
    }).join('');

    const isAllEnemyMode = this._targeter.targetingMode && this._targeter.targetingType === 'all_enemy';
    const wrapperClass = 'combat-enemy-cards-wrapper' + (isAllEnemyMode ? ' selectable' : '');

    // 保存当前HP用于下次比较
    this._prevEnemyState = enemies.map(function(e) {
      return { name: e.name, hp: e.vitality || 0, maxHp: e.max_vitality || 1 };
    });

    // 保存友方 HP 快照
    const allies = cmb.allies || [];
    const player = cmb.player;
    const units = player ? [player, ...allies] : [...allies];
    this._prevAllyState = units.map(function(u) {
      return { name: u.name, hp: u.vitality || 0, maxHp: u.max_vitality || 1 };
    });

    return '<div class="' + wrapperClass + '">' + cardsHtml + '</div>';
  }

  /** 受击动画：敌方立即（被友方攻击），友方延迟（被敌方攻击） */
  _animateHpChanges(cmb, prevEnemyState, prevAllyState) {
    // 敌方立即动画（友方攻击造成）
    const enemies = cmb.enemies || [];
    if (prevEnemyState && prevEnemyState.length > 0) {
      const cards = this.shadowRoot.querySelectorAll('.combat-enemy-card');
      for (let i = 0; i < cards.length && i < enemies.length; i++) {
        const prev = prevEnemyState[i];
        const cur = enemies[i];
        if (!prev || prev.hp === cur.vitality) continue;
        this._animateCardHp(cards[i], prev.hp, prev.maxHp, cur.vitality, cur.max_vitality || 1);
      }
    }

    // 友方动画：治疗（HP上升）立即，伤害（HP下降）延迟800ms与敌方弹字同步
    const allies = cmb.allies || [];
    const player = cmb.player;
    const curUnits = player ? [player, ...allies] : [...allies];
    if (prevAllyState && prevAllyState.length > 0) {
      const prevSnap = prevAllyState.map(a => ({ ...a }));
      const curSnap = curUnits.map(u => ({ vitality: u.vitality, max_vitality: u.max_vitality }));
      const cards = this.shadowRoot.querySelectorAll('.combat-ally-card');
      // 立即动画：HP上升（治疗/回复）
      for (let i = 0; i < cards.length && i < curSnap.length; i++) {
        const prev = prevSnap[i];
        const cur = curSnap[i];
        if (!prev || prev.hp === cur.vitality || cur.vitality < prev.hp) continue;
        this._animateCardHp(cards[i], prev.hp, prev.maxHp, cur.vitality, cur.max_vitality || 1);
      }
      // 延迟动画：HP下降（敌方攻击造成）
      setTimeout(() => {
        for (let i = 0; i < cards.length && i < curSnap.length; i++) {
          const prev = prevSnap[i];
          const cur = curSnap[i];
          if (!prev || prev.hp === cur.vitality || cur.vitality >= prev.hp) continue;
          this._animateCardHp(cards[i], prev.hp, prev.maxHp, cur.vitality, cur.max_vitality || 1);
        }
      }, 800);
    }
  }

  /** 单张卡片：血条过渡 + 闪烁 */
  _animateCardHp(card, oldHp, oldMax, newHp, newMax) {
    if (!card) return;
    const fill = card.querySelector('.combat-hp-fill');
    const oldPct = Math.round(oldHp / Math.max(oldMax, 1) * 100);
    const newPct = Math.round(newHp / Math.max(newMax, 1) * 100);
    if (oldPct === newPct) return;

    const isHeal = newHp > oldHp;

    // 闪烁
    card.classList.add(isHeal ? 'heal-flash' : 'damage-flash');
    setTimeout(() => card.classList.remove('damage-flash', 'heal-flash'), 500);

    // 血条过渡
    if (fill) {
      fill.style.transition = 'none';
      fill.style.width = oldPct + '%';
      fill.offsetHeight;
      fill.style.transition = 'width 0.35s ease-out';
      fill.style.width = newPct + '%';
    }
  }

  /** 根据 replay_actions 分批弹出弹字：友方先 → 敌方后 */
  _spawnPopups(cmb) {
    if (this._replayConsumed) return;
    const actions = cmb.replay_actions;
    if (!actions || actions.length === 0) { this._replayConsumed = true; return; }
    this._replayConsumed = true;

    const statLabels = cmb.attr_labels || {};
    const F = CombatAllies.fmtNum;

    // 按行动者阵营分组
    const allyActions = [];
    const enemyActions = [];
    for (const action of actions) {
      // 敌方行动 或 DOT tick 都延迟显示
      if (action.actor_side === 'enemy' || action.action_type === 'dot') {
        enemyActions.push(action);
      } else {
        allyActions.push(action);
      }
    }

    // 构建弹字数据
    const buildPopups = (actionList) => {
      const popups = [];
      for (const action of actionList) {
        const targets = action.targets || [];
        const effects = action.effects || [];
        if (targets.length === 0 || effects.length === 0) continue;
        for (const effect of effects) {
          const result = this._buildPopupText(effect, statLabels, F);
          if (!result) continue;
          for (const t of targets) {
            popups.push({ side: t.side, id: t.id, cls: result.cls, text: result.text });
          }
        }
      }
      return popups;
    };

    // 友方立即弹出
    this._spawnPopupList(buildPopups(allyActions));

    // 敌方延迟弹出（等友方动画结束）
    const enemyPopups = buildPopups(enemyActions);
    if (enemyPopups.length > 0) {
      setTimeout(() => this._spawnPopupList(enemyPopups), 800);
    }
  }

  /** 构建单个效果的弹字类型和文本 */
  _buildPopupText(effect, statLabels, F) {
    const type = effect.type;
    const value = effect.value;
    const isPursuit = effect.pursuit === true;
    let cls, text;
    if (type === 'hp' && value < 0) {
      if (isPursuit) {
        cls = 'pursuit'; text = '追击 ' + F(Math.abs(value));
      } else {
        const isCrit = Math.abs(value) > 30;
        cls = isCrit ? 'crit' : 'damage'; text = isCrit ? '暴击 ' + F(Math.abs(value)) : F(value);
      }
    } else if (type === 'hp' && value > 0) {
      cls = 'heal'; text = '+' + F(value);
    } else if (type === 'shield') {
      cls = 'shield'; text = '+' + F(value) + ' 护盾';
    } else if (type === 'stunned') {
      cls = 'stun'; text = effect.name || '眩晕';
    } else if (type === 'buffs_removed') {
      cls = 'dispel'; text = '驱散';
    } else if (type === 'dot' && value < 0) {
      cls = 'dot'; text = F(value);
    } else if (type === 'dot' && value > 0) {
      cls = 'heal'; text = '+' + F(value);
    } else if (value > 0) {
      const label = statLabels[type] || type;
      cls = 'buff'; text = '↑' + label + ' +' + F(value);
    } else if (value < 0) {
      const label = statLabels[type] || type;
      cls = 'debuff'; text = '↓' + label + ' ' + F(value);
    } else {
      return null;
    }
    return { cls, text };
  }

  /** 批量弹出弹字列表 */
  _spawnPopupList(popups) {
    for (const p of popups) {
      const card = this._findCard(p.side, p.id);
      if (card) this._spawnOne(card, p.cls, p.text);
    }
  }

  /** 查找卡片元素 */
  _findCard(side, name) {
    const root = this.shadowRoot;
    if (!name) return null;
    if (side === 'enemy') {
      const cards = root.querySelectorAll('.combat-enemy-card');
      for (const card of cards) {
        const nameEl = card.querySelector('.combat-card-name');
        if (nameEl && nameEl.textContent.trim() === name) return card;
      }
    } else {
      const escaped = CSS.escape ? CSS.escape(name) : name.replace(/"/g, '\\"');
      return root.querySelector('.combat-ally-card[data-unit-name="' + escaped + '"]');
    }
    return null;
  }

  /** 在卡片上弹出一个弹字 */
  _spawnOne(card, cls, text) {
    const el = document.createElement('div');
    el.className = 'dmg-num ' + cls;
    el.textContent = text;

    // 计数已有弹字，递增偏移避免堆叠
    const existing = card.querySelectorAll('.dmg-num').length;
    const rx = (Math.random() - 0.5) * 20;
    const ry = -existing * 26 - 10 + (Math.random() - 0.5) * 8;
    el.style.left = 'calc(50% + ' + rx + 'px)';
    el.style.top = 'calc(40% + ' + ry + 'px)';

    card.appendChild(el);
    el.addEventListener('animationend', () => el.remove());
  }

  _renderActions(cmb) {
    const phase = cmb.phase;
    if (phase !== 'player_turn') {
      const hints = { enemy_turn: '敌人行动中...', resolving: '结算中...' };
      return '<div class="combat-actions"><div style="text-align:center;color:var(--color-text-muted);padding:10px;font-size:var(--font-size-sm)">' + (hints[phase] || '请稍候...') + '</div></div>';
    }

    const actions = cmb.available_actions || ['ability', 'item', 'defend', 'flee'];
    const labels = { ability: '技能', item: '物品', defend: '防御', flee: '逃跑' };
    const hasAbilities = cmb.available_abilities && cmb.available_abilities.length > 0;
    const hasItems = cmb.available_items && cmb.available_items.length > 0;

    const self = this;
    const actionsHtml = actions.map(function(a) {
      const disabled = (a === 'ability' && !hasAbilities) || (a === 'item' && !hasItems);
      const isActive = self._targeter.selectedAction === a;
      let btnClass = 'combat-action-btn';
      if (isActive) btnClass += ' active';
      if (a === 'flee') btnClass += ' flee';
      return '<button class="' + btnClass + '" data-action="' + a + '"' +
        (disabled ? ' disabled' : '') + '>' + (labels[a] || a) + '</button>';
    }).join('');

    return '<div class="combat-actions">' + actionsHtml + '</div>';
  }

  _renderResultOverlay() {
    return '<div class="combat-result-overlay hidden" id="result-overlay">' +
      '<div class="combat-result-box">' +
      '<div class="combat-result-title" id="result-title"></div>' +
      '<div class="combat-result-detail" id="result-detail"></div>' +
      '<button class="combat-result-btn">继续</button>' +
      '</div></div>';
  }

  _bindEvents() {
    // 点击敌人卡片（目标选择）
    this.shadowRoot.querySelectorAll('.combat-enemy-card.selectable').forEach(card => {
      card.addEventListener('click', () => {
        const idx = parseInt(card.dataset.enemyIndex);
        if (!isNaN(idx)) {
          this._targeter.executeTarget(idx);
        }
      });
    });

    // 点击全体敌人外框
    const allEnemyWrapper = this.shadowRoot.querySelector('.combat-enemy-cards-wrapper.selectable');
    if (allEnemyWrapper) {
      allEnemyWrapper.addEventListener('click', () => {
        this._targeter.confirmTarget();
      });
    }

    // 点击友方卡片（自身目标选择）
    this.shadowRoot.querySelectorAll('.combat-ally-card.selectable').forEach(card => {
      card.addEventListener('click', () => {
        this._targeter.confirmTarget();
      });
    });

    // 操作按钮
    this.shadowRoot.querySelectorAll('.combat-action-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const action = btn.dataset.action;
        this._handleAction(action);
      });
    });

    // 技能列表项
    this.shadowRoot.querySelectorAll('.combat-sub-item[data-ability-id]').forEach(item => {
      item.addEventListener('click', () => {
        const abilityId = item.dataset.abilityId;
        this._handleAbilitySelect(abilityId);
      });
    });

    // 物品列表项
    this.shadowRoot.querySelectorAll('.combat-sub-item[data-item-id]').forEach(item => {
      item.addEventListener('click', () => {
        const itemId = item.dataset.itemId;
        this._handleItemSelect(itemId);
      });
    });

    // 关闭子面板按钮
    const closeBtn = this.shadowRoot.querySelector('.combat-sub-close');
    if (closeBtn) {
      closeBtn.addEventListener('click', () => {
        this._targeter.reset();
        this._renderAll();
      });
    }

    // 点击分组标签弹出该技能的子效果详情
    this.shadowRoot.querySelectorAll('.combat-tag.clickable').forEach(tag => {
      tag.addEventListener('click', (e) => {
        e.stopPropagation();
        const card = tag.closest('[data-unit-name]');
        const unitName = card && card.dataset.unitName;
        const sourceKey = tag.dataset.sourceKey;
        if (unitName) this._toggleBuffDetail(unitName, tag.closest('.combat-tags'), sourceKey);
      });
    });
    // 点击 +N 溢出标签弹出全部汇总
    this.shadowRoot.querySelectorAll('.combat-tag.more').forEach(tag => {
      tag.addEventListener('click', (e) => {
        e.stopPropagation();
        const card = tag.closest('[data-unit-name]');
        const unitName = card && card.dataset.unitName;
        if (unitName) this._toggleBuffDetail(unitName, tag.closest('.combat-tags'));
      });
    });

    // 恢复展开状态
    this._restoreExpand();
  }

  _handleAction(type) {
    if (type === 'defend' || type === 'flee') {
      this._targeter.sendActionDirect(type);
      return;
    }

    if (this._targeter.selectedAction === type) {
      // 再次点击同一按钮：收起
      this._targeter.reset();
      this._renderAll();
      return;
    }

    this._targeter.selectedAction = type;
    if (type !== 'ability') this._targeter.selectedAbilityId = null;
    if (type !== 'item') this._targeter.selectedItemId = null;
    this._targeter.targetingMode = false;
    this._targeter.targetingType = null;
    this._renderAll();
  }

  _handleAbilitySelect(abilityId) {
    const cmb = AppState.getCombat();
    const abilities = cmb.available_abilities || [];
    const ability = abilities.find(s => s.id === abilityId);
    if (!ability) return;

    if (this._targeter.selectedAbilityId === abilityId) {
      this._targeter.selectedAbilityId = null;
      this._targeter.targetingMode = false;
      this._targeter.targetingType = null;
      this._renderAll();
      return;
    }

    this._targeter.selectedAbilityId = abilityId;

    // 进入目标模式
    const effects = ability.effects || [];
    const primaryTarget = effects.length > 0 ? effects[0].target : 'enemy';
    if (primaryTarget === 'self' || primaryTarget === 'all_ally') {
      this._targeter.startTargeting('self');
    } else if (primaryTarget === 'all_enemy') {
      this._targeter.startTargeting('all_enemy');
    } else {
      this._targeter.startTargeting('single_enemy');
    }

    this._renderAll();
  }

  _handleItemSelect(itemId) {
    const cmb = AppState.getCombat();
    const items = cmb.available_items || [];
    const item = items.find(it => it.item_id === itemId);
    if (!item) return;

    if (this._targeter.selectedItemId === itemId) {
      this._targeter.selectedItemId = null;
      this._targeter.targetingMode = false;
      this._targeter.targetingType = null;
      this._renderAll();
      return;
    }

    this._targeter.selectedItemId = itemId;

    let primaryTarget = 'self';
    if (item.effects && item.effects.length > 0) {
      primaryTarget = item.effects[0].target || 'self';
    }
    if (primaryTarget === 'self' || primaryTarget === 'all_ally') {
      this._targeter.startTargeting('self');
    } else if (primaryTarget === 'all_enemy') {
      this._targeter.startTargeting('all_enemy');
    } else {
      this._targeter.startTargeting('single_enemy');
    }

    this._renderAll();
  }

  _restoreExpand() {
    if (!this._targeter.selectedAbilityId && !this._targeter.selectedItemId) return;

    const subPanel = this.shadowRoot.querySelector('.combat-sub-panel');
    if (!subPanel) return;

    const cmb = AppState.getCombat();
    if (!cmb) return;

    if (this._targeter.selectedAbilityId) {
      const ability = (cmb.available_abilities || []).find(s => s.id === this._targeter.selectedAbilityId);
      if (ability) {
        const itemEl = subPanel.querySelector('[data-ability-id="' + this._targeter.selectedAbilityId + '"]');
        if (itemEl) {
          itemEl.classList.add('selected');
          this._expandDetail(itemEl, ability);
        }
      }
    }
    if (this._targeter.selectedItemId) {
      const item = (cmb.available_items || []).find(it => it.item_id === this._targeter.selectedItemId);
      if (item) {
        const itemEl = subPanel.querySelector('[data-item-id="' + this._targeter.selectedItemId + '"]');
        if (itemEl) {
          itemEl.classList.add('selected');
          this._expandDetail(itemEl, item);
        }
      }
    }
  }

  _expandDetail(itemEl, data) {
    let expandHtml = '<div class="combat-sub-expand">';

    if (data.effects && data.effects.length > 0) {
      expandHtml += '<div class="expand-effects">';
      for (const e of data.effects) {
        const schema = AppState.getAttributesSchema() || {};
        expandHtml += '<div>' + CombatPanels.formatEffectText(e, (attrId) => CombatPanels.getAttrLabel(attrId, schema)) + '</div>';
      }
      expandHtml += '</div>';
    }

    const effects = data.effects || [];
    const primaryEffect = effects.length > 0 ? effects[0] : null;
    const effType = primaryEffect ? primaryEffect.type : '';
    const effTarget = primaryEffect ? primaryEffect.target : '';

    let typeLabel = '';
    if (effType === 'damage' && effTarget === 'all_enemy') typeLabel = '范围技';
    else if (effType === 'damage') typeLabel = '攻击技';
    else if (effType === 'fixed_damage' || effType === 'fixed_dot') typeLabel = '真实伤害';
    else if (effType === 'heal') typeLabel = '恢复技';
    else if (effType === 'buff') {
      const isDebuff = primaryEffect && ((primaryEffect.modifier && primaryEffect.modifier < 0) || (primaryEffect.value && primaryEffect.value < 0));
      typeLabel = isDebuff ? '减益技' : '增益技';
    } else if (effType === 'debuff') typeLabel = '减益技';
    else if (effType === 'dot') typeLabel = '持续伤害';
    else if (effType === 'stun') typeLabel = '控制';
    else if (effType === 'shield') typeLabel = '防护';
    else if (effType === 'dispel') typeLabel = '驱散';

    if (typeLabel) {
      expandHtml += '<div class="expand-meta">类型：' + typeLabel + '</div>';
    }

    const desc = data.description || '';
    if (desc) {
      expandHtml += '<div class="expand-desc">' + this._esc(desc) + '</div>';
    }

    expandHtml += '</div>';

    const tempDiv = document.createElement('div');
    tempDiv.innerHTML = expandHtml;
    const expandNode = tempDiv.firstChild;
    if (!itemEl.parentNode) return;
    itemEl.parentNode.insertBefore(expandNode, itemEl.nextSibling);
  }

  /** 显示战斗结果 */
  showResult(phase, rewards) {
    const overlay = this.shadowRoot.getElementById('result-overlay');
    const titleEl = this.shadowRoot.getElementById('result-title');
    const detailEl = this.shadowRoot.getElementById('result-detail');
    if (!overlay || !titleEl || !detailEl) return;

    const titles = { victory: '胜利', defeat: '败北', flee: '逃跑成功' };
    const titleClass = phase === 'victory' ? 'victory' : 'defeat';

    let rewardsHtml = '';
    if (rewards) {
      const exp = rewards.exp_gained || 0;
      const loot = rewards.loot || [];
      const parts = [];
      if (exp > 0) parts.push('获得经验 ' + exp);
      if (loot.length > 0) {
        const lootNames = loot.map(l => (l.name || l.item_id) + ' x' + (l.quantity || 1));
        parts.push('获得物品: ' + lootNames.join('、'));
      }
      if (parts.length > 0) rewardsHtml = parts.join('<br/>');
    }

    titleEl.textContent = titles[phase] || phase;
    titleEl.className = 'combat-result-title ' + titleClass;
    detailEl.innerHTML = rewardsHtml;
    overlay.classList.remove('hidden');
  }

  _closeResult() {
    if (this._resultTimer) { clearTimeout(this._resultTimer); this._resultTimer = null; }
    const overlay = this.shadowRoot.getElementById('result-overlay');
    if (overlay) overlay.classList.add('hidden');
    AppState.endCombat();
  }
}

customElements.define('combat-ui', CombatUI);
