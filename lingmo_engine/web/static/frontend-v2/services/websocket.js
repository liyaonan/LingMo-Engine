// services/websocket.js — WebSocket 连接管理，从旧的 websocket.js 移植
let socket = null;
let reconnectTimer = null;
let _onMessage = null;

export const WebSocketService = {
  get socket() { return socket; },

  set onMessage(handler) { _onMessage = handler; },

  connect() {
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url = `${protocol}//${location.host}/ws`;

    socket = new WebSocket(url);

    socket.onopen = () => {
      // WebSocket 连接成功
      if (reconnectTimer) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
      }
    };

    socket.onclose = () => {
      // WebSocket 断开，3秒后重连
      if (!reconnectTimer) {
        reconnectTimer = setTimeout(() => this.connect(), 3000);
      }
    };

    socket.onerror = (err) => console.error('[WS] 错误:', err);

    socket.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (_onMessage) _onMessage(msg);
      } catch (e) {
        console.error('[WS] 消息解析失败:', e);
      }
    };
  },

  send(data) {
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify(data));
    } else {
      // WebSocket 未连接，消息未发送
    }
  },
};
