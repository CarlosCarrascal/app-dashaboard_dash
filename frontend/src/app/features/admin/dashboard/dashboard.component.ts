import { Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivityOverviewComponent } from './activity-overview.component';
import { RouterLink } from '@angular/router';
import { ApiClient } from '../../../core/api/api-client.service';
import { EvaluationCounts, AdminQASummary } from '../../../core/api/models';
import { AuthService } from '../../../core/auth/auth.service';
import { AppIconComponent } from '../../../shared/ui/app-icon.component';
const FAMILIES = [
  { key: 'estadios', label: 'Estadios', icon: 'grid', color: '#145B45', description: 'Composición por color del fruto' },
  { key: 'flores', label: 'Flores', icon: 'flower', color: '#23946F', description: 'Flores, cuajos y yemas' },
  { key: 'baya', label: 'Desarrollo de fruto', icon: 'fruit', color: '#699C79', description: 'Tamaño y estados de las muestras' },
  { key: 'pesos', label: 'Peso de fruto', icon: 'weight', color: '#A3C979', description: 'Peso, diámetro y uniformidad' },
  { key: 'brotes', label: 'Brotes', icon: 'leaf', color: '#C39A4E', description: 'Conteos por lote y piso' },
  { key: 'ramas', label: 'Ramas', icon: 'branches', color: '#7D9896', description: 'Conteos y diámetros de ramas' },
];
@Component({
  selector: 'app-dashboard', standalone: true,
  imports: [RouterLink, AppIconComponent, ActivityOverviewComponent],
  templateUrl: './dashboard.component.html', styleUrl: './dashboard.component.scss',
})
export class DashboardComponent implements OnInit {
  private readonly api = inject(ApiClient);
  private readonly destroy = inject(DestroyRef);
  readonly auth = inject(AuthService);
  readonly summary = signal<EvaluationCounts | null>(null);
  readonly quality = signal<AdminQASummary | null>(null);
  readonly loading = signal(false);
  readonly qualityLoading = signal(false);
  readonly error = signal(false);
  readonly qualityError = signal(false);
  readonly canSeeEvaluations = computed(() => this.auth.hasPermission('admin:evaluaciones:leer'));
  readonly canSeeQuality = computed(() => this.auth.hasPermission('admin:qa:leer'));
  readonly families = computed(() => FAMILIES.map(f => ({ ...f, data: this.summary()?.por_modulo.find(m => m.module_key === f.key) })));
  readonly activeFamilies = computed(() => this.summary()?.por_modulo.filter(f => f.total > 0).length ?? 0);
  readonly reasons = computed(() => [...(this.quality()?.motivos ?? [])].sort((a, b) => b.filas - a.filas).slice(0, 3));
  ngOnInit(): void { this.loadSummary(); this.loadQuality(); }
  loadSummary(): void {
    if (!this.canSeeEvaluations() || this.loading()) return;
    this.loading.set(true); this.error.set(false);
    this.api.evaluationCounts().pipe(takeUntilDestroyed(this.destroy)).subscribe({
      next: value => { this.summary.set(value); this.loading.set(false); },
      error: () => { this.error.set(true); this.loading.set(false); },
    });
  }
  loadQuality(): void {
    if (!this.canSeeQuality() || this.qualityLoading()) return;
    this.qualityLoading.set(true); this.qualityError.set(false);
    this.api.qualitySummary().pipe(takeUntilDestroyed(this.destroy)).subscribe({
      next: value => { this.quality.set(value); this.qualityLoading.set(false); },
      error: () => { this.qualityError.set(true); this.qualityLoading.set(false); },
    });
  }
  share(count: number): number { const total = this.summary()?.total ?? 0; return total > 0 ? count / total * 100 : 0; }
  number(value: number): string { return new Intl.NumberFormat('es-PE').format(value); }
  percent(value: number): string { return new Intl.NumberFormat('es-PE', { maximumFractionDigits: 1 }).format(value) + '%'; }
  date(value?: string | null): string {
    if (!value) return 'Sin capturas';
    const parsed = new Date(value.length === 10 ? value + 'T12:00:00' : value);
    return Number.isNaN(parsed.getTime()) ? 'Fecha no disponible' : new Intl.DateTimeFormat('es-PE', { dateStyle: 'medium' }).format(parsed);
  }
  reason(value: string): string { return ({ DUPLICADO_EXACTO: 'Registros duplicados', EV_V1_OBSERVACION: 'Observaciones de captura', LOTE_INEXISTENTE: 'Lotes sin correspondencia', CONFLICTO_DIAMETRO_RAMA: 'Conflictos de diámetro' } as Record<string, string>)[value] ?? value.replaceAll('_', ' ').toLocaleLowerCase('es-PE'); }
}






