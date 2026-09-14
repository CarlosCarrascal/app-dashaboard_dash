import { TestBed } from '@angular/core/testing';
import { Router } from '@angular/router';
import { Subject } from 'rxjs';
import { vi } from 'vitest';
import { AuthService } from './auth.service';
import { ApiClient } from '../api/api-client.service';
import { TokenPair } from '../api/models';
describe('Concurrent session refresh', () => {
  let auth: AuthService,
    response: Subject<TokenPair>,
    api: { refresh: ReturnType<typeof vi.fn>; clearReadCache: ReturnType<typeof vi.fn> };
  beforeEach(() => {
    sessionStorage.clear();
    sessionStorage.setItem('aquanqa.access_token', 'old');
    sessionStorage.setItem('aquanqa.refresh_token', 'refresh');
    response = new Subject();
    api = { refresh: vi.fn(() => response), clearReadCache: vi.fn() };
    TestBed.configureTestingModule({
      providers: [
        { provide: ApiClient, useValue: api },
        { provide: Router, useValue: { navigate: vi.fn() } },
      ],
    });
    auth = TestBed.inject(AuthService);
  });
  afterEach(() => sessionStorage.clear());
  const tokens = {
    expires_in: 900,
    token_type: 'bearer',
    access_token: 'new',
    refresh_token: 'next',
    user: {
      usuario_id: 1,
      email: 'test@example.com',
      nombre: 'Test',
      rol: 'lectura',
      permisos: [],
      alcances: [],
    },
  } as TokenPair;
  it('coalesces simultaneous expired requests into one renewal', () => {
    const seen: string[] = [];
    auth.refresh().subscribe((t) => seen.push(t.access_token));
    auth.refresh().subscribe((t) => seen.push(t.access_token));
    expect(api.refresh).toHaveBeenCalledTimes(1);
    response.next(tokens);
    response.complete();
    expect(seen).toEqual(['new', 'new']);
    expect(auth.accessToken()).toBe('new');
    auth.refresh().subscribe();
    expect(api.refresh).toHaveBeenCalledTimes(2);
  });
  it('does not restore a session after logout', () => {
    const error = vi.fn();
    auth.refresh().subscribe({ error });
    auth.logout();
    response.next(tokens);
    response.complete();
    expect(auth.isAuthenticated()).toBe(false);
    expect(error).toHaveBeenCalledTimes(1);
  });
  it('clears invalid credentials once for a shared failed renewal', () => {
    auth.refresh().subscribe({ error: () => {} });
    auth.refresh().subscribe({ error: () => {} });
    response.error(new Error('expired'));
    expect(api.refresh).toHaveBeenCalledTimes(1);
    expect(api.clearReadCache).toHaveBeenCalledTimes(1);
    expect(auth.isAuthenticated()).toBe(false);
  });
});
