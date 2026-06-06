import { describe, it, expect, beforeEach, vi } from 'vitest';

// Mock 浏览器全局对象 (vitest node 环境下无 sessionStorage)
vi.stubGlobal('sessionStorage', {
  _store: {},
  setItem(key, val) { this._store[key] = String(val); },
  getItem(key) { return this._store[key] || null; },
  removeItem(key) { delete this._store[key]; },
  clear() { this._store = {}; },
});

// Mock AppState
const mockSetInputEnabled = vi.fn();
const mockSetStateUpdate = vi.fn();
const mockUpdateWorld = vi.fn();
const mockSetAttributesSchema = vi.fn();
const mockSetCharacterData = vi.fn();
const mockStartCombat = vi.fn();
const mockUpdateCombat = vi.fn();
const mockSetCombatActive = vi.fn();
const mockAddMessage = vi.fn();
const mockAppendStream = vi.fn();
const mockEndStream = vi.fn();
const mockDeleteMessage = vi.fn();
const mockUpdateMessage = vi.fn();
const mockClearNarrative = vi.fn();

vi.mock('../../state/app-state.js', () => ({
  AppState: {
    setInputEnabled: (...args) => mockSetInputEnabled(...args),
    setStateUpdate: (...args) => mockSetStateUpdate(...args),
    updateWorld: (...args) => mockUpdateWorld(...args),
    setAttributesSchema: (...args) => mockSetAttributesSchema(...args),
    setCharacterData: (...args) => mockSetCharacterData(...args),
    startCombat: (...args) => mockStartCombat(...args),
    updateCombat: (...args) => mockUpdateCombat(...args),
    setCombatActive: (...args) => mockSetCombatActive(...args),
    addMessage: (...args) => mockAddMessage(...args),
    appendStream: (...args) => mockAppendStream(...args),
    endStream: (...args) => mockEndStream(...args),
    deleteMessage: (...args) => mockDeleteMessage(...args),
    updateMessage: (...args) => mockUpdateMessage(...args),
    clearNarrative: (...args) => mockClearNarrative(...args),
    updateInventory: vi.fn(),
    updateAbilities: vi.fn(),
  },
}));

// Mock EventBus
const mockEventBusEmit = vi.fn();
vi.mock('../../event-bus.js', () => ({
  EventBus: {
    emit: (...args) => mockEventBusEmit(...args),
  },
}));

// Mock WebSocketService
const mockWsSend = vi.fn();
vi.mock('../../services/websocket.js', () => ({
  WebSocketService: {
    send: (...args) => mockWsSend(...args),
  },
}));

// 动态 import 确保 mock 先生效
const { MessageRouter } = await import('../../services/message-router.js');

describe('MessageRouter', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('input_state 消息调用 setInputEnabled', () => {
    MessageRouter.handleMessage({ type: 'input_state', enabled: false });
    expect(mockSetInputEnabled).toHaveBeenCalledWith(false);
  });

  it('input_state 默认 enabled=true', () => {
    MessageRouter.handleMessage({ type: 'input_state' });
    expect(mockSetInputEnabled).toHaveBeenCalledWith(true);
  });

  it('state_update 调用 setStateUpdate 和 updateWorld', () => {
    const data = { player: { name: '勇者' }, location: '森林' };
    MessageRouter.handleMessage({ type: 'state_update', data });
    expect(mockSetStateUpdate).toHaveBeenCalledWith(data);
    expect(mockUpdateWorld).toHaveBeenCalledWith(data);
  });

  it('attributes_schema 调用 setAttributesSchema', () => {
    const schema = { hp: { type: 'number' } };
    MessageRouter.handleMessage({ type: 'attributes_schema', data: schema });
    expect(mockSetAttributesSchema).toHaveBeenCalledWith(schema);
  });

  it('character_data 调用 setCharacterData', () => {
    MessageRouter.handleMessage({
      type: 'character_data',
      character: { name: '勇者' },
      panel_config: { sections: [] },
      abilities: { fireball: {} },
      equipment_expanded: { weapon: true },
    });
    const args = mockSetCharacterData.mock.calls[0];
    expect(args[0]).toEqual({ name: '勇者' });
    expect(args[1]).toEqual({ sections: [] });
    expect(args[2]).toEqual({ fireball: {} });
    expect(args[3]).toEqual({ weapon: true });
  });

  it('combat_start 调用 startCombat', () => {
    const state = { enemies: [], phase: 'start' };
    MessageRouter.handleMessage({ type: 'combat_start', state });
    expect(mockStartCombat).toHaveBeenCalledWith(state);
  });

  it('combat_state_update 非终端阶段不调用 setCombatActive', () => {
    MessageRouter.handleMessage({
      type: 'combat_state_update',
      state: { phase: 'player_turn' },
    });
    expect(mockUpdateCombat).toHaveBeenCalled();
    expect(mockSetCombatActive).not.toHaveBeenCalled();
  });

  it('game_loaded 调用 clearNarrative 并 emit 事件', () => {
    MessageRouter.handleMessage({ type: 'game_loaded' });
    expect(mockClearNarrative).toHaveBeenCalled();
    expect(mockEventBusEmit).toHaveBeenCalledWith('action:game-loaded', null);
  });

  it('message.event message.created 调用 addMessage', () => {
    const data = { id: 'm1', role: 'assistant', content: 'Hello' };
    MessageRouter.handleMessage({
      type: 'message.event',
      event: 'message.created',
      data,
    });
    expect(mockAddMessage).toHaveBeenCalledWith(data);
    expect(mockEventBusEmit).toHaveBeenCalledWith('narrative:message-created', data);
  });

  it('message.event message.streaming 调用 appendStream', () => {
    MessageRouter.handleMessage({
      type: 'message.event',
      event: 'message.streaming',
      data: { delta: 'Hello' },
    });
    expect(mockAppendStream).toHaveBeenCalledWith('Hello');
  });

  it('message.event message.stream_end 调用 endStream', () => {
    MessageRouter.handleMessage({
      type: 'message.event',
      event: 'message.stream_end',
      data: { content: '完整内容' },
    });
    expect(mockEndStream).toHaveBeenCalledWith('完整内容');
  });

  it('message.event message.deleted 调用 deleteMessage', () => {
    MessageRouter.handleMessage({
      type: 'message.event',
      event: 'message.deleted',
      data: { id: 'm1' },
    });
    expect(mockDeleteMessage).toHaveBeenCalledWith('m1');
  });

  it('unknown type 发射 ws: 前缀事件', () => {
    const msg = { type: 'custom_event', payload: 42 };
    MessageRouter.handleMessage(msg);
    expect(mockEventBusEmit).toHaveBeenCalledWith('ws:custom_event', msg);
  });

  it('sendUserInput 发送正确格式的 WebSocket 消息', () => {
    vi.spyOn(Date, 'now').mockReturnValue(1700000000000);
    MessageRouter.sendUserInput('你好');
    expect(mockWsSend).toHaveBeenCalled();
    const callArg = mockWsSend.mock.calls[0][0];
    expect(callArg.type).toBe('message');
    expect(callArg.action).toBe('create');
    expect(callArg.message.role).toBe('user');
    expect(callArg.message.content).toBe('你好');
    expect(callArg.message.id).toBeDefined();
    expect(callArg.message.page_id).toBeDefined();
  });
});
