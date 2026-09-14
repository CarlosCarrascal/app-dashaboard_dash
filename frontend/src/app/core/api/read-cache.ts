import { Observable, defer, finalize, shareReplay, tap } from 'rxjs';
interface Entry {
  value: Observable<unknown>;
  expires: number;
}
/** Session-local, bounded cache. Pending reads share one cancellable subscription. */
export class ReadCache {
  private readonly entries = new Map<string, Entry>();
  constructor(
    private readonly capacity = 80,
    private readonly now = () => Date.now(),
  ) {}
  clear(): void {
    this.entries.clear();
  }
  read<T>(key: string, request: () => Observable<T>, ttl = 30_000): Observable<T> {
    return defer(() => {
      const hit = this.entries.get(key);
      if (hit && hit.expires > this.now()) {
        this.entries.delete(key);
        this.entries.set(key, hit);
        return hit.value as Observable<T>;
      }
      if (hit) this.entries.delete(key);
      let completed = false;
      const entry: Entry = { value: undefined!, expires: Infinity };
      entry.value = defer(request).pipe(
        tap({
          complete: () => {
            completed = true;
            entry.expires = this.now() + ttl;
          },
        }),
        finalize(() => {
          if (!completed && this.entries.get(key) === entry) this.entries.delete(key);
        }),
        shareReplay({ bufferSize: 1, refCount: true }),
      );
      this.entries.set(key, entry);
      while (this.entries.size > this.capacity)
        this.entries.delete(this.entries.keys().next().value!);
      return entry.value as Observable<T>;
    });
  }
}
