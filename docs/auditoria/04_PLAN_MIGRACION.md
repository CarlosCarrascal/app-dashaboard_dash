# Plan de migración a PostgreSQL · BD_AQUANQA_26

**Fecha:** 2026-08-02
**Para:** TI / equipo de datos
**Origen:** `BD_AQUANQA_26.accdb` — 18 tablas, 40 consultas, 683.180 filas
**Destino:** PostgreSQL 15+

---

## 1 · Principio rector

**Se migra el modelo corregido, no el modelo actual.**

Los tres hallazgos críticos de `01_AUDITORIA.md` comparten una raíz común: **el motor nunca
tuvo permiso para rechazar un dato inválido**. No hay claves foráneas, las claves primarias
son incorrectas y ningún índice único impidió las recargas duplicadas.

Replicar la estructura tal cual sería conservar exactamente el defecto que garantiza que
todos los demás vuelvan a aparecer. Este plan declara las restricciones que Access no tenía.

### Las tres reglas del plan

**1 · Nada se descarta en silencio.** Toda fila que viole una restricción va a una tabla de
cuarentena con el motivo. No se pierde información: se aparta para revisión.

**2 · Los contratos que consume Power BI se preservan.** Las consultas validas se
expondran como vistas en `reporting`, conservando nombres y columnas compatibles.
Las consultas rotas no se copiaran ciegamente: se reconstruira su salida despues de
corregir la causa.

**3 · Ningún cambio de interpretación sin decisión del negocio.** Los defectos con
corrección técnica evidente se corrigen; los que dependen de una definición de negocio
quedan bloqueados hasta que se defina (§8).

---

## 2 · Arquitectura destino · PostgreSQL para app y BI

### Estructura de esquemas

```
aquanqa
├── raw.*          copia intacta del origen Access
├── stg.*          staging de carga y normalizacion
├── core.*         modelo normalizado de la aplicacion
├── qua.*          cuarentena y trazabilidad de rechazos
└── reporting.*    vistas/marts dimensionales para Power BI
```

La separacion importa: `raw` conserva el origen, `stg` permite perfilarlo, `qua` conserva lo
que no paso las reglas, `core` es la fuente operativa de la aplicacion y `reporting` es la
interfaz estable para Power BI. Access no sera la fuente operativa despues del corte.

`core` sera normalizado y lo administrara el backend Next.js mediante Drizzle y migraciones
versionadas. `reporting` tendra dimensiones, hechos, vistas y, cuando haga falta, vistas
materializadas. Las transformaciones de calidad y negocio no deben repetirse en Power BI,
el backend y Access.

### 2.1 · Regla para consolidar tablas

No se consolidan tablas solo porque tengan nombres parecidos. La decision se toma por
**grano**, ciclo de vida, columnas obligatorias y reglas de escritura:

| Grupo de origen | Tratamiento en `core` | Motivo |
|---|---|---|
| `H00` + `H01` | una entidad de cosecha con trazabilidad de origen | representan el mismo hecho; sus diferencias se auditan |
| `E01` ramas | evaluacion tipada de ramas | tiene grano planta/fecha |
| `E02` flores + `E03` estados | cabecera comun de evaluacion y detalles tipados | comparten evaluacion, pero no la misma medida |
| `E04` brotes + `E05` bayas | hechos de medicion separados | distinto grano y ciclo de captura |
| `R08` + `R09` | hechos de forecast separados | distinto horizonte, grano y version |
| `H05` clima | hecho por timestamp | no debe mezclarse con evaluaciones agronomicas |

La app escribira en `core`; Power BI consumira `reporting`. No se creara una tabla generica
de atributos sin tipo para meter todas las evaluaciones, porque ocultaria el grano y
facilitaria volver a inflar cifras.

### 2.2 · Frontera Drizzle / SQL / Power BI

| Capa | Responsable | Regla |
|---|---|---|
| `core` | Drizzle + migraciones | tablas, relaciones, claves, restricciones |
| `raw`, `stg`, `qua` | SQL/script de carga | copia, perfilado, lotes y rechazos |
| `reporting` | SQL/Drizzle views | contratos de salida para Power BI |
| Power BI | modelo semantico | medidas y visualizaciones, no limpieza estructural |

### 2.3 · Core minimo para la aplicacion

El modelo de la aplicacion no sera una copia directa de las 18 tablas de Access. El minimo
normalizado queda organizado asi:

| Dominio | Tablas principales |
|---|---|
| Identidad | `core.evaluador`, `core.usuario`, `core.rol` |
| Ubicacion | `core.empresa`, `core.fundo`, `core.fundo_alias`, `core.modulo`, `core.lote` |
| Tiempo | `core.campania`, `core.poda`, `core.calendario` |
| Operacion | `core.cosecha`, `core.clima`, `core.forecast` |
| Evaluaciones | `core.evaluacion`, `core.ramas`, `core.flores`, `core.estados`, `core.brotes`, `core.bayas` |

`core.usuario` no reemplaza a `core.evaluador`: un evaluador es una persona del dominio y
un usuario es una identidad de acceso. El DNI puede ser un atributo unico del evaluador,
pero no se almacenara como contrasena.

### Dimensiones

| Tabla | Origen | Filas esperadas | Resuelve |
|---|---|---|---|
| `core.empresa` / `dim.fundo` | maestro actualizado | empresa + fundos fisicos | H-01 |
| `core.fundo_alias` / `dim.fundo_alias` | maestro actualizado + legado | alias historicos | **H-01** |
| `dim.modulo` | `M_Lotes` agregada | 23 | |
| `dim.lote` | maestro actualizado | lote por empresa/fundo/modulo | |
| `dim.tiempo` | `M_Time` + derivadas | 2.189 | **H-04 caso 5** |
| `dim.evaluador` | `M_Evaluadores` | 31 | **H-09** |
| `dim.variedad` | derivada de `M_Lotes` | ~5 | |
| `dim.calibre` | derivada de `H02` | ~10 | **H-10** |
| `dim.version_forecast` | derivada de `R08`/`R09` | ~61 | |

### Hechos de `reporting`

| Tabla | Origen | Filas esperadas | Corrección aplicada |
|---|---|---|---|
| `fact.ramas` | `E01_Ramas` | **71.095** | dedup H-03 (de 94.236) |
| `fact.flores` | `E02_ConteoFlores` | 43.490 | |
| `fact.estados` | `E03_ConteoEstados` | 18.714 | |
| `fact.brotes` | `E04_Brotes` | 3.385 | |
| `fact.diametro_baya` | `E05_DiametrosBayas` | 4.193 | se migra pese a no tener consumo |
| `fact.cosecha` | `H00` + `H01` | ~30.811 | **H-06, H-07** |
| `fact.packing` | `H02_BDElifab` | 117.536 | tipado H-10 |
| `fact.clima` | `H05_Clima` | **153.413** | dedup H-08 (de 155.588) |
| `fact.forecast_campana` | `R08` | 101.715 | |
| `fact.forecast_semanal` | `R09` | 48.368 | |
| `core.poda` | `M_Poda` | 2.159 | |
| `dim.muestra_requerida` | `M_nMuestra` | 681 | se migra pese a no tener consumo |
| `dim.equivalencia_elifab` | `M_EquivalenciaElifab` | 15 | |

**Se descarta una sola tabla:** `Errores de pegado` (0 filas, generada por Access).

---

## 3 · DDL comentado

El DDL de `dim`/`fact` de esta seccion corresponde a la capa `reporting`. El modelo
operativo `core` se declarara en Drizzle y sus migraciones; no se debe usar una dimension
de reporting como tabla de escritura de la aplicacion.

### 3.1 · Maestro de empresa, fundo fisico y alias · H-01

El maestro actualizado separa la razon social de la entidad fisica. El alias no es una
clave: solo sirve para resolver nombres de origen. La identidad se determina por empresa,
modulo y lote.

```sql
CREATE TABLE core.empresa (
    empresa_id smallint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nombre_canonico text NOT NULL UNIQUE,
    activo boolean NOT NULL DEFAULT true
);

CREATE TABLE core.fundo (
    fundo_id smallint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    empresa_id smallint NOT NULL REFERENCES core.empresa(empresa_id),
    codigo text NOT NULL,                  -- Aqu Anqa 1 ... Aqu Anqa 6
    alias_operativo text,
    activo boolean NOT NULL DEFAULT true,
    UNIQUE (empresa_id, codigo)
);

CREATE TABLE core.fundo_alias (
    alias text PRIMARY KEY,
    fundo_id smallint REFERENCES core.fundo(fundo_id),
    tipo text NOT NULL,                    -- empresa, fisico u operativo
    origen text NOT NULL                   -- Access, M_Lotes, R08, R09, etc.
);
```

`FundoPPto` se carga en `core.empresa`, `Fundo` en `core.fundo` y `Fundo_pptom5` en
`core.fundo_alias`/`alias_operativo`. No se cargaran como canonicos los mapeos antiguos de
`Ampliacion`, `Vivadis` y `Sta.Teresa` que este documento tenia por inferencia.

Los hechos historicos se resuelven mediante `empresa + modulo + lote`; los registros que no
encuentren correspondencia quedan en `qua` y no entran al modelo operativo.

### 3.2 · Dimensión de tiempo — resuelve H-04 caso 5

```sql
CREATE TABLE dim.tiempo (
    fecha              date PRIMARY KEY,
    semana             smallint NOT NULL,        -- M_Time.Sem
    mes                smallint NOT NULL,
    anio               smallint NOT NULL,
    trimestre          smallint NOT NULL,        -- NUEVO: faltaba (H-04 caso 5)
    sem_ev_conteo      smallint,                 -- M_Time.SEvConteo, nullable
    campana_productiva text,                     -- NUEVO: 'C2025' etc. (H-04 caso 5)
    mes_sem            text
);
```

`trimestre` es trivial de derivar. **`campana_productiva` requiere que Planeamiento defina
las fechas de corte de cada campaña** — decisión D-2 (§8). Sin ella,
`R0801_Forecast_Campaña_SemMes` no puede corregirse.

Se descarta `AQII` (100% nula).

**Dimensión de semana de evaluación** — evita la repetición de H-05:

```sql
-- Grano semanal explícito. Unir contra esto, NUNCA contra dim.tiempo por sem_ev_conteo.
CREATE TABLE dim.semana_evaluacion (
    anio          smallint NOT NULL,
    sem_ev_conteo smallint NOT NULL,
    fecha_inicio  date NOT NULL,
    fecha_fin     date NOT NULL,
    PRIMARY KEY (anio, sem_ev_conteo)
);
```

Existe precisamente para que ninguna consulta futura una una tabla semanal contra una tabla
de días.

### 3.3 · Lote y módulo

```sql
CREATE TABLE dim.modulo (
    modulo_id smallint PRIMARY KEY,
    fundo_id  smallint NOT NULL REFERENCES dim.fundo(fundo_id),
    codigo    text NOT NULL,
    UNIQUE (fundo_id, codigo)
);

CREATE TABLE dim.lote (
    lote_id     integer PRIMARY KEY,
    modulo_id   smallint NOT NULL REFERENCES dim.modulo(modulo_id),
    turno       text NOT NULL,
    codigo      text NOT NULL,
    variedad    text NOT NULL,
    area_ha     numeric(10,4) NOT NULL CHECK (area_ha > 0),
    n_plantas   integer NOT NULL CHECK (n_plantas > 0),
    fecha_siembra date,
    maceta      text,
    tipo_fibra  text,
    key_map     text,                      -- 53 nulos conocidos, se permite
    UNIQUE (modulo_id, codigo)
);
```

Se descartan `Moduloo` (typo que duplica `Modulo`) y `kk` (derivable de `key_map`).

La restriccion `UNIQUE (modulo_id, codigo)` es valida porque `modulo_id` ya pertenece a un
fundo fisico. La clave de negocio completa se audita contra
`(empresa_id, fundo_id, modulo_id, codigo)`; el conteo antiguo de 860/855 no se usa como
criterio del nuevo maestro. `L000` se conserva como codigo de origen y se marca para
trazabilidad, no se elimina silenciosamente.

### 3.4 · Hechos con las correcciones aplicadas

```sql
-- fact.ramas: la clave UNIQUE es la corrección de H-03
CREATE TABLE fact.ramas (
    ramas_id     bigserial PRIMARY KEY,
    lote_id      integer NOT NULL REFERENCES dim.lote(lote_id),
    evaluador_id smallint REFERENCES dim.evaluador(evaluador_id),
    fecha        date NOT NULL,
    cortina      smallint NOT NULL,
    hilera       smallint NOT NULL,
    planta       smallint NOT NULL,
    actividad    text,
    ramas_menor5 smallint,
    ramas_mayor5 smallint,
    ramas_total  smallint NOT NULL,
    diametro     numeric(6,3) NOT NULL,
    -- H-03: impide que una segunda carga duplique en silencio
    UNIQUE (lote_id, fecha, cortina, hilera, planta)
);

-- fact.brotes: la PK incluye fecha — corrige H-02
CREATE TABLE fact.brotes (
    brotes_id bigserial PRIMARY KEY,
    lote_id   integer NOT NULL REFERENCES dim.lote(lote_id),
    fecha     date NOT NULL,              -- ANTES NO ESTABA EN LA CLAVE
    piso      text NOT NULL,
    cortina   smallint NOT NULL,
    hilera    smallint NOT NULL,
    planta    smallint NOT NULL,
    brotes    smallint NOT NULL,
    -- Permite evaluar la misma planta en fechas distintas (H-02)
    UNIQUE (lote_id, fecha, piso, cortina, hilera, planta)
);

-- fact.estados: la clave NO incluye medidas — corrige H-02
CREATE TABLE fact.estados (
    estados_id bigserial PRIMARY KEY,
    lote_id    integer NOT NULL REFERENCES dim.lote(lote_id),
    fecha      date NOT NULL,
    cortina    smallint NOT NULL,
    hilera     smallint NOT NULL,
    planta     smallint NOT NULL,
    e1 smallint NOT NULL, e2 smallint NOT NULL, e3 smallint NOT NULL,
    e4 smallint NOT NULL, e5 smallint NOT NULL,
    -- 'Total' NO se almacena: se calcula. Elimina la inconsistencia de 2.430 frutos
    total smallint GENERATED ALWAYS AS (e1+e2+e3+e4+e5) STORED,
    UNIQUE (lote_id, fecha, cortina, hilera, planta)   -- sin E1 en la clave
);

-- fact.cosecha: NOT NULL en dimensiones — corrige H-06
CREATE TABLE fact.cosecha (
    cosecha_id bigserial PRIMARY KEY,
    lote_id    integer NOT NULL REFERENCES dim.lote(lote_id),
    fecha      date NOT NULL,             -- NOT NULL bloquea las filas de subtotal
    campana    text NOT NULL,
    kg         numeric(12,4) NOT NULL CHECK (kg >= 0),
    pana       smallint,
    peso_baya  numeric(8,4),
    origen     char(3) NOT NULL CHECK (origen IN ('H00','H01'))
);

-- fact.clima: UNIQUE en timestamp — corrige H-08
CREATE TABLE fact.clima (
    fecha_hora timestamp PRIMARY KEY,     -- la PK es la corrección
    temp numeric(6,2) NOT NULL,
    temp_alta numeric(6,2) NOT NULL,      -- corrige el typo 'TembAlta'
    temp_baja numeric(6,2) NOT NULL,
    humedad numeric(6,2) NOT NULL,
    lluvia numeric(8,3) NOT NULL,
    et_mm numeric(8,3),
    dg_calentamiento numeric(8,3),
    dg_enfriamiento numeric(8,3)
    -- resto de las 25 columnas
);
```

### 3.5 · Cuarentena

```sql
CREATE TABLE qua.rechazos (
    rechazo_id   bigserial PRIMARY KEY,
    tabla_origen text NOT NULL,
    motivo       text NOT NULL,     -- 'FK_LOTE_INEXISTENTE', 'DUPLICADO', 'FILA_SUBTOTAL'
    hallazgo     text,              -- 'H-01', 'H-03', 'H-06'...
    fila_json    jsonb NOT NULL,    -- la fila completa, para no perder nada
    cargado_en   timestamp NOT NULL DEFAULT now()
);
CREATE INDEX ON qua.rechazos (tabla_origen, motivo);
```

**Ninguna fila se descarta sin registro.** `fila_json` conserva el registro íntegro: si
Agronomía determina que una fila rechazada era válida, se puede reprocesar.

---

## 4 · Estrategia ETL

### 4.1 · Orden de carga

El orden no es arbitrario: cada paso depende de las FK del anterior.

```
1. dim.fundo  +  dim.fundo_alias      ← sin ellas nada resuelve el fundo
2. dim.tiempo  +  dim.semana_evaluacion
3. dim.modulo → dim.lote
4. dim.evaluador, dim.variedad, dim.calibre, dim.version_forecast
5. dim.poda, dim.muestra_requerida, dim.equivalencia_elifab
6. fact.*  (en cualquier orden; todas dependen solo de dimensiones)
```

### 4.2 · El patrón de resolución de fundo

Todo hecho pasa por el mismo paso. Es la aplicación práctica de la solución a H-01:

```sql
INSERT INTO fact.ramas (lote_id, fecha, cortina, hilera, planta, ...)
SELECT l.lote_id, s.fecha, s.cortina, s.hilera, s.planta, ...
FROM stg.e01_ramas s
JOIN dim.fundo_alias fa ON fa.alias = trim(s.fundo)   -- resuelve CUALQUIER vocabulario
JOIN dim.modulo m ON m.fundo_id = fa.fundo_id AND m.codigo = trim(s.modulo)
JOIN dim.lote   l ON l.modulo_id = m.modulo_id AND l.codigo = trim(s.lote)
ON CONFLICT (lote_id, fecha, cortina, hilera, planta) DO NOTHING;   -- dedup H-03
```

Dos cosas ocurren aquí:

1. **`JOIN dim.fundo_alias`** traduce `'Kawsay Allpa'` (vocabulario D) al mismo `fundo_id`
   que `'Aqu Anqa II - Kawsay Allpa'` (vocabulario C). El join que en Access **nunca
   acertaba** ahora siempre acierta.
2. **`ON CONFLICT ... DO NOTHING`** hace la deduplicación de H-03 en la propia carga:
   conserva la primera ocurrencia y descarta las 23.141 repetidas.

### 4.3 · Cuarentena de lo que no resuelve

El `JOIN` del paso anterior descarta silenciosamente lo que no encuentra lote. Eso no es
aceptable — hay que capturarlo:

```sql
INSERT INTO qua.rechazos (tabla_origen, motivo, hallazgo, fila_json)
SELECT 'E01_Ramas', 'FK_LOTE_INEXISTENTE', 'H-01', to_jsonb(s)
FROM stg.e01_ramas s
WHERE NOT EXISTS (
    SELECT 1 FROM dim.fundo_alias fa
    JOIN dim.modulo m ON m.fundo_id = fa.fundo_id AND m.codigo = trim(s.modulo)
    JOIN dim.lote   l ON l.modulo_id = m.modulo_id AND l.codigo = trim(s.lote)
    WHERE fa.alias = trim(s.fundo)
);
```

**Criterio de aceptación:** si esta consulta devuelve un número alto, `dim.fundo_alias` está
incompleta y hay que ampliarla — no forzar la carga.

### 4.4 · Filas de subtotal — H-06

```sql
INSERT INTO qua.rechazos (tabla_origen, motivo, hallazgo, fila_json)
SELECT 'H00_VolumenCampo', 'FILA_SUBTOTAL_SIN_IDENTIFICADORES', 'H-06', to_jsonb(s)
FROM stg.h00_volumencampo s
WHERE s.fundo IS NULL OR s.modulo IS NULL OR s.lote IS NULL OR s.fecha IS NULL;
```

Se esperan exactamente **3 filas** (1 de `H00`, 2 de `H01`) con **1.925.995 kg** en total.
Si aparecen más, hay filas basura no detectadas en la auditoría y debe revisarse antes de
continuar.

### 4.5 · Reconciliación H00 / H01 — H-07

`core.cosecha` unifica el hecho de negocio y conserva `origen` para saber de que tabla
proviene cada registro. Las tablas crudas H00 y H01 se mantienen separadas en `raw` para
trazabilidad.

La auditoria confirma que ambas representan la misma cosecha, pero H00 contiene todos los
registros de kilos en C2023/C2024 y H01 tiene 187 filas menos. Por ello, la referencia
tecnica para la medida de KG en `reporting` sera H00; los atributos adicionales de H01
(`Turno`, `Paña`, `Peso`, `nPlantas`) se conservaran cuando puedan reconciliarse. El grano
final de `core.cosecha` se fijara en F0 antes de crear la tabla canonica; no se hara un
`SELECT *` de dos fuentes con granos distintos.

La diferencia no se oculta: se registra en la reconciliacion H00/H01 y queda disponible
para auditoria.

La vista de reporting expondra una sola cosecha por grano canonico, con KG de referencia
de H00 y columnas H01 solo cuando la reconciliacion las pueda asociar. El detalle de
origen y las discrepancias permaneceran consultables desde `raw`/`qua`.

### 4.6 · Idempotencia

Toda carga debe poder repetirse sin duplicar. Tres mecanismos:

| Mecanismo | Dónde | Efecto |
|---|---|---|
| `ON CONFLICT DO NOTHING` | hechos con clave natural | segunda carga no duplica |
| `TRUNCATE` + recarga | dimensiones pequeñas | reconstrucción completa |
| `UNIQUE` declarado | todas las tablas de hechos | el motor rechaza, no el script |

**Esta es la corrección estructural de H-03 y H-08.** Ambos defectos existen porque una
recarga se ejecutó sobre datos ya cargados y nada la detuvo. Con estas restricciones, la
segunda ejecución es inocua.

### 4.7 · Tipado de `H02_BDElifab` — H-10

```sql
INSERT INTO fact.packing (lote_id, fecha_cosecha, fecha_proceso, semana, calibre_id,
                          mercado, recuento, peso_kg)
SELECT l.lote_id,
       s.fecha_cosecha::date,
       s.fecha_proceso::date,
       NULLIF(trim(s.semana), '')::smallint,     -- texto → entero
       c.calibre_id,                             -- texto → dimensión ordenada
       upper(trim(s.mercado)),
       NULLIF(trim(s.recuento), '')::integer,
       s.peso_total_kg::numeric(12,4)
FROM stg.h02_bdelifab s
LEFT JOIN dim.calibre c ON c.etiqueta = trim(s.calibre)
...
```

**Los 5 pares duplicados se consolidan**, conservando la columna con menos nulos:

| Par en Access | Se conserva |
|---|---|
| `Modulo` / `Módulo` | `Modulo` |
| `Productor1` / `Productor` | `Productor` |
| `Calibre` / `Calibres` | `Calibre` (vía `dim.calibre`) |
| `ACDT` / `ACDT 2` | `ACDT` |
| `Peso total (kg)` / `Peso total (kg)2` | `Peso total (kg)2` (0 nulos vs 1) |

`dim.calibre` incluye una columna `orden` para que `12mm < 14mm < ... < 26mm+` ordene
correctamente — hoy se ordena alfabéticamente (`10` antes que `2`).

### 4.8 · Enlace de evaluadores — H-09

```sql
-- El enlace correcto es por DNI, no por Cod
INSERT INTO dim.evaluador (dni, nombres, apellidos, codigo, zona, activo)
SELECT trim(dni), trim(nombres), trim(apellidos),
       NULLIF(trim(cod), ''), trim(zona), estado
FROM stg.m_evaluadores;
```

Los **2 DNI de `E01_Ramas` sin registro en el maestro** van a cuarentena. El hecho se carga
con `evaluador_id` NULL (la FK lo permite) para no perder la evaluación.

`InicioLabores` y `Nacimiento`, hoy texto, se convierten a `date` con `NULLIF` para tolerar
los formatos inválidos.

---

## 5 · Reglas de limpieza por hallazgo

Resumen ejecutable de todas las correcciones:

| Hallazgo | Regla | Verificación |
|---|---|---|
| **H-01** | resolver fundo vía `dim.fundo_alias` antes de cualquier join | huérfanos = 0 |
| **H-02** | declarar FK y PK correctas | FK declaradas > 0 |
| **H-03** | `UNIQUE (lote_id, fecha, cortina, hilera, planta)` + `ON CONFLICT DO NOTHING` | `fact.ramas` = 71.095 |
| **H-04** | corregir 4 consultas; 2 bloqueadas por decisión | consultas rotas = 0 (o 2) |
| **H-05** | unir por fecha o contra `dim.semana_evaluacion`, nunca por `SEvConteo` contra días | vista = 9.040 filas |
| **H-06** | `NOT NULL` en dimensiones; filas nulas a cuarentena | 3 filas en `qua`, 1.925.995 kg |
| **H-07** | unificar el hecho, KG de referencia H00 y origen H01 auditable | reconciliacion registrada |
| **H-08** | `PRIMARY KEY (fecha_hora)` | `fact.clima` = 153.413 |
| **H-09** | enlazar por DNI; 2 sin maestro a cuarentena | 2 filas en `qua` |
| **H-10** | tipar 34 columnas; consolidar 5 pares; `dim.calibre` ordenada | 0 columnas numéricas en texto |
| **H-11** | `LATERAL (VALUES ...)` en vez de `UNION ALL` repetido | 6 consultas simplificadas |
| **H-12** | descartar `Errores de pegado`, `E`, `~TMPCLP*`; **migrar** las 3 tablas sin consumo | 4.905 filas conservadas |

---

## 6 · Consultas de Access → contratos de reporting

### 6.1 · Estrategia de compatibilidad

Cada consulta valida de Access se convierte en una vista de PostgreSQL **con su nombre
original**, dentro de `reporting`, incluidos los acentos y la `ñ`:

```sql
CREATE VIEW reporting."R0801_ResCampaña" AS ...
CREATE VIEW reporting."H0105_RendTurno_paña" AS ...
CREATE VIEW reporting."R0802_ResumenAño" AS ...
```

Las comillas dobles preservan la grafía exacta. Power BI las encuentra igual que hoy.

**Internamente** las vistas usan nombres `snake_case` ASCII; solo la capa de compatibilidad
tiene los nombres originales.

### 6.2 · Consolidación

Las 40 consultas se reducen a **~15 vistas base** más las de compatibilidad. Los casos de
consolidación:

| Vistas base | Reemplazan a |
|---|---|
| `v_evaluacion_larga` | `0106_RaFloYem`, `0107_YemasAb`, `0306_FrutosFlores` |
| `v_estados_turno` | `0302_ConteoAjustado`, `0303_ConteoEstados_Turno` |
| `v_cosecha_resumen` | `H0100`, `H0101`, `H0102`, `H0103` sobre `core.cosecha` |
| `v_forecast_campana` | `R0801_ResCampaña`, `R0801_Forecast_Campaña_SemMes` |

Las consultas originales siguen existiendo como vistas delgadas sobre estas bases. La
consolidacion ocurre en `reporting`; no se mezclan tablas de distinto grano en `core`.

### 6.3 · Vistas materializadas

Cuatro consultas justifican materialización por coste de cálculo:

| Vista | Motivo | Refresco |
|---|---|---|
| `mv_clima_diario` | agrega 153.413 filas | diario |
| `mv_packing_calibre` | agrega 117.536 filas | diario |
| `mv_forecast_vigente` | filtra la versión vigente de 150.083 filas | por carga |
| `mv_cosecha_campana` | base de los tableros de gerencia | diario |

### 6.4 · Reescritura del despivote — H-11

El patrón de `UNION ALL` triplicado se reemplaza por:

```sql
-- Antes: 3 bloques FROM idénticos de 25 líneas cada uno
-- Ahora: el bloque FROM se evalúa UNA vez
SELECT f.*, d.descripcion, d.valor
FROM fact.forecast_campana f
CROSS JOIN LATERAL (VALUES
    ('Kg Exp', f.kg_exp),
    ('Kg Des', f.kg_des),
    ('Kg Con', f.kg_con)
) AS d(descripcion, valor);
```

Una sola definición de la lógica: corregir un error se hace en un sitio, no en tres.

### 6.5 · Corrección de H-05

```sql
-- Access (mal): une semana contra tabla de días → ×54
--   INNER JOIN M_Time ON [0104_PromFlores].Sem = M_Time.SEvConteo

-- PostgreSQL (bien): une contra la dimensión de grano semanal
CREATE VIEW reporting."01_Flores_C2025" AS
SELECT p.*, se.fecha_inicio, se.fecha_fin
FROM v_prom_flores p
JOIN dim.semana_evaluacion se
  ON se.anio = p.anio AND se.sem_ev_conteo = p.semana;   -- grano semanal = semanal
```

**Resultado esperado: 9.040 filas** en vez de 487.368.

---

## 7 · Plan de validación

### 7.1 · Cifras que deben reproducirse exactamente

De `evidencia\04_metricas_validacion.txt`:

| Métrica | Valor esperado |
|---|---|
| `M_Lotes` filas en Access | 860 |
| `M_Time` filas | 2.189 |
| `E02_ConteoFlores` filas | 43.490 |
| `E03_ConteoEstados` filas | 18.714 |
| `E04_Brotes` filas | 3.385 |
| `E05_DiametrosBayas` filas | 4.193 |
| `H02_BDElifab` filas | 117.536 |
| `R08_Forecast_Campaña` filas | 101.715 |
| `R09_Forecast_Semanal` filas | 48.368 |
| `E01 SUM(ramas_total)` | 730.318 |
| `E02 SUM(nFlores)` | 3.050.031 |
| `E04 SUM(Brotes)` | 225.638 |
| `E05 AVG(Diametro)` | 19,8850703636331 |
| `M_Lotes SUM(Area)` | 829,021356070414 |
| `M_Lotes SUM(NPlantas)` | 4.711.564 |
| `R08 SUM([KG Exp])` | 648.044.713,139312 |
| `R09 SUM(Kg)` | 51.083.049,9174915 |

La cifra de 860 es la linea base historica de Access, no una validacion del maestro vigente
de nomenclatura. La identidad canonica de fundos, empresa, modulo y lote se toma del
maestro actualizado durante la carga; la cantidad de filas del maestro no se usa como
decision de negocio.

### 7.2 · Cifras que DEBEN cambiar

Si estas **no** cambian, la migración no aplicó las correcciones:

| Métrica | Access | PostgreSQL | Hallazgo |
|---|---|---|---|
| `fact.ramas` filas | 94.236 | **71.095** | H-03 |
| `fact.clima` filas | 155.588 | **153.413** | H-08 |
| `H00 SUM(KG)` | 33.381.134,66 | **32.450.472,60** | H-06 |
| `H01 SUM(KG)` | 33.441.319,22 | **32.445.986,02** | H-06 |
| `01_Flores_C2025` filas | 487.368 | **9.040** | H-05 |
| `E01 AVG(diametro)` | 10,9776538610781 | **10,8870645965645** | H-03 |
| `0101_Diametros` con turno NULL | 94.236 | **0** | H-01 |
| `0108_diam` filas | 0 | **> 0** | H-01 |

### 7.3 · Defectos que deben quedar en cero

```sql
-- Todas estas consultas deben devolver 0
SELECT count(*) FROM fact.ramas   WHERE lote_id IS NULL;   -- H-01
SELECT count(*) FROM fact.brotes  WHERE lote_id IS NULL;   -- H-01
SELECT count(*) FROM fact.cosecha WHERE fecha IS NULL;     -- H-06

-- Duplicados: 0 por construcción (UNIQUE), pero se verifica
SELECT count(*) FROM (
  SELECT lote_id, fecha, cortina, hilera, planta
  FROM fact.ramas GROUP BY 1,2,3,4,5 HAVING count(*) > 1
) d;                                                        -- H-03

SELECT count(*) FROM (
  SELECT fecha_hora FROM fact.clima GROUP BY 1 HAVING count(*) > 1
) d;                                                        -- H-08
```

### 7.4 · Verificación de integridad del origen

Al terminar, `BD_AQUANQA_26.accdb` debe permanecer intacta y de solo lectura. La validacion
no exigira conservar tamano ni fecha de modificacion: se verificaran filas, totales, claves,
duplicados y trazabilidad mediante la evidencia del origen.

### 7.5 · Verificación cruzada con Power BI

Las 7 verificaciones de `03_GUIA_REPORTES.md` §4 deben ejecutarse **antes** de migrar, para
tener la foto del "antes". Después se comparan contra §7.1 y §7.2.

---

## 8 · Decisiones y dependencias restantes

Con el nuevo maestro y la reconciliacion H00/H01, ya no hay seis bloqueos generales. Quedan
dos dependencias de negocio para terminar la capa de forecast y una regla de diseno de
reporting.

### D-1 · ¿Qué kilos compara `R0902_Forecast_Sem_vs_Camp`? — Planeamiento

`R08` tiene tres columnas de kilos y la consulta pide un `KG` que no existe (H-04 caso 6).

| Opción | `SUM` |
|---|---|
| `[KG Exp]` | 648.044.713,14 |
| `[KG Exp] + [Kg Con]` | 657.404.158,58 |
| los tres | 689.684.707,86 |

**Precedente interno:** `R0801_ResCampaña` usa solo `[KG Exp]`. Sería consistente.
**Pendiente adicional:** definir qué versión de `R08` compara contra qué versión de `R09` —
sin filtrar versión la comparación no tiene sentido.
**Bloquea:** corrección de `R0902_Forecast_Sem_vs_Camp`.

### D-2 · Fechas de corte de la campaña productiva — Planeamiento

`CampProAra` no existe en `M_Time` y dos consultas la piden (H-04 caso 5). Se necesita: para
cada campaña C2022–C2026, la fecha de inicio y fin.

**Impacto:** bloquea solo la correccion de `R0801_Forecast_Campaña_SemMes`, la columna
`dim.tiempo.campana_productiva` y la agregacion historica de `H0103_ResModulo`. No bloquea
la carga del modelo core ni el cambio de alias.

### D-3 · Reconciliacion H00/H01 — actualizado por auditoria

H00 y H01 representan la misma cosecha. Difieren en 187 filas y 4.486,59 kg: H00 conserva
los registros completos de kilos en C2023/C2024, mientras H01 contiene campos adicionales
de captura historica.

**Criterio tecnico del plan:** H00 es la referencia de KG en `reporting`; H01 se conserva
como origen y aporta atributos adicionales cuando la fila puede reconciliarse. La diferencia
queda registrada, no se elimina ni se presenta como una segunda cosecha.

**Estado:** deja de bloquear la estructura de migracion. Solo queda validar con Agronomia
los atributos de H01 que no tengan correspondencia exacta.

### D-4 · Nuevo maestro de fundos y alias — actualizado por M_Lotes.xlsx

El maestro vigente separa tres niveles que no deben volver a mezclarse:

- `FundoPPto`: empresa/razon social (`Aqu Anqa` o `Aqu Anqa II`).
- `Fundo`: fundo fisico numerado (`Aqu Anqa 1` a `Aqu Anqa 6`).
- `Fundo_pptom5`: alias operativo o comercial.

El mapeo antiguo de `Ampliacion`, `Vivadis` y `Sta.Teresa` que aparece en este documento
se considera obsoleto y no se usara como fuente canonica. Los joins no se haran por alias
solo: usaran empresa/fundo fisico, modulo y lote. Los registros historicos sin correspondencia
quedan fuera de `core`/`reporting` y se conservan en `raw`/`qua`.

**Estado:** la estructura de alias esta definida por el nuevo maestro; este plan ya no
considera D-4 un bloqueo general de la migracion.

### D-5 · Clave de lote — reemplaza el hallazgo antiguo

El conteo antiguo de 860 filas y 855 combinaciones de `(Modulo, Lote)` no es una regla
valida para el nuevo maestro: ignoraba la empresa y el fundo fisico. La clave de negocio
se evaluara como `(empresa_id, modulo_id, codigo_lote)` y la clave tecnica sera `lote_id`.

**Estado:** el hallazgo de "5 lotes duplicados" queda obsoleto como bloqueo. `L000` se
conserva como codigo de origen hasta que su uso funcional quede auditado; no se elimina
silenciosamente.

### D-6 · Filtros de campaña en reporting — regla de diseño

Cinco consultas tienen la campaña escrita en el SQL (`0201_Flores` → C2026,
`H0105_RendTurno_paña` → C2025, etc.). En PostgreSQL pueden ser parámetros.

**Regla del nuevo modelo:** las vistas de `reporting` no tendran campañas fijas; Power BI
filtrara por `Campaña`/`dim_campania`. Los filtros fijos solo se conservaran en una vista de
compatibilidad si un reporte historico cerrado lo necesita.
**Estado:** no bloquea la migracion; se aplica al construir las vistas nuevas.

---

## 9 · Cronograma actualizado

| Fase | Trabajo | Depende de |
|---|---|---|
| **F0 · Contratos** | fijar grano, claves, nombres canonicos y salidas que consume Power BI | auditoria |
| **F1 · Raw** | cargar Access a `raw` sin modificar el origen | F0 |
| **F2 · Core** | crear `core` normalizado con Drizzle y migraciones PostgreSQL | F0 |
| **F3 · Calidad** | resolver alias, deduplicar, reconciliar H00/H01 y enviar excepciones a `qua` | F1, F2 |
| **F4 · Hechos** | cargar cosecha, evaluaciones, clima, packing y forecast con grano estable | F3 |
| **F5 · Reporting** | crear `reporting` dimensional, vistas y contratos compatibles con Power BI | F4 |
| **F6 · Validacion** | ejecutar cifras de control, duplicados, totales y pruebas de regresion | F5 |
| **F7 · Paralelo BI** | comparar PostgreSQL contra Access durante un ciclo de reportes | F6 |
| **F8 · App** | conectar Next.js/Drizzle al `core` y probar captura de evaluaciones | F2, F3 |
| **F9 · AWS** | desplegar PostgreSQL, migraciones, secretos, backups y monitoreo | F6, F8 |
| **F10 · Corte** | dejar Access como historico de solo lectura | F7, F9 |

El camino critico ya no pasa por una decision de alias antigua. Pasa por la calidad del
`core`, la reconciliacion de cosecha y la validacion de los contratos de `reporting`.

La convivencia temporal con Access es solo para comparar resultados; no es un pipeline
permanente que vuelva a alimentar la logica defectuosa de Access.

---

## 10 · Resumen

**Qué se corrige automáticamente** (sin decisión de negocio):

- H-02 · claves foráneas y primarias declaradas
- H-03 · 23.141 filas duplicadas eliminadas
- H-05 · explosión ×54 corregida
- H-06 · 1.925.995 kg de filas basura a cuarentena
- H-08 · 2.175 mediciones de clima duplicadas eliminadas
- H-09 · evaluadores enlazados por DNI
- H-10 · 34 columnas tipadas, 5 pares consolidados
- H-11 · 6 despivotes reescritos
- H-12 · basura descartada, 4.905 filas útiles conservadas
- H-04 · 4 de las 6 consultas rotas

**Qué requiere dependencia externa:**

- H-04 · kilos/versiones del forecast (D-1)
- H-04 · fechas de campaña productiva (D-2), solo para reporting temporal

**Qué cambia:** la fuente operativa pasa a `core` en PostgreSQL; Power BI conserva sus
contratos mediante vistas de `reporting`, no mediante consultas ejecutadas en Access.

---

**Documentos relacionados:** `01_AUDITORIA.md` (hallazgos y evidencia) ·
`02_LOGICA_NEGOCIO.md` (qué hace cada consulta) · `03_GUIA_REPORTES.md` (impacto en Power
BI) · `evidencia\` (cifras verificables)
