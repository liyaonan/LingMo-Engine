// plugins/event/static/frontend-v2/event-state.js
export function createEventState() {
  return {
    name: 'events',
    _state: {
      events: [],
      active_event_id: null,
      choices: [],
      description: '',
    },
    getState() { return { ...this._state }; },

    setEvents(data) {
      this._state.events = data.events || [];
      this._state.active_event_id = data.active_event_id || null;
      this._state.choices = data.choices || [];
      this._state.description = data.description || '';
      return 'events';
    },

    clearEvents() {
      this._state.events = [];
      this._state.active_event_id = null;
      this._state.choices = [];
      this._state.description = '';
      return 'events';
    },

    restore(state) { Object.assign(this._state, state); },
  };
}
