# Contrato completo Access → `raw`

## Propósito

La base `aquanqa_migracion` recibe snapshots inmutables de las tablas físicas de Access. La
regla es conservar en `raw` todas las columnas físicas de las tablas de negocio, aunque todavía
no se conozca su semántica o no tengan un destino en `stg`/`core`.

Que una columna esté en `raw` no significa que deba convertirse automáticamente en una columna
de `core`. `raw` responde a trazabilidad del origen; `stg` responde a normalización; `core`
responde a un modelo de negocio aprobado por grano, claves y relaciones.

## Qué ocurrió con la omisión

El contrato inicial se construyó como una selección de campos considerados necesarios para el
modelo. El extractor solo generaba las columnas incluidas en `catalogo.py` y no existía una
comprobación que comparara ese catálogo con todas las columnas físicas de Access. Por eso algunos
campos válidos podían desaparecer sin que la extracción fallara.

El contrato v5 corrige esa frontera. En la copia de Access revisada se incorporaron a `raw`:

| Tabla Access | Columnas conservadas |
| --- | --- |
| `E02_ConteoFlores` | `YMuertas`, `BrtTiernos`, `Des1` |
| `E05_DiametrosBayas` | `Fundo` |
| `H02_BDElifab` | `Operador`, `ACDTChina` |
| `M_Evaluadores` | `TallaPolo` |
| `M_Time` | `nMesSem`, `Feriados`, `CampProAra`, `Trimestre` |

No se les asigna todavía una regla de negocio inventada. Por ejemplo, `YMuertas` queda disponible
para la aplicación y para un futuro modelo de fenología, mientras que `BrtTiernos` no se mezcla
automáticamente con `E04_Brotes` porque su grano y definición podrían ser distintos.

## Guardas obligatorias

Antes de escribir cualquier CSV, el extractor inspecciona el archivo Access y exige que:

1. cada tabla física de negocio esté en el catálogo;
2. cada columna física esté mapeada a `raw`, o aparezca en una exclusión explícita y justificada;
3. el manifiesto registre tablas, columnas, versión del contrato y columnas no mapeadas;
4. una nueva versión del catálogo no reutilice un snapshot generado con un contrato anterior.

Si Access trae una tabla o columna nueva, la extracción se detiene. No se continúa con una copia
parcial ni se oculta el cambio.

## Flujo por capas

```text
Access / Excel de contraste
          │ extracción solo lectura + SHA + contrato físico
          ▼
raw: snapshot completo e inmutable
          │ revisión de grano, claves, relaciones y dominios
          ▼
stg: normalización técnica
          │ reglas de negocio aprobadas y conciliación
          ▼
core: entidades y hechos con significado estable
          │
          ├── API / aplicación móvil (posterior)
          └── reporting / Power BI (posterior)
```

El Excel `M_Lotes.xlsx` permanece como fuente independiente de contraste. No se mezcla
automáticamente con Access ni puede sobrescribir `M_Lotes` sin una decisión explícita.

## Estado de esta corrección

- El snapshot `5` conserva la línea base del Access anterior, ya reextraído con el contrato
  v5; el ledger de publicaciones lo mantiene como antecedente histórico.
- El snapshot `4` corresponde al Access nuevo y quedó publicado como vigente después de la
  reconstrucción completa autorizada.
- El run `8` cerró las 23 fuentes: `18` publicadas en `core` y `5` como `raw_only`, con los
  bloques `B01` a `B05` y la auditoría final superados.
- El perfilado del snapshot `4` guardó evidencia para 23 tablas y 24 relaciones: 7 validadas,
  7 con huérfanos y 10 no evaluables; ninguna relación se aprobó ni se convirtió en FK de forma
  automática.
- La comparación contra la línea base actual detecta únicamente `E02_ConteoFlores` (+2.839 filas)
  y `E03_ConteoEstados` (+5/-5). Las columnas nuevas no se presentan como cambios de negocio por
  sí mismas.
- `raw.source_table_delta.snapshot_anterior_id` identifica la publicación usada para calcular
  cada delta; si un delta histórico fue generado antes de existir ese campo, el orquestador lo
  recalcula contra la publicación vigente.
- La base `aquanqa`, consumida por el dashboard existente, no forma parte de esta carga y permanece
  operativa.

## Regla para cada actualización periódica

1. Extraer el Access completo y validar el contrato.
2. Reutilizar el snapshot si el SHA y el contrato son idénticos; no duplicar filas.
3. Registrar una versión nueva si cambió el archivo.
4. Validar y comparar contra el snapshot publicado.
5. Promover solo después de revisar los cambios.
6. Ejecutar únicamente los bloques afectados y cerrar conteos, duplicados, huérfanos, rechazos y
   linaje.

La promoción a `stg`/`core` es una decisión posterior a la captura completa de `raw`; nunca es un
requisito para conservar un dato de Access.
