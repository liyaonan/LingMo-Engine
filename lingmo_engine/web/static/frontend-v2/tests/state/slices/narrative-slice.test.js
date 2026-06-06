import { describe, it, expect, beforeEach } from 'vitest';
import { createNarrativeSlice } from '../../../state/slices/narrative-slice.js';

describe('NarrativeSlice', () => {
  let slice;

  beforeEach(() => {
    slice = createNarrativeSlice();
  });

  it('初始状态 messages 为空', () => {
    expect(slice.getMessages().size).toBe(0);
    expect(slice.getCurrentPage()).toBe(-1);
  });

  it('addMessage 追加消息到 messages 和 pageIndex', () => {
    slice.addMessage({ id: 'm1', role: 'assistant', page_id: 'p1' });
    expect(slice.getMessages().size).toBe(1);
    expect(slice.getMessages().get('m1').role).toBe('assistant');
    expect(slice.getPageIndex().get('p1')).toEqual(['m1']);
  });

  it('deleteMessage 将消息标记为 deleted', () => {
    slice.addMessage({ id: 'm1', role: 'assistant' });
    slice.deleteMessage('m1');
    expect(slice.getMessages().get('m1').status).toBe('deleted');
  });

  it('deleteMessage 不存在的 id 不抛异常', () => {
    expect(() => slice.deleteMessage('nonexistent')).not.toThrow();
  });

  it('startStream + appendStream + endStream 流式生命周期', () => {
    slice.startStream('s1');
    expect(slice.getStreaming().id).toBe('s1');
    expect(slice.getStreaming().content).toBe('');

    slice.appendStream('Hello');
    slice.appendStream(' World');
    expect(slice.getStreaming().content).toBe('Hello World');

    slice.endStream(null);
    expect(slice.getStreaming().id).toBeNull();
    expect(slice.getStreaming().content).toBe('');
  });

  it('endStream 传入 content 参数', () => {
    slice.startStream('s1');
    slice.appendStream('partial...');
    slice.endStream('完整内容');
    expect(slice.getStreaming().id).toBeNull();
  });

  it('setCurrentPage 设置当前页', () => {
    slice.setCurrentPage(2);
    expect(slice.getCurrentPage()).toBe(2);
  });

  it('loadMessages 批量加载并重建 pageIndex', () => {
    const msgs = [
      { id: 'm1', role: 'user', page_id: 'p1' },
      { id: 'm2', role: 'assistant', page_id: 'p1' },
      { id: 'm3', role: 'user', page_id: 'p2' },
    ];
    slice.loadMessages(msgs);
    expect(slice.getMessages().size).toBe(3);
    expect(slice.getPageIndex().get('p1')).toEqual(['m1', 'm2']);
    expect(slice.getPageIndex().get('p2')).toEqual(['m3']);
  });

  it('clear() 清空所有数据', () => {
    slice.addMessage({ id: 'm1', role: 'user' });
    slice.setCurrentPage(0);
    slice.clear();
    expect(slice.getMessages().size).toBe(0);
    expect(slice.getCurrentPage()).toBe(-1);
  });

  it('getState() 返回 messages 和 pageIndex 的数组序列化', () => {
    slice.addMessage({ id: 'm1', role: 'user', page_id: 'p1' });
    const state = slice.getState();
    expect(Array.isArray(state.messages)).toBe(true);
    expect(Array.isArray(state.pageIndex)).toBe(true);
    expect(state.currentPage).toBe(-1);
  });

  it('restore() 恢复完整状态', () => {
    slice.addMessage({ id: 'm1', role: 'user', page_id: 'p1' });
    slice.setCurrentPage(0);
    const snap = slice.getState();
    slice.clear();
    slice.restore(snap);
    expect(slice.getMessages().size).toBe(1);
    expect(slice.getCurrentPage()).toBe(0);
  });
});
