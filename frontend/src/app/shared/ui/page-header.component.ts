import { Component, input } from '@angular/core';

@Component({
  selector: 'app-page-header',
  standalone: true,
  template: `
    <header class="page-header">
      <div>
        <span class="eyebrow">{{ eyebrow() }}</span>
        <h1>{{ title() }}</h1>
        <p>{{ subtitle() }}</p>
      </div>
      <div class="page-actions"><ng-content /></div>
    </header>
  `,
  styleUrl: './page-header.component.scss',
})
export class PageHeaderComponent {
  readonly title = input.required<string>();
  readonly subtitle = input.required<string>();
  readonly eyebrow = input('OPERACIÓN AGRÍCOLA');
}
