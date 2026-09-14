import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import type { PageEvent } from '@angular/material/paginator';
import { DecimalPipe } from '@angular/common';
import { A11yModule } from '@angular/cdk/a11y';
import { Subscription, EMPTY, expand, reduce, of } from 'rxjs';
import { ActivatedRoute, Router } from '@angular/router';
import { ApiClient } from '../../../core/api/api-client.service';
import { AuthService } from '../../../core/auth/auth.service';
import { AdminMasterPage, MasterMutationRequest, MasterResource } from '../../../core/api/models';
import { AppIconComponent } from '../../../shared/ui/app-icon.component';

interface MasterOption {
  resource: MasterResource;
  label: string;
  icon: string;
}

interface MasterColumn {
  key: string;
  label: string;
}

type MasterFieldType = 'text' | 'number' | 'date' | 'toggle' | 'select';

interface MasterField {
  key: string;
  label: string;
  type: MasterFieldType;
  required?: boolean;
  min?: number;
  options?: string;
  hint?: string;
}

interface FieldOption {
  value: string | number;
  label: string;
}

@Component({
  selector: 'app-maestros',
  standalone: true,
  imports: [AppIconComponent, DecimalPipe, A11yModule, ReactiveFormsModule],
  templateUrl: './maestros.component.html',
  styleUrl: './maestros.component.scss',
})
export class MaestrosComponent implements OnInit {
  private readonly api = inject(ApiClient);
  private readonly auth = inject(AuthService);
  private readonly formBuilder = inject(FormBuilder);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);

  readonly options: MasterOption[] = [
    { resource: 'empresas', label: 'Empresas', icon: 'structure' },
    { resource: 'fundos', label: 'Fundos', icon: 'leaf' },
    { resource: 'modulos', label: 'Módulos', icon: 'grid' },
    { resource: 'lotes', label: 'Lotes', icon: 'grid' },
    { resource: 'evaluadores', label: 'Evaluadores', icon: 'person' },
    { resource: 'campanias', label: 'Campañas', icon: 'calendar' },
    { resource: 'variedades', label: 'Variedades', icon: 'leaf' },
    { resource: 'turnos', label: 'Turnos', icon: 'clock' },
    { resource: 'muestreo', label: 'Muestreo', icon: 'evaluations' },
  ];
  readonly groups: Array<{ label: string; resources: MasterResource[] }> = [
    { label: 'Estructura territorial', resources: ['empresas', 'fundos', 'modulos', 'lotes'] },
    { label: 'Personas', resources: ['evaluadores'] },
    {
      label: 'Configuración del cultivo',
      resources: ['variedades', 'campanias', 'turnos', 'muestreo'],
    },
  ];
  readonly view = signal<'cards' | 'table'>('cards');
  readonly detail = signal<Record<string, unknown> | null>(null);
  readonly columnsOpen = signal(false);
  readonly hiddenColumns = signal<string[]>([]);
  readonly visibleColumns = computed(() =>
    this.columnsFor(this.selectedResource()).filter((c) => !this.hiddenColumns().includes(c.key)),
  );
  readonly visibleFields = computed(() =>
    this.detail()
      ? Object.entries(this.detail()!)
          .filter(([k]) => !['es_sentinel', 'es_ficticio'].includes(k))
          .map(([key, value]) => ({
            key,
            label:
              this.columnsFor(this.selectedResource()).find((c) => c.key === key)?.label ??
              this.fieldsFor(this.selectedResource()).find((f) => f.key === key)?.label ??
              key.replaceAll('_', ' '),
            value: this.display(value),
          }))
      : [],
  );
  readonly counts = signal<Partial<Record<MasterResource, number>>>({});
  readonly referenceLoading = signal(false);
  readonly referenceError = signal(false);
  private pendingReferences = 0;
  private referencesRequested = new Set<MasterResource>();
  private listRequest?: Subscription;
  private mutationKey = '';
  private appliedSearch = '';
  private readonly cache = new Map<string, { value: AdminMasterPage; expires: number }>();
  option(resource: MasterResource): MasterOption {
    return this.options.find((o) => o.resource === resource)!;
  }
  description(): string {
    return (
      {
        empresas: 'Organizaciones que agrupan la operación agrícola.',
        fundos: 'Unidades de campo vinculadas a una empresa.',
        modulos: 'Divisiones del fundo para organizar el trabajo de campo.',
        lotes: 'Ubicación, variedad y superficie de cada unidad productiva.',
        evaluadores: 'Identificación y disponibilidad del equipo de evaluación.',
        campanias: 'Periodos que organizan la actividad agrícola.',
        variedades: 'Variedades disponibles para identificar los cultivos.',
        turnos: 'Códigos de turno asociados a los lotes.',
        muestreo: 'Cantidad y ubicación de las muestras requeridas por evaluación.',
      } as Record<MasterResource, string>
    )[this.selectedResource()];
  }
  primaryLabel(row: Record<string, unknown>): string {
    return this.selectedResource() === 'evaluadores'
      ? [row['nombres'], row['apellidos']].filter(Boolean).join(' ') ||
          String(row['dni'] ?? 'Evaluador')
      : String(
          row['nombre'] ||
            row['alias_operativo'] ||
            row['codigo'] ||
            row['evaluacion'] ||
            'Registro',
        );
  }
  contextLabel(row: Record<string, unknown>): string {
    return (
      [row['empresa'], row['fundo'], row['modulo'], row['lote']].filter(Boolean).join(' / ') ||
      (this.selectedResource() === 'evaluadores'
        ? String(row['dni'] || 'Sin DNI')
        : 'Registro de catálogo')
    );
  }
  toggleColumn(key: string): void {
    this.hiddenColumns.update((cols) =>
      cols.includes(key) ? cols.filter((c) => c !== key) : [...cols, key],
    );
  }
  refresh(): void {
    this.api.clearReadCache();
    this.cache.clear();
    this.load(this.response()?.meta.page ?? 1);
  }
  showDetail(row: Record<string, unknown>): void {
    this.detail.set(row);
    this.errorMessage.set(null);
  }
  numeric(key: string): boolean {
    return ['area_ha', 'n_plantas', 'muestras'].includes(key) || key.endsWith('_id');
  }
  fieldInvalid(key: string): boolean {
    const control = this.masterForm.get(key);
    return !!control?.invalid && !!control.touched;
  }

  readonly filters = this.formBuilder.nonNullable.group({ search: '' });
  readonly selectedResource = signal<MasterResource>('empresas');
  readonly response = signal<AdminMasterPage | null>(null);
  readonly loading = signal(false);
  readonly errorMessage = signal<string | null>(null);
  readonly successMessage = signal<string | null>(null);
  readonly editingId = signal<number | null>(null);
  readonly editorOpen = signal(false);
  readonly saving = signal(false);
  readonly masterForm = this.formBuilder.group({
    nombre: [''],
    activo: [true],
    empresa_id: [null as number | null],
    codigo: [''],
    alias_operativo: [''],
    fundo_id: [null as number | null],
    modulo_id: [null as number | null],
    turno_id: [null as number | null],
    variedad_id: [null as number | null],
    area_ha: [null as number | null],
    n_plantas: [null as number | null],
    fecha_siembra: [''],
    maceta: [''],
    tipo_fibra: [''],
    key_map: [''],
    dni: [''],
    nombres: [''],
    apellidos: [''],
    zona: [''],
    celular: [''],
    inicio_labores: [''],
    nacimiento: [''],
    en_maestro: [true],
    fecha_inicio: [''],
    fecha_fin: [''],
    origen_fechas: ['panel'],
    lote_id: [null as number | null],
    evaluacion: [''],
    cortina: [null as number | null],
    hilera: [null as number | null],
    planta: [null as number | null],
    muestras: [null as number | null],
    comentario: [''],
  });
  readonly referenceOptions = signal<Record<string, FieldOption[]>>({});
  readonly activeFields = computed(() => this.fieldsFor(this.selectedResource()));

  ngOnInit(): void {
    this.route.queryParamMap.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((params) => {
      const resource = params.get('recurso');
      const selected = this.options.find((option) => option.resource === resource)?.resource;
      this.selectedResource.set(selected ?? 'empresas');
      this.filters.controls.search.setValue(params.get('buscar') || '');
      this.appliedSearch = this.filters.controls.search.value;
      this.editorOpen.set(false);
      this.detail.set(null);
      this.hiddenColumns.set([]);
      this.columnsOpen.set(false);
      this.view.set(
        ['empresas', 'fundos', 'variedades', 'turnos'].includes(this.selectedResource())
          ? 'cards'
          : 'table',
      );
      this.response.set(null);
      this.load(Number(params.get('pagina')) || 1);
    });
  }

  selectResource(resource: MasterResource): void {
    if (resource === this.selectedResource()) return;
    this.editorOpen.set(false);
    this.successMessage.set(null);
    void this.router.navigate([], {
      relativeTo: this.route,
      queryParams: { recurso: resource },
    });
  }

  applyFilters(): void {
    const search = this.filters.controls.search.value;
    if (search === this.appliedSearch) this.load(1);
    else
      void this.router.navigate([], {
        relativeTo: this.route,
        queryParams: { recurso: this.selectedResource(), buscar: search || null },
      });
  }

  onPage(event: PageEvent): void {
    this.load(event.pageIndex + 1, event.pageSize);
  }

  columnsFor(resource: MasterResource): MasterColumn[] {
    const definitions: Record<MasterResource, MasterColumn[]> = {
      empresas: [
        { key: 'empresa_id', label: 'ID' },
        { key: 'nombre', label: 'Empresa' },
        { key: 'activo', label: 'Estado' },
        { key: 'creado_en', label: 'Creada' },
      ],
      fundos: [
        { key: 'fundo_id', label: 'ID' },
        { key: 'empresa', label: 'Empresa' },
        { key: 'codigo', label: 'Código' },
        { key: 'alias_operativo', label: 'Alias' },
        { key: 'activo', label: 'Estado' },
      ],
      modulos: [
        { key: 'modulo_id', label: 'ID' },
        { key: 'empresa', label: 'Empresa' },
        { key: 'fundo', label: 'Fundo' },
        { key: 'codigo', label: 'Código' },
        { key: 'activo', label: 'Estado' },
      ],
      lotes: [
        { key: 'lote_id', label: 'ID' },
        { key: 'empresa', label: 'Empresa' },
        { key: 'fundo', label: 'Fundo' },
        { key: 'modulo', label: 'Módulo' },
        { key: 'codigo', label: 'Lote' },
        { key: 'variedad', label: 'Variedad' },
        { key: 'area_ha', label: 'Área ha' },
      ],
      evaluadores: [
        { key: 'evaluador_id', label: 'ID' },
        { key: 'dni', label: 'DNI' },
        { key: 'nombres', label: 'Nombres' },
        { key: 'apellidos', label: 'Apellidos' },
        { key: 'codigo', label: 'Código' },
        { key: 'zona', label: 'Zona' },
        { key: 'activo', label: 'Estado' },
      ],
      campanias: [
        { key: 'campania_id', label: 'ID' },
        { key: 'codigo', label: 'Campaña' },
        { key: 'fecha_inicio', label: 'Inicio' },
        { key: 'fecha_fin', label: 'Fin' },
        { key: 'origen_fechas', label: 'Origen' },
      ],
      variedades: [
        { key: 'variedad_id', label: 'ID' },
        { key: 'nombre', label: 'Variedad' },
      ],
      turnos: [
        { key: 'turno_id', label: 'ID' },
        { key: 'codigo', label: 'Turno' },
      ],
      muestreo: [
        { key: 'muestra_id', label: 'ID' },
        { key: 'empresa', label: 'Empresa' },
        { key: 'fundo', label: 'Fundo' },
        { key: 'modulo', label: 'Módulo' },
        { key: 'lote', label: 'Lote' },
        { key: 'evaluacion', label: 'Evaluación' },
        { key: 'muestras', label: 'Muestras' },
      ],
    };
    return definitions[resource];
  }

  display(value: unknown): string {
    if (value === null || value === undefined || value === '') {
      return '—';
    }
    if (typeof value === 'boolean') {
      return value ? 'Activo' : 'Inactivo';
    }
    if (typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value))
      return value.split('-').reverse().join('/');
    if (
      typeof value === 'string' &&
      /^\d{4}-\d{2}-\d{2}T/.test(value) &&
      !Number.isNaN(Date.parse(value))
    )
      return new Intl.DateTimeFormat('es-PE', {
        dateStyle: 'short',
        timeStyle: 'short',
        timeZone: 'America/Lima',
      }).format(new Date(value));
    return String(value);
  }

  selectedLabel(): string {
    return this.options.find((option) => option.resource === this.selectedResource())?.label ?? '';
  }

  canManage(): boolean {
    return this.auth.hasPermission('admin:maestros:gestionar');
  }

  newMaster(): void {
    if (!this.canManage()) return;
    this.mutationKey = crypto.randomUUID();
    this.loadReferenceOptions();
    this.editingId.set(null);
    this.configureEditor({ activo: true, en_maestro: true, origen_fechas: 'panel' });
    this.errorMessage.set(null);
    this.editorOpen.set(true);
  }

  editMaster(row: Record<string, unknown>): void {
    if (!this.canManage()) return;
    this.mutationKey = crypto.randomUUID();
    this.loadReferenceOptions();
    const id = this.idFor(this.selectedResource(), row);
    if (!id) return;
    this.editingId.set(id);
    this.configureEditor(this.editableValues(this.selectedResource(), row));
    this.errorMessage.set(null);
    this.editorOpen.set(true);
  }

  cancelEditor(): void {
    if (this.saving()) return;
    this.editorOpen.set(false);
    this.editingId.set(null);
  }

  saveMaster(): void {
    if (!this.canManage() || this.saving()) return;
    if (this.masterForm.invalid) {
      this.masterForm.markAllAsTouched();
      this.errorMessage.set('Revisa los campos obligatorios antes de guardar.');
      return;
    }
    const raw = this.masterForm.getRawValue();
    const values: Record<string, unknown> = {};
    for (const field of this.activeFields()) {
      const value = raw[field.key as keyof typeof raw];
      values[field.key] = value === '' ? null : value;
    }
    const payload: MasterMutationRequest = {
      valores: values,
      comentario: raw.comentario || null,
      idempotency_key: this.mutationKey || crypto.randomUUID(),
    };
    this.saving.set(true);
    this.errorMessage.set(null);
    const id = this.editingId();
    const request$ = id
      ? this.api.updateMaster(this.selectedResource(), id, payload)
      : this.api.createMaster(this.selectedResource(), payload);
    request$.subscribe({
      next: () => {
        this.saving.set(false);
        this.editorOpen.set(false);
        this.editingId.set(null);
        this.successMessage.set(`${this.selectedLabel()} guardado y auditado correctamente.`);
        this.cache.clear();
        this.referencesRequested.clear();
        this.detail.set(null);
        this.load(1);
      },
      error: (error: unknown) => {
        this.saving.set(false);
        this.errorMessage.set(this.messageFor(error, 'No se pudo guardar el maestro.'));
      },
    });
  }

  deactivateMaster(row: Record<string, unknown>): void {
    const id = this.idFor(this.selectedResource(), row);
    if (!this.canManage() || this.saving() || !id || !this.hasActiveField(this.selectedResource()))
      return;
    const payload: MasterMutationRequest = {
      valores: { activo: false },
      comentario: 'Desactivación desde el panel administrativo',
      idempotency_key: crypto.randomUUID(),
    };
    this.saving.set(true);
    this.api.updateMaster(this.selectedResource(), id, payload).subscribe({
      next: () => {
        this.saving.set(false);
        this.successMessage.set(`${this.selectedLabel()} desactivado correctamente.`);
        this.cache.clear();
        this.detail.set(null);
        this.load(this.response()?.meta.page ?? 1);
      },
      error: (error: unknown) => {
        this.saving.set(false);
        this.errorMessage.set(this.messageFor(error, 'No se pudo desactivar el registro.'));
      },
    });
  }

  hasActiveField(resource: MasterResource): boolean {
    return ['empresas', 'fundos', 'modulos', 'evaluadores'].includes(resource);
  }

  fieldsFor(resource: MasterResource): MasterField[] {
    const definitions: Record<MasterResource, MasterField[]> = {
      empresas: [
        { key: 'nombre', label: 'Nombre de la empresa', type: 'text', required: true },
        { key: 'activo', label: 'Empresa activa', type: 'toggle' },
      ],
      fundos: [
        {
          key: 'empresa_id',
          label: 'Empresa',
          type: 'select',
          options: 'empresas',
          required: true,
        },
        { key: 'codigo', label: 'Código del fundo', type: 'text', required: true },
        {
          key: 'alias_operativo',
          label: 'Nombre operativo',
          type: 'text',
          hint: 'Nombre usado por el equipo de campo',
        },
        { key: 'activo', label: 'Fundo activo', type: 'toggle' },
      ],
      modulos: [
        { key: 'fundo_id', label: 'Fundo', type: 'select', options: 'fundos', required: true },
        { key: 'codigo', label: 'Código del módulo', type: 'text', required: true },
        { key: 'activo', label: 'Módulo activo', type: 'toggle' },
      ],
      lotes: [
        {
          key: 'modulo_id',
          label: 'Módulo agrícola',
          type: 'select',
          options: 'modulos',
          required: true,
        },
        { key: 'codigo', label: 'Código del lote', type: 'text', required: true },
        { key: 'turno_id', label: 'Turno', type: 'select', options: 'turnos', required: true },
        {
          key: 'variedad_id',
          label: 'Variedad',
          type: 'select',
          options: 'variedades',
          required: true,
        },
        { key: 'area_ha', label: 'Área (ha)', type: 'number', min: 0, required: true },
        { key: 'n_plantas', label: 'Número de plantas', type: 'number', min: 0, required: true },
        { key: 'fecha_siembra', label: 'Fecha de siembra', type: 'date' },
        { key: 'maceta', label: 'Maceta', type: 'text' },
        { key: 'tipo_fibra', label: 'Tipo de fibra', type: 'text' },
        { key: 'key_map', label: 'Clave cartográfica', type: 'text' },
      ],
      evaluadores: [
        { key: 'dni', label: 'DNI', type: 'text', required: true },
        { key: 'nombres', label: 'Nombres', type: 'text' },
        { key: 'apellidos', label: 'Apellidos', type: 'text' },
        { key: 'codigo', label: 'Código interno', type: 'text' },
        { key: 'zona', label: 'Zona', type: 'text' },
        { key: 'celular', label: 'Celular', type: 'text' },
        { key: 'inicio_labores', label: 'Inicio de labores', type: 'date' },
        { key: 'nacimiento', label: 'Fecha de nacimiento', type: 'date' },
        { key: 'activo', label: 'Evaluador activo', type: 'toggle' },
        { key: 'en_maestro', label: 'Disponible en maestro', type: 'toggle' },
      ],
      campanias: [
        { key: 'codigo', label: 'Código de campaña', type: 'text', required: true },
        { key: 'fecha_inicio', label: 'Fecha de inicio', type: 'date' },
        { key: 'fecha_fin', label: 'Fecha de cierre', type: 'date' },
        { key: 'origen_fechas', label: 'Origen de fechas', type: 'text', required: true },
      ],
      variedades: [{ key: 'nombre', label: 'Nombre de la variedad', type: 'text', required: true }],
      turnos: [{ key: 'codigo', label: 'Código del turno', type: 'text', required: true }],
      muestreo: [
        { key: 'lote_id', label: 'Lote', type: 'select', options: 'lotes', required: true },
        {
          key: 'evaluacion',
          label: 'Tipo de evaluación',
          type: 'select',
          options: 'evaluaciones',
          required: true,
        },
        { key: 'cortina', label: 'Cortina', type: 'number', min: 1 },
        { key: 'hilera', label: 'Hilera', type: 'number', min: 1 },
        { key: 'planta', label: 'Planta', type: 'number', min: 1 },
        { key: 'muestras', label: 'Muestras requeridas', type: 'number', min: 1, required: true },
      ],
    };
    return definitions[resource];
  }

  optionsFor(field: MasterField): FieldOption[] {
    if (field.options === 'evaluaciones') {
      return [
        { value: 'estadios', label: 'Conteo de estadios' },
        { value: 'flores', label: 'Conteo de flores' },
        { value: 'baya', label: 'Desarrollo de fruto' },
        { value: 'pesos', label: 'Peso de baya' },
        { value: 'brotes', label: 'Conteo de brotes' },
        { value: 'ramas', label: 'Conteo de ramas' },
      ];
    }
    return field.options ? (this.referenceOptions()[field.options] ?? []) : [];
  }

  idFor(resource: MasterResource, row: Record<string, unknown>): number {
    const key =
      resource === 'empresas'
        ? 'empresa_id'
        : resource === 'fundos'
          ? 'fundo_id'
          : resource === 'modulos'
            ? 'modulo_id'
            : resource === 'lotes'
              ? 'lote_id'
              : resource === 'evaluadores'
                ? 'evaluador_id'
                : resource === 'campanias'
                  ? 'campania_id'
                  : resource === 'variedades'
                    ? 'variedad_id'
                    : resource === 'turnos'
                      ? 'turno_id'
                      : 'muestra_id';
    const id = Number(row[key]);
    return Number.isFinite(id) && id > 0 ? id : 0;
  }

  private editableValues(
    resource: MasterResource,
    row: Record<string, unknown>,
  ): Record<string, unknown> {
    const result: Record<string, unknown> = {};
    for (const field of this.fieldsFor(resource)) {
      if (row[field.key] !== undefined) result[field.key] = row[field.key];
    }
    return result;
  }

  private configureEditor(values: Record<string, unknown>): void {
    this.masterForm.reset({
      activo: true,
      en_maestro: true,
      origen_fechas: 'panel',
      comentario: '',
    });
    for (const control of Object.values(this.masterForm.controls)) {
      control.clearValidators();
      control.updateValueAndValidity({ emitEvent: false });
    }
    for (const field of this.activeFields()) {
      const control = this.masterForm.get(field.key);
      if (!control) continue;
      const validators = [];
      if (field.required) validators.push(Validators.required);
      if (field.min !== undefined) validators.push(Validators.min(field.min));
      control.setValidators(validators);
      if (Object.prototype.hasOwnProperty.call(values, field.key)) {
        control.setValue(values[field.key] as never);
      }
      control.updateValueAndValidity({ emitEvent: false });
    }
    this.masterForm.controls.comentario.setValue('');
  }

  loadReferenceOptions(): void {
    const resources = [
      ...new Set(
        this.activeFields()
          .filter((f) => f.type === 'select' && f.options !== 'evaluaciones')
          .map((f) => f.options as MasterResource),
      ),
    ];
    this.referenceError.set(false);
    for (const resource of resources) {
      if (this.referencesRequested.has(resource)) continue;
      this.referencesRequested.add(resource);
      this.pendingReferences++;
      this.referenceLoading.set(true);
      this.api
        .listMaster(resource, { page: 1, page_size: 500 })
        .pipe(
          expand((page) =>
            page.meta.page < page.meta.pages
              ? this.api.listMaster(resource, { page: page.meta.page + 1, page_size: 500 })
              : EMPTY,
          ),
          reduce((items, page) => [...items, ...page.items], [] as Record<string, unknown>[]),
          takeUntilDestroyed(this.destroyRef),
        )
        .subscribe({
          next: (rows) => {
            this.referenceOptions.update((current) => ({
              ...current,
              [resource]: rows.map((row) => ({
                value: this.idFor(resource, row),
                label: this.optionLabel(resource, row),
              })),
            }));
            this.pendingReferences--;
            this.referenceLoading.set(this.pendingReferences > 0);
          },
          error: () => {
            this.referencesRequested.delete(resource);
            this.referenceError.set(true);
            this.pendingReferences--;
            this.referenceLoading.set(this.pendingReferences > 0);
          },
        });
    }
  }

  private optionLabel(resource: MasterResource, row: Record<string, unknown>): string {
    if (resource === 'empresas') return String(row['nombre'] ?? 'Empresa');
    if (resource === 'fundos') return `${row['empresa'] ?? ''} · ${row['codigo'] ?? ''}`;
    if (resource === 'modulos') return `${row['fundo'] ?? ''} · ${row['codigo'] ?? ''}`;
    if (resource === 'lotes')
      return `${row['fundo'] ?? ''} · ${row['modulo'] ?? ''} · ${row['codigo'] ?? ''}`;
    if (resource === 'variedades') return String(row['nombre'] ?? 'Variedad');
    return String(row['codigo'] ?? 'Turno');
  }

  private load(page = 1, pageSize = this.response()?.meta.page_size ?? 25): void {
    this.listRequest?.unsubscribe();
    this.loading.set(true);
    this.errorMessage.set(null);
    const resource = this.selectedResource();
    const query = { page, page_size: pageSize, search: this.appliedSearch || undefined };
    const key = JSON.stringify([resource, query]);
    const cached = this.cache.get(key);
    this.listRequest = (
      cached && cached.expires > Date.now()
        ? of(cached.value)
        : this.api.listMaster(resource, query)
    )
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (response) => {
          this.cache.set(key, {
            value: response,
            expires: cached && cached.expires > Date.now() ? cached.expires : Date.now() + 600_000,
          });
          if (this.cache.size > 30) this.cache.delete(this.cache.keys().next().value!);
          this.response.set(response);
          if (!this.appliedSearch)
            this.counts.update((counts) => ({ ...counts, [resource]: response.meta.total }));
          this.loading.set(false);
        },
        error: (error: unknown) => {
          this.loading.set(false);
          this.errorMessage.set(this.messageFor(error));
        },
      });
  }

  private messageFor(
    error: unknown,
    fallback = 'No se pudo consultar el maestro seleccionado.',
  ): string {
    if (error instanceof HttpErrorResponse && typeof error.error?.detail === 'string') {
      return error.error.detail;
    }
    return fallback;
  }
}
