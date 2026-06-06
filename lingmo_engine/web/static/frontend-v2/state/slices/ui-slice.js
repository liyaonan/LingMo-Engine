// state/slices/ui-slice.js
export function createUISlice() {
  return {
    name: 'ui',

    _state: {
      inputEnabled: true,
      isBusy: false,
      combatActive: false,
      activePlugin: null,
      savePanelOpen: false,
      settingsOpen: false,
      newPageIndicator: false,
      showThinking: true,
    },

    getInputEnabled() { return this._state.inputEnabled && !this._state.combatActive; },
    isBusy() { return this._state.isBusy; },
    isCombatActive() { return this._state.combatActive; },
    getActivePlugin() { return this._state.activePlugin; },

    setInputEnabled(enabled) {
      this._state.inputEnabled = enabled;
      this._state.isBusy = !enabled;
      return 'ui';
    },

    setCombatActive(active) {
      this._state.combatActive = active;
      return 'ui';
    },

    setActivePlugin(name) {
      this._state.activePlugin = name;
      return 'ui';
    },

    toggleSavePanel(open) {
      this._state.savePanelOpen = open !== undefined ? open : !this._state.savePanelOpen;
      return 'ui';
    },

    toggleSettings(open) {
      this._state.settingsOpen = open !== undefined ? open : !this._state.settingsOpen;
      return 'ui';
    },

    showNewPageIndicator(show) {
      this._state.newPageIndicator = show;
      return 'ui';
    },

    setShowThinking(show) {
      this._state.showThinking = show;
      return 'ui';
    },

    getState() { return { ...this._state }; },
    restore(state) { Object.assign(this._state, state); },
  };
}
