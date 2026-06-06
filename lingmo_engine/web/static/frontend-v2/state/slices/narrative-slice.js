// state/slices/narrative-slice.js
export function createNarrativeSlice() {
  return {
    name: 'narrative',

    _state: {
      messages: new Map(),
      pageIndex: new Map(),
      pages: [],
      currentPage: -1,
      streamingMessageId: null,
      streamingContent: '',
    },

    getMessages() { return this._state.messages; },
    getPageIndex() { return this._state.pageIndex; },
    getPages() { return this._state.pages; },
    getCurrentPage() { return this._state.currentPage; },
    getStreaming() { return { id: this._state.streamingMessageId, content: this._state.streamingContent }; },

    addMessage(msg) {
      this._state.messages.set(msg.id, msg);
      if (msg.page_id) {
        const list = this._state.pageIndex.get(msg.page_id) || [];
        list.push(msg.id);
        this._state.pageIndex.set(msg.page_id, list);
      }
      return 'narrative';
    },

    appendStream(delta) {
      this._state.streamingContent += delta;
      return 'narrative';
    },

    startStream(msgId) {
      this._state.streamingMessageId = msgId;
      this._state.streamingContent = '';
      return 'narrative';
    },

    endStream(content) {
      const finalContent = content || this._state.streamingContent;
      this._state.streamingMessageId = null;
      this._state.streamingContent = '';
      return 'narrative';
    },

    updateMessage(id, updates) {
      const msg = this._state.messages.get(id);
      if (msg) Object.assign(msg, updates);
      return 'narrative';
    },

    deleteMessage(id) {
      const msg = this._state.messages.get(id);
      if (msg) msg.status = 'deleted';
      return 'narrative';
    },

    setCurrentPage(index) {
      this._state.currentPage = index;
      return 'narrative';
    },

    loadMessages(messages) {
      this._state.messages.clear();
      this._state.pageIndex.clear();
      for (const m of messages) {
        this._state.messages.set(m.id, m);
        if (m.page_id) {
          const list = this._state.pageIndex.get(m.page_id) || [];
          list.push(m.id);
          this._state.pageIndex.set(m.page_id, list);
        }
      }
      return 'narrative';
    },

    clear() {
      this._state.messages.clear();
      this._state.pageIndex.clear();
      this._state.pages = [];
      this._state.currentPage = -1;
      return 'narrative';
    },

    getState() {
      return {
        messages: Array.from(this._state.messages.entries()),
        pageIndex: Array.from(this._state.pageIndex.entries()),
        pages: this._state.pages,
        currentPage: this._state.currentPage,
        streamingMessageId: this._state.streamingMessageId,
        streamingContent: this._state.streamingContent,
      };
    },

    restore(state) {
      this._state.messages = new Map(state.messages || []);
      this._state.pageIndex = new Map(state.pageIndex || []);
      this._state.pages = state.pages || [];
      this._state.currentPage = state.currentPage ?? -1;
      this._state.streamingMessageId = state.streamingMessageId || null;
      this._state.streamingContent = state.streamingContent || '';
    },
  };
}
