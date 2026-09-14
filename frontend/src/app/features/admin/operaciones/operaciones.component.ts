import { Component } from '@angular/core';
import { MatCardModule } from '@angular/material/card';
import { PageHeaderComponent } from '../../../shared/ui/page-header.component';
import { AppIconComponent } from '../../../shared/ui/app-icon.component';

@Component({
  selector: 'app-operaciones',
  standalone: true,
  imports: [AppIconComponent, MatCardModule, PageHeaderComponent],
  template: `
    <app-page-header
      eyebrow="ROADMAP OPERATIVO"
      title="Módulos agrícolas"
      subtitle="El panel ya tiene la base de navegación y permisos para crecer por dominio."
    />
    <section class="roadmap-grid">
      @for (module of modules; track module.name) {
        <mat-card class="roadmap-card">
          <span class="module-icon"><app-icon name="evaluations" /></span>
          <h2>{{ module.name }}</h2>
          <p>{{ module.description }}</p>
          <span class="status">Siguiente módulo</span>
        </mat-card>
      }
    </section>
  `,
  styles: [
    `
      :host { display: block; }
      .roadmap-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 15px; }
      .roadmap-card { min-height: 170px; padding: 20px; border: 1px solid var(--aa-border); border-radius: 13px; }
      .module-icon { display: grid; width: 35px; height: 35px; place-items: center; border-radius: 9px; background: var(--aa-accent-soft); color: var(--aa-accent-deep); }
      h2 { margin: 17px 0 6px; color: var(--aa-ink); font-size: 1rem; }
      p { margin: 0; color: var(--aa-muted); font-size: .8rem; line-height: 1.5; }
      .status { display: inline-block; margin-top: 17px; color: var(--aa-accent-deep); font-size: .68rem; font-weight: 700; text-transform: uppercase; letter-spacing: .08em; }
      @media (max-width: 850px) { .roadmap-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
      @media (max-width: 520px) { .roadmap-grid { grid-template-columns: 1fr; } }
    `,
  ],
})
export class OperacionesComponent {
  readonly modules = [
    { name: 'Forecast', description: 'Proyección, aprobación y seguimiento de cosecha.', icon: 'trending_up' },
    { name: 'Cosecha', description: 'Avance, rendimiento y trazabilidad por lote.', icon: 'agriculture' },
    { name: 'Riego', description: 'Programación y cumplimiento de riegos.', icon: 'water_drop' },
    { name: 'Packing', description: 'Recepción, proceso y salida de fruta.', icon: 'inventory_2' },
    { name: 'Tareo', description: 'Jornales, turnos y productividad de campo.', icon: 'badge' },
    { name: 'Reportes', description: 'Indicadores exportables para la operación.', icon: 'summarize' },
  ];
}
