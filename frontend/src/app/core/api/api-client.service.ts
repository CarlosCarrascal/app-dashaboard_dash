import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, tap, catchError, throwError } from 'rxjs';
import { ReadCache } from './read-cache';
import { SessionReadCache } from './session-read-cache';
import {
  EvaluationCounts,
  AdminEvaluationDetail,
  AdminEvaluationCorrection,
  AdminEvaluationPage,
  AdminEvaluationSummary,
  AdminLoadPage,
  AdminMasterPage,
  AdminMutation,
  AdminQAPage,
  AdminQAReview,
  AdminQABulkResolution,
  AdminQASummary,
  AuthUser,
  EvaluationQuery,
  ImportPreview,
  ImportConfirmRequest,
  ImportResult,
  EvaluationCorrectionRequest,
  MasterMutationRequest,
  LoginRequest,
  LoadQuery,
  MasterQuery,
  MasterResource,
  QAQuery,
  QABulkDuplicateRequest,
  QAReviewRequest,
  TokenPair,
  UserMutationRequest,
} from './models';

@Injectable({ providedIn: 'root' })
export class ApiClient {
  private readonly http = inject(HttpClient);
  private readonly baseUrl = '/v1';
  private readonly reads = new ReadCache();
  private readonly evaluationReads = new ReadCache(36);
  private readonly sessionReads = new SessionReadCache();
  clearReadCache(): void {
    this.sessionReads.clear();
    this.reads.clear();
    this.evaluationReads.clear();
  }
  private cachedGet<T>(url: string, query: object = {}, ttl = 30_000, cache = this.reads): Observable<T> {
    const params = this.toParams(query);
    const key =
      url +
      '?' +
      params
        .keys()
        .sort()
        .map((k) => encodeURIComponent(k) + '=' + encodeURIComponent(params.get(k)!))
        .join('&');
    const aggregate = url.endsWith('/conteos') || url.endsWith('/qa/resumen') || url.endsWith('/maestros/fundos')
      || (url.includes('/analitica') && (params.get('snapshot') === 'true' || params.get('series_only') === 'true'));
    const request = () => this.http.get<T>(url, { params });
    return cache.read(key, () => aggregate ? this.sessionReads.read(key, request, ttl) : request(), ttl);
  }

  login(payload: LoginRequest): Observable<TokenPair> {
    return this.http
      .post<TokenPair>(`${this.baseUrl}/auth/login`, payload)
      .pipe(tap(() => this.clearReadCache()));
  }

  refresh(refreshToken: string): Observable<TokenPair> {
    return this.http
      .post<TokenPair>(`${this.baseUrl}/auth/refresh`, {
        refresh_token: refreshToken,
      })
      .pipe(tap(() => this.clearReadCache()));
  }

  me(): Observable<AuthUser> {
    return this.http.get<AuthUser>(`${this.baseUrl}/auth/me`);
  }

  listEvaluations(query: EvaluationQuery = {}): Observable<AdminEvaluationPage> {
    return this.cachedGet<AdminEvaluationPage>(`${this.baseUrl}/admin/evaluaciones`, query, 600_000, this.evaluationReads);
  }

  evaluationAnalytics<T>(query: Record<string, unknown>, trend = false): Observable<T> {
    const url = `${this.baseUrl}/admin/evaluaciones/analitica${trend ? '/tendencia' : ''}`;
    return this.cachedGet<T>(url, query, 600_000, this.evaluationReads);
  }

  evaluationCounts(query: EvaluationQuery = {}): Observable<EvaluationCounts> {
    return this.cachedGet<EvaluationCounts>(`${this.baseUrl}/admin/evaluaciones/conteos`, query, 600_000).pipe(
      catchError(error => error.status === 404 ? this.evaluationSummary(query) : throwError(() => error)),
    );
  }

  evaluationSummary(query: EvaluationQuery = {}): Observable<AdminEvaluationSummary> {
    return this.cachedGet<AdminEvaluationSummary>(`${this.baseUrl}/admin/evaluaciones/resumen`, query, 600_000);
  }

  evaluationDetail(
    moduleKey: string,
    sourceId: number,
    sourceTable?: string,
  ): Observable<AdminEvaluationDetail> {
    let params = new HttpParams();
    if (sourceTable) {
      params = params.set('source_table', sourceTable);
    }
    return this.http.get<AdminEvaluationDetail>(
      `${this.baseUrl}/admin/evaluaciones/${moduleKey}/${sourceId}`,
      { params },
    );
  }

  evaluationCard(
    moduleKey: string,
    sourceId: number,
    sourceTable: string,
  ): Observable<AdminEvaluationDetail> {
    return this.http.get<AdminEvaluationDetail>(
      `${this.baseUrl}/admin/evaluaciones/ficha/${moduleKey}/${sourceId}`,
      { params: { source_table: sourceTable } },
    );
  }

  evaluationObservations(moduleKey: string, sourceId: number, sourceTable: string, page = 1) {
    return this.http.get<{
      items: Record<string, unknown>[];
      total: number;
      page: number;
      page_size: number;
    }>(`${this.baseUrl}/admin/evaluaciones/observaciones/${moduleKey}/${sourceId}`, {
      params: { source_table: sourceTable, page, page_size: 25 },
    });
  }

  correctEvaluation(
    moduleKey: string,
    sourceId: number,
    payload: EvaluationCorrectionRequest,
  ): Observable<AdminEvaluationCorrection> {
    return this.http
      .patch<AdminEvaluationCorrection>(
        `${this.baseUrl}/admin/evaluaciones/${moduleKey}/${sourceId}`,
        payload,
      )
      .pipe(tap(() => this.clearReadCache()));
  }

  listMaster(resource: MasterResource, query: MasterQuery = {}): Observable<AdminMasterPage> {
    return this.cachedGet<AdminMasterPage>(`${this.baseUrl}/admin/maestros/${resource}`, query, 300_000);
  }

  createMaster(
    resource: MasterResource,
    payload: MasterMutationRequest,
  ): Observable<AdminMutation> {
    return this.http
      .post<AdminMutation>(`${this.baseUrl}/admin/maestros/${resource}`, payload)
      .pipe(tap(() => this.clearReadCache()));
  }

  updateMaster(
    resource: MasterResource,
    resourceId: number,
    payload: MasterMutationRequest,
  ): Observable<AdminMutation> {
    return this.http
      .patch<AdminMutation>(`${this.baseUrl}/admin/maestros/${resource}/${resourceId}`, payload)
      .pipe(tap(() => this.clearReadCache()));
  }

  listRoles(query: MasterQuery = {}): Observable<AdminMasterPage> {
    return this.cachedGet<AdminMasterPage>(`${this.baseUrl}/admin/roles`, query);
  }

  listUsers(query: MasterQuery = {}): Observable<AdminMasterPage> {
    return this.cachedGet<AdminMasterPage>(`${this.baseUrl}/admin/usuarios`, query);
  }

  createUser(payload: UserMutationRequest): Observable<AdminMutation> {
    return this.http
      .post<AdminMutation>(`${this.baseUrl}/admin/usuarios`, payload)
      .pipe(tap(() => this.clearReadCache()));
  }

  updateUser(usuarioId: number, payload: UserMutationRequest): Observable<AdminMutation> {
    return this.http
      .patch<AdminMutation>(`${this.baseUrl}/admin/usuarios/${usuarioId}`, payload)
      .pipe(tap(() => this.clearReadCache()));
  }

  listImports(query: LoadQuery = {}): Observable<AdminLoadPage> {
    return this.http.get<AdminLoadPage>(`${this.baseUrl}/admin/cargas`, {
      params: this.toParams(query),
    });
  }

  qualitySummary(): Observable<AdminQASummary> {
    return this.cachedGet<AdminQASummary>(`${this.baseUrl}/admin/qa/resumen`);
  }

  listQuality(query: QAQuery = {}): Observable<AdminQAPage> {
    return this.cachedGet<AdminQAPage>(`${this.baseUrl}/admin/qa/rechazos`, query);
  }

  reviewQuality(rechazoId: number, payload: QAReviewRequest): Observable<AdminQAReview> {
    return this.http
      .patch<AdminQAReview>(`${this.baseUrl}/admin/qa/rechazos/${rechazoId}/revision`, payload)
      .pipe(tap(() => this.clearReadCache()));
  }

  confirmQualityDuplicates(payload: QABulkDuplicateRequest): Observable<AdminQABulkResolution> {
    return this.http
      .post<AdminQABulkResolution>(`${this.baseUrl}/admin/qa/duplicados/confirmar`, payload)
      .pipe(tap(() => this.clearReadCache()));
  }

  previewEvaluations(file: File): Observable<ImportPreview> {
    const form = new FormData();
    form.append('archivo', file, file.name);
    return this.http
      .post<ImportPreview>(`${this.baseUrl}/admin/evaluaciones/previsualizar`, form)
      .pipe(tap(() => this.clearReadCache()));
  }

  confirmEvaluations(payload: ImportConfirmRequest): Observable<ImportResult> {
    return this.http
      .post<ImportResult>(`${this.baseUrl}/admin/evaluaciones/cargar`, payload)
      .pipe(tap(() => this.clearReadCache()));
  }

  downloadEvaluationTemplate(): Observable<Blob> {
    return this.http.get(`${this.baseUrl}/admin/evaluaciones/plantilla`, {
      responseType: 'blob',
    });
  }

  private toParams(query: object): HttpParams {
    let params = new HttpParams();
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined && value !== null && value !== '') {
        params = params.set(key, String(value));
      }
    }
    return params;
  }
}
