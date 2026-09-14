import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { AdminLayoutComponent } from './admin-layout.component';
import { AuthService } from '../auth/auth.service';
import { ApiClient } from '../api/api-client.service';

describe('Evaluation navigation preparation', () => {
  it('prepares before navigation and shares pointer, keyboard and destination reads', () => {
    TestBed.configureTestingModule({
      providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting(),
        { provide: AuthService, useValue: { isAuthenticated: () => true, hasPermission: () => true } }],
    });
    const fixture = TestBed.createComponent(AdminLayoutComponent);
    fixture.detectChanges();
    const http = TestBed.inject(HttpTestingController);
    const link: HTMLAnchorElement = fixture.nativeElement.querySelector('a[aria-label="Flores"]');
    link.dispatchEvent(new Event('pointerenter'));
    link.dispatchEvent(new Event('focus'));
    link.dispatchEvent(new Event('pointerdown'));
    let received: unknown;
    TestBed.inject(ApiClient).evaluationAnalytics({
      module_key: 'flores', sort_by: 'fecha', sort_dir: 'desc', snapshot: true,
      snapshot_series: true, series_only: true, include_trend: false, metric: 'n_flores',
    }).subscribe(value => received = value);
    const request = http.expectOne(r => r.url.includes('/analitica'));
    expect(received).toBeUndefined();
    request.flush({ summary: { evaluations: 2 } });
    expect(received).toEqual({ summary: { evaluations: 2 } });
    link.dispatchEvent(new Event('focus'));
    http.expectNone(r => r.url.includes('/analitica'));
    http.verify();
    fixture.destroy();
  });
});
