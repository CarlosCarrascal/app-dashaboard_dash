import { TestBed } from '@angular/core/testing';
import { Subject } from 'rxjs';
import { vi } from 'vitest';
import { DashboardComponent } from './dashboard.component';
import { ApiClient } from '../../../core/api/api-client.service';
import { AuthService } from '../../../core/auth/auth.service';
import { AdminEvaluationSummary, AdminQASummary, AdminEvaluationPage } from '../../../core/api/models';
import { ADMIN_ROUTES } from '../admin.routes';

describe('Inicio del panel', () => {
  let summary: Subject<AdminEvaluationSummary>;
  let qa: Subject<AdminQASummary>;
  let api: { evaluationCounts: ReturnType<typeof vi.fn>; qualitySummary: ReturnType<typeof vi.fn>; listEvaluations: ReturnType<typeof vi.fn> };
  let recent: Subject<AdminEvaluationPage>[];
  let permissions: string[];
  let component: DashboardComponent;
  beforeEach(() => {
    permissions = ['admin:evaluaciones:leer', 'admin:qa:leer'];
    summary = new Subject(); qa = new Subject();
    recent = [];
    api = { listEvaluations: vi.fn(() => { const request = new Subject<AdminEvaluationPage>(); recent.push(request); return request; }), evaluationCounts: vi.fn(() => summary), qualitySummary: vi.fn(() => qa) };
    TestBed.configureTestingModule({ providers: [
      { provide: ApiClient, useValue: api },
      { provide: AuthService, useValue: { hasPermission: (p: string) => permissions.includes(p) } },
    ] });
    component = TestBed.runInInjectionContext(() => new DashboardComponent());
  });
  it('opens the dashboard at the authenticated root', async () => {
    const route = ADMIN_ROUTES.find(r => r.path === '');
    expect(await (route!.loadComponent! as () => Promise<unknown>)()).toBe(DashboardComponent);
  });
  it('shows evaluation data without waiting for QA and preserves it on QA failure', () => {
    component.ngOnInit();
    summary.next({ total: 10, lotes: 3, evaluadores: 2, por_modulo: [
      { module_key: 'estadios', total: 3, muestras: 300, lotes: 2, evaluadores: 2 },
      { module_key: 'flores', total: 7, muestras: 900, lotes: 3, evaluadores: 2 },
    ] });
    expect(component.loading()).toBe(false);
    expect(component.qualityLoading()).toBe(true);
    expect(component.share(3)).toBe(30);
    expect(component.activeFamilies()).toBe(2);
    qa.error(new Error('unavailable'));
    expect(component.summary()?.total).toBe(10);
    expect(component.error()).toBe(false);
    expect(component.qualityError()).toBe(true);
  });
  it('handles an empty dataset without invented percentages', () => {
    component.ngOnInit();
    summary.next({ total: 0, lotes: 0, evaluadores: 0, por_modulo: [] });
    expect(component.share(0)).toBe(0);
    expect(component.activeFamilies()).toBe(0);
    expect(component.date(null)).toBe('Sin capturas');
  });
  it('does not request restricted data', () => {
    permissions = [];
    component.ngOnInit();
    expect(api.evaluationCounts).not.toHaveBeenCalled();
    expect(api.qualitySummary).not.toHaveBeenCalled();
    expect(api.listEvaluations).not.toHaveBeenCalled();
  });
});




