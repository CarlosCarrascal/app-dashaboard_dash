import { computed, DestroyRef, inject, Injectable, OnInit, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

import type { PageEvent } from '@angular/material/paginator';
import { ActivatedRoute, Router } from '@angular/router';
import {
  ColumnDef,
  createAngularTable,
  getCoreRowModel,
  VisibilityState,
} from '@tanstack/angular-table';
import {
  catchError,
  combineLatest,
  concatMap,
  EMPTY,
  firstValueFrom,
  from,
  map,
  of,
  Subscription,
  switchMap,
  timer,
  toArray,
} from 'rxjs';

import {
  AdminEvaluationDetail,
  AdminEvaluationItem,
  AdminEvaluationPage,
  EvaluationQuery,
  ModuleKey,
} from '../../../core/api/models';
import { AuthService } from '../../../core/auth/auth.service';
import { EvaluationDetail } from './detalle/evaluation-detail';
import { FieldAnalytics, palette, stageNames } from './field-analytics';
import { EvaluationFilters } from './filtros/evaluation-filters';

import { EvaluationAnalysis } from './analisis/evaluation-analysis';
import { EvaluationCorrection } from './correccion/evaluation-correction';
import { EvaluationData } from './datos/evaluation-data.service';
import {
  detailEntries,
  formatCapture,
  formatCell,
  formatDate,
  formatMetric,
  grainLabel,
  messageFor,
  numberValue,
  percentage,
} from './evaluation-format';
import {
  columnsFor,
  detailColumnLabel,
  EVALUATION_FAMILIES,
  familyDescription,
  familyLabel,
  familyOrdinal,
} from './familias/evaluation-families';
/** Page-scoped facade: route synchronization and coordination between feature controllers. */
@Injectable()
export class EvaluationWorkspace implements OnInit {
  private readonly detailState: EvaluationDetail = new EvaluationDetail(() => this);
  readonly selected = this.detailState.selected;
  readonly detailLoading = this.detailState.detailLoading;
  readonly observationPage = this.detailState.observationPage;
  readonly observationSize = this.detailState.observationSize;
  readonly observationRows = this.detailState.observationRows;
  readonly observationTotal = this.detailState.observationTotal;
  readonly observationsLoading = this.detailState.observationsLoading;
  readonly observations = this.detailState.observations.bind(this.detailState);
  readonly pagedObservations = this.detailState.pagedObservations.bind(this.detailState);
  readonly loadObservationPage = this.detailState.loadObservationPage.bind(this.detailState);
  readonly selectRecord = this.detailState.selectRecord.bind(this.detailState);
  private readonly filterState: EvaluationFilters = new EvaluationFilters(() => this);
  readonly filters = this.filterState.filters;
  readonly appliedValues = this.filterState.appliedValues;
  readonly empresas = this.filterState.empresas;
  readonly fundos = this.filterState.fundos;
  readonly modulos = this.filterState.modulos;
  readonly lotes = this.filterState.lotes;
  readonly evaluadores = this.filterState.evaluadores;
  readonly filtersExpanded = this.filterState.filtersExpanded;
  readonly filteredFundos = this.filterState.filteredFundos.bind(this.filterState);
  readonly filteredModulos = this.filterState.filteredModulos.bind(this.filterState);
  readonly filteredLotes = this.filterState.filteredLotes.bind(this.filterState);
  readonly resetBelow = this.filterState.resetBelow.bind(this.filterState);
  readonly filterCatalogLoading = this.filterState.filterCatalogLoading;
  readonly filterCatalogError = this.filterState.filterCatalogError;
  readonly retryFilterCatalog = this.filterState.retryFilterCatalog.bind(this.filterState);
  readonly toggleFilters = this.filterState.toggleFilters.bind(this.filterState);
  readonly activeFilterCount = this.filterState.activeFilterCount.bind(this.filterState);
  readonly appliedFilters = this.filterState.appliedFilters.bind(this.filterState);
  readonly removeFilter = this.filterState.removeFilter.bind(this.filterState);
  readonly clearFilters = this.filterState.clearFilters.bind(this.filterState);
  private readonly data = inject(EvaluationData);
  readonly modules = EVALUATION_FAMILIES;
  private readonly correction: EvaluationCorrection = new EvaluationCorrection(() => this);
  private readonly analysis: EvaluationAnalysis = new EvaluationAnalysis(() => this);
  readonly formatMetric = formatMetric;
  readonly formatCell = formatCell;
  readonly percentage = percentage;
  readonly grainLabel = grainLabel;
  readonly formatDate = formatDate;
  readonly formatCapture = formatCapture;
  readonly numberValue = numberValue;
  readonly messageFor = messageFor;
  readonly detailEntries = detailEntries;
  readonly detailColumnLabel = detailColumnLabel;
  readonly familyLabel = familyLabel;
  readonly familyDescription = familyDescription;
  readonly familyOrdinal = familyOrdinal;
  readonly editing = this.correction.editing;
  readonly saving = this.correction.saving;
  readonly correctionForm = this.correction.correctionForm;
  readonly canCorrect = this.correction.canCorrect.bind(this.correction);
  readonly canCorrectDetail = this.correction.canCorrectDetail.bind(this.correction);
  readonly startCorrection = this.correction.startCorrection.bind(this.correction);
  readonly cancelCorrection = this.correction.cancelCorrection.bind(this.correction);
  readonly submitCorrection = this.correction.submitCorrection.bind(this.correction);
  readonly sampleEntries = this.analysis.sampleEntries;
  readonly context = this.analysis.context;
  readonly mainChart = this.analysis.mainChart;
  readonly histogram = this.analysis.histogram;
  readonly evolution = this.analysis.evolution;
  readonly flowerScatter = this.analysis.flowerScatter;
  readonly metricOptions = this.analysis.metricOptions;
  readonly chartTitle = this.analysis.chartTitle;
  readonly unit = this.analysis.unit;
  readonly categoryEntries = this.analysis.categoryEntries.bind(this.analysis);
  readonly stagePercent = this.analysis.stagePercent.bind(this.analysis);
  readonly categoryTotal = this.analysis.categoryTotal.bind(this.analysis);
  readonly availabilityEntries = this.analysis.availabilityEntries.bind(this.analysis);
  canEditEvaluations(): boolean {
    return this.auth.hasPermission('admin:evaluaciones:corregir');
  }
  refreshAfterCorrection(): void {
    this.invalidateQueryCache();
    this.load(this.meta().page);
  }

  private readonly auth = inject(AuthService);

  private readonly route = inject(ActivatedRoute);

  private readonly router = inject(Router);

  private readonly destroyRef = inject(DestroyRef);

  readonly activeFamily = signal<ModuleKey | ''>('');

  readonly activeView = signal<'data' | 'import'>('data');

  readonly canImport = computed(() => this.auth.hasPermission('admin:evaluaciones:cargar'));

  readonly rows = signal<AdminEvaluationItem[]>([]);

  readonly meta = signal<AdminEvaluationPage['meta']>({
    page: 1,
    page_size: 50,
    total: 0,
    pages: 0,
  });

  readonly loading = signal(false);

  readonly successMessage = signal<string | null>(null);

  readonly errorMessage = signal<string | null>(null);

  readonly selectPanelWidth = 280;

  readonly columnDefs = signal<ColumnDef<AdminEvaluationItem>[]>(columnsFor(''));

  readonly columnVisibility = signal<VisibilityState>({ variedad: false });

  readonly table = createAngularTable(() => ({
    data: this.rows(),
    columns: this.columnDefs(),
    getCoreRowModel: getCoreRowModel(),
    getRowId: (row) => row.id,
    manualPagination: true,
    manualSorting: true,
    columnResizeMode: 'onChange',
    defaultColumn: { size: 140, minSize: 80 },
    rowCount: this.meta().total,
    state: {
      columnVisibility: this.columnVisibility(),
      pagination: { pageIndex: this.meta().page - 1, pageSize: this.meta().page_size },
    },
    onColumnVisibilityChange: (updater) =>
      this.columnVisibility.update((current) =>
        typeof updater === 'function' ? updater(current) : updater,
      ),
  }));

  readonly analytics = signal<FieldAnalytics | null>(null);

  readonly workspaceView = signal<'analisis' | 'registros'>('analisis');

  readonly metric = signal('n_flores');

  readonly chartMode = signal('mediciones');

  readonly focusedLot = signal('');

  readonly contextOpen = signal(false);

  readonly columnMenu = signal(false);

  readonly grain = signal('');

  readonly piso = signal('');

  readonly estado = signal('');

  readonly weightMin = signal('');

  readonly weightMax = signal('');

  readonly exporting = signal(false);

  readonly snapshot = signal(true);

  readonly stageNames = stageNames;

  readonly palette = palette;

  readonly title = computed(
    () => this.modules.find((m) => m.key === this.activeFamily())?.label ?? 'Evaluaciones',
  );

  currentQuery: EvaluationQuery & { grano?: string; piso?: string; estado?: string } = {};

  selectLot(key: string) {
    this.focusedLot.set('');
    this.contextData.set(null);
    this.contextRequest?.unsubscribe();
    if (key.startsWith('record:')) {
      this.selectRecord({
        module_key: this.activeFamily() as ModuleKey,
        source_id: Number(key.slice(7)),
        source_table: 'ev_evaluacion',
      });
      return;
    }
    if (this.analytics()?.lots.some((l) => l.key === key)) {
      this.focusedLot.set(key);
      this.contextOpen.set(true);
      const params = {
        ...this.currentQuery,
        lote_id: Number(key),
        desde: this.analytics()?.trend_desde,
        hasta: this.analytics()?.hasta,
        snapshot: this.snapshot(),
        metric: this.metric(),
      };
      this.contextRequest = this.data
        .context(params)
        .pipe(takeUntilDestroyed(this.destroyRef))
        .subscribe({
          next: (d) => this.contextData.set(d),
          error: () => this.errorMessage.set('No se pudo cargar la evolución del lote.'),
        });
    }
  }

  openLotRecords() {
    const lot = this.context()?.lote_id;
    if (lot) this.filters.controls.lote_id.setValue(lot);
    this.workspaceView.set('registros');
    this.applyFilters();
  }

  setView(view: 'analisis' | 'registros') {
    this.workspaceView.set(view);
    void this.router.navigate([], {
      relativeTo: this.route,
      queryParams: { vista: view },
      queryParamsHandling: 'merge',
    });
  }

  async exportFiltered() {
    this.exporting.set(true);
    try {
      const blob = await firstValueFrom(this.data.export(this.currentQuery));
      const url = URL.createObjectURL(blob),
        a = document.createElement('a');
      a.href = url;
      a.download = `${this.activeFamily()}-${this.currentQuery.hasta ?? 'consulta'}.csv`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch {
      this.errorMessage.set('No se pudo exportar la consulta completa.');
    } finally {
      this.exporting.set(false);
    }
  }

  isNumeric(value: unknown) {
    return typeof value === 'number';
  }

  adjustColumn(id: string, delta: number) {
    const column = this.table.getColumn(id);
    if (column)
      this.table.setColumnSizing((s) => ({ ...s, [id]: Math.max(80, column.getSize() + delta) }));
  }

  resizeColumn(event: MouseEvent | TouchEvent, id: string) {
    const header = this.table.getFlatHeaders().find((h) => h.column.id === id);
    header?.getResizeHandler()(event);
  }

  readonly summaryLoading = signal(false);

  private listRequest?: Subscription;

  readonly trendLoading = signal(false);

  readonly trendError = signal(false);

  private historyRequest?: Subscription;

  private historyKey = '';

  private displayedAnalysisKey = '';

  private pendingQueryKey = '';

  private routeQueryKey = '';

  private lastAnalyticalQuery: Record<string, unknown> = {};

  private warmupStarted = false;

  private contextRequest?: Subscription;

  readonly contextData = signal<FieldAnalytics | null>(null);

  sortColumn(id: string): void {
    if (!this.sortableColumn(id)) return;
    const previous = this.filters.getRawValue();
    this.filters.patchValue({
      sort_by: id as EvaluationQuery['sort_by'],
      sort_dir: previous.sort_by === id && previous.sort_dir === 'desc' ? 'asc' : 'desc',
    });
    this.load(1);
  }

  sortableColumn(id: string): boolean {
    return ['fecha', 'lote', 'modulo', 'fundo', 'evaluador', 'empresa', 'captured_at'].includes(id);
  }

  ngOnInit(): void {
    combineLatest([this.route.paramMap, this.route.queryParamMap])
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(([path, params]) => {
        const candidate = path.get('familia') || 'estadios';
        if (!this.modules.some((m) => m.key === candidate)) {
          void this.router.navigate(['/admin/evaluaciones/estadios'], { replaceUrl: true });
          return;
        }
        const family = candidate as ModuleKey;
        this.activeFamily.set(family);
        localStorage.setItem('aquanqa.lastEvaluation', family);
        this.workspaceView.set(params.get('vista') === 'registros' ? 'registros' : 'analisis');
        this.activeView.set(
          params.get('vista') === 'importar' && this.canImport() ? 'import' : 'data',
        );
        const routeKey = JSON.stringify([
          family,
          params.keys
            .filter((k) => k !== 'vista')
            .sort()
            .map((k) => [k, params.getAll(k)]),
        ]);
        if (routeKey === this.routeQueryKey && this.activeView() === 'data') {
          if (this.analytics())
            this.loadTrend(this.analytics()!, this.lastAnalyticalQuery, this.displayedAnalysisKey);
          this.prefetchNextPage();
          return;
        }
        this.routeQueryKey = routeKey;
        this.snapshot.set(params.get('periodo') !== 'rango');
        this.grain.set(params.get('grano') || '');
        this.piso.set(params.get('piso') || '');
        this.estado.set(params.get('estado') || '');
        this.metric.set(params.get('metrica') || 'n_flores');
        this.weightMin.set(params.get('peso_min') || '');
        this.weightMax.set(params.get('peso_max') || '');
        this.filters.patchValue({
          module_key: family,
          search: params.get('search') || '',
          desde: params.get('desde') || '',
          hasta: params.get('hasta') || '',
          empresa_id: Number(params.get('empresa_id')) || 0,
          fundo_id: Number(params.get('fundo_id')) || 0,
          modulo_id: Number(params.get('modulo_id')) || 0,
          lote_id: Number(params.get('lote_id')) || 0,
          evaluador_id: Number(params.get('evaluador_id')) || 0,
        });
        this.filters.patchValue({
          sort_by: ([
            'fecha',
            'captured_at',
            'lote',
            'modulo',
            'fundo',
            'empresa',
            'evaluador',
          ].includes(params.get('sort_by') || '')
            ? params.get('sort_by')
            : 'fecha') as EvaluationQuery['sort_by'],
          sort_dir: params.get('sort_dir') === 'asc' ? 'asc' : 'desc',
        });
        this.columnDefs.set(columnsFor(family));
        this.columnVisibility.set({
          variedad: false,
          ...(window.innerWidth < 768 ? { modulo: false, fundo: false, evaluador: false } : {}),
        });
        this.focusedLot.set('');
        if (this.activeView() === 'data') this.load(1);
      });
  }

  selectFamily(moduleKey: ModuleKey | '') {
    void this.router.navigate(['/admin/evaluaciones', moduleKey || 'estadios']);
  }

  openImport(): void {
    void this.router.navigate([], {
      relativeTo: this.route,
      queryParams: { vista: 'importar' },
      queryParamsHandling: 'merge',
    });
  }

  closeImport(): void {
    void this.router.navigate([], {
      relativeTo: this.route,
      queryParams: { vista: null },
      queryParamsHandling: 'merge',
    });
  }

  numberValuePublic(value: unknown) {
    return Number(value) || 0;
  }

  isNarrow() {
    return window.innerWidth < 1280;
  }

  refreshData(): void {
    this.invalidateQueryCache();
    this.filters.patchValue(this.appliedValues());
    this.load(this.meta().page);
  }

  private invalidateQueryCache(): void {
    this.data.invalidate();
    this.pendingQueryKey = '';
    this.historyRequest?.unsubscribe();
    this.historyKey = '';
  }

  applyFilters(): void {
    this.invalidateQueryCache();
    const r = this.filters.getRawValue();
    const queryParams = {
      vista: this.workspaceView(),
      periodo: this.snapshot() ? 'ultima' : 'rango',
      desde: r.desde || null,
      hasta: r.hasta || null,
      search: r.search || null,
      empresa_id: r.empresa_id || null,
      fundo_id: r.fundo_id || null,
      modulo_id: r.modulo_id || null,
      lote_id: r.lote_id || null,
      evaluador_id: r.evaluador_id || null,
      grano: this.grain() || null,
      piso: this.piso() || null,
      estado: this.estado() || null,
      metrica: this.metric(),
      peso_min: this.weightMin() || null,
      peso_max: this.weightMax() || null,
      sort_by: r.sort_by,
      sort_dir: r.sort_dir,
    };
    const tree = this.router.createUrlTree([], { relativeTo: this.route, queryParams });
    if (this.router.serializeUrl(tree) === this.router.url) this.load(1);
    else void this.router.navigateByUrl(tree);
  }

  onPage(event: PageEvent): void {
    this.listRequest?.unsubscribe();
    this.loading.set(true);
    this.errorMessage.set(null);
    const query = { ...this.currentQuery, page: event.pageIndex + 1, page_size: event.pageSize };
    this.listRequest = this.data.requestPage(query).subscribe({
      next: (result) => {
        this.rows.set(result.items);
        this.meta.set(result.meta);
        this.loading.set(false);
        this.prefetchNextPage();
      },
      error: (error: unknown) => {
        this.loading.set(false);
        this.errorMessage.set(this.messageFor(error, 'No se pudo cargar la página.'));
      },
    });
  }

  focusOnLot(detail: AdminEvaluationDetail): void {
    const loteId = this.numberValue(detail.lote_id);
    if (!loteId) return;
    this.filters.patchValue({ empresa_id: 0, fundo_id: 0, modulo_id: 0, lote_id: loteId });
    this.selected.set(null);
    this.editing.set(false);
    this.snapshot.set(false);
    this.filters.patchValue({ desde: '', hasta: '' });
    this.applyFilters();
  }

  focusOnEvaluator(detail: AdminEvaluationDetail): void {
    const evaluadorId = this.numberValue(detail.evaluador_id);
    if (!evaluadorId) return;
    this.filters.controls.evaluador_id.setValue(evaluadorId);
    this.selected.set(null);
    this.editing.set(false);
    this.snapshot.set(false);
    this.filters.patchValue({ desde: '', hasta: '' });
    this.applyFilters();
  }

  private load(page = 1, pageSize = this.meta().page_size): void {
    const raw = this.filters.getRawValue();
    if (raw.desde && raw.hasta && raw.desde > raw.hasta) {
      this.errorMessage.set('La fecha inicial debe ser anterior a la final.');
      return;
    }
    const query: EvaluationQuery = {
      module_key: this.activeFamily() as ModuleKey,
      search: raw.search || undefined,
      desde: raw.desde || undefined,
      hasta: raw.hasta || undefined,
      empresa_id: raw.empresa_id || undefined,
      fundo_id: raw.fundo_id || undefined,
      modulo_id: raw.modulo_id || undefined,
      lote_id: raw.lote_id || undefined,
      evaluador_id: raw.evaluador_id || undefined,
      sort_by: raw.sort_by,
      sort_dir: raw.sort_dir,
    };
    const analytical = {
      ...query,
      snapshot: this.snapshot(),
      snapshot_series: this.snapshot(),
      series_only: true,
      include_trend: !this.snapshot(),
      metric: this.metric(),
      grano: this.grain() || undefined,
      piso: this.piso() || undefined,
      estado: this.estado() || undefined,
      weight_min: this.weightMin() || undefined,
      weight_max: this.weightMax() || undefined,
    };
    this.lastAnalyticalQuery = analytical;
    const key = JSON.stringify({ ...analytical, sort_by: undefined, sort_dir: undefined });
    const pendingKey = JSON.stringify([key, query.sort_by, query.sort_dir, page, pageSize]);
    if (this.loading() && this.pendingQueryKey === pendingKey && !this.listRequest?.closed) {
      if (this.analytics()) this.loadTrend(this.analytics()!, analytical, key);
      return;
    }
    const retainedAnalysis = this.displayedAnalysisKey === key ? this.analytics() : null;
    this.displayedAnalysisKey = key;
    this.pendingQueryKey = pendingKey;
    this.listRequest?.unsubscribe();
    this.detailState.cancelPending();
    this.selected.set(null);
    if (!retainedAnalysis) this.rows.set([]);
    this.loading.set(true);
    this.summaryLoading.set(true);
    this.errorMessage.set(null);
    this.contextData.set(null);
    this.contextRequest?.unsubscribe();
    if (!retainedAnalysis) this.analytics.set(null);
    this.appliedValues.set(raw);
    const request = this.data.fetchAnalysis(analytical, key);
    this.listRequest = request
      .pipe(
        switchMap((data) => {
          this.analytics.set(data);
          this.summaryLoading.set(false);
          this.loadTrend(data, analytical, key);
          if (data.trend.length || !data.summary.evaluations) this.warmModules(analytical);
          this.currentQuery = {
            ...query,
            desde: data.desde || undefined,
            hasta: data.hasta || undefined,
            grano: data.grano || undefined,
            piso: this.piso() || undefined,
            estado: this.estado() || undefined,
          };
          // Analysis can render as soon as its aggregates arrive. The table loads in
          // the background once and is reused when switching views or returning to a page.
          const pageQuery = { ...this.currentQuery, page, page_size: pageSize };
          return this.data.requestPage(pageQuery);
        }),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe({
        next: (result) => {
          this.rows.set(result.items);
          this.meta.set(result.meta);
          this.loading.set(false);
          this.prefetchNextPage();
        },
        error: (error: unknown) => {
          this.loading.set(false);
          this.summaryLoading.set(false);
          this.errorMessage.set(this.messageFor(error, 'No se pudo cargar el análisis.'));
        },
      });
  }

  private warmModules(query: Record<string, unknown>): void {
    if (
      this.warmupStarted ||
      !query['snapshot'] ||
      [
        'desde',
        'hasta',
        'search',
        'empresa_id',
        'fundo_id',
        'modulo_id',
        'lote_id',
        'evaluador_id',
        'grano',
        'piso',
        'estado',
        'weight_min',
        'weight_max',
      ].some((k) => query[k])
    )
      return;
    this.warmupStarted = true;
    const generation = this.data.cacheGeneration;
    timer(1500)
      .pipe(
        switchMap(() => from(this.modules.filter((m) => m.key !== query['module_key']))),
        concatMap((module) => {
          if (generation !== this.data.cacheGeneration) return EMPTY;
          const next = {
            ...query,
            module_key: module.key,
            metric: 'n_flores',
            include_trend: false,
          };
          const key = JSON.stringify({ ...next, sort_by: undefined, sort_dir: undefined });
          return this.data.fetchAnalysis(next, key).pipe(
            // Compact daily quantiles are now bounded reads. Prepare them before
            // navigation, sharing the same pending read with a foreground visit.
            concatMap((data) =>
              data.summary.evaluations && !data.trend.length
                ? this.data.fetchTrend(data, next, key).pipe(
                    map(() => data),
                    catchError(() => of(data)),
                  )
                : of(data),
            ),
            map((data) => ({ module, data })),
            catchError(() => EMPTY),
          );
        }),
        // A slow speculative table must not delay analysis for the next module.
        toArray(),
        concatMap((prepared) => from(prepared)),
        concatMap(({ module, data }) =>
          generation !== this.data.cacheGeneration
            ? EMPTY
            : this.data
                .requestPage({
                  module_key: module.key as ModuleKey,
                  desde: data.desde || undefined,
                  hasta: data.hasta || undefined,
                  grano: data.grano || undefined,
                  sort_by: 'fecha',
                  sort_dir: 'desc',
                  page: 1,
                  page_size: this.meta().page_size,
                })
                .pipe(catchError(() => EMPTY)),
        ),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe();
  }

  private prefetchNextPage(): void {
    if (this.workspaceView() !== 'registros' || this.meta().page >= this.meta().pages) return;
    this.data
      .requestPage({
        ...this.currentQuery,
        page: this.meta().page + 1,
        page_size: this.meta().page_size,
      })
      .subscribe({
        error: () => {
          /* A speculative read never hides the current page. */
        },
      });
  }

  private loadTrend(data: FieldAnalytics, query: Record<string, unknown>, key: string): void {
    if (this.workspaceView() !== 'analisis') return;
    if (data.trend.length || !data.summary.evaluations || !data.snapshot) {
      this.trendLoading.set(false);
      this.trendError.set(false);
      return;
    }
    if (this.historyKey === key && this.historyRequest && !this.historyRequest.closed) return;
    this.historyRequest?.unsubscribe();
    this.historyKey = key;
    this.trendLoading.set(true);
    this.trendError.set(false);
    const generation = this.data.cacheGeneration;
    this.historyRequest = this.data.fetchTrend(data, query, key).subscribe({
      next: () => {
        if (generation !== this.data.cacheGeneration || this.displayedAnalysisKey !== key) return;
        const entry = this.data.cachedAnalysis(key);
        if (entry) this.analytics.set(entry.value);
        this.trendLoading.set(false);
        this.warmModules(query);
      },
      error: () => {
        if (generation === this.data.cacheGeneration && this.displayedAnalysisKey === key) {
          this.trendLoading.set(false);
          this.trendError.set(true);
        }
      },
    });
  }
}
