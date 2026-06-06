// shared/i18n.js
// UI 文本国际化模块 — 默认中文标签，支持世界配置动态覆盖

/** @type {Record<string, string>} */
const _labels = {
  // 状态栏
  hp: '生命',
  mp: '灵力',
  level: '等级',
  // 战斗
  spiritual_power: '灵力',
  // 装备
  element: '元素',
  cultivation_path: '道途',
  secondary_path: '辅修',
  spiritual_roots: '灵根',
  equip_requirements: '装备要求',
  // 系统按钮
  character: '角色',
  save: '存档',
  settings: '系统',
  combat: '战斗',
  abilities: '技能',
  inventory: '背包',
  event: '事件',
  crafting: '炼器',
  cultivation: '修炼',

  // 存档面板
  save_management: '存档管理',
  import_save: '导入存档',
  save_progress: '保存当前进度',
  save_as_new: '另存为新槽位',
  loading: '加载中...',
  save_name: '存档名称',
  save_default_name: '存档',
  no_saves: '暂无存档',
  autosave_prefix: '[自动] ',
  confirm_load: '加载存档 "{name}"？当前未保存的进度将丢失。',
  confirm_delete: '确定删除存档 "{name}"？此操作不可撤销。',
  import_success: '存档导入成功: {id}',
  import_failed: '导入失败: {error}',
  delete_failed: '删除失败: {error}',
  unknown_error: '未知错误',
  load: '加载',
  export: '导出',
  delete: '删除',
  save_config: '保存配置',

  // 设置面板
  close: '关闭',
  test_connection: '测试连接',
  model: '模型',
  model_placeholder: '手动输入模型名称',
  provider_openai_compatible: 'OpenAI 兼容',
  model_fetch: '获取',
  model_empty_option: '-- 手动输入或拉取模型列表 --',
  model_custom_option: '-- 手动输入 --',
  provider_label: 'LLM 服务商',
  base_url_label: 'API 地址',
  api_key_label: 'API 密钥',
  temperature_label: '温度',
  max_tokens_label: '最大令牌',
  stream_label: '流式输出（逐字显示 LLM 生成内容）',
  show_thinking_label: '显示思考过程（在叙述区展示 LLM 推理内容）',
  tab_default: '默认推理',
  tab_fast: '快速推理',
  tab_ui: '界面',
  font_scale_label: '文字大小倍率',
  font_scale_desc: '调整全局文字大小。更改后立即生效，刷新页面后保持。',
  saving: '保存中...',
  testing: '测试中...',
  api_key_required: '请先填写 API 密钥',
  fetching_models: '正在拉取模型列表...',
  config_saved: '配置已保存',
  save_failed: '保存失败',
  connection_success: '连接成功',
  connection_failed: '连接失败',
  models_fetched: '已获取 {count} 个模型',
  no_models: '未获取到模型',

  // 叙事区
  input_placeholder: '输入你的行动...',
  input_busy: '等待回复中...',
  send: '发送',
  request_processing: '请求处理中，请等待完成后再试',
  retry_page: '重试本页',
  retry_tooltip: '回滚到本页创建前的状态并重新生成',
  thinking_process: '思考过程',
  waiting_adventure: '等待冒险开始...',
  new_replies: '有新回复',
  confirm_retry: '回滚到本页创建前的状态并重新生成？',
  page_indicator: '页 {current}/{total}',

  // 场景区
  parent_area: '上级',
  child_area: '子区域',
  adjacent: '相邻',

  // 遭遇卡片
  encounter_ended: '已结束',
  encounter_start: '点击开始',
  encounter_view_detail: '点击查看详情',

  // 标题画面
  start_game: '开始游戏',
  load_save: '加载存档',
  title_settings: '配置',

  // 角色创建
  character_creation: '角色创建',
  connecting: '正在连接游戏服务器…',

  // 通用面板
  panel_close: '关闭',

  // 数字单位
  unit_wan: '万',
  unit_yi: '亿',
  relationship_unknown: '未知',

  // 隐藏/显示
  hide: '隐藏',
  show: '显示',

  // 错误提示
  error_auth_failed: 'LLM API 密钥无效或未配置，请在设置页面检查 API Key 和 Base URL 配置。',

  // 角色/渲染器
  no_data: '暂无',
  no_equipment: '无装备',
  no_skills: '无技能',
  no_memories: '暂无记忆',
  no_relationships: '暂无人脉',
  unknown: '未知',
  memory_shared_experiences: '共同经历',
  memory_personal_events: '个人大事',
  memory_opinions: '内心真实想法',
  male: '男',
  female: '女',
  years_old: '岁',
};

// 服务端注入的 ui_labels（HTML 内联脚本优先于模块加载）
if (window.__UI_LABELS) {
  Object.assign(_labels, window.__UI_LABELS);
}

export const i18n = {
  /** 根据 key 获取翻译文本，未找到则返回 key 本身 */
  t(key, params) {
    let text = _labels[key] || key;
    if (params) {
      for (const [k, v] of Object.entries(params)) {
        text = text.replace(`{${k}}`, v);
      }
    }
    return text;
  },

  /** 合并新的标签映射（来自世界配置 ui_labels） */
  update(newLabels) {
    Object.assign(_labels, newLabels);
  },
};
