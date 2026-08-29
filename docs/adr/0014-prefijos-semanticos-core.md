# ADR-0014 · Prefijos semánticos para `core`

## Contexto

Las tablas de `raw` representan fuentes externas y deben conservar el nombre físico de
Access para poder auditar la extracción. En cambio, `core` es el modelo canónico: una tabla
de Access puede producir varias tablas de `core`, y el nombre de origen no siempre describe
el papel que tendrá en PostgreSQL.

## Decisión

Se aplican prefijos semánticos solo a las tablas de negocio de `core`:

| Prefijo | Significado | Ejemplos |
|---|---|---|
| `m_` | maestro o referencia estable | `m_empresa`, `m_lote`, `m_evaluador` |
| `t_` | dimensión temporal | `t_campania`, `t_calendario` |
| `evt_` | evento agronómico puntual | `evt_poda` |
| `ev_` | evaluación o medición de campo | `ev_flores`, `ev_evaluacion_ramas` |
| `op_` | operación o movimiento | `op_cosecha`, `op_packing`, `op_forecast_semanal` |
| `cfg_` | configuración de captura o negocio | `cfg_muestra_requerida` |

La convención se aplica a tablas, referencias SQL, procedimientos, catálogo, ETL, auditorías
y linaje. No se renombran las tablas/columnas físicas de `raw`, ni las tablas de la base
`aquanqa`, que continúa siendo la base operativa del dashboard. Tampoco se cambia el nombre de
columnas, índices o restricciones: son detalles internos y su renombrado no aporta claridad de
negocio.

## Mapeo aplicado

Los nombres de Access se preservan en `raw`; por ejemplo, `M_Lotes` sigue siendo
`raw.m_lotes`, mientras que sus entidades canónicas son `core.m_empresa`, `core.m_fundo`,
`core.m_modulo`, `core.m_turno`, `core.m_variedad` y `core.m_lote`.

En `aquanqa_migracion` el cambio se realizó con `ALTER TABLE ... RENAME`, dentro de una
transacción protegida. Por tanto, no recarga, no duplica y no altera las filas ni las
relaciones. Las referencias estructuradas del ledger y del linaje se actualizaron en la misma
operación; los nombres físicos y los snapshots de origen permanecen intactos. Como el catálogo
de destinos forma parte del contrato, se registró `access-c2026-2026-08-28.v2`; la versión `v1`
se conserva como histórico.

## Consecuencia

Al abrir `core` en pgAdmin, el prefijo permite distinguir rápidamente maestros, tiempo,
evaluaciones y operaciones. `core.v_catalogo` sigue siendo el punto de lectura funcional y
debe clasificar cualquier tabla nueva; una tabla no clasificada es una señal para revisar el
modelo, no un permiso para inventar otro prefijo.
