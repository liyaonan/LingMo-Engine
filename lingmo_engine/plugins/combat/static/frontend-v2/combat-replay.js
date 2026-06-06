// plugins/combat/combat-replay.js
// 行动回放动画 — 两阶段：行动者高亮 → 目标受击
export const CombatReplay = {
  _playing: false,
  _skip: false,

  /** 播放行动回放 */
  async play(actions, shadowRoot, onComplete) {
    if (!actions || actions.length === 0) {
      if (onComplete) onComplete();
      return;
    }
    this._playing = true;
    this._skip = false;

    for (const action of actions) {
      if (this._skip) break;
      await this._playOne(action, shadowRoot);
    }

    this._playing = false;
    this._clearAll(shadowRoot);
    if (onComplete) onComplete();
  },

  /** 跳过当前回放 */
  skip() {
    this._skip = true;
  },

  get isPlaying() { return this._playing; },

  async _playOne(action, shadowRoot) {
    if (!shadowRoot) return;

    // 阶段 1：行动者高亮
    const actorEl = this._findCard(shadowRoot, action.actor_side, action.actor_name || action.actor_id);
    if (actorEl) actorEl.classList.add('active-turn');
    await this._wait(500);
    if (actorEl) actorEl.classList.remove('active-turn');

    // 阶段 2：目标受击
    const targets = action.targets || [];
    const isHeal = (action.effects || []).some(e => e.type === 'heal');
    const flashClass = isHeal ? 'heal-flash' : 'damage-flash';

    for (const t of targets) {
      const el = this._findCard(shadowRoot, t.side, t.id);
      if (el) el.classList.add(flashClass);
    }
    await this._wait(500);

    this._clearAll(shadowRoot);
    // 间隔
    await this._wait(100);
  },

  /** 查找卡片元素 */
  _findCard(shadowRoot, side, id) {
    if (!id) return null;
    const escapedId = CSS.escape ? CSS.escape(id) : id.replace(/"/g, '\\"');
    if (side === 'ally' || side === 'player') {
      return shadowRoot.querySelector('.combat-ally-card[data-unit-name="' + escapedId + '"]');
    }
    // 敌方通过 enemy index 或 name 查找
    const enemies = shadowRoot.querySelectorAll('.combat-enemy-card');
    for (const card of enemies) {
      const nameEl = card.querySelector('.combat-card-name');
      if (nameEl && nameEl.textContent.trim() === id) return card;
    }
    return null;
  },

  /** 清除所有动画状态 */
  _clearAll(shadowRoot) {
    if (!shadowRoot) return;
    shadowRoot.querySelectorAll('.active-turn, .damage-flash, .heal-flash').forEach(el => {
      el.classList.remove('active-turn', 'damage-flash', 'heal-flash');
    });
  },

  _wait(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  },
};