// cultivation-ui.js — 修炼面板独立UI
// 通过EventBus挂载，不修改现有前端v2代码

(function() {
  'use strict';

  class CultivationUI {
    constructor() {
      this._panel = null;
      this._visible = false;
      this._data = null;
      this._init();
    }

    _init() {
      document.addEventListener('DOMContentLoaded', () => {
        const checkBus = setInterval(() => {
          if (window.EventBus) {
            clearInterval(checkBus);
            window.EventBus.on('action:cultivation_state', (data) => this._update(data));
            this._createPanel();
          }
        }, 100);
      });
    }

    _createPanel() {
      this._panel = document.createElement('div');
      this._panel.id = 'cultivation-ui-panel';
      this._panel.className = 'cultivation-overlay';
      this._panel.innerHTML =
        '<div class="cult-header">修炼</div>' +
        '<div class="cult-body" id="cult-body">' +
        '<div class="cult-row"><span>等待数据...</span></div>' +
        '</div>';
      this._panel.style.display = 'none';
      document.body.appendChild(this._panel);
    }

    _update(data) {
      this._data = data;
      if (!this._visible) {
        this._visible = true;
        this._panel.style.display = 'block';
      }
      var body = document.getElementById('cult-body');
      if (body && data) {
        body.innerHTML =
          '<div class="cult-row"><span>境界</span><span>' + (data.stage_name || data.stage || '?') + '</span></div>' +
          '<div class="cult-row"><span>子阶段</span><span>' + (data.substage || '?') + '</span></div>' +
          '<div class="cult-row"><span>主修</span><span>' + (data.path || '无') + '</span></div>' +
          '<div class="cult-row"><span>灵力</span><span>' + (data.spiritual_power || 0) + '</span></div>' +
          '<div class="cult-row"><span>道韵</span><span>' + (data.dao_rhyme || 0) +
            (data.dao_rhyme_threshold > 0 ? ' / ' + data.dao_rhyme_threshold : '') +
            (data.enlightenment_ready ? ' ★顿悟' : '') +
            '</span></div>' +
          '<div class="cult-row"><span>神识</span><span>' + (data.divine_sense || 0) + '</span></div>' +
          '<div class="cult-row"><span>感悟</span><span>' + (data.enlightenment || 0) + '/100</span></div>' +
          '<div class="cult-row"><span>灵根</span><span>' + (data.quality || '未知') + '</span></div>';
      }
    }

    toggle() {
      this._visible = !this._visible;
      this._panel.style.display = this._visible ? 'block' : 'none';
    }
  }

  window.CultivationUI = new CultivationUI();
})();
