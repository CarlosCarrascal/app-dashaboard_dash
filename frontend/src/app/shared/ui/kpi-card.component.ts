import { Component, input } from '@angular/core';
import { AppIconComponent } from './app-icon.component';

@Component({
  selector: 'app-kpi-card',
  standalone: true,
  imports: [AppIconComponent],
  template: `
    <article class="kpi-card">
      <div class="kpi-topline">
        <span class="kpi-label">{{ label() }}</span>
        <span class="kpi-icon"><app-icon [name]="icon()" /></span>
      </div>
      <strong>{{ value() }}</strong>
      <span class="kpi-caption">{{ caption() }}</span>
    </article>
  `,
  styleUrl: './kpi-card.component.scss',
})
export class KpiCardComponent {
  readonly label = input.required<string>();
  readonly value = input.required<string>();
  readonly caption = input.required<string>();
  readonly icon = input.required<string>();
}
