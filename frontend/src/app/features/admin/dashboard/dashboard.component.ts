import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { RouterLink } from '@angular/router';
import { forkJoin } from 'rxjs';
import { ApiClient } from '../../../core/api/api-client.service';
import { AdminEvaluationSummary, AdminLoadItem, AdminQASummary } from '../../../core/api/models';
import { AuthService } from '../../../core/auth/auth.service';
import { AppIconComponent } from '../../../shared/ui/app-icon.component';
import { PageHeaderComponent } from '../../../shared/ui/page-header.component';

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [
    MatButtonModule,
    MatCardModule,
    AppIconComponent,
    PageHeaderComponent,
    RouterLink,
  ],
  templateUrl: './dashboard.component.html',
  styleUrl: './dashboard.component.scss',
})
export class DashboardComponent implements OnInit {
  private readonly api = inject(ApiClient);
  private readonly auth = inject(AuthService);
  readonly summary = signal<AdminEvaluationSummary | null>(null);
  readonly quality = signal<AdminQASummary | null>(null);
  readonly imports = signal<AdminLoadItem[]>([]);
  readonly loading = signal(true);
  readonly errorMessage = signal<string | null>(null);
  readonly canSeeEvaluations = computed(() => this.auth.hasPermission('admin:evaluaciones:leer'));
  readonly canSeeQuality = computed(() => this.auth.hasPermission('admin:qa:leer'));
  readonly canImport = computed(() => this.auth.hasPermission('admin:evaluaciones:cargar'));

  ngOnInit(): void {
    const requests: Record<string, ReturnType<ApiClient['evaluationSummary']> | ReturnType<ApiClient['qualitySummary']> | ReturnType<ApiClient['listImports']>> = {};
    if (this.canSeeEvaluations()) requests['evaluations'] = this.api.evaluationSummary();
    if (this.canSeeQuality()) requests['quality'] = this.api.qualitySummary();
    if (this.canImport()) requests['imports'] = this.api.listImports({ page: 1, page_size: 5 });

    if (Object.keys(requests).length === 0) {
      this.loading.set(false);
      return;
    }

    forkJoin(requests).subscribe({
      next: (responses) => {
        if (responses['evaluations']) this.summary.set(responses['evaluations'] as AdminEvaluationSummary);
        if (responses['quality']) this.quality.set(responses['quality'] as AdminQASummary);
        if (responses['imports']) this.imports.set((responses['imports'] as { items: AdminLoadItem[] }).items);
        this.loading.set(false);
      },
      error: (error: unknown) => {
        this.loading.set(false);
        this.errorMessage.set(this.messageFor(error));
      },
    });
  }

  familyLabel(key: string): string {
    return ({ estadios: 'Conteo de estadios', flores: 'Conteo de flores', baya: 'Desarrollo de fruto', pesos: 'Peso de baya', brotes: 'Conteo de brotes', ramas: 'Conteo de ramas' } as Record<string, string>)[key] ?? key;
  }

  reasonLabel(code: string): string {
    return ({ LOTE_INEXISTENTE: 'Lote sin correspondencia', DUPLICADO_EXACTO: 'Registro duplicado', CONFLICTO_DIAMETRO_RAMA: 'Diámetros distintos para la misma rama', DIAMETRO_FUERA_RANGO: 'Diámetro fuera de rango', DIAMETRO_NO_POSITIVO: 'Diámetro no válido', CONTEO_NEGATIVO: 'Conteo negativo', EVALUADOR_INEXISTENTE: 'Evaluador sin correspondencia', CLAVE_NATURAL_REPETIDA: 'Captura repetida' } as Record<string, string>)[code] ?? code.replaceAll('_', ' ').toLocaleLowerCase('es-PE');
  }

  importStatus(value: AdminLoadItem['estado']): string {
    return ({ pending_confirmation: 'Pendiente', processing: 'Procesando', accepted: 'Completada', failed: 'Fallida' })[value];
  }

  hasOperationalAttention(): boolean {
    return Boolean(
      (this.quality()?.total_rechazos ?? 0) > 0
      || this.summary()?.por_modulo.some((item) => item.total === 0)
      || this.imports().some((item) => item.estado === 'failed' || item.estado === 'pending_confirmation'),
    );
  }

  formatNumber(value: number): string {
    return new Intl.NumberFormat('es-PE').format(value);
  }

  formatDate(value: string | null | undefined): string {
    if (!value) {
      return 'Sin datos';
    }
    return new Intl.DateTimeFormat('es-PE', { dateStyle: 'medium' }).format(new Date(value));
  }

  private messageFor(error: unknown): string {
    if (error instanceof HttpErrorResponse && typeof error.error?.detail === 'string') {
      return error.error.detail;
    }
    return 'No se pudo cargar el resumen. Revisa que FastAPI esté disponible.';
  }
}
