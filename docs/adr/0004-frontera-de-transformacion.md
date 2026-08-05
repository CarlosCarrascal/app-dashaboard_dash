# ADR-0004 · Cada transformación vive en una sola capa

- **Estado:** aceptado
- **Fecha:** 2026-08-03
- **Origen:** hallazgos B-2, B-3, B-4 y B-6 de `../historico-access/05_ADDENDA_TECNICA.md`

## Contexto

Hoy la misma clase de lógica está repartida en cuatro sitios, y en tres de ellos está mal:

| Dónde | Qué hace | Estado |
|---|---|---|
| SQL de Access | joins de fundo, agregaciones, despivotes con `UNION ALL` | 6 consultas rotas, 1 inflada ×54 |
| Power Query | partir `Fundo_pptom5`, 5 `Table.ReplaceValue`, `Table.Group` de `RESUM_*` | colapsa dos fundos distintos |
| DAX (columnas calculadas) | `SWITCH` que asigna fundo por módulo | asigna mal M01–M04, deja M17–M24 en blanco |
| DAX (tablas calculadas) | dimensiones con `SUMMARIZECOLUMNS` sobre los hechos | `LOTE` sin módulo mezcla lotes homónimos |

Ninguno de esos errores es por descuido: son la consecuencia previsible de tener que resolver en
la capa de presentación un problema que el origen no resolvía. Mientras la frontera no esté
declarada, el atajo siempre gana, porque arreglarlo en Power Query es más rápido que arreglarlo
en el modelo.

## Decisión

| Capa | Le corresponde | Le está prohibido |
|---|---|---|
| `raw` | copiar el origen tal cual | interpretar, tipar, corregir |
| `stg` | normalizar códigos, resolver identidad, tipar | inventar filas, descartar en silencio |
| `qua` | conservar lo rechazado con su motivo y su fila íntegra | — |
| `core` | el modelo operativo, sus claves y sus restricciones | agregar para reportes |
| `dim` / `fact` | grano dimensional y reglas de negocio agregadas | limpiar datos: ya llegan limpios |
| `reporting` | contratos estables de salida | filtros fijos de campaña |
| **Power BI** | **medidas, formato, visualización** | **dimensiones calculadas, mapeos de negocio, limpieza de texto** |

Reglas operativas que se derivan:

1. **Ninguna dimensión se construye con `SUMMARIZECOLUMNS`.** Toda dimensión viene de
   `reporting` con su clave real. Si a Power BI le falta una dimensión, se añade en SQL.
2. **Ningún mapeo de negocio en DAX ni en M.** El mapa módulo → fundo → empresa vive en
   `core.modulo` y `core.fundo`; el de alias en `core.fundo_alias`.
3. **Los atributos no se suman desde el hecho.** `KG/HA` toma el área de la dimensión de lote.
   Es el defecto B-4.
4. **Toda agregación reutilizable es una vista.** `RESUM_FLORES`, `RESUM_FRUTOS` y
   `TAB RESUM_FL` bajan de Power Query a `reporting`; `TAB RESUM_FL` en particular es una regla
   de validación —jornadas con flores contadas y sin frutos— que hoy solo conoce un archivo
   `.pbix`.
5. **La inteligencia de tiempo automática se desactiva.** Hay `dim_tiempo`; las 10 tablas
   `LocalDateTable_*` que Power BI genera solo añaden peso y ambigüedad.

## Consecuencias

- Un cambio de regla se hace una vez. Hoy corregir el mapeo de fundo exige editar Power Query,
  dos columnas DAX y el SQL de Access, sin garantía de que queden iguales.
- El modelo semántico se vuelve delgado y revisable: `bi/semantic-model/` versiona TMDL, y un
  diff muestra si alguien volvió a meter una dimensión calculada.
- Coste real: añadir una dimensión pasa a requerir una migración de SQL en lugar de dos clics.
  Es deliberado — ese roce es lo que mantiene la lógica en su sitio.
- Hay una excepción explícita: **las medidas siguen en DAX**. Son presentación, se benefician del
  contexto de filtro y no tiene sentido materializarlas.

## Alternativas descartadas

- **Dejar el modelo de Power BI como está y solo cambiar el origen.** Más rápido y sin riesgo
  visual, pero conserva los cuatro defectos en los tableros de gerencia y desperdicia la única
  oportunidad natural de corregirlos.
- **Mover todas las medidas a vistas SQL.** Pierde el contexto de filtro, multiplica las vistas y
  obliga a una migración por cada indicador nuevo.
