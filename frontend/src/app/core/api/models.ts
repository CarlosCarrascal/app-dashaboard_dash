import type { components, operations } from './generated';

type Schemas = components['schemas'];

export type ModuleKey = Schemas['AdminEvaluationItem']['module_key'];
export type MasterResource =
  | 'empresas'
  | 'fundos'
  | 'modulos'
  | 'lotes'
  | 'evaluadores'
  | 'campanias'
  | 'variedades'
  | 'turnos'
  | 'muestreo';

export type PageInfo = Schemas['PageInfo'];
export type AdminEvaluationItem = Schemas['AdminEvaluationItem'];
export type AdminEvaluationDetail = Schemas['AdminEvaluationDetail'];
export type AdminEvaluationCorrection = Schemas['AdminEvaluationCorrection'];
export type AdminEvaluationPage = Schemas['AdminEvaluationPage'];
export type AdminMasterPage = Schemas['AdminMasterPage'];
export type AdminMutation = Schemas['AdminMutation'];
export type AdminLoadItem = Schemas['AdminLoadItem'];
export type AdminLoadPage = Schemas['AdminLoadPage'];
export type AdminQAPage = Schemas['AdminQAPage'];
export type AdminQARejectItem = Schemas['AdminQARejectItem'];
export type AdminQASummary = Schemas['AdminQASummary'];
export type AdminQAReview = Schemas['AdminQAReview'];
export type AdminQABulkResolution = Schemas['AdminQABulkResolution'];
export type QABulkDuplicateRequest = Schemas['QABulkDuplicateRequest'];
export type ImportPreview = Schemas['ImportPreview'];
export type ImportConfirmRequest = Schemas['ImportConfirmRequest'];
export type ImportResult = Schemas['ImportResult'];
export type ImportPreviewRow = Schemas['ImportPreviewRow'];
export type EvaluationCreate = Schemas['EvaluationCreate'];
export type EvaluationCorrectionRequest = Schemas['EvaluationCorrectionRequest'];
export type MasterMutationRequest = Schemas['MasterMutationRequest'];
export type UserMutationRequest = Schemas['UserMutationRequest'];
export type EvaluationReceipt = Schemas['EvaluationReceipt'];
export type AuthUser = Schemas['AuthUser'];
export type TokenPair = Schemas['TokenPair'];

export type AdminEvaluationFamilySummary = Schemas['AdminEvaluationFamilySummary'];
export type AdminEvaluationIndicatorValues = Schemas['AdminEvaluationIndicatorValues'];
export type ModuleTotal = AdminEvaluationFamilySummary;
export type AdminEvaluationSummary = Schemas['AdminEvaluationSummary'];

export type LoginRequest = NonNullable<
  operations['iniciarSesionAdmin']['requestBody']
>['content']['application/json'];
export type RefreshRequest = NonNullable<
  operations['renovarSesionAdmin']['requestBody']
>['content']['application/json'];
export type EvaluationQuery = NonNullable<
  operations['listarEvaluacionesAdmin']['parameters']['query']
>;
export type MasterQuery = NonNullable<
  operations['listarMaestroAdmin']['parameters']['query']
>;
export type LoadQuery = NonNullable<
  operations['listarCargasAdmin']['parameters']['query']
>;
export type QAQuery = NonNullable<
  operations['listarRechazosCalidadAdmin']['parameters']['query']
>;
export type QAReviewRequest = NonNullable<
  operations['revisarRechazoCalidadAdmin']['requestBody']
>['content']['application/json'];

export type EvaluationCounts = Pick<AdminEvaluationSummary, 'total' | 'lotes' | 'evaluadores' | 'desde' | 'hasta' | 'ultima_captura'> & {
  por_modulo: Array<{module_key: string; total: number}>;
};
