import { TestBed } from '@angular/core/testing';
import { of, Subject, BehaviorSubject } from 'rxjs';
import { ActivatedRoute, Router, convertToParamMap } from '@angular/router';
import { vi } from 'vitest';
import { SeguridadComponent } from './seguridad.component';
import { ApiClient } from '../../../core/api/api-client.service';
import { AuthService } from '../../../core/auth/auth.service';
import { AdminMasterPage } from '../../../core/api/models';
const page = (items: Record<string, unknown>[], current = 1, pages = 1): AdminMasterPage => ({
  items,
  meta: { page: current, page_size: 25, total: items.length, pages },
});
describe('Access workspace', () => {
  let c: SeguridadComponent, allowed: boolean;
  let routeParams: BehaviorSubject<ReturnType<typeof convertToParamMap>>;
  let api: {
    listUsers: ReturnType<typeof vi.fn>;
    listRoles: ReturnType<typeof vi.fn>;
    listMaster: ReturnType<typeof vi.fn>;
    createUser: ReturnType<typeof vi.fn>;
    updateUser: ReturnType<typeof vi.fn>;
  };
  beforeEach(() => {
    allowed = true;
    routeParams = new BehaviorSubject(convertToParamMap({}));
    api = {
      listUsers: vi.fn(() => of(page([]))),
      listRoles: vi.fn(() =>
        of(
          page([
            {
              rol_id: 1,
              codigo: 'lectura',
              permisos: [{ codigo: 'admin:datos:leer', descripcion: 'Consultar datos' }],
            },
          ]),
        ),
      ),
      listMaster: vi.fn(() => of(page([]))),
      createUser: vi.fn(() => of({})),
      updateUser: vi.fn(() => of({})),
    };
    TestBed.configureTestingModule({
      providers: [
        { provide: ApiClient, useValue: api },
        { provide: AuthService, useValue: { hasPermission: () => allowed } },
        { provide: ActivatedRoute, useValue: { queryParamMap: routeParams } },
        { provide: Router, useValue: { navigate: vi.fn() } },
      ],
    });
    c = TestBed.runInInjectionContext(() => new SeguridadComponent());
    c.ngOnInit();
  });
  it('does not reload roles or load reference catalogues when searching users or changing tabs', () => {
    c.filters.controls.search.setValue('ana');
    c.applyFilters();
    c.selectTab(1);
    expect(api.listRoles).toHaveBeenCalledTimes(1);
    expect(api.listMaster).not.toHaveBeenCalled();
    expect(c.permissionGroups()[0].items[0].codigo).toBe('admin:datos:leer');
  });
  it('loads every reference page, including lots beyond 500', () => {
    api.listMaster.mockImplementation((resource, query) =>
      of(
        page(
          resource === 'lotes' ? [{ lote_id: query.page, codigo: 'L' + query.page }] : [],
          query.page,
          resource === 'lotes' ? 2 : 1,
        ),
      ),
    );
    c.newUser();
    expect(c.optionsFor('lotes')).toHaveLength(2);
  });
  it('preserves scopes and omits an unchanged password from updates', () => {
    c.editUser({
      usuario_id: 7,
      nombre: 'Ana',
      email: 'ana@example.com',
      rol: 'lectura',
      activo: true,
      alcances: [{ lote_id: 800 }],
    });
    c.saveUser();
    expect(api.updateUser).toHaveBeenCalledWith(
      7,
      expect.objectContaining({ alcances: [{ lote_id: 800 }], rol: 'lectura' }),
    );
    expect(api.updateUser.mock.calls[0][1]).not.toHaveProperty('password');
  });
  it('blocks invalid, duplicate and unauthorized writes', () => {
    c.newUser();
    c.saveUser();
    expect(api.createUser).not.toHaveBeenCalled();
    c.userForm.patchValue({ nombre: 'Ana', email: 'ana@example.com' });
    api.createUser.mockReturnValue(new Subject());
    c.saveUser();
    c.saveUser();
    expect(api.createUser).toHaveBeenCalledTimes(1);
    c.saving.set(false);
    allowed = false;
    c.saveUser();
    expect(api.createUser).toHaveBeenCalledTimes(1);
  });
  it('compares permissions without granting them to other roles', () => {
    c.roles.set(
      page([
        {
          codigo: 'admin',
          permisos: [
            { codigo: 'admin:datos:leer', descripcion: 'Consultar' },
            { codigo: 'admin:datos:editar', descripcion: 'Editar' },
          ],
        },
        { codigo: 'lectura', permisos: [{ codigo: 'admin:datos:leer', descripcion: 'Consultar' }] },
      ]),
    );
    expect(c.permissionMatrix().find((p) => p.codigo.endsWith(':leer'))?.roles).toEqual([
      'admin',
      'lectura',
    ]);
    expect(c.permissionMatrix().find((p) => p.codigo.endsWith(':editar'))?.roles).toEqual([
      'admin',
    ]);
    c.permissionSearch.set('EDITAR');
    expect(c.permissionMatrix()).toHaveLength(1);
    c.permissionSearch.set('inexistente');
    expect(c.permissionMatrix()).toHaveLength(0);
  });
  it('opens a user role without issuing a new API request', () => {
    c.inspectRole('lectura');
    expect(c.selectedTab()).toBe(1);
    expect(c.selectedRole()?.['codigo']).toBe('lectura');
    c.selectTab(2);
    expect(TestBed.inject(Router).navigate).toHaveBeenLastCalledWith(
      [],
      expect.objectContaining({ queryParams: { vista: 'permisos' } }),
    );
    expect(api.listRoles).toHaveBeenCalledTimes(1);
    expect(api.listUsers).toHaveBeenCalledTimes(1);
  });
  it('restores search and pagination from history without refetching when only the view changes', () => {
    routeParams.next(convertToParamMap({ buscar: 'Ana', pagina: '2' }));
    expect(api.listUsers).toHaveBeenLastCalledWith({ page: 2, page_size: 25, search: 'Ana' });
    expect(c.filters.controls.search.value).toBe('Ana');
    const requests = api.listUsers.mock.calls.length;
    routeParams.next(convertToParamMap({ buscar: 'Ana', pagina: '2', vista: 'permisos' }));
    expect(c.selectedTab()).toBe(2);
    expect(api.listUsers).toHaveBeenCalledTimes(requests);
    routeParams.next(convertToParamMap({ pagina: '-9' }));
    expect(api.listUsers).toHaveBeenLastCalledWith({ page: 1, page_size: 25, search: undefined });
  });
  it('does not keep a stale user inspector after the directory changes', () => {
    c.selectedUser.set({ usuario_id: 99, nombre: 'Anterior' });
    c.applyFilters();
    expect(c.selectedUser()).toBeNull();
  });
  it('restores the selected role from a shared URL', () => {
    c.roles.set(page([{ codigo: 'admin' }, { codigo: 'lectura' }]));
    routeParams.next(convertToParamMap({ vista: 'roles', rol: 'lectura' }));
    expect(c.selectedRole()?.['codigo']).toBe('lectura');
    expect(api.listUsers).toHaveBeenCalledTimes(1);
  });
});
