export function createInventoryState() {
  return {
    name: 'inventory',
    _state: {
      inventory: [],
      equipment: {},
      categories: [],
      rarities: [],
      slots: [],
      gold: 0,
      max_slots: 30,
      player_name: '',
    },
    getState() { return { ...this._state }; },
    update(data) { Object.assign(this._state, data); return 'inventory'; },
    /** 处理完整 inventory_state WS 响应 */
    updateFullState(data) {
      this._state.inventory = data.inventory || [];
      this._state.equipment = data.equipment || {};
      this._state.categories = data.categories || [];
      this._state.rarities = data.rarities || [];
      this._state.slots = data.slots || [];
      this._state.gold = data.gold || 0;
      this._state.max_slots = data.max_slots || 30;
      this._state.player_name = data.player_name || '';
      return 'inventory';
    },
    restore(state) { Object.assign(this._state, state); },
  };
}
