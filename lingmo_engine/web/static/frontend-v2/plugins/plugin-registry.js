// plugins/plugin-registry.js — 插件前端注册中心
// 插件通过此注册中心声明：按钮、UI组件、状态切片、消息处理器

const _plugins = new Map();
const _systemButtons = { left: [], right: [] };

export const PluginRegistry = {
  registerPlugin(config) {
    if (!config || !config.name) {
      throw new Error('PluginRegistry.registerPlugin: config.name is required');
    }
    const entry = {
      name: config.name,
      system: config.system || false,
      hidden: config.hidden || false,
      position: config.position || null,
      button: config.button,
      ui: config.ui,
      stateSlice: config.stateSlice || null,
      messages: config.messages || null,
      _registeredAt: Date.now(),
    };
    if (config.system) {
      const side = config.position === 'right' ? 'right' : 'left';
      _systemButtons[side].push(entry);
    } else {
      _plugins.set(config.name, entry);
    }
  },

  getPlugin(name) {
    return _plugins.get(name)
      || _systemButtons.left.find(p => p.name === name)
      || _systemButtons.right.find(p => p.name === name)
      || null;
  },

  // 向后兼容别名 — plugin-host.js:38 调用 PluginRegistry.get(name)
  get(name) { return this.getPlugin(name); },

  has(name) {
    return _plugins.has(name)
      || _systemButtons.left.some(p => p.name === name)
      || _systemButtons.right.some(p => p.name === name);
  },

  listPlugins() {
    return Array.from(_plugins.values())
      .sort((a, b) => a._registeredAt - b._registeredAt);
  },

  // 向后兼容 — 测试调用 PluginRegistry.list() 期望返回名字数组
  list() { return this.listPlugins().map(p => p.name); },

  listAll() {
    return [
      ..._systemButtons.left,
      ...Array.from(_plugins.values()).sort((a, b) => a._registeredAt - b._registeredAt),
      ..._systemButtons.right,
    ];
  },

  // 旧 API 兼容（server.py PLUGIN_MODULES 生成调用 register() 而非 registerPlugin()）
  register(name, config) {
    _plugins.set(name, {
      name,
      system: false,
      position: null,
      button: { label: name, icon: null },
      ui: { mode: 'overlay', tagName: config.tagName },
      stateSlice: config.stateSlice || null,
      component: config.component || null,
      messages: null,
      _registeredAt: Date.now(),
    });
  },
};
