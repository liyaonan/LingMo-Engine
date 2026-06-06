// plugins/combat/combat-state.js
export function createCombatState() {
  return {
    name: 'combat',
    _state: {
      active: false,
      round: 0,
      phase: '',
      enemies: [],
      player: null,
      poolAttrs: [],
      log: [],
      available_actions: [],
      available_abilities: [],
      available_items: [],
      ability_rarities: {},
      ability_categories: [],
      cooldowns: {},
      rewards: null,
      allies: [],
      replay_actions: [],
      level_colors: [],
      attr_labels: {},
    },
    getState() { return { ...this._state }; },

    show(state) {
      this._state.active = true;
      Object.assign(this._state, {
        round: state.round || 1,
        phase: state.phase || '',
        enemies: state.enemies || [],
        player: state.player || null,
        poolAttrs: state.pool_attrs || [],
        log: state.log || [],
        available_actions: state.available_actions || [],
        available_abilities: state.available_abilities || [],
        available_items: state.available_items || [],
        ability_rarities: state.ability_rarities || {},
        ability_categories: state.ability_categories || [],
        cooldowns: (state.player && state.player.cooldowns) || {},
        allies: state.allies || [],
        replay_actions: state.replay_actions || [],
        level_colors: state.level_colors || [],
        attr_labels: state.attr_labels || {},
      });
      return 'combat';
    },

    updateState(state) {
      Object.assign(this._state, {
        round: state.round || this._state.round,
        phase: state.phase || this._state.phase,
        enemies: state.enemies || this._state.enemies,
        player: state.player || this._state.player,
        poolAttrs: state.pool_attrs || this._state.poolAttrs,
        log: state.log || this._state.log,
        available_actions: state.available_actions || this._state.available_actions,
        available_abilities: state.available_abilities || this._state.available_abilities,
        available_items: state.available_items || this._state.available_items,
        ability_rarities: state.ability_rarities || this._state.ability_rarities,
        ability_categories: state.ability_categories || this._state.ability_categories,
        cooldowns: (state.player && state.player.cooldowns) || this._state.cooldowns,
        rewards: state.rewards || null,
        allies: state.allies || this._state.allies,
        replay_actions: state.replay_actions || this._state.replay_actions,
        level_colors: state.level_colors || this._state.level_colors,
        attr_labels: state.attr_labels || this._state.attr_labels,
      });
      return 'combat';
    },

    hide() {
      this._state.active = false;
      return 'combat';
    },

    clear() {
      this._state.active = false;
      this._state.enemies = [];
      this._state.player = null;
      this._state.log = [];
      this._state.allies = [];
      this._state.replay_actions = [];
      this._state.level_colors = [];
      return 'combat';
    },

    restore(state) { Object.assign(this._state, state); },
  };
}
