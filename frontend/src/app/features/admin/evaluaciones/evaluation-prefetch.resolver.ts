import { inject } from '@angular/core';
import { ResolveFn } from '@angular/router';
import { EvaluationPreload } from '../../../core/api/evaluation-preload.service';

/** Start the unfiltered first read while Angular downloads the lazy component.
 * The workspace subscribes to the same ApiClient pending read. Never block routing.
 */
export const evaluationPrefetch: ResolveFn<boolean> = (route) => {
  const family = route.paramMap.get('familia');
  if (!family || !['estadios', 'flores', 'baya', 'pesos', 'brotes', 'ramas'].includes(family))
    return true;
  // Filtered URLs are interpreted by the workspace; do not issue a different query.
  if (route.queryParamMap.keys.some((key) => !['vista', 'graphTiming'].includes(key))) return true;
  inject(EvaluationPreload).prepare(family);
  return true;
};
