import { of, Subject, throwError } from 'rxjs';
import { vi } from 'vitest';
import { SessionReadCache } from './session-read-cache';

describe('Reload aggregate cache', () => {
  beforeEach(() => {
    sessionStorage.clear();
    sessionStorage.setItem('aquanqa.user', 'user-one');
    sessionStorage.setItem('aquanqa.access_token', 'test-session');
  });
  afterEach(() => sessionStorage.clear());

  it('restores a recent response after reload without another request and expires within a minute', () => {
    let now = 0;
    const request = vi.fn(() => of({ total: 0 }));
    new SessionReadCache(() => sessionStorage, () => now).read('counts', request, 600_000).subscribe();
    now = 59_999;
    let value: unknown;
    new SessionReadCache(() => sessionStorage, () => now).read('counts', request, 600_000).subscribe(v => value = v);
    expect(value).toEqual({ total: 0 });
    expect(request).toHaveBeenCalledTimes(1);
    now = 60_001;
    new SessionReadCache(() => sessionStorage, () => now).read('counts', request, 600_000).subscribe();
    expect(request).toHaveBeenCalledTimes(2);
  });

  it('separates queries and user permissions', () => {
    const cache = new SessionReadCache();
    const request = vi.fn(() => of(1));
    cache.read('family=estadios', request, 60_000).subscribe();
    cache.read('family=flores', request, 60_000).subscribe();
    sessionStorage.setItem('aquanqa.user', 'user-two');
    cache.read('family=estadios', request, 60_000).subscribe();
    expect(request).toHaveBeenCalledTimes(3);
  });

  it('does not persist an in-flight response after logout or a mutation', () => {
    const cache = new SessionReadCache();
    const pending = new Subject<number>();
    cache.read('counts', () => pending, 60_000).subscribe();
    cache.clear();
    pending.next(1); pending.complete();
    const request = vi.fn(() => of(2));
    cache.read('counts', request, 60_000).subscribe();
    expect(request).toHaveBeenCalledTimes(1);
  });

  it('falls back to network when storage is blocked and retries failed requests', () => {
    const cache = new SessionReadCache(() => { throw new Error('blocked'); });
    let value = 0;
    cache.read('counts', () => of(4), 60_000).subscribe(v => value = v);
    expect(value).toBe(4);
    const failing = vi.fn(() => throwError(() => new Error('offline')));
    const normal = new SessionReadCache();
    normal.read('counts', failing, 60_000).subscribe({ error: () => {} });
    normal.read('counts', failing, 60_000).subscribe({ error: () => {} });
    expect(failing).toHaveBeenCalledTimes(2);
  });
});
