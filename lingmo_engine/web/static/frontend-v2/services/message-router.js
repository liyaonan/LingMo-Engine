// services/message-router.js — 消息分发中心，替代旧 game.js handleMessage() + message_client.js
import { AppState } from '../state/app-state.js';
import { WebSocketService } from './websocket.js';
import { EventBus } from '../event-bus.js';
import { i18n } from '../shared/i18n.js';

/** 生成客户端消息 ID */
function generateId() {
  return 'msg_' + Date.now().toString(36) + '_' + Math.random().toString(36).slice(2, 10);
}

export const MessageRouter = {
  // 动态消息处理器注册表（插件通过 registerPlugin().messages 注册）
  _handlers: {},

  /** 插件注册消息类型处理器 */
  registerHandlers(handlers) {
    if (!handlers) return;
    Object.entries(handlers).forEach(([type, handler]) => {
      this._handlers[type] = handler;
    });
  },

  /** 处理来自 WebSocket 的所有消息 */
  handleMessage(msg) {
    // 先查动态注册表（插件消息处理器优先）
    if (this._handlers[msg.type]) {
      this._handlers[msg.type](msg);
      return;
    }

    switch (msg.type) {
      // === 输入状态 ===
      case 'input_state':
        AppState.setInputEnabled(msg.enabled !== false);
        break;

      // === 状态更新 ===
      case 'state_update':
        AppState.setStateUpdate(msg.data);
        AppState.updateWorld(msg.data);
        // 游戏页收到无 player 的 state_update 说明游戏已结束/重置，跳回标题页
        // 标题页/创建页没有 player 是正常的，不触发重定向
        if (!msg.data || !msg.data.player) {
          if (window.location.pathname === '/game') {
            window.location.href = '/';
            return;
          }
        }
        break;

      // === 属性 Schema ===
      case 'attributes_schema':
        AppState.setAttributesSchema(msg.data);
        break;

      // === 角色数据 ===
      case 'character_data':
        AppState.setCharacterData(
          msg.character, msg.panel_config,
          msg.abilities || {}, msg.equipment_expanded || {},
          msg.memories || null, msg.relationships || [],
          msg.panel_schema || null, msg.display_values || null
        );
        break;

      // === 游戏开场 ===
      case 'game_started':
        if (msg.data && msg.data.opening) {
          EventBus.emit('action:show-opening', msg.data.opening);
        }
        break;

      // === 游戏加载 ===
      case 'game_loaded':
        sessionStorage.setItem('game_loaded', '1');
        AppState.clearNarrative();
        EventBus.emit('action:game-loaded', null);
        break;

      // === Message 事件 ===
      case 'message.event':
        this._handleMessageEvent(msg.event, msg.data);
        break;

      // === 服务端推送的内部消息（不在叙述区展示） ===
      case 'system':
      case 'error':
        // 不在叙述区渲染，仅 console 记录
        // system/error 消息不渲染
        break;

      // === Page 重试 ===
      case 'page_retry':
        EventBus.emit('narrative:page-retry', msg);
        break;

      // === LLM 忙碌警告 ===
      case 'llm_busy_warning':
        EventBus.emit('toast:show', msg.message || i18n.t('request_processing'));
        break;

      // === 背包相关 ===
      case 'inventory_state':
        AppState.updateInventory(msg);
        break;
      case 'inventory_action_result':
        if (msg.success) {
          WebSocketService.send({ type: 'inventory_open' });
          // 装备变更影响了技能，刷新技能面板
          if (msg.abilities_changed) {
            WebSocketService.send({ type: 'abilities_open' });
          }
        }
        break;

      // === 存档相关 ===
      case 'save_list':
      case 'save_result':
      case 'delete_result':
      case 'rename_result':
      case 'export_ready':
        EventBus.emit('action:' + msg.type, msg);
        break;

      // === 设置相关 ===
      case 'config_data':
      case 'config_saved':
      case 'config_test_result':
      case 'config_models_result':
        EventBus.emit('action:' + msg.type, msg);
        break;

      // === Debug 面板 ===
      case 'debug_panel':
        EventBus.emit('action:toggle-debug', null);
        break;

      // === 战斗相关 ===
      case 'combat_start':
        AppState.startCombat(msg.state);
        break;
      case 'combat_state_update':
        AppState.updateCombat(msg.state);
        break;

      // === 技能管理 ===
      case 'abilities_state':
        AppState.updateAbilities(msg);
        break;
      case 'ability_action_result':
        if (msg.success) {
          WebSocketService.send({ type: 'abilities_open' });
        }
        break;

      // === 事件面板 ===
      case 'events_data':
        EventBus.emit('action:events_data', msg);
        break;

      case 'scene_npc_names':
        EventBus.emit('action:scene_npc_names', msg);
        break;

      // === 未知消息 → 插件/自定义路由 ===
      default:
        EventBus.emit('ws:' + msg.type, msg);
        break;
    }
  },

  /** 处理 message.event 子类型 */
  _handleMessageEvent(event, data) {
    switch (event) {
      case 'message.created':
        AppState.addMessage(data);
        EventBus.emit('narrative:message-created', data);
        break;
      case 'message.updated':
        AppState.updateMessage(data.id, {
          content: data.content,
          edited_at: data.edited_at,
          meta: data.meta,
        });
        EventBus.emit('narrative:message-updated', data);
        break;
      case 'message.deleted':
        AppState.deleteMessage(data.id);
        EventBus.emit('narrative:message-deleted', data);
        break;
      case 'message.streaming':
        AppState.appendStream(data.delta || '');
        EventBus.emit('narrative:streaming', data);
        break;
      case 'message.stream_end':
        AppState.endStream(data.content);
        EventBus.emit('narrative:stream-end', data);
        break;
      case 'message.stream_discard':
        EventBus.emit('narrative:stream-discard', data);
        break;
      case 'message.retracted':
        EventBus.emit('narrative:stream-retracted', data);
        break;
    }
  },

  // === 出站：发送用户输入 ===

  sendUserInput(content) {
    const pageId = 'page_' + Date.now().toString(36);
    WebSocketService.send({
      type: 'message',
      action: 'create',
      message: {
        id: generateId(),
        role: 'user',
        content: content,
        page_id: pageId,
      },
    });
  },

  /** 发送 Page 重试请求 */
  retryPage(pageId) {
    WebSocketService.send({
      type: 'retry_page',
      page_id: pageId,
    });
  },

};
