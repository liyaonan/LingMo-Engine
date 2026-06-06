// plugins/combat/abilities-state.js — 技能管理面板状态切片
export function createAbilitiesState() {
  return {
    name: 'abilities',

    _state: {
      abilities: [],
      categories: [],
      rarities: [],
      max_abilities: 20,
      player_name: '',
    },

    getState() { return { ...this._state }; },

    updateFullState(data) {
      this._state.abilities = data.abilities || [];
      this._state.categories = data.categories || [];
      this._state.rarities = data.rarities || [];
      this._state.rarities = data.rarities || [];
      this._state.max_abilities = data.max_abilities || 20;
      this._state.player_name = data.player_name || '';
      return 'abilities';
    },

    restore(state) { Object.assign(this._state, state); },
  };
}
