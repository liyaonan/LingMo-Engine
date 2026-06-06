import { describe, it, expect, beforeEach, vi } from 'vitest';
import { EventBus } from '../event-bus.js';

describe('EventBus', () => {
  beforeEach(() => {
    EventBus.clear();
  });

  it('on 注册 + emit 触发回调并传递数据', () => {
    const received = [];
    EventBus.on('test', (data) => received.push(data));
    EventBus.emit('test', { value: 42 });
    expect(received).toEqual([{ value: 42 }]);
  });

  it('off 移除监听器后不再触发', () => {
    const fn = vi.fn();
    EventBus.on('test', fn);
    EventBus.off('test', fn);
    EventBus.emit('test', 'data');
    expect(fn).not.toHaveBeenCalled();
  });

  it('同一事件多个监听器全部被调用', () => {
    const fn1 = vi.fn();
    const fn2 = vi.fn();
    EventBus.on('test', fn1);
    EventBus.on('test', fn2);
    EventBus.emit('test', 'data');
    expect(fn1).toHaveBeenCalledWith('data');
    expect(fn2).toHaveBeenCalledWith('data');
  });

  it('不同事件隔离 — emit A 不触发 B', () => {
    const fnA = vi.fn();
    const fnB = vi.fn();
    EventBus.on('a', fnA);
    EventBus.on('b', fnB);
    EventBus.emit('a', 'data');
    expect(fnA).toHaveBeenCalled();
    expect(fnB).not.toHaveBeenCalled();
  });

  it('回调异常不中断其他回调', () => {
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    const badFn = () => { throw new Error('boom'); };
    const goodFn = vi.fn();
    EventBus.on('test', badFn);
    EventBus.on('test', goodFn);
    EventBus.emit('test', 'data');
    expect(goodFn).toHaveBeenCalled();
    expect(consoleSpy).toHaveBeenCalled();
    consoleSpy.mockRestore();
  });

  it('clear() 清空所有监听器', () => {
    const fn = vi.fn();
    EventBus.on('test', fn);
    EventBus.clear();
    EventBus.emit('test', 'data');
    expect(fn).not.toHaveBeenCalled();
  });

  it('emit 无监听器的事件不抛异常', () => {
    expect(() => EventBus.emit('nonexistent', 'data')).not.toThrow();
  });
});
