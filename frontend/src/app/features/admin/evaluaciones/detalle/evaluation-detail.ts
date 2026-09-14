import { DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Subscription } from 'rxjs';
import { ApiClient } from '../../../../core/api/api-client.service';
import type { AdminEvaluationDetail, AdminEvaluationItem } from '../../../../core/api/models';
import { observationsFor } from '../evaluation-format';
import type { EvaluationWorkspace } from '../evaluation-workspace.service';
type Host = Pick<EvaluationWorkspace, 'errorMessage' | 'editing' | 'successMessage' | 'messageFor'>;
export class EvaluationDetail {
  constructor(private readonly getHost: () => Host) {}
  cancelPending(): void {
    this.detailRequest?.unsubscribe();
    this.observationRequest?.unsubscribe();
  }
  private get host(): Host {
    return this.getHost();
  }
  private readonly api = inject(ApiClient);
  private readonly destroyRef = inject(DestroyRef);
  readonly selected = signal<AdminEvaluationDetail | null>(null);
  readonly detailLoading = signal(false);
  readonly observationPage = signal(1);
  readonly observationSize = 25;
  readonly observationRows = signal<Record<string, unknown>[]>([]);
  readonly observationTotal = signal(0);
  readonly observationsLoading = signal(false);
  private observationRequest?: Subscription;
  private detailRequest?: Subscription;
  observations(detail: AdminEvaluationDetail): Array<Record<string, unknown>> {
    return observationsFor(
      detail.detalle ?? {},
      detail.module_key === 'ramas' ? 'mediciones' : 'observaciones',
    );
  }
  pagedObservations(detail: AdminEvaluationDetail) {
    return this.observationRows();
  }
  loadObservationPage(page = 1) {
    const detail = this.selected();
    if (!detail) return;
    this.observationRequest?.unsubscribe();
    this.observationsLoading.set(true);
    this.observationRows.set([]);
    this.observationRequest = this.api
      .evaluationObservations(detail.module_key, detail.source_id, detail.source_table, page)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (r) => {
          this.observationRows.set(r.items);
          this.observationTotal.set(r.total);
          this.observationPage.set(r.page);
          this.observationsLoading.set(false);
        },
        error: () => {
          this.observationsLoading.set(false);
          this.host.errorMessage.set('No se pudieron cargar las observaciones.');
        },
      });
  }
  selectRecord(row: Pick<AdminEvaluationItem, 'module_key' | 'source_id' | 'source_table'>): void {
    this.observationPage.set(1);
    this.detailRequest?.unsubscribe();
    this.detailLoading.set(true);
    this.selected.set(null);
    this.host.editing.set(false);
    this.host.successMessage.set(null);
    this.observationRows.set([]);
    this.observationTotal.set(0);
    this.observationRequest?.unsubscribe();
    this.detailRequest = this.api
      .evaluationCard(row.module_key, row.source_id, row.source_table)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (detail) => {
          this.detailLoading.set(false);
          this.selected.set(detail);
          this.observationTotal.set(Number(detail.detalle?.['total_observaciones']) || 0);
          if (this.observationTotal()) this.loadObservationPage();
        },
        error: (error: unknown) => {
          this.detailLoading.set(false);
          this.host.errorMessage.set(
            this.host.messageFor(error, 'No se pudo cargar el detalle. Intenta de nuevo.'),
          );
        },
      });
  }
}
