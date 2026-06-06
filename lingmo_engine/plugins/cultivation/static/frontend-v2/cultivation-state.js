/**
 * 修炼面板状态切片
 */
export function createCultivationState() {
  return {
    name: 'cultivation',
    _state: {
      stage_id: 'mortal',
      stage_name: '凡人',
      substage: '1',
      substage_name: '一阶',
      path: '',
      path_name: '',
      spiritual_power: 0,
      next_threshold: 0,
      breakthrough_ready: false,
      lifespan_remaining: 100,
      lifespan_total: 100,
      roots: [],
      root_quality: 'waste',
      root_quality_name: '废灵根',
      root_modifier: 1.0,
      qi_density: 0.4,
      qi_level_id: 'thin',
      qi_level_name: '正常',
      qi_modifier: 0.6,
      daily_meditation: 0,
      stone_rate: 100,
      breakthrough_cooldown: 0,
      breakthrough_rates: {},
      dao_rhyme: 0,
      dao_rhyme_threshold: 0,
      enlightenment_ready: false,
      next_stage_name: '',
      session_active: false,
      cultivation_log: [],
      action_result: null,
    },

    getState() { return { ...this._state }; },

    update(msg) {
      if (msg.data) Object.assign(this._state, msg.data);
      if (msg.action_result) {
        this._state.action_result = msg.action_result;
      } else if (msg.type === 'cultivation_state') {
        this._state.action_result = null;
      }
      if (msg.type === 'cultivation_session_end') {
        this._state.session_active = false;
        this._state.cultivation_log = [];
        this._state.action_result = null;
      }
      return 'cultivation';
    },

    clearActionResult() {
      this._state.action_result = null;
    },

    restore(state) {
      if (state) Object.assign(this._state, state);
    },
  };
}
