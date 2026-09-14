import { TestBed } from '@angular/core/testing';
import { HttpClient } from '@angular/common/http';
import { ActivatedRoute, convertToParamMap, Router } from '@angular/router';
import { BehaviorSubject, of } from 'rxjs';
import { vi } from 'vitest';
import { ApiClient } from '../../../core/api/api-client.service';
import { AuthService } from '../../../core/auth/auth.service';
import { EvaluacionesComponent } from './evaluaciones.component';
import { FieldAnalytics } from './field-analytics';

vi.mock('echarts/core', () => ({ use: vi.fn(), init: vi.fn() }));

describe('Evaluation page composition', () => {
  const detail = {
    id: 'ev_evaluacion:1',
    source_id: 1,
    source_table: 'ev_evaluacion',
    module_key: 'estadios',
    fecha: '2026-08-26',
    lote_id: 1,
    lote: 'Lote de prueba',
    fundo: 'Fundo',
    modulo: 'Módulo',
    evaluador: 'Evaluador',
    detalle: { e1: 10, e5: 90, total_origen: 100 },
  };
  const result = {
    module_key: 'estadios',
    desde: '2026-08-26',
    hasta: '2026-08-26',
    trend_desde: '2026-08-26',
    snapshot: true,
    grano: 'registro_access',
    grains: ['registro_access'],
    lots: [],
    states: [],
    trend: [],
    summary: {
      key: 'all',
      label: 'Consulta',
      evaluations: 1,
      observations: 0,
      complete: 1,
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

  function setup() {
    const query = new BehaviorSubject(convertToParamMap({ vista: 'registros' }));
    const api = {
      clearReadCache: vi.fn(),
      evaluationAnalytics: vi.fn((_query: Record<string, unknown>, _trend = false) => of(result)),
      listEvaluations: vi.fn(() =>
        of({ items: [detail], meta: { page: 1, page_size: 50, total: 1, pages: 1 } }),
      ),
      listMaster: vi.fn(() => of({ items: [], meta: { page: 1, pages: 1 } })),
      evaluationCard: vi.fn(() =>
        of({ ...detail, detalle: { ...detail.detalle, total_observaciones: 0 } }),
      ),
      evaluationDetail: vi.fn(() => of(detail)),
      correctEvaluation: vi.fn(() => of({ evaluacion: detail })),
    };
    TestBed.configureTestingModule({
      providers: [
        { provide: ApiClient, useValue: api },
        { provide: HttpClient, useValue: { get: vi.fn() } },
        { provide: AuthService, useValue: { hasPermission: () => true } },
        {
          provide: ActivatedRoute,
          useValue: {
            paramMap: of(convertToParamMap({ familia: 'estadios' })),
            queryParamMap: query,
          },
        },
        {
          provide: Router,
          useValue: {
            navigate: vi.fn(),
            createUrlTree: vi.fn(),
            serializeUrl: () => '/',
            url: '/',
            navigateByUrl: vi.fn(),
          },
        },
      ],
    });
    vi.stubGlobal(
      'ResizeObserver',
      class {
        observe() {}
        disconnect() {}
      },
    );
    const fixture = TestBed.createComponent(EvaluacionesComponent);
    fixture.detectChanges();
    return { fixture, api, query };
  }
  afterEach(() => vi.unstubAllGlobals());

  it('shares state between extracted filters and records and retains data when changing views', () => {
    const { fixture, api, query } = setup();
    expect(fixture.nativeElement.querySelector('app-evaluation-records').textContent).toContain(
      'Lote de prueba',
    );
    fixture.componentInstance.vm.toggleFilters();
    fixture.detectChanges();
    const filterForm = fixture.nativeElement.querySelector('app-evaluation-filters form');
    expect(filterForm).not.toBeNull();
    const input = filterForm.querySelector('input[formControlName="search"]');
    input.value = 'Lote';
    input.dispatchEvent(new Event('input'));
    expect(fixture.componentInstance.vm.filters.controls.search.value).toBe('Lote');
    const requests = api.evaluationAnalytics.mock.calls.filter(([, trend]) => !trend).length;
    query.next(convertToParamMap({ vista: 'analisis' }));
    fixture.detectChanges();
    expect(api.evaluationAnalytics.mock.calls.filter(([, trend]) => !trend).length).toBe(requests);
    expect(fixture.nativeElement.querySelector('app-evaluation-analysis')).not.toBeNull();
    fixture.destroy();
  });

  it('opens the extracted detail and correction form and invalidates reads after saving', () => {
    const { fixture, api } = setup();
    const open = fixture.nativeElement.querySelector(
      'button[aria-label="Ver evaluación ev_evaluacion:1"]',
    );
    open.click();
    fixture.detectChanges();
    expect(
      fixture.nativeElement.querySelector('app-evaluation-detail [role="dialog"]'),
    ).not.toBeNull();
    const edit = [...fixture.nativeElement.querySelectorAll('app-evaluation-detail button')].find(
      (button: HTMLButtonElement) => button.textContent?.includes('Corregir'),
    ) as HTMLButtonElement;
    edit.click();
    fixture.detectChanges();
    const form = fixture.nativeElement.querySelector('app-evaluation-correction form');
    expect(form).not.toBeNull();
    fixture.componentInstance.vm.correctionForm.controls.comentario.setValue(
      'Corrección de prueba',
    );
    form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    fixture.detectChanges();
    expect(api.correctEvaluation).toHaveBeenCalledOnce();
    expect(api.clearReadCache).toHaveBeenCalledOnce();
    expect(fixture.componentInstance.vm.editing()).toBe(false);
    fixture.destroy();
  });
});
