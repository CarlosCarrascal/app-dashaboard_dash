import { TestBed } from '@angular/core/testing';
import { of, Subject, throwError } from 'rxjs';
import { vi } from 'vitest';
import { QaComponent } from './qa.component';
import { ApiClient } from '../../../core/api/api-client.service';
import { AuthService } from '../../../core/auth/auth.service';
import { AdminQARejectItem, AdminQAPage } from '../../../core/api/models';

const row: AdminQARejectItem = {
  rechazo_id: 1,
  motivo: 'EV_V1_OBSERVACION',
  hallazgo: 'EVALUACIONES-V1',
  tabla_origen: 'e05_seguimiento',
  tabla_destino: 'core.ev_fruto_observacion',
  fila: { numero_muestra: 7, source_row_number: 966 },
  estado_revision: 'pendiente',
  excede_umbral: false,
  cargado_en: '2026-09-08T09:46:00Z',
  detalle: '["VALOR_NO_PUBLICABLE:d07"]',
};
describe('QA review workspace', () => {
  let c: QaComponent;
  let reads: Subject<AdminQAPage>[];
  let api: {
    listQuality: ReturnType<typeof vi.fn>;
    qualitySummary: ReturnType<typeof vi.fn>;
    reviewQuality: ReturnType<typeof vi.fn>;
    confirmQualityDuplicates: ReturnType<typeof vi.fn>;
  };
  let allowed: boolean;
  beforeEach(() => {
    allowed = true;
    reads = [];
    api = {
      listQuality: vi.fn(() => {
        const request = new Subject<AdminQAPage>();
        reads.push(request);
        return request;
      }),
      qualitySummary: vi.fn(() => of({ total_rechazos: 100, alertas: 1, motivos: [] })),
      reviewQuality: vi.fn(() => of({})),
      confirmQualityDuplicates: vi.fn(() => of({ procesados: 1 })),
    };
    TestBed.configureTestingModule({
      providers: [
        { provide: ApiClient, useValue: api },
        { provide: AuthService, useValue: { hasPermission: () => allowed } },
      ],
    });
    c = TestBed.runInInjectionContext(() => new QaComponent());
    c.ngOnInit();
  });
  it('ignores obsolete filter responses and combines state with reason', () => {
    c.filterByReason('EV_V1_OBSERVACION');
    c.setState('corregir');
    reads[0].next({ items: [row], meta: { page: 1, page_size: 25, total: 100, pages: 4 } });
    expect(c.page()).toBeNull();
    expect(api.listQuality.mock.calls.at(-1)?.[0]).toMatchObject({
      motivo: 'EV_V1_OBSERVACION',
      estado_revision: 'corregir',
      page: 1,
    });
    reads[2].next({ items: [], meta: { page: 1, page_size: 25, total: 0, pages: 0 } });
    expect(c.loading()).toBe(false);
  });
  it('keeps existing rows while paging and uses server pagination', () => {
    const data = { items: [row], meta: { page: 1, page_size: 25, total: 100, pages: 4 } };
    reads[0].next(data);
    c.onPage({ pageIndex: 1, pageSize: 25, length: 100 });
    expect(c.page()).toBe(data);
    expect(c.loading()).toBe(true);
    expect(api.listQuality.mock.calls.at(-1)?.[0].page).toBe(2);
  });
  it('identifies migrated fruit evidence and preserves its original values', () => {
    expect(c.domainLabel(row)).toBe('Evaluaciones');
    expect(c.humanFields(row)).toEqual([
      { label: 'Muestra', value: '7' },
      { label: 'Fila de origen', value: '966' },
    ]);
    expect(c.findingText(row)).toBe('Valor no publicable · d07');
    expect(row.detalle).toBe('["VALOR_NO_PUBLICABLE:d07"]');
  });
  it('requires review permission and retains a stable retry key', () => {
    c.selectForReview(row);
    allowed = false;
    c.submitReview();
    expect(api.reviewQuality).not.toHaveBeenCalled();
    allowed = true;
    api.reviewQuality.mockReturnValue(throwError(() => new Error('network')));
    c.submitReview();
    c.submitReview();
    expect(api.reviewQuality.mock.calls[0][1].idempotency_key).toBe(
      api.reviewQuality.mock.calls[1][1].idempotency_key,
    );
    expect(c.selected()?.rechazo_id).toBe(1);
    expect(c.reviewing()).toBe(false);
  });
  it('limits bulk selection to eligible duplicates and avoids repeated IDs', () => {
    c.toggleDuplicate(row, true);
    expect(c.selectedDuplicateIds()).toEqual([]);
    const duplicate = { ...row, motivo: 'DUPLICADO_EXACTO' };
    c.toggleDuplicate(duplicate, true);
    c.toggleDuplicate(duplicate, true);
    expect(c.selectedDuplicateIds()).toEqual([1]);
    c.setState('pendiente');
    expect(c.selectedDuplicateIds()).toEqual([]);
  });
  it('calculates reason participation against all evidence, not the current page', () => {
    expect(c.reasonPercent(25)).toBe(25);
    c.summary.set({ total_rechazos: 0, alertas: 0, motivos: [] });
    expect(c.reasonPercent(0)).toBe(0);
  });
});
