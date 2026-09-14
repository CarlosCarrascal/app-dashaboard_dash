import { Component, inject } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
@Component({ selector: 'app-evaluation-entry', standalone: true, template: '' })
export class EvaluationEntryComponent {
  constructor() {
    const route = inject(ActivatedRoute),
      router = inject(Router);
    const candidate =
      route.snapshot.queryParamMap.get('familia') ||
      localStorage.getItem('aquanqa.lastEvaluation') ||
      'estadios';
    const key = ['estadios', 'flores', 'baya', 'pesos', 'brotes', 'ramas'].includes(candidate)
      ? candidate
      : 'estadios';
    void router.navigate(['/admin/evaluaciones', key], { replaceUrl: true });
  }
}
