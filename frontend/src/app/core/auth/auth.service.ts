import { computed, inject, Injectable, signal } from '@angular/core';
import { Router } from '@angular/router';
import { catchError, finalize, Observable, shareReplay, tap, throwError } from 'rxjs';
import { ApiClient } from '../api/api-client.service';
import { AuthUser, LoginRequest, TokenPair } from '../api/models';

const ACCESS_TOKEN_KEY = 'aquanqa.access_token';
const REFRESH_TOKEN_KEY = 'aquanqa.refresh_token';
const USER_KEY = 'aquanqa.user';

@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly api = inject(ApiClient);
  private readonly router = inject(Router);
  private readonly accessTokenSignal = signal(this.readStorage(ACCESS_TOKEN_KEY));
  private readonly refreshTokenSignal = signal(this.readStorage(REFRESH_TOKEN_KEY));
  private readonly userSignal = signal<AuthUser | null>(this.readUser());

  private pendingRefresh?: { token: string; request: Observable<TokenPair> };

  readonly accessToken = this.accessTokenSignal.asReadonly();
  readonly user = this.userSignal.asReadonly();
  readonly isAuthenticated = computed(() => Boolean(this.accessTokenSignal()));

  login(payload: LoginRequest): Observable<TokenPair> {
    return this.api.login(payload).pipe(tap((tokens) => this.setSession(tokens)));
  }

  refresh(): Observable<TokenPair> {
    const token = this.refreshTokenSignal();
    if (!token) {
      return throwError(() => new Error('No existe una sesión renovable'));
    }
    if (this.pendingRefresh?.token === token) return this.pendingRefresh.request;
    const request = this.api.refresh(token).pipe(
      tap((tokens) => {
        if (this.refreshTokenSignal() !== token)
          throw new Error('La sesión cambió durante la renovación');
        this.setSession(tokens);
      }),
      catchError((error) => {
        if (this.refreshTokenSignal() === token) this.clearSession();
        return throwError(() => error);
      }),
      finalize(() => {
        if (this.pendingRefresh?.request === request) this.pendingRefresh = undefined;
      }),
      shareReplay({ bufferSize: 1, refCount: false }),
    );
    this.pendingRefresh = { token, request };
    return request;
  }

  loadCurrentUser(): Observable<AuthUser> {
    return this.api.me().pipe(
      tap((user) => this.setUser(user)),
      catchError((error) => {
        this.clearSession();
        return throwError(() => error);
      }),
    );
  }

  hasPermission(permission: string): boolean {
    const permissions = this.userSignal()?.permisos ?? [];
    return permissions.includes('*') || permissions.includes(permission);
  }

  logout(): void {
    this.clearSession();
    void this.router.navigate(['/login']);
  }

  private setSession(tokens: TokenPair): void {
    this.writeStorage(ACCESS_TOKEN_KEY, tokens.access_token);
    this.writeStorage(REFRESH_TOKEN_KEY, tokens.refresh_token);
    this.accessTokenSignal.set(tokens.access_token);
    this.refreshTokenSignal.set(tokens.refresh_token);
    this.setUser(tokens.user);
  }

  private setUser(user: AuthUser): void {
    this.userSignal.set(user);
    this.writeStorage(USER_KEY, JSON.stringify(user));
  }

  private clearSession(): void {
    this.api.clearReadCache();
    this.removeStorage(ACCESS_TOKEN_KEY);
    this.removeStorage(REFRESH_TOKEN_KEY);
    this.removeStorage(USER_KEY);
    this.accessTokenSignal.set(null);
    this.refreshTokenSignal.set(null);
    this.userSignal.set(null);
  }

  private readUser(): AuthUser | null {
    const raw = this.readStorage(USER_KEY);
    if (!raw) {
      return null;
    }
    try {
      return JSON.parse(raw) as AuthUser;
    } catch {
      return null;
    }
  }

  private readStorage(key: string): string | null {
    return typeof sessionStorage === 'undefined' ? null : sessionStorage.getItem(key);
  }

  private writeStorage(key: string, value: string): void {
    if (typeof sessionStorage !== 'undefined') {
      sessionStorage.setItem(key, value);
    }
  }

  private removeStorage(key: string): void {
    if (typeof sessionStorage !== 'undefined') {
      sessionStorage.removeItem(key);
    }
  }
}
