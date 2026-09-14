import { HttpClient, HttpParams } from '@angular/common/http';
import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap, Router } from '@angular/router';
import { BehaviorSubject, of, Subject } from 'rxjs';
import { vi } from 'vitest';
import { ApiClient } from '../../../core/api/api-client.service';
import { AdminEvaluationPage, EvaluationQuery } from '../../../core/api/models';
import { AuthService } from '../../../core/auth/auth.service';
import { EvaluationData } from './datos/evaluation-data.service';
import { EvaluationWorkspace } from './evaluation-workspace.service';
import { FieldAnalytics } from './field-analytics';

const analytics = {
  module_key: 'estadios',
  desde: '2026-08-26',
  hasta: '2026-08-26',
  trend_desde: '2026-07-28',
  snapshot: true,
  grano: 'registro_access',
  grains: ['registro_access'],
  lots: [],
  trend: [{ key: '2026-08-26', categories: { E1: 10, E5: 90 } }],
  states: [],
  summary: {
    key: 'all',
    label: 'Consulta',
    evaluations: 2,
    observations: 0,
    complete: 2,
    excluded: 0,
    categories: { E1: 10, E5: 90 },
    availability: {},
    distribution: { n: 0 },
    diameter: { n: 0 },
    scatter: [],
    scatter_total: 0,
    sample_categories: {},
  },
} as unknown as FieldAnalytics;
describe('Independent evaluation workspaces', () => {
  let c: EvaluationWorkspace,
    params: BehaviorSubject<ReturnType<typeof convertToParamMap>>,
    path: BehaviorSubject<ReturnType<typeof convertToParamMap>>;
  let analyses: Subject<FieldAnalytics>[],
    pages: Subject<AdminEvaluationPage>[],
    queries: EvaluationQuery[],
    http: ReturnType<
      typeof vi.fn<(url: string, options: { params: HttpParams }) => Subject<FieldAnalytics>>
    >;
  beforeEach(() => {
    analyses = [];
    pages = [];
    queries = [];
    params = new BehaviorSubject(convertToParamMap({}));
    path = new BehaviorSubject(convertToParamMap({ familia: 'estadios' }));
    http = vi.fn(() => {
      const s = new Subject<FieldAnalytics>();
      analyses.push(s);
      return s;
    });
    TestBed.configureTestingModule({
      providers: [
        EvaluationData,
        { provide: HttpClient, useValue: { get: http } },
        { provide: ActivatedRoute, useValue: { paramMap: path, queryParamMap: params } },
        {
          provide: Router,
          useValue: {
            url: '/current',
            createUrlTree: vi.fn(),
            serializeUrl: () => '/current',
            navigate: vi.fn(),
            navigateByUrl: vi.fn(),
          },
        },
        { provide: AuthService, useValue: { hasPermission: () => false } },
        {
          provide: ApiClient,
          useValue: {
            clearReadCache: vi.fn(),
            evaluationAnalytics: (query: Record<string, unknown>, trend = false) => {
              let requestParams = new HttpParams();
              for (const [key, value] of Object.entries(query)) {
                if (value !== undefined && value !== null)
                  requestParams = requestParams.set(key, String(value));
              }
              return http('/v1/admin/evaluaciones/analitica' + (trend ? '/tendencia' : ''), {
                params: requestParams,
              });
            },
            listMaster: vi.fn(() => of({ items: [], meta: { pages: 0 } })),
            listEvaluations: (q: EvaluationQuery) => {
              queries.push(q);
              const s = new Subject<AdminEvaluationPage>();
              pages.push(s);
              return s;
            },
          },
        },
      ],
    });
    c = TestBed.runInInjectionContext(() => new EvaluationWorkspace());
    c.ngOnInit();
  });
  it('preserves primary chart options when history arrives but updates them for new aggregates', () => {
    c.analytics.set({
      ...analytics,
      trend: analytics.trend.map((point) => ({ ...point, label: point.key })),
    });
    const initial = c.mainChart();
    const initialEvolution = c.evolution();
    c.analytics.set({ ...analytics, trend: [] });
    expect(c.mainChart()).toBe(initial);
    expect(c.evolution()).not.toBe(initialEvolution);
    c.analytics.set({ ...analytics, lots: [...analytics.lots] });
    expect(c.mainChart()).not.toBe(initial);
    c.analytics.set(null);
    expect(c.mainChart()).toEqual({});
  });
  it('defers agricultural catalogues until filters are opened and reuses them', () => {
    const api = TestBed.inject(ApiClient);
    const read = vi.spyOn(api, 'listMaster');
    expect(read).not.toHaveBeenCalled();
    expect(c.filterCatalogLoading()).toBe(false);
    c.toggleFilters();
    expect(read).toHaveBeenCalledTimes(5);
    c.toggleFilters();
    c.toggleFilters();
    expect(read).toHaveBeenCalledTimes(5);
  });
  it('uses the independent family and the effective snapshot dates for records', () => {
    expect(http.mock.calls[0][1].params.get('snapshot_series')).toBe('true');
    analyses[0].next(analytics);
    expect(queries[0]).toMatchObject({
      module_key: 'estadios',
      desde: '2026-08-26',
      hasta: '2026-08-26',
      grano: 'registro_access',
    });
  });
  it('never publishes responses from a superseded query', () => {
    params.next(convertToParamMap({ lote_id: '10' }));
    analyses[0].next(analytics);
    expect(queries).toHaveLength(0);
    analyses[1].next(analytics);
    expect(queries[0].lote_id).toBe(10);
  });
  it('reuses complete aggregates when paging', () => {
    analyses[0].next(analytics);
    pages[0].next({ items: [], meta: { page: 1, page_size: 50, total: 100, pages: 2 } });
    c.onPage({ pageIndex: 1, pageSize: 50, length: 100 });
    expect(http).toHaveBeenCalledTimes(1);
    expect(queries[1].page).toBe(2);
  });
  it('renders analysis without waiting for the background records', () => {
    analyses[0].next(analytics);
    expect(c.summaryLoading()).toBe(false);
    expect(c.analytics()).toBe(analytics);
    expect(c.loading()).toBe(true);
  });
  it('does not restart an in-flight query when only the view changes', () => {
    params.next(convertToParamMap({ vista: 'registros' }));
    expect(http).toHaveBeenCalledTimes(1);
    analyses[0].next(analytics);
    params.next(convertToParamMap({}));
    expect(queries).toHaveLength(1);
  });
  it('switches views and returns to visited modules without refetching', () => {
    analyses[0].next(analytics);
    pages[0].next({ items: [], meta: { page: 1, page_size: 50, total: 2, pages: 1 } });
    c.setView('registros');
    params.next(convertToParamMap({ vista: 'registros' }));
    expect(queries).toHaveLength(1);
    path.next(convertToParamMap({ familia: 'flores' }));
    analyses[1].next({ ...analytics, module_key: 'flores', trend: [] });
    pages[1].next({ items: [], meta: { page: 1, page_size: 50, total: 2, pages: 1 } });
    path.next(convertToParamMap({ familia: 'estadios' }));
    expect(http).toHaveBeenCalledTimes(2);
    expect(queries).toHaveLength(2);
    expect(c.analytics()?.module_key).toBe('estadios');
  });
  it('keeps the same query visible during explicit refresh without showing other filters', () => {
    analyses[0].next(analytics);
    pages[0].next({ items: [], meta: { page: 1, page_size: 50, total: 2, pages: 1 } });
    c.refreshData();
    expect(c.analytics()).toBe(analytics);
    expect(c.summaryLoading()).toBe(true);
    params.next(convertToParamMap({ lote_id: '77' }));
    expect(c.analytics()).toBeNull();
  });
  it('loads history separately without delaying the current snapshot', () => {
    analyses[0].next({ ...analytics, trend: [] });
    expect(c.analytics()?.summary).toBe(analytics.summary);
    expect(c.summaryLoading()).toBe(false);
    expect(c.trendLoading()).toBe(true);
    expect(queries).toHaveLength(1);
    expect(http.mock.calls[1][0]).toBe('/v1/admin/evaluaciones/analitica/tendencia');
    expect(http.mock.calls[1][1].params.get('snapshot')).toBe('false');
    expect(http.mock.calls[1][1].params.get('series_only')).toBe('true');
    analyses[1].next(analytics);
    expect(c.trendLoading()).toBe(false);
    expect(c.analytics()?.trend).toEqual(analytics.trend);
  });
  it('finishes a departed module history and reuses it without contaminating the current module', () => {
    analyses[0].next({ ...analytics, trend: [] });
    path.next(convertToParamMap({ familia: 'flores' }));
    analyses[2].next({ ...analytics, module_key: 'flores', trend: [] });
    expect(http).toHaveBeenCalledTimes(4);
    analyses[1].next(analytics);
    analyses[1].complete();
    expect(c.analytics()?.module_key).toBe('flores');
    expect(c.analytics()?.trend).toEqual([]);
    path.next(convertToParamMap({ familia: 'estadios' }));
    expect(http).toHaveBeenCalledTimes(4);
    expect(c.analytics()?.trend).toEqual(analytics.trend);
    expect(c.trendLoading()).toBe(false);
  });
  it('reattaches to an unfinished history when returning quickly', () => {
    analyses[0].next({ ...analytics, trend: [] });
    path.next(convertToParamMap({ familia: 'flores' }));
    analyses[2].next({ ...analytics, module_key: 'flores', trend: [] });
    path.next(convertToParamMap({ familia: 'estadios' }));
    expect(http).toHaveBeenCalledTimes(4);
    analyses[1].next(analytics);
    expect(c.analytics()?.trend).toEqual(analytics.trend);
    expect(c.trendLoading()).toBe(false);
  });
  it('does not put a history from before refresh into the refreshed snapshot', () => {
    analyses[0].next({ ...analytics, trend: [] });
    c.refreshData();
    analyses[2].next({ ...analytics, trend: [] });
    analyses[1].next(analytics);
    expect(c.analytics()?.trend).toEqual([]);
    expect(c.trendLoading()).toBe(true);
    analyses[3].next({ ...analytics, trend: [] });
    expect(c.trendLoading()).toBe(false);
  });
  it('keeps view navigation immediate after time passes and supports explicit refresh', () => {
    const now = Date.now();
    const clock = vi.spyOn(Date, 'now').mockReturnValue(now);
    analyses[0].next(analytics);
    pages[0].next({ items: [], meta: { page: 2, page_size: 50, total: 100, pages: 2 } });
    pages[0].complete();
    clock.mockReturnValue(now + 601_000);
    params.next(convertToParamMap({ vista: 'registros' }));
    expect(http).toHaveBeenCalledTimes(1);
    expect(c.meta().page).toBe(2);
    c.applyFilters();
    expect(http).toHaveBeenCalledTimes(2);
    clock.mockRestore();
  });
  it('prepares compact history and shares it with navigation without fetching a full-period analysis', () => {
    vi.useFakeTimers();
    try {
      analyses[0].next(analytics);
      pages[0].next({ items: [], meta: { page: 1, page_size: 50, total: 2, pages: 1 } });
      vi.advanceTimersByTime(1500);
      expect(http).toHaveBeenCalledTimes(2);
      expect(http.mock.calls[1][1].params.get('module_key')).toBe('flores');
      expect(http.mock.calls[1][1].params.get('include_trend')).toBe('false');
      analyses[1].next({ ...analytics, module_key: 'flores', trend: [] });
      expect(http).toHaveBeenCalledTimes(3);
      expect(http.mock.calls[2][1].params.get('series_only')).toBe('true');
      path.next(convertToParamMap({ familia: 'flores' }));
      expect(http).toHaveBeenCalledTimes(3);
      expect(http.mock.calls[2][0]).toBe('/v1/admin/evaluaciones/analitica/tendencia');
      expect(c.analytics()?.module_key).toBe('flores');
      expect(c.summaryLoading()).toBe(false);
      analyses[2].next({ ...analytics, module_key: 'flores' });
      analyses[2].complete();
      expect(c.trendLoading()).toBe(false);
      expect(c.analytics()?.trend).toEqual(analytics.trend);
      path.next(convertToParamMap({ familia: 'estadios' }));
      path.next(convertToParamMap({ familia: 'flores' }));
      expect(http).toHaveBeenCalledTimes(3);
    } finally {
      vi.useRealTimers();
    }
  });
  it('warms every analysis before a slow speculative table can hold up the queue', () => {
    vi.useFakeTimers();
    try {
      analyses[0].next(analytics);
      vi.advanceTimersByTime(1500);
      for (let index = 1; index <= 5; index++) {
        expect(analyses).toHaveLength(index + 1);
        expect(pages).toHaveLength(1);
        const family = http.mock.calls[index][1].params.get('module_key')!;
        analyses[index].next({ ...analytics, module_key: family } as FieldAnalytics);
        analyses[index].complete();
      }
      expect(pages).toHaveLength(2);
      path.next(convertToParamMap({ familia: 'ramas' }));
      expect(c.summaryLoading()).toBe(false);
      expect(c.analytics()?.module_key).toBe('ramas');
      expect(http).toHaveBeenCalledTimes(6);
    } finally {
      vi.useRealTimers();
    }
  });
  it('prefetches the next page and shares an in-flight request with navigation', () => {
    c.workspaceView.set('registros');
    analyses[0].next(analytics);
    const first = [{ source_id: 1 }] as AdminEvaluationPage['items'];
    pages[0].next({ items: first, meta: { page: 1, page_size: 50, total: 100, pages: 2 } });
    expect(queries.map((q) => q.page)).toEqual([1, 2]);
    c.onPage({ pageIndex: 1, pageSize: 50, length: 100 });
    expect(queries).toHaveLength(2);
    expect(c.rows()).toBe(first);
    expect(c.loading()).toBe(true);
    pages[1].next({
      items: [{ source_id: 2 }] as AdminEvaluationPage['items'],
      meta: { page: 2, page_size: 50, total: 100, pages: 2 },
    });
    c.onPage({ pageIndex: 0, pageSize: 50, length: 100 });
    expect(c.rows()).toBe(first);
    expect(c.loading()).toBe(false);
    expect(queries).toHaveLength(2);
    expect(http).toHaveBeenCalledTimes(1);
  });
  it('keeps the applied snapshot when paging after analysis cache expires', () => {
    analyses[0].next(analytics);
    pages[0].next({ items: [], meta: { page: 1, page_size: 50, total: 100, pages: 2 } });
    const clock = vi.spyOn(Date, 'now').mockReturnValue(Date.now() + 61_000);
    c.filters.controls.lote_id.setValue(999);
    c.onPage({ pageIndex: 1, pageSize: 50, length: 100 });
    expect(http).toHaveBeenCalledTimes(1);
    expect(queries[1].desde).toBe('2026-08-26');
    expect(queries[1].lote_id).toBeUndefined();
    clock.mockRestore();
  });
  it('rejects reversed dates before sending requests', () => {
    c.filters.patchValue({ desde: '2026-09-10', hasta: '2026-09-01' });
    c.applyFilters();
    expect(http).toHaveBeenCalledTimes(1);
    expect(c.errorMessage()).toContain('fecha inicial');
  });
  it('keeps draft filters out of applied labels', () => {
    c.filters.controls.search.setValue('draft');
    expect(c.appliedFilters().some((x) => x.value === 'draft')).toBe(false);
  });
  it('changes families without combining their analyses', () => {
    path.next(convertToParamMap({ familia: 'pesos' }));
    expect(c.activeFamily()).toBe('pesos');
    expect(http.mock.calls.at(-1)?.[1].params.get('module_key')).toBe('pesos');
  });
  it('preserves unavailable percentages instead of reporting zero', () => {
    expect(c.percentage(0, 0)).toBeNull();
    expect(c.stagePercent(analytics.summary)).toBe(90);
  });
});
