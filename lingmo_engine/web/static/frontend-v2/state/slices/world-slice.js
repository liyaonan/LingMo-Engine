// state/slices/world-slice.js
export function createWorldSlice() {
  return {
    name: 'world',

    _state: {
      location: null,
      locationType: null,
      breadcrumb: [],
      currentNode: null,
      parent: null,
      children: [],
      connections: [],
      gameTime: null,
      worldTitle: 'LingMo Engine',
    },

    getLocation() { return this._state.location; },

    updateFromState(data) {
      if (data.location !== undefined) this._state.location = data.location;
      if (data.breadcrumb !== undefined) this._state.breadcrumb = data.breadcrumb;
      if (data.current_node !== undefined) this._state.currentNode = data.current_node;
      if (data.parent !== undefined) this._state.parent = data.parent;
      if (data.children !== undefined) this._state.children = data.children;
      if (data.connections !== undefined) this._state.connections = data.connections;
      if (data.game_time !== undefined) this._state.gameTime = data.game_time;
      if (data.world_title !== undefined) this._state.worldTitle = data.world_title;
      return 'world';
    },

    getState() { return { ...this._state }; },
    restore(state) { Object.assign(this._state, state); },
  };
}
