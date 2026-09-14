import { DatePipe, DecimalPipe, JsonPipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, DestroyRef, computed, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import type { PageEvent } from '@angular/material/paginator';
import { A11yModule } from '@angular/cdk/a11y';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Subscription } from 'rxjs';
import { ApiClient } from '../../../core/api/api-client.service';
import { AuthService } from '../../../core/auth/auth.service';
import {
  AdminQARejectItem,
  AdminQAPage,
  AdminQASummary,
  QAReviewRequest,
} from '../../../core/api/models';
import { AppIconComponent } from '../../../shared/ui/app-icon.component';

@Component({
  selector: 'app-qa',
  standalone: true,
  imports: [AppIconComponent, DecimalPipe, DatePipe, JsonPipe, A11yModule, ReactiveFormsModule],
  templateUrl: './qa.component.html',
  styleUrl: './qa.component.scss',
})
export class QaComponent implements OnInit {
  private readonly destroyRef = inject(DestroyRef);
  private listRequest?: Subscription;
  readonly filtersOpen = signal(false);
  readonly reasonSearch = signal('');
  readonly states = [
    { value: '' as const, label: 'Todas' },
    { value: 'pendiente' as const, label: 'Pendientes' },
    { value: 'corregir' as const, label: 'Por corregir' },
    { value: 'aceptado' as const, label: 'Aceptadas' },
    { value: 'descartado' as const, label: 'Descartadas' },
  ];
  readonly activeState = signal<string>('');
  readonly activeReason = signal('');
  readonly activePriority = signal(false);
  readonly reasons = computed(() =>
    (this.summary()?.motivos ?? []).filter((m) =>
      this.reasonLabel(m.motivo)
        .toLocaleLowerCase()
        .includes(this.reasonSearch().toLocaleLowerCase()),
    ),
  );
  reasonPercent(count: number): number {
    return this.summary()?.total_rechazos ? (count / this.summary()!.total_rechazos) * 100 : 0;
  }
  isCompact(): boolean {
    return window.innerWidth < 1280;
  }
  stateLabel(state: string): string {
    return (
      (
        {
          pendiente: 'Pendiente',
          corregir: 'Por corregir',
          aceptado: 'Aceptada',
          descartado: 'Descartada',
        } as Record<string, string>
      )[state] ?? state
    );
  }
  setState(value: '' | QAReviewRequest['estado'] | 'pendiente'): void {
    this.filters.controls.estado_revision.setValue(value);
    this.applyFilters();
  }
  togglePriority(): void {
    this.filters.controls.excede_umbral.setValue(
      this.filters.controls.excede_umbral.value === 'true' ? '' : 'true',
    );
    this.applyFilters();
  }
  refresh(): void {
    this.api.clearReadCache();
    this.loadSummary();
    this.loadRows(this.page()?.meta.page ?? 1);
  }

  private readonly api = inject(ApiClient);
  private readonly formBuilder = inject(FormBuilder);
  private readonly auth = inject(AuthService);

  readonly filters = this.formBuilder.nonNullable.group({
    search: '',
    motivo: '',
    tabla_origen: '',
    hallazgo: '',
    excede_umbral: ['' as '' | 'true' | 'false'],
    estado_revision: ['' as '' | QAReviewRequest['estado'] | 'pendiente'],
  });
  readonly reviewForm = this.formBuilder.nonNullable.group({
    estado: ['corregir' as QAReviewRequest['estado']],
    comentario: [''],
  });
  readonly summary = signal<AdminQASummary | null>(null);
  readonly page = signal<AdminQAPage | null>(null);
  readonly selected = signal<AdminQARejectItem | null>(null);
  private reviewKey: string | null = null;
  readonly loading = signal(false);
  readonly reviewing = signal(false);
  readonly bulkReviewing = signal(false);
  readonly selectedDuplicateIds = signal<number[]>([]);
  readonly successMessage = signal<string | null>(null);
  readonly errorMessage = signal<string | null>(null);
  readonly canReview = () => this.auth.hasPermission('admin:qa:gestionar');

  ngOnInit(): void {
    this.loadSummary();
    this.loadRows();
  }

  applyFilters(): void {
    this.selected.set(null);
    this.selectedDuplicateIds.set([]);
    this.loadRows(1);
  }

  clearFilters(): void {
    this.filters.reset({
      search: '',
      motivo: '',
      tabla_origen: '',
      hallazgo: '',
      excede_umbral: '',
      estado_revision: '',
    });
    this.reasonSearch.set('');
    this.applyFilters();
  }

  selectForReview(row: AdminQARejectItem): void {
    this.selected.set(row);
    this.reviewKey = crypto.randomUUID();
    this.reviewForm.reset({
      estado: row.estado_revision === 'pendiente' ? 'corregir' : row.estado_revision,
      comentario: row.comentario_revision ?? '',
    });
  }

  canBulkSelect(row: AdminQARejectItem): boolean {
    return (
      this.canReview() &&
      this.auth.hasPermission('admin:evaluaciones:corregir') &&
      row.motivo === 'DUPLICADO_EXACTO' &&
      this.isEvaluation(row)
    );
  }

  duplicateSelected(id: number): boolean {
    return this.selectedDuplicateIds().includes(id);
  }

  toggleDuplicate(row: AdminQARejectItem, checked: boolean): void {
    if (!this.canBulkSelect(row)) return;
    this.selectedDuplicateIds.update((ids) =>
      checked ? [...new Set([...ids, row.rechazo_id])] : ids.filter((id) => id !== row.rechazo_id),
    );
  }

  confirmSelectedDuplicates(): void {
    const ids = this.selectedDuplicateIds();
    if (!ids.length) return;
    this.bulkReviewing.set(true);
    this.errorMessage.set(null);
    this.api
      .confirmQualityDuplicates({
        rechazo_ids: ids,
        comentario: 'Duplicados exactos confirmados desde el panel administrativo.',
        idempotency_key: crypto.randomUUID(),
      })
      .subscribe({
        next: (result) => {
          this.bulkReviewing.set(false);
          this.selectedDuplicateIds.set([]);
          this.successMessage.set(
            `${result.procesados} duplicados confirmados sin reinsertar datos.`,
          );
          this.loadRows(this.page()?.meta.page ?? 1);
        },
        error: (error: unknown) => {
          this.bulkReviewing.set(false);
          this.errorMessage.set(this.messageFor(error));
        },
      });
  }

  confirmSingleDuplicate(row: AdminQARejectItem): void {
    if (!this.canBulkSelect(row)) return;
    this.bulkReviewing.set(true);
    this.errorMessage.set(null);
    this.api
      .confirmQualityDuplicates({
        rechazo_ids: [row.rechazo_id],
        comentario:
          this.reviewForm.controls.comentario.value ||
          'Duplicado exacto confirmado desde el detalle de calidad.',
        idempotency_key: crypto.randomUUID(),
      })
      .subscribe({
        next: (result) => {
          this.bulkReviewing.set(false);
          this.selected.set(null);
          this.successMessage.set(
            `${result.procesados} duplicado confirmado sin reinsertar datos.`,
          );
          this.loadSummary();
          this.loadRows(this.page()?.meta.page ?? 1);
        },
        error: (error: unknown) => {
          this.bulkReviewing.set(false);
          this.errorMessage.set(this.messageFor(error));
        },
      });
  }

  cancelReview(): void {
    this.selected.set(null);
    this.reviewKey = null;
  }

  submitReview(): void {
    const row = this.selected();
    if (!row || !this.canReview()) {
      return;
    }
    this.reviewing.set(true);
    this.errorMessage.set(null);
    const payload: QAReviewRequest = {
      ...this.reviewForm.getRawValue(),
      idempotency_key: this.reviewKey ?? crypto.randomUUID(),
    };
    this.api.reviewQuality(row.rechazo_id, payload).subscribe({
      next: () => {
        this.reviewing.set(false);
        this.selected.set(null);
        this.reviewKey = null;
        this.successMessage.set(
          'Decisión guardada. El criterio y la persona responsable quedan registrados.',
        );
        this.loadSummary();
        this.loadRows(this.page()?.meta.page ?? 1);
      },
      error: (error: unknown) => {
        this.reviewing.set(false);
        this.errorMessage.set(this.messageFor(error));
      },
    });
  }

  onPage(event: PageEvent): void {
    this.loadRows(event.pageIndex + 1, event.pageSize);
  }

  filterByReason(reason: string): void {
    this.filters.controls.motivo.setValue(reason);
    this.applyFilters();
  }

  reasonLabel(code: string): string {
    const labels: Record<string, string> = {
      EV_V1_NO_PUBLICABLE: 'Evaluación no publicable',
      EV_V1_OBSERVACION: 'Observación de evaluación',
      LOTE_INEXISTENTE: 'Lote sin correspondencia',
      DUPLICADO_EXACTO: 'Registro duplicado',
      CONFLICTO_DIAMETRO_RAMA: 'Diámetros distintos para la misma rama',
      DIAMETRO_FUERA_RANGO: 'Diámetro fuera de rango',
      DIAMETRO_NO_POSITIVO: 'Diámetro no válido',
      CONTEO_NEGATIVO: 'Conteo negativo',
      EVALUADOR_INEXISTENTE: 'Evaluador sin correspondencia',
      CLAVE_NATURAL_REPETIDA: 'Captura repetida de flores',
      IDENTIFICADORES_INCOMPLETOS: 'Faltan identificadores obligatorios',
    };
    return (
      labels[code] ??
      code
        .replaceAll('_', ' ')
        .toLocaleLowerCase('es-PE')
        .replace(/^./, (letter) => letter.toLocaleUpperCase('es-PE'))
    );
  }

  domainLabel(row: AdminQARejectItem): string {
    const source = `${row.tabla_origen} ${row.tabla_destino ?? ''}`.toLocaleLowerCase();
    if (
      /estado|flor|fruto|baya|brote|rama|evaluacion/.test(source) ||
      row.hallazgo === 'EVALUACIONES-V1'
    )
      return 'Evaluaciones';
    if (source.includes('forecast')) return 'Forecast';
    if (source.includes('cosecha')) return 'Cosecha';
    if (source.includes('packing')) return 'Packing';
    return 'Otros datos';
  }

  isEvaluation(row: AdminQARejectItem): boolean {
    return this.domainLabel(row) === 'Evaluaciones';
  }

  resolutionTitle(row: AdminQARejectItem): string {
    if (!this.isEvaluation(row)) return 'Consulta y clasificación';
    const titles: Record<string, string> = {
      DUPLICADO_EXACTO: 'Confirmar sin volver a insertar',
      LOTE_INEXISTENTE: 'Asignar un lote válido',
      CONFLICTO_DIAMETRO_RAMA: 'Elegir el diámetro correcto',
      DIAMETRO_FUERA_RANGO: 'Corregir o aceptar conscientemente',
      DIAMETRO_NO_POSITIVO: 'Introducir una medición válida',
      CONTEO_NEGATIVO: 'Corregir el conteo enlazado',
      EVALUADOR_INEXISTENTE: 'Vincular con un evaluador',
      CLAVE_NATURAL_REPETIDA: 'Comparar capturas candidatas',
      IDENTIFICADORES_INCOMPLETOS: 'Completar identificadores',
    };
    return titles[row.motivo] ?? 'Revisar evidencia de evaluación';
  }

  resolutionDescription(row: AdminQARejectItem): string {
    if (!this.isEvaluation(row)) {
      return 'Puedes clasificar la evidencia y dejar un criterio auditado. El reproceso de este dominio aún no está habilitado.';
    }
    const descriptions: Record<string, string> = {
      DUPLICADO_EXACTO:
        'La evidencia se marcará como duplicada y no se volverá a materializar en las tablas de evaluaciones.',
      LOTE_INEXISTENTE:
        'Marca la incidencia para corrección; el lote debe seleccionarse desde el catálogo agrícola antes del reproceso.',
      CONFLICTO_DIAMETRO_RAMA:
        'Compara el valor recibido con la captura existente y documenta cuál debe conservarse.',
      DIAMETRO_FUERA_RANGO:
        'Comprueba la unidad y el valor original antes de corregirlo o aceptar la excepción.',
      DIAMETRO_NO_POSITIVO:
        'La observación necesita un diámetro mayor que cero para poder materializarse.',
      CONTEO_NEGATIVO:
        'El conteo enlazado debe corregirse a un valor válido antes de cerrar la incidencia.',
      EVALUADOR_INEXISTENTE:
        'Verifica el DNI y deja indicada la vinculación correcta con el maestro de evaluadores.',
      CLAVE_NATURAL_REPETIDA:
        'Revisa las capturas que comparten fecha, lote y planta antes de decidir cuál conservar.',
      IDENTIFICADORES_INCOMPLETOS:
        'Completa lote, fecha y posición de planta antes de enviar el registro a corrección.',
    };
    return (
      descriptions[row.motivo] ??
      'Revisa la evidencia, documenta el criterio y asigna la siguiente acción.'
    );
  }

  findingText(row: AdminQARejectItem): string {
    const detail = row.detalle;
    if (!detail) return row.hallazgo || 'La regla identificó una incidencia en esta evidencia.';
    try {
      const reasons: unknown = JSON.parse(detail);
      if (Array.isArray(reasons) && reasons.every((r) => typeof r === 'string')) {
        return reasons
          .map((r) =>
            r
              .split(':')
              .map((part: string, i: number) => (i ? part : this.reasonLabel(part)))
              .join(' · '),
          )
          .join('; ');
      }
    } catch {
      /* Free-text findings are already readable. */
    }
    return detail;
  }

  setDecision(state: QAReviewRequest['estado']): void {
    this.reviewForm.controls.estado.setValue(state);
  }

  selectedDecision(state: QAReviewRequest['estado']): boolean {
    return this.reviewForm.controls.estado.value === state;
  }

  humanFields(row: AdminQARejectItem): Array<{ label: string; value: string }> {
    const labels: Record<string, string> = {
      numero_muestra: 'Muestra',
      publicacion_id: 'Publicación',
      source_row_number: 'Fila de origen',
      Fecha: 'Fecha',
      fecha: 'Fecha',
      Fundo: 'Fundo',
      fundo: 'Fundo',
      Modulo: 'Módulo',
      modulo: 'Módulo',
      Lote: 'Lote',
      lote: 'Lote',
      DNI: 'DNI del evaluador',
      dni: 'DNI del evaluador',
      Cortina: 'Cortina',
      cortina: 'Cortina',
      Hilera: 'Hilera',
      hilera: 'Hilera',
      Planta: 'Planta',
      planta: 'Planta',
      Diametro: 'Diámetro',
      diametro: 'Diámetro',
      Item: 'Ítem',
      item: 'Ítem',
    };
    return Object.entries(row.fila)
      .filter(
        ([key, value]) =>
          value !== null &&
          value !== '' &&
          (labels[key] ||
            /fecha|fundo|modulo|lote|dni|cortina|hilera|planta|diametro|item/i.test(key)),
      )
      .slice(0, 12)
      .map(([key, value]) => ({
        label: labels[key] ?? key.replaceAll('_', ' '),
        value: String(value),
      }));
  }

  private loadSummary(): void {
    this.api
      .qualitySummary()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (summary) => this.summary.set(summary),
        error: (error: unknown) => this.errorMessage.set(this.messageFor(error)),
      });
  }

  private loadRows(page = 1, pageSize = this.page()?.meta.page_size ?? 25): void {
    this.listRequest?.unsubscribe();
    this.loading.set(true);
    this.errorMessage.set(null);
    this.activeState.set(this.filters.controls.estado_revision.value);
    this.activeReason.set(this.filters.controls.motivo.value);
    this.activePriority.set(this.filters.controls.excede_umbral.value === 'true');
    this.listRequest = this.api
      .listQuality({
        page,
        page_size: pageSize,
        search: this.filters.controls.search.value || undefined,
        motivo: this.filters.controls.motivo.value || undefined,
        tabla_origen: this.filters.controls.tabla_origen.value || undefined,
        hallazgo: this.filters.controls.hallazgo.value || undefined,
        excede_umbral:
          this.filters.controls.excede_umbral.value === ''
            ? undefined
            : this.filters.controls.excede_umbral.value === 'true',
        estado_revision: this.filters.controls.estado_revision.value || undefined,
      })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (response) => {
          this.page.set(response);
          this.loading.set(false);
        },
        error: (error: unknown) => {
          this.loading.set(false);
          this.errorMessage.set(this.messageFor(error));
        },
      });
  }

  private messageFor(error: unknown): string {
    if (error instanceof HttpErrorResponse && typeof error.error?.detail === 'string') {
      return error.error.detail;
    }
    return 'No se pudo consultar la cuarentena de calidad.';
  }
}
