import { TestBed } from '@angular/core/testing';
import { BehaviorSubject, of, Subject } from 'rxjs';
import { ActivatedRoute, Router, convertToParamMap } from '@angular/router';
import { vi } from 'vitest';
import { MaestrosComponent } from './maestros.component';
import { ApiClient } from '../../../core/api/api-client.service';
import { AuthService } from '../../../core/auth/auth.service';
import { AdminMasterPage } from '../../../core/api/models';

const result = (items: Record<string, unknown>[], page = 1, pages = 1): AdminMasterPage => ({
  items,
  meta: { page, page_size: 25, total: items.length, pages },
});
describe('Master catalogue workspace', () => {
  let c: MaestrosComponent,
    params: BehaviorSubject<ReturnType<typeof convertToParamMap>>,
    allowed: boolean;
  let api: {
    listMaster: ReturnType<typeof vi.fn>;
    createMaster: ReturnType<typeof vi.fn>;
    updateMaster: ReturnType<typeof vi.fn>;
  };
  let reads: Subject<AdminMasterPage>[];
  beforeEach(() => {
    allowed = true;
    reads = [];
    params = new BehaviorSubject(convertToParamMap({}));
    api = {
      listMaster: vi.fn(() => {
        const request = new Subject<AdminMasterPage>();
        reads.push(request);
        return request;
      }),
      createMaster: vi.fn(() => of({})),
      updateMaster: vi.fn(() => of({})),
    };
    TestBed.configureTestingModule({
      providers: [
        { provide: ApiClient, useValue: api },
        { provide: AuthService, useValue: { hasPermission: () => allowed } },
        { provide: ActivatedRoute, useValue: { queryParamMap: params } },
        { provide: Router, useValue: { navigate: vi.fn() } },
      ],
    });
    c = TestBed.runInInjectionContext(() => new MaestrosComponent());
    c.ngOnInit();
  });
  it('loads only the selected catalogue and discards obsolete responses', () => {
    expect(api.listMaster).toHaveBeenCalledTimes(1);
    params.next(convertToParamMap({ recurso: 'fundos' }));
    reads[0].next(result([{ empresa_id: 1, nombre: 'Old' }]));
    expect(c.response()).toBeNull();
    reads[1].next(result([{ fundo_id: 2, codigo: 'F2' }]));
    expect(c.response()?.items[0]['codigo']).toBe('F2');
  });
  it('reuses loaded catalogues on return without another request', () => {
    reads[0].next(result([{ empresa_id: 2, nombre: 'A' }]));
    params.next(convertToParamMap({ recurso: 'fundos' }));
    reads[1].next(result([]));
    params.next(convertToParamMap({ recurso: 'empresas' }));
    expect(api.listMaster).toHaveBeenCalledTimes(2);
    expect(c.response()?.items[0]['nombre']).toBe('A');
  });
  it('starts new records empty and prevents invalid writes', () => {
    c.newMaster();
    expect(c.masterForm.controls.nombre.value).toBeNull();
    c.saveMaster();
    expect(api.createMaster).not.toHaveBeenCalled();
    expect(c.masterForm.controls.nombre.touched).toBe(true);
  });
  it('preserves every editable field rather than only example fields', () => {
    params.next(convertToParamMap({ recurso: 'lotes' }));
    c.editMaster({
      lote_id: 8,
      modulo_id: 2,
      codigo: 'L8',
      turno_id: 3,
      variedad_id: 4,
      area_ha: 0,
      n_plantas: 0,
      fecha_siembra: '2020-01-01',
      maceta: 'M',
      tipo_fibra: 'F',
      key_map: 'K',
    });
    expect(c.masterForm.getRawValue()).toMatchObject({
      area_ha: 0,
      n_plantas: 0,
      maceta: 'M',
      tipo_fibra: 'F',
      key_map: 'K',
      fecha_siembra: '2020-01-01',
    });
  });
  it('paginates reference catalogues past the first 500 entries', () => {
    params.next(convertToParamMap({ recurso: 'muestreo' }));
    api.listMaster.mockImplementation((resource, q) =>
      of({
        items: q.page === 1 ? [{ lote_id: 1, codigo: 'L1' }] : [{ lote_id: 501, codigo: 'L501' }],
        meta: { page: q.page, page_size: 500, total: 501, pages: 2 },
      }),
    );
    c.newMaster();
    expect(c.referenceOptions()['lotes'].map((x) => x.value)).toEqual([1, 501]);
    expect(c.referenceLoading()).toBe(false);
  });
  it('enforces manage permission for all mutation entry points', () => {
    allowed = false;
    c.newMaster();
    c.editMaster({ empresa_id: 2 });
    c.deactivateMaster({ empresa_id: 2, activo: true });
    c.saveMaster();
    expect(c.editorOpen()).toBe(false);
    expect(api.updateMaster).not.toHaveBeenCalled();
    expect(api.createMaster).not.toHaveBeenCalled();
  });
});
