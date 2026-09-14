import { Routes } from '@angular/router';
import { authGuard } from './core/guards/auth.guard';

export const routes: Routes = [
  {
    path: 'login',
    loadComponent: () =>
      import('./features/seguridad/login.component').then((module) => module.LoginComponent),
  },
  {
    path: '',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./core/layout/admin-layout.component').then(
        (module) => module.AdminLayoutComponent,
      ),
    children: [
      {
        path: 'access-denied',
        loadComponent: () =>
          import('./features/seguridad/access-denied.component').then(
            (module) => module.AccessDeniedComponent,
          ),
      },
      {
        path: 'admin',
        loadChildren: () =>
          import('./features/admin/admin.routes').then((module) => module.ADMIN_ROUTES),
      },
      { path: '', pathMatch: 'full', redirectTo: 'admin' },
    ],
  },
  { path: '**', redirectTo: 'admin' },
];
