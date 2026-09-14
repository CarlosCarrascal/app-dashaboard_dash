import { defer, Observable, of, tap } from 'rxjs';

/** Short-lived aggregate snapshots survive reloads, within the current tab and user only. */
export class SessionReadCache {
  private readonly key = 'aquanqa.aggregate-cache.v1';
  private generation = 0;
  constructor(
    private readonly storage: () => Storage | undefined = () => typeof sessionStorage === 'undefined' ? undefined : sessionStorage,
    private readonly now = () => Date.now(),
  ) {}

  clear(): void {
    this.generation++;
    try { this.storage()?.removeItem(this.key); } catch { /* Storage can be unavailable. */ }
  }

  read<T>(key: string, request: () => Observable<T>, ttl: number): Observable<T> {
    return defer(() => {
      let storage: Storage | undefined;
      let scope: string | null = null;
      try {
        storage = this.storage();
        scope = storage?.getItem('aquanqa.user') ?? null;
        if (!storage?.getItem('aquanqa.access_token')) scope = null;
        const cached = JSON.parse(storage?.getItem(this.key) ?? 'null');
        const hit = cached?.scope === scope && scope ? cached.entries?.[key] : null;
        if (hit && hit.expires > this.now()) return of(hit.value as T);
      } catch { /* A malformed or blocked cache must never block the API. */ }
      const generation = this.generation;
      return request().pipe(tap(value => {
        if (!scope || !storage || generation !== this.generation) return;
        try {
          if (storage.getItem('aquanqa.user') !== scope || !storage.getItem('aquanqa.access_token')) return;
          const previous = JSON.parse(storage.getItem(this.key) ?? 'null');
          const entries = previous?.scope === scope ? previous.entries ?? {} : {};
          const current = Object.fromEntries(Object.entries(entries)
            .filter(([k, entry]) => k !== key && (entry as { expires: number }).expires > this.now()).slice(-31));
          current[key] = { value, expires: this.now() + Math.min(ttl, 60_000) };
          storage.setItem(this.key, JSON.stringify({ scope, entries: current }));
        } catch { /* Quota or privacy settings fall back to the memory cache. */ }
      }));
    });
  }
}
