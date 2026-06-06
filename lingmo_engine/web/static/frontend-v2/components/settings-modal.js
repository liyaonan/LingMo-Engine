import { ComponentBase } from '../shared/component-base.js';
import { AppState } from '../state/app-state.js';
import { WebSocketService } from '../services/websocket.js';
import { EventBus } from '../event-bus.js';
import { i18n } from '../shared/i18n.js';

const CSS = `
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  .backdrop {
    display: flex; align-items: center; justify-content: center;
    width: 100%; height: 100%;
  }
  .modal {
    background: var(--color-surface); border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-lg); width: 90%; max-width: 420px; max-height: 85vh;
    display: flex; flex-direction: column;
    overflow-y: auto;
    scrollbar-width: none;
    -ms-overflow-style: none;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.6);
  }
  .modal::-webkit-scrollbar { display: none; }
  .header {
    display: flex; justify-content: space-between; align-items: center;
    padding: 14px var(--space-xl); border-bottom: 1px solid var(--color-border-light);
    color: var(--color-primary); font-size: var(--font-size-narrative); font-weight: 600;
    font-family: var(--font-narrative);
  }
  .header button {
    background: none; border: 1px solid var(--color-border-light);
    color: var(--color-text-dim); cursor: pointer;
    font-size: var(--font-size-base); padding: 2px 10px; border-radius: var(--radius-sm);
    font-family: var(--font-ui); transition: all var(--transition-fast); line-height: 1;
  }
  .header button:hover { color: var(--color-danger); border-color: var(--color-danger); }
  .tab-bar {
    display: flex; border-bottom: 1px solid var(--color-border-light);
    padding: 0 var(--space-xl);
  }
  .tab-btn {
    flex: 1; padding: 10px 0; text-align: center;
    background: none; border: none; border-bottom: 2px solid transparent;
    color: var(--color-text-dim); font-size: var(--font-size-base); cursor: pointer;
    font-family: var(--font-ui); font-weight: 500;
    transition: all var(--transition-fast);
  }
  .tab-btn:hover { color: var(--color-text); }
  .tab-btn.active { color: var(--color-primary); border-bottom-color: var(--color-primary); }
  .tab-content { display: none; }
  .tab-content.active { display: block; }
  .body { padding: var(--space-xl); }
  .form-group { margin-bottom: 14px; }
  .form-group label {
    display: block; font-size: var(--font-size-sm); color: var(--color-text-dim); margin-bottom: var(--space-xs);
  }
  .form-group select, .form-group input[type="text"], .form-group input[type="password"], .form-group input[type="number"] {
    width: 100%; padding: 8px 12px;
    background: var(--color-surface-alt); border: 1px solid var(--color-border-light);
    border-radius: var(--radius-sm); color: var(--color-text);
    font-size: var(--font-size-md); font-family: var(--font-ui);
    outline: none; transition: border-color var(--transition-fast);
  }
  .form-group select:focus, .form-group input:focus { border-color: var(--color-primary); }
  .form-group select {
    cursor: pointer; appearance: none;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%236b5c3a' stroke-width='2'%3E%3Cpath d='M6 9l6 6 6-6'/%3E%3C/svg%3E");
    background-repeat: no-repeat; background-position: right 12px center; padding-right: 32px;
  }
  .form-group select option { background: var(--color-surface-alt); color: var(--color-text); }
  .form-group input[type="range"] {
    width: 100%; height: 5px; appearance: none;
    background: rgba(201, 169, 97, 0.12); border-radius: 2px; outline: none;
  }
  .form-group input[type="range"]::-webkit-slider-thumb {
    appearance: none; width: 14px; height: 14px;
    background: var(--color-primary); border-radius: 50%; cursor: pointer;
  }
  .form-group input[type="number"] { appearance: textfield; -moz-appearance: textfield; }
  .form-group input[type="number"]::-webkit-inner-spin-button,
  .form-group input[type="number"]::-webkit-outer-spin-button { appearance: none; margin: 0; }
  .checkbox-label { display: flex !important; align-items: center; gap: var(--space-md); font-size: var(--font-size-md); color: var(--color-text); cursor: pointer; }
  .checkbox-label input[type="checkbox"] { width: auto; margin: 0; cursor: pointer; }

  .input-with-action { display: flex; gap: 6px; }
  .input-with-action input,
  .input-with-action select { flex: 1; }
  .icon-btn {
    background: var(--color-surface-alt); border: 1px solid var(--color-border-light);
    border-radius: var(--radius-sm); color: var(--color-text-dim);
    cursor: pointer; padding: 0 10px; font-size: var(--font-size-xs);
    font-family: var(--font-ui); transition: all var(--transition-fast);
    white-space: nowrap;
  }
  .icon-btn:hover { color: var(--color-primary); border-color: var(--color-primary); }

  .modal-actions { display: flex; gap: 10px; margin-top: var(--space-xl); }
  .btn-primary {
    flex: 1; padding: 10px 16px;
    background: rgba(201, 169, 97, 0.15); border: 1px solid var(--color-primary);
    color: var(--color-primary); border-radius: var(--radius-sm);
    font-weight: 600; font-size: var(--font-size-base); cursor: pointer; font-family: var(--font-ui);
    transition: all var(--transition-fast);
  }
  .btn-primary:hover { background: var(--color-primary); color: var(--color-bg); }
  .btn-primary:disabled { opacity: 0.4; cursor: not-allowed; }
  .btn-secondary {
    flex: 1; padding: 10px 16px;
    background: transparent; border: 1px solid var(--color-border-light);
    color: var(--color-text); border-radius: var(--radius-sm);
    font-size: var(--font-size-base); cursor: pointer; font-family: var(--font-ui);
    transition: all var(--transition-fast);
  }
  .btn-secondary:hover { border-color: var(--color-primary); color: var(--color-primary); }

  .cfg-status { margin-top: 10px; padding: 8px 12px; border-radius: var(--radius-sm); font-size: var(--font-size-md); text-align: center; }
  .cfg-status.hidden { display: none; }
  .cfg-status.success { background: rgba(100,180,100,0.1); color: #64b464; border: 1px solid rgba(100,180,100,0.2); }
  .cfg-status.error { background: rgba(220,80,80,0.1); color: #d45050; border: 1px solid rgba(220,80,80,0.2); }

  .model-custom-input { margin-top: 6px; }
  .model-custom-input.hidden { display: none; }
  .shared-section {
    border-top: 1px solid var(--color-border-light);
    padding-top: var(--space-lg); margin-top: var(--space-lg);
  }
`;

export class SettingsModal extends ComponentBase {
  static get observedState() { return ['ui']; }

  constructor() {
    super();
    this._config = {};
    this._configRequested = false;
    this._models = [];
    this._configFast = {};
    this._modelsFast = [];
    this._activeTab = 'strong';
    this._fontScale = parseFloat(localStorage.getItem('lingmo-font-scale') || '1');
  }

  connectedCallback() {
    super.connectedCallback();
    EventBus.on('action:config_data', (msg) => this._onConfigData(msg.data));
    EventBus.on('action:config_saved', (msg) => this._onConfigSaved(msg.data));
    EventBus.on('action:config_test_result', (msg) => this._onTestResult(msg.data));
    EventBus.on('action:config_models_result', (msg) => this._onModelsResult(msg.data));
  }

  _onStateChanged(key, data) {
    const wasOpen = this._wasOpen;
    const isOpen = AppState.getUI().settingsOpen;
    if (wasOpen === isOpen) return;
    this._wasOpen = isOpen;
    this._render();
  }

  _showOverlay(show) {
    this.style.display = show ? 'flex' : 'none';
    this.style.position = show ? 'fixed' : '';
    this.style.top = show ? '0' : '';
    this.style.left = show ? '0' : '';
    this.style.width = show ? '100%' : '';
    this.style.height = show ? '100%' : '';
    this.style.background = show ? 'rgba(0,0,0,0.7)' : '';
    this.style.zIndex = show ? '100' : '';
    this.style.alignItems = show ? 'center' : '';
    this.style.justifyContent = show ? 'center' : '';
  }

  _render() {
    const ui = AppState.getUI();
    if (!ui.settingsOpen) {
      this._showOverlay(false);
      this._renderHTML(`<style>${CSS}</style>`);
      return;
    }
    this._showOverlay(true);

    if (!this._configRequested) {
      this._configRequested = true;
      WebSocketService.send({ type: 'config_get' });
    }
    this._renderContent();
  }

  _buildProviderOptions(selected) {
    return `
      <option value="openai_compatible" ${selected === 'openai_compatible' ? 'selected' : ''}>${i18n.t('provider_openai_compatible')}</option>
      <option value="anthropic" ${selected === 'anthropic' ? 'selected' : ''}>Anthropic (Claude)</option>
      <option value="google" ${selected === 'google' ? 'selected' : ''}>Google (Gemini)</option>
    `;
  }

  _buildModelSelect(currentModel, models, selectId, fetchBtnId, customId) {
    let opts = '';
    if (currentModel) {
      opts += `<option value="${this._esc(currentModel)}" selected>${this._esc(currentModel)}</option>`;
    }
    for (const m of models) {
      if (m === currentModel) continue;
      opts += `<option value="${this._esc(m)}">${this._esc(m)}</option>`;
    }
    if (opts === '') {
      opts = '<option value="">' + i18n.t('model_empty_option') + '</option>';
    }
    opts += '<option value="__custom__">' + i18n.t('model_custom_option') + '</option>';
    return `
      <div class="form-group">
        <label>${i18n.t('model')}</label>
        <div class="input-with-action">
          <select id="${selectId}">${opts}</select>
          <button id="${fetchBtnId}" class="icon-btn">${i18n.t('model_fetch')}</button>
        </div>
        <input type="text" id="${customId}" class="model-custom-input hidden" placeholder="${i18n.t('model_placeholder')}">
      </div>
    `;
  }

  _renderContent() {
    const c = this._config;
    const cf = this._configFast;
    const isStrongOpen = c.provider === 'openai_compatible' || !c.provider;
    const isFastOpenAI = cf.provider === 'openai_compatible' || !cf.provider;
    const tab = this._activeTab;

    this._renderHTML(`
      <style>${CSS}</style>
      <div class="backdrop" id="backdrop">
        <div class="modal">
          <div class="header"><span>${i18n.t('settings')}</span><button id="modal-close">${i18n.t('close')}</button></div>
          <div class="tab-bar">
            <button class="tab-btn ${tab === 'strong' ? 'active' : ''}" data-tab="strong">${i18n.t('tab_default')}</button>
            <button class="tab-btn ${tab === 'fast' ? 'active' : ''}" data-tab="fast">${i18n.t('tab_fast')}</button>
            <button class="tab-btn ${tab === 'ui' ? 'active' : ''}" data-tab="ui">${i18n.t('tab_ui')}</button>
          </div>

          <!-- 默认推理模型 -->
          <div class="body tab-content ${tab === 'strong' ? 'active' : ''}" id="tab-strong">
            <div class="form-group">
              <label>${i18n.t('provider_label')}</label>
              <select id="cfg-provider">${this._buildProviderOptions(c.provider)}</select>
            </div>
            <div class="form-group" id="cfg-baseurl-group" style="${isStrongOpen ? '' : 'display:none'}">
              <label>${i18n.t('base_url_label')}</label>
              <input type="text" id="cfg-baseurl" value="${this._esc(c.base_url || '')}" placeholder="https://api.deepseek.com/v1">
            </div>
            <div class="form-group">
              <label>${i18n.t('api_key_label')}</label>
              <div class="input-with-action">
                <input type="password" id="cfg-apikey" value="${this._esc(c.api_key_masked || '')}" placeholder="sk-...">
                <button id="cfg-toggle-key" class="icon-btn">${i18n.t('show')}</button>
              </div>
            </div>
            ${this._buildModelSelect(c.model, this._models, 'cfg-model', 'cfg-fetch-models', 'cfg-model-custom')}
            <div class="form-group">
              <label>${i18n.t('temperature_label')} <span id="temp-val">${c.temperature || 0.8}</span></label>
              <input type="range" id="cfg-temperature" min="0" max="1.0" step="0.1" value="${c.temperature || 0.8}">
            </div>
            <div class="form-group">
              <label>${i18n.t('max_tokens_label')}</label>
              <input type="number" id="cfg-maxtokens" value="${c.max_tokens || 2048}" min="256" max="8192" step="256">
            </div>
            <div class="shared-section">
              <div class="form-group">
                <label class="checkbox-label"><input type="checkbox" id="cfg-stream" ${c.stream_response !== false ? 'checked' : ''}>${i18n.t('stream_label')}</label>
              </div>
              <div class="form-group">
                <label class="checkbox-label"><input type="checkbox" id="cfg-show-thinking" ${c.show_thinking !== false ? 'checked' : ''}>${i18n.t('show_thinking_label')}</label>
              </div>
              <div class="modal-actions">
                <button id="cfg-test-btn" class="btn-secondary">${i18n.t('test_connection')}</button>
                <button id="cfg-save-btn" class="btn-primary">${i18n.t('save_config')}</button>
              </div>
              <div id="cfg-status" class="cfg-status hidden"></div>
            </div>
          </div>

          <!-- 快速推理模型 -->
          <div class="body tab-content ${tab === 'fast' ? 'active' : ''}" id="tab-fast">
            <div class="form-group">
              <label>${i18n.t('provider_label')}</label>
              <select id="cfg-fast-provider">${this._buildProviderOptions(cf.provider)}</select>
            </div>
            <div class="form-group" id="cfg-fast-baseurl-group" style="${isFastOpenAI ? '' : 'display:none'}">
              <label>${i18n.t('base_url_label')}</label>
              <input type="text" id="cfg-fast-baseurl" value="${this._esc(cf.base_url || '')}" placeholder="https://api.deepseek.com/v1">
            </div>
            <div class="form-group">
              <label>${i18n.t('api_key_label')}</label>
              <div class="input-with-action">
                <input type="password" id="cfg-fast-apikey" value="${this._esc(cf.api_key_masked || '')}" placeholder="sk-...">
                <button id="cfg-fast-toggle-key" class="icon-btn">${i18n.t('show')}</button>
              </div>
            </div>
            ${this._buildModelSelect(cf.model, this._modelsFast, 'cfg-fast-model', 'cfg-fast-fetch-models', 'cfg-fast-model-custom')}
            <div class="form-group">
              <label>${i18n.t('temperature_label')} <span id="fast-temp-val">${cf.temperature ?? 0.6}</span></label>
              <input type="range" id="cfg-fast-temperature" min="0" max="1.0" step="0.1" value="${cf.temperature ?? 0.6}">
            </div>
            <div class="form-group">
              <label>${i18n.t('max_tokens_label')}</label>
              <input type="number" id="cfg-fast-maxtokens" value="${cf.max_tokens ?? 8000}" min="256" max="8192" step="256">
            </div>
            <div class="shared-section">
              <div class="modal-actions">
                <button id="cfg-fast-test-btn" class="btn-secondary">${i18n.t('test_connection')}</button>
                <button id="cfg-fast-save-btn" class="btn-primary">${i18n.t('save_config')}</button>
              </div>
              <div id="cfg-fast-status" class="cfg-status hidden"></div>
            </div>
          </div>

          <!-- 界面设置 -->
          <div class="body tab-content ${tab === 'ui' ? 'active' : ''}" id="tab-ui">
            <div class="form-group">
              <label>${i18n.t('font_scale_label')} <span id="font-scale-val">${this._fontScale.toFixed(1)}</span>x</label>
              <input type="range" id="cfg-font-scale" min="0.8" max="2.0" step="0.1" value="${this._fontScale}">
            </div>
            <p style="color: var(--color-text-dim); font-size: var(--font-size-sm); margin-top: 8px;">
              ${i18n.t('font_scale_desc')}
            </p>
          </div>
        </div>
      </div>
    `);

    this._bindEvents();
  }

  _bindEvents() {
    const root = this.shadowRoot;

    // 关闭按钮 & 点击遮罩关闭
    if (this._closeHandler) this.removeEventListener('click', this._closeHandler);
    this._closeHandler = (e) => {
      const path = e.composedPath();
      if (path[0]?.id === 'modal-close' || path[0]?.id === 'backdrop') {
        this._showOverlay(false);
        this._configRequested = false;
        this._models = [];
        this._modelsFast = [];
        AppState.toggleSettings(false);
      }
    };
    this.addEventListener('click', this._closeHandler);

    // 分页切换
    root.querySelectorAll('.tab-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        this._syncFormToState();
        this._activeTab = e.target.dataset.tab;
        root.querySelectorAll('.tab-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === this._activeTab));
        root.querySelectorAll('.tab-content').forEach(c => c.classList.toggle('active', c.id === 'tab-' + this._activeTab));
      });
    });

    // === 界面设置 事件 ===
    const fontScaleEl = root.getElementById('cfg-font-scale');
    if (fontScaleEl) {
      fontScaleEl.addEventListener('input', (e) => {
        const scale = parseFloat(e.target.value);
        this._fontScale = scale;
        document.documentElement.style.setProperty('--font-scale', scale);
        localStorage.setItem('lingmo-font-scale', scale);
        const valEl = root.getElementById('font-scale-val');
        if (valEl) valEl.textContent = scale.toFixed(1);
      });
    }

    // === 默认推理模型 事件 ===
    const providerEl = root.getElementById('cfg-provider');
    if (providerEl) {
      providerEl.addEventListener('change', (e) => {
        const group = root.getElementById('cfg-baseurl-group');
        if (group) group.style.display = e.target.value === 'openai_compatible' ? '' : 'none';
      });
    }

    const tempEl = root.getElementById('cfg-temperature');
    if (tempEl) {
      tempEl.addEventListener('input', (e) => {
        const tv = root.getElementById('temp-val');
        if (tv) tv.textContent = e.target.value;
      });
    }

    const toggleKeyBtn = root.getElementById('cfg-toggle-key');
    if (toggleKeyBtn) {
      toggleKeyBtn.addEventListener('click', () => {
        const inp = root.getElementById('cfg-apikey');
        if (inp.type === 'password') { inp.type = 'text'; toggleKeyBtn.textContent = i18n.t('hide'); }
        else { inp.type = 'password'; toggleKeyBtn.textContent = i18n.t('show'); }
      });
    }

    const modelEl = root.getElementById('cfg-model');
    if (modelEl) {
      modelEl.addEventListener('change', (e) => {
        const ci = root.getElementById('cfg-model-custom');
        if (e.target.value === '__custom__') { ci.classList.remove('hidden'); ci.focus(); }
        else { ci.classList.add('hidden'); }
      });
    }

    const fetchBtn = root.getElementById('cfg-fetch-models');
    if (fetchBtn) fetchBtn.addEventListener('click', () => this._fetchModels());

    const testBtn = root.getElementById('cfg-test-btn');
    if (testBtn) testBtn.addEventListener('click', () => this._testConfig('strong'));

    const saveBtn = root.getElementById('cfg-save-btn');
    if (saveBtn) saveBtn.addEventListener('click', () => this._saveConfig());

    // === 快速推理模型 事件 ===
    const fastProviderEl = root.getElementById('cfg-fast-provider');
    if (fastProviderEl) {
      fastProviderEl.addEventListener('change', (e) => {
        const group = root.getElementById('cfg-fast-baseurl-group');
        if (group) group.style.display = e.target.value === 'openai_compatible' ? '' : 'none';
      });
    }

    const fastTempEl = root.getElementById('cfg-fast-temperature');
    if (fastTempEl) {
      fastTempEl.addEventListener('input', (e) => {
        const tv = root.getElementById('fast-temp-val');
        if (tv) tv.textContent = e.target.value;
      });
    }

    const fastToggleBtn = root.getElementById('cfg-fast-toggle-key');
    if (fastToggleBtn) {
      fastToggleBtn.addEventListener('click', () => {
        const inp = root.getElementById('cfg-fast-apikey');
        if (inp.type === 'password') { inp.type = 'text'; fastToggleBtn.textContent = i18n.t('hide'); }
        else { inp.type = 'password'; fastToggleBtn.textContent = i18n.t('show'); }
      });
    }

    const fastModelEl = root.getElementById('cfg-fast-model');
    if (fastModelEl) {
      fastModelEl.addEventListener('change', (e) => {
        const ci = root.getElementById('cfg-fast-model-custom');
        if (e.target.value === '__custom__') { ci.classList.remove('hidden'); ci.focus(); }
        else { ci.classList.add('hidden'); }
      });
    }

    const fastFetchBtn = root.getElementById('cfg-fast-fetch-models');
    if (fastFetchBtn) fastFetchBtn.addEventListener('click', () => this._fetchModelsFast());

    const fastTestBtn = root.getElementById('cfg-fast-test-btn');
    if (fastTestBtn) fastTestBtn.addEventListener('click', () => this._testConfig('fast'));

    const fastSaveBtn = root.getElementById('cfg-fast-save-btn');
    if (fastSaveBtn) fastSaveBtn.addEventListener('click', () => this._saveConfig());
  }

  // ---- 操作方法 ----

  _resolveModel(selectId, customId) {
    const root = this.shadowRoot;
    const sel = root?.getElementById(selectId);
    let val = sel ? sel.value : '';
    if (val === '__custom__' || val === '') {
      const ci = root?.getElementById(customId);
      val = ci ? ci.value : '';
    }
    return val;
  }

  _saveConfig() {
    const root = this.shadowRoot;
    const data = {
      provider: root.getElementById('cfg-provider')?.value,
      base_url: root.getElementById('cfg-baseurl')?.value,
      api_key: root.getElementById('cfg-apikey')?.value,
      model: this._resolveModel('cfg-model', 'cfg-model-custom'),
      temperature: parseFloat(root.getElementById('cfg-temperature')?.value || '0.8'),
      max_tokens: parseInt(root.getElementById('cfg-maxtokens')?.value || '2048'),
      stream_response: root.getElementById('cfg-stream')?.checked,
      show_thinking: root.getElementById('cfg-show-thinking')?.checked,
      llm_fast: {
        provider: root.getElementById('cfg-fast-provider')?.value || 'openai_compatible',
        base_url: root.getElementById('cfg-fast-baseurl')?.value || '',
        api_key: root.getElementById('cfg-fast-apikey')?.value || '',
        model: this._resolveModel('cfg-fast-model', 'cfg-fast-model-custom'),
        temperature: parseFloat(root.getElementById('cfg-fast-temperature')?.value || '0.6'),
        max_tokens: parseInt(root.getElementById('cfg-fast-maxtokens')?.value || '8000'),
      },
    };
    this._showStatus(null, i18n.t('saving'));
    this._showFastStatus(null, i18n.t('saving'));
    const saveBtn = root.getElementById('cfg-save-btn');
    const fastSaveBtn = root.getElementById('cfg-fast-save-btn');
    if (saveBtn) saveBtn.disabled = true;
    if (fastSaveBtn) fastSaveBtn.disabled = true;
    WebSocketService.send({ type: 'config_update', data: data });
    setTimeout(() => {
      if (saveBtn) saveBtn.disabled = false;
      if (fastSaveBtn) fastSaveBtn.disabled = false;
    }, 2000);
  }

  _testConfig(target) {
    if (target === 'fast') {
      this._showFastStatus(null, i18n.t('testing'));
      const btn = this.shadowRoot.getElementById('cfg-fast-test-btn');
      if (btn) btn.disabled = true;
      WebSocketService.send({ type: 'config_test', data: { target: 'fast' } });
      setTimeout(() => { if (btn) btn.disabled = false; }, 3000);
    } else {
      this._showStatus(null, i18n.t('testing'));
      const btn = this.shadowRoot.getElementById('cfg-test-btn');
      if (btn) btn.disabled = true;
      WebSocketService.send({ type: 'config_test' });
      setTimeout(() => { if (btn) btn.disabled = false; }, 3000);
    }
  }

  _fetchModels() {
    const root = this.shadowRoot;
    const apiKey = root.getElementById('cfg-apikey')?.value;
    const baseUrl = root.getElementById('cfg-baseurl')?.value;
    if (!apiKey || apiKey === '****') {
      this._showStatus(false, i18n.t('api_key_required'));
      return;
    }
    this._showStatus(null, i18n.t('fetching_models'));
    const fetchBtn = root.getElementById('cfg-fetch-models');
    if (fetchBtn) fetchBtn.disabled = true;
    WebSocketService.send({ type: 'config_models', data: { api_key: apiKey, base_url: baseUrl } });
    setTimeout(() => { if (fetchBtn) fetchBtn.disabled = false; }, 5000);
  }

  _fetchModelsFast() {
    const root = this.shadowRoot;
    const apiKey = root.getElementById('cfg-fast-apikey')?.value;
    const baseUrl = root.getElementById('cfg-fast-baseurl')?.value;
    if (!apiKey || apiKey === '****') {
      this._showFastStatus(false, i18n.t('api_key_required'));
      return;
    }
    this._showFastStatus(null, i18n.t('fetching_models'));
    const fetchBtn = root.getElementById('cfg-fast-fetch-models');
    if (fetchBtn) fetchBtn.disabled = true;
    WebSocketService.send({ type: 'config_models', data: { api_key: apiKey, base_url: baseUrl, target: 'fast' } });
    setTimeout(() => { if (fetchBtn) fetchBtn.disabled = false; }, 5000);
  }

  // ---- EventBus 回调 ----

  _onConfigData(data) {
    this._config = data || {};
    this._configFast = data?.llm_fast || {};
    AppState.setShowThinking(this._config.show_thinking !== false);
    if (AppState.getUI().settingsOpen) this._renderContent();
  }

  _onConfigSaved(data) {
    if (data && data.success) {
      const showThinkingEl = this.shadowRoot.getElementById('cfg-show-thinking');
      if (showThinkingEl) AppState.setShowThinking(showThinkingEl.checked);
      this._showStatus(true, data.message || i18n.t('config_saved'));
      this._showFastStatus(true, data.message || i18n.t('config_saved'));
      setTimeout(() => {
        this._configRequested = false;
        this._models = [];
        this._modelsFast = [];
        AppState.toggleSettings(false);
      }, 1200);
    } else {
      this._showStatus(false, (data && data.message) || i18n.t('save_failed'));
      this._showFastStatus(false, (data && data.message) || i18n.t('save_failed'));
    }
  }

  _onTestResult(data) {
    const target = data?.target || 'strong';
    if (data && data.success) {
      const msg = i18n.t('connection_success') + ' — ' + (data.model_info || '');
      if (target === 'fast') this._showFastStatus(true, msg);
      else this._showStatus(true, msg);
    } else {
      const msg = i18n.t('connection_failed') + ' — ' + ((data && data.message) || i18n.t('unknown_error'));
      if (target === 'fast') this._showFastStatus(false, msg);
      else this._showStatus(false, msg);
    }
  }

  _syncFormToState() {
    const root = this.shadowRoot;
    if (!root) return;
    const apiKey = root.getElementById('cfg-apikey')?.value;
    if (apiKey) this._config.api_key_masked = apiKey;
    const baseUrl = root.getElementById('cfg-baseurl')?.value;
    if (baseUrl !== undefined) this._config.base_url = baseUrl;
    const fastApiKey = root.getElementById('cfg-fast-apikey')?.value;
    if (fastApiKey) this._configFast.api_key_masked = fastApiKey;
    const fastBaseUrl = root.getElementById('cfg-fast-baseurl')?.value;
    if (fastBaseUrl !== undefined) this._configFast.base_url = fastBaseUrl;
  }

  _onModelsResult(data) {
    const target = data?.target || 'strong';
    if (data && data.success && data.models && data.models.length > 0) {
      if (target === 'fast') {
        this._modelsFast = data.models;
      } else {
        this._models = data.models;
      }
      const msg = i18n.t('models_fetched', { count: data.models.length });
      this._showStatus(true, msg);
      this._showFastStatus(true, msg);
      this._syncFormToState();
      this._renderContent();
    } else {
      const msg = (data && data.message) || i18n.t('no_models');
      this._showStatus(false, msg);
      this._showFastStatus(false, msg);
    }
  }

  // ---- 状态消息 ----

  _showStatus(success, message) {
    const el = this.shadowRoot.getElementById('cfg-status');
    if (!el) return;
    el.classList.remove('hidden', 'success', 'error');
    if (success === true) el.classList.add('success');
    else if (success === false) el.classList.add('error');
    el.textContent = message;
  }

  _showFastStatus(success, message) {
    const el = this.shadowRoot.getElementById('cfg-fast-status');
    if (!el) return;
    el.classList.remove('hidden', 'success', 'error');
    if (success === true) el.classList.add('success');
    else if (success === false) el.classList.add('error');
    el.textContent = message;
  }
}

customElements.define('settings-modal', SettingsModal);
