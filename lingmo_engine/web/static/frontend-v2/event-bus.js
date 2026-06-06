// event-bus.js — 跨组件事件总线，替代旧的 PluginRouter
const _listeners = new Map();

export const EventBus = {
  on(event, callback) {
    if (!_listeners.has(event)) {
      _listeners.set(event, new Set());
    }
    _listeners.get(event).add(callback);
  },

  off(event, callback) {
    const cbs = _listeners.get(event);
    if (cbs) cbs.delete(callback);
  },

  emit(event, data) {
    const cbs = _listeners.get(event);
    if (cbs) cbs.forEach(fn => {
      try { fn(data); } catch (e) { console.error('EventBus:', event, e); }
    });
  },

  /** 清除所有监听器（仅用于测试/重置） */
  clear() {
    _listeners.clear();
  },
};
