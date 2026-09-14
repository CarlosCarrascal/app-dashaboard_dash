import { Injectable, inject } from '@angular/core';
import { ApiClient } from './api-client.service';
import { AuthService } from '../auth/auth.service';

@Injectable({ providedIn: 'root' })
export class EvaluationPreload {
  private readonly api = inject(ApiClient);
  private readonly auth = inject(AuthService);

  prepare(family: string): void {
    if (!this.auth.isAuthenticated() || !this.auth.hasPermission('admin:evaluaciones:leer')) return;
    if (!['estadios', 'flores', 'baya', 'pesos', 'brotes', 'ramas'].includes(family)) return;
    // ApiClient shares pending reads and cached results with the destination.
    this.api.evaluationAnalytics({
      module_key: family, sort_by: 'fecha', sort_dir: 'desc',
      snapshot: true, snapshot_series: true, series_only: true,
      include_trend: false, metric: 'n_flores',
    // Let the finite HTTP observable complete so ReadCache can retain the result.
    }).subscribe({ error: () => { /* The destination handles errors and retry. */ } });
  }
}
