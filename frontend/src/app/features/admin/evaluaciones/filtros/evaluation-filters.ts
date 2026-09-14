import { DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormBuilder } from '@angular/forms';
import { forkJoin } from 'rxjs';
import type { EvaluationQuery } from '../../../../core/api/models';
import { EvaluationData } from '../datos/evaluation-data.service';
interface FilterOption {
  id: number;
  label: string;
  empresaId?: number;
  fundoId?: number;
  moduloId?: number;
}

type RemovableFilter =
  | 'search'
  | 'desde'
  | 'hasta'
  | 'empresa_id'
  | 'fundo_id'
  | 'modulo_id'
  | 'lote_id'
  | 'evaluador_id'
  | 'sort_by'
  | 'sort_dir';

interface AppliedFilter {
  key: RemovableFilter;
  label: string;
  value: string;
}

import type { EvaluationWorkspace } from '../evaluation-workspace.service';
type Host = Pick<
  EvaluationWorkspace,
  | 'formatDate'
  | 'applyFilters'
  | 'activeFamily'
  | 'grain'
  | 'piso'
  | 'estado'
  | 'weightMin'
  | 'weightMax'
  | 'snapshot'
  | 'metric'
>;
export class EvaluationFilters {
  constructor(private readonly getHost: () => Host) {}
  private get host(): Host {
    return this.getHost();
  }
  private readonly formBuilder = inject(FormBuilder);
  private readonly data = inject(EvaluationData);
  private readonly destroyRef = inject(DestroyRef);
  readonly filters = this.formBuilder.nonNullable.group({
    search: '',
    module_key: '',
    desde: '',
    hasta: '',
    empresa_id: 0,
    fundo_id: 0,
    modulo_id: 0,
    lote_id: 0,
    evaluador_id: 0,
    sort_by: ['captured_at' as EvaluationQuery['sort_by']],
    sort_dir: ['desc' as EvaluationQuery['sort_dir']],
  });
  readonly appliedValues = signal(this.filters.getRawValue());
  readonly empresas = signal<FilterOption[]>([]);
  readonly fundos = signal<FilterOption[]>([]);
  readonly modulos = signal<FilterOption[]>([]);
  readonly lotes = signal<FilterOption[]>([]);
  readonly evaluadores = signal<FilterOption[]>([]);
  readonly filtersExpanded = signal(false);
  filteredFundos(): FilterOption[] {
    const empresaId = this.filters.controls.empresa_id.value;
    return empresaId ? this.fundos().filter((item) => item.empresaId === empresaId) : this.fundos();
  }
  filteredModulos(): FilterOption[] {
    const fundoId = this.filters.controls.fundo_id.value;
    return fundoId ? this.modulos().filter((item) => item.fundoId === fundoId) : this.modulos();
  }
  filteredLotes(): FilterOption[] {
    const moduloId = this.filters.controls.modulo_id.value;
    return moduloId ? this.lotes().filter((item) => item.moduloId === moduloId) : this.lotes();
  }
  resetBelow(level: 'empresa' | 'fundo' | 'modulo'): void {
    if (level === 'empresa') this.filters.patchValue({ fundo_id: 0, modulo_id: 0, lote_id: 0 });
    if (level === 'fundo') this.filters.patchValue({ modulo_id: 0, lote_id: 0 });
    if (level === 'modulo') this.filters.patchValue({ lote_id: 0 });
  }
  readonly filterCatalogLoading = signal(false);
  readonly filterCatalogError = signal(false);
  private filterCatalogLoaded = false;
  retryFilterCatalog(): void {
    this.loadFilterOptions();
  }
  toggleFilters(): void {
    this.filtersExpanded.update((expanded) => !expanded);
    if (this.filtersExpanded()) this.loadFilterOptions();
  }
  activeFilterCount(): number {
    const value = this.appliedValues();
    return [
      value.search,
      value.module_key,
      value.desde,
      value.hasta,
      value.empresa_id,
      value.fundo_id,
      value.modulo_id,
      value.lote_id,
      value.evaluador_id,
      value.sort_by !== 'captured_at',
      value.sort_dir !== 'desc',
    ].filter(Boolean).length;
  }
  appliedFilters(): AppliedFilter[] {
    const value = this.appliedValues();
    const chips: AppliedFilter[] = [];
    const add = (key: RemovableFilter, label: string, display: string | undefined) => {
      if (display) chips.push({ key, label, value: display });
    };
    add('search', 'Búsqueda', value.search || undefined);
    add('desde', 'Desde', value.desde ? this.host.formatDate(value.desde) : undefined);
    add('hasta', 'Hasta', value.hasta ? this.host.formatDate(value.hasta) : undefined);
    add('empresa_id', 'Empresa', this.optionLabel(this.empresas(), value.empresa_id));
    add('fundo_id', 'Fundo', this.optionLabel(this.fundos(), value.fundo_id));
    add('modulo_id', 'Módulo', this.optionLabel(this.modulos(), value.modulo_id));
    add('lote_id', 'Lote', this.optionLabel(this.lotes(), value.lote_id));
    add('evaluador_id', 'Evaluador', this.optionLabel(this.evaluadores(), value.evaluador_id));
    if (value.sort_by !== 'fecha') {
      add(
        'sort_by',
        'Orden',
        (
          {
            fecha: 'Fecha',
            empresa: 'Empresa',
            fundo: 'Fundo',
            modulo: 'Módulo',
            lote: 'Lote',
            evaluador: 'Evaluador',
          } as Record<string, string>
        )[value.sort_by ?? ''],
      );
    }
    if (value.sort_dir !== 'desc') add('sort_dir', 'Dirección', 'Más antiguas');
    return chips;
  }
  removeFilter(key: RemovableFilter): void {
    if (key === 'search' || key === 'desde' || key === 'hasta')
      this.filters.controls[key].setValue('');
    if (key === 'empresa_id') {
      this.filters.patchValue({ empresa_id: 0, fundo_id: 0, modulo_id: 0, lote_id: 0 });
    }
    if (key === 'fundo_id') this.filters.patchValue({ fundo_id: 0, modulo_id: 0, lote_id: 0 });
    if (key === 'modulo_id') this.filters.patchValue({ modulo_id: 0, lote_id: 0 });
    if (key === 'lote_id' || key === 'evaluador_id') this.filters.controls[key].setValue(0);
    if (key === 'sort_by') this.filters.controls.sort_by.setValue('captured_at');
    if (key === 'sort_dir') this.filters.controls.sort_dir.setValue('desc');
    this.host.applyFilters();
  }
  clearFilters(): void {
    this.filters.reset({
      module_key: this.host.activeFamily(),
      sort_by: 'captured_at',
      sort_dir: 'desc',
    });
    this.host.grain.set('');
    this.host.piso.set('');
    this.host.estado.set('');
    this.host.weightMin.set('');
    this.host.weightMax.set('');
    this.host.snapshot.set(true);
    this.host.metric.set('n_flores');
    this.filtersExpanded.set(false);
    this.host.applyFilters();
  }
  private loadFilterOptions(): void {
    if (this.filterCatalogLoaded || this.filterCatalogLoading()) return;
    this.filterCatalogLoading.set(true);
    this.filterCatalogError.set(false);
    forkJoin({
      empresas: this.data.loadCatalog('empresas'),
      fundos: this.data.loadCatalog('fundos'),
      modulos: this.data.loadCatalog('modulos'),
      lotes: this.data.loadCatalog('lotes'),
      evaluadores: this.data.loadCatalog('evaluadores'),
    })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (catalogs) => {
          this.filterCatalogLoaded = true;
          this.filterCatalogLoading.set(false);
          this.empresas.set(
            catalogs.empresas.items.map((row) => ({
              id: Number(row['empresa_id']),
              label: String(row['nombre'] ?? row['empresa_id']),
            })),
          );
          this.fundos.set(
            catalogs.fundos.items.map((row) => ({
              id: Number(row['fundo_id']),
              label: `${row['empresa'] ?? ''} · ${row['codigo'] ?? row['fundo_id']}`,
              empresaId: Number(row['empresa_id']),
            })),
          );
          this.modulos.set(
            catalogs.modulos.items.map((row) => ({
              id: Number(row['modulo_id']),
              label: `${row['fundo'] ?? ''} · ${row['codigo'] ?? row['modulo_id']}`,
              fundoId: Number(row['fundo_id']),
            })),
          );
          this.lotes.set(
            catalogs.lotes.items.map((row) => ({
              id: Number(row['lote_id']),
              label: `${row['fundo'] ?? ''} · ${row['modulo'] ?? ''} · ${row['codigo'] ?? row['lote_id']}`,
              moduloId: Number(row['modulo_id']),
            })),
          );
          this.evaluadores.set(
            catalogs.evaluadores.items.map((row) => ({
              id: Number(row['evaluador_id']),
              label:
                `${row['dni'] ?? ''} · ${row['nombres'] ?? ''} ${row['apellidos'] ?? ''}`.trim(),
            })),
          );
        },
        error: () => {
          this.filterCatalogLoading.set(false);
          this.filterCatalogError.set(true);
        },
      });
  }
  private optionLabel(options: FilterOption[], id: number): string | undefined {
    return id ? (options.find((item) => item.id === id)?.label ?? `ID ${id}`) : undefined;
  }
}
