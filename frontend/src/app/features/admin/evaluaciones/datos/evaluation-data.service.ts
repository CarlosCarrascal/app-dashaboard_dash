import { HttpClient, HttpParams } from '@angular/common/http';
import { DestroyRef, inject, Injectable } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { EMPTY, expand, finalize, Observable, of, reduce, shareReplay, tap } from 'rxjs';
import { ApiClient } from '../../../../core/api/api-client.service';
import type {
  AdminEvaluationPage,
  AdminMasterPage,
  EvaluationQuery,
  MasterResource,
} from '../../../../core/api/models';
import type { FieldAnalytics } from '../field-analytics';

/** One cache owner per evaluation workspace. Destroying the page cancels pending reads. */
@Injectable()
export class EvaluationData {
  cachedAnalysis(key: string) {
    return this.analysisCache.get(key);
  }
  private readonly api = inject(ApiClient);
  private readonly http = inject(HttpClient);
  private readonly destroyRef = inject(DestroyRef);
  private readonly pendingTrends = new Map<string, Observable<Pick<FieldAnalytics, 'trend'>>>();

  private readonly analysisCache = new Map<string, { value: FieldAnalytics; expires: number }>();

  private readonly pageCache = new Map<string, { value: AdminEvaluationPage; expires: number }>();

  private readonly pendingPages = new Map<string, Observable<AdminEvaluationPage>>();

  cacheGeneration = 0;

  private readonly cacheLifetime = 600_000;

  private readonly pendingAnalyses = new Map<string, Observable<FieldAnalytics>>();

  fetchAnalysis(query: Record<string, unknown>, key: string): Observable<FieldAnalytics> {
    const cached = this.analysisCache.get(key);
    if (cached && cached.expires > Date.now()) return of(cached.value);
    const pending = this.pendingAnalyses.get(key);
    if (pending) return pending;
    const generation = this.cacheGeneration;
    const request = this.api.evaluationAnalytics<FieldAnalytics>(query).pipe(
      takeUntilDestroyed(this.destroyRef),
      tap((value) => {
        if (generation === this.cacheGeneration) {
          this.analysisCache.set(key, { value, expires: Date.now() + this.cacheLifetime });
          if (this.analysisCache.size > 12)
            this.analysisCache.delete(this.analysisCache.keys().next().value!);
        }
      }),
      finalize(() => {
        if (generation === this.cacheGeneration) this.pendingAnalyses.delete(key);
      }),
      shareReplay({ bufferSize: 1, refCount: false }),
    );
    this.pendingAnalyses.set(key, request);
    return request;
  }

  requestPage(query: EvaluationQuery): Observable<AdminEvaluationPage> {
    const key = JSON.stringify(
      Object.entries(query)
        .filter(([, value]) => value !== undefined)
        .sort(([a], [b]) => a.localeCompare(b)),
    );
    const cached = this.pageCache.get(key);
    if (cached && cached.expires > Date.now()) return of(cached.value);
    const pending = this.pendingPages.get(key);
    if (pending) return pending;
    const generation = this.cacheGeneration;
    const request = this.api.listEvaluations(query).pipe(
      takeUntilDestroyed(this.destroyRef),
      tap((value) => {
        if (generation !== this.cacheGeneration) return;
        this.pageCache.set(key, { value, expires: Date.now() + this.cacheLifetime });
        if (this.pageCache.size > 24) this.pageCache.delete(this.pageCache.keys().next().value!);
      }),
      finalize(() => {
        if (generation === this.cacheGeneration) this.pendingPages.delete(key);
      }),
      shareReplay({ bufferSize: 1, refCount: false }),
    );
    this.pendingPages.set(key, request);
    return request;
  }

  fetchTrend(
    data: FieldAnalytics,
    query: Record<string, unknown>,
    key: string,
  ): Observable<Pick<FieldAnalytics, 'trend'>> {
    const pending = this.pendingTrends.get(key);
    if (pending) return pending;
    const generation = this.cacheGeneration;
    const request = this.api
      .evaluationAnalytics<Pick<FieldAnalytics, 'trend'>>(
        {
          ...query,
          snapshot: false,
          include_trend: true,
          series_only: true,
          desde: data.trend_desde || undefined,
          hasta: data.hasta || undefined,
          grano: data.grano || undefined,
        },
        true,
      )
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        tap((history) => {
          if (generation !== this.cacheGeneration) return;
          const entry = this.analysisCache.get(key);
          if (entry)
            this.analysisCache.set(key, {
              ...entry,
              value: { ...entry.value, trend: history.trend },
            });
        }),
        finalize(() => {
          if (generation === this.cacheGeneration) this.pendingTrends.delete(key);
        }),
        // Navigation releases only the view subscriber. The bounded HTTP read finishes
        // for its own query and is cancelled when this workspace is destroyed.
        shareReplay({ bufferSize: 1, refCount: false }),
      );
    this.pendingTrends.set(key, request);
    return request;
  }

  loadCatalog(resource: MasterResource) {
    return this.api.listMaster(resource, { page: 1, page_size: 500 }).pipe(
      expand((page) =>
        page.meta.page < page.meta.pages
          ? this.api.listMaster(resource, { page: page.meta.page + 1, page_size: 500 })
          : EMPTY,
      ),
      reduce((all, page) => ({ ...page, items: [...all.items, ...page.items] }), {
        items: [],
        meta: { page: 1, page_size: 500, total: 0, pages: 0 },
      } as AdminMasterPage),
    );
  }

  params(query: object) {
    return new HttpParams({
      fromObject: Object.fromEntries(
        Object.entries(query)
          .filter(([, v]) => v !== undefined && v !== null && v !== '')
          .map(([k, v]) => [k, String(v)]),
      ),
    });
  }
  invalidate(): void {
    this.api.clearReadCache();
    this.analysisCache.clear();
    this.pendingAnalyses.clear();
    this.pendingTrends.clear();
    this.pageCache.clear();
    this.pendingPages.clear();
    this.cacheGeneration++;
  }
  context(query: object) {
    return this.http.get<FieldAnalytics>('/v1/admin/evaluaciones/analitica', {
      params: this.params(query),
    });
  }
  export(query: object) {
    return this.http.get('/v1/admin/evaluaciones/exportar', {
      params: this.params(query),
      responseType: 'blob',
    });
  }
}
