import { Routes } from '@angular/router';
import { permissionGuard } from '../../core/guards/permission.guard';
import { evaluationPrefetch } from './evaluaciones/evaluation-prefetch.resolver';

export const ADMIN_ROUTES: Routes = [
  {
    path: '',
    pathMatch: 'full',
    loadComponent: () =>
      import('./dashboard/dashboard.component').then((module) => module.DashboardComponent),
  },
  {
    path: 'evaluaciones',
    pathMatch: 'full',
    canActivate: [permissionGuard('admin:evaluaciones:leer')],
    loadComponent: () => import('./evaluaciones/evaluation-entry.component').then(m => m.EvaluationEntryComponent),
  },
  {
    path: 'evaluaciones/:familia',
    canActivate: [permissionGuard('admin:evaluaciones:leer')],
    resolve: { prepared: evaluationPrefetch },
    loadComponent: () =>
      import('./evaluaciones/evaluaciones.component').then(
        (module) => module.EvaluacionesComponent,
      ),
  },
  {
    path: 'maestros',
    canActivate: [permissionGuard('admin:maestros:leer')],
    loadComponent: () =>
      import('./maestros/maestros.component').then((module) => module.MaestrosComponent),
  },
  {
    path: 'qa',
    canActivate: [permissionGuard('admin:qa:leer')],
    loadComponent: () => import('./qa/qa.component').then((module) => module.QaComponent),
  },
  {
    path: 'seguridad',
    canActivate: [permissionGuard('admin:usuarios:gestionar')],
    loadComponent: () =>
      import('./seguridad/seguridad.component').then((module) => module.SeguridadComponent),
  },
  {
    path: 'cargas',
    canActivate: [permissionGuard('admin:evaluaciones:cargar')],
    loadComponent: () => import('./cargas/cargas.component').then(m => m.CargasComponent),
  },
  {
    path: 'operaciones',
    redirectTo: '',
    pathMatch: 'full',
  },
];
