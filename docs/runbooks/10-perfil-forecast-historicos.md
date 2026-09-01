# Perfilado del histórico de forecast R08/R09

**Fecha:** 2026-08-30  
**Base:** aquanqa_migracion  
**Snapshot Access publicado:** 4 (BD_AQUANQA_26(1).accdb)  
**Decisión actual:** las tres fuentes permanecen raw_only.

El perfilado es reproducible y de solo lectura:

    node scripts/run.mjs psql -d aquanqa_migracion -f db/tools/perfil_forecast_historicos.sql

## Fuentes revisadas

| Fuente | Filas | Columnas Access | Versiones | Cobertura observada |
|---|---:|---:|---:|---|
| R08_Forecast_Campaña_24 | 6.932 | 6 | 13 | Año 2023–2026, semanas 1–52 |
| R08_Forecast_Campaña_25 | 75.383 | 13 | 13 | C2024/C2025, año 2025–2027, semanas 1–53 |
| R09_Forecast_Semanal_25 | 67.026 | 15 | 62 | C2024/C2025, fechas 2024-12-30–2025-12-13 |

Ninguna de las tres fuentes tiene índice ni clave primaria registrada en el catálogo
físico de Access.

## Controles de calidad

- Las tres fuentes llegaron completas al snapshot y no tienen campos obligatorios
  vacíos ni números inválidos.
- No hay valores negativos en las métricas revisadas.
- R08 campaña 24 tiene una clave candidata única:
  versión + FundoPPto + módulo + año + semana.
- R09 semanal 25 tiene una clave única si se conservan las fechas:
  versión + campaña + fundo + módulo + turno + lote + semana + fecha anterior +
  fecha de cosecha. La fecha anterior no es decorativa: al quitar las fechas
  aparecen 49 grupos repetidos.
- En R09, la semana declarada coincide con la semana ISO de fecha de cosecha y
  fecha anterior no es posterior a fecha de cosecha.

## Hallazgos críticos de R08 campaña 25

R08 campaña 25 no tiene un grano único suficientemente explicado:

- La clave candidata con todos los campos de identificación disponibles deja
  7.311 filas excedentes.
- Hay 9 huellas exactamente repetidas; se conservaron en raw y no se eliminaron.
- La versión Proy.Jul25 contiene 7.794 filas con PlnFundo, PlntMod, Turno,
  Plantas, desc y frtTotal vacíos. Varias filas comparten el mismo fundo,
  módulo, campaña, año y semana, pero tienen diferentes valores de KG.
- No es seguro sumar, deduplicar o llevar esas filas a un hecho core sin
  descubrir el identificador que falta.

## Identidad de ubicación

R08 campaña 24 usa FundoPPto como único campo de ubicación y mezcla niveles:
empresa, fundo físico y aliases comerciales. Solo Aqu Anqa - Arena Azul coincide
directamente con un alias físico aprobado; Aqu Anqa y Aqu Anqa II son nombres de
empresa, y Aqu Anqa II - Amp, Sta. Teresa, Vivadis y Aqu Anqa III no tienen un
alias exacto aprobado.

R08 campaña 25 utiliza Aqu Anqa I, II, III, IV, V y VI. La nomenclatura romana
no se convierte automáticamente a los aliases numéricos del maestro vigente.
Aqu Anqa II coincide solo como empresa, no como fundo físico.

R09 semanal 25 resuelve 66.965 de 67.026 filas contra el maestro de lotes vigente.
Las 61 no resueltas son:

| Fundo | Módulo | Lote | Filas |
|---|---|---|---:|
| Aqu Anqa - Arena Azul | M04 | L078 | 24 |
| Aqu Anqa - Arena Azul | M04 | L079 | 23 |
| Aqu Anqa - Arena Azul | M04 | L080 | 14 |

No se crearon aliases ni lotes ficticios para cubrirlas.

## Versionado y relación con lo vigente

R09 histórico contiene 67 pares distintos de versión + campaña, mientras que el
R09 vigente contiene 36. No hay pares versión + campaña comunes entre ambos
conjuntos; por tanto, el histórico es complementario al conjunto vigente y no
debe tratarse como una simple recarga de la tabla actual.

Sin embargo, 31 pares históricos reutilizan códigos que ya existen en
core.m_version_forecast, correspondientes a 29 códigos. Ese catálogo actual
identifica una versión solo por sistema + código y no por campaña/año. Si se
cargara el histórico directamente, podría reutilizarse el version_id de otra
campaña.

Además, R09 histórico contiene grafías distintas para S30_v4/S30_V4 y
S44_v2/S44_V2. No comparten claves de datos, por lo que no se deben fusionar
solo pasando el texto a minúsculas.

R08 campaña 24 no trae campaña explícita. R08 campaña 25 sí la trae, pero su
estructura y nombres de versión no son equivalentes uno a uno con R08 vigente.

## Decisión

Las tres fuentes quedan completas y trazables en raw_only. No se modifica core,
stg ni la base operativa del dashboard.

Antes de una promoción se necesita:

1. aprobar una clave de versión que incluya el contexto temporal/campaña cuando
   el código se reutilice;
2. explicar el grano faltante de R08 campaña 25, especialmente Proy.Jul25;
3. definir aliases históricos de ubicación con el responsable del maestro;
4. confirmar si R08 campaña 24 se conservará como histórico auxiliar por no traer
   campaña o si existe una regla para derivarla;
5. decidir si los históricos deben vivir como archivo de forecast separado,
   evitando alterar los hechos vigentes del dashboard.
