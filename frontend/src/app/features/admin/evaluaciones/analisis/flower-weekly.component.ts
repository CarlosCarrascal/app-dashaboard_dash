import { Component, DestroyRef, computed, effect, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Router, RouterLink } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { ApiClient } from '../../../../core/api/api-client.service';
import { EvaluationWorkspace } from '../evaluation-workspace.service';
import { EvaluationChartComponent } from '../evaluation-chart.component';
import { WeeklyReport, reportOptions } from '../../informes/weekly-series';

export function weeklyScope(raw: Record<string, unknown>, snapshot: boolean, grain: string | null, end: string | null, metric: string, weeks: number): Record<string, unknown> {
  const query: Record<string, unknown> = { metric, weeks, grano: grain || undefined, hasta: end || undefined };
  for (const key of ['empresa_id','fundo_id','modulo_id','lote_id','evaluador_id','search']) {
    if (raw[key]) query[key] = raw[key];
  }
  if (!snapshot && raw['desde']) query['desde'] = raw['desde'];
  return query;
}

@Component({
  selector: 'app-flower-weekly', standalone: true,
  imports: [FormsModule, RouterLink, EvaluationChartComponent],
  templateUrl: './flower-weekly.component.html',
})
export class FlowerWeeklyComponent {
  readonly vm = inject(EvaluationWorkspace);
  private api = inject(ApiClient);
  private destroy = inject(DestroyRef);
  private router = inject(Router);
  readonly weeks = signal(26);
  readonly metric = signal('n_flores');
  readonly report = signal<WeeklyReport | null>(null);
  readonly loading = signal(false);
  readonly error = signal(false);
  private retry = signal(0);
  readonly title = computed(() => (this.report()?.metric ?? this.metric()) === 'cuajo' ? 'Cuajos observados' : 'Flores observadas');
  readonly query = computed(() => weeklyScope(this.vm.appliedValues(), this.vm.snapshot(), this.vm.analytics()?.grano ?? null, this.vm.analytics()?.hasta ?? null, this.metric(), this.weeks()));
  readonly presentationQuery = computed(() => ({...this.query(), indicador:this.report()?.metric ?? this.metric(), semanas:this.weeks(), desde:this.report()?.desde, hasta:this.report()?.hasta, metric:undefined, weeks:undefined}));
  readonly funds = computed(() => {
    const r = this.report(); if (!r) return [];
    return [...new Map(r.points.map(p => [p.fundo_id,p.fundo])).entries()].map(([id,name]) => {
      const points = r.points.filter(p => p.fundo_id === id);
      return {id,name,points,options:reportOptions(r,points),available:points.reduce((sum,p)=>sum+p.available,0),evaluations:points.reduce((sum,p)=>sum+p.evaluations,0)};
    });
  });
  constructor() {
    effect(onCleanup => {
      const query = this.query(); this.retry();
      if (!this.vm.analytics()) return;
      this.loading.set(true); this.error.set(false);
      const subscription = this.api.weeklyReport<WeeklyReport>(query).pipe(takeUntilDestroyed(this.destroy)).subscribe({
        next: value => { this.report.set(value); this.loading.set(false); },
        error: () => { this.error.set(true); this.loading.set(false); },
      });
      onCleanup(() => subscription.unsubscribe());
    });
  }
  reload() { this.retry.update(n => n+1); }
  number(value: number) { return value.toLocaleString('es-PE',{maximumFractionDigits:1}); }
  openPoint(key: string) {
    const [module,week] = key.split('|'), r = this.report();
    if (!module || !week || !r) return;
    const end = new Date(week+'T00:00:00Z'); end.setUTCDate(end.getUTCDate()+6);
    void this.router.navigate(['/admin/evaluaciones/flores'],{queryParams:{...this.vm.appliedValues(),module_key:undefined,vista:'registros',periodo:'rango',desde:week,hasta:end.toISOString().slice(0,10)<r.hasta! ? end.toISOString().slice(0,10):r.hasta,modulo_id:module,grano:r.grano}});
  }
}
