// state/slices/player-slice.js
export function createPlayerSlice() {
  return {
    name: 'player',

    _state: {
      player: null,
      attributesSchema: null,
      inventory: null,
      abilitySlots: null,
      equipmentExpanded: {},
      abilitiesData: {},
      memories: null,
      relationshipsResolved: [],
      characterData: null,
      panelConfig: null,
      panelSchema: null,
      displayValues: null,
    },

    getPlayer() { return this._state.player ? { ...this._state.player } : null; },
    getSchema() { return this._state.attributesSchema; },
    getInventory() { return this._state.inventory; },

    updatePlayer(playerData) {
      Object.assign(this._state.player || (this._state.player = {}), playerData);
      return 'player';
    },

    setAttributesSchema(schema) {
      this._state.attributesSchema = schema;
      return 'player';
    },

    setStateUpdate(data) {
      if (data.player) this._state.player = Object.assign(this._state.player || {}, data.player);
      if (data.inventory) this._state.inventory = data.inventory;
      return 'player';
    },

    setCharacterData(character, panelConfig, abilities, equipmentExpanded, memories, relationships, panelSchema, displayValues) {
      this._state.characterData = character;
      this._state.panelConfig = panelConfig;
      this._state.abilitiesData = abilities || {};
      this._state.equipmentExpanded = equipmentExpanded || {};
      this._state.memories = memories || null;
      this._state.relationshipsResolved = relationships || [];
      this._state.panelSchema = panelSchema || null;
      this._state.displayValues = displayValues || null;
      return 'player';
    },

    setAbilitySlots(slots) {
      this._state.abilitySlots = slots;
      return 'player';
    },

    getState() { return { ...this._state }; },
    restore(state) { Object.assign(this._state, state); },
  };
}
