import { ComponentBase } from '/static/frontend-v2/shared/component-base.js';
import { EventBus } from '/static/frontend-v2/event-bus.js';
import { AppState } from '/static/frontend-v2/state/app-state.js';
import { WebSocketService } from '/static/frontend-v2/services/websocket.js';

const CSS = `
  :host { display: block; overflow-y: auto; }

  .event-section-title {
    font-size: var(--font-size-md); color: var(--color-primary);
    padding: 0 16px 8px; margin: 0;
    border-bottom: 1px solid var(--color-border);
  }
  .event-empty {
    padding: 16px; color: var(--color-text-dim);
    font-size: var(--font-size-md); text-align: center;
  }
  .event-card {
    margin: 6px 16px; padding: 12px;
    background: var(--color-surface);
    border: 1px solid var(--color-border);
    border-radius: 6px; cursor: pointer;
    transition: border-color 0.15s;
  }
  .event-card:hover { border-color: var(--color-primary); }
  .event-card.active-event {
    border-color: var(--color-primary);
    box-shadow: 0 0 8px rgba(201, 169, 97, 0.15);
  }
  .event-card-header {
    display: flex; align-items: center; justify-content: space-between;
  }
  .event-title {
    font-size: var(--font-size-base); color: #fff; font-weight: bold;
  }
  .event-status {
    font-size: var(--font-size-xs); padding: 2px 8px; border-radius: 3px;
  }
  .event-status.active {
    background: rgba(100,180,100,0.15); color: #64b464;
  }
  .event-status.completed {
    background: rgba(128,128,128,0.15); color: #888;
  }
  .event-card-detail {
    margin-top: 10px; padding-top: 10px;
    border-top: 1px solid var(--color-border);
  }
  .event-markdown {
    font-family: var(--font-ui); font-size: var(--font-size-sm);
    color: var(--color-text-dim); line-height: 1.7;
    white-space: pre-wrap; word-break: break-word;
    margin: 0; background: transparent;
  }
  .event-choices {
    margin-top: 10px; padding-top: 10px;
    border-top: 1px solid var(--color-border-light);
  }
  .event-choices-title {
    font-size: var(--font-size-sm); color: var(--color-primary); margin-bottom: 6px;
  }
  .event-choice-btn {
    display: block; width: 100%; text-align: left;
    padding: 6px 10px; margin-bottom: 4px;
    background: rgba(201, 169, 97, 0.08);
    border: 1px solid var(--color-border-light);
    border-radius: 4px; color: var(--color-text);
    font-size: var(--font-size-sm); font-family: var(--font-ui);
    cursor: pointer; transition: all 0.15s;
  }
  .event-choice-btn:hover {
    background: rgba(201, 169, 97, 0.15);
    border-color: var(--color-primary);
  }
`;

export class EventPanel extends ComponentBase {
  static get observedState() { return ['events']; }

  constructor() {
    super();
    this._eventsData = [];
    this._expandedEvents = {};

    this._eventsHandler = (msg) => {
      this._eventsData = msg.events || [];
      this._render();
    };
  }

  connectedCallback() {
    super.connectedCallback();
    EventBus.on('action:events_data', this._eventsHandler);
    this._listeners.push({ event: 'action:events_data', cb: this._eventsHandler });
    // 面板打开时主动拉取事件列表
    WebSocketService.send({ type: 'get_events' });
  }

  _onStateChanged(key, data) {
    // 响应 events 状态变化（如存档加载后恢复）
    if (key === 'events' || key === '*') {
      const state = AppState.getSlice('events');
      if (state && state.events && state.events.length > 0) {
        this._eventsData = state.events;
      }
      this._render();
    }
  }

  _render() {
    const eventsState = AppState.getSlice('events') || {};
    const activeEventId = eventsState.active_event_id || null;
    const choices = eventsState.choices || [];

    let html = '<div class="event-section">';
    html += '<h3 class="event-section-title">世界事件</h3>';

    if (this._eventsData.length === 0) {
      html += '<div class="event-empty">暂无活跃事件</div>';
    } else {
      for (const ev of this._eventsData) {
        const statusLabel = ev.status === 'active' ? '进行中' : '已结束';
        const statusClass = ev.status === 'active' ? 'active' : 'completed';
        const isActiveEvent = activeEventId && ev.event_id === activeEventId;
        const cardClass = 'event-card' + (isActiveEvent ? ' active-event' : '');
        const isExpanded = this._expandedEvents[ev.event_id];

        html += `<div class="${cardClass}" data-event-id="${this._esc(ev.event_id)}">`;
        html += '<div class="event-card-header">';
        html += `<span class="event-title">${this._esc(ev.title)}</span>`;
        html += `<span class="event-status ${statusClass}">${statusLabel}</span>`;
        html += '</div>';

        // 事件详情（可展开/折叠）
        const detailStyle = isExpanded ? '' : 'style="display:none"';
        html += `<div class="event-card-detail" id="detail-${this._esc(ev.event_id)}" ${detailStyle}>`;

        const viewContent = ev.player_view || ev.plan_md || ev.description || '';
        if (viewContent) {
          html += `<pre class="event-markdown">${this._esc(viewContent)}</pre>`;
        }

        // 当前活跃事件的选项
        if (isActiveEvent && choices && choices.length > 0) {
          html += '<div class="event-choices">';
          html += '<div class="event-choices-title">可选行动</div>';
          for (const choice of choices) {
            const choiceText = choice.text || choice.label || choice.description || '';
            html += `<button class="event-choice-btn" data-choice-id="${this._esc(choice.id || '')}">${this._esc(choiceText)}</button>`;
          }
          html += '</div>';
        }

        html += '</div>';  // .event-card-detail
        html += '</div>';  // .event-card
      }
    }

    html += '</div>';  // .event-section
    this._renderHTML(`<style>${CSS}</style>${html}`);

    // 绑定事件处理（等待 DOM 更新）
    setTimeout(() => this._bindEvents(), 0);
  }

  _bindEvents() {
    const root = this.shadowRoot;
    if (!root) return;

    // 事件卡片点击：展开/折叠详情
    root.querySelectorAll('.event-card').forEach(card => {
      card.addEventListener('click', (e) => {
        // 点击选项按钮时不触发展开/折叠
        if (e.target.classList.contains('event-choice-btn')) return;

        const eventId = card.dataset.eventId;
        const detail = root.getElementById('detail-' + eventId);
        if (detail) {
          const isVisible = detail.style.display !== 'none';
          detail.style.display = isVisible ? 'none' : 'block';
          this._expandedEvents[eventId] = !isVisible;
        }
      });
    });

    // 事件选项按钮点击
    root.querySelectorAll('.event-choice-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const choiceId = btn.dataset.choiceId;
        // 事件选项点击 — 预留后端交互协议接口
      });
    });
  }
}

customElements.define('event-panel', EventPanel);
