import { TestBed } from '@angular/core/testing';
import { Router } from '@angular/router';
import { HttpErrorResponse } from '@angular/common/http';
import { Subject } from 'rxjs';
import { vi } from 'vitest';
import { AuthService } from '../../core/auth/auth.service';
import { LoginComponent } from './login.component';

describe('Login form', () => {
  let pending: Subject<unknown>;
  let login: ReturnType<typeof vi.fn>;
  let navigate: ReturnType<typeof vi.fn>;
  beforeEach(() => {
    pending = new Subject();
    login = vi.fn(() => pending);
    navigate = vi.fn();
    TestBed.configureTestingModule({ providers: [
      { provide: AuthService, useValue: { login } },
      { provide: Router, useValue: { navigate } },
    ] });
  });
  it('shows linked validation errors without attempting authentication', () => {
    const fixture = TestBed.createComponent(LoginComponent);
    fixture.detectChanges();
    fixture.nativeElement.querySelector('form').dispatchEvent(new Event('submit'));
    fixture.detectChanges();
    expect(login).not.toHaveBeenCalled();
    expect(fixture.nativeElement.querySelector('#login-email').getAttribute('aria-describedby')).toBe('email-error');
    expect(fixture.nativeElement.querySelector('#password-error').textContent).toContain('Ingresa tu contraseña');
  });
  it('prevents duplicate submissions while pending and preserves successful navigation', () => {
    const c = TestBed.createComponent(LoginComponent).componentInstance;
    c.form.setValue({ email: 'test@example.com', password: 'test-password' });
    c.submit(); c.submit();
    expect(login).toHaveBeenCalledTimes(1);
    expect(c.loading()).toBe(true);
    pending.next({});
    expect(navigate).toHaveBeenCalledWith(['/admin']);
    expect(c.loading()).toBe(false);
  });
  it('shows an authentication failure and allows a new attempt', () => {
    const c = TestBed.createComponent(LoginComponent).componentInstance;
    c.form.setValue({ email: 'test@example.com', password: 'test-password' });
    c.submit();
    pending.error(new HttpErrorResponse({ status: 401, error: { detail: 'Credenciales incorrectas' } }));
    expect(c.loading()).toBe(false);
    expect(c.errorMessage()).toBe('Credenciales incorrectas');
    pending = new Subject();
    c.submit();
    expect(login).toHaveBeenCalledTimes(2);
    expect(c.errorMessage()).toBeNull();
  });
  it('toggles password visibility without submitting the form', () => {
    const fixture = TestBed.createComponent(LoginComponent);
    fixture.detectChanges();
    fixture.nativeElement.querySelector('button[type="button"]').click();
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('#login-password').type).toBe('text');
    expect(login).not.toHaveBeenCalled();
    fixture.nativeElement.querySelector('button[type="button"]').click();
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('#login-password').type).toBe('password');
  });
});
