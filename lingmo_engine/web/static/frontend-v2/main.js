// main.js — 应用启动入口

// === i18n ===
import { i18n } from './shared/i18n.js';

// === 核心组件 ===
import './components/app-shell.js';
import './components/status-bar.js';
import './components/scene-area.js';
import './components/narrative-area.js';
import './components/quick-bar.js';
import './components/input-area.js';
import './components/plugin-host.js';
import './components/save-panel.js';
import './components/settings-modal.js';
import './components/toast-container.js';

// === 核心服务 ===
import { PluginRegistry } from './plugins/plugin-registry.js';
import { MessageRouter } from './services/message-router.js';
import { WebSocketService } from './services/websocket.js';
import { EventBus } from './event-bus.js';
import { AppState } from './state/app-state.js';

// === 系统按钮注册 ===
// 先导入系统面板组件（<character-panel> 等）
import('/static/plugins/character/frontend-v2/character-component.js');

PluginRegistry.registerPlugin({
  name: 'character', system: true, position: 'left',
  button: { label: i18n.t('character'), icon: null },
  ui: { mode: 'panel', tagName: 'character-panel' },
  messages: {
    'character_data': (msg) => {
      AppState.setCharacterData(
        msg.character, msg.panel_config,
        msg.abilities || {}, msg.equipment_expanded || {},
        msg.memories || null, msg.relationships || [],
        msg.panel_schema || null, msg.display_values || null
      );
    },
    'attributes_schema': (msg) => {
      AppState.setAttributesSchema(msg.data);
    },
    'scene_npc_names': (msg) => {
      EventBus.emit('action:scene_npc_names', msg);
    },
    'state_update': (msg) => {
      AppState.setStateUpdate(msg.data);
      AppState.updateWorld(msg.data);
      // 游戏页收到无 player 的 state_update 说明游戏已结束/重置，跳回标题页
      if (!msg.data || !msg.data.player) {
        if (window.location.pathname === '/game') {
          window.location.href = '/';
          return;
        }
      }
    },
  },
});

PluginRegistry.registerPlugin({
  name: 'save', system: true, position: 'right',
  button: { label: i18n.t('save'), icon: null },
  ui: { mode: 'panel', tagName: 'save-panel' },
  messages: {
    'save_list': (msg) => EventBus.emit('action:save_list', msg),
    'save_result': (msg) => EventBus.emit('action:save_result', msg),
    'delete_result': (msg) => EventBus.emit('action:delete_result', msg),
    'rename_result': (msg) => EventBus.emit('action:rename_result', msg),
    'export_ready': (msg) => EventBus.emit('action:export_ready', msg),
  },
});

PluginRegistry.registerPlugin({
  name: 'settings', system: true, position: 'right',
  button: { label: i18n.t('settings'), icon: null },
  ui: { mode: 'panel', tagName: 'settings-modal' },
  messages: {
    'config_data': (msg) => EventBus.emit('action:config_data', msg),
    'config_saved': (msg) => EventBus.emit('action:config_saved', msg),
    'config_test_result': (msg) => EventBus.emit('action:config_test_result', msg),
    'config_models_result': (msg) => EventBus.emit('action:config_models_result', msg),
  },
});

// === 插件注册 ===
// 注意：插件文件已迁移到 /static/plugins/<name>/frontend-v2/

// cultivation 插件（改为交互卡片触发，不再注册工具栏按钮）
import('/static/plugins/cultivation/frontend-v2/cultivation-component.js');
import('/static/plugins/cultivation/frontend-v2/cultivation-state.js').then(m => {
  AppState.registerSlice(m.createCultivationState);
});
import('/static/plugins/cultivation/frontend-v2/cultivation-interaction-cards.js');
import('/static/plugins/cultivation/frontend-v2/cultivation-content.js');

PluginRegistry.registerPlugin({
  name: 'cultivation',
  hidden: true,
  button: { label: i18n.t('cultivation') },
  ui: { mode: 'panel', tagName: 'cultivation-panel' },
  messages: {
    'cultivation_state': (msg) => AppState.updateCultivation(msg),
    'cultivation_session_end': (msg) => AppState.updateCultivation(msg),
  },
});

// combat 插件
import('/static/plugins/combat/frontend-v2/combat-content.js');
import('/static/plugins/combat/frontend-v2/combat-skill-slots.js');
import('/static/plugins/combat/frontend-v2/combat-targeting.js');
import('/static/plugins/combat/frontend-v2/combat-panels.js');
import('/static/plugins/combat/frontend-v2/combat-component.js');
import('/static/plugins/combat/frontend-v2/combat-state.js').then(m => {
  AppState.registerSlice(m.createCombatState);
});
import('/static/plugins/combat/frontend-v2/abilities-state.js').then(m => {
  AppState.registerSlice(m.createAbilitiesState);
});

PluginRegistry.registerPlugin({
  name: 'combat',
  hidden: true,  // 战斗由系统触发，不在功能栏显示按钮
  button: { label: i18n.t('combat'), icon: null },
  ui: { mode: 'overlay', tagName: 'combat-ui' },
  messages: {
    'combat_start': (msg) => AppState.startCombat(msg.state),
    'combat_state_update': (msg) => AppState.updateCombat(msg.state),
    'abilities_state': (msg) => AppState.updateAbilities(msg),
    'ability_action_result': (msg) => {
      if (msg.success) WebSocketService.send({ type: 'abilities_open' });
    },
  },
});

// abilities 插件
import('/static/plugins/combat/frontend-v2/abilities-component.js');

PluginRegistry.registerPlugin({
  name: 'abilities',
  button: { label: i18n.t('abilities'), icon: null },
  ui: { mode: 'panel', tagName: 'abilities-panel' },
});

// inventory 插件
import('/static/plugins/inventory/frontend-v2/inventory-component.js');
import('/static/plugins/inventory/frontend-v2/inventory-state.js').then(m => {
  AppState.registerSlice(m.createInventoryState);
});

PluginRegistry.registerPlugin({
  name: 'inventory',
  button: { label: i18n.t('inventory'), icon: null },
  ui: { mode: 'panel', tagName: 'inventory-panel' },
  messages: {
    'inventory_state': (msg) => AppState.updateInventory(msg),
    'inventory_action_result': (msg) => {
      if (msg.success) {
        WebSocketService.send({ type: 'inventory_open' });
        if (msg.abilities_changed) {
          WebSocketService.send({ type: 'abilities_open' });
        }
      }
    },
  },
});

// event 插件
import('/static/plugins/event/frontend-v2/event-component.js');
import('/static/plugins/event/frontend-v2/event-state.js').then(m => {
  AppState.registerSlice(m.createEventState);
});

PluginRegistry.registerPlugin({
  name: 'event',
  button: { label: i18n.t('event'), icon: null },
  ui: { mode: 'panel', tagName: 'event-panel' },
  messages: {
    'events_data': (msg) => EventBus.emit('action:events_data', msg),
  },
});

// crafting 插件
import('/static/plugins/crafting/frontend-v2/crafting-component.js');

PluginRegistry.registerPlugin({
  name: 'crafting',
  button: { label: i18n.t('crafting'), icon: null },
  ui: { mode: 'panel', tagName: 'crafting-panel' },
  hidden: true,
});

// === 启动后批量注册消息处理器 ===
PluginRegistry.listAll().forEach(plugin => {
  if (plugin.messages) {
    MessageRouter.registerHandlers(plugin.messages);
  }
});

// 触发 quick-bar 等组件重新渲染（注册表已填充完毕）
AppState.setActivePlugin(null);

// Expose for debugging (dev only)
window.__AppState = AppState;
window.__EventBus = EventBus;

// Wire up WebSocket → MessageRouter
// 注册 ui_labels 消息处理器（在 MessageRouter 之前，确保 i18n 更新优先于组件渲染）
MessageRouter.registerHandlers({
  'ui_labels': (msg) => {
    if (msg.labels) i18n.update(msg.labels);
  },
});

WebSocketService.onMessage = (msg) => MessageRouter.handleMessage(msg);

// 将开场白作为 user 消息发送给 LLM，生成第一条回复
function _sendOpeningAsPlayerInput() {
  const opening = sessionStorage.getItem('opening_narrative');
  if (!opening) return;
  sessionStorage.removeItem('opening_narrative');

  const ws = WebSocketService.socket;
  const content = `【游戏开场。请根据以下背景开始游戏叙事，并通过工具调用初始化角色状态和场景数据。】\n\n${opening}`;
  const send = () => WebSocketService.send({ type: 'player_input', content });

  if (ws && ws.readyState === WebSocket.OPEN) {
    send();
  } else if (ws) {
    const origOnOpen = ws.onopen;
    ws.onopen = (e) => {
      if (origOnOpen) origOnOpen(e);
      send();
    };
  }
}

// Connect when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => {
    WebSocketService.connect();
    _sendOpeningAsPlayerInput();
  });
} else {
  WebSocketService.connect();
  _sendOpeningAsPlayerInput();
}
