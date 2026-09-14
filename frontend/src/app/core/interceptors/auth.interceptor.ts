import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { catchError, switchMap, throwError } from 'rxjs';
import { AuthService } from '../auth/auth.service';

export const authInterceptor: HttpInterceptorFn = (request, next) => {
  const auth = inject(AuthService);
  const token = auth.accessToken();
  if (!token || request.url.endsWith('/auth/login') || request.url.endsWith('/auth/refresh')) {
    return next(request);
  }
  const authenticatedRequest = request.clone({
    setHeaders: { Authorization: `Bearer ${token}` },
  });
  return next(authenticatedRequest).pipe(
    catchError((error: unknown) => {
      if (!(error instanceof HttpErrorResponse) || error.status !== 401) {
        return throwError(() => error);
      }
      return auth.refresh().pipe(
        switchMap(() => {
          const renewedToken = auth.accessToken();
          if (!renewedToken) {
            return throwError(() => error);
          }
          return next(
            request.clone({
              setHeaders: { Authorization: `Bearer ${renewedToken}` },
            }),
          );
        }),
        catchError((refreshError: unknown) => throwError(() => refreshError)),
      );
    }),
  );
};
