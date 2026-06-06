// state/app-state.js
import { EventBus } from '../event-bus.js';
import { createPlayerSlice } from './slices/player-slice.js';
import { createWorldSlice } from './slices/world-slice.js';
import { createNarrativeSlice } from './slices/narrative-slice.js';
import { createUISlice } from './slices/ui-slice.js';

class _AppState {
  constructor() {
    this._slices = {};
    this._registerBuiltinSlices();
  }

  _registerBuiltinSlices() {
    this._slices.player = createPlayerSlice();
    this._slices.world = createWorldSlice();
    this._slices.narrative = createNarrativeSlice();
    this._slices.ui = createUISlice();
  }

  registerSlice(factory) {
    const slice = factory();
    this._slices[slice.name] = slice;
  }

  getSlice(name) {
    return this._slices[name] ? this._slices[name].getState() : null;
  }

  _call(sliceName, method, ...args) {
    const slice = this._slices[sliceName];
    if (!slice || !slice[method]) {
      console.warn(`[AppState] 未知方法: ${sliceName}.${method}`);
      return;
    }
    const key = slice[method](...args);
    if (key) {
      EventBus.emit(`state:changed:${key}`, this.getSlice(sliceName));
    }
  }

  // ---- Public API ----
  getPlayer() { return this._slices.player.getPlayer(); }
  getAttributesSchema() { return this._slices.player.getSchema(); }
  updatePlayer(data) { this._call('player', 'updatePlayer', data); }
  setAttributesSchema(schema) { this._call('player', 'setAttributesSchema', schema); }
  setStateUpdate(data) { this._call('player', 'setStateUpdate', data); }
  setCharacterData(char, cfg, ab, eq, mem, rel, schema, vals) { this._call('player', 'setCharacterData', char, cfg, ab, eq, mem, rel, schema, vals); }
  setAbilitySlots(slots) { this._call('player', 'setAbilitySlots', slots); }

  getWorld() { return this._slices.world.getState(); }
  updateWorld(data) { this._call('world', 'updateFromState', data); }

  getNarrative() { return this._slices.narrative.getState(); }
  addMessage(msg) { this._call('narrative', 'addMessage', msg); }
  appendStream(delta) { this._call('narrative', 'appendStream', delta); }
  startStream(id) { this._call('narrative', 'startStream', id); }
  endStream(content) { this._call('narrative', 'endStream', content); }
  updateMessage(id, u) { this._call('narrative', 'updateMessage', id, u); }
  deleteMessage(id) { this._call('narrative', 'deleteMessage', id); }
  setCurrentPage(idx) { this._call('narrative', 'setCurrentPage', idx); }
  loadMessages(msgs) { this._call('narrative', 'loadMessages', msgs); }
  clearNarrative() { this._call('narrative', 'clear'); }

  getUI() { return this._slices.ui.getState(); }
  setInputEnabled(enabled) { this._call('ui', 'setInputEnabled', enabled); }
  setCombatActive(active) { this._call('ui', 'setCombatActive', active); }
  isBusy() { return this._slices.ui.isBusy(); }
  isCombatActive() { return this._slices.ui.isCombatActive(); }
  setActivePlugin(name) { this._call('ui', 'setActivePlugin', name); }
  toggleSavePanel(open) { this._call('ui', 'toggleSavePanel', open); }
  toggleSettings(open) { this._call('ui', 'toggleSettings', open); }
  showNewPageIndicator(show) { this._call('ui', 'showNewPageIndicator', show); }
  setShowThinking(show) { this._call('ui', 'setShowThinking', show); }

  getInventory() { return this._slices.inventory ? this._slices.inventory.getState() : null; }
  updateInventory(data) {
    const slice = this._slices.inventory;
    if (!slice) return;
    const key = slice.updateFullState(data);
    if (key) EventBus.emit(`state:changed:${key}`, this.getSlice('inventory'));
  }

  getCombat() { return this._slices.combat ? this._slices.combat.getState() : null; }
  getAbilities() { return this._slices.abilities ? this._slices.abilities.getState() : null; }
  updateAbilities(data) {
    const slice = this._slices.abilities;
    if (!slice) return;
    const key = slice.updateFullState(data);
    if (key) EventBus.emit(`state:changed:${key}`, this.getSlice('abilities'));
  }
  startCombat(state) {
    const slice = this._slices.combat;
    if (!slice) return;
    const key = slice.show(state);
    if (key) EventBus.emit(`state:changed:${key}`, this.getSlice('combat'));
    this.setCombatActive(true);
    this.setActivePlugin('combat');  // 触发 plugin-host 挂载 <combat-ui>
    this.setInputEnabled(false);
  }
  updateCombat(state) {
    const slice = this._slices.combat;
    if (!slice) return;
    const key = slice.updateState(state);
    if (state.phase === 'victory' || state.phase === 'defeat' || state.phase === 'flee') {
      this.setCombatActive(false);
      // activePlugin 由 endCombat() 清除 — 用户关闭结果弹窗时触发
    }
    if (key) EventBus.emit(`state:changed:${key}`, this.getSlice('combat'));
  }
  endCombat() {
    const slice = this._slices.combat;
    if (!slice) return;
    const key = slice.hide();
    if (key) EventBus.emit(`state:changed:${key}`, this.getSlice('combat'));
    this.setActivePlugin(null);  // 关闭 combat 覆盖层
    // 不调用 setInputEnabled(true) — 输入恢复由后端的 input_state 消息控制
    // 后端 LLM_IDLE 时会发送 input_state: { enabled: true }
  }

  // ---- cultivation ----
  getCultivation() { return this._slices.cultivation?.getState(); }
  updateCultivation(msg) {
    if (this._slices.cultivation) {
      const key = this._slices.cultivation.update(msg);
      if (key) EventBus.emit(`state:changed:${key}`, this.getSlice('cultivation'));
    }
  }

  snapshot() {
    const result = {};
    for (const [name, slice] of Object.entries(this._slices)) {
      if (slice.getState) result[name] = slice.getState();
    }
    return result;
  }

  restore(snapshot) {
    for (const [name, state] of Object.entries(snapshot)) {
      const slice = this._slices[name];
      if (slice && slice.restore) slice.restore(state);
    }
    EventBus.emit('state:changed:bulk', snapshot);
  }
}

export const AppState = new _AppState();
