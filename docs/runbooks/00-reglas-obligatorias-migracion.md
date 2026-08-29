# Reglas obligatorias de la migración Access → PostgreSQL

Estas reglas son parte del diseño operativo. Si una condición no se cumple, el proceso debe detenerse; no se debe continuar “a mano” ni marcar una tabla como migrada para hacer avanzar el porcentaje.

## 1. Bases separadas

- `aquanqa` es la base operativa del dashboard. Se conserva funcionando y no recibe DDL ni datos de esta migración.
- `aquanqa_migracion` es la única base autorizada para `raw → stg → qua → core`.
- Todos los comandos de migración deben indicar explícitamente `--database aquanqa_migracion`.
- El CLI bloquea `build`, `migrate`, `raw-only` y las carpetas del modelo cuando apuntan a `aquanqa`.

## 2. Fuente primaria

- `BD_AQUANQA_26.accdb` / `M_Lotes` de Access es la fuente principal para la campaña `C2026`.
- `M_Lotes.xlsx` solo sirve para contraste y control de diferencias; no puede sustituir Access.
- Solo se puede iniciar una ejecución contra un snapshot Access publicado.
- Cada archivo Access nuevo debe entrar como un snapshot nuevo, identificado por hash y versión; nunca se debe mezclar con el snapshot anterior en la misma ejecución.

## 3. Esquemas permitidos en esta fase

La base de migración usa únicamente estas capas de aplicación:

| Esquema | Uso obligatorio |
|---|---|
| `raw` | Copia auditable e inmutable de Access y controles de snapshots/ETL |
| `stg` | Tipado, limpieza y materialización intermedia |
| `qua` | Rechazos, diferencias y observaciones que no deben perderse |
| `core` | Modelo relacional validado para consumo futuro |

`public` es el esquema predeterminado de PostgreSQL, no una capa del modelo. `information_schema` y `pg_catalog` son esquemas del sistema.

En esta etapa no se permiten `dim`, `fact`, `reporting`, `analytics` ni `mlflow`. La visualización se mantiene fuera del alcance y el dashboard sigue en su base actual.

## 4. Tablas de `core` no equivalen a tablas migradas

Actualmente `core` contiene 34 tablas base y la vista `core.v_catalogo`: es el blueprint relacional preparado para recibir datos. La existencia de una tabla vacía no significa que su fuente Access esté migrada.

El avance oficial es exclusivamente el ledger:

```sql
SELECT * FROM raw.v_migracion_resumen;
SELECT tabla_raw, estado, filas_raw, filas_stg, filas_core, filas_cuarentena
FROM raw.v_migracion_tablas
ORDER BY tabla_raw;
```

El objetivo inicial es una ejecución con 23 tablas Access registradas. Una tabla solo pasa a `migrada` después de validar `raw → stg → core`; si hay rechazos documentados, queda `migrada_con_observaciones`.

## 5. Check-to-check obligatorio

Cada bloque debe:

1. Ejecutar el preflight.
2. Marcar una única tabla como `en_proceso`.
3. Materializar su staging.
4. Cargar su destino core, si ya está definido.
5. Medir filas en raw, stg, core y qua.
6. Comparar contra el criterio del plan.
7. Registrar el resultado con `raw.sp_registrar_tabla_migracion(...)`.
8. Detenerse si la comparación falla.

No se permite actualizar directamente el estado del ledger saltándose el procedimiento. El trigger impide cerrar una tabla sin conteos raw/stg/core, detalle de validación y control de cuarentena.

## 6. Prohibición de carga completa accidental

`db/sql/50_carga_core/090_ejecutar.sql` está bloqueado durante la migración incremental. Solo se podrá ejecutar cuando las 23 tablas tengan cierre en el ledger y exista una autorización técnica explícita en la sesión:

```sql
SET aquanqa.allow_full_core = 'on';
```

La carga completa no es el mecanismo normal de avance; el mecanismo normal son los scripts controlados por tabla o bloque.

## 7. Comandos autorizados

Antes de trabajar:

```powershell
node scripts/run.mjs preflight --database aquanqa_migracion
```

Para una tabla o bloque controlado, se debe usar el script específico y luego revisar:

```powershell
node scripts/run.mjs psql -d aquanqa_migracion -c "SELECT * FROM raw.v_migracion_resumen"
node scripts/run.mjs psql -d aquanqa_migracion -c "SELECT * FROM raw.v_migracion_tablas ORDER BY tabla_raw"
```

Si el preflight falla, la causa debe corregirse antes de ejecutar otra carga.

## 8. Estado inicial de esta ejecución

- Plan Access: 23 tablas.
- Snapshot Access publicado: `source_snapshot_id = 1`, campaña `C2026`.
- `M_Lotes`: cerrada correctamente como `migrada`.
- Pendientes: 22 tablas.
- La base `aquanqa` no forma parte del avance y debe seguir atendiendo al dashboard.
