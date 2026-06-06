// plugins/combat/combat-targeting.js
// 目标选择系统 — 从旧前端 CombatUI 目标相关方法移植
import { WebSocketService } from '/static/frontend-v2/services/websocket.js';

export const CombatTargeting = {
  /** 创建目标选择器实例（每个战斗会话一个） */
  create() {
    return {
      selectedAction: null,
      selectedAbilityId: null,
      selectedItemId: null,
      selectedTargetIndex: null,
      targetingMode: false,
      targetingType: null,  // 'single_enemy' | 'all_enemy' | 'self' | 'all_ally'
      targetSide: null,       // "enemy" | "ally" — 目标阵营

      /** 开始目标选择 */
      startTargeting(type, side) {
        this.targetingMode = true;
        this.targetingType = type || 'single_enemy';
        this.targetSide = side || 'enemy';
        this.selectedTargetIndex = null;
      },

      /** 选择单个目标 */
      selectTarget(index) {
        this.selectedTargetIndex = index;
      },

      /** 确认目标并发送 */
      confirmTarget() {
        this._sendAction();
      },

      /** 执行单个敌人目标 + 发送 */
      executeTarget(index) {
        this.selectedTargetIndex = index;
        this._sendAction();
      },

      /** 发送战斗行动 */
      _sendAction() {
        const action = { type: this.selectedAction };
        if (this.selectedAbilityId) action.ability_id = this.selectedAbilityId;
        if (this.selectedItemId) action.item_id = this.selectedItemId;
        if (this.selectedTargetIndex !== null) {
          action.target_index = this.selectedTargetIndex;
          action.target_side = this.targetSide || 'enemy';
        }
        WebSocketService.send({ type: 'combat_action', action });
        this.reset();
      },

      /** 执行无需目标的行动（防御、逃跑） */
      sendActionDirect(type) {
        WebSocketService.send({ type: 'combat_action', action: { type } });
        this.reset();
      },

      /** 重置选择状态 */
      reset() {
        this.selectedAction = null;
        this.selectedAbilityId = null;
        this.selectedItemId = null;
        this.selectedTargetIndex = null;
        this.targetingMode = false;
        this.targetingType = null;
        this.targetSide = null;
      },
    };
  },
};
