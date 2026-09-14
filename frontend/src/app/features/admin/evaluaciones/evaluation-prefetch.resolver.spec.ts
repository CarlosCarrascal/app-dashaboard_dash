import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { ActivatedRouteSnapshot, RouterStateSnapshot, convertToParamMap } from '@angular/router';
import { ApiClient } from '../../../core/api/api-client.service';
import { AuthService } from '../../../core/auth/auth.service';
import { evaluationPrefetch } from './evaluation-prefetch.resolver';

describe('Evaluation first-entry preparation', () => {
  let http: HttpTestingController;
  let allowed: boolean;
  const run = (family = 'flores', query = {}) =>
    TestBed.runInInjectionContext(() =>
      evaluationPrefetch(
        {
          paramMap: convertToParamMap({ familia: family }),
          queryParamMap: convertToParamMap(query),
        } as ActivatedRouteSnapshot,
        {} as RouterStateSnapshot,
      ),
    );
  beforeEach(() => {
    allowed = true;
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        {
          provide: AuthService,
          useValue: { isAuthenticated: () => allowed, hasPermission: () => allowed },
        },
      ],
    });
    http = TestBed.inject(HttpTestingController);
  });
  afterEach(() => http.verify());
  it('returns immediately and shares the pending HTTP response with the workspace', () => {
    expect(run()).toBe(true);
    let received: unknown;
    TestBed.inject(ApiClient)
      .evaluationAnalytics({
        module_key: 'flores',
        sort_by: 'fecha',
        sort_dir: 'desc',
        snapshot: true,
        snapshot_series: true,
        series_only: true,
        include_trend: false,
        metric: 'n_flores',
      })
      .subscribe((value) => (received = value));
    const request = http.expectOne((r) => r.url === '/v1/admin/evaluaciones/analitica');
    expect(received).toBeUndefined();
    request.flush({ summary: { evaluations: 1 } });
    expect(received).toEqual({ summary: { evaluations: 1 } });
  });
  it('does not fetch unpermitted modules or substitute an unfiltered query for a filtered URL', () => {
    allowed = false;
    run();
    allowed = true;
    run('unknown');
    run('flores', { desde: '2026-08-01' });
    run('flores', { indicador: 'cuajo' });
    http.expectNone((r) => r.url.includes('/analitica'));
  });
  it('allows a failed early read to be retried by the workspace', () => {
    run();
    http
      .expectOne((r) => r.url.includes('/analitica'))
      .flush({}, { status: 503, statusText: 'Unavailable' });
    expect(run()).toBe(true);
    http.expectOne((r) => r.url.includes('/analitica')).flush({});
  });
  it('retains an early response when the workspace subscribes only after HTTP completion', () => {
    run();
    http.expectOne((r) => r.url.includes('/analitica')).flush({ summary: { evaluations: 3 } });
    run();
    let received: unknown;
    TestBed.inject(ApiClient)
      .evaluationAnalytics({
        module_key: 'flores',
        sort_by: 'fecha',
        sort_dir: 'desc',
        snapshot: true,
        snapshot_series: true,
        series_only: true,
        include_trend: false,
        metric: 'n_flores',
      })
      .subscribe((value) => (received = value));
    http.expectNone((r) => r.url.includes('/analitica'));
    expect(received).toEqual({ summary: { evaluations: 3 } });
  });
});
