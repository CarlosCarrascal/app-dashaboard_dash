# Cierre de la migración · nulos, cuarentena y qué queda pendiente

Este documento declara **hasta dónde llega la responsabilidad de ingeniería** en la migración de
`BD_AQUANQA_26.accdb` a PostgreSQL, y qué queda abierto esperando una decisión que no es técnica.

Existe porque "la migración terminó" no es una afirmación que se pueda hacer sin definir qué
significa. Aquí se define: **ninguna fila del origen se perdió sin registro, ninguna clave
foránea de un hecho quedó nula, y toda fila apartada tiene un motivo tipificado dentro de su
umbral previsto.** Lo que no cierra ingeniería —porque no le corresponde— queda listado en §3
con su dueño.

---

## 1 · Evidencia de cierre técnico

Reproducible en cualquier momento con `npm run validate` (contrato) y consultando `qua.v_resumen`.

### 1.1 · Contrato de aceptación

`db/sql/90_checks/` compara la base contra las cifras de control publicadas en la auditoría.
Última ejecución:

| | Resultado |
|---|---|
| Comprobaciones **ok** | 39 |
| Comprobaciones **FALLA** | 3 |
| **error** (consulta que no corre) | 0 |
| Pruebas de funciones de normalización falladas | 0 |

Las 3 "FALLA" **no son defectos**: son las tres comprobaciones del grupo `core`, que existe
precisamente para registrar en qué difiere la base nueva del histórico de Access y por qué.
Confundir el grupo `core` con el grupo `reproducir` es el error que haría parecer que la
migración pierde datos (advertido en `db/sql/90_checks/010_contrato.sql:12-17`):

| Comprobación | Access | En core | Por qué difiere |
|---|---|---|---|
| `core.lotes` | 860 | 880 | El maestro vigente tiene 19 lotes más, y módulos nuevos M14–M24 (N-4). El 880 incluye la fila centinela |
| `core.fundos` | 4 | 7 | `Aqu Anqa 1` a `6` del maestro vigente, frente a los 4 nombres comerciales del origen (N-5). El 7 incluye la fila centinela |
| `core.modulos` | 23 | 30 | M01 a M04 pertenecen a dos fundos a la vez (N-4) |

Es decir: **las tres fallas son el maestro de lotes vigente siendo más completo que Access**,
que es el resultado buscado, no un fallo de carga.

### 1.2 · Nulos en claves foráneas de hechos

Cerrado por ADR-0005 (`docs/adr/0005-filas-centinela-sin-null-en-fk.md`). El inventario completo
de las 41 claves foráneas de `core` encontró 4 con nulos reales; las tres que estaban en tablas
de hechos ahora apuntan a una fila centinela `es_sentinel = true` ("Sin identificar") y sus
columnas son `NOT NULL` — la garantía la da el motor, no la disciplina de quien escriba:

| Comprobación del contrato | Valor | Significado |
|---|---|---|
| `cero.fk_nula_en_hechos` | 0 | Ninguna FK de un hecho es NULL |
| `cero.sentinel_duplicado` | 0 | Exactamente una fila centinela por dimensión |
| `core.forecast_campania_sentinel` | 624 | Filas cuyo módulo no resolvía. Antes NULL **y sin registrar en cuarentena** |
| `core.forecast_semanal_sentinel` | 23 | Antes NULL **y duplicadas en cuarentena a la vez** |
| `core.cosecha_sentinel` | 4 | Solo existen en `H01_ProdHistorica`, que nunca tuvo columna de variedad |

Las columnas que siguen aceptando NULL en `core` lo hacen por una razón distinta y legítima:
**el origen no midió ese dato**. `flores.cuajo`, `packing.acidez`, `poda.fecha_inicio` y
similares no son fallos de carga — forzarles un valor inventaría información que nadie capturó.
La única excepción documentada es `fundo_alias.fundo_id` (7 de 23 nulos): esa tabla existe para
registrar alias que **no** determinan un fundo físico, y la columna `ambiguo` ya gobierna ese
caso.

### 1.3 · Cuarentena

**19.029 filas** apartadas, en **11 motivos**, **0 alertas activas** (`qua.v_alertas` vacío) y
**0 filas sin motivo**. Todas por debajo de su umbral previsto en `qua.umbral`:

| Motivo | Hallazgo | Filas | Tope |
|---|---|---:|---:|
| `DUPLICADO_EXACTO` | H-03 | 14.660 | 24.000 |
| `TIMESTAMP_DUPLICADO` | H-08 | 2.079 | 2.500 |
| `CONFLICTO_DIAMETRO_RAMA` | N-1 | 781 | 5.000 |
| `LOTE_INEXISTENTE` | N-3 | 728 | 900 |
| `MODULO_INEXISTENTE` | N-15 | 624 | 700 |
| `CLAVE_NATURAL_REPETIDA` | N-9 | 116 | 1.000 |
| `DIAMETRO_FUERA_DE_RANGO` | N-12 | 24 | 60 |
| `EVALUADOR_SIN_MAESTRO` | H-09 | 6 | 10 |
| `SIN_IDENTIFICADORES` | H-06 | 5 | 10 |
| `CONTEO_NEGATIVO` | N-12 | 4 | 10 |
| `MERCADO_INVALIDO` | N-2 | 2 | 45.000 |

Cada fila conserva su contenido íntegro en `jsonb`, de forma que si una decisión de negocio
determina que era válida se puede reprocesar sin volver al `.accdb`.

**Cuarentena no significa "dato perdido"** — significa "dato que no entró en `core` con su
razón registrada". Hay dos comportamientos distintos según el motivo, y conviene no confundirlos:

- **Apartada de `core`**: la fila no está en las tablas operativas (`SIN_IDENTIFICADORES`,
  `DUPLICADO_EXACTO`, `LOTE_INEXISTENTE` en evaluaciones y cosecha…).
- **Cargada y marcada**: la fila **sí** está en `core`, pero con una anotación —
  `DIAMETRO_FUERA_DE_RANGO` carga con `sospechoso = true`; `MODULO_INEXISTENTE` y las 23 de
  `forecast_semanal` cargan apuntando al centinela; `MERCADO_INVALIDO` carga con el mercado
  marcado. Se registran en cuarentena para que conste el problema, no para excluirlas.

---

## 2 · Qué se considera "migrado con éxito"

La migración está cerrada desde ingeniería cuando las **cinco** condiciones se cumplen a la vez:

1. ✅ El contrato de aceptación corre sin errores y sus únicas fallas son las del grupo `core`,
   con su nota explicativa.
2. ✅ `cero.fk_nula_en_hechos = 0` — ninguna clave foránea de un hecho quedó nula.
3. ✅ Ningún motivo de cuarentena excede su umbral (`qua.v_alertas` vacío).
4. ✅ Ninguna fila apartada sin motivo (`core.cuarentena = 0` en el contrato).
5. ⚠️ **Cada columna de Access está localizada en `core` o su ausencia está justificada.**

> La auditoría de mapeo columna por columna
> ([`../modelo/01_mapeo_access_core.md`](../modelo/01_mapeo_access_core.md), 2026-08-05) cubrió
> las 235 columnas del origen y encontró siete hallazgos nuevos (N-16 … N-22). Los cuatro que
> dependían solo de ingeniería **ya están corregidos**: N-16 (`core.packing.peso_kg` sumaba el
> total del grupo repetido por fila e inflaba los kilos ~24 veces; ahora es sumable y
> `peso_kg_lote` documenta el total aparte), N-17 (la hora de captura de estados, antes
> descartada por perder su encabezado, carga en `core.estados.hora`), N-19 (390 programas de
> packing rescatados de la columna equivocada) y N-22 (el comentario obsoleto de N-9).
> `core.packing.peso_kg` ya puede usarse en medidas de Power BI.
>
> El punto 5 sigue en ⚠️ solo por dos hallazgos de documentación/decisión, ya trasladados a la
> tabla de §3: **N-18** (el turno se descarta en cinco tablas sin que nadie haya comprobado si
> es derivable del lote) y **N-21** (seis columnas de packing sin significado documentado).
> Ninguno bloquea el cierre técnico ni el uso de `core`.

Access queda como **archivo histórico de solo lectura**. No se apaga hasta que los flujos de
captura que hoy lo alimentan tengan reemplazo (ver `docs/adr/0006-*`).

---

## 3 · Lo que ingeniería no puede cerrar

Siete asuntos siguen abiertos. Ninguno bloquea el uso de la base: D-1, D-2, N-12, N-14 y la
discrepancia H00/H01 están implementados con un supuesto explícito y reversible; N-18 y N-21 son
columnas que hoy no se cargan en absoluto, pendientes de que su dueño confirme si hace falta
hacerlo. Lo que falta en todos los casos es la confirmación de quien tiene la autoridad de
negocio para fijarlos.

### D-1 · Qué kilos compara `R0902_Forecast_Sem_vs_Camp` · **Planeamiento**

- **Estado**: implementado con `[KG Exp]`, por el precedente de `R0801_ResCampaña`.
- **Reversible con**: un `UPDATE` en `core.config_decision`. No requiere recarga.
- **Fuente**: `docs/historico-access/05_ADDENDA_TECNICA.md` §4 (tabla de decisiones), y
  `docs/historico-access/03_GUIA_REPORTES.md`.

### D-2 · La regla de asignación de campaña · **Planeamiento**

- **Estado**: la pregunta original ("fechas de corte") estaba mal planteada — las campañas se
  solapan y una fecha no determina la campaña (N-11). Lo que hace falta confirmar es la **regla
  de asignación por poda**. Hoy se registra como `campania.origen_fechas = 'derivado'`.
- **Fuente**: `docs/historico-access/05_ADDENDA_TECNICA.md` N-11 y §4.

### N-12 · 29 ramas y 3 bayas con diámetros físicamente imposibles · **Agronomía**

- **Estado**: se cargan igual (excluirlas rompería las cifras de control de la auditoría), pero
  quedan marcadas `sospechoso = true` y en cuarentena con motivo `DIAMETRO_FUERA_DE_RANGO`.
- **Qué decidir**: si son decimales perdidos (el patrón lo sugiere: hasta 8.789 mm en rama y
  13.381 mm en baya) y hay que corregirlos, o si se descartan. Excluirlas bajaría la media de
  rama de 10,89 a 10,62 y la de baya de 19,89 a 16,34 — por eso no se hace sin criterio.
- **Fuente**: `docs/historico-access/05_ADDENDA_TECNICA.md` N-12; umbral en
  `db/sql/40_qua/010_cuarentena.sql`.

### N-14 · 276 + 90 registros de cosecha de lotes retirados del maestro · **Agronomía**

- **Estado**: en cuarentena con motivo `LOTE_INEXISTENTE`. Son cosecha real (M04/L078-L080 y
  similares) de lotes que ya no figuran en el maestro vigente.
- **Qué decidir**: si esos lotes deben volver al maestro como históricos, o si su cosecha se
  reasigna, o si se acepta que queden fuera de `core`.
- **Fuente**: `docs/historico-access/05_ADDENDA_TECNICA.md` N-14, consecuencia 3.

### N-18 · El turno se descarta en cinco tablas del origen · **sin dueño asignado**

- **Estado**: `H01`, `E05`, `M_Poda`, `M_nMuestra` y `R09` no traen turno a `core`, mientras que
  `R08` sí lo persiste. Nada se pierde en `qua` porque no es un descarte con motivo: es una
  columna que nunca se leyó. Y en dos de los cinco casos (`M_Poda`, `M_nMuestra`, `R09`) ni
  siquiera llega a `stg` — se descarta un paso antes de lo que se pensaba, al construir la
  vista, así que hoy no hay ningún valor con el que comparar.
- **Por qué el fix no es automático**: para las dos tablas donde el turno sí sobrevive hasta
  `stg` (`H01`, `E05`), comparar contra `core.lote.turno_id` (el turno resuelto por lote, del
  maestro vigente) da resultados distintos:
  - `H01`: 30.536/30.536 filas coinciden (100%). Ahí sí sería seguro derivar de lote.
  - `E05`: 3.788/3.889 coinciden (97,4%); las 101 que no coinciden son **siempre el mismo par**,
    turno `T09` en el origen contra `T11` en el maestro. No es ruido aleatorio — es un
    desacuerdo sistemático entre una fuente y otra para un grupo de lotes concreto.

  Escribir "turno = turno del lote" sin decidir cuál de las dos fuentes vale para esos 101
  casos repetiría exactamente el patrón que esta migración corrige en otros hallazgos (H-01,
  H-07): confiar en un join sin verificarlo primero. Puede ser que el maestro vigente
  reasignara esos lotes de `T09` a `T11` después de que se capturaran esas evaluaciones —en
  cuyo caso derivar de lote sería *incorrecto* para esas filas históricas, no solo redundante—,
  o que sea un error de captura en E05. Sin esa decisión, "derivar de lote" arriesga
  reemplazar un dato real por uno equivocado en el 2,6% de los casos, con la apariencia de
  estar corregido.
- **Qué decidir**: (1) para `E05`, cuál de las dos fuentes vale para los 101 casos T09/T11 —o si
  ambos turnos son válidos porque el lote cambió de turno entre campañas—; (2) si vale la pena
  restaurar el turno en la vista de `stg` de `M_Poda`, `M_nMuestra` y `R09` solo para poder
  hacer la misma comprobación ahí, dado que hoy no hay nada que comparar.
- **Fuente**: `docs/historico-access/05_ADDENDA_TECNICA.md` N-18.

### N-21 · Seis campos de packing (Elifab) sin significado documentado · **Operaciones de packing**

- **Estado**: `ENSAYO`, `S26`, `S271`, `Packet`, `Clasificación` y `ACDT 2` se descartaron por
  parecer duplicados. La auditoría de mapeo comprobó que **no lo son** (N-21): tienen valores
  propios que no se derivan de ninguna otra columna.
- **Qué decidir**: qué representa cada uno. Si son operativamente útiles, se cargan; si no, se
  documenta el descarte con su motivo. Hoy no están ni cargados ni justificados.

### Las 105 filas de cosecha con kilos discrepantes entre H00 y H01 · **Agronomía**

- **Estado**: conservadas en `core.cosecha`, con `kg` (de H00, por convención) y `kg_h01` en
  paralelo. Son 105 de 30.532 filas presentes en ambas fuentes (0,34 %).
- **Qué decidir**: cuál de las dos cifras vale cuando difieren. Ninguna se ha perdido.

**Cerradas por los datos, ya sin pregunta pendiente**: D-3 (H00 y H01 contienen la misma
cosecha, 0,01 kg de diferencia — N-14), D-4 (el maestro vigente sustituye el vocabulario A —
N-5), D-5 (confirmado obsoleto).

---

## 4 · Política de retención de `qua.rechazos`

- **Permanencia**: `qua.rechazos` es **archivo histórico permanente**. No se purga ni vence.
  Es el registro de que nada se descartó en silencio, y ese registro no caduca.
- **Reproceso**: a demanda, solo cuando llega una decisión de negocio de §3. No hay reproceso
  automático ni periódico. El procedimiento es el del runbook de cambio de esquema
  (`03-cambiar-el-esquema.md`): ajustar la regla, recargar, correr el contrato.
- **Idempotencia**: cada `sp_cargar_*` vacía su propio destino antes de recargar, así que
  `qua.rechazos` se reconstruye completo en cada corrida de `npm run build`. Las filas no se
  acumulan entre corridas.
- **Si un umbral se excede** en una carga futura: `qua.v_alertas` devuelve filas y el informe lo
  marca `REVISAR`. Eso **no** es un error de la migración — es señal de que apareció un caso
  que la auditoría no cubría, y hay que mirarlo antes de dar la carga por buena. Un umbral se
  sube solo con la explicación de por qué, en el mismo commit.

---

## 5 · Aprobación

El cierre técnico (§1 y §2) lo verifica cualquiera ejecutando `npm run validate`: no depende de
la palabra de nadie.

El cierre **funcional** —declarar que la base sustituye a Access para efectos operativos— lo
aprueba el responsable de la plataforma de datos, y requiere que las cuatro decisiones de §3
estén respondidas o aceptadas explícitamente como supuestos vigentes. Mientras no lo estén, la
base es utilizable pero esos cuatro puntos siguen siendo supuestos de ingeniería, no acuerdos
del negocio.
