import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { catchError, map, of } from 'rxjs';
import { AuthService } from '../auth/auth.service';

export function permissionGuard(permission: string): CanActivateFn {
  return () => {
    const auth = inject(AuthService);
    const router = inject(Router);
    if (!auth.isAuthenticated()) {
      return router.createUrlTree(['/login']);
    }
    if (auth.user()) {
      return auth.hasPermission(permission)
        ? true
        : router.createUrlTree(['/access-denied']);
    }
    return auth.loadCurrentUser().pipe(
      map((user) =>
        (user.permisos ?? []).includes('*') || (user.permisos ?? []).includes(permission)
          ? true
          : router.createUrlTree(['/access-denied']),
      ),
      catchError(() => of(router.createUrlTree(['/login']))),
    );
  };
}
