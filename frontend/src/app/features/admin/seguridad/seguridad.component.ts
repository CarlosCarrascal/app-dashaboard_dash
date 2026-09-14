import { A11yModule } from '@angular/cdk/a11y';
import { EMPTY, Subscription, expand, reduce } from 'rxjs';
import { DatePipe, DOCUMENT } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, OnInit, inject, signal, computed } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { ApiClient } from '../../../core/api/api-client.service';
import { AuthService } from '../../../core/auth/auth.service';
import { AdminMasterPage, UserMutationRequest } from '../../../core/api/models';
import { AppIconComponent } from '../../../shared/ui/app-icon.component';

type Row = Record<string, unknown>;

@Component({
  selector: 'app-seguridad',
  standalone: true,
  imports: [AppIconComponent, DatePipe, A11yModule, ReactiveFormsModule],
  templateUrl: './seguridad.component.html',
  styleUrl: './seguridad.component.scss',
})
export class SeguridadComponent implements OnInit {
  private readonly api = inject(ApiClient);
  private readonly formBuilder = inject(FormBuilder);
  private readonly auth = inject(AuthService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);
  private readonly document = inject(DOCUMENT);
  readonly navigation = [
    { label: 'Directorio', icon: 'users' },
    { label: 'Roles', icon: 'quality' },
    { label: 'Permisos', icon: 'grid' },
  ];
  private requestedPage = 1;
  private queryInitialized = false;

  readonly filters = this.formBuilder.nonNullable.group({ search: '' });
  readonly users = signal<AdminMasterPage | null>(null);
  readonly roles = signal<AdminMasterPage | null>(null);
  readonly loading = signal(false);
  readonly errorMessage = signal<string | null>(null);
  readonly successMessage = signal<string | null>(null);
  readonly editorOpen = signal(false);
  readonly editorSection = signal(0);
  readonly editorSections = ['Identidad', 'Perfil y vínculo', 'Alcance agrícola'];
  readonly editingUserId = signal<number | null>(null);
  readonly saving = signal(false);
  readonly selectedTab = signal(0);
  readonly userForm = this.formBuilder.group({
    email: ['', [Validators.required, Validators.email]],
    nombre: ['', Validators.required],
    rol: ['lectura', Validators.required],
    evaluador_id: [null as number | null],
    activo: [true],
    password: [''],
    comentario: [''],
    alcances: this.formBuilder.array([this.createScope()]),
  });
  readonly referenceOptions = signal<Record<string, Array<{ value: number; label: string }>>>({});
  readonly userColumns = [
    'nombre',
    'email',
    'rol',
    'evaluador',
    'activo',
    'ultimo_acceso',
    'acciones',
  ];

  ngOnInit(): void {
    this.route.queryParamMap.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((params) => {
      this.selectedTab.set(
        params.get('vista') === 'permisos' ? 2 : params.get('vista') === 'roles' ? 1 : 0,
      );
      this.selectedRoleCode.set(params.get('rol') ?? '');
      const search = params.get('buscar') ?? '';
      const rawPage = Number(params.get('pagina') ?? 1);
      const page = Number.isSafeInteger(rawPage) && rawPage > 0 ? rawPage : 1;
      if (!this.queryInitialized || search !== this.appliedSearch || page !== this.requestedPage) {
        this.queryInitialized = true;
        this.appliedSearch = search;
        this.filters.controls.search.setValue(search);
        this.load(page);
      }
    });
  }

  selectUser(row: Row): void {
    this.selectedUser.set(row);
    requestAnimationFrame(() =>
      this.document.getElementById('access-inspector')?.focus({
        preventScroll: (this.document.defaultView?.innerWidth ?? 0) >= 1280,
      }),
    );
  }

  chooseRole(code: string): void {
    this.selectedRoleCode.set(code);
    void this.router.navigate([], {
      relativeTo: this.route,
      queryParams: { rol: code },
      queryParamsHandling: 'merge',
    });
  }

  private persistDirectory(): void {
    void this.router.navigate([], {
      relativeTo: this.route,
      queryParams: {
        buscar: this.appliedSearch || null,
        pagina: this.requestedPage === 1 ? null : this.requestedPage,
      },
      queryParamsHandling: 'merge',
    });
  }

  selectTab(index: number): void {
    this.selectedTab.set(index);
    void this.router.navigate([], {
      relativeTo: this.route,
      queryParams: { vista: index === 2 ? 'permisos' : index === 1 ? 'roles' : null },
      queryParamsHandling: 'merge',
    });
  }

  applyFilters(): void {
    this.appliedSearch = this.filters.controls.search.value;
    this.load();
    this.persistDirectory();
  }

  clearFilters(): void {
    this.filters.reset({ search: '' });
    this.appliedSearch = '';
    this.load();
    this.persistDirectory();
  }

  canManage(): boolean {
    return this.auth.hasPermission('admin:usuarios:gestionar');
  }

  newUser(): void {
    if (!this.canManage() || this.saving()) return;
    this.editorSection.set(0);
    this.loadReferenceOptions();
    this.mutationKey = crypto.randomUUID();
    this.editingUserId.set(null);
    this.userForm.reset({
      email: '',
      nombre: '',
      rol: 'lectura',
      evaluador_id: null,
      activo: true,
      password: '',
      comentario: '',
    });
    this.userForm.controls.alcances.clear();
    this.addScope();
    this.errorMessage.set(null);
    this.successMessage.set(null);
    this.editorOpen.set(true);
  }

  editUser(row: Row): void {
    if (!this.canManage() || this.saving()) return;
    this.editorSection.set(0);
    this.loadReferenceOptions();
    this.mutationKey = crypto.randomUUID();
    const usuarioId = Number(row['usuario_id']);
    if (!Number.isFinite(usuarioId) || usuarioId <= 0) return;
    this.editingUserId.set(usuarioId);
    this.userForm.reset({
      email: String(row['email'] ?? ''),
      nombre: String(row['nombre'] ?? ''),
      rol: String(row['rol'] ?? 'lectura'),
      evaluador_id: Number(row['evaluador_id']) || null,
      activo: Boolean(row['activo']),
      password: '',
      comentario: '',
    });
    this.userForm.controls.alcances.clear();
    const scopes = Array.isArray(row['alcances']) ? (row['alcances'] as Row[]) : [];
    for (const scope of scopes) this.addScope(scope);
    if (!scopes.length) this.addScope();
    this.errorMessage.set(null);
    this.successMessage.set(null);
    this.editorOpen.set(true);
  }

  cancelEditor(): void {
    if (this.saving()) return;
    this.editorOpen.set(false);
    this.editingUserId.set(null);
  }

  saveUser(): void {
    if (!this.canManage() || this.saving()) return;
    if (this.userForm.invalid) {
      this.editorSection.set(0);
      this.userForm.markAllAsTouched();
      this.errorMessage.set('Completa correctamente el nombre, correo y rol.');
      return;
    }
    const values = this.userForm.getRawValue();
    const alcances = values.alcances
      .map((scope) =>
        Object.fromEntries(Object.entries(scope).filter(([, value]) => Number(value) > 0)),
      )
      .filter((scope) => Object.keys(scope).length > 0);
    const payload: UserMutationRequest = {
      email: values.email || null,
      nombre: values.nombre || null,
      rol: values.rol as UserMutationRequest['rol'],
      evaluador_id: values.evaluador_id || null,
      activo: values.activo,
      alcances,
      idempotency_key: this.mutationKey,
      comentario: values.comentario || null,
    };
    const password = values.password;
    if (password) payload.password = password;
    this.saving.set(true);
    this.errorMessage.set(null);
    const usuarioId = this.editingUserId();
    const request$ = usuarioId
      ? this.api.updateUser(usuarioId, payload)
      : this.api.createUser(payload);
    request$.subscribe({
      next: () => {
        this.saving.set(false);
        this.editorOpen.set(false);
        this.editingUserId.set(null);
        this.successMessage.set('Usuario guardado y auditado correctamente.');
        this.selectedUser.set(null);
        this.load();
      },
      error: (error: unknown) => {
        this.saving.set(false);
        this.errorMessage.set(this.messageFor(error, 'No se pudo guardar el usuario.'));
      },
    });
  }

  deactivateUser(row: Row): void {
    if (!this.canManage() || this.saving()) return;
    const usuarioId = Number(row['usuario_id']);
    if (
      !Number.isFinite(usuarioId) ||
      usuarioId <= 0 ||
      !window.confirm(`¿Desactivar el usuario ${String(row['email'] ?? usuarioId)}?`)
    )
      return;
    this.saving.set(true);
    this.errorMessage.set(null);
    this.api
      .updateUser(usuarioId, {
        activo: false,
        comentario: 'Desactivación desde el panel administrativo',
        idempotency_key: crypto.randomUUID(),
      })
      .subscribe({
        next: () => {
          this.saving.set(false);
          this.successMessage.set('Usuario desactivado correctamente.');
          this.load();
        },
        error: (error: unknown) => {
          this.saving.set(false);
          this.errorMessage.set(this.messageFor(error, 'No se pudo desactivar el usuario.'));
        },
      });
  }

  permissions(role: Row): Array<{ codigo: string; descripcion: string }> {
    const value = role['permisos'];
    if (!Array.isArray(value)) {
      return [];
    }
    return value.filter((item): item is { codigo: string; descripcion: string } => {
      return Boolean(item && typeof item === 'object' && 'codigo' in item);
    });
  }

  scopeControls() {
    return this.userForm.controls.alcances.controls;
  }

  addScope(value: Row = {}): void {
    this.userForm.controls.alcances.push(this.createScope(value));
  }

  removeScope(index: number): void {
    if (this.userForm.controls.alcances.length === 1) {
      this.userForm.controls.alcances.at(0).reset();
      return;
    }
    this.userForm.controls.alcances.removeAt(index);
  }

  optionsFor(resource: string): Array<{ value: number; label: string }> {
    return this.referenceOptions()[resource] ?? [];
  }

  display(value: unknown): string {
    if (value === null || value === undefined || value === '') {
      return '—';
    }
    return typeof value === 'boolean' ? (value ? 'Activo' : 'Inactivo') : String(value);
  }

  readonly selectedUser = signal<Row | null>(null);
  readonly selectedRoleCode = signal('');
  readonly permissionSearch = signal('');
  readonly selectedRole = computed(
    () =>
      this.roles()?.items.find((r) => r['codigo'] === this.selectedRoleCode()) ??
      this.roles()?.items[0] ??
      null,
  );
  readonly permissionGroups = computed(() => {
    const role = this.selectedRole();
    const groups = new Map<string, Array<{ codigo: string; descripcion: string }>>();
    for (const p of role ? this.permissions(role) : []) {
      if (
        !(p.codigo + ' ' + p.descripcion)
          .toLowerCase()
          .includes(this.permissionSearch().toLowerCase())
      )
        continue;
      const key = p.codigo.split(':').slice(0, -1).join(' · ') || 'General';
      groups.set(key, [...(groups.get(key) ?? []), p]);
    }
    return [...groups].map(([name, items]) => ({ name, items }));
  });
  readonly permissionMatrix = computed(() => {
    const entries = new Map<string, { codigo: string; descripcion: string; roles: string[] }>();
    for (const role of this.roles()?.items ?? []) {
      for (const permission of this.permissions(role)) {
        const entry = entries.get(permission.codigo) ?? { ...permission, roles: [] };
        entry.roles.push(String(role['codigo']));
        entries.set(permission.codigo, entry);
      }
    }
    const term = this.permissionSearch().trim().toLowerCase();
    return [...entries.values()]
      .filter((p) => (p.codigo + ' ' + p.descripcion).toLowerCase().includes(term))
      .sort((a, b) => a.codigo.localeCompare(b.codigo));
  });
  permissionArea(code: string): string {
    const key = code.split(':').slice(0, -1).join(':');
    return (
      (
        {
          'admin:evaluaciones': 'Evaluaciones',
          'admin:usuarios': 'Usuarios',
          'admin:maestros': 'Maestros',
          'admin:qa': 'Calidad de datos',
          'campo:evaluaciones': 'Captura de campo',
          'api:evaluaciones': 'Captura de campo',
          'admin:panel': 'Panel administrativo',
          'admin:reportes': 'Reportes',
        } as Record<string, string>
      )[key] ?? key.replaceAll(':', ' · ')
    );
  }
  inspectRole(code: unknown): void {
    this.selectedRoleCode.set(String(code));
    this.permissionSearch.set('');
    this.selectedTab.set(1);
    void this.router.navigate([], {
      relativeTo: this.route,
      queryParams: { vista: 'roles', rol: String(code) },
      queryParamsHandling: 'merge',
    });
  }
  readonly referenceLoading = signal(false);
  readonly referenceError = signal(false);
  private referencesRequested = false;
  private mutationKey = crypto.randomUUID();
  private userRequest?: Subscription;
  private appliedSearch = '';
  readonly scopeFields = [
    { key: 'empresa_id', resource: 'empresas', label: 'Empresa' },
    { key: 'fundo_id', resource: 'fundos', label: 'Fundo' },
    { key: 'modulo_id', resource: 'modulos', label: 'Módulo' },
    { key: 'lote_id', resource: 'lotes', label: 'Lote' },
  ];
  initials(row: Row): string {
    return String(row['nombre'] || row['email'] || '?')
      .trim()
      .split(/\s+/)
      .slice(0, 2)
      .map((p) => p[0])
      .join('')
      .toUpperCase();
  }
  roleLabel(code: unknown): string {
    return (
      (
        {
          admin: 'Administrador',
          agronomo: 'Agrónomo',
          evaluador: 'Evaluador',
          lectura: 'Lectura',
        } as Record<string, string>
      )[String(code)] ?? String(code ?? 'Sin rol').replaceAll('_', ' ')
    );
  }
  scopes(row: Row): Row[] {
    return Array.isArray(row['alcances']) ? (row['alcances'] as Row[]) : [];
  }
  scopeLabel(scope: Row): string {
    return this.scopeFields
      .filter((f) => scope[f.key])
      .map(
        (f) =>
          `${f.label}: ${scope[f.resource === 'empresas' ? 'empresa' : f.resource === 'fundos' ? 'fundo' : f.resource === 'modulos' ? 'modulo' : 'lote'] ?? scope[f.key]}`,
      )
      .join(' · ');
  }
  userPermissions(row: Row) {
    return this.permissions(this.roles()?.items.find((r) => r['codigo'] === row['rol']) ?? {});
  }
  refresh(): void {
    this.api.clearReadCache();
    this.load(this.users()?.meta.page ?? 1);
    this.loadRoles();
  }
  page(number: number): void {
    if (!this.loading() && number >= 1 && number <= (this.users()?.meta.pages ?? 1)) {
      this.load(number);
      this.persistDirectory();
    }
  }
  private load(page = 1): void {
    this.requestedPage = page;
    this.userRequest?.unsubscribe();
    this.loading.set(true);
    this.errorMessage.set(null);
    this.userRequest = this.api
      .listUsers({ page, page_size: 25, search: this.appliedSearch || undefined })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (response) => {
          this.users.set(response);
          const selected = this.selectedUser();
          if (selected)
            this.selectedUser.set(
              response.items.find((row) => row['usuario_id'] === selected['usuario_id']) ?? null,
            );
          this.loading.set(false);
        },
        error: (error) => {
          this.errorMessage.set(this.messageFor(error));
          this.loading.set(false);
        },
      });
    if (!this.roles()) this.loadRoles();
  }
  private loadRoles(): void {
    this.api
      .listRoles({ page: 1, page_size: 100 })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (response) => this.roles.set(response),
        error: (error) => this.errorMessage.set(this.messageFor(error)),
      });
  }

  private createScope(value: Row = {}) {
    return this.formBuilder.group({
      empresa_id: [Number(value['empresa_id']) || (null as number | null)],
      fundo_id: [Number(value['fundo_id']) || (null as number | null)],
      modulo_id: [Number(value['modulo_id']) || (null as number | null)],
      lote_id: [Number(value['lote_id']) || (null as number | null)],
    });
  }

  loadReferenceOptions(): void {
    if (this.referencesRequested) return;
    this.referencesRequested = true;
    this.referenceLoading.set(true);
    this.referenceError.set(false);
    const resources = ['empresas', 'fundos', 'modulos', 'lotes', 'evaluadores'] as const;
    let pending = resources.length;
    const done = () => {
      if (--pending === 0) this.referenceLoading.set(false);
    };
    for (const resource of resources) {
      this.api
        .listMaster(resource, { page: 1, page_size: 500 })
        .pipe(
          expand((page) =>
            page.meta.page < page.meta.pages
              ? this.api.listMaster(resource, { page: page.meta.page + 1, page_size: 500 })
              : EMPTY,
          ),
          reduce((rows: Row[], page) => [...rows, ...page.items], []),
          takeUntilDestroyed(this.destroyRef),
        )
        .subscribe({
          next: (rows) => {
            this.referenceOptions.update((current) => ({
              ...current,
              [resource]: rows.map((row) => ({
                value: Number(
                  row[
                    resource === 'empresas'
                      ? 'empresa_id'
                      : resource === 'fundos'
                        ? 'fundo_id'
                        : resource === 'modulos'
                          ? 'modulo_id'
                          : resource === 'lotes'
                            ? 'lote_id'
                            : 'evaluador_id'
                  ],
                ),
                label: this.referenceLabel(resource, row),
              })),
            }));
            done();
          },
          error: () => {
            this.referenceError.set(true);
            this.referencesRequested = false;
            done();
          },
        });
    }
  }

  private referenceLabel(resource: string, row: Row): string {
    if (resource === 'empresas') return String(row['nombre'] ?? 'Empresa');
    if (resource === 'fundos') return `${row['empresa'] ?? ''} · ${row['codigo'] ?? ''}`;
    if (resource === 'modulos') return `${row['fundo'] ?? ''} · ${row['codigo'] ?? ''}`;
    if (resource === 'lotes')
      return `${row['fundo'] ?? ''} · ${row['modulo'] ?? ''} · ${row['codigo'] ?? ''}`;
    return `${row['nombres'] ?? ''} ${row['apellidos'] ?? ''} · ${row['dni'] ?? ''}`.trim();
  }

  private messageFor(
    error: unknown,
    fallback = 'No se pudo consultar la configuración de seguridad.',
  ): string {
    if (error instanceof HttpErrorResponse && typeof error.error?.detail === 'string') {
      return error.error.detail;
    }
    return fallback;
  }
}
