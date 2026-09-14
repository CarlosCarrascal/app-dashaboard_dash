import { of, Subject, throwError } from 'rxjs';
import { vi } from 'vitest';
import { ReadCache } from './read-cache';
describe('Dashboard read cache', () => {
  it('shares in-flight requests and replays completed reads without network work', () => {
    const cache = new ReadCache();
    const source = new Subject<number>();
    const request = vi.fn(() => source);
    const values: number[] = [];
    cache.read('a', request).subscribe((v) => values.push(v));
    cache.read('a', request).subscribe((v) => values.push(v));
    expect(request).toHaveBeenCalledTimes(1);
    source.next(7);
    source.complete();
    cache.read('a', request).subscribe((v) => values.push(v));
    expect(values).toEqual([7, 7, 7]);
    expect(request).toHaveBeenCalledTimes(1);
  });
  it('expires results and evicts least recently used entries', () => {
    let now = 0;
    const cache = new ReadCache(2, () => now);
    const request = vi.fn(() => of(1));
    for (const key of ['a', 'b', 'a', 'c', 'b']) cache.read(key, request, 10).subscribe();
    expect(request).toHaveBeenCalledTimes(4);
    now = 11;
    cache.read('b', request, 10).subscribe();
    expect(request).toHaveBeenCalledTimes(5);
  });
  it('clears session data and does not resurrect an invalidated in-flight result', () => {
    const cache = new ReadCache();
    const old = new Subject<number>();
    cache.read('a', () => old).subscribe();
    cache.clear();
    old.next(1);
    old.complete();
    let result = 0;
    cache.read('a', () => of(2)).subscribe((v) => (result = v));
    expect(result).toBe(2);
  });
  it('retries failures and cancels abandoned requests', () => {
    const cache = new ReadCache();
    const request = vi.fn(() => throwError(() => new Error('offline')));
    cache.read('a', request).subscribe({ error: () => {} });
    cache.read('a', request).subscribe({ error: () => {} });
    expect(request).toHaveBeenCalledTimes(2);
    const pending = new Subject<number>();
    const sub = cache.read('b', () => pending).subscribe();
    expect(pending.observed).toBe(true);
    sub.unsubscribe();
    expect(pending.observed).toBe(false);
    let value = 0;
    cache.read('b', () => of(3)).subscribe((v) => (value = v));
    expect(value).toBe(3);
  });
  it('keeps different filters and pages separate', () => {
    const cache = new ReadCache();
    const values: number[] = [];
    cache.read('page=1', () => of(1)).subscribe((v) => values.push(v));
    cache.read('page=2', () => of(2)).subscribe((v) => values.push(v));
    expect(values).toEqual([1, 2]);
  });
});
