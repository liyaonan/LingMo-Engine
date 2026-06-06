// components/narrative-area.js
// 叙述区翻页组件 — 替代旧 pages.js PageManager（998行）
// 负责：page-view 容器架构、消息创建、流式文本渲染、页面导航、遭遇卡片绑定
import { ComponentBase } from '../shared/component-base.js';
import { AppState } from '../state/app-state.js';
import { EventBus } from '../event-bus.js';
import { WebSocketService } from '../services/websocket.js';
import { ContentRenderer } from '../plugins/content-renderer.js';
import { i18n } from '../shared/i18n.js';
import { InteractionCardRegistry } from '../plugins/interaction-registry.js';
import { parseCombatReview } from '/static/plugins/combat/frontend-v2/combat-interaction-cards.js';
import { parseCultivationReview } from '/static/plugins/cultivation/frontend-v2/cultivation-interaction-cards.js';
// 确保插件内容类型在消息到达前注册
import '/static/plugins/combat/frontend-v2/combat-content.js';
import '/static/plugins/combat/frontend-v2/combat-interaction-cards.js';
import '/static/plugins/cultivation/frontend-v2/cultivation-content.js';
import '/static/plugins/cultivation/frontend-v2/cultivation-interaction-cards.js';

const CORE_CSS = `
  :host {
    display: flex;
    align-items: stretch;
    overflow: hidden;
    position: relative;
    flex: 1;
  }
  .page-nav-zone {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 16px;
    flex-shrink: 0;
    cursor: pointer;
    transition: background var(--transition-fast);
    user-select: none;
  }
  .page-nav-zone:hover:not(.disabled) {
    background: rgba(201, 169, 97, 0.06);
  }
  .page-nav-zone.disabled {
    cursor: default;
    opacity: 0.12;
    pointer-events: none;
  }
  .page-nav-arrow {
    font-size: var(--font-size-lg);
    color: var(--color-text-muted);
    font-family: var(--font-narrative);
    opacity: 0;
    transition: opacity var(--transition-fast);
  }
  .page-nav-zone:hover:not(.disabled) .page-nav-arrow {
    color: var(--color-primary);
    opacity: 1;
  }

  .page-container {
    flex: 1;
    overflow-y: auto;
    overflow-x: hidden;
    padding: var(--space-xxl) var(--space-xxl) var(--space-xl);
    min-width: 0;
    scrollbar-width: none;
    -ms-overflow-style: none;
    display: flex;
    flex-direction: column;
  }
  .page-container::-webkit-scrollbar { display: none; }
  #page-content {
    flex: 1;
  }

  .page-view { display: none; animation: fadeIn 0.3s ease; }
  .page-view.active { display: block; }

  .page-empty {
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 200px;
    color: var(--color-text-muted);
    font-family: var(--font-narrative);
    font-size: var(--font-size-narrative);
    font-style: italic;
  }

  .page-player-input {
    text-align: right;
    color: var(--color-mana);
    font-size: var(--font-size-md);
    padding: var(--space-xs) 0 var(--space-md);
    font-family: var(--font-ui);
  }

  .page-narrative {
    font-family: var(--font-narrative);
    font-size: var(--font-size-narrative);
    line-height: 2.0;
    color: var(--color-text);
    animation: fadeIn 0.3s ease;
    word-break: break-word;
  }
  .page-narrative p {
    text-indent: 2em;
    margin: 0;
  }

  .page-narrative.streaming::after {
    content: '\\258E';
    animation: blink-cursor 0.8s steps(1) infinite;
    color: var(--color-primary);
    font-weight: normal;
  }
  @keyframes blink-cursor {
    50% { opacity: 0; }
  }

  .page-narrative.retracted {
    animation: retractOut 0.3s ease-in forwards;
  }
  @keyframes retractOut {
    from { opacity: 1; transform: translateX(0); }
    to { opacity: 0; transform: translateX(-40px); }
  }

  .page-error {
    border: 1px solid var(--color-danger);
    background: var(--color-danger-bg);
    color: var(--color-danger);
    padding: 8px 12px;
    border-radius: var(--radius-md);
    margin: 6px 0;
    font-size: 0.9em;
  }

  @keyframes fadeIn {
    from { opacity: 0; transform: translateY(8px); }
    to { opacity: 1; transform: translateY(0); }
  }

  .msg-block { margin-bottom: 14px; }

  .thinking-block {
    margin-bottom: 12px;
    border-left: 2px solid rgba(201, 169, 97, 0.15);
    padding-left: 10px;
  }
  .thinking-label {
    cursor: pointer;
    font-size: var(--font-size-sm);
    color: var(--color-text-dim);
    font-family: var(--font-ui);
    letter-spacing: 1px;
    user-select: none;
    list-style: none;
    display: flex;
    align-items: center;
    gap: 4px;
  }
  .thinking-label::before {
    content: '\\25B8';
    display: inline-block;
    transition: transform 0.2s;
    font-size: var(--font-size-xs);
  }
  .thinking-block[open] .thinking-label::before {
    transform: rotate(90deg);
  }
  .thinking-content {
    margin-top: 4px;
    padding: 8px;
    background: rgba(0, 0, 0, 0.12);
    border-radius: var(--radius-sm);
    color: var(--color-text-dim);
    font-size: var(--font-size-base);
    line-height: 1.6;
    font-family: var(--font-ui);
    white-space: pre-wrap;
    word-break: break-word;
  }

  .page-indicator {
    text-align: center;
    font-size: var(--font-size-xs);
    color: var(--color-text-muted);
    padding: 10px 0 6px;
    font-family: var(--font-ui);
    letter-spacing: 1px;
  }

  .new-indicator {
    position: absolute;
    bottom: 12px;
    left: 50%;
    transform: translateX(-50%);
    background: var(--color-primary);
    color: var(--color-bg);
    padding: 6px 18px;
    border-radius: var(--radius-sm);
    font-size: var(--font-size-sm);
    font-weight: 600;
    cursor: pointer;
    z-index: 10;
    animation: fadeIn 0.3s ease;
    box-shadow: 0 2px 12px rgba(201, 169, 97, 0.2);
  }
  .new-indicator.hidden { display: none; }

  .page-retry-btn {
    position: absolute;
    bottom: 12px;
    right: 12px;
    padding: 6px 16px;
    border: 1px solid var(--color-primary);
    border-radius: var(--radius-sm);
    background: var(--color-bg);
    color: var(--color-primary);
    font-size: var(--font-size-xs);
    font-family: var(--font-ui);
    cursor: pointer;
    transition: all var(--transition-fast);
    opacity: 0.7;
    z-index: 10;
  }
  .page-retry-btn:hover {
    background: var(--color-primary);
    color: var(--color-bg);
    opacity: 1;
  }
  .page-retry-btn:disabled {
    opacity: 0.3;
    cursor: not-allowed;
  }
  .page-retry-btn.hidden { display: none; }
`;

export class NarrativeArea extends ComponentBase {
  static get observedState() { return ['ui']; }

  constructor() {
    super();
    this._pages = [];
    this._currentPage = -1;
    this._streamPageIdx = -1;
    this._streamBlock = null;
    this._streamBuffer = '';
    this._streamRole = null;
    this._rafId = null;
    this._MAX_PAGES = 200;
    this._committedThinking = '';  // 之前流式会话已提交的思考内容
    this._npcNameMap = new Map();  // name → id
    this._npcRegex = null;
    // 提供给 ContentRenderer 的辅助函数
    this._helpers = {
      esc: (t) => this._esc(t),
      formatNarrative: (t) => this._formatNarrative(t),
      shadowRoot: this.shadowRoot,
      sendMessage: (msg) => WebSocketService.send(msg),
    };
  }

  connectedCallback() {
    super.connectedCallback();
    this._rendered = false;
    this._setupEventListeners();
    this._initialRender();
  }

  disconnectedCallback() {
    if (this._streamTimeoutId) { clearTimeout(this._streamTimeoutId); this._streamTimeoutId = null; }
    if (this._rafId) { cancelAnimationFrame(this._rafId); this._rafId = null; }
    super.disconnectedCallback();
  }

  // ========== 事件监听配置 ==========
  _setupEventListeners() {
    EventBus.on('narrative:message-created', (msg) => {
      if (msg.status === 'deleted') return;
      if (msg.role === 'user') this._onUserMessage(msg);
      else this._onContentMessage(msg);
    });
    EventBus.on('narrative:streaming', (data) => this._onStreamChunk(data));
    EventBus.on('narrative:stream-end', (data) => this._onStreamEnd(data));
    EventBus.on('narrative:stream-discard', (data) => this._onStreamDiscard(data));
    EventBus.on('narrative:stream-retracted', () => this._onStreamRetracted());
    EventBus.on('action:show-opening', (text) => this._createSessionPage(text));
    EventBus.on('action:game-loaded', () => this._clearAllPages());
    EventBus.on('narrative:page-retry', (msg) => this._onPageRetry(msg));
    EventBus.on('action:scene_npc_names', (msg) => {
      if (msg.names) this._updateNpcNames(msg.names);
    });

    // 键盘导航：左右方向键翻页（输入框内不拦截）
    // 使用 composedPath 获取 Shadow DOM 内的真实焦点元素
    document.addEventListener('keydown', (e) => {
      const realTarget = (e.composedPath && e.composedPath()[0]) || e.target;
      const tag = realTarget && realTarget.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
      if (e.key === 'ArrowLeft') { e.preventDefault(); this._navigateRelative(-1); }
      else if (e.key === 'ArrowRight') { e.preventDefault(); this._navigateRelative(1); }
    });

    // NPC 名字点击事件委托（Shadow DOM 内需要 composedPath 获取真实目标）
    this.addEventListener('click', (e) => {
      const realTarget = (e.composedPath && e.composedPath()[0]) || e.target;
      const link = realTarget.closest?.('.npc-link');
      if (!link) return;
      const npcId = parseInt(link.dataset.npcId, 10);
      if (!npcId) return;
      WebSocketService.send({ type: 'get_character', id: npcId });
      AppState.setActivePlugin('character');
    });
  }

  // ========== 状态变更回调 ==========
  _onStateChanged(key, data) {
    if (key === 'ui') {
      const ui = AppState.getUI();
      const indicator = this.shadowRoot.querySelector('.new-indicator');
      if (indicator) indicator.classList.toggle('hidden', !ui.newPageIndicator);
      // 输入恢复（LLM 循环结束）时显示重试按钮，禁用时隐藏
      this._updateRetryButtonVisibility(ui.inputEnabled);
    }
  }

  _onBulkStateChanged(data) {
    if (data && data.narrative) this._rebuildAllPages();
  }

  // ========== 初始渲染 ==========
  _initialRender() {
    const pluginCSS = ContentRenderer.getRegisteredCSS() + InteractionCardRegistry.getRegisteredCSS();
    this._renderHTML(`
      <style>${CORE_CSS}${pluginCSS}</style>
      <div class="page-nav-zone disabled" data-dir="-1"><span class="page-nav-arrow">&#9664;</span></div>
      <div class="page-container" id="page-container">
        <div class="page-empty">${i18n.t('waiting_adventure')}</div>
        <div id="page-content"></div>
        <div class="page-indicator" style="display:none"></div>
      </div>
      <div class="page-nav-zone disabled" data-dir="1"><span class="page-nav-arrow">&#9654;</span></div>
      <div class="new-indicator hidden">&#9660; ${i18n.t('new_replies')}</div>
      <button class="page-retry-btn hidden" title="${i18n.t('retry_tooltip')}">${i18n.t('retry_page')}</button>
    `);

    const self = this;
    // 导航箭头点击
    this.shadowRoot.querySelectorAll('.page-nav-zone').forEach(el => {
      el.addEventListener('click', () => {
        const dir = parseInt(el.dataset.dir);
        if (!el.classList.contains('disabled')) self._navigateRelative(dir);
      });
    });
    // 新回复指示器点击
    this.shadowRoot.querySelector('.new-indicator').addEventListener('click', () => {
      self._navigateTo(self._pages.length - 1);
    });
    // 重试按钮点击
    this.shadowRoot.querySelector('.page-retry-btn').addEventListener('click', () => {
      const btn = self.shadowRoot.querySelector('.page-retry-btn');
      if (btn.disabled) return;
      if (!confirm(i18n.t('confirm_retry'))) return;
      btn.disabled = true;
      const lastPage = self._pages[self._pages.length - 1];
      if (lastPage) {
        WebSocketService.send({
          type: 'retry_page',
          page_id: lastPage.id,
        });
      }
    });
    // 触摸滑动导航
    const container = this.shadowRoot.getElementById('page-container');
    let touchStartX = 0, touchStartY = 0;
    container.addEventListener('touchstart', (e) => {
      touchStartX = e.touches[0].clientX;
      touchStartY = e.touches[0].clientY;
    });
    container.addEventListener('touchend', (e) => {
      const dx = e.changedTouches[0].clientX - touchStartX;
      const dy = e.changedTouches[0].clientY - touchStartY;
      if (Math.abs(dx) > 40 && Math.abs(dx) > Math.abs(dy)) {
        self._navigateRelative(dx < 0 ? 1 : -1);
      }
    });
  }

  // ================================================================
  // 页面创建
  // ================================================================

  /** 用户消息 → 创建新页面（已存在则复用） */
  _onUserMessage(msg) {
    // 优先通过 page_id 查找已存在的页面（历史消息加载）
    if (msg.page_id) {
      for (let i = this._pages.length - 1; i >= 0; i--) {
        if (this._pages[i].id === msg.page_id) {
          const page = this._pages[i];
          page.playerInput = msg.content;
          this._updatePlayerInput(page._container, msg.content);
          if (this._currentPage !== i) this._showPage(i);
          return;
        }
      }
    }
    // 正常流程：创建新页面并切换过去
    const page = this._createPage(msg);
    this._showPage(this._pages.length - 1);
    this._updateRetryButtonVisibility(false);
  }

  /** 创建页面 DOM 容器与数据对象 */
  _createPage(msg) {
    const container = document.createElement('div');
    container.className = 'page-view';
    // combat-review / cultivation-review 等价于玩家输入（折叠卡片），放在页面顶部而非底部交互卡区
    const combatReview = msg.content ? parseCombatReview(msg.content) : null;
    const cultReview = msg.content ? parseCultivationReview(msg.content) : null;
    if (combatReview) {
      const handler = InteractionCardRegistry.getHandler('combat_review');
      if (handler) {
        const cardEl = handler.createCard(msg, this._helpers);
        if (cardEl) container.appendChild(cardEl);
      }
    } else if (cultReview) {
      const handler = InteractionCardRegistry.getHandler('cultivation_review');
      if (handler) {
        const cardEl = handler.createCard(msg, this._helpers);
        if (cardEl) container.appendChild(cardEl);
      }
    } else if (msg.content) {
      const inputEl = document.createElement('div');
      inputEl.className = 'page-player-input';
      inputEl.textContent = '> ' + msg.content;
      container.appendChild(inputEl);
    }
    const interactionSlot = document.createElement('div');
    interactionSlot.className = 'interaction-slot';
    container.appendChild(interactionSlot);

    const contentEl = this.shadowRoot.getElementById('page-content') || this.shadowRoot.getElementById('page-container');
    if (contentEl) contentEl.appendChild(container);

    const page = {
      id: msg.page_id || msg.id,
      playerInput: msg.content || '',
      blocks: [],
      thinkingText: '',
      interactionCard: null,
      _container: container,
      timestamp: msg.timestamp || new Date().toISOString(),
    };
    this._pages.push(page);

    // 页面数量上限保护
    while (this._pages.length > this._MAX_PAGES) {
      const old = this._pages.shift();
      if (old._container) old._container.remove();
    }
    // 新页面创建后通知遭遇卡片：旧页面卡片应失效
    EventBus.emit('narrative:page-changed');
    return page;
  }

  _updatePlayerInput(container, content) {
    // 清除旧的输入或回顾卡
    const oldInput = container.querySelector('.page-player-input');
    const oldCard = container.querySelector('.encounter-card.result-胜利, .encounter-card.result-败北, .encounter-card.result-逃跑, .cultivation-review-card');
    if (oldInput) oldInput.remove();
    if (oldCard) oldCard.remove();

    const combatReview = content ? parseCombatReview(content) : null;
    const cultReview = content ? parseCultivationReview(content) : null;

    if (combatReview) {
      const handler = InteractionCardRegistry.getHandler('combat_review');
      if (handler) {
        const cardEl = handler.createCard({ content, content_blocks: undefined }, this._helpers);
        if (cardEl) container.insertBefore(cardEl, container.firstChild);
      }
    } else if (cultReview) {
      const handler = InteractionCardRegistry.getHandler('cultivation_review');
      if (handler) {
        const cardEl = handler.createCard({ content, content_blocks: undefined }, this._helpers);
        if (cardEl) container.insertBefore(cardEl, container.firstChild);
      }
    } else {
      const inputEl = document.createElement('div');
      inputEl.className = 'page-player-input';
      inputEl.textContent = '> ' + (content || '');
      container.insertBefore(inputEl, container.firstChild);
    }
  }

  // ================================================================
  // 内容消息处理
  // ================================================================

  /** AI 回复 → 在当前页面追加内容块 */
  _onContentMessage(msg) {
    // 跳过内部消息：system / tool 不在叙述区展示，但含交互卡的 system 消息放行
    if ((msg.role === 'system' || msg.role === 'tool') && !this._getInteractionType(msg)) return;
    let page = this._findPage(msg);
    if (!page) return;

    // 提取思考内容并累积到页面级别
    const { thinking, narrative } = this._extractThinking(msg.content || '');
    if (thinking) {
      page.thinkingText = page.thinkingText
        ? page.thinkingText + '\n' + thinking
        : thinking;
      this._renderThinkingBlock(page);
    }

    // 使用去除思考的叙事文本进行去重和渲染
    const cleanMsg = thinking ? { ...msg, content: narrative } : msg;

    // 判断是否为交互卡类型 → 走交互卡路径
    const interactionType = this._getInteractionType(cleanMsg);
    if (interactionType) {
      this._renderInteractionCard(page, cleanMsg, interactionType);
      if (this._isOnLatestPage()) {
        this._scrollToBottom();
      } else {
        AppState.showNewPageIndicator(true);
      }
      return;
    }

    // 原有内容块路径
    if (this._isDuplicateBlock(page, cleanMsg)) return;

    const el = this._createBlockElement(cleanMsg);
    if (el) {
      this._appendBeforeSlot(page, el);
    }
    page.blocks.push(this._blockData(cleanMsg));
    page.timestamp = msg.timestamp || new Date().toISOString();

    if (this._isOnLatestPage()) {
      this._scrollToBottom();
    } else {
      AppState.showNewPageIndicator(true);
    }
  }

  /** 根据 page_id 查找目标页面，不存在则回退到最后一页 */
  _findPage(msg) {
    if (msg.page_id) {
      for (const p of this._pages) {
        if (p.id === msg.page_id) return p;
      }
    }
    // 没有任何页面时，用第一条消息创建首个页面
    if (this._pages.length === 0) {
      const page = this._createPage(msg);
      this._showPage(0);
      return page;
    }
    return this._pages[this._pages.length - 1];
  }

  /** 将内容块插入到 interaction-slot 之前，确保重试按钮和插槽始终在页尾 */
  _appendBeforeSlot(page, el) {
    const container = page._container;
    const refNode = container.querySelector('.page-retry-btn')
      || container.querySelector('.interaction-slot');
    if (refNode) {
      container.insertBefore(el, refNode);
    } else {
      container.appendChild(el);
    }
  }

  /** 检测连续同类型文本是否重复（防止后端重复广播 / 流式结束后 message.created 再次渲染） */
  _isDuplicateBlock(page, msg) {
    if (page.blocks.length === 0) return false;
    const last = page.blocks[page.blocks.length - 1];
    // 核心类型：narrative 和 error 做内容去重
    if (msg.role === 'narrative' && last.type === 'narrative' && last.content === msg.content) return true;
    if (msg.role === 'error' && last.type === 'error' && last.content === msg.content) return true;
    // 插件类型：委托 ContentRenderer 的判断
    const handler = ContentRenderer.getHandler(msg.role);
    if (handler && handler.isDuplicate) {
      return handler.isDuplicate(last, msg);
    }
    return false;
  }

  /** 将消息转换为内部 block 数据 */
  _blockData(msg) {
    // 核心类型
    if (msg.role === 'narrative') return { type: 'narrative', role: msg.role, content: msg.content };
    if (msg.role === 'error') return { type: 'error', role: msg.role, content: msg.content };
    // system / 插件类型：优先委托 ContentRenderer（插件可拦截 system 提取 loot 等）
    const handler = ContentRenderer.getHandler(msg.role);
    if (handler) {
      const data = handler.getBlockData(msg, this._helpers);
      data.role = msg.role; // 保留原始 role 用于编辑重建
      data.content_blocks = msg.content_blocks; // 保留原始 content_blocks 用于编辑重建
      return data;
    }
    // 回退：system 或未知类型 → 通用 narrative
    return { type: 'narrative', role: msg.role, content: msg.content };
  }

  /** 判断消息是否为交互卡类型 */
  _getInteractionType(msg) {
    if (InteractionCardRegistry.hasType(msg.role)) return msg.role;
    if (msg.content_blocks) {
      for (const block of msg.content_blocks) {
        if (InteractionCardRegistry.hasType(block.type)) return block.type;
      }
    }
    return null;
  }

  /** 渲染交互卡到尾部插槽（单一替换） */
  _renderInteractionCard(page, msg, type) {
    const handler = InteractionCardRegistry.getHandler(type);
    const el = handler.createCard(msg, this._helpers);
    if (!el) return;

    const slot = page._container.querySelector('.interaction-slot');
    if (!slot) return;
    slot.innerHTML = '';
    slot.appendChild(el);

    page.interactionCard = handler.getCardData(msg, this._helpers);
    if (page.interactionCard) {
      page.interactionCard.role = msg.role;
      page.interactionCard.content_blocks = msg.content_blocks;
    }
  }

  // ================================================================
  // Block 元素创建
  // ================================================================

  /** 根据消息类型创建对应 DOM 元素 */
  _createBlockElement(msg) {
    // 核心类型
    if (msg.role === 'narrative') {
      const formatted = this._formatNarrative(msg.content || '');
      // 跳过空内容（工具调用过渡文本被裁剪后的空块）
      if (!formatted) return null;
      const el = document.createElement('div');
      el.className = 'page-narrative';
      el.dataset.rawText = msg.content;
      el.innerHTML = formatted;
      return el;
    }
    if (msg.role === 'error') {
      const el = document.createElement('div');
      el.className = 'page-error';
      el.textContent = msg.content || '';
      return el;
    }
    // system / 插件类型：优先委托 ContentRenderer
    const handler = ContentRenderer.getHandler(msg.role);
    if (handler && handler.createBlock) {
      const el = handler.createBlock(msg, this._helpers);
      if (el) return el;
      // Handler 返回 null，回退到文本渲染
    } else if (msg.role !== 'system') {
      // 该 role 无 ContentRenderer handler
    }
    // 回退：通用 narrative
    if (msg.content) {
      const el = document.createElement('div');
      el.className = 'page-narrative';
      el.dataset.rawText = msg.content;
      el.innerHTML = this._formatNarrative(msg.content);
      return el;
    }
    return null;
  }

  // ================================================================
  // 流式文本渲染
  // ================================================================

  /** 流式 chunk → 使用 requestAnimationFrame 批量合并渲染 */
  _onStreamChunk(data) {
    if (!data.delta) return;
    const pageIdx = this._getStreamPageIdx(data);
    if (pageIdx < 0) return;
    const page = this._pages[pageIdx];

    if (!this._streamBlock || this._streamPageIdx !== pageIdx) {
      this._initStreamForPage(page, data);
      this._streamPageIdx = pageIdx;
    }

    this._streamBuffer += data.delta;
    this._resetStreamTimeout();
    const self = this;
    if (!this._rafId) {
      this._rafId = requestAnimationFrame(() => {
        self._rafId = null;
        self._flushStream();
      });
    }
  }

  /** 确定流式内容应渲染到哪个页面 */
  _getStreamPageIdx(data) {
    if (data.page_id) {
      for (let i = 0; i < this._pages.length; i++) {
        if (this._pages[i].id === data.page_id) return i;
      }
    }
    return this._pages.length > 0 ? this._pages.length - 1 : -1;
  }

  /** 初始化流式渲染 block */
  _initStreamForPage(page, data) {
    this._streamRole = data.role || 'narrative';
    this._streamBuffer = '';
    // 保存当前页面已累积的思考内容（用于多轮合并）
    this._committedThinking = page.thinkingText || '';

    // 尝试插件渲染器
    const handler = ContentRenderer.getHandler(data.role);
    if (handler && handler.createStreamBlock) {
      const el = handler.createStreamBlock(data, this._helpers);
      if (el) {
        this._appendBeforeSlot(page, el);
        this._streamBlock = el;
        return;
      }
    }
    // 默认：通用 narrative 流式块
    const el = document.createElement('div');
    el.className = 'page-narrative streaming';
    this._appendBeforeSlot(page, el);
    this._streamBlock = el;
  }

  /** 将累积的 buffer 刷新到 DOM */
  _flushStream() {
    if (!this._streamBlock) return;

    // 提取思考内容，与之前轮次合并后渲染为页面级折叠块
    const { thinking, narrative } = this._extractThinking(this._streamBuffer);
    if (this._streamPageIdx >= 0 && this._streamPageIdx < this._pages.length) {
      const page = this._pages[this._streamPageIdx];
      const merged = this._committedThinking
        ? this._committedThinking + '\n' + thinking
        : thinking;
      if (merged) {
        page.thinkingText = merged;
        this._renderThinkingBlock(page);
      }
    }

    // 仅渲染叙事内容
    const handler = ContentRenderer.getHandler(this._streamRole);
    if (handler && handler.flushStreamBlock) {
      handler.flushStreamBlock(this._streamBlock, narrative, this._helpers);
    } else {
      this._streamBlock.dataset.rawText = narrative;
      this._streamBlock.innerHTML = this._formatNarrative(narrative);
    }
    if (this._isOnLatestPage()) this._scrollToBottom();
  }

  /** 流式结束：刷新剩余 buffer，移除 streaming 样式，记录到 blocks 防止后续 message.created 重复 */
  _onStreamEnd(data) {
    if (this._streamTimeoutId) { clearTimeout(this._streamTimeoutId); this._streamTimeoutId = null; }
    if (this._rafId) { cancelAnimationFrame(this._rafId); this._rafId = null; }

    // 如果之前没有收到 streaming chunk（_streamBlock 为 null），
    // 例如服务端直接发送完整 content 而没有任何 delta 块到达，
    // 需要先初始化 stream block 再渲染，否则 _flushStream 会直接返回
    if (!this._streamBlock) {
      const pageIdx = this._getStreamPageIdx(data);
      if (pageIdx >= 0) {
        const page = this._pages[pageIdx];
        this._initStreamForPage(page, data);
        this._streamPageIdx = pageIdx;
      }
    }

    this._streamBuffer = this._streamBuffer || data.content || '';
    this._flushStream();

    // 流式结束后检查内容是否为空（工具调用过渡文本被裁剪）
    if (this._streamBlock && !this._streamBlock.innerHTML.trim()) {
      this._streamBlock.remove();
      this._streamBlock = null;
      this._streamBuffer = '';
      this._streamPageIdx = -1;
      this._streamRole = null;
      return;
    }

    if (this._streamBlock) this._streamBlock.classList.remove('streaming');

    // 将流式内容写入 page.blocks，防止后续 message.created 重复追加
    // 优先使用 data.content（后端最终内容），确保与 message.created 的 msg.content 一致以通过去重
    const rawContent = (data.content || '').replace(/<thinking>[\s\S]*?(<\/thinking>|$)/gi, '').trim();
    const finalContent = rawContent || this._streamBuffer.replace(/<thinking>[\s\S]*?(<\/thinking>|$)/gi, '').trim();
    if (finalContent && this._streamPageIdx >= 0 && this._streamPageIdx < this._pages.length) {
      const page = this._pages[this._streamPageIdx];
      // 使用插件 handler 的 getBlockData 或回退为 narrative
      const handler = ContentRenderer.getHandler(this._streamRole);
      if (handler && handler.getBlockData) {
        const bd = handler.getBlockData({ role: this._streamRole, content: finalContent, content_blocks: [] }, this._helpers);
        bd.role = this._streamRole;
        page.blocks.push(bd);
      } else {
        page.blocks.push({ type: 'narrative', role: this._streamRole, content: finalContent });
      }
    }

    this._streamBlock = null;
    this._streamBuffer = '';
    this._streamPageIdx = -1;
    this._streamRole = null;
    this._committedThinking = '';
  }

  /** 流式丢弃：安全网(3A/3B)触发重试时，移除已流式输出到前端的内容 */
  _onStreamDiscard(data) {
    // 先正常结束流式状态
    this._onStreamEnd(data);
    // 找到当前页最后一个 narrative 块并移除（即刚被 STREAM_END 写入的那个）
    const pageIdx = this._getStreamPageIdx(data);
    if (pageIdx >= 0 && pageIdx < this._pages.length) {
      const page = this._pages[pageIdx];
      // 从 blocks 末尾移除
      if (page.blocks.length > 0) {
        page.blocks.pop();
      }
      // 从 DOM 移除最后一个 narrative 元素
      const container = page._container;
      if (container) {
        const narrativeEls = container.querySelectorAll('.page-narrative');
        if (narrativeEls.length > 0) {
          narrativeEls[narrativeEls.length - 1].remove();
        }
      }
    }
  }

  /** 流式撤回：标记后延迟移除 */
  _onStreamRetracted() {
    if (this._streamBlock) {
      this._streamBlock.classList.add('retracted');
      const el = this._streamBlock;
      setTimeout(() => { if (el.parentNode) el.parentNode.removeChild(el); }, 300);
    }
    this._streamBlock = null;
    this._streamBuffer = '';
    this._streamPageIdx = -1;
    this._streamRole = null;
  }

  /** 流式空闲超时：60秒内无新 chunk 则自动终止流式状态 */
  _resetStreamTimeout() {
    if (this._streamTimeoutId) clearTimeout(this._streamTimeoutId);
    this._streamTimeoutId = setTimeout(() => {
      console.warn('[NarrativeArea] 流式空闲超时(60s)，自动终止');
      this._streamTimeoutId = null;
      const data = { role: this._streamRole || 'narrative', content: '' };
      if (this._streamPageIdx >= 0 && this._streamPageIdx < this._pages.length) {
        data.page_id = this._pages[this._streamPageIdx].id;
      }
      this._onStreamEnd(data);
    }, 60000);
  }

  // ================================================================
  // 页面导航
  // ================================================================

  /** 切换到指定页面并更新导航栏 */
  _showPage(index) {
    if (index < 0 || index >= this._pages.length) return;
    this._currentPage = index;
    AppState.showNewPageIndicator(false);
    this._renderNav();
    for (let i = 0; i < this._pages.length; i++) {
      this._pages[i]._container.classList.toggle('active', i === index);
    }
    // 通知遭遇卡片更新状态：最新页可用，非最新页禁用
    EventBus.emit('narrative:page-changed');

    // 非最新页时隐藏重试按钮
    if (index !== this._pages.length - 1) {
      this._updateRetryButtonVisibility(false);
    } else {
      const ui = AppState.getUI();
      this._updateRetryButtonVisibility(ui.inputEnabled);
    }
  }

  _navigateTo(index) { this._showPage(index); }

  _navigateRelative(delta) {
    const target = this._currentPage + delta;
    if (target >= 0 && target < this._pages.length) this._navigateTo(target);
  }

  _isOnLatestPage() {
    return this._pages.length === 0 || this._currentPage === this._pages.length - 1;
  }

  /** 更新导航栏箭头、页码、操作按钮状态 */
  _renderNav() {
    const total = this._pages.length;
    const cur = this._currentPage;
    const left = this.shadowRoot.querySelector('.page-nav-zone[data-dir="-1"]');
    const right = this.shadowRoot.querySelector('.page-nav-zone[data-dir="1"]');
    const indicator = this.shadowRoot.querySelector('.page-indicator');
    const empty = this.shadowRoot.querySelector('.page-empty');

    if (empty) empty.style.display = total === 0 ? '' : 'none';
    if (left) left.classList.toggle('disabled', cur <= 0);
    if (right) right.classList.toggle('disabled', cur >= total - 1);
    if (indicator) {
      indicator.style.display = total > 0 ? '' : 'none';
      indicator.textContent = total > 0 ? i18n.t('page_indicator', { current: cur + 1, total }) : '';
    }
  }

  _scrollToBottom() {
    const container = this.shadowRoot.getElementById('page-container');
    if (container) container.scrollTop = container.scrollHeight;
  }

  // ================================================================
  // 会话开场页
  // ================================================================

  /** 创建会话开场页面（清空所有旧页面） */
  _createSessionPage(content) {
    this._pages.forEach(p => p._container?.remove());
    this._pages = [];
    this._currentPage = -1;

    const container = document.createElement('div');
    container.className = 'page-view active';
    const inputEl = document.createElement('div');
    inputEl.className = 'page-player-input';
    inputEl.textContent = '> ';
    container.appendChild(inputEl);
    if (content) {
      const nel = document.createElement('div');
      nel.className = 'page-narrative';
      nel.dataset.rawText = content;
      nel.innerHTML = this._formatNarrative(content);
      container.appendChild(nel);
    }
    const sessionSlot = document.createElement('div');
    sessionSlot.className = 'interaction-slot';
    container.appendChild(sessionSlot);
    const contentEl = this.shadowRoot.getElementById('page-content') || this.shadowRoot.getElementById('page-container');
    if (contentEl) contentEl.appendChild(container);

    this._pages.push({
      id: 'page_' + Date.now().toString(36),
      playerInput: '',
      blocks: content ? [{ type: 'narrative', role: 'narrative', content }] : [],
      thinkingText: '',
      interactionCard: null,
      _container: container,
      timestamp: new Date().toISOString(),
    });
    this._currentPage = 0;
    this._renderNav();
  }

  // ================================================================
  // Debug / 调试功能
  // ================================================================

  /** 向当前页追加调试文本 */
  _addDebugText(text) {
    const page = this._pages.length > 0 ? this._pages[this._pages.length - 1] : null;
    if (!page) return;
    const el = document.createElement('div');
    el.className = 'page-narrative';
    el.textContent = text;
    this._appendBeforeSlot(page, el);
    page.blocks.push({ type: 'narrative', role: 'narrative', content: text });
    this._scrollToBottom();
  }

  // ================================================================
  // 从缓存重建（F5 刷新后恢复 / 加载存档）
  // ================================================================

  /** 清除所有页面 DOM 和内部状态（加载存档时调用） */
  _clearAllPages() {
    this._pages.forEach(p => p._container?.remove());
    this._pages = [];
    this._currentPage = -1;
    this._streamBlock = null;
    this._streamBuffer = '';
    this._streamPageIdx = -1;
    this._streamRole = null;
    this._committedThinking = '';
    if (this._rafId) { cancelAnimationFrame(this._rafId); this._rafId = null; }
    if (this._streamTimeoutId) { clearTimeout(this._streamTimeoutId); this._streamTimeoutId = null; }
    this._renderNav();
  }

  /** 根据条件更新重试按钮可见性 */
  _updateRetryButtonVisibility(show) {
    const btn = this.shadowRoot.querySelector('.page-retry-btn');
    if (!btn) return;
    // 仅在最新页 + 非流式状态时显示
    const isLastPage = this._currentPage === this._pages.length - 1;
    btn.classList.toggle('hidden', !(show && isLastPage));
    if (show && isLastPage) btn.disabled = false;
  }

  /** 处理后端 page_retry 事件 */
  _onPageRetry(msg) {
    const { page_id, user_input } = msg;

    // 1. 从 _pages 中删除该 Page
    const idx = this._pages.findIndex(p => p.id === page_id);
    if (idx !== -1) {
      this._pages[idx]._container?.remove();
      this._pages.splice(idx, 1);
    }

    // 2. 导航到前一个 Page
    if (this._pages.length > 0) {
      this._currentPage = Math.min(idx, this._pages.length - 1);
      this._showPage(this._currentPage);
    } else {
      this._currentPage = -1;
    }
    this._renderNav();

    // 3. 重新发送原始输入（走完整的新 Page 创建流程）
    if (user_input) {
      WebSocketService.send({
        type: 'message',
        action: 'create',
        message: {
          id: 'msg_' + Date.now().toString(36) + '_' + Math.random().toString(36).slice(2, 10),
          role: 'user',
          content: user_input,
          page_id: 'page_' + Date.now().toString(36),
        },
      });
    }
  }

  /** 从 AppState narrative 切片重建所有页面 */
  _rebuildAllPages() {
    this._pages.forEach(p => p._container?.remove());
    this._pages = [];
    this._currentPage = -1;

    const narrative = AppState.getNarrative();
    const msgs = narrative.messages;
    // narrative-slice getState() 返回 [key, value] 条目数组
    const sorted = [...msgs]
      .filter(([, m]) => m.status !== 'deleted')
      .sort(([, a], [, b]) => (a.timestamp || '') < (b.timestamp || '') ? -1 : 1);

    for (const [, msg] of sorted) {
      if (msg.role === 'user') this._createPage(msg);
      else this._onContentMessage(msg);
    }
    if (this._pages.length > 0) this._showPage(this._pages.length - 1);
    this._renderNav();
  }

  /** 等待消息批量到达后重建（用于 F5 恢复） */
  _rebuildFromMessages() {
    const narrative = AppState.getNarrative();
    const msgs = narrative.messages;
    if (!msgs || msgs.length === 0) return;
    this._rebuildAllPages();
  }

  // ================================================================
  // 渲染辅助函数 —— HTML 格式化与转义
  // ================================================================

  /**
   * 从文本中提取指定标签包裹的内容。
   * 支持多标签块和未闭合标签（流式传输）。
   */
  _extractTagContent(text, openTag, closeTag) {
    if (!text) return text;
    const parts = [];
    let searchStart = 0;
    while (searchStart < text.length) {
      const openIdx = text.indexOf(openTag, searchStart);
      if (openIdx === -1) break;
      const contentStart = openIdx + openTag.length;
      const closeIdx = text.indexOf(closeTag, contentStart);
      if (closeIdx !== -1) {
        parts.push(text.substring(contentStart, closeIdx));
        searchStart = closeIdx + closeTag.length;
      } else {
        // 未闭合：流式传输中，取标签后全部内容
        parts.push(text.substring(contentStart));
        break;
      }
    }
    return parts.length > 0 ? parts.join('\n') : text;
  }

  /**
   * 提取叙事内容：从 <p> 标签中提取正文，丢弃无标签的过渡性文字。
   */
  _extractNarrative(text) {
    if (!text) return text;
    const pContent = this._extractTagContent(text, '<p>', '</p>');
    if (pContent !== text) return pContent;
    // 无 <p> 标签，丢弃（可能是AI调用技能输出的过渡性文字）
    return '';
  }

  /**
   * 格式化叙述文本：
   * - 提取 <p> 标签内容
   * - 转义 HTML 特殊字符，但保留 LLM 输出的 <br> 标签
   * - \n → <br>（段落分隔）
   * - 【xxx】→ 高亮关键词
   * - 《xxx》→ 毒属性标记
   */
  _updateNpcNames(names) {
    this._npcNameMap.clear();
    for (const { id, name } of names) {
      if (name) this._npcNameMap.set(name, id);
    }
    // 按名字长度降序构建正则，避免短名字截断长名字
    const sorted = [...this._npcNameMap.keys()].sort((a, b) => b.length - a.length);
    if (sorted.length === 0) {
      this._npcRegex = null;
      return;
    }
    const pattern = sorted.map(n => n.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|');
    this._npcRegex = new RegExp(pattern, 'g');
    // 重新渲染当前页所有叙事块
    this._rebindNpcLinks();
  }

  /** 用当前 NPC 名字缓存重新渲染所有页面的叙事块。 */
  _rebindNpcLinks() {
    if (!this._npcRegex) return;
    for (const page of this._pages) {
      const blocks = page._container.querySelectorAll('.page-narrative[data-raw-text]');
      for (const block of blocks) {
        block.innerHTML = this._formatNarrative(block.dataset.rawText);
      }
    }
  }

  _formatNarrative(text) {
    if (!text) return '';
    const extracted = this._extractNarrative(text);
    const safe = this._esc(extracted)
      .replace(/&lt;br\s*\/?&gt;/gi, '\n')
      .replace(/&lt;(\/?)(em|strong|b|i)&gt;/gi, '<$1$2>');
    // 按换行拆分为段落，每段用 <p> 包裹以实现首行缩进
    const paragraphs = safe.split(/\n+/).filter(p => p.trim());
    return paragraphs
      .map(p => p
        .replace(this._npcRegex || /(?!)/g, (match) => {
          const npcId = this._npcNameMap.get(match);
          if (npcId == null) return match;
          return `<span class="npc-link" data-npc-id="${npcId}" style="color:var(--color-secondary);cursor:pointer;border-bottom:1px dashed var(--color-secondary)">${match}</span>`;
        })
        .replace(/【([^】]+)】/g, '<span style="color:var(--color-secondary);font-weight:bold">【$1】</span>')
        .replace(/《([^》]+)》/g, '<span style="color:var(--color-poison)">《$1》</span>'))
      .map(p => `<p>${p}</p>`)
      .join('');
  }

  // ================================================================
  // 思考内容（页面级合并）
  // ================================================================

  /** 从文本中提取思考内容和叙事内容 */
  _extractThinking(text) {
    if (!text) return { thinking: '', narrative: '' };
    const thinkingContent = this._extractTagContent(text, '<thinking>', '</thinking>');
    const hasThinking = thinkingContent !== text;
    const narrative = hasThinking
      ? text.replace(/<thinking>[\s\S]*?(<\/thinking>|$)/gi, '').trim()
      : text;
    return { thinking: hasThinking ? thinkingContent : '', narrative };
  }

  /** 渲染/更新页面顶部的思考折叠块 */
  _renderThinkingBlock(page) {
    const showThinking = AppState.getUI().showThinking !== false;
    const existingEl = page._container.querySelector('.thinking-block');

    // 设置关闭或无内容：移除已有块
    if (!showThinking || !page.thinkingText) {
      if (existingEl) existingEl.remove();
      return;
    }

    // 已有块：原地更新内容，避免每次 flush 重建 DOM
    if (existingEl) {
      const contentEl = existingEl.querySelector('.thinking-content');
      if (contentEl) {
        contentEl.innerHTML = this._esc(page.thinkingText).replace(/\n/g, '<br>');
      }
      return;
    }

    // 首次创建思考折叠块，插入到玩家输入之后
    const thinkingEl = document.createElement('details');
    thinkingEl.className = 'thinking-block';
    thinkingEl.innerHTML = `<summary class="thinking-label">${i18n.t('thinking_process')}</summary><div class="thinking-content">${this._esc(page.thinkingText).replace(/\n/g, '<br>')}</div>`;

    // 查找页面顶部锚点（玩家输入或回顾卡片），确保思考块在其之后
    const anchor = page._container.querySelector('.page-player-input')
      || page._container.querySelector('.encounter-card[class*="result-"]')?.parentElement
      || page._container.querySelector('.cultivation-review-card')?.parentElement;
    if (anchor?.nextSibling) {
      page._container.insertBefore(thinkingEl, anchor.nextSibling);
    } else if (anchor) {
      page._container.appendChild(thinkingEl);
    } else {
      // 无锚点时插入到容器最前面
      page._container.prepend(thinkingEl);
    }
  }

}

customElements.define('narrative-area', NarrativeArea);
