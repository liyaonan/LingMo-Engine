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
  .dialog {
    background: var(--color-surface); border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-lg); width: 90%; max-width: 440px; max-height: 80vh;
    display: flex; flex-direction: column;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.6);
  }
  .header {
    display: flex; justify-content: space-between; align-items: center;
    padding: 16px var(--space-xxl); border-bottom: 1px solid var(--color-border-light);
    font-size: var(--font-size-xl); font-weight: bold;
  }
  .header span { color: var(--color-primary); font-family: var(--font-narrative); }
  .header button {
    background: none; border: none;
    color: var(--color-text-dim); cursor: pointer; font-size: var(--font-size-xl);
    transition: color var(--transition-fast);
  }
  .header button:hover { color: var(--color-danger); }
  .actions { padding: 12px var(--space-xxl); }
  .actions button {
    padding: 6px 16px; background: var(--color-primary); color: var(--color-bg);
    border: none; border-radius: var(--radius-lg); cursor: pointer;
    font-size: var(--font-size-sm); font-family: var(--font-ui);
  }
  .list { flex: 1; overflow-y: auto; padding: 0 var(--space-xxl); }
  .slot {
    display: flex; align-items: center; justify-content: space-between;
    padding: 12px 0; border-bottom: 1px solid var(--color-border-light);
  }
  .slot-info { flex: 1; overflow: hidden; }
  .slot-name { color: var(--color-text); font-weight: bold; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .slot-date { color: var(--color-text-dim); font-size: var(--font-size-xs); }
  .slot-actions { display: flex; gap: 6px; flex-shrink: 0; }
  .slot-actions button {
    padding: 4px 10px; border: 1px solid var(--color-border); background: transparent;
    color: var(--color-text); border-radius: 4px; cursor: pointer; font-size: var(--font-size-xs);
    font-family: var(--font-ui); transition: all var(--transition-fast);
  }
  .slot-actions button:hover { background: var(--color-primary); color: var(--color-bg); }
  .slot-actions button.danger:hover { background: var(--color-danger); color: #fff; }
  .footer {
    padding: 16px var(--space-xxl); border-top: 1px solid var(--color-border-light);
    display: flex; gap: var(--space-sm);
  }
  .footer button { flex: 1; padding: var(--space-md); border-radius: var(--radius-lg); cursor: pointer; font-size: var(--font-size-sm); }
  .btn-primary { background: var(--color-primary); color: var(--color-bg); border: none; font-weight: bold; }
  .btn-secondary { background: transparent; color: var(--color-primary); border: 1px solid var(--color-primary); }
`;

export class SavePanel extends ComponentBase {
  static get observedState() { return ['ui']; }

  constructor() { super(); this._saveList = []; this._listRequested = false; }

  connectedCallback() {
    super.connectedCallback();
    EventBus.on('action:save_list', (msg) => this._onSaveList(msg));
    EventBus.on('action:save_result', (msg) => this._onSaveResult(msg));
    EventBus.on('action:export_ready', (msg) => this._onExportReady(msg));
    EventBus.on('action:delete_result', (msg) => this._onDeleteResult(msg));
  }

  _onStateChanged(key, data) {
    const wasOpen = this._wasOpen;
    const isOpen = AppState.getUI().savePanelOpen;
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
    if (!ui.savePanelOpen) {
      this._showOverlay(false);
      this._renderHTML(`<style>${CSS}</style>`);
      return;
    }
    this._showOverlay(true);

    if (!this._listRequested) {
      this._listRequested = true;
      WebSocketService.send({ type: 'list_saves' });
    }
    this._renderContent();
  }

  _renderContent() {
    let listHtml = '';
    if (this._saveList.length === 0) {
      listHtml = `<div style="color:var(--color-text-dim);text-align:center;padding:20px;">${i18n.t('no_saves')}</div>`;
    } else {
      for (const save of this._saveList) {
        const isAuto = save.is_autosave;
        const name = (isAuto ? i18n.t('autosave_prefix') : '') + (save.slot_id || 'unknown');
        const meta = (save.player_name || '') + ' Lv.' + (save.level || 1) + '  ' + (save.location || '');
        const time = save.updated_at ? save.updated_at.slice(0, 16).replace('T', ' ') : '';
        const escapedId = this._esc(save.slot_id);
        listHtml += `<div class="slot" data-slot="${escapedId}">`;
        listHtml += `<div class="slot-info"><div class="slot-name">${this._esc(name)}</div><div class="slot-date">${this._esc(meta)} — ${this._esc(time)}</div></div>`;
        listHtml += '<div class="slot-actions">';
        listHtml += `<button class="load-btn" data-slot="${escapedId}">${i18n.t('load')}</button>`;
        listHtml += `<button class="export-btn" data-slot="${escapedId}">${i18n.t('export')}</button>`;
        if (!isAuto) {
          listHtml += `<button class="danger delete-btn" data-slot="${escapedId}">${i18n.t('delete')}</button>`;
        }
        listHtml += '</div>';
        listHtml += '</div>';
      }
    }

    this._renderHTML(`
      <style>${CSS}</style>
      <div class="backdrop" id="backdrop">
        <div class="dialog">
          <div class="header"><span>${i18n.t('save_management')}</span><button id="close-btn">&times;</button></div>
          <div class="actions"><button id="btn-import">${i18n.t('import_save')}</button><input type="file" id="import-file" accept=".zip" style="display:none"></div>
          <div class="list">${listHtml}</div>
          <div class="footer">
            <button class="btn-primary" id="btn-save">${i18n.t('save_progress')}</button>
            <button class="btn-secondary" id="btn-save-as">${i18n.t('save_as_new')}</button>
          </div>
        </div>
      </div>
    `);

    // 关闭按钮 & 点击遮罩关闭
    if (this._closeHandler) this.removeEventListener('click', this._closeHandler);
    this._closeHandler = (e) => {
      const path = e.composedPath();
      if (path[0]?.id === 'close-btn' || path[0]?.id === 'backdrop') {
        this._showOverlay(false);
        this._listRequested = false;
        AppState.toggleSavePanel(false);
      }
    };
    this.addEventListener('click', this._closeHandler);

    // 保存当前进度
    this.shadowRoot.getElementById('btn-save').addEventListener('click', () => {
      WebSocketService.send({ type: 'save_game' });
    });

    // 另存为新槽位
    this.shadowRoot.getElementById('btn-save-as').addEventListener('click', () => {
      const defaultName = this._generateDefaultName();
      const name = prompt(i18n.t('save_name') + ':', defaultName);
      if (name && name.trim()) {
        WebSocketService.send({ type: 'save_game', slot_id: name.trim() });
      }
    });

    // 导入存档
    const importBtn = this.shadowRoot.getElementById('btn-import');
    const importFile = this.shadowRoot.getElementById('import-file');
    importBtn.addEventListener('click', () => importFile.click());
    importFile.addEventListener('change', (e) => {
      const file = e.target.files[0];
      if (!file) return;
      this._uploadImport(file);
      e.target.value = '';
    });

    // 槽位操作按钮
    this.shadowRoot.querySelectorAll('.load-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        this._loadSlot(btn.dataset.slot);
      });
    });
    this.shadowRoot.querySelectorAll('.export-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        WebSocketService.send({ type: 'export_save', slot_id: btn.dataset.slot });
      });
    });
    this.shadowRoot.querySelectorAll('.delete-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        this._deleteSlot(btn.dataset.slot);
      });
    });
  }

  _generateDefaultName() {
    const world = AppState.getWorld();
    const playerSlice = AppState.getSlice('player');
    const character = playerSlice && playerSlice.characterData;
    const playerName = (character && character.name) || '';
    const lv = (character && character.level) || 1;
    const now = new Date();
    const ts = (now.getMonth() + 1) + '/' + now.getDate() + ' ' + now.getHours() + ':' + String(now.getMinutes()).padStart(2, '0');
    return (playerName || i18n.t('save_default_name')) + '_Lv' + lv + '_' + ts;
  }

  _loadSlot(slotId) {
    if (confirm(i18n.t('confirm_load', { name: slotId }))) {
      sessionStorage.setItem('game_loaded', '1');
      WebSocketService.send({ type: 'load_save', slot: slotId });
      this._listRequested = false;
      AppState.toggleSavePanel(false);
    }
  }

  _deleteSlot(slotId) {
    if (confirm(i18n.t('confirm_delete', { name: slotId }))) {
      WebSocketService.send({ type: 'delete_save', slot_id: slotId });
    }
  }

  async _uploadImport(file) {
    const formData = new FormData();
    formData.append('file', file);
    try {
      const resp = await fetch('/api/import', { method: 'POST', body: formData });
      const data = await resp.json();
      if (data.success) {
        alert(i18n.t('import_success', { id: data.slot_id }));
        this._listRequested = false;
        WebSocketService.send({ type: 'list_saves' });
      } else {
        alert(i18n.t('import_failed', { error: data.error || i18n.t('unknown_error') }));
      }
    } catch (e) {
      alert(i18n.t('import_failed', { error: e.message }));
    }
  }

  // ---- EventBus 回调 ----

  _onSaveList(msg) {
    this._saveList = (msg.data && msg.data.saves) || [];
    if (AppState.getUI().savePanelOpen) this._renderContent();
  }

  _onSaveResult(msg) {
    // 保存成功后刷新列表，面板保持打开（对齐旧前端行为）
    if (msg.success) {
      this._listRequested = false;
      WebSocketService.send({ type: 'list_saves' });
    }
  }

  _onExportReady(msg) {
    if (msg.url) {
      window.open(msg.url, '_blank');
    }
  }

  _onDeleteResult(msg) {
    if (msg.success) {
      this._listRequested = false;
      WebSocketService.send({ type: 'list_saves' });
    } else {
      alert(i18n.t('delete_failed', { error: msg.error || i18n.t('unknown_error') }));
    }
  }
}

customElements.define('save-panel', SavePanel);
