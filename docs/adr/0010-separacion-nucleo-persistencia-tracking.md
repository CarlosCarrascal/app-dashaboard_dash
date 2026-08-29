# 0010 · Separar núcleo analítico, persistencia y tracking

## Estado

Aceptado.

## Contexto

La lógica analítica debe poder ejecutarse con datos en memoria y sin importar clientes de
base de datos, MLflow o librerías pesadas en las rutas que no los usan. El módulo histórico de
gobernanza mezclaba serialización, PostgreSQL, claims, identificación Git y tracking MLflow.
Esa mezcla hacía difícil importar, probar y reutilizar el núcleo.

## Decisión

Se separan las responsabilidades así:

- `proyeccion/infraestructura/`: serialización, identidad del commit y adaptadores técnicos;
- `proyeccion/persistencia/`: `RepositorioAnalytics` y operaciones de almacenamiento;
- `proyeccion/tracking.py`: contexto y registro opcional en MLflow;
- `proyeccion/gobernanza.py`: fachada de compatibilidad para los nombres históricos;
- los módulos de proyección: contratos, transformaciones y cálculos puros.

Las dependencias opcionales se importan dentro de las funciones que las necesitan. La
fachada `analitica.proyeccion` puede importarse sin activar PostgreSQL, `psycopg`, MLflow,
XGBoost o la pila estadística. Esto no significa que la instalación completa del paquete sea
minimalista: el `pyproject.toml` actual declara varias dependencias de ejecución como
obligatorias. La fachada `analitica.nucleo` también usa carga diferida; al solicitar
entrenamiento o evaluación se activan las librerías correspondientes, pero importar contratos,
clima o la fachada no las carga.

La corrección del contrato de `guardar_claims` —orden de parámetros y serialización segura
de campos JSONB— se conserva como corrección funcional controlada. No se cambia el contrato
de las demás operaciones SQL sin una prueba de equivalencia.

## Consecuencias

- El núcleo se puede probar sin infraestructura externa.
- La fachada mantiene `RepositorioAnalytics`, `commit_actual` y las funciones MLflow en sus
  rutas históricas.
- La persistencia real sigue necesitando una prueba de integración con PostgreSQL antes del
  cierre final; esa prueba está preparada en CI y no se pudo ejecutar en este entorno local.
- `analytics.evidence_claim` sigue siendo la tabla vigente del dashboard y
  `analytics.evidence_claim_history` conserva una copia por `(claim_id, run_id)`. El backfill
  normaliza strings JSON legacy o los conserva bajo `_legacy_jsonb`; no puede recuperar
  versiones que ya fueron sobrescritas antes de instalar la migración. Si el mismo par llega
  otra vez con contenido diferente, la persistencia detiene la corrida con
  `ClaimHistoryConflictError`.
- La actualización de campos de claims no contemplados por el upsert queda como revisión
  pendiente, no como cambio silencioso.

## Alternativas descartadas

- Importar todos los adaptadores al arrancar: haría frágiles los imports y los comandos.
- Mantener todo en `gobernanza.py`: conserva el acoplamiento que motivó la extracción.
- Reemplazar la persistencia por mocks en producción: ocultaría errores de SQL.
