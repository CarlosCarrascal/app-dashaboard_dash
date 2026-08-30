# Plan de refactor transversal — estado reestructurado

Fecha: 2026-08-27
Alcance: todo el repositorio, no solo `packages/analitica/proyeccion`.

## Objetivo explicado en términos sencillos

Ordenar el proyecto para que cada responsabilidad tenga un lugar claro, sin cambiar las
fórmulas, los resultados, las versiones de modelo, los nombres públicos ni el significado de
los datos. Una persona que no desarrolla debe poder seguir el recorrido:

`fuente autorizada → extracción → tablas raw → transformación → análisis → resultado versionado → dashboard`.

Cada paso debe poder detenerse con un mensaje útil, repetirse sin duplicar datos y demostrar
qué datos, código, contrato y versión produjo un resultado.

## Reglas que no se pueden romper

1. No se cambia una fórmula, unidad, horizonte, escenario, fecha de corte, nombre de columna ni
   ruta pública sin una prueba de equivalencia y una decisión documentada.
2. Las rutas antiguas siguen funcionando mediante fachadas o reexportaciones mientras exista un
   consumidor; primero se demuestra equivalencia y después se retira código.
3. El dashboard solo muestra datos de PostgreSQL que tengan corrida, snapshot y release
   identificables. Excel/Access es fuente de extracción o paridad, no una segunda fuente oculta
   para la interfaz oficial.
4. Cada fase tiene una prueba, una evidencia y un punto de reversión. No se considera terminado
   porque el código “parezca ordenado”.
5. Los comandos Python se ejecutan como `python -m ...`, porque Python no está disponible como
   ejecutable independiente en el PATH del equipo.

## Fases y criterio de salida

| Fase | Qué se entrega | Cómo se demuestra que no rompió nada |
|---|---|---|
| 0. Inventario | Mapa de paquetes, scripts, SQL, dashboard, entradas y salidas | Importaciones públicas, árbol de archivos y pruebas base registrados |
| 1. Fronteras | Contratos, fechas, identidad, hashes, serialización y configuración | Pruebas unitarias de tipos, fechas, caché corrupta y entradas inválidas |
| 2. Núcleo analítico | Fenología, híbrido, relaciones, candidatos, parámetros y horizonte separados | Equivalencia de API y resultados contra una línea base versionada |
| 3. Persistencia | Snapshot, corrida, predicción, calidad, claims, artifacts y releases | FKs, unicidad, inmutabilidad y `as-of` comprobados en PostgreSQL |
| 4. Operación | CLI y scripts delgados, sin depender de funciones privadas internas | `--help`, ejecución aislada y mensajes de error reproducibles |
| 5. Cadena de datos | `setup → extract → load → build → validate` desde base vacía | Base temporal vacía, carga de fixture válido y validación positiva |
| 6. Dashboard | Lectura de release aprobada, trazabilidad y degradación visible | Suite Dash, datos desconectados, SQL real y artefactos verificables |
| 7. Entrega | Wheels limpios, Docker, CI, documentación y rollback | Wheel aislado, `compileall`, Ruff global y build reproducible |
| 8. Auditoría final | Matriz de aceptación firmada y decisión de release | PostgreSQL, Access/Excel, MLflow y despliegue reales; sin bloqueadores |

## Estado después de la auditoría de subagentes

### Comprobado localmente

- `python -m pytest packages/analitica/tests -q`: 346 pasan y 3 se omiten por dependencia externa,
  después de corregir la lectura de columnas `FePas1…FePasN` en una `Series` y versionar el
  fixture dorado del nowcast.
- `python -m pytest apps/dashboard/tests -q`: 188 pasan.
- `python -m pytest etl/tests -q`: 33 pasan, incluyendo el contrato de manifiestos completos y parciales.
- Focales de claims, serialización, fenología e híbrido: 43 pasan.
- `python -m compileall -q packages/analitica apps/dashboard etl/src`: pasa.
- `node --check scripts/run.mjs`: pasa.
- `python -m ruff check packages/analitica apps/dashboard etl/src etl/tests`: pasa sin errores.
- `python -m pytest domain/tests -q`: 2 pasan; `domain` y ETL declaran `src` como ruta de
  pruebas para no depender de una instalación editable previa.
- Las fronteras nuevas de fenología, híbrido, candidatos, persistencia, operación y
  relaciones-partes, además de fechas/normalización/serialización comunes, importan sin activar
  una segunda implementación; `test_fronteras_arquitectura` valida 20 contratos de importación,
  identidad y declaración de empaquetado.
- `relaciones_partes` y `operativo` son por ahora fachadas de transición sobre la lógica existente;
  no se afirma todavía que `relaciones.py` o los módulos operativos hayan sido extraídos físicamente.
- El wheel disponible en `packages/analitica/dist_clean_final` contiene los subpaquetes
  fenológico, híbrido, horizonte y scripts.
- Las fachadas públicas, la ayuda del CLI, el empaquetado limpio y la carga perezosa de
  dependencias pesadas tienen pruebas locales.
- Los scripts ya no importan nombres privados de otros scripts: cada utilidad compartida tiene
  un nombre público y conserva aliases históricos solo dentro del consumidor. La prueba AST y
  la auditoría independiente verifican que no haya símbolos privados inexistentes.
- El test de equivalencia del nowcast ya no depende de `.tmp`: usa
  `packages/analitica/tests/fixtures/nowcast_cierre_adaptativo_c2026.json`, con 84 filas de
  entrada y 12 filas de holdout para S31--S33. En un checkout sin `.tmp`, el focal dio 8 pasadas
  y la suite completa mantuvo 346 pasadas y 3 omisiones.
- `setup` y `build` incluyen las tablas `10_raw`, por lo que el primer `load` ya no depende de
  una orden escondida.
- El dashboard marca la release aprobada de los artefactos y selecciona métricas, replay,
  calidad y fuentes desde corridas gobernadas.
- `node scripts/run.mjs validate-fixture`: pasa en una base efímera, con 92 comprobaciones
  correctas, y elimina la base al terminar.
- `node scripts/run.mjs validate`: conserva el caso negativo; terminó con código 1 porque la
  base configurada no tiene `analytics.evidence_claim_history`; el nuevo aislamiento clonó la base
  mediante `pg_dump/pg_restore` porque tenía 3 sesiones activas, ejecutó los checks en la copia y
  la eliminó junto con el dump temporal.
- La prueba real de historial de claims pasó contra una base PostgreSQL efímera preparada con
  las capas SQL del repositorio, excluyendo únicamente el bootstrap de roles; la base configurada
  del equipo sigue sin demostrar ese contrato.
- MLflow pasó una corrida, métricas, firma, artefacto y registro de modelo usando backend SQLite
  efímero. El backend `file://` falla por el modo de mantenimiento de MLflow 3.15 y no se pudo
  probar Docker porque el daemon de Docker Desktop no está iniciado.
- La auditoría independiente de fenología no encontró P0 ni P2. El contrato de parámetros de
  `guardar_claims` queda en el orden del SQL y está cubierto por una prueba de integración real
  contra PostgreSQL efímero.
- El dashboard etiqueta sus rutas históricas como `Fuente histórica · Excel/Access` y conserva
  `/analitica/*` como camino oficial PostgreSQL; el contrato de fuentes pasa 5 pruebas nuevas.
- La extracción Access registra `alcance`, `snapshot_completo`, tablas catalogadas, extraídas y
  omitidas; una petición `--solo` desconocida falla antes de abrir la conexión.
- El wheel reconstruido desde una copia limpia contiene las nuevas fronteras y 172 entradas sin
  `.pyc`; el wheel antiguo bajo `dist_clean_final` sigue siendo un artefacto obsoleto hasta una
  entrega autorizada.

## Revisión independiente posterior a la implementación

El auditor transversal terminó después de revisar el árbol completo sin editarlo ni limpiar el
worktree. Confirmó que no hay P0, pero dejó estos bloqueadores P1 que cambian el orden del plan:

1. El estado actual incluye cambios y DDL SQL, aunque el material de requisitos pedía no cambiar
   SQL/tablas. La decisión de alcance debe tomarse antes de una release; no se debe esconder esta
   incompatibilidad bajo el nombre de refactor.
2. El dashboard aún tiene dos caminos: `/analitica/*` usa PostgreSQL, mientras páginas históricas
   y de impacto consumen `PANEL_STORE` desde Excel/Access. Debe separarse explícitamente lo
   oficial de PostgreSQL de lo histórico, con una etiqueta visible de fuente.
3. El catálogo ETL declara menos tablas que el Access real y `--solo` puede dejar un manifiesto
   parcial presentado como si fuera un snapshot completo. Ya se corrigió el manifiesto para
   declarar alcance completo/parcial, pero sigue pendiente decidir si se incorporan las tablas
   reales adicionales sin contradecir la restricción SQL.
4. `npm run validate` modifica la base configurada (`DROP`, `TRUNCATE`, `INSERT`) antes de fallar;
   ya usa una copia temporal no mutante; el modo fallback puede ser costoso en bases grandes.
5. El wheel histórico de `dist_clean_final` está obsoleto. La verificación nueva ya construyó un
   wheel limpio desde una copia temporal, con las fronteras nuevas y cero `.pyc`, pero falta
   decidir si ese artefacto debe reemplazar al histórico bajo una entrega autorizada.
6. El gate `sqlfluff lint db/sql --dialect postgres` falla según la auditoría. El shell principal
   no resuelve `sqlfluff` como ejecutable, pero la auditoría final sí pudo ejecutar
   `python -m sqlfluff lint db/sql --dialect postgres` y obtuvo código 1. El `E501` de ETL ya
   fue corregido. No se declara CI SQL verde.

Los hallazgos P2 restantes son las advertencias masivas de `Timedelta`, el `TRUNCATE` de raw ante
interrupciones, la falta de baseline histórico fila por fila y la ausencia de un rollback
versionado autorizado.

### Aún no certificable

1. **Equivalencia histórica:** no existe todavía una línea base ejecutable de la versión anterior
   que permita probar fórmula, resultado y versión de modelo fila por fila.
2. **PostgreSQL del entorno configurado:** la integración efímera pasó y `validate` ya no muta la
   base configurada, pero la instancia
   configurada no tiene `analytics.evidence_claim_history`; falta ejecutar la cadena completa
   contra la instancia autorizada y aclarar la aplicación del bootstrap de roles.
3. **Fuentes operativas:** falta ejecutar con los libros Access/Excel autorizados y comparar el
   motor contra esos resultados reales.
4. **MLflow y despliegue:** el contrato de MLflow ya pasó con SQLite efímero, pero falta validar
   el backend autorizado y el contenedor; Docker está bloqueado externamente mientras el daemon
   no esté disponible.
5. **Entrega reversible:** el trabajo actual está en el árbol local con archivos nuevos sin un
   commit o tag de fase; todavía no hay un punto de rollback compartible. El wheel viejo en
   `dist_clean_final` no se sobrescribe sin autorización.
6. **Extracción física y equivalencia:** las nuevas rutas de `relaciones_partes` son aliases de
   transición, y no hay una línea base histórica ejecutable para certificar cambios físicos.
7. **Advertencias:** las pruebas producen muchas advertencias de deprecación de
   `pandas/NumPy Timedelta` y alguna convergencia de `statsmodels`; no fallan hoy, pero deben
   tratarse antes de subir versiones de esas dependencias.

### Nota sobre el alcance de los cambios SQL

El material de requisitos pegado al inicio indicaba no cambiar SQL ni tablas. El estado actual
sí incluye cambios SQL de gobernanza, analytics y compuertas, porque eran necesarios para cerrar
trazabilidad, releases y validación desde base vacía. Esto está documentado aquí como una
decisión de alcance pendiente de aprobación; no se presenta como cumplimiento literal de aquella
restricción.

## Revisión final posterior a las remediaciones

La segunda auditoría independiente terminó después de esperar todas sus comprobaciones. Fue
estrictamente de lectura, incluyó el working tree no comprometido y volvió a excluir las rutas
reservadas de horizonte. Confirmó que no hay P0, pero mantiene el veredicto **NO LIBERABLE** por
estos P1:

1. **Alcance SQL:** el árbol modifica SQL existente y agrega `80_analytics`, checks y fixtures,
   pese a que el requisito original pedía no cambiar SQL ni tablas. Falta una decisión explícita
   entre variante estricta y alcance ampliado.
2. **Contrato Access:** el manifiesto ahora diferencia completo/parcial, pero la documentación
   contiene cifras incompatibles (17 tablas catalogadas, 18 descritas y 23 locales en el Access),
   el loader todavía acepta snapshots parciales y el reporting/dashboard no expone claramente
   `alcance` ni `snapshot_completo`.
3. **Dashboard:** `/analitica/*` usa PostgreSQL y las páginas históricas están etiquetadas como
   Excel/Access, pero el servicio oficial aún consulta directamente `stg`/`dim`; falta cerrar la
   fachada reporting autorizada y hacer visible el estado del snapshot.
4. **Entrega:** `dist_clean_final` tiene un wheel antiguo de 154 entradas frente a 172 del wheel
   limpio verificado, que contiene 0 `.pyc`. Hay además artefactos de build/cache temporales sin
   una política de entrega y no existe commit/tag de rollback autorizado.
5. **SQLFluff:** el gate CI sigue activo y la ejecución final de `python -m sqlfluff lint
   db/sql --dialect postgres` terminó con código 1 y miles de violaciones históricas de
   formato/estructura (`LT01`, `LT02`, `LT05`, entre otras); no se puede declarar la cadena SQL
   verde.

La auditoría confirmó como evidencia positiva las fachadas públicas fuera de horizonte, el
aislamiento de `validate`, el manifiesto completo/parcial y las suites ya registradas. Los P2
restantes son limpieza ante terminación forzada, `TRUNCATE` durante cargas interrumpidas,
warnings de dependencias, ausencia de baseline histórico y falta de rollback versionado.

El orden queda reestructurado: primero resolver alcance SQL y contrato Access; después completar
la fachada reporting del dashboard; luego resolver SQLFluff y artefactos de entrega; finalmente
ejecutar las integraciones externas y repetir la auditoría antes de cualquier decisión de
release.

## Verificación posterior del fixture y contratos inter-script

La auditoría independiente posterior al último cambio terminó con veredicto **APROBADO** para
este tramo. Se comprobó lo siguiente:

- La prueba ya no lee `.tmp/screening_adaptive_nowcast_fund_guard.json`; usa el fixture
  versionable del paquete.
- El fixture contiene 84 filas, de las cuales 12 corresponden al holdout de semanas 31, 32 y
  33, y la comparación reproduce el resultado esperado.
- Sin la carpeta `.tmp`, `python -m pytest packages/analitica/tests/test_nowcast_cierre_adaptativo.py -q`
  terminó con `8 passed`.
- La suite completa volvió a terminar con `346 passed, 3 skipped`.
- `python -m ruff check` pasó en el perímetro del cambio.
- No hubo cambios en `packages/analitica/proyeccion/horizonte/*` ni en
  `packages/analitica/proyeccion/pronostico_horizonte.py`.

Este resultado demuestra la reproducibilidad funcional del fixture en el worktree, pero todavía
no cierra su entrega: la auditoría final comprobó que `git ls-files` no devuelve el JSON nuevo.
Por tanto, debe quedar incorporado en la entrega versionada antes de considerar cerrado ese
control. Permanecen además los bloqueadores de alcance SQL, contrato Access, fachada reporting,
SQLFluff y entrega reversible descritos arriba.

## Auditoría final posterior a los nombres públicos de scripts

La última auditoría independiente fue estrictamente de solo lectura, terminó y fue archivada.
Su veredicto es **NO LIBERABLE**, pero confirma que la remediación Python no introdujo regresiones
en la frontera revisada:

- Revisó 67 imports entre scripts; todos apuntan a nombres públicos existentes y no quedan aliases
  privados importados entre scripts.
- `Panel`/`Hallazgo` conservan identidad pública, cinco campos compatibles y el `__module__`
  histórico de `Panel`; el roundtrip de pickle pasó.
- Ruff terminó con 0 errores; las pruebas focales con `python -m pytest` dieron 23 passed.
- Las suites amplias dieron 346 passed y 3 skipped en analítica, 188 passed en dashboard y 33
  passed en ETL. `compileall` y `node --check scripts/run.mjs` también pasaron.
- La corrección local se verificó además con 59 pruebas focales y la suite completa de analítica
  (`346 passed, 3 skipped`) después de reemplazar los últimos call sites privados.

La auditoría descubrió dos matices de entrega que deben quedar explícitos:

1. `git status --short` muestra como `??` tanto `packages/analitica/proyeccion/horizonte/` como
   `packages/analitica/proyeccion/pronostico_horizonte.py`. Es trabajo paralelo fuera del alcance
   de esta subtarea; este hilo no los modificó ni debe incorporarlos, borrarlos o restaurarlos.
   El responsable de esa subtarea debe cerrar su integración y repetir la revisión de perímetro.
2. `packages/analitica/tests/fixtures/nowcast_cierre_adaptativo_c2026.json` está presente y hace
   pasar la prueba, pero `git ls-files` aún no lo devuelve. Es reproducible localmente, no todavía
   entregable desde un checkout limpio, hasta que exista una entrega versionada autorizada.

El resto de los P1 confirmados son: 5.875 violaciones SQLFluff en 43 archivos; alcance SQL aún
sin decisión; catálogo Access de 17 tablas frente a documentación/archivo operativo de 18/23 y
cargas parciales aún aceptadas; dashboard con PANEL_STORE/Excel histórico junto con PostgreSQL y
consultas directas a `stg`/`dim`; wheel `dist_clean_final` antiguo que omite 18 módulos productivos
y el fixture; falta de rollback/tag autorizado; y ausencia de una baseline histórica ejecutable
fila por fila. Los P2 son los warnings masivos de Timedelta, limpieza ante interrupciones y
comandos documentales que todavía no siguen siempre `python -m`.

### Reestructuración del plan después de la auditoría final

El orden de ejecución queda así, sin confundir una prueba verde con una autorización de entrega:

1. Esperar y revisar el cierre del responsable de las rutas reservadas; comprobar que su estado no
   se mezcle con esta subtarea y que la fachada final sea compatible.
2. Elegir la variante de alcance SQL: estricta sin nuevos DDL o ampliada con aprobación explícita;
   después decidir qué hacer con el gate SQLFluff sin desactivarlo silenciosamente.
3. Fijar una única cifra para el contrato Access, completar el catálogo autorizado y bloquear o
   etiquetar de forma inequívoca los snapshots parciales.
4. Completar la fachada única de reporting del dashboard y exponer `alcance`/`snapshot_completo`.
5. Versionar, con autorización, el fixture y el wheel limpio; definir rollback/tag y política de
   artefactos temporales.
6. Ejecutar las integraciones reales autorizadas (PostgreSQL, Access/Excel, MLflow y Docker),
   conservar paridad y repetir esta auditoría independiente.
7. Solo si todos los P1 desaparecen y la baseline histórica o su ausencia quedan formalmente
   resueltas, evaluar la liberación.

## Trabajo inmediato reordenado

1. Decidir formalmente el alcance SQL: variante estricta sin nuevos DDL o aprobación explícita
   del alcance ampliado actual.
2. Resolver el contrato Access con una única cifra fuente (17, 18 o 23), listar las exclusiones
   y decidir si un snapshot parcial puede cargarse o debe bloquearse.
3. Mantener `validate` aislado, añadir limpieza ante terminación forzada y medir el coste del
   fallback en bases grandes.
4. Completar la fachada reporting del dashboard para no consultar directamente `stg`/`dim` en
   el camino oficial y exponer `alcance`/`snapshot_completo`; conservar la etiqueta histórica.
5. Ejecutar SQLFluff en el entorno de CI o acordar una excepción temporal visible; no desactivar
   el gate silenciosamente.
6. Definir la política de artefactos temporales, regenerar el wheel oficial solo con autorización
   y documentar un punto de rollback versionado.
7. Ejecutar PostgreSQL autorizado, Access/Excel, MLflow y Docker; conservar evidencia de paridad,
   limpieza y despliegue.
8. Recuperar una muestra histórica ejecutable o registrar formalmente su ausencia y tratar los
   warnings de dependencias antes de actualizar versiones.
9. Repetir la auditoría independiente después de cerrar los P1 y solo entonces decidir la
   liberación; hasta ese momento conservar el worktree sin staging ni rollback destructivo.

## Comandos de aceptación

```powershell
$env:PYTHONPATH='packages;apps/dashboard'
python -m pytest packages/analitica/tests -q
python -m pytest apps/dashboard/tests -q
python -m pytest etl/tests -q
python -m compileall -q packages/analitica apps/dashboard etl/src
python -m ruff check packages/analitica apps/dashboard etl/src etl/tests
python -m sqlfluff lint db/sql --dialect postgres
node --check scripts/run.mjs
git ls-files packages/analitica/tests/fixtures/nowcast_cierre_adaptativo_c2026.json
npm run setup
npm run extract
npm run load
npm run build
npm run validate
```

Los cinco últimos comandos requieren PostgreSQL y archivos de entrada reales; no se deben
simular como “éxito” si faltan esas dependencias. El estado actual es **refactor avanzado, no
liberable todavía** hasta cerrar los seis puntos de certificación anteriores y decidir el alcance
SQL.

## Auditoría del contrato Access y trazabilidad física

La auditoría independiente posterior a las remediaciones terminó y fue esperada antes de
continuar. Su resultado es **aprobado para el endurecimiento local, no aprobado como release**.

Quedó implementado y comprobado lo siguiente:

- Una carga completa se detiene antes de abrir PostgreSQL si falta el manifiesto Access, si el
  manifiesto es parcial, si falta algún CSV del catálogo o si falta `m_lotes_maestro`; `tareo`
  conserva su carácter opcional.
- Las recargas `--solo` siguen disponibles, pero verifican la campaña, existencia y SHA-256 del
  CSV seleccionado cuando existe un manifiesto.
- El contrato `FuenteInfo` conserva opcionalmente `source_snapshot_id`; el repositorio lo guarda
  dentro de la cobertura del snapshot analítico y el dashboard consulta exactamente ese ID físico.
- La trazabilidad de la UI muestra `completo`, `parcial` o `no verificable`; no presenta como
  completo el último snapshot Access si no coincide con la corrida visible.
- Evidencia posterior: `python -m pytest etl/tests/test_manifiesto_access.py etl/tests/test_catalogo.py -q`
  terminó con `40 passed`; Ruff y `python -m compileall -q packages/analitica apps/dashboard
  etl/src domain/src` pasaron.

La auditoría no encontró P0. Mantiene estos bloqueos que no se resuelven con más refactor local:

1. El repositorio contiene cambios SQL que contradicen literalmente la variante estricta de los
   requisitos; hace falta decidir si se conserva el alcance ampliado o se vuelve a una variante
   sin DDL nuevo.
2. El catálogo documentado sigue necesitando una decisión única entre 17 tablas catalogadas,
   18 descritas y 23 observadas en el Access auditado; no se debe inventar una equivalencia.
3. Las rutas `packages/analitica/proyeccion/horizonte/*` y
   `packages/analitica/proyeccion/pronostico_horizonte.py` siguen siendo trabajo paralelo no
   rastreado. Este hilo no las modificó y no puede certificar su equivalencia hasta que su
   responsable entregue el resultado y exista una comparación contra una baseline.
4. El fixture del nowcast y el wheel limpio funcionan en el worktree, pero aún no constituyen
   una entrega reproducible desde un checkout limpio ni un punto de rollback autorizado.
5. SQLFluff continúa fallando con miles de violaciones históricas; no se debe desactivar el gate
   silenciosamente.

### Reestructuración del plan después de la auditoría Access

El orden operativo queda actualizado así:

1. Esperar la integración y la evidencia del responsable de horizonte; auditar el perímetro sin
   modificar sus archivos.
2. Resolver por escrito la variante de alcance SQL y el criterio de aceptación de SQLFluff.
3. Cerrar el catálogo Access con una cifra autorizada, exclusiones y campaña documentadas; luego
   validar contra el origen Access real.
4. Con autorización, versionar el fixture y regenerar el wheel limpio; crear un tag o commit de
   rollback sin sobrescribir el worktree actual.
5. Ejecutar la cadena real de PostgreSQL, Access/Excel, MLflow y Docker; conservar paridad y
   evidencias separadas de las pruebas efímeras.
6. Construir o registrar formalmente la baseline histórica fila por fila y tratar los warnings
   de `Timedelta` antes de actualizar dependencias.
7. Repetir la auditoría independiente completa. Solo con cero P1 y decisiones de alcance
   documentadas se evaluará la liberación.

## Auditoría posterior al cierre de Kepler y plan vigente

La auditoría independiente posterior al último ajuste de R09 terminó y fue esperada antes de
reestructurar nuevamente este documento. Su veredicto es **funcionalmente aprobado para el
perímetro revisado, pero no liberable todavía**.

### Qué quedó comprobado

- R09 conserva `NULL` cuando no hay snapshots Access, asigna el snapshot correcto para una
  campaña y asigna IDs independientes cuando hay varias campañas.
- Si el vínculo es parcial, solo se completa la campaña con correspondencia; no se inventan IDs
  para las demás. La columna conserva el dtype nullable `Int64`.
- El replay exige contratos de evaluación `approved` tanto al seleccionar releases como al cargar
  predicciones, y mantiene las condiciones de release aprobado y activo.
- Se añadieron pruebas funcionales explícitas para ausencia de snapshots y vínculo parcial:
  `python -m pytest tests/test_reporting_facade.py tests/test_replay_contracts.py -q` terminó con
  `12 passed`.
- La verificación completa posterior terminó con `197 passed, 21043 warnings` en dashboard,
  `346 passed, 3 skipped` en analítica y `41 passed` en ETL.
- `python -m ruff check packages/analitica apps/dashboard etl/src etl/tests domain` pasó;
  `python -m compileall -q packages/analitica apps/dashboard etl/src domain` pasó;
  `node --check scripts/run.mjs` pasó; el entorno responde con `pytest 9.1.1` mediante
  `python -m pytest --version`.
- No se modificaron `packages/analitica/proyeccion/horizonte/*` ni
  `packages/analitica/proyeccion/pronostico_horizonte.py`. Ambos siguen apareciendo como trabajo
  paralelo no rastreado y requieren su propia entrega y comparación contra baseline.

### Qué no debe confundirse con una liberación

Las pruebas verdes demuestran que el refactor local revisado no rompe las rutas cubiertas; no
resuelven por sí solas los bloqueos de entrega. Continúan abiertos:

1. Decidir por escrito si se conserva el alcance SQL ampliado actual o se vuelve a la variante
   estricta sin DDL nuevo.
2. Fijar una única cifra y lista autorizada para el catálogo Access: 17 tablas catalogadas,
   18 descritas o 23 observadas no pueden coexistir como contrato implícito.
3. Integrar y auditar las rutas reservadas de horizonte con una baseline y evidencia propia.
4. Versionar, con autorización, el fixture `packages/analitica/tests/fixtures/nowcast_cierre_adaptativo_c2026.json`;
   `git ls-files` todavía no lo devuelve. El wheel limpio y el punto de rollback tampoco están
   autorizados/versionados.
5. Resolver las violaciones históricas de SQLFluff o aprobar una excepción visible; el gate no se
   debe desactivar silenciosamente.
6. Ejecutar integraciones reales autorizadas de PostgreSQL, Access/Excel, MLflow y Docker, y
   recuperar una baseline histórica ejecutable o registrar formalmente su ausencia.

Las `21043` advertencias del dashboard y `32088` de analítica son principalmente deprecaciones
de `Timedelta`; no fallan las pruebas, pero quedan como deuda antes de actualizar dependencias.
`git diff --check` no encontró errores de whitespace; solo emitió avisos de normalización CRLF/LF
en dos archivos existentes.

### Orden reestructurado de trabajo

El plan operativo queda reducido a cinco puertas, en este orden:

1. **Cerrar la integración paralela de horizonte.** Esperar su entrega, comprobar que no invade
   este perímetro y ejecutar la comparación funcional; hasta entonces no certificar todo
   `packages/analitica`.
2. **Cerrar contratos externos.** Resolver alcance SQL, catálogo Access, política de snapshots
   parciales y criterio de aceptación SQLFluff. Estas son decisiones de proyecto, no cambios que
   deba inventar el refactor.
3. **Hacer reproducible la entrega.** Autorizar el versionado del fixture, regenerar el wheel,
   definir rollback/tag y establecer la política de temporales sin sobrescribir el worktree
   actual.
4. **Probar el sistema real.** Ejecutar PostgreSQL, Access/Excel, MLflow y Docker; contrastar
   resultados con la baseline histórica y conservar los logs separados de las pruebas unitarias.
5. **Auditar y decidir release.** Repetir la auditoría completa. Solo si no quedan P1, las
   decisiones están documentadas y la baseline está resuelta o formalmente aceptada, evaluar la
   liberación.

**Estado vigente:** refactor local avanzado y verificado; entrega todavía no liberable. No se
debe borrar, restaurar, hacer rollback destructivo, incorporar ni modificar el trabajo paralelo
de horizonte desde este hilo.

## Auditoría final posterior a la corrección de snapshots

Esta revisión volvió a esperar los dos subagentes finales antes de cambiar el plan. Ambos
trabajaron en solo lectura, no tocaron las rutas reservadas y fueron cerrados después de entregar
su dictamen. El resultado sigue siendo **NO GO para liberar**, aunque el código local cubierto por
las pruebas está estable.

### Cambios locales comprobados

- La identidad de snapshots Access se busca por campaña y SHA-256, y la reutilización comprueba
  que el manifiesto cubra realmente las tablas solicitadas. Un manifiesto parcial ya no se
  reutiliza como carga completa.
- El loader consulta `raw.source_table_snapshot` antes de omitir Access. Si un snapshot completo
  se cargó primero con `--solo e01_ramas`, una ejecución posterior puede cargar otra tabla del
  mismo snapshot en vez de omitirla por el estado global.
- El loader rechaza manifiestos cuyo `tipo` no sea `access`; la publicación exige tanto
  `snapshot_completo=true` como `alcance='completo'`; rollback y promoción comprueban campaña.
- Se mantienen los ajustes previos de imports lazy en `nucleo.datos`, dependencia exacta del
  dashboard, Ruff completo, wheel smoke en entorno limpio y `python -m pip` en Docker/CI.
- No se modificaron `packages/analitica/proyeccion/horizonte/*` ni
  `packages/analitica/proyeccion/pronostico_horizonte.py`.

### Evidencia reproducida después de la revisión

```text
python -m pytest --version                         pytest 9.1.1
python -m pytest packages/analitica/tests -q       347 passed, 3 skipped, 32088 warnings
dashboard/tests -q                                 197 passed, 21043 warnings
domain/tests etl/tests -q                          56 passed
etl/tests focales                                  16 passed
python -m ruff check --no-cache ...                All checks passed
python -m compileall -q ...                        OK
node --check scripts/run.mjs                       OK
```

Las advertencias son principalmente deprecaciones de `Timedelta`; no son fallos de prueba, pero
deben tratarse antes de actualizar versiones científicas. `git diff --check` no encontró errores
de whitespace y solo informó la normalización CRLF/LF de dos archivos existentes.

### Bloqueos confirmados por la auditoría final

1. `packages/analitica/scripts` contiene 47 Python no rastreados por Git y conserva 21 imports
   directos entre 15 scripts. Debe extraerse la lógica común a servicios/módulos estables y luego
   versionarse con autorización; no se debe fingir que el wheel del worktree equivale a un
   checkout limpio.
2. No existe lockfile ni archivo de constraints. Los límites inferiores actuales no garantizan
   que futuras instalaciones conserven las versiones de modelos, métricas y librerías científicas.
3. El DDL aún no fuerza que `snapshot_publication.tipo/campania` coincidan con el snapshot físico,
   su unicidad concurrente por campaña y SHA no está protegida por una restricción alineada, y la
   vista legacy de snapshots puede ocultar filas de tablas no relacionadas cuando hay una
   publicación. Estos puntos requieren una decisión explícita sobre SQL/tablas; no se cambian aquí
   porque el contrato de esta refactorización prohíbe alterar SQL de negocio sin autorización.
4. Las pruebas Python no sustituyen PostgreSQL, Access/Excel, MLflow ni Docker reales; tampoco
   existe todavía una baseline histórica fila por fila. El catálogo actual del código tiene 23
   tablas, mientras la documentación histórica habla de 17/18: hace falta una cifra autorizada.
5. El fixture, scripts y nuevos módulos siguen sin constituir por sí solos un punto de rollback o
   una entrega desde checkout limpio. El wheel limpio probado es evidencia local, no una versión
   publicada.
6. SQLFluff sigue pendiente por las violaciones históricas y no debe desactivarse silenciosamente.

La auditoría desestimó como obsoleta la observación de que `EXTERNAS_REQUERIDAS` estuviera vacío:
el estado actual exige `m_lotes_maestro` para carga completa y conserva `tareo` como opcional. Esto
se verificó en el código y en la suite ETL vigente.

## Plan reestructurado después de la auditoría final

El orden de trabajo queda así, para que cada puerta tenga una salida verificable y entendible:

1. **Esperar y recibir horizonte.** El responsable debe entregar sus tres archivos, pruebas,
   Ruff y `compileall`; después se compara fachada, contratos, fórmulas, modelos y rutas contra la
   baseline sin modificar sus archivos desde este hilo.
2. **Cerrar el contrato de datos.** Un responsable del proyecto debe decidir por escrito la cifra
   oficial del catálogo Access, las exclusiones, el alcance SQL permitido, la política de baseline
   estricto/advertencia y si se corrigen las restricciones/vistas de snapshots mediante una
   migración aprobada.
3. **Desacoplar scripts.** Mover las funciones compartidas de los 21 enlaces entre scripts a
   `servicios`/módulos de dominio, dejar cada script como adaptador CLI delgado y añadir una prueba
   que importe los 47 módulos y ejecute sus `--help` sin efectos laterales.
4. **Hacer entregable el refactor.** Con autorización, versionar todos los archivos intencionados,
   crear lock/constraints, reconstruir wheel desde un directorio limpio, comparar fuente contra
   wheel y definir tag/rollback. No hacer `git add`, commit ni rollback destructivo desde esta
   sesión.
5. **Probar infraestructura real.** Ejecutar en entornos autorizados PostgreSQL, Access/Excel,
   MLflow y Docker; verificar promoción/rollback, exportaciones, dashboard, scripts y paridad con
   la baseline. Guardar logs separados de pruebas unitarias.
6. **Cerrar calidad y release.** Resolver o aprobar visiblemente SQLFluff, reducir deprecaciones,
   repetir las suites completas y la auditoría independiente. Solo con cero P1, decisiones
   documentadas, horizonte integrado y evidencia reproducible se puede evaluar la liberación.

**Estado tras esta reestructuración:** refactor local avanzado, con evidencia automatizada verde,
pero todavía no liberable. El objetivo permanece abierto hasta cerrar los P1 y recibir la entrega
del horizonte; se conserva todo el trabajo existente y se mantiene intacto su perímetro reservado.

## Auditoría posterior al desacoplamiento de scripts y a la validación de empaquetado

Se esperaron los dos subagentes especializados hasta su estado final y se revisaron sus
dictámenes contra el árbol de trabajo. Ambos trabajaron en solo lectura y confirmaron que no se
modificaron `packages/analitica/proyeccion/horizonte/*` ni
`packages/analitica/proyeccion/pronostico_horizonte.py`.

### Estado que sí quedó demostrado

- Los 47 scripts analíticos ya no importan directamente otros scripts: la compuerta AST reporta
  cero enlaces entre `analitica.scripts.*` y cero imports de scripts desde los servicios.
- Las fachadas de replay, parámetros, router, cross-campaign y small-data conservan identidad y
  firmas; los servicios nowcast y expertos son importables.
- `python -m pytest packages/analitica/tests -q`: **355 passed, 3 skipped**.
- Pruebas focalizadas de nowcast/adaptativo/replay/cross/small-data: **36 passed** en la última
  ejecución local; la auditoría independiente reprodujo además **71 passed** en su alcance.
- `python -m ruff check --no-cache packages/analitica apps/dashboard etl/src etl/tests domain`:
  **All checks passed** después de corregir cuatro E501 de formato en ETL.
- `python -m compileall -q packages/analitica apps/dashboard etl/src domain` y
  `node --check scripts/run.mjs`: correctos.
- `python -m pip install --dry-run -c constraints-analitica.txt
  "packages/analitica[dev,operativo]" "apps/dashboard[dev]"`: correcto.
- Wheel analítico construido desde copia limpia: **0 `.pyc`**, contiene CLI, servicios, horizonte
  y entry point. La auditoría también construyó e instaló ruedas analítica/dashboard en un entorno
  aislado, con `pip check` e imports correctos.
- Los workflows YAML pudieron parsearse; el archivo de constraints ya se usa en el workflow del
  dashboard y en el Dockerfile.

### No-Go confirmado por los auditores

1. **P1 de arquitectura:** eliminar imports entre scripts no basta. El algoritmo adaptativo sigue
   duplicado en `servicios/nowcast.py` y `screening_adaptive_nowcast.py`; el algoritmo experto
   principal sigue en el script y `servicios/expertos.py` solo comparte lectura/métricas. Esto
   permite deriva futura y no cumple completamente el objetivo de scripts como adaptadores CLI.
2. **P1 de entorno:** no hay evidencia real de PostgreSQL, Access/Excel, MLflow, Docker Linux ni
   baseline histórica fila por fila. El build Docker local no pudo ejecutarse porque Docker Desktop
   no tenía activo el daemon.
3. **P1 de entrega:** los cambios del refactor, scripts, servicios y tests aparecen como archivos
   no rastreados en este worktree. No se deben versionar automáticamente desde esta sesión, pero
   sí debe existir un inventario entregable y una decisión explícita del responsable del proyecto.
4. **P2 de reproducibilidad:** `constraints-analitica.txt` fija dependencias directas, no las
   transitivas ni hashes, y no fija `setuptools`, `pyodbc` ni `gunicorn`. Además, `python.yml` y
   `db.yml` todavía instalan sin ese archivo, por lo que no existe una política única entre las
   matrices Python 3.12, 3.13 y 3.14.
5. **P2 de entorno local:** `pip check` global está contaminado por una instalación previa de
   `aquanqa-etl` que exige `pyodbc` y `rich`; el entorno aislado analítica/dashboard sí pasó. Esto
   no debe confundirse con una validación completa de ETL.
6. **P2 histórico:** permanecen advertencias de deprecación de `Timedelta`, SQLFluff pendiente y
   las decisiones SQL/DDL ya documentadas sobre identidad/publicación de snapshots. No se modifica
   SQL de negocio sin autorización explícita.

## Plan reestructurado después de la segunda auditoría

El siguiente orden sustituye el orden anterior y queda sujeto a evidencia por puerta:

1. **Centralizar la lógica duplicada.** Extraer el algoritmo adaptativo completo y el algoritmo
   experto completo a servicios estables, manteniendo en cada script solo imports, parámetros,
   composición de contrato, serialización y `main`. Añadir pruebas de identidad/firma y paridad de
   resultados para las fachadas históricas. No cambiar fórmulas, columnas, versiones, rutas ni
   semántica as-of.
2. **Unificar la política de dependencias.** Decidir si el archivo será constraints directas o
   lock completo; aplicar la decisión a `python.yml`, `db.yml`, dashboard, Docker y documentación.
   Validar explícitamente los tres intérpretes objetivo y declarar los extras ETL (`pyodbc`, `rich`)
   y deploy (`gunicorn`) donde correspondan, sin falsear `pip check` del entorno global.
3. **Hacer la entrega trazable.** Mantener inventario de archivos intencionados, reconstruir ruedas
   desde checkout limpio, comprobar que no llevan bytecode, ejecutar smoke de entry points y
   definir tag/rollback. No hacer `git add`, commit ni rollback destructivo desde esta sesión.
4. **Integrar el horizonte reservado.** Esperar la entrega del responsable paralelo; validar luego
   fachada, contratos, modelos, fórmulas, tolerancias, imports, Ruff, `compileall` y tests sin
   modificar sus archivos desde este hilo.
5. **Probar infraestructura autorizada.** Ejecutar CI/Linux y Docker con daemon activo, PostgreSQL,
   Access/Excel y MLflow; comprobar exportaciones, persistencia, dashboard, scripts y paridad con
   la baseline histórica. Registrar por separado qué fue ejecutado de forma real y qué solo fue
   probado unitariamente.
6. **Cerrar gobierno y release.** Obtener decisión escrita sobre catálogo Access, baseline,
   exclusiones y SQL/DDL; resolver o aceptar SQLFluff/deprecaciones; repetir suites completas y
   auditoría independiente. Solo con cero P1, horizonte integrado y evidencia reproducible se
   evalúa liberar.

**Estado actual después de esta auditoría:** refactor avanzado y automatizado, pero **NO GO** para
liberar. La siguiente acción técnica es centralizar las dos lógicas duplicadas; ninguna acción
debe tocar el perímetro reservado de horizonte.

## Revisión posterior a la centralización de nowcast y expertos

Se esperaron ambos subagentes de implementación hasta su estado final y se revisaron directamente
los archivos cambiados. Sus alcances fueron disjuntos; no tocaron el horizonte reservado.

### Cambios aceptados después de revisión

- `servicios/nowcast.py` es ahora la única implementación del algoritmo adaptativo, selección,
  evaluación y composición del contrato. `screening_adaptive_nowcast.py` conserva la fachada y el
  CLI, con aliases históricos, pero solo define `main` y delega el negocio.
- `servicios/expertos.py` es ahora la única implementación del ajuste experto, optimización,
  replay secuencial, evaluación y contrato. `screening_expert_adjustment_online.py` conserva el
  CLI y aliases públicos/privados para consumidores históricos.
- Se añadieron pruebas de paridad, protección frente a usar R09 contemporáneo como predictor y
  compatibilidad de aliases.
- Los scripts heredados sin `argparse` recibieron un parser mínimo: `--help` ya no inicia
  conexiones, replays ni cálculos. La ejecución sin argumentos conserva su camino anterior.

### Evidencia reproducida después de los cambios

```text
python -m pytest packages/analitica/tests -q       358 passed, 3 skipped, 32088 warnings
pruebas focalizadas nowcast/expert/replay         48 passed
python -m ruff check --no-cache ...               All checks passed
python -m compileall -q ...                       OK
AST scripts↔servicios                             0 imports
importación de scripts                            46 módulos, 0 fallos
python -m analitica.scripts.* --help              46 módulos, 0 fallos
wheel desde copia limpia                          0 .pyc y entry points presentes
```

Las advertencias siguen siendo principalmente deprecaciones de `Timedelta`; no constituyen fallos
funcionales, pero quedan registradas para una actualización controlada de pandas/numpy.

### Pendientes que mantienen el estado NO GO

1. No se pudo construir el Docker real en esta máquina porque Docker Desktop no tenía activo el
   daemon. La combinación Python 3.12/Linux debe validarse en CI o con Docker activo.
2. `constraints-analitica.txt` fija dependencias directas, pero no es un lock transitivo con hashes;
   `python.yml` y `db.yml` aún no aplican una política común. También deben decidirse las versiones
   de `setuptools`, `pyodbc`, `gunicorn`, `rich` y demás extras del monorepo.
3. El `pip check` global no representa un entorno limpio: la instalación previa de ETL solicita
   `pyodbc` y `rich`. La auditoría aislada de analítica/dashboard sí pasó, pero la validación ETL
   completa requiere instalar sus extras en un entorno separado.
4. Faltan ejecuciones reales contra PostgreSQL, Access/Excel, MLflow y una baseline histórica
   fila-por-fila. Las pruebas sintéticas no sustituyen esos contratos.
5. Las decisiones SQL/DDL, SQLFluff, catálogo Access, baseline y versionado de los numerosos
   archivos nuevos siguen requiriendo autorización/ejecución del proceso de entrega; esta sesión
   no hace `git add`, commits ni rollbacks.
6. Falta recibir e integrar la entrega del horizonte paralelo. Su contenido sigue fuera del alcance
   de esta sesión y no se ha certificado desde aquí.

## Plan reestructurado vigente después de la centralización

1. **Reproducibilidad multiplataforma:** aplicar una política de constraints/lock coherente a los
   cuatro workflows, validar Python 3.12/3.13/3.14 y corregir o documentar los extras opcionales.
2. **Entrega limpia:** reconstruir wheel de analítica y dashboard desde copias limpias, ejecutar
   `pip check` e imports aislados y añadir smoke tests de entry points/contenedor.
3. **Horizonte:** esperar la entrega paralela y comparar fachadas, firmas, modelos, fórmulas,
   tolerancias, rutas y tests sin modificar sus archivos.
4. **Infraestructura y datos reales:** levantar PostgreSQL/Docker cuando estén autorizados,
   ejecutar Access/Excel y MLflow con fuentes disponibles y conservar logs de cada prueba; comparar
   contra baseline histórica sin convertir ausencia en cero.
5. **Gobierno y calidad:** resolver decisiones de catálogo, baseline, SQL/DDL y SQLFluff; reducir
   deprecaciones sin alterar resultados; auditar otra vez el worktree completo.
6. **Decisión de release:** solo con cero P1, horizonte integrado, archivos intencionados
   versionados por el responsable y evidencia reproducible se puede declarar GO.

**Estado vigente:** la arquitectura de scripts ya está centralizada y la calidad automatizada está
verde, pero el refactor completo continúa **NO GO** por validaciones de entorno, decisiones de
entrega y horizonte pendiente. El objetivo permanece abierto.

## Auditoría final independiente posterior a la centralización

Se esperaron los dos subagentes finales hasta estado completado y se cruzaron sus dictámenes con
las ejecuciones locales. Ninguno modificó el repositorio ni tocó el horizonte reservado.

### Evidencia final consolidada

- Analítica: `python -m pytest packages/analitica/tests -q` → **358 passed, 3 skipped**.
- Dashboard: `python -m pytest apps/dashboard/tests -q` → **197 passed**.
- Domain + ETL: **56 passed**.
- Ruff global sobre analítica, dashboard, ETL y domain: **All checks passed**.
- `compileall` de Python y `node --check scripts/run.mjs`: correctos.
- AST de producción: **0** imports script→script, **0** servicio→script y 26 imports script→
  servicio desde 20 scripts.
- Importación aislada: 56 módulos correctos. CLI `--help`: 46 scripts, 0 fallos y sin iniciar
  conexiones/cálculos; los scripts heredados sin parser recibieron una protección mínima.
- Ruedas post-centralización de analítica y dashboard construidas desde copias limpias: **0 `.pyc`**;
  el smoke de imports públicos y entry point funciona. La auditoría aislada confirmó `pip check`
  limpio en su entorno propio; el intento local con `--system-site-packages` queda separado porque
  heredó una instalación global externa de ETL.
- El Dockerfile usa constraints, pero el `docker build` local no fue posible: Docker Desktop no
  tenía activo el daemon.

### Hallazgos que impiden el cierre total

1. La centralización completa se logró para nowcast adaptativo y ajuste experto principal, pero no
   para todo `scripts/`: 41 de 46 scripts todavía contienen lógica de negocio propia, incluyendo
   override, residual, intraweek, fund-guard, cross-campaign, fenología GDD y turno/reingreso. No
   deben declararse adaptadores delgados hasta decidir y ejecutar esas extracciones con paridad.
2. El worktree contiene aproximadamente 47 scripts, 12 servicios y 60 tests nuevos sin seguimiento
   Git. La sesión no debe hacer `git add` ni commit, por lo que la trazabilidad queda como tarea
   explícita del responsable del proyecto.
3. La matriz de ejecución no está unificada: paquetes declaran `>=3.12`, dashboard/Docker usan
   3.12, workflows Python/DB usan 3.13 y constraints fueron verificadas localmente en 3.14. Las
   simulaciones Linux de resolución no certifican todavía la combinación objetivo, en particular
   la cadena `shap`/`numba`.
4. `constraints-analitica.txt` fija dependencias directas, no transitivas ni hashes; no fija de
   forma explícita build (`setuptools`) ni extras ETL/deploy (`pyodbc`, `rich`, `gunicorn`). Solo
   dashboard aplica actualmente constraints; Python y DB aún instalan sin política común.
5. No hay evidencia de ejecución real contra Access/Excel, PostgreSQL productivo, MLflow, Docker
   Linux ni baseline histórica fila a fila. Las pruebas sintéticas y el PostgreSQL de CI descrito
   no sustituyen todas esas fuentes reales.
6. Continúan pendientes las decisiones autorizadas de catálogo Access, baseline, SQL/DDL y
   SQLFluff, así como la entrega/equivalencia del horizonte paralelo. No se inspeccionó ni modificó
   `packages/analitica/proyeccion/horizonte/*` ni `pronostico_horizonte.py`.

## Plan reestructurado definitivo de trabajo pendiente

1. **Inventario y priorización de los 41 scripts restantes.** Clasificar cada uno como adaptador,
   algoritmo independiente o persistencia; centralizar primero las lógicas que tienen consumidores
   múltiples y añadir una compuerta AST/alias/paridad por módulo. Mantener cada extracción en un
   alcance disjunto y no cambiar resultados, versiones, rutas, SQL ni semántica as-of.
2. **Matriz de Python y dependencias.** Elegir una matriz oficial (3.12, 3.13 o ambas), validar
   resolución en Linux real y decidir por escrito si `constraints-analitica.txt` será constraints
   directas o lock con transitivas/hashes. Aplicar luego la política elegida a todos los workflows,
   Docker, ETL y deploy; mantener `pyodbc` opcional donde depende del driver Access.
3. **Entrega versionada y reproducible.** El responsable debe incorporar los archivos intencionados
   al control de versiones; después reconstruir ruedas desde checkout limpio, ejecutar `pip check`
   en entornos realmente aislados y verificar entry points, imports y ausencia de bytecode.
4. **Horizonte reservado.** Esperar la entrega paralela y ejecutar una comparación independiente de
   fachada, contratos, modelos, fórmulas, tolerancias, rutas, Ruff, compileall y tests. Esta sesión
   no debe editar esos archivos.
5. **Infraestructura y datos reales.** Con Docker/CI disponibles, ejecutar build y arranque del
   dashboard, PostgreSQL, Access/Excel y MLflow; contrastar persistencia, exportaciones, dashboard,
   scripts y baseline fila a fila con logs separados de pruebas unitarias.
6. **Gobierno y release.** Obtener las decisiones sobre catálogo, exclusiones, baseline y SQL/DDL;
   resolver o aceptar SQLFluff y deprecaciones; repetir la auditoría independiente. Solo con cero
   P1, scripts priorizados centralizados, horizonte integrado, trazabilidad Git y evidencia real
   se puede declarar GO.

**Veredicto de esta ronda:** **NO GO para cierre o release**. El refactor local es funcionalmente
fuerte y las suites automatizadas están verdes, pero aún faltan centralización global, matriz de
dependencias/CI, versionado, infraestructura real, baseline y horizonte. El objetivo permanece
abierto.

## Revisión posterior a fund-guard y cross-campaign

Se esperaron los dos subagentes especializados hasta estado `completed`, se cerraron sus tareas y
se inspeccionaron directamente las fachadas y servicios resultantes. Sus alcances fueron disjuntos:
uno trabajó en el guardia adaptativo por fundo dentro de `nowcast.py` y el otro en
`cross_campaign.py`; ninguno modificó `proyeccion/horizonte` ni `pronostico_horizonte.py`.

### Cambios aceptados

- `servicios/nowcast.py` concentra ahora también guardia por fundo, reconciliación, selección y
  evaluación; `screening_adaptive_nowcast_fund_guard.py` conserva aliases históricos y CLI, y solo
  define `main`.
- `servicios/cross_campaign.py` concentra lectura, panel as-of, modelos, evaluación, selección y
  serialización; `screening_cross_campaign_h1.py` conserva aliases históricos y CLI, y solo define
  `main`.
- Se añadieron pruebas de identidad, paridad, R09 contemporáneo, selección de vintage y semántica
  as-of. Los subagentes reportaron además Ruff, `compileall` y `git diff --check` correctos.

### Evidencia reproducida después de esta ronda

```text
python -m pytest packages/analitica/tests -q       369 passed, 3 skipped, 32104 warnings
python -m pytest apps/dashboard/tests -q           197 passed, 21043 warnings
python -m pytest domain etl -q                     56 passed
python -m ruff check --no-cache ...                All checks passed
python -m compileall -q ...                        OK
node --check scripts/run.mjs                      OK
AST scripts                                      47 módulos, 0 imports script→script,
                                                  26 imports script→servicio
Fachadas sin lógica propia                        7 de 46 scripts ejecutables
```

Las advertencias siguen siendo principalmente deprecaciones de `Timedelta`; no son fallos, pero
deben resolverse de forma controlada y sin alterar resultados. La revisión AST muestra que todavía
hay 39 scripts ejecutables con funciones/clases propias; por tanto, la centralización global aún no
está terminada.

## Plan reestructurado vigente después de esta ronda

1. **Continuar la extracción por prioridad:** delegar en alcances disjuntos la fenología GDD y el
   turno/reingreso multihorizonte, pues son los dos algoritmos grandes restantes con pruebas y
   consumidores claros. Después clasificar los otros 37 scripts por algoritmo independiente,
   persistencia o simple orquestación. En cada extracción: servicio único, fachada compatible,
   aliases, prueba de paridad y compuerta AST. No tocar fórmulas, columnas, versiones, rutas, SQL,
   tablas ni semántica as-of.
2. **Matriz de Python y dependencias:** elegir matriz oficial, resolver Linux real y decidir si
   `constraints-analitica.txt` será constraints directas o lock transitivo con hashes. Aplicar la
   política elegida a workflows, Docker, ETL y deploy; documentar `pyodbc`, `rich` y `gunicorn`.
3. **Entrega trazable:** inventariar archivos intencionados y que el responsable los incorpore al
   control de versiones; reconstruir ruedas desde checkout limpio y validar `pip check`, imports,
   entry points y ausencia de bytecode. Esta sesión no hace `git add` ni commit.
4. **Horizonte reservado:** esperar la entrega paralela; después ejecutar comparación independiente
   de fachada, contratos, modelos, fórmulas, tolerancias, rutas, Ruff, `compileall` y tests sin
   editar esos archivos desde este hilo.
5. **Infraestructura y datos reales:** con Docker/CI disponibles, probar build/arranque, PostgreSQL,
   Access/Excel y MLflow, además de exportaciones, persistencia, dashboard y baseline histórica;
   separar logs reales de pruebas sintéticas.
6. **Gobierno y release:** resolver catálogo, exclusiones, baseline, SQL/DDL, SQLFluff y
   deprecaciones; repetir auditoría independiente. Solo con cero P1, scripts priorizados
   centralizados, horizonte integrado, trazabilidad Git y evidencia real se puede declarar GO.

**Veredicto actualizado:** **NO GO** para cierre o release. Esta ronda amplió la centralización sin
romper las suites, pero el objetivo global permanece abierto y la siguiente acción es extraer los
dos algoritmos priorizados antes de volver a auditar.

## Revisión posterior a fenología GDD y turno/reingreso multihorizonte

Se esperaron ambos subagentes especializados hasta `completed`, se cerraron sus tareas y se
revisaron directamente los archivos entregados. Los alcances fueron disjuntos y no tocaron
`packages/analitica/proyeccion/horizonte/*`, `packages/analitica/proyeccion/pronostico_horizonte.py`,
SQL, dashboard ni el otro algoritmo.

### Cambios aceptados

- `servicios/fenologia_honest.py` concentra el screening GDD/fenología; su script conserva aliases,
  firmas, argumentos CLI, JSON y rutas, y queda como fachada con `main`.
- `servicios/turno_reingreso.py` concentra el algoritmo multihorizonte; su script conserva parser,
  aliases, H1-H6, selección S13-S30, holdout S31-S33, R09, contratos y ruta de salida.
- Se añadieron pruebas de identidad, firma, paridad y compuerta AST para ambos servicios. Las
  pruebas focalizadas conjuntas con fund-guard y cross-campaign pasaron 42 tests.

### Evidencia reproducida después de esta ronda

```text
python -m pytest packages/analitica/tests -q       373 passed, 3 skipped, 32104 warnings
python -m pytest apps/dashboard/tests -q           197 passed, 21043 warnings
python -m pytest domain etl -q                     56 passed
pruebas focalizadas de las cuatro extracciones    42 passed
python -m ruff check --no-cache ...                All checks passed
python -m compileall -q ...                        OK
node --check scripts/run.mjs                      OK
CLI --help de scripts ejecutables                 46 módulos, 0 fallos
AST scripts                                      47 módulos, 0 script→script,
                                                  28 script→servicio,
                                                  12 fachadas delgadas y 34 con lógica propia
```

Las advertencias continúan concentradas en deprecaciones de `Timedelta`; quedan pendientes de una
actualización compatible y controlada. La suite verde acredita ausencia de regresión conocida, no
sustituye todavía pruebas reales contra Access/Excel, PostgreSQL, MLflow, Docker Linux ni baseline.

## Plan reestructurado definitivo de la siguiente ronda

1. **Reducir la lógica restante por dominios:** extraer primero scheduler de lotes activos y deltas
   de parámetros Excel, cada uno en un servicio disjunto con fachada, aliases, paridad y pruebas.
   Después clasificar los otros 32 scripts con lógica propia como algoritmo, persistencia u
   orquestación; no forzar una extracción si no existe consumidor reusable, pero documentar la
   decisión y aislar dependencias.
2. **Matriz de Python y dependencias:** elegir matriz oficial, resolver Linux real y decidir si
   `constraints-analitica.txt` será constraints directas o lock transitivo con hashes. Aplicar la
   política elegida a workflows, Docker, ETL y deploy; documentar `pyodbc`, `rich` y `gunicorn`.
3. **Entrega trazable:** inventariar archivos intencionados y que el responsable los incorpore al
   control de versiones; reconstruir ruedas desde checkout limpio y validar `pip check`, imports,
   entry points y ausencia de bytecode. Esta sesión no hace `git add` ni commit.
4. **Horizonte reservado:** esperar la entrega paralela; después ejecutar comparación independiente
   de fachada, contratos, modelos, fórmulas, tolerancias, rutas, Ruff, `compileall` y tests sin
   editar esos archivos desde este hilo.
5. **Infraestructura y datos reales:** con Docker/CI disponibles, probar build/arranque, PostgreSQL,
   Access/Excel y MLflow, además de exportaciones, persistencia, dashboard y baseline histórica;
   separar logs reales de pruebas sintéticas.
6. **Gobierno y release:** resolver catálogo, exclusiones, baseline, SQL/DDL, SQLFluff y
   deprecaciones; repetir auditoría independiente. Solo con cero P1, scripts priorizados
   centralizados, horizonte integrado, trazabilidad Git y evidencia real se puede declarar GO.

**Veredicto de esta ronda:** **NO GO** para cierre o release. El avance de arquitectura mantiene
las suites verdes y reduce el acoplamiento, pero todavía falta la revisión de los 34 scripts con
lógica propia, además de las puertas de reproducibilidad, infraestructura, datos y entrega.

## Revisión posterior a scheduler y deltas de parámetros Excel

Se esperaron ambos subagentes hasta estado final, se cerraron sus tareas y se revisaron sus archivos
directamente. La discrepancia temporal de Ruff que uno reportó mientras el otro aún escribía se
resolvió repitiendo la comprobación después de ambas entregas: el resultado final fue limpio.

### Cambios aceptados

- `servicios/active_lot_scheduler.py` concentra el scheduler de lotes activos; su script conserva
  aliases, firmas, CLI, selección, as-of, R09 y serialización como fachada.
- `servicios/excel_parameter_deltas.py` concentra inventario Excel, deltas, shrinkage, contrato,
  predicción, selección y serialización; su script conserva aliases, firmas, CLI, rutas, fórmulas y
  semántica as-of.
- Ambos alcances añadieron pruebas de identidad/firma/paridad y compuerta AST. No modificaron
  horizonte, `pronostico_horizonte.py`, SQL, dashboard ni el otro alcance.

### Evidencia reproducida

```text
pruebas focalizadas scheduler + Excel + imports   40 passed
python -m ruff check --no-cache ...                All checks passed
python -m compileall -q packages/analitica         OK
AST scripts                                      47 módulos, 46 ejecutables,
                                                  0 script→script,
                                                  28 script→servicio,
                                                  14 fachadas delgadas,
                                                  32 con lógica propia
```

El inventario se redujo de 34 a 32 scripts ejecutables con funciones/clases propias. El estado no
es todavía GO: la suite completa de analítica y el dashboard deben repetirse después de estos dos
cambios, y siguen abiertas las puertas de dependencias, infraestructura, baseline, versionado y
horizonte reservado.

## Plan reestructurado vigente después de esta ronda

1. **Repetir suites completas y auditar el árbol:** ejecutar analítica, dashboard, domain+ETL,
   Ruff, `compileall`, `--help`, imports y wheel después de las extracciones; comparar el inventario
   AST y corregir cualquier regresión antes de otra delegación.
2. **Reducir la lógica restante por dominios:** clasificar los 32 scripts con lógica propia como
   algoritmo, persistencia u orquestación. Extraer los algoritmos con consumidores reutilizables en
   servicios disjuntos; los scripts de persistencia pueden conservar composición específica, pero
   deben usar servicios, contratos y adaptadores sin duplicar cálculos.
3. **Matriz de Python y dependencias:** elegir matriz oficial, resolver Linux real y decidir si
   `constraints-analitica.txt` será constraints directas o lock transitivo con hashes. Aplicar la
   política elegida a workflows, Docker, ETL y deploy; documentar `pyodbc`, `rich` y `gunicorn`.
4. **Entrega trazable:** inventariar archivos intencionados y que el responsable los incorpore al
   control de versiones; reconstruir ruedas desde checkout limpio y validar `pip check`, imports,
   entry points y ausencia de bytecode. Esta sesión no hace `git add` ni commit.
5. **Horizonte reservado:** esperar la entrega paralela; después ejecutar comparación independiente
   de fachada, contratos, modelos, fórmulas, tolerancias, rutas, Ruff, `compileall` y tests sin
   editar esos archivos desde este hilo.
6. **Infraestructura y gobierno:** con Docker/CI disponibles, probar PostgreSQL, Access/Excel y
   MLflow; resolver catálogo, baseline, SQL/DDL, SQLFluff y deprecaciones. Solo con cero P1,
   scripts priorizados centralizados, horizonte integrado, trazabilidad Git y evidencia real se
   puede declarar GO.

**Veredicto actualizado:** **NO GO** para cierre o release. La arquitectura avanzó a 14 fachadas
delgadas y las validaciones focalizadas están verdes, pero aún deben repetirse las suites completas
y cerrarse 32 scripts con lógica propia y las puertas externas.

## Revisión posterior a la cuarta extracción y rueda limpia

Se esperaron y cerraron los dos subagentes de scheduler y Excel, se revisaron sus archivos y se
repitieron las validaciones desde el árbol resultante. La ejecución de Ruff que un subagente vio
durante una escritura concurrente fue repetida después de la entrega y quedó limpia.

### Evidencia consolidada

```text
python -m pytest packages/analitica/tests -q       399 passed, 3 skipped, 32163 warnings
python -m pytest apps/dashboard/tests -q           197 passed, 21043 warnings
python -m pytest domain etl -q                     56 passed
pruebas focalizadas scheduler + Excel + imports   40 passed
python -m ruff check --no-cache ...                All checks passed
python -m compileall -q ...                        OK
node --check scripts/run.mjs                      OK
CLI --help de scripts ejecutables                 46 módulos, 0 fallos
AST scripts                                      47 módulos, 46 ejecutables,
                                                  0 script→script, 28 script→servicio,
                                                  14 fachadas delgadas y 32 con lógica propia
wheel desde copia limpia                          180 archivos Python,
                                                  0 `.pyc`, cuatro servicios nuevos presentes
```

La rueda construida directamente desde el árbol de pruebas arrastró bytecode, por lo que no se
usó como evidencia; la rueda desde copia temporal sin caches sí pasó el chequeo explícito. Esto
mantiene la comprobación reproducible y evita confundir un artefacto sucio con un fallo de código.

### Plan reestructurado vigente

1. **Continuar por dominios reutilizables:** extraer en alcances disjuntos los siguientes
   algoritmos con mayor oportunidad de reutilización (small-data H1 y temporal-shift online),
   conservar fachadas y contratos y añadir paridad/AST. Los scripts de persistencia se revisarán
   después como orquestadores, sin mover SQL ni publicación hasta tener baseline.
2. **Repetir suites completas tras cada bloque:** analítica, dashboard, domain+ETL, Ruff,
   `compileall`, imports, `--help` y rueda limpia; comparar resultados, columnas, contratos,
   selección, versiones y semántica as-of.
3. **Matriz de Python y dependencias:** elegir matriz oficial, resolver Linux real y decidir si
   `constraints-analitica.txt` será constraints directas o lock transitivo con hashes. Aplicar la
   política elegida a workflows, Docker, ETL y deploy; documentar `pyodbc`, `rich` y `gunicorn`.
4. **Entrega trazable:** inventariar archivos intencionados y que el responsable los incorpore al
   control de versiones; validar ruedas e imports en entornos realmente aislados. Esta sesión no
   hace `git add` ni commit.
5. **Horizonte reservado:** esperar la entrega paralela; después ejecutar comparación independiente
   de fachada, contratos, modelos, fórmulas, tolerancias, rutas, Ruff, `compileall` y tests sin
   editar esos archivos desde este hilo.
6. **Infraestructura y gobierno:** con Docker/CI disponibles, probar PostgreSQL, Access/Excel y
   MLflow; resolver catálogo, baseline, SQL/DDL, SQLFluff y deprecaciones. Solo con cero P1,
   scripts priorizados centralizados, horizonte integrado, trazabilidad Git y evidencia real se
   puede declarar GO.

**Veredicto de esta revisión:** **NO GO**. La refactorización compatible avanza y está cubierta por
pruebas, pero quedan 32 scripts con lógica propia y las puertas externas de reproducibilidad,
versionado, infraestructura, datos reales y horizonte.

## Revisión posterior a small-data H1 y temporal-shift online

Se esperaron ambos subagentes hasta `completed`, se cerraron y se revisaron directamente sus
fachadas, servicios y pruebas. La discrepancia del reporte intermedio de `small_data_h1` se resolvió
repitiendo la suite cuando `temporal_shift` terminó.

### Cambios aceptados y evidencia

- `servicios/small_data_h1.py` centraliza el modelo pequeño H1; la fachada conserva aliases, CLI,
  selección, R09, as-of y ruta de salida.
- `servicios/temporal_shift.py` centraliza el desplazamiento temporal online; la fachada conserva
  aliases, CLI, contrato, R09, as-of y serialización.
- Pruebas focalizadas de ambos módulos e imports públicos: **15 passed**.
- Suite completa analítica: **408 passed, 3 skipped**.
- Dashboard: **197 passed**; domain+ETL: **56 passed**.
- Ruff global y `compileall`: correctos; `--help`: **46 módulos, 0 fallos**.
- AST final: **47 módulos**, **0** imports script→script, **16** fachadas delgadas y **30** scripts
  con lógica propia.

No se modificó el perímetro reservado de horizonte ni SQL. Las advertencias siguen siendo
deprecaciones de `Timedelta`, sin fallos funcionales observados.

## Plan reestructurado vigente después de esta ronda

1. **Continuar el desacoplamiento de algoritmos restantes:** priorizar turno/reingreso H1 y
   small-data por fundo, en alcances disjuntos; luego abordar residual-as-of, delta momentum y
   diagnóstico/replay. Los scripts de persistencia se tratarán como composición/persistencia y no
   se reescribirán sin baseline y contrato de escritura.
2. **Repetir suite completa después de cada bloque:** analítica, dashboard, domain+ETL, Ruff,
   `compileall`, imports, `--help`, AST y rueda limpia; registrar resultados y warnings sin ocultar
   fallos.
3. **Matriz de Python y dependencias:** elegir matriz oficial, resolver Linux real y decidir si
   `constraints-analitica.txt` será constraints directas o lock transitivo con hashes. Aplicar la
   política elegida a workflows, Docker, ETL y deploy; documentar `pyodbc`, `rich` y `gunicorn`.
4. **Entrega trazable:** inventariar archivos intencionados y que el responsable los incorpore al
   control de versiones; validar ruedas e imports en entornos realmente aislados. Esta sesión no
   hace `git add` ni commit.
5. **Horizonte reservado:** esperar la entrega paralela; después ejecutar comparación independiente
   de fachada, contratos, modelos, fórmulas, tolerancias, rutas, Ruff, `compileall` y tests sin
   editar esos archivos desde este hilo.
6. **Infraestructura y gobierno:** con Docker/CI disponibles, probar PostgreSQL, Access/Excel y
   MLflow; resolver catálogo, baseline, SQL/DDL, SQLFluff y deprecaciones. Solo con cero P1,
   scripts priorizados centralizados, horizonte integrado, trazabilidad Git y evidencia real se
   puede declarar GO.

**Veredicto actualizado:** **NO GO**. La centralización funcional continúa estable y ya hay 16
fachadas delgadas, pero el inventario aún tiene 30 scripts con lógica propia y faltan las puertas
externas de entrega y operación.

## Revisión posterior a turno H1 y small-data por fundo

Se esperaron ambos subagentes hasta `completed`, se cerraron y se revisaron directamente sus
entregas. Los scripts quedaron como fachadas compatibles y los servicios nuevos no tocaron el
servicio previo de small-data ni el servicio multihorizonte. El perímetro reservado de horizonte,
`pronostico_horizonte.py`, SQL y dashboard no fue modificado en esta ronda.

### Evidencia reproducida

```text
pruebas focalizadas H1 + small-data + imports   14 passed
python -m pytest packages/analitica/tests -q    416 passed, 3 skipped, 32403 warnings
python -m ruff check --no-cache ...              All checks passed
python -m compileall -q ...                      OK
python -m pytest apps/dashboard/tests -q         197 passed
python -m pytest domain etl -q                   56 passed
CLI --help de scripts ejecutables                46 módulos, 0 fallos
AST scripts                                      47 módulos, 0 script→script,
                                                  18 fachadas delgadas y 28 con lógica propia
```

Las advertencias permanecen concentradas en deprecaciones de `Timedelta`; no han producido fallos,
pero quedan como deuda técnica controlada.

## Plan reestructurado vigente después de esta ronda

1. **Continuar extracción por algoritmos:** delegar `residual_asof` y `param_delta_momentum` en
   servicios disjuntos, con paridad, aliases, pruebas y compuerta AST. Después revisar los 26
   scripts restantes, distinguiendo algoritmo, diagnóstico y persistencia.
2. **No forzar persistencia:** los scripts que escriben/publican deben conservar composición de
   contrato, transacciones y SQL hasta disponer de baseline y pruebas de integración; sí deben
   consumir servicios y no duplicar cálculos puros.
3. **Repetir suite completa por bloque:** analítica, dashboard, domain+ETL, Ruff, `compileall`,
   imports, `--help`, AST y rueda limpia; registrar warnings y cualquier diferencia de resultados.
4. **Matriz de Python y dependencias:** elegir matriz oficial, resolver Linux real y decidir si
   `constraints-analitica.txt` será constraints directas o lock transitivo con hashes. Aplicar la
   política elegida a workflows, Docker, ETL y deploy; documentar `pyodbc`, `rich` y `gunicorn`.
5. **Entrega y horizonte:** versionar por el proceso responsable, esperar la entrega del horizonte
   paralelo y certificar allí fachada, contratos, modelos, fórmulas, tolerancias, rutas, Ruff,
   `compileall` y tests sin editar esos archivos desde este hilo.
6. **Infraestructura y gobierno:** con Docker/CI disponibles, probar PostgreSQL, Access/Excel y
   MLflow; resolver catálogo, baseline, SQL/DDL, SQLFluff y deprecaciones. Solo con cero P1,
   scripts priorizados centralizados, horizonte integrado, trazabilidad Git y evidencia real se
   puede declarar GO.

**Veredicto de esta revisión:** **NO GO**. El bloque fue funcionalmente seguro y deja 18 fachadas
delgadas, pero aún faltan algoritmos por aislar y todas las puertas de entrega/operación.

## Revisión posterior a residual-asof

Se centralizó exclusivamente el screening residual as-of. La fachada
`packages/analitica/scripts/screening_residual_asof.py` conserva los aliases públicos y privados
históricos, firmas, `--salida`, serialización y rutas; la lógica quedó en
`packages/analitica/servicios/residual_asof.py`. Se añadieron pruebas de identidad, firma, paridad
de agregación/comparación/score, malla de configuraciones, CLI y compuerta AST. No se modificaron
el horizonte reservado, `pronostico_horizonte.py`, SQL, dashboard ni `param_delta_momentum`.

### Evidencia reproducida

```text
python -m pytest --version                                  pytest 9.1.1
pruebas focalizadas residual-asof + imports públicos         7 passed
Ruff del alcance residual-asof                              All checks passed
python -m compileall -q packages/analitica                  OK
CLI --help residual-asof                                    OK
```

La comprobación global de Ruff sigue mostrando cinco errores E501 preexistentes en
`test_screening_param_delta_momentum.py`, un alcance explícitamente excluido de esta tarea; no se
modificó ese archivo. La evidencia de esta ronda no cambia el veredicto general: continúan
pendientes la integración del horizonte paralelo, la decisión de dependencias/matriz Python,
infraestructura real, baseline/SQL y trazabilidad Git.

## Revisión posterior a router de parámetros lagged y delta replay

Se esperaron ambos subagentes hasta `completed`, se cerraron y se revisaron sus entregas desde el
hilo principal. El primer alcance centralizó `screening_router_parametros_lagged` en
`servicios/router_parametros_lagged.py`; el segundo centralizó `screening_parameter_delta_replay`
en `servicios/parameter_delta_replay.py`. En ambos casos se conservaron aliases públicos y
privados, firmas, CLI, `--salida`, serialización y rutas, y se añadieron pruebas de identidad,
paridad, CLI y AST. No se modificaron `proyeccion/horizonte/*`,
`proyeccion/pronostico_horizonte.py`, SQL, dashboard ni workflows.

### Evidencia reproducida después de cerrar ambos subagentes

```text
pruebas focalizadas router + delta + imports públicos   32 passed
python -m pytest packages/analitica/tests -q            468 passed, 3 skipped, 32411 warnings
python -m pytest apps/dashboard/tests -q                197 passed, 21043 warnings
python -m pytest domain etl -q                          56 passed
python -m ruff check --no-cache ...                     All checks passed
python -m compileall -q ...                             OK
AST scripts                                             47 módulos, 46 ejecutables,
                                                         0 script→script, 21 fachadas delgadas,
                                                         25 con lógica propia
```

Las advertencias siguen siendo principalmente deprecaciones de `Timedelta`. Apareció además una
`FutureWarning` aislada en `servicios/param_delta_momentum.py` por `fillna` sobre dtype objeto; no
rompe hoy, pero queda registrada como deuda para una corrección aislada con prueba de paridad.

## Plan reestructurado vigente después de esta ronda

1. **Continuar el desacoplamiento por familias restantes:** priorizar
   `screening_lagged_parameters_horizons.py` y `screening_parameter_delta_replay.py` ya queda
   cerrado; por tanto el siguiente bloque debe elegir solo scripts todavía no centralizados,
   empezando por `screening_lagged_parameters_horizons.py` y un diagnóstico/replay disjunto, sin
   mezclar scripts de persistencia. El contador AST actual identifica 25 módulos con lógica propia;
   no se considerarán todos candidatos a extracción automática: diagnóstico, composición y
   persistencia requieren contratos y baseline separados.
2. **Repetir la compuerta tras cada pareja:** pruebas focalizadas, suite analítica completa,
   dashboard, domain+ETL, Ruff, `compileall`, imports públicos, `--help`, AST y rueda limpia.
   Cualquier reporte de subagente se tratará como provisional hasta esta repetición principal.
3. **Corregir deuda pequeña sin alterar resultados:** estudiar el `FutureWarning` de
   `param_delta_momentum` y las deprecaciones de `Timedelta` únicamente con pruebas de paridad;
   no cambiar fórmulas, modelos, versiones, rutas, SQL, tablas, escenarios ni semántica as-of.
4. **Matriz y entrega reproducibles:** decidir Python oficial (3.12/3.13/3.14), convertir si
   procede las constraints directas en lock transitivo con hashes, aplicarlas a workflows/Docker y
   validar un wheel sin bytecode en entorno aislado. Esta sesión no hace `git add` ni commit.
5. **Horizonte paralelo:** esperar la entrega externa y auditarla de forma independiente; este
   hilo no edita sus archivos. Después se ejecutarán fórmulas, tolerancias, modelos, imports,
   rutas, Ruff, `compileall` y pruebas antes de considerarlo integrado.
6. **Infraestructura y gobierno:** habilitar Docker/CI y ejecutar PostgreSQL, Access/Excel y
   MLflow reales; resolver catálogo, baseline, SQL/DDL, SQLFluff y deprecaciones. Solo con cero
   P1, centralización suficiente, horizonte integrado, trazabilidad Git y evidencia real se puede
   declarar GO.

**Veredicto de esta revisión:** **NO GO**. Los dos flujos nuevos quedaron centralizados y las
suites por paquete permanecen verdes, pero siguen pendientes 25 scripts con lógica propia,
la matriz reproducible, la validación externa, la entrega Git, la infraestructura real y el
horizonte reservado.

### Compuerta adicional de la suite raíz

Se ejecutó `python -m pytest -q` después de cerrar y revisar ambos subagentes:
**720 passed, 3 skipped y 1 failed**. La única falla es
`domain/tests/test_fronteras.py::test_el_paquete_importa_por_si_solo`, con
`ModuleNotFoundError: No module named 'aquanqa_domain'`. No es una regresión observada en los
paquetes: `python -m pytest domain etl -q` entrega **56 passed**; la suite raíz usa este intérprete
sin instalar `domain` como paquete. La compuerta queda abierta hasta reproducirla mediante una
instalación editable limpia, no ocultándola con `PYTHONPATH`.

## Nueva estructura de trabajo después de la compuerta raíz

1. **Siguiente extracción funcional:** centralizar `screening_lagged_parameters_horizons.py` y
   `screening_excel_assisted.py` en dos servicios disjuntos, preservando la frontera Access/Excel,
   aliases, contratos as-of, CLI y serialización. No tocar persistencia ni el horizonte reservado.
2. **Revisión después de la pareja:** esperar los dos estados `completed`, cerrar ambos, inspeccionar
   fachadas/servicios y comprobar paridad, tests, AST e imports desde el hilo principal. Ejecutar
   las cuatro suites por paquete más la suite raíz cuando el bloque esté integrado.
3. **Instalación reproducible:** repetir la suite raíz en un entorno donde `domain` esté instalado
   (`python -m pip install -e domain`), y dejar separado el resultado de la instalación mínima de
   cada paquete. No aceptar un verde obtenido únicamente por modificar `PYTHONPATH`.
4. **Después de las extracciones:** corregir warnings de pandas solo en cambios aislados con pruebas
   de igualdad; completar la rueda limpia, el `--help` de los 46 ejecutables y la auditoría de
   scripts restantes antes de decidir nuevas parejas.

## Revisión posterior a lagged horizons y Excel assisted

Se esperaron ambos subagentes hasta `completed`, se cerraron y se revisaron sus cambios desde el
hilo principal. `screening_lagged_parameters_horizons.py` quedó respaldado por
`servicios/lagged_parameters_horizons.py`; `screening_excel_assisted.py` quedó respaldado por
`servicios/excel_assisted.py`, manteniendo la ruta opcional de Access/Excel cuando no existen
`pyodbc` o `python-calamine`. Las fachadas, aliases, firmas, CLI, `--salida`, serialización y
contratos as-of se conservaron. El perímetro `proyeccion/horizonte/*`,
`proyeccion/pronostico_horizonte.py`, SQL, dashboard y workflows permaneció sin edición en esta
ronda.

### Evidencia reproducida

```text
foco de la pareja + imports públicos/ligeros       17 passed
python -m pytest packages/analitica/tests -q       482 passed, 3 skipped, 32411 warnings
python -m pytest apps/dashboard/tests -q           197 passed, 21043 warnings
python -m pytest domain etl -q                     56 passed
python -m pytest -q (domain instalado editable)    735 passed, 3 skipped, 53454 warnings
python -m ruff check --no-cache ...                All checks passed
python -m compileall -q ...                        OK
CLI --help                                         46 módulos, 0 fallos
AST scripts                                        47 módulos, 46 ejecutables,
                                                     0 script→script, 23 fachadas delgadas,
                                                     23 con lógica propia
rueda limpia                                       190 módulos Python, 0 bytecode
```

La suite raíz ya no presenta el fallo de `aquanqa_domain` porque se ejecutó tras
`python -m pip install -e domain`; esa instalación debe formar parte del procedimiento CI/local.
Las advertencias de pandas y `Timedelta` siguen registradas como deuda, no como fallos.

## Plan reestructurado vigente después de esta ronda

1. **Siguiente bloque funcional, todavía no persistente:** delegar en alcances disjuntos
   `build_expert_parameter_h1_panel.py` y `build_lagged_parameter_h1_panel.py`. Cada subagente
   debe extraer solo su lógica a un servicio, conservar la fachada y probar paridad; no tocar el
   horizonte reservado, SQL, dashboard, workflows ni scripts de persistencia.
2. **Revisión principal obligatoria:** esperar los dos estados `completed`, cerrar ambos y volver a
   ejecutar desde este hilo focalizadas, suite analítica, dashboard, domain+ETL, suite raíz con
   instalación editable, Ruff, `compileall`, imports, `--help`, AST y rueda limpia.
3. **Clasificación de los 21 restantes con lógica propia después de esa pareja:** separar
   diagnóstico/reporte, composición de replay, persistencia y validación externa. Solo extraer
   lógica pura cuando exista prueba de paridad; para persistencia exigir antes baseline de escritura
   y contrato de transacción.
4. **Warnings y reproducibilidad:** arreglar de forma aislada `param_delta_momentum` y las
   deprecaciones de `Timedelta`, con igualdad de resultados; documentar instalación de `domain`,
   versión oficial de Python, lock/constraints, `pyodbc` y `python-calamine`.
5. **Horizonte e infraestructura:** esperar la entrega paralela y auditarla sin editarla; después
   habilitar Docker/CI y validar PostgreSQL, Access/Excel y MLflow reales, junto con SQL/DDL,
   SQLFluff, baseline y trazabilidad Git. El estado se mantiene **NO GO** hasta cerrar esas puertas.

## Revisión posterior a constructores de panel H1

Se esperaron ambos subagentes hasta `completed`, se cerraron y se revisaron directamente sus
fachadas y servicios. `build_expert_parameter_h1_panel.py` y
`build_lagged_parameter_h1_panel.py` conservan aliases, argumentos, `--salida`, serialización,
lectura opcional Excel/Access y semántica as-of; la lógica quedó en servicios separados. No se
modificaron horizonte, SQL, dashboard ni workflows.

### Evidencia reproducida

```text
foco de la pareja + imports públicos/ligeros       11 passed
python -m pytest packages/analitica/tests -q       490 passed, 3 skipped, 32411 warnings
Ruff global                                         All checks passed
compileall global                                   OK
CLI --help                                          46 módulos, 0 fallos
AST scripts                                         47 módulos, 46 ejecutables,
                                                     0 script→script, 25 fachadas delgadas,
                                                     21 con lógica propia
rueda limpia previa                                 190 módulos Python, 0 bytecode
suite raíz previa con domain instalado             735 passed, 3 skipped
```

La ejecución de los constructores no requiere cargar `pyodbc` ni `python-calamine` de forma eager.
Las advertencias continúan siendo deuda de pandas/`Timedelta`; no hay fallos funcionales en la
suite analítica.

## Plan reestructurado vigente después de esta ronda

1. **Clasificar los 21 scripts restantes con lógica propia:** continuar solo con diagnósticos,
   validadores y composición que puedan probarse sin escribir en base. Priorizar
   `diagnostico_v2_vs_nowcast_horizontes.py` y `evaluar_ocurrencia_v3.py` en alcances disjuntos,
   o reemplazar uno por un diagnóstico equivalente si la revisión de contrato demuestra que no
   tiene API reusable.
2. **No extraer persistencia todavía:** `persistir_*`, `replay_campania_completo.py` y
   `certificar_releases_replay.py` quedan detrás de un baseline de escritura, transacciones,
   release/versionado y pruebas PostgreSQL; la fachada puede permanecer como composición.
3. **Después de la pareja siguiente:** repetir espera a `completed`, cierre, inspección directa,
   foco, analítica completa, dashboard, domain+ETL, suite raíz instalada, Ruff, `compileall`,
   imports, `--help`, AST y rueda limpia.
4. **Calidad y entrega:** aislar la corrección de warnings con paridad, documentar constraints/lock,
   validar `domain` instalado, probar Docker/CI y ejecutar las integraciones Access/Excel,
   PostgreSQL y MLflow cuando estén disponibles. Mantener **NO GO** hasta cerrar esas puertas y
   recibir la entrega del horizonte reservado.

## Auditoría posterior de evaluar_ocurrencia_v3

La primera entrega de `evaluar_ocurrencia_v3` no tenía informe final utilizable porque el agente
original quedó `not_found`. Se inspeccionó el árbol y se asignó un revisor especializado que sí
terminó en `completed`. La auditoría encontró dos incompatibilidades y las corrigió dentro del
alcance: faltaban los aliases privados históricos `_emisiones_completas` y `_normalizar_modelo`, y
la fachada había agregado un `argparse` sin opciones que rechazaba argumentos que el CLI histórico
ignoraba. Se añadieron pruebas para ambos casos.

### Evidencia posterior a la auditoría

```text
foco diagnóstico + evaluación + imports públicos    11 passed
python -m pytest packages/analitica/tests -q        499 passed, 3 skipped, 32411 warnings
Ruff de alcance y global                            All checks passed
compileall                                          OK
```

La corrección preserva el orden de los cuatro modelos, campaña, `horizonte_semanas=1`,
`max_cortes=None`, normalización, replay/as-of y serialización. No se tocaron horizonte,
`pronostico_horizonte.py`, SQL, dashboard ni workflows.

## Plan reestructurado vigente después de la auditoría

1. **Aceptar el patrón de auditoría como obligatorio:** ninguna entrega de subagente se acepta por
   su propio reporte; el hilo principal debe revisar aliases públicos y privados, tolerancia CLI,
   paridad, AST, imports y suites. Si un agente no entrega informe final, reasignar una auditoría
   del mismo alcance antes de contabilizar el trabajo.
2. **Continuar con los módulos restantes:** quedan 19 scripts con lógica propia según AST, pero se
   deben clasificar antes de extraer. La siguiente pareja candidata es `buscar_candidatos_replay.py`
   y `diagnostico_ocurrencia_v3.py`, por ser análisis/composición sin persistencia; no tocar aún
   `persistir_*`, `certificar_releases_replay.py` ni el horizonte reservado.
3. **Compuertas por bloque:** esperar ambos `completed`, cerrar, revisar directamente y repetir
   foco, suite analítica, dashboard, domain+ETL, suite raíz con `domain` instalado, Ruff,
   `compileall`, imports, `--help`, AST y rueda limpia.
4. **Cierre de reproducibilidad e infraestructura:** conservar la evidencia de `domain` instalado,
   decidir Python oficial y lock/constraints, probar Docker/CI, PostgreSQL, Access/Excel y MLflow
   reales, y resolver baseline/SQL/DDL/SQLFluff. El estado sigue **NO GO** hasta integrar horizonte,
   trazabilidad Git y esas pruebas externas.

## Revisión posterior a buscar candidatos y completar replay

Se esperaron ambos subagentes hasta `completed`, se cerraron y se revisaron sus fachadas y servicios
desde el hilo principal. `buscar_candidatos_replay.py` y `completar_replay_c2025_r09.py` conservan
aliases públicos/privados, firmas, CLI, serialización, rutas, modelos y reglas as-of; la lógica
reutilizable quedó en servicios separados. No se editaron horizonte, SQL, dashboard ni workflows.

### Evidencia reproducida

```text
foco de la pareja + evaluación/diagnóstico previos  21 passed
python -m pytest packages/analitica/tests -q       509 passed, 3 skipped, 32411 warnings
AST scripts                                        47 módulos, 46 ejecutables,
                                                     0 script→script, 29 fachadas delgadas,
                                                     17 con lógica propia
```

La auditoría previa de `evaluar_ocurrencia_v3` se mantiene como compuerta de compatibilidad: los
aliases privados y la tolerancia de CLI ya están cubiertos. Los warnings siguen siendo deuda de
pandas/`Timedelta`, no fallos.

## Plan reestructurado vigente después de esta ronda

1. **Siguiente pareja no persistente:** extraer `extract_excel_parameter_transitions.py` y
   `validate_intraweek_nowcast_external.py` a servicios disjuntos. Preservar lectores, contratos de
   Excel, JSON/CSV, CLI, serialización, rutas, `as-of` y el comportamiento cuando falten drivers o
   fuentes externas.
2. **Auditoría posterior obligatoria:** esperar ambos `completed`, cerrar, revisar aliases públicos
   y privados, tolerancia CLI, paridad de columnas/orden/tipos, imports y no invasión del horizonte;
   luego repetir focalizadas y suite analítica desde el hilo principal.
3. **Después de los flujos externos:** abordar `loop_forecast_horizontes.py` y los scripts de
   turno/reingreso solo con contratos de datos sintéticos; dejar `persistir_*`, certificación y
   replay con escritura detrás de baseline PostgreSQL/MLflow.
4. **Cierre integral:** volver a ejecutar dashboard, domain+ETL, suite raíz con `domain` instalado,
   Ruff, `compileall`, `--help`, AST y rueda limpia; resolver warnings, constraints/lock, CI/Docker,
   integraciones reales y la entrega paralela del horizonte antes de cambiar **NO GO**.

## Revisión posterior a extract_excel_parameter_transitions y validate_intraweek_nowcast_external

Se esperaron ambos subagentes hasta `completed`, se cerraron y se revisaron los cambios desde el
hilo principal. Las fachadas mantienen CLI, aliases, serialización, orden de columnas, contratos de
Excel/JSON/CSV y comportamiento tolerante ante drivers o fuentes externas ausentes; las operaciones
reutilizables quedaron en servicios separados. No se tocaron horizonte, `pronostico_horizonte.py`,
SQL, dashboard ni workflows.

### Evidencia reproducida

```text
foco de la pareja + imports públicos                  38 passed
python -m pytest packages/analitica/tests -q         545 passed, 3 skipped, 32411 warnings
fachadas/servicios                                     139/705 y 49/269 líneas
imports ejecutables entre scripts                     0 coincidencias
Ruff/compileall/ayudas CLI                            OK según revisión de la pareja
```

La rueda limpia quedó construida en `.tmp/wheel-clean-20260828-final2`; la comprobación final debe
usar los nombres instalables reales (`analitica/...`, no `aquanqa_analitica/...`). El recuento AST
debe distinguir `build_parser` de lógica de negocio para no penalizar una fachada por declarar su
parser. Los warnings continúan siendo deuda técnica de `Timedelta`/pandas y no fallos de esta ronda.

## Plan reestructurado vigente después de esta ronda

1. **Siguiente pareja de composición no persistente:** extraer `loop_forecast_horizontes.py` y
   `ver_comparaciones.py` a servicios disjuntos, preservando fórmulas, agregaciones, filtros,
   orden de salida, CLI y tolerancia histórica. No tocar `screening_router_horizonte.py` mientras
   siga pendiente la entrega paralela de horizonte.
2. **Auditoría posterior obligatoria:** esperar ambos subagentes hasta `completed`, cerrarlos,
   revisar directamente fachadas/servicios y ejecutar foco, suite analítica, imports, AST, Ruff,
   `compileall` y `--help`. Después repetir dashboard, domain+ETL y, por bloques, la suite raíz.
3. **Bloque de persistencia separado:** abordar `persistir_*`, `replay_*` y certificación solo con
   una matriz explícita de escrituras, transacciones, idempotencia, SQL, tablas, `as-of`, MLflow y
   baseline; cualquier cambio de esquema o contrato queda fuera de una refactorización ciega.
4. **Cierre integral:** completar scripts restantes, integrar y auditar el horizonte reservado,
   fijar Python oficial y lock/constraints, resolver Docker/CI, y obtener evidencia real de
   PostgreSQL, Access/Excel y MLflow. El estado permanece **NO GO** hasta cerrar esas compuertas.

## Revisión posterior a loop_forecast_horizontes y ver_comparaciones

Se esperaron ambos subagentes hasta `completed`, se cerraron y se inspeccionaron directamente sus
fachadas, servicios y pruebas. La lógica del bucle conserva fórmulas, agregaciones, filtros,
campaña, `desarrollo_hasta`, as-of, rutas y JSON; el visor conserva consultas, tablas, etiquetas,
versiones, orden y opciones CLI. Las dependencias `pyodbc`/`python_calamine` siguen siendo lazy.
No se tocaron horizonte, `pronostico_horizonte.py`, SQL, dashboard, workflows ni el plan hasta
esta revisión.

### Evidencia reproducida desde el hilo principal

```text
foco de la pareja + imports públicos                  22 passed
loop: fachada/servicio                                 63/491 líneas
comparaciones: fachada/servicio                         54/393 líneas
imports ejecutables entre scripts                       0 coincidencias
rueda limpia                                           198 .py, 0 bytecode
```

La suite analítica completa fue reportada por el agente como `565 passed, 3 skipped`, pero queda
como compuerta pendiente de repetir desde el hilo principal tras esta pareja. También queda
pendiente repetir dashboard, domain+ETL, estática completa y suite raíz en el bloque de cierre.

## Plan reestructurado vigente después de esta ronda

1. **Cerrar evidencia de esta pareja:** ejecutar desde el hilo principal `python -m pytest
   packages/analitica/tests -q`, después repetir dashboard, domain+ETL, Ruff, `compileall`, ayudas
   CLI, AST y rueda limpia. No aceptar cifras reportadas por agentes sin esa repetición.
2. **Siguiente bloque no persistente y disjunto:** auditar/refactorizar `demo_auditoria_en_vivo.py`
   junto con `screening_turno_reingreso_multihorizon.py` solo si sus contratos no se solapan; si
   hay acoplamiento, procesarlos en rondas separadas. Mantener fuera `screening_router_horizonte.py`
   mientras el trabajo paralelo de horizonte siga abierto.
3. **Bloque de persistencia con control reforzado:** tratar `persistir_*`, `replay_*` y
   `certificar_releases_replay.py` únicamente con una matriz de escrituras, transacciones,
   idempotencia, SQL/tablas, `as-of`, MLflow y baseline; no extraer por volumen de líneas.
4. **Cierre integral:** incluir scripts restantes, horizonte reservado, dashboard y CI; fijar Python
   oficial/lock, y obtener pruebas reales de PostgreSQL, Access/Excel, MLflow y Docker. El estado
   permanece **NO GO** hasta cerrar todas las compuertas de equivalencia y trazabilidad.

## Revisión principal de la pareja loop/ver_comparaciones

La repetición desde el hilo principal confirmó `565 passed, 3 skipped, 32411 warnings` en la suite
analítica después de ambos cambios. También quedaron verdes las pruebas de dashboard (`197 passed`),
domain+ETL (`56 passed`) y la rueda limpia (`198` archivos Python, `0` bytecode). Los warnings son
deprecaciones existentes de pandas/NumPy; no se altera su semántica en esta ronda.

## Plan reestructurado vigente para la siguiente ronda

1. **Siguiente pareja disjunta:** extraer `demo_auditoria_en_vivo.py` y el screening legado
   `screening_turno_reingreso.py` a servicios separados. El demo debe eliminar el `sys.path` absoluto
   y conservar exactamente la demostración matemática; el screening debe conservar globales,
   configuraciones, calendario, as-of, métrica, JSON y CLI.
2. **Auditoría posterior:** esperar ambos agentes hasta `completed`, cerrar, inspeccionar servicios y
   fachadas, y ejecutar pruebas focalizadas desde el hilo principal. Repetir la suite analítica y
   revisar scripts→scripts, AST, imports opcionales y la reserva de horizonte.
3. **No mezclar familias:** `screening_turno_reingreso_h1.py` y
   `screening_turno_reingreso_multihorizon.py` ya usan servicios especializados; no reabrirlos sin
   una prueba de contrato que demuestre que el screening legado es compatible con esa familia.
4. **Después:** tratar persistencia/replay/certificación con matriz de efectos; cerrar infraestructura,
   CI, constraints/lock, integraciones reales y entrega del horizonte. Mantener **NO GO** hasta
   demostrar equivalencia conjunta de packages, dashboard y CI.

## Revisión posterior a demo_auditoria_en_vivo y screening_turno_reingreso

Se esperaron ambos subagentes hasta `completed`, se cerraron y se revisaron directamente los
cambios. El demo conserva las tres llamadas a `ajustar_lote`, los datos, mensajes y resultados
matemáticos, pero elimina el `sys.path` absoluto. El screening legado conserva `Config`, globales,
calendario, as-of, configuraciones, métricas, `schema`, JSON, campañas y opciones `--micro`/`--salida`.
No se usó ni modificó el servicio de turno/reingreso ya existente para evitar mezclar contratos.

### Evidencia reproducida desde el hilo principal

```text
foco de la pareja + imports públicos                   10 passed
demo: fachada/servicio                                  15/108 líneas
screening: fachada/servicio                              56/302 líneas
sys.path absoluto en el demo                             0 coincidencias
imports ejecutables entre scripts                        0 coincidencias
```

La suite analítica completa fue reportada por el agente como `826 passed, 3 skipped`; debe repetirse
desde el hilo principal antes de contabilizar la ronda. También siguen pendientes las compuertas
externas y la validación del global privado `_COSECHA_GLOBAL` si algún consumidor histórico lo asigna
directamente en la fachada.

## Plan reestructurado vigente después de esta ronda

1. **Cerrar evidencia:** repetir `python -m pytest packages/analitica/tests -q` desde este hilo y
   luego actualizar los conteos conjuntos; ejecutar dashboard, domain+ETL, Ruff, `compileall`,
   ayudas CLI, AST e integridad de la rueda.
2. **Siguiente bloque no persistente:** auditar y refactorizar `screening_turno_reingreso_h1.py`
   solo si requiere cambios —hoy ya es fachada— y revisar `screening_cross_campaign_h1.py`,
   `screening_intraweek_nowcast.py` o `screening_residual_state_online.py` en rondas disjuntas,
   priorizando primero las que aún contengan lógica propia.
3. **Bloque crítico de persistencia:** separar `persistir_*`, `replay_*` y
   `certificar_releases_replay.py` con contratos de escritura, transacciones, idempotencia,
   tablas/SQL, `as-of`, MLflow y baseline; no se aceptará una simple reducción de líneas.
4. **Cierre integral:** incorporar el horizonte reservado, dashboard y CI; fijar Python oficial y
   lock/constraints, resolver Docker y obtener pruebas reales PostgreSQL/Access/Excel/MLflow. Seguir
   en **NO GO** hasta la equivalencia conjunta y la trazabilidad Git.

## Revisión principal de demo y screening legado

La repetición desde el hilo principal confirmó `573 passed, 3 skipped, 33377 warnings` en la suite
analítica después de esta ronda. La pareja focalizada pasó `10` pruebas; las fachadas quedaron en
`15` y `56` líneas frente a servicios de `108` y `302`, sin `sys.path` absoluto ni imports
ejecutables entre scripts. La evidencia de dashboard/domain+ETL y rueda permanece verde de la ronda
anterior; se repetirá en el cierre conjunto.

## Plan reestructurado vigente después de esta ronda

1. **Siguiente clasificación por riesgo:** revisar los scripts no persistentes que aún conservan
   lógica propia (`screening_cross_campaign_h1.py`, `screening_intraweek_nowcast.py`,
   `screening_residual_state_online.py` y, si corresponde, `screening_router_parametros_lagged.py`).
   Solo se emparejarán archivos con servicios y contratos disjuntos; no se tocará
   `screening_router_horizonte.py` mientras el horizonte paralelo esté abierto.
2. **Auditoría obligatoria por pareja:** esperar todos los subagentes hasta `completed`, revisar
   aliases y fachadas, ejecutar pruebas focalizadas desde este hilo y repetir suite analítica,
   imports, AST, Ruff, `compileall` y CLI. Una cifra del subagente no es aceptación.
3. **Persistencia después de estabilizar lo puro:** `persistir_*`, `replay_*` y
   `certificar_releases_replay.py` requieren una matriz de efectos (SQL, tablas, transacciones,
   idempotencia, as-of, MLflow, archivos y rutas) y pruebas contra dobles antes de cualquier cambio.
4. **Cierre integral:** dashboard, domain+ETL, suite raíz con `domain` editable instalado, rueda,
   CI/Docker, Python oficial/lock y bases externas; integrar y auditar el horizonte. Mantener **NO GO**
   hasta resolver todas las compuertas de equivalencia y trazabilidad.

## Revisión principal de screening legado y demo

La suite analítica repetida desde el hilo principal confirmó `573 passed, 3 skipped, 33377 warnings`.
La pareja añadió cobertura focalizada y eliminó una ruta absoluta del demo sin modificar fórmulas,
resultados, rutas, SQL ni horizonte. La clasificación AST actual muestra que los scripts restantes
con lógica propia son principalmente de persistencia/certificación; las demás fachadas ya delegan en
servicios.

## Plan reestructurado vigente para persistencia

1. **Siguiente pareja controlada:** extraer `certificar_releases_replay.py` y
   `persistir_hibrido_parametros_asof.py` a servicios disjuntos, manteniendo SQL, tablas, contratos,
   versiones, `as-of`, hashes, idempotencia, transacciones, dry-run, códigos de salida y CLI. Los
   agentes deben usar dobles de conexión y no ejecutar escrituras reales.
2. **Auditoría posterior:** esperar ambos agentes hasta `completed`, cerrar y revisar cada query,
   `commit`, excepción, alias histórico y fachada. Ejecutar pruebas focalizadas desde el hilo
   principal; una suite verde del agente no basta.
3. **Bloques siguientes:** procesar por separado los demás `persistir_*`, `replay_*` y
   certificación, sin refactorizar SQL/DDL ni cambiar el orden de efectos. El horizonte reservado y
   `screening_router_horizonte.py` permanecen fuera del alcance.
4. **Cierre:** repetir suites de packages, dashboard, domain+ETL y raíz; Ruff, compileall, AST,
   ayudas, rueda, CI/Docker, Python oficial/lock e integraciones reales PostgreSQL/Access/Excel/MLflow.
   Mantener **NO GO** hasta contar con evidencia conjunta y trazabilidad Git.

## Revisión posterior a certificación y HibridoParametrosAsOf

Se esperaron ambos subagentes hasta `completed`, se cerraron y se revisaron directamente los
cambios. La certificación mantiene SQL, contratos, hashes, estados, idempotencia, orden de efectos,
`commit`/`rollback`, `--apply` y la carga lazy de `psycopg`. El flujo candidate-only mantiene
baselines, snapshots, contratos, as-of, hashes, dry-run/preflight, códigos de salida y orden de
persistencia. No se tocaron SQL/DDL, dashboard, workflows ni el horizonte reservado.

### Evidencia reproducida desde el hilo principal

```text
foco de la pareja + imports públicos                    8 passed
fachadas/servicios                                      45/640 y 114/521 líneas
dry-run con dobles                                      0 escrituras
apply con doble de conexión                             1 commit, orden preservado
imports ejecutables entre scripts                       0 coincidencias
```

La suite analítica completa fue reportada por los agentes como `579 passed, 3 skipped`; queda
pendiente repetirla desde el hilo principal y volver a ejecutar las compuertas globales. El riesgo
externo sigue siendo la ausencia de PostgreSQL/MLflow reales.

## Plan reestructurado vigente después de esta ronda

1. **Cerrar la evidencia de esta pareja:** repetir `python -m pytest packages/analitica/tests -q`
   desde el hilo principal; luego ejecutar dashboard, domain+ETL, Ruff, `compileall`, `--help`, AST,
   imports y rueda limpia.
2. **Siguiente pareja de persistencia disjunta:** extraer `persistir_nowcast_cierre_adaptativo.py`
   y `persistir_ocurrencia_universo.py`, preservando orden de writes, tablas, SQL, transacciones,
   dry-run, hashes, contratos, modelos/versiones y semántica as-of. Usar dobles; no escribir en bases
   reales durante la refactorización.
3. **Bloque posterior:** tratar `persistir_ocurrencia_v2.py`, `persistir_proyeccion_operativa_v2.py`,
   `persistir_replay_campania.py`, `persistir_replay_r09_corregido.py` y
   `replay_campania_completo.py` por parejas realmente disjuntas, sin mezclar SQL o modelos.
4. **Cierre integral:** incluir `screening_router_horizonte.py` solo después de la entrega paralela,
   integrar/auditar horizonte, repetir raíz/dashboard/domain+ETL, y cerrar Python oficial, lock,
   CI/Docker, PostgreSQL, Access/Excel y MLflow. Mantener **NO GO** hasta entonces.

## Revisión principal de certificación y persistencia candidate-only

La suite analítica repetida desde el hilo principal confirmó `579 passed, 3 skipped, 33377 warnings`.
La pareja focalizada pasó `8` pruebas: el dry-run del candidate-only produjo cero escrituras, y la
certificación con doble de conexión confirmó rollback sin `--apply` y un solo commit con el orden de
efectos preservado con `--apply`. Las fachadas no importan scripts entre sí; no se tocaron SQL/DDL,
dashboard, workflows ni la entrega paralela de horizonte.

## Plan reestructurado vigente para el siguiente bloque de persistencia

1. **Siguiente pareja disjunta:** extraer `persistir_nowcast_cierre_adaptativo.py` y
   `persistir_ocurrencia_universo.py` a servicios, conservando modelo/version, hashes, snapshots,
   contratos, tablas, SQL, orden de writes, transacciones, idempotencia, dry-run, `as-of`, JSON y
   códigos/CLI. Los dobles deben probar ausencia de escritura en dry-run.
2. **Auditoría posterior:** esperar ambos agentes hasta `completed`, cerrar, revisar queries y efectos
   desde el hilo principal, ejecutar foco e imports, y luego repetir la suite analítica. Las pruebas
   reales PostgreSQL/MLflow quedan para el cierre autorizado, no para una refactorización ciega.
3. **Después:** refactorizar `persistir_ocurrencia_v2.py`, `persistir_proyeccion_operativa_v2.py`,
   `persistir_replay_campania.py`, `persistir_replay_r09_corregido.py` y `replay_campania_completo.py`
   en parejas sin solapar tablas/contratos. Mantener fuera el router de horizonte.
4. **Cierre integral:** incluir horizon, dashboard, domain+ETL, raíz, rueda, CI/Docker, Python oficial,
   lock/constraints y pruebas reales de PostgreSQL, Access/Excel y MLflow; mantener **NO GO**.

## Revisión posterior a nowcast y universo de ocurrencia

Se esperaron ambos subagentes hasta `completed`, se cerraron y se revisaron directamente sus
fachadas, servicios y pruebas. El nowcast conserva la separación cierre semanal/forecast H1,
modelo/version, hashes, snapshots, contratos, `as-of`, SQL, tablas, commits, fallos y rollback. El
universo conserva la intersección común, snapshot, modelos/versiones, métricas, contratos, dry-run y
orden de efectos. No se tocaron SQL/DDL, dashboard, workflows ni horizonte.

### Evidencia reproducida desde el hilo principal

```text
foco de la pareja + imports públicos                  12 passed
nowcast: fachada/servicio                               89/680 líneas
universo: fachada/servicio                              45/248 líneas
dry-run y orden de persistencia                         OK con dobles
imports ejecutables entre scripts                      0 coincidencias
```

La suite analítica anterior estaba en `579 passed, 3 skipped`; la nueva suite completa debe repetirse
desde este hilo después de esta pareja. Continúa pendiente la evidencia real de PostgreSQL/MLflow.

## Plan reestructurado vigente después de esta ronda

1. **Cerrar esta ronda:** repetir `python -m pytest packages/analitica/tests -q`, y luego dashboard,
   domain+ETL, Ruff, `compileall`, ayudas CLI, AST, imports y rueda limpia.
2. **Siguiente pareja persistente disjunta:** extraer `persistir_ocurrencia_v2.py` y
   `persistir_proyeccion_operativa_v2.py`, con dobles para SQL, transacciones, contratos, modelos,
   versiones, snapshots, `as-of`, dry-run y orden de escrituras. No cambiar nombres ni DDL.
3. **Después:** refactorizar `persistir_replay_campania.py`, `persistir_replay_r09_corregido.py` y
   `replay_campania_completo.py` por alcance separado; auditar cada replay contra sus tablas y
   baseline. Mantener fuera `screening_router_horizonte.py`.
4. **Cierre integral:** integrar/auditar el horizonte paralelo y repetir todas las suites, CI/Docker,
   Python oficial/lock, Access/Excel, PostgreSQL y MLflow. Seguir en **NO GO** hasta equivalencia y
   trazabilidad completa.

## Revisión posterior a los replays de campaña y R09

Se esperaron ambos subagentes hasta `completed`, se cerraron y se revisaron directamente sus
fachadas, servicios y pruebas. `persistir_replay_campania` mantiene fuentes, snapshot, modelos,
versiones, métricas, calidad, contratos, as-of, dry-run y orden de efectos. `persistir_replay_r09`
mantiene la consulta vintage, detección de corrida reutilizable, universo, columnas, métricas y
persistencia transaccional. No se tocaron SQL/DDL, dashboard, workflows ni horizonte.

### Evidencia reproducida desde el hilo principal

```text
foco de la pareja + imports públicos                  16 passed
campaña: fachada/servicio                              68/254 líneas
R09: fachada/servicio                                  50/324 líneas
reutilización, dobles y orden transaccional             OK
imports ejecutables entre scripts                      0 coincidencias
```

La suite analítica anterior estaba en `603 passed, 3 skipped`; queda pendiente repetirla desde el
hilo principal después de esta pareja. La validación de PostgreSQL/MLflow reales sigue fuera de
entorno/autorización.

## Plan reestructurado vigente después de esta ronda

1. **Cerrar esta ronda:** repetir `python -m pytest packages/analitica/tests -q` y actualizar el
   conteo real; después dashboard, domain+ETL, Ruff, `compileall`, ayudas CLI, AST, imports y rueda.
2. **Último script con lógica propia:** refactorizar `replay_campania_completo.py` a un servicio
   específico, comparando explícitamente contratos con los replays ya extraídos, sin cambiar modelos,
   versiones, snapshots, SQL, tablas, as-of, dry-run u orden de escrituras.
3. **Router reservado:** `screening_router_horizonte.py` solo se revisará después de recibir y auditar
   la entrega paralela de `proyeccion/horizonte` y `pronostico_horizonte.py`; no tocar esos archivos
   durante la espera.
4. **Cierre final:** ejecutar raíz, dashboard, domain+ETL, rueda, CI/Docker, fijar Python/lock y
   obtener evidencia real PostgreSQL/Access/Excel/MLflow. Mantener **NO GO** hasta todo ello.

## Revisión posterior a ocurrencia_v2 y proyección operativa v2

Se esperaron ambos subagentes hasta `completed`, se cerraron y se revisaron directamente las
fachadas, servicios y pruebas. Ocurrencia v2 conserva el universo común, snapshot, fuentes,
modelos/versiones, fórmulas, métricas, contratos, dry-run, idempotencia y orden de escritura. La
proyección operativa conserva selección de run/snapshot, cortes as-of, semanas, distribución
`lote-paña`, metadatos, dry-run y finalización exitosa/fallida. No se tocaron SQL/DDL, dashboard,
workflows ni horizonte.

### Evidencia reproducida desde el hilo principal

```text
foco de la pareja + imports públicos                  16 passed
ocurrencia v2: fachada/servicio                         49/321 líneas
operativa v2: fachada/servicio                           43/370 líneas
dry-run, paridad, filas/kg y fallo failed               OK con dobles
imports ejecutables entre scripts                      0 coincidencias
```

La suite analítica anterior estaba en `589 passed, 3 skipped`; queda pendiente repetirla desde el
hilo principal después de esta pareja. Persisten como riesgos externos la falta de PostgreSQL/MLflow
reales y la compatibilidad de esquema productivo.

## Plan reestructurado vigente después de esta ronda

1. **Cerrar esta ronda:** repetir `python -m pytest packages/analitica/tests -q`, y después dashboard,
   domain+ETL, Ruff, `compileall`, ayudas CLI, AST, imports y rueda limpia.
2. **Siguiente pareja de replay disjunta:** extraer `persistir_replay_campania.py` y
   `persistir_replay_r09_corregido.py`, preservando baseline, tablas, SQL, modelos/versiones,
   contratos, as-of, orden de efectos, dry-run, errores e idempotencia con dobles.
3. **Después:** tratar `replay_campania_completo.py` por separado y auditar que no duplique ni
   cambie los contratos del replay anterior. `screening_router_horizonte.py` queda bloqueado hasta
   la entrega paralela del horizonte.
4. **Cierre integral:** repetir raíz, dashboard, domain+ETL, rueda y CI/Docker; fijar Python/lock,
   probar PostgreSQL, Access/Excel y MLflow reales, e integrar horizonte. Mantener **NO GO**.

## Revisión posterior a ocurrencia_v2 y proyección operativa v2

La repetición desde el hilo principal confirmó `603 passed, 3 skipped, 33470 warnings` en la suite
analítica tras la pareja. La revisión focalizada pasó `16` pruebas: las fachadas conservaron aliases,
firmas y CLI; los dobles confirmaron paridad de filas/kg, dry-run, y finalización `succeeded/failed`.
No se tocaron SQL/DDL, dashboard, workflows ni el horizonte reservado.

## Plan reestructurado vigente para replay

1. **Siguiente pareja disjunta:** extraer `persistir_replay_campania.py` y
   `persistir_replay_r09_corregido.py`, preservando fuentes, baseline, snapshot, modelos/versiones,
   SQL, tablas, contratos, as-of, orden de efectos, idempotencia, dry-run o reutilización histórica,
   errores y salida CLI. Validar solo con dobles, sin escrituras externas.
2. **Auditoría posterior:** esperar ambos agentes hasta `completed`, cerrar, revisar directamente
   queries/aliases/fachadas y ejecutar pruebas focalizadas, suite analítica, imports, AST, Ruff,
   compileall y `--help` desde el hilo principal.
3. **Último replay:** abordar `replay_campania_completo.py` por separado, comparando explícitamente
   sus contratos con los replays previos para evitar duplicación o cambios de modelo/version.
4. **Cierre integral:** solo después tratar `screening_router_horizonte.py` con la entrega paralela;
   repetir raíz, dashboard, domain+ETL, rueda, CI/Docker, Python/lock y pruebas reales PostgreSQL,
   Access/Excel y MLflow. Mantener **NO GO**.

## Revisión posterior a los replays de campaña y R09 corregido

La suite analítica repetida desde el hilo principal confirmó `617 passed, 3 skipped, 33473 warnings`.
La revisión focalizada pasó `16` pruebas y confirmó fachadas delgadas, cero imports entre scripts,
consultas históricas, reutilización de corrida R09, universo/fechas y orden de efectos. No se
modificaron SQL/DDL, dashboard, workflows ni horizonte.

## Plan reestructurado vigente antes del cierre de scripts

1. **Último script con lógica propia:** refactorizar `replay_campania_completo.py` a un servicio
   específico, comparando explícitamente contratos con los replays ya extraídos y conservando
   modelos/versiones, snapshots, SQL, tablas, as-of, dry-run, aliases y orden de writes.
2. **Auditoría posterior:** esperar el subagente hasta `completed`, cerrar, revisar directamente y
   ejecutar pruebas focalizadas, suite analítica, imports, AST, Ruff, `compileall` y `--help` desde el
   hilo principal.
3. **Horizon reservado:** no modificar `packages/analitica/proyeccion/horizonte/*`,
   `packages/analitica/proyeccion/pronostico_horizonte.py` ni aceptar como final
   `screening_router_horizonte.py` hasta recibir y auditar la entrega paralela.
4. **Cierre integral:** repetir raíz, dashboard, domain+ETL, rueda, CI/Docker, Python/lock y pruebas
   reales PostgreSQL, Access/Excel y MLflow. Mantener **NO GO** hasta cerrar scripts, horizonte,
   infraestructura y trazabilidad Git.

## Revisión posterior al replay de campaña completo

Se esperó el subagente hasta `completed`, se cerró y se revisó directamente el servicio y la
fachada. El replay completo conserva su contrato independiente frente a `persistir_replay_campania`:
`--max-targets`, `--keep-run`, snapshot fijo `40`, run origen `76`, cuatro modelos, dry-run, métricas,
errores y orden de persistencia. No se tocaron SQL/DDL, dashboard, workflows ni horizonte.

### Evidencia reproducida desde el hilo principal

```text
foco del replay + imports públicos                     5 passed
fachada/servicio                                        63/279 líneas
dry-run, snapshot fijo y finalización failed             OK con dobles
imports ejecutables entre scripts                       0 coincidencias
```

La suite analítica anterior estaba en `617 passed, 3 skipped`; queda pendiente una última repetición
desde el hilo principal para incluir las pruebas nuevas. La capa de scripts ya no muestra lógica
propia salvo el router reservado de horizonte; se verificará con AST.

## Plan reestructurado vigente: cierre técnico y horizonte

1. **Cerrar scripts:** repetir `python -m pytest packages/analitica/tests -q`; ejecutar AST para
   confirmar que solo `screening_router_horizonte.py` queda fuera por la reserva, y ejecutar Ruff,
   compileall, todas las ayudas CLI, imports y rueda limpia.
2. **Auditar entrega paralela:** esperar la finalización del trabajo reservado en
   `packages/analitica/proyeccion/horizonte/*` y `pronostico_horizonte.py`; solo después revisar
   `screening_router_horizonte.py` y sus contratos. El hilo principal no editará esos archivos.
3. **Cierre de ecosistema:** repetir dashboard, domain+ETL y suite raíz con `domain` editable;
   revisar workflows/CI, Python oficial y lock/constraints; intentar Docker, PostgreSQL, Access/Excel
   y MLflow reales cuando estén disponibles, documentando bloqueos sin simular éxito.
4. **Decisión final:** conservar **NO GO** mientras falte horizonte, infraestructura externa,
   matriz CI/reproducibilidad o trazabilidad Git; no borrar archivos antiguos ni cambiar SQL/DDL sin
   evidencia de equivalencia.

## Revisión posterior al cierre local de scripts y ETL

Se esperaron los tres subagentes de esta ronda hasta `completed` y se revisaron sus resultados.
La corrección ETL fue mecánica: orden de imports, saltos de línea e importación segura de
`TablaModelo`; no cambió lógica, nombres, valores, tablas ni SQL. La fachada
`evaluar_ocurrencia_v3` recibió además una compuerta CLI inocua para que `--help` no dispare una
consulta PostgreSQL y siga aceptando argumentos históricos desconocidos. No se tocó ningún archivo
reservado del horizonte.

### Evidencia reproducida desde el hilo principal

```text
python -m pytest -q                                      881 passed, 3 skipped, 54516 warnings
python -m pytest apps/dashboard/tests -q                 197 passed, 21043 warnings
PYTHONPATH=src python -m pytest domain etl -q             64 passed
python -m ruff check --no-cache ...                       All checks passed
python -m compileall -q ...                               exit 0
ayuda CLI de scripts                                     46/46 OK
AST scripts                                              46 ejecutables, 0 imports entre scripts
wheel actual                                             211 .py, 0 faltantes, 0 bytecode, entrypoint OK
```

El AST todavía identifica tres definiciones propias, todas justificadas y acotadas: el wrapper de
compatibilidad `_cargar_priors_excel`, el constructor de parser de
`screening_turno_reingreso_multihorizon.py` y el router de horizonte reservado. El wrapper mantiene
un punto histórico de monkeypatch; los dos últimos son frontera CLI/router. No se deben eliminar sin
pruebas de consumidores externos.

### Plan reestructurado vigente después de esta revisión

1. **Cerrar la entrega paralela de horizonte:** esperar su resultado final y auditar
   `packages/analitica/proyeccion/horizonte/*`, `pronostico_horizonte.py` y luego
   `screening_router_horizonte.py`. El hilo principal no modifica esas rutas durante la reserva.
2. **Cerrar reproducibilidad sin cambiar semántica:** decidir y documentar la versión Python oficial
   o una matriz explícita; alinear CI/Docker/constraints; evaluar un lockfile transitivo con hashes y
   mantener `pyodbc` como dependencia opcional de Windows/Access. Cualquier cambio debe validarse en
   un entorno limpio y con wheel.
3. **Cerrar integraciones reales:** ejecutar el workflow PostgreSQL/DDL con DSN, Access/Excel con
   driver y libros oficiales, y MLflow contra tracking server/registry. Si no están disponibles,
   conservar el bloqueo explícito y no simular aprobación.
4. **Cierre de calidad y trazabilidad:** revisar la política de los 54.516 warnings, validar YAML de
   workflows con herramienta específica cuando exista, registrar los cambios intencionados y
   mantener archivos antiguos hasta contar con equivalencia. Repetir raíz, dashboard, domain+ETL,
   Ruff, compileall, CLI, AST y wheel tras cualquier cambio del horizonte o CI.
5. **Decisión:** el refactor está localmente integrado y cubierto, pero continúa **NO GO** para
   aceptación completa mientras falten horizonte paralelo, integraciones reales y reproducibilidad
   CI/lock/trazabilidad. No alterar fórmulas, resultados, modelos, versiones, rutas, SQL, tablas,
   escenarios ni semántica `as-of` para cerrar una compuerta.

## Revisión posterior a horizonte y router

El task paralelo del horizonte terminó y fue esperado hasta estado final. Su entrega conserva la
fachada histórica de `pronostico_horizonte.py`, agrega el paquete interno de horizonte y separa
contratos, corrección y evaluación sin cambiar la API pública. La prueba focalizada desde el hilo
principal pasó `10`, Ruff pasó y `compileall` terminó sin errores. Después se auditó el router
reservado: un subagente movió `evaluar_campania` y `ejecutar` al servicio, manteniendo fórmulas,
runs, modelos, columnas, claves, JSON, argumentos y aliases; la fachada quedó con solo `main`.

### Evidencia posterior de integración

```text
python -m pytest packages/analitica/tests -q             624 passed, 3 skipped, 33473 warnings
router + cadena + imports públicos                       11 passed
horizonte focalizado                                     10 passed, 291 warnings
ruff alcance completo                                    All checks passed
compileall alcance completo                              exit 0
ayuda CLI                                                46/46 OK
AST scripts                                              46 ejecutables, 0 imports entre scripts
                                                        45 delgadas; 1 adaptador histórico justificado
```

### Plan reestructurado vigente tras esta ronda

1. **Regresión final local:** repetir raíz, dashboard, domain+ETL, Ruff, compileall, ayudas CLI,
   AST e inspección del wheel después de cualquier modificación restante.
2. **Reproducibilidad:** resolver la diferencia Python 3.12/3.13/3.14, alinear constraints entre
   workflows y smoke tests, y decidir un lockfile transitivo con hashes. No cambiar versiones por
   intuición: validar en entorno limpio y documentar la decisión.
3. **Integraciones reales:** ejecutar PostgreSQL con el DSN del workflow, Access/Excel con driver y
   archivos oficiales, y MLflow con tracking server/registry. Los dobles y fixtures ya prueban
   contratos, pero no sustituyen esas compuertas.
4. **Higiene de entrega:** establecer política para los warnings deprecados, validar workflows con
   `actionlint` si está disponible y revisar trazabilidad Git de los archivos intencionados. No
   borrar módulos antiguos ni alterar SQL/DDL sin equivalencia demostrada.
5. **Decisión:** la refactorización de código queda en **GO LOCAL**; la aceptación de plataforma
   sigue **NO GO** hasta cerrar reproducibilidad, integraciones externas y trazabilidad. Mantener
   intactos resultados, fórmulas, modelos, versiones, rutas, tablas, escenarios y `as-of`.

## Línea base final local y bloqueos externos

La repetición final posterior al router terminó con `885 passed, 3 skipped` en la raíz y
`624 passed, 3 skipped` en `packages/analitica/tests`. El wheel final contiene `211` módulos
Python, sin bytecode ni faltantes, y conserva el entrypoint `aquanqa-analytics`. `ruff`,
`compileall`, las `46` ayudas CLI, el AST de scripts y `pip check` quedaron limpios. MLflow se
probó con su API real contra un backend temporal y creó un run correctamente.

Los tres skips de integración PostgreSQL permanecen porque no existe `AQUANQA_TEST_POSTGRES_DSN`.
Docker tiene cliente, pero el daemon Docker Desktop no está activo. `python-calamine` está
instalado; `pyodbc` y el driver ODBC de Access, los `.accdb` y los libros Excel oficiales no están
disponibles. No hay servidor/registry MLflow configurado. Por tanto, estos resultados no se
presentan como pruebas de infraestructura productiva.

### Plan de salida vigente

1. **Aceptación local:** conservar la línea base anterior como gate de regresión para cualquier
   cambio futuro y no tocar la semántica protegida.
2. **Entorno reproducible:** elegir formalmente Python 3.12/3.13/3.14, alinear workflows, Docker y
   constraints, y generar el lock transitivo con hashes en una tarea de infraestructura separada.
3. **Pruebas externas:** con DSN/servicios/archivos oficiales, ejecutar PostgreSQL+DDL, extracción
   Access/Excel real y MLflow server+registry; guardar sus evidencias y repetir los gates locales.
4. **Entrega:** validar YAML con `actionlint` cuando esté disponible, resolver la política de
   warnings deprecados y crear el baseline/tag de Git autorizado. Mientras eso no ocurra, el estado
   correcto es **GO LOCAL / NO GO PRODUCTIVO**.

## Auditoría arquitectónica posterior a la línea base local

La auditoría independiente posterior a la línea base confirmó que las pruebas verdes prueban
compatibilidad, pero no todavía extracción física completa. Se esperó al auditor hasta
`completed` y se revisó su informe antes de modificar este plan. Los incumplimientos concretos son:

- `proyeccion/fenologico_v1.py` aún contiene predicción por emisión, backtest, proyección y
  escenarios; `fenologico/servicio.py` solo reexporta.
- `proyeccion/hibrido_legacy.py` aún contiene el panel y las dos proyecciones; `hibrido/servicio.py`
  importa desde la fachada histórica en dirección invertida.
- `proyeccion/relaciones.py` aún contiene todo el cálculo; `relaciones_partes/*` son puentes que
  reimportan el monolito.
- `cli.py` aún contiene handlers, carga de datos, tracking, persistencia y parser en un solo módulo.
- `config.py` y `catalogos.py` tienen objetos equivalentes pero no siempre la misma identidad; debe
  quedar una única fuente para `PARAMS`, `HOJAS` y colores.
- `gobernanza.py` sí es fachada real; `settings.py` es cohesivo y no requiere división urgente.

### Plan reestructurado antes de la siguiente campaña de subagentes

1. **Fenología:** mover físicamente la orquestación a `proyeccion/fenologico/servicio.py`, dejando
   `fenologico_v1.py` como fachada compatible; preservar as-of, fórmula, intervalos, columnas,
   sensibilidades, escenarios y modelos.
2. **Híbrido legacy:** mover panel y proyecciones a `proyeccion/hibrido/servicio.py`, corregir la
   dirección de dependencias y mantener priors, residual, replay, procedencia y nombres de modelo.
3. **Relaciones:** extraer físicamente panel, estadística, packing y evidencia a
   `relaciones_partes/*`; conservar temporalmente todos los símbolos públicos y privados mediante
   reexports, sin cambiar pruebas, fórmulas ni resultados.
4. **Configuración:** consolidar `config.py` y `catalogos.py` con una sola definición de objetos,
   manteniendo rutas, valores, identidad pública y comportamiento de mutación documentado.
5. **CLI:** dividir handlers en `commands/*` o servicios de comandos, dejando `cli.py` con
   `parser()`/`main()` y reexports de compatibilidad; conservar subcomandos, argumentos, entrypoint,
   orden de efectos y estados `failed`.
6. **Servicios monolíticos:** después de esos tres núcleos, abordar por familias los servicios
   nowcast, parámetros, fenología/campaña/reingreso, Excel/Access y replays. Cada agente tendrá un
   conjunto de archivos exclusivo y deberá entregar pruebas focalizadas antes de cerrar.
7. **Auditoría posterior:** repetir la raíz, dashboard, domain+ETL, Ruff, compileall, imports, 46
   ayudas CLI, AST y wheel; volver a revisar este plan con la evidencia, sin considerar suficiente un
   simple alias hacia el monolito.
8. **Compuertas externas:** mantener separadas las validaciones de PostgreSQL real, Access/Excel
   oficial, MLflow remoto, Docker, Python/lockfile y trazabilidad Git. Estado actual: **GO para
   regresión local / NO GO para arquitectura completa y producción**.

## Revisión posterior a la consolidación de configuración y catálogos (2026-08-28)

Se ejecutó la tarea de configuración con alcance exclusivo sobre `config.py`, `catalogos.py`,
`settings.py` y sus pruebas. `catalogos.py` quedó como única fuente de `ETIQUETAS`, `GLOSARIO`,
`PARAMS`, `HOJAS` y la paleta; `config.py` conserva la fachada histórica mediante reexportaciones.
`settings.py` no recibió cambios de lógica: se cubrieron explícitamente las rutas relativas y
absolutas y las dos formas históricas de construir el DSN.

### Evidencia de la revisión

```text
python -m pytest packages/analitica/tests/test_config_catalogos.py -q
5 passed

python -m ruff check --no-cache packages/analitica/config.py packages/analitica/catalogos.py
  packages/analitica/settings.py packages/analitica/tests/test_config_catalogos.py
All checks passed!

python -m compileall -q packages/analitica
exit 0

comparación de valores contra config.py de HEAD
ok

identidad config/catalogos para ETIQUETAS, GLOSARIO, PARAMS, HOJAS y colores
True

wheel
incluye analitica/catalogos.py, analitica/config.py y analitica/settings.py
build exit 0
```

La revisión AST confirmó cero definiciones propias de esos nombres en `config.py` y una sola
definición por nombre en `catalogos.py`. Las rutas reservadas del horizonte y el resto de módulos
fuera del alcance no fueron modificados. El wheel generado en este checkout conserva además
bytecode preexistente/generado por la configuración actual de setuptools; queda como deuda de
higiene de empaquetado separada, sin afectar la consolidación ni la API solicitada.

### Plan reestructurado después de esta auditoría

1. **Configuración cerrada localmente:** mantener `catalogos.py` como fuente única y `config.py`
   como fachada; no mover todavía `FEATURES`, `CLIMA` u otros contratos no solicitados.
2. **Regresión amplia:** después de cada cambio de otra familia repetir la suite raíz, dashboard,
   domain+ETL, Ruff, `compileall`, imports, ayudas CLI y wheel; conservar los cinco tests de
   configuración como gate obligatorio.
3. **Arquitectura pendiente:** continuar, en rondas disjuntas y con auditoría posterior, con
   fenología, híbrido, relaciones, CLI y servicios monolíticos según el orden anterior del plan.
4. **Compuertas externas:** mantener **NO GO productivo** hasta validar PostgreSQL, Access/Excel,
   MLflow, Docker, Python/lockfile y trazabilidad Git; esta tarea no altera esa decisión.

## Auditoría arquitectónica posterior a la ronda de fachadas (2026-08-28)

Se esperó el resultado final de los cinco subagentes de extracción y se revisó la integración
desde el hilo principal. La ronda sí realizó extracción física —no simples alias— de fenología,
híbrido legacy, relaciones, configuración/catálogos y CLI. Se añadió `analitica.commands` al
listado explícito de paquetes para que la nueva estructura viaje en el wheel. Las fachadas
históricas se conservaron y los módulos internos no dependen de ellas en sentido inverso.

### Evidencia consolidada de esta ronda

```text
python -m pytest packages/analitica/tests -q       637 passed, 3 skipped, 33473 warnings
python -m pytest apps/dashboard/tests -q            197 passed, 21043 warnings
PYTHONPATH=src python -m pytest domain etl -q       64 passed
python -m pytest -q                                 898 passed, 3 skipped, 54516 warnings
python -m ruff check --no-cache ...                 All checks passed
python -m compileall -q ...                         exit 0
python -m pip check                                 No broken requirements found
AST scripts                                         46 ejecutables, 0 imports entre scripts,
                                                     44 delgadas, 2 auxiliares justificadas
wheel                                             218 archivos Python, 0 faltantes, 0 bytecode
CLI help                                           exit 0; 8 subcomandos preservados
PostgreSQL focalizado                               1 skipped por falta de AQUANQA_TEST_POSTGRES_DSN
```

La suite verde demuestra compatibilidad local, no disponibilidad de infraestructura externa.
Persisten los bloqueos ya registrados: DSN/servidor PostgreSQL de integración, driver y libros
Access/Excel oficiales, servidor/registry MLflow, daemon Docker y decisión de matriz Python/
lockfile. También quedan warnings de deprecación de pandas/NumPy que requieren una política
separada; no se corrigen incidentalmente durante una extracción funcional.

### Revisión de alcance pendiente

La extracción principal de proyección y CLI está avanzada, pero aún hay monolitos físicos en
`servicios/nowcast.py` (1517 líneas), `servicios/cross_campaign.py` (954),
`servicios/fenologia_honest.py` (949), `proyeccion/hibrido_parametros_asof.py` (932),
`proyeccion/persistencia/repositorio.py` (925), `servicios/turno_reingreso.py` (881), además
de los servicios Excel, replays y scheduler. Por tanto, la arquitectura completa todavía no se
puede declarar cerrada aunque la regresión local esté verde.

### Plan reestructurado después de esta auditoría

1. **Refactorizar servicios por familia en rondas disjuntas:** nowcast; campaña/fenología
   honesta; parámetros y Excel/Access; turno/reingreso; persistencia y replay. Cada subagente
   recibe archivos exclusivos, mantiene la fachada pública y entrega pruebas focalizadas.
2. **Revisar cada ronda antes de continuar:** esperar todos los resultados finales, comprobar
   dependencias unidireccionales, imports públicos, tamaño/cohesión de los módulos y repetir las
   pruebas focalizadas. Si aparece una regresión, detener la siguiente familia y corregirla.
3. **Gate de integración tras cada familia:** repetir paquete analítico, raíz, dashboard,
   domain+ETL, Ruff, compileall, ayudas CLI, AST y wheel limpio. La orden de Python siempre será
   `python -m ...`; no depender del PATH.
4. **Preservar contrato:** no cambiar fórmulas, resultados, modelos/versiones, rutas, SQL,
   tablas, escenarios, `as-of`, nombres de columnas, estados ni orden de efectos. No borrar
   fachadas antiguas hasta contar con equivalencia y evidencia de consumidores.
5. **Infraestructura separada:** cerrar PostgreSQL, Access/Excel, MLflow, Docker, matriz Python,
   lockfile y warnings solo con sus recursos reales; no presentar dobles locales como validación
   productiva. Estado actual: **GO local / NO GO arquitectura completa y productivo**.

## Revisión posterior a la ronda de servicios (2026-08-28)

Se esperaron y revisaron los resultados finales de seis subagentes: nowcast, campaña cruzada,
fenología honesta, Excel/Access, persistencia y turno/reingreso. Sus extracciones son físicas,
mantienen fachadas históricas y no modificaron las rutas reservadas de horizonte ni el plan. El
intento separado para `hibrido_parametros_asof.py` no produjo cambios ni informe después de
varias esperas y fue cerrado como no concluyente; ese módulo no se considera refactorizado.

### Evidencia de subagentes revisados

```text
nowcast                         34 pruebas; Ruff y compileall OK
cross_campaign                 16 pruebas; Ruff y compileall OK
fenologia_honest               11 pruebas; Ruff y compileall OK
Excel/Access                   64 pruebas; Ruff y compileall OK
persistencia                   26 pruebas; Ruff y compileall OK; 1 skip sin DSN
turno/reingreso                16 pruebas; Ruff y compileall OK
hibrido_parametros_asof        pendiente; agente cerrado sin cambios
```

### Plan reestructurado después de la ronda de servicios

1. Reintentar una sola extracción especializada de `hibrido_parametros_asof.py`, con partes
   físicas y fachada compatible; si vuelve a no producir evidencia, dejarlo explícitamente como
   deuda y no forzar un cambio de alto riesgo.
2. Revisar la integración completa: imports públicos, dependencias unidireccionales, fachadas,
   wheel y ausencia de bytecode o módulos huérfanos. El conteo de pruebas focalizadas no sustituye
   la suite raíz.
3. Ejecutar nuevamente paquete analítico, dashboard, domain+ETL, raíz, Ruff, compileall, ayudas
   CLI y wheel limpio usando `python -m ...`. Comparar contra la línea base de `637/898` y los
   skips de infraestructura conocidos.
4. Mantener separadas las compuertas reales PostgreSQL, Access/Excel, MLflow, Docker, Python/
   lockfile, warnings y trazabilidad Git. Estado provisional: **GO local condicionado / NO GO
   arquitectura completa y productivo** hasta resolver el punto 1 y revisar los gates.

## Auditoría posterior a la extracción transversal completa (2026-08-28)

Se esperaron los seis subagentes de la ronda de servicios y el subagente final de parámetros
as-of hasta estado final. Se revisaron sus cambios desde el hilo principal y se repitieron las
pruebas del paquete y del repositorio. Las fachadas históricas de nowcast, campaña, fenología,
Excel/Access, turno/reingreso, persistencia y parámetros as-of ya no contienen la implementación
principal; las partes nuevas dependen en una sola dirección.

### Evidencia final de regresión

```text
python -m pytest packages/analitica/tests -q       655 passed, 3 skipped, 33507 warnings
python -m pytest apps/dashboard/tests -q            197 passed, 21043 warnings
PYTHONPATH=src python -m pytest domain etl -q       64 passed
python -m pytest -q                                 916 passed, 3 skipped, 54550 warnings
python -m ruff check --no-cache ...                 All checks passed
python -m compileall -q ...                         exit 0
python -m pip check                                 No broken requirements found
CLI help                                           cli_help_ok modules=46
wheel limpio                                      262 Python, 0 faltantes, 0 bytecode
CLI principal                                     8 subcomandos y entry point válidos
```

Los tres skips siguen explicados por la ausencia local de `AQUANQA_TEST_POSTGRES_DSN`. No se
simularon PostgreSQL, Access/Excel oficial ni MLflow remoto. Continúan fuera de este checkout el
driver `pyodbc`, los libros oficiales, el daemon Docker, el servidor/registry MLflow, una matriz
Python única y un lockfile transitivo con hashes. Los warnings de pandas/NumPy siguen siendo una
deuda de mantenimiento independiente y no se ocultaron para hacer pasar la regresión.

### Resultado entendible para no desarrolladores

La aplicación conserva sus entradas, salidas y nombres conocidos; se ordenó el interior detrás
de fachadas compatibles, como ordenar una oficina sin cambiar los formularios que usan las
personas. Las pruebas automáticas confirman que el cambio no altera los cálculos en el entorno
local. Aún no significa que todas las conexiones externas estén disponibles ni que exista una
aprobación de producción.

### Plan reestructurado vigente

1. Mantener `python -m pytest -q`, dashboard, domain+ETL, Ruff, `compileall`, CLI y wheel como
   gates obligatorios después de cualquier modificación.
2. En una siguiente ronda separada, revisar servicios de segundo nivel que aún concentran varias
   responsabilidades: `active_lot_scheduler.py`, `persistir_nowcast_cierre_adaptativo.py`,
   `certificar_releases_replay.py`, `persistir_hibrido_parametros_asof.py`, `small_data_h1.py`
   y `loop_forecast_horizontes.py`. No dividir `nucleo/clima.py` o `bhattacharya.py` solo por
   tamaño: primero demostrar fronteras y paridad, porque son núcleos científicos cohesivos.
3. Auditar reexports públicos, dependencias unidireccionales, contratos de datos, SQL y
   transacciones tras cada extracción. No borrar fachadas ni cambiar fórmulas, modelos,
   versiones, rutas, tablas, escenarios, estados u orden de efectos sin equivalencia.
4. Cerrar por separado las pruebas reales de PostgreSQL, Access/Excel y MLflow, además de Docker,
   matriz Python, lockfile, warnings y trazabilidad Git, solo cuando se disponga de sus recursos.
5. Estado actual: **GO para regresión local y refactor transversal; NO GO para producción** hasta
   cerrar las compuertas externas y revisar los servicios de segundo nivel.

## Revisión final posterior a servicios de segundo nivel (2026-08-29)

Se esperaron los cuatro subagentes de esta ronda. Nash, Nietzsche e Hilbert entregaron informes
finales; Ptolemy fue cerrado después de quedar sin respuesta, pero su extracción física del
scheduler fue comprobada directamente en el checkout: fachada de 120 líneas, cinco partes
conectadas y pruebas incluidas en la regresión. No se modificaron las rutas reservadas de
`proyeccion/horizonte` ni `pronostico_horizonte.py`.

### Resultado de la revisión

Se separaron también persistencia del cierre nowcast, certificación/replay, small-data H1 y loop
forecast por horizontes. En conjunto, las fachadas principales del paquete quedaron delgadas y
las responsabilidades viven en módulos de contratos, lectura, transformación, predicción,
evaluación, persistencia o salida según el caso.

```text
python -m pytest packages/analitica/tests -q       664 passed, 3 skipped, 33507 warnings
python -m pytest apps/dashboard/tests -q            197 passed, 21043 warnings
PYTHONPATH=src python -m pytest domain etl -q       64 passed
python -m pytest -q                                 925 passed, 3 skipped, 54550 warnings
python -m ruff check --no-cache ...                 All checks passed
python -m compileall -q ...                         exit 0
python -m pip check                                 No broken requirements found
CLI help                                           cli_help_ok modules=46
wheel limpio                                      281 Python, 0 faltantes, 0 bytecode
PostgreSQL focalizado                               1 skipped sin DSN
```

El conteo de warnings aumentó solo por la ejecución de nuevas pruebas y conserva advertencias de
deprecación ya visibles; no se ocultaron. Las pruebas reales externas siguen pendientes: no hay
DSN PostgreSQL local, `pyodbc` ni libros oficiales Access/Excel, Docker Desktop no tiene daemon,
MLflow solo está disponible como biblioteca local sin servidor/registry, y no existe lockfile
transitivo. La versión local es Python 3.14.6 mientras CI/Docker usan una matriz distinta.

### Plan operativo, explicado para cualquier persona

1. **Qué ya está hecho:** se ordenó el interior del paquete sin cambiar los formularios
   externos. Los nombres históricos siguen funcionando; los cálculos, tablas, escenarios,
   estados, rutas, SQL, modelos/versiones y reglas `as-of` conservan sus contratos. Cada bloque
   importante tiene pruebas focalizadas y la regresión completa está verde.
2. **Qué debe hacerse antes de publicar:** ejecutar las mismas pruebas contra PostgreSQL real,
   los libros oficiales de Excel/Access y un servidor/registry MLflow; activar Docker y guardar
   sus evidencias. Sin esos recursos, solo se puede afirmar que el código funciona localmente.
3. **Reproducibilidad:** acordar una versión oficial de Python, alinear CI/Docker/constraints y
   generar un lockfile transitivo con hashes. Esto evita que otra persona instale combinaciones
   distintas de librerías.
4. **Mantenimiento:** definir una política para las 54.550 advertencias y validar los workflows
   con una herramienta YAML/actionlint cuando esté disponible. Estos cambios deben ir en tareas
   separadas para no mezclar limpieza con fórmulas científicas.
5. **Regla de seguridad:** ante cualquier cambio futuro, ejecutar `python -m pytest -q`,
   dashboard, domain+ETL, Ruff, `compileall`, ayudas CLI y wheel. Si algo falla, detener la
   publicación y conservar la fachada anterior hasta demostrar equivalencia.

Estado final de esta sesión: **GO para refactor y regresión local; NO GO para producción** hasta
cerrar infraestructura, reproducibilidad y trazabilidad externas.

## Plan revisado antes de la auditoría de continuidad (2026-08-29)

La revisión del checkout confirma que la refactorización transversal está implementada y que
la regresión local sigue verde. Antes de declarar cerrada la entrega se hará una ronda separada
para las garantías que todavía pueden cambiar el resultado entre máquinas:

1. **CI del paquete analítico.** Revisar el workflow de Python para que la suite de
   `packages/analitica` tenga una compuerta explícita y para que la versión de Python usada por
   CI, Docker y el entorno documentado no quede ambigua. No se cambiarán fórmulas, modelos,
   SQL, tablas ni fachadas públicas.
2. **Reproducibilidad del entorno.** Auditar `constraints-analitica.txt`, los metadatos de
   empaquetado y el wheel. Solo se agregará un mecanismo de resolución reproducible si puede
   verificarse localmente con `python -m`; no se inventará un lockfile incompleto.
3. **Calidad y límites arquitectónicos.** Revisar imports inversos, scripts, warnings y
   workflows como riesgos independientes. La limpieza de warnings no se mezclará con cambios
   científicos; los núcleos cohesivos (`nucleo/clima.py` y `bhattacharya.py`) no se dividirán
   por tamaño sin una frontera demostrable.
4. **Compuertas externas.** Mantener como pruebas pendientes, y no simular, PostgreSQL real,
   Access/Excel oficiales, MLflow remoto, Docker y la trazabilidad Git. Si falta un recurso,
   se documentará como bloqueo operativo y se conservará la evidencia local.
5. **Orden de integración.** Esperar el resultado final de cada subagente, revisar sus cambios
   en el checkout, ejecutar de nuevo paquete, dashboard, domain+ETL, raíz, Ruff, compileall,
   ayudas CLI y wheel; después de esa auditoría se reestructurará este plan y se decidirá si
   existe base para el cierre.

Estado previo a esta ronda: **GO para continuar el refactor y las pruebas locales; NO GO para
producción** por las compuertas externas y la reproducibilidad todavía no demostradas.

## Reestructuración posterior a la auditoría de continuidad (2026-08-29)

Los tres informes finales fueron recibidos y revisados. La ronda confirmó que la compuerta
analítica de CI ya quedó explícita en `python.yml`, pero también encontró dos defectos de diseño
que deben resolverse antes de seguir con limpieza o con una decisión de publicación:

1. **Primero: dependencias internas.** `proyeccion/hibrido/replay.py` necesita proyectar mediante
   el servicio mientras el servicio importa sus funciones de replay; además,
   `proyeccion/parametros/ejecucion.py` importa símbolos privados de `hibrido_legacy.py`. Se
   extraerán contratos/utilidades internas o se invertirán dependencias, manteniendo la fachada
   y sus aliases históricos hasta demostrar equivalencia. Esta ronda no tocará
   `proyeccion/horizonte/` ni `pronostico_horizonte.py`.
2. **Segundo: protección de arquitectura.** Añadir pruebas o comprobaciones estáticas que
   impidan que una nueva parte interna vuelva a depender de una fachada histórica, sin prohibir
   los reexports públicos que protegen compatibilidad.
3. **Tercero: warnings.** Medir y registrar el baseline actual de warnings; convertir en error
   únicamente las categorías nuevas o controlables, sin ocultar las 54.550 advertencias existentes
   ni mezclar cambios de APIs científicas con limpieza de dependencias.
4. **Cuarto: reproducibilidad.** Mantener `constraints-analitica.txt` como constraints directas
   hasta elegir oficialmente entre lock transitivo con hashes o constraints por intérprete/
   plataforma. No se creará un archivo que parezca completo si no puede verificarse.
5. **Validación obligatoria después de cada corrección:** `python -m pytest -q`, suite de
   `packages/analitica`, dashboard, domain+ETL, Ruff, `compileall`, ayuda de CLI, ayuda de scripts,
   wheel y `pip check`. Luego se volverá a revisar este plan con evidencia final.

Estado después de la auditoría: **GO para corregir acoplamientos y reforzar gates locales; NO GO
para producción** por reproducibilidad, warnings y compuertas externas aún abiertas.

## Revisión final posterior al desacoplamiento y regresión (2026-08-29)

Se esperaron los dos subagentes de corrección hasta sus informes finales y se revisaron sus
cambios en el checkout. Pascal separó el motor común de proyecciones en `hibrido/proyecciones.py`
y eliminó el ciclo entre `replay` y `servicio`; Cicero reapuntó `parametros/ejecucion.py` a
`hibrido.priors`, `hibrido.replay` y `hibrido.servicio`. Ninguno modificó
`proyeccion/horizonte/` ni `pronostico_horizonte.py`.

### Evidencia final de esta ronda

```text
python -m pytest packages/analitica/tests -q       666 passed, 3 skipped, 33507 warnings
python -m pytest apps/dashboard/tests -q            197 passed, 21043 warnings
PYTHONPATH=src python -m pytest domain etl -q       64 passed
python -m pytest -q                                 927 passed, 3 skipped, 54550 warnings
python -m ruff check --no-cache ...                 All checks passed
python -m compileall -q ...                         exit 0
python -m pip check                                 No broken requirements found
CLI + ayudas de scripts                            46 módulos OK
wheel limpio                                      282 esperados, 282 presentes, 0 bytecode
```

También quedaron comprobadas las firmas públicas del híbrido, la ausencia de imports de la
fachada histórica desde `parametros/ejecucion.py`, la prueba AST contra el ciclo y el entry point
`aquanqa-analytics = analitica.cli:main`. El workflow `.github/workflows/python.yml` ahora
incluye una compuerta explícita para analítica, build del wheel, Ruff, compileall, `pip check` y
ayuda de CLI.

### Decisión reestructurada

1. **Refactor funcional:** cerrado para el alcance local. Las fachadas históricas, los contratos,
   fórmulas, modelos, versiones, SQL, tablas, escenarios, estados, rutas de exportación y orden
   de efectos se conservaron; las nuevas pruebas no alteran esos contratos.
2. **Arquitectura:** el ciclo de híbrido y el acoplamiento de parámetros a la fachada quedaron
   corregidos. Se mantiene como deuda controlada que algunos servicios consuman fachadas públicas
   históricas; no se eliminarán esos reexports sin pruebas de consumidores y deprecación explícita.
3. **Warnings:** el baseline queda registrado, pero no se ocultará ni se convertirá todo en
   error de golpe: hay 54.550 advertencias, principalmente de pandas/NumPy y algunos tests. La
   siguiente tarea debe clasificar fuentes, corregir las advertencias propias y aplicar un
   presupuesto incremental.
4. **Reproducibilidad:** no se inventará un lockfile. `constraints-analitica.txt` fija versiones
   directas, pero no transitivas ni hashes; falta decidir una política oficial de Python y generar
   locks/constraints por intérprete y plataforma, incluyendo build/deploy/ETL.
5. **Producción:** siguen pendientes las pruebas con DSN PostgreSQL real, Access/Excel oficiales
   y driver `pyodbc`, servidor/registry MLflow, daemon Docker, validación actionlint en CI y
   trazabilidad Git. La etiqueta Docker `python:3.12-slim` tampoco está fijada por digest.

Estado final verificable: **GO para el refactor y la regresión local; NO GO para producción o
cierre de reproducibilidad** hasta resolver las compuertas externas, la política de warnings y
el lockfile/matriz Python con sus recursos reales.

## Plan de continuidad tras la auditoría de requisitos completos (2026-08-29)

La comparación literal con las dos especificaciones muestra que aún hay entregables locales que
sí pueden completarse sin infraestructura externa:

1. Crear los tres ADR con los nombres requeridos exactamente, registrando responsabilidad movida,
   motivo, API conservada, pruebas, riesgos y rollback. Los ADR equivalentes existentes se
   conservarán como historial y se enlazarán al índice sin borrar documentación del usuario.
2. Revisar `candidate_turno_temporal.py`: si las fronteras son demostrables, mover su lógica a
   `proyeccion/candidatos/` y dejar una fachada compatible; mantener fechas, fugas temporales,
   columnas y resultados idénticos.
3. Revisar `operativo_excel.py` y `validacion_operativa.py`: separar lectura, normalización,
   cálculo, validación y salida solo donde haya equivalencia demostrable; mantener la lectura
   lazy de Access/Excel, hashes, errores y contratos de exportación.
4. Añadir pruebas de arquitectura para esas fachadas y ejecutar cada subagente hasta informe
   final antes de integrar. Ningún subagente tocará `proyeccion/horizonte/` ni
   `pronostico_horizonte.py`.
5. Repetir suite analítica, dashboard, domain+ETL, raíz, Ruff, compileall, ayudas, wheel y
   `pip check`; después revisar nuevamente este plan. Los bloqueos de PostgreSQL, Access/Excel
   oficial, MLflow, Docker, lockfile y warnings seguirán separados y explícitos.

Estado previo: **GO para cerrar entregables locales pendientes; NO GO para producción**.

## Plan revisado antes de la auditoría de servicios de segundo nivel (2026-08-29)

La ejecución posterior a la última revisión confirmó que candidatos temporales, operación y
documentación ya están cubiertos, pero la comparación del inventario completo aún identifica dos
servicios de aplicación grandes con fronteras funcionales demostrables:

1. `servicios/certificar_releases_replay.py`: separar contratos, lectura/consultas, certificación
   del universo y persistencia de releases, conservando exactamente SQL, transacciones, estados,
   errores y el parámetro `aplicar`.
2. `servicios/persistir_hibrido_parametros_asof.py`: separar configuración, lectura de baselines y
   snapshots, construcción candidate-only, preflight, persistencia y orquestación, manteniendo
   el aislamiento de baselines y las reglas `as-of`.
3. Mantener ambas rutas como fachadas compatibles, añadir pruebas de identidad/paridad y no
   tocar `proyeccion/horizonte/` ni `pronostico_horizonte.py`.
4. Esperar los informes finales de los subagentes, revisar sus cambios desde el hilo principal y
   ejecutar nuevamente todas las suites, static gates, ayudas y wheel antes de reestructurar el
   plan otra vez.

El lockfile transitivo, la matriz oficial de Python, warnings, Docker, PostgreSQL real,
Access/Excel oficial, MLflow remoto y la trazabilidad Git siguen siendo compuertas separadas; no
se simularán durante esta extracción.

Estado previo: **GO para continuar el refactor local; NO GO para producción**.

## Revisión final posterior a servicios de segundo nivel (2026-08-29)

Se esperaron los dos subagentes hasta sus informes finales y se cerraron después de revisar sus
cambios. Kuhn dejó `certificar_releases_replay.py` como fachada de 129 líneas con contratos,
lectura, certificación, serialización y persistencia separados; Locke dejó
`persistir_hibrido_parametros_asof.py` como fachada de 353 líneas con configuración, lectura,
candidate-only, preflight, persistencia y orquestación separados. Se conservaron SQL, tablas,
transacciones, estados, `run_id`, reglas `as-of`, firmas y orden de efectos. No se modificaron
`proyeccion/horizonte/` ni `pronostico_horizonte.py`.

También quedaron creados los ADR con los nombres exactos exigidos:
`0009-refactor-interno-analitica.md`, `0010-desacoplamiento-nucleo.md` y
`0011-descomposicion-proyeccion.md`; el índice enlaza los tres y conserva los documentos
anteriores como antecedentes.

### Evidencia posterior a esta ronda

```text
python -m pytest packages/analitica/tests -q       675 passed, 3 skipped, 33507 warnings
python -m pytest apps/dashboard/tests -q            197 passed, 21043 warnings
PYTHONPATH=src python -m pytest domain etl -q       64 passed
python -m pytest -q                                 936 passed, 3 skipped, 54550 warnings
python -m pytest test_fronteras + fachadas          26 passed
python -m ruff check --no-cache ...                 All checks passed
python -m compileall -q ...                         exit 0
python -m pip check                                 No broken requirements found
CLI + ayudas de scripts                            46 módulos OK
wheel limpio                                      304 esperados, 304 presentes, 0 bytecode
imports públicos                                   9 módulos y cli.main OK
```

### Decisión final del plan

1. **Alcance local del refactor:** completado para las familias con fronteras demostrables:
   núcleo compartido, fenología, híbrido, relaciones, candidatos, parámetros, operación,
   persistencia, servicios de aplicación, CLI, scripts, visualizaciones y dashboard. Las
   fachadas históricas permanecen para compatibilidad.
2. **Módulos grandes deliberadamente cohesivos:** `nucleo/clima.py`, `catalogos.py`,
   `nucleo/bhattacharya.py` y el pipeline de `candidate_param_delta.py` no se dividieron solo
   por cantidad de líneas; no hay evidencia suficiente para hacerlo sin riesgo científico.
3. **Compatibilidad:** las pruebas de fronteras/imports comprueban las fachadas requeridas,
   las nuevas partes internas, el entry point y las rutas públicas. No se eliminarán aliases ni
   archivos históricos sin un baseline versionado, pruebas de consumidores y deprecación.
4. **Warnings:** el baseline queda en 54.550 para la raíz. No se ocultó ni se convirtió todo en
   error; la próxima tarea de mantenimiento debe clasificar y reducir advertencias propias sin
   mezclar cambios de cálculo.
5. **Reproducibilidad y publicación:** sigue pendiente el lock transitivo con hashes, la matriz
   oficial de Python, digest Docker, actionlint, PostgreSQL real, Access/Excel oficiales y
   MLflow remoto. El checkout tampoco tiene commit/tag de rollback dedicado.

Estado final verificable: **GO para refactor y regresión local; NO GO para producción y cierre
definitivo** hasta completar las compuertas externas, reproducibilidad, warnings y rollback.

## Plan revisado antes de mantenimiento de warnings (2026-08-29)

La nueva auditoría de calidad distingue entre advertencias controlables por el proyecto y avisos
emitidos por tests o por la combinación actual pandas/NumPy. Se hará una corrección pequeña y
verificable:

1. Corregir el `FutureWarning` propio de `servicios/param_delta_momentum.py` sin cambiar valores,
   columnas, tipos esperados, cobertura ni la semántica de R09 ausente.
2. Añadir una prueba de regresión que demuestre la paridad de esa columna y que la salida siga
   distinguiendo `r09_disponible` de `r09_kg=0`.
3. Medir nuevamente el baseline de warnings; no filtrar globalmente ni convertir de golpe todos
   los avisos en errores. Las advertencias externas o de tests se documentarán para una etapa
   independiente.
4. Esperar el informe final del subagente, revisar el diff y repetir paquete, dashboard,
   domain+ETL, raíz, Ruff, compileall, CLI, ayudas y wheel. Después se actualizará este plan.

Esta etapa no toca fórmulas científicas, fachadas, SQL, tablas, rutas históricas, horizonte ni
`pronostico_horizonte.py`.

Estado previo: **GO para mantenimiento local acotado; NO GO para producción**.

## Revisión final posterior a mantenimiento de warnings (2026-08-29)

Se esperó el informe final de McClintock, se revisó su diff y se confirmó que la corrección
queda limitada a la asignación de `r09_kg` en `servicios/param_delta_momentum.py`: cuando R09 no
está disponible se conserva el cero de capacidad, y cuando sí está disponible se conserva el
valor observado. La prueba de screening ahora cubre esa paridad. No se modificaron fórmulas,
SQL, tablas, fachadas públicas, rutas de exportación, CI ni las rutas reservadas
`proyeccion/horizonte/` y `pronostico_horizonte.py`.

### Evidencia final posterior a esta etapa

```text
python -m pytest packages/analitica/tests -q       675 passed, 3 skipped, 33506 warnings
python -m pytest apps/dashboard/tests -q            197 passed, 21043 warnings
PYTHONPATH=src python -m pytest domain etl -q       64 passed
python -m pytest -q --disable-warnings              936 passed, 3 skipped, 54549 warnings
screening + -W error::FutureWarning                 17 passed, 7 DeprecationWarnings
python -m ruff check --no-cache ...                 All checks passed
python -m compileall -q ...                         exit 0
python -m pip check                                 No broken requirements found
CLI + 46 ayudas de scripts                          47 comandos OK
wheel limpio                                       304 esperados, 304 presentes, 0 bytecode
entrypoint                                          aquanqa-analytics = analitica.cli:main
```

La regresión raíz se ejecutó completa después de la corrección, no solo las pruebas del módulo
afectado. La medición estricta de `FutureWarning` pasó; permanecen advertencias deprecadas de
dependencias/tests para una etapa posterior, sin filtros globales. El wheel se construyó en una
copia temporal fuera del árbol fuente para evitar contaminación del paquete.

### Decisión reestructurada después de la auditoría final

1. **Refactor local:** completado para el alcance seguro de `packages/analitica` y sus
   consumidores comprobables: núcleo, fenología, híbrido, relaciones, candidatos, parámetros,
   operación, persistencia, servicios, CLI, scripts, visualizaciones y dashboard. Se conservaron
   fachadas, reexports y archivos históricos para no romper consumidores.
2. **Calidad local:** GO. Las suites analítica, dashboard, domain+ETL y raíz pasan; también pasan
   arquitectura/imports, Ruff, `compileall`, `pip check`, ayudas de CLI/scripts y el wheel limpio.
3. **Warnings:** mejora aplicada sin alterar cálculo; queda pendiente clasificar y reducir las
   54.549 advertencias raíz restantes, principalmente de dependencias/tests. No se deben ocultar
   con filtros globales.
4. **Producción/reproducibilidad:** NO GO todavía. Faltan lock transitivo con hashes y política
   oficial de Python, digest de Docker, `actionlint`, DSN PostgreSQL real, archivos Access/Excel
   oficiales con `pyodbc`, servidor/registry MLflow y un commit/tag de rollback. Estas compuertas
   no se pueden certificar desde el entorno local actual.
5. **Siguiente etapa segura:** preparar esas compuertas con infraestructura y decisión del equipo;
   después repetir la matriz completa. No eliminar aliases ni archivos antiguos hasta contar con
   baseline versionado, pruebas de consumidores y una deprecación explícita.

Estado final de esta ejecución: **GO para el refactor y la regresión local; NO GO para producción
y cierre definitivo de reproducibilidad** por las compuertas externas documentadas.

## Plan revisado antes de la auditoría de completitud (2026-08-29)

La continuidad del objetivo exige comprobar el estado actual contra las dos especificaciones
originales, no asumir que la evidencia anterior sigue siendo suficiente. La auditoría seguirá
este orden:

1. **Inventario y límites:** verificar que todo `packages/analitica` y sus consumidores estén
   cubiertos, identificar fachadas, reexports, subpaquetes y archivos generados, y confirmar que
   `proyeccion/horizonte/` y `pronostico_horizonte.py` permanezcan fuera del cambio de esta tarea.
2. **Configuración y distribución:** revisar `pyproject.toml`, dependencias opcionales, todos los
   subpaquetes declarados, entrypoint, scripts `python -m` y workflow de CI.
3. **Compatibilidad y arquitectura:** comprobar imports públicos, ciclos, contratos, rutas de
   exportación, dashboard y consumidores; separar evidencia directa de evidencia ausente por
   infraestructura externa.
4. **Pruebas y calidad:** revisar que existan pruebas para fórmulas, escenarios, temporalidad,
   formatos, scripts y fachadas; repetir solo las pruebas necesarias después de cualquier cambio.
5. **Corrección local:** implementar los incumplimientos que puedan resolverse en el checkout sin
   cambiar fórmulas, SQL, tablas, modelos, escenarios ni contratos; conservar rollback mediante
   diff y no borrar archivos históricos.
6. **Auditoría posterior:** ejecutar regresión, Ruff, `compileall`, `pip check`, ayudas, wheel y
   pruebas de fronteras; registrar resultados, limitaciones externas y la decisión final en una
   nueva sección de este plan.

La auditoría no declarará producción lista si faltan DSN/archivos oficiales, servidor MLflow,
driver Access, Docker, lockfile/matriz Python o rollback versionado. Esos elementos se tratarán
como evidencia faltante, no como éxito inferido por pruebas locales.

## Revisión final posterior a la auditoría de completitud (2026-08-29)

La auditoría contra `pasted-text-1.txt` y `pasted-text-2.txt` confirmó que las etapas locales del
plan están implementadas: utilidades compartidas, contratos del núcleo, fachadas de fenología e
híbrido, relaciones, persistencia, candidatos, parámetros, operación, servicios, CLI, scripts,
visualizaciones, dashboard, empaquetado y CI. Los módulos grandes sin frontera segura adicional se
mantienen cohesivos. Se verificó que los 46 scripts no importan otros scripts y que las rutas
públicas siguen resolviendo.

El único incumplimiento local encontrado fue de cobertura de aceptación: no existía una prueba
explícita para el camino CSV de `COPY analytics.prediction`. Se añadió una prueba de contrato que
comprueba `FORMAT CSV`, quoting, columnas principales y conservación de columnas extra dentro de
`componentes`; no se cambió la persistencia ni su SQL. También se actualizaron los ADR para que
sus cifras coincidan con la regresión vigente.

### Evidencia posterior a la auditoría

```text
python -m pytest --version                         pytest 9.1.1
python -m pytest packages/analitica/tests -q       676 passed, 3 skipped, 33506 warnings
python -m pytest apps/dashboard/tests -q            197 passed, 21043 warnings
PYTHONPATH=src python -m pytest domain etl -q       64 passed
python -m pytest -q                                 937 passed, 3 skipped, 54549 warnings
CSV + FutureWarning estricto                       17 passed, 7 DeprecationWarnings
python -m ruff check --no-cache ...                 All checks passed
python -m compileall -q ...                         exit 0
python -m pip check                                 No broken requirements found
CLI + 46 scripts                                   47 comandos OK
imports públicos                                   public_imports_ok
wheel limpio                                       304 fuente, 304 wheel, 0 bytecode
entrypoint                                          aquanqa-analytics = analitica.cli:main
```

La salida de `git diff --check` termina correctamente; solo informa la normalización CRLF/LF de
dos archivos ya modificados. Las rutas reservadas `proyeccion/horizonte/` y
`pronostico_horizonte.py` se conservaron sin cambios en esta ejecución. La copia temporal
incompleta producida durante una validación fue apartada fuera del árbol fuente y no participa en
el paquete ni en las pruebas.

### Decisión posterior a la auditoría

1. **Requisitos locales:** cumplidos y verificables. La suite conjunta, el dashboard, domain/ETL,
   imports, scripts, CI declarado, wheel y controles estáticos tienen evidencia actual.
2. **Compatibilidad:** mantenida mediante fachadas y reexports. No se borraron módulos históricos,
   no se cambiaron fórmulas, resultados, SQL, tablas, escenarios, versiones ni reglas `as-of`.
3. **Calidad:** el warning propio de R09 ya fue corregido sin cambiar su semántica. Las 54.549
   advertencias raíz restantes siguen siendo deuda de mantenimiento, principalmente de tests o
   dependencias, y no se ocultan mediante filtros globales.
4. **Control de cambios:** no se crearon commits ni tags porque el checkout contiene cambios
   locales preexistentes y el estado de trabajo debe preservarse; por ello el rollback versionado
   requerido por la especificación continúa pendiente de una acción explícita del equipo.
5. **Compuertas externas:** PostgreSQL real, Access/Excel oficiales con `pyodbc`, MLflow remoto,
   Docker/actionlint, lock transitivo con hashes y matriz oficial de Python siguen sin evidencia
   disponible en este entorno. No se simulan ni se declaran aprobadas.

Estado actualizado: **GO para el refactor y la regresión local; NO GO para producción y cierre
definitivo** hasta aportar las compuertas externas, reproducibilidad y rollback versionado.

## Plan revisado después de la auditoría especializada (2026-08-29)

Los dos informes finales fueron esperados y comparados. Carson confirmó el empaquetado actual y
la reproducibilidad byte-a-byte al fijar `SOURCE_DATE_EPOCH`; Wegener detectó correctamente que
los wheels históricos conservados en `dist*` no sirven como artefactos de publicación. Ambos
coincidieron en que las integraciones externas y el rollback versionado no están demostrados.

Se actuará solo sobre hallazgos locales seguros:

1. Declarar `hypothesis` en el extra `dev` y fijarlo en `constraints-analitica.txt`, porque la
   especificación lo exige aunque la suite actual no lo importe directamente.
2. Sustituir el `simplefilter("ignore")` global de `inferencia.py` por un filtro limitado a
   `ConvergenceWarning` de `statsmodels`, dejando visibles avisos inesperados.
3. Evitar el `RuntimeWarning` de `np.nanmean` cuando no existe ningún WAPE válido, preservando el
   resultado `NaN`; añadir una prueba de regresión para esa condición.
4. Corregir dos asignaciones incompatibles en tests que provocan `FutureWarning`, sin cambiar los
   datos que el test presenta al contrato.
5. Hacer que los workflows construyan el wheel con `SOURCE_DATE_EPOCH` derivado del commit para
   que una misma revisión produzca el mismo artefacto; no usar un wheel histórico incompleto.
6. Ejecutar la suite completa, warnings estrictos de las categorías corregidas, Ruff,
   `compileall`, `pip check`, ayudas y wheel; luego registrar una revisión posterior del plan.

No se tocarán las rutas reservadas de horizonte, fórmulas, resultados, SQL, tablas, modelos,
escenarios, reglas `as-of` ni archivos de datos oficiales inexistentes.

## Revisión final posterior a la auditoría especializada (2026-08-29)

Se esperaron los dos subagentes hasta sus informes finales y se cerraron después de revisar sus
conclusiones. Carson confirmó que el wheel construido desde el checkout actual contiene 304/304
módulos, no contiene bytecode y puede reproducirse byte-a-byte fijando `SOURCE_DATE_EPOCH`.
Wegener encontró wheels históricos incompletos en `dist*`; la revisión principal comprobó que no
son artefactos válidos de publicación y que no representan el wheel recién construido.

La auditoría también identificó deuda real de calidad: un filtro global de warnings en
`proyeccion/inferencia.py`, un `RuntimeWarning` propio en la métrica de fenología y dos
`FutureWarning` generados por asignaciones incompatibles en tests. Se corrigieron esos puntos sin
cambiar cálculos, SQL, tablas, resultados ni rutas reservadas. Se declaró `hypothesis` en el
extra `dev` y en constraints, y ambos workflows que construyen analítica derivan
`SOURCE_DATE_EPOCH` del commit.

### Evidencia posterior a las correcciones

```text
python -m pytest packages/analitica/tests -q -W error::RuntimeWarning -W error::FutureWarning
                                                     677 passed, 3 skipped, 33502 warnings
python -m pytest apps/dashboard/tests -q --disable-warnings
                                                     197 passed, 21043 warnings
PYTHONPATH=src python -m pytest domain etl -q --disable-warnings
                                                     70 passed
python -m pytest -q --disable-warnings               944 passed, 3 skipped, 54545 warnings
FutureWarning en preflight+horizonte                  20 passed, 0 FutureWarning
fenología con RuntimeWarning estricto                  5 passed, 0 RuntimeWarning
python -m ruff check --no-cache ...                   All checks passed
python -m compileall -q ...                           exit 0
python -m pip check                                   No broken requirements found
workflows YAML                                       4 válidos
CLI + 46 scripts                                     47 comandos OK
wheel reproducible                                   hash A = hash B
wheel                                               304 fuente, 304 wheel, 0 bytecode
```

El hash reproducible obtenido en esta auditoría fue
`0B07DCB66213922034EF2691E5F8E7436976BF9FF6EA7D4B299BE67F47EF7C7C` en ambas construcciones.
El nuevo test de persistencia comprueba el contrato CSV de `COPY analytics.prediction`; la
prueba estricta de warnings confirma que no quedan `FutureWarning` ni `RuntimeWarning` en las
rutas corregidas. Persisten `DeprecationWarning` de la matriz NumPy/Pandas, tests y la ruta
reservada de horizonte, que no fue modificada por instrucción.

### Decisión posterior a la auditoría especializada

1. **Calidad local:** GO. El filtro amplio fue reemplazado por uno específico de
   `ConvergenceWarning`, las muestras vacías conservan `NaN` sin warning y los tests presentan
   explícitamente los tipos compatibles. `hypothesis` queda declarado como dependencia de
   desarrollo.
2. **Reproducibilidad local:** mejorada y verificable para el wheel: dos copias limpias del mismo
   fuente producen el mismo SHA-256 y el mismo inventario de módulos. Los wheels históricos en
   `dist*` no se usarán para publicar.
3. **Compatibilidad:** las suites posteriores pasan y las fachadas, reexports, fórmulas,
   resultados, SQL, tablas, escenarios, versiones y reglas `as-of` permanecen sin cambios en
   esta etapa.
4. **Pendientes no resolubles localmente:** no existe todavía baseline limpio/commit por etapa ni
   tag de rollback; además faltan lock transitivo con hashes y validación real de PostgreSQL,
   Access/Excel con `pyodbc`, MLflow, Docker, actionlint y ejecución GitHub.
5. **Decisión global:** el estado sigue siendo **GO para refactor, regresión y wheel local; NO GO
   para producción** hasta cerrar esas compuertas externas y el rollback versionado.

## Plan revisado antes del mantenimiento de `DeprecationWarning` (2026-08-29)

La auditoría especializada dejó una señal de mantenimiento adicional: todavía aparecen
`DeprecationWarning`, principalmente en conversiones numéricas de NumPy/Pandas, además de
warnings de tests/dependencias y de la ruta de horizonte reservada. Antes de cambiar código,
se reestructura el trabajo así:

1. **Clasificar el origen:** separar warnings propios de producción, tests, dependencias externas
   y archivos reservados. Solo los primeros dos grupos mantenibles entran en esta fase.
2. **Corregir con cambios semánticamente neutros:** usar unidades explícitas o conversiones a
   tipos nativos únicamente donde la evidencia reproduzca el warning; no cambiar fórmulas,
   horizontes, SQL, tablas, contratos públicos ni reglas `as-of`.
3. **Proteger las fronteras del encargo:** no modificar ningún archivo bajo
   `packages/analitica/proyeccion/horizonte/` ni
   `packages/analitica/proyeccion/pronostico_horizonte.py`, que están siendo integrados por otro
   trabajo.
4. **Validar por capas:** ejecutar primero las pruebas del módulo afectado y después la suite de
   analítica con `RuntimeWarning`/`FutureWarning` estrictos, Ruff y compilación; si hay cambios
   relevantes, repetir la regresión completa y la auditoría del wheel.
5. **Cerrar la revisión:** documentar qué warnings desaparecieron, cuáles pertenecen a terceros o
   a rutas reservadas y qué compuertas de producción siguen abiertas. El criterio de salida es
   evidencia reproducible, no la desaparición artificial de todos los warnings.

## Revisión posterior al mantenimiento de `DeprecationWarning` (2026-08-29)

La auditoría y su validación posterior produjeron estos cambios y resultados:

1. **Correcciones aplicadas:** se hicieron conversiones de tiempo con unidad explícita en
   Bhattacharya, `CandidateParamDelta`, preflight, fuentes, residual as-of y turno/reingreso;
   también se corrigieron fixtures de tests que generaban el mismo warning. No se modificaron
   `packages/analitica/proyeccion/horizonte/` ni
   `packages/analitica/proyeccion/pronostico_horizonte.py`.
2. **Pruebas funcionales:** la batería focalizada pasó con `62 passed` bajo
   `RuntimeWarning` y `FutureWarning` estrictos; la suite de analítica pasó con
   `677 passed, 3 skipped` y `30.246 warnings`; la suite completa pasó con
   `944 passed, 3 skipped` y `51.289 warnings`.
3. **Calidad técnica:** Ruff terminó en `All checks passed`, `compileall` terminó con código 0,
   `pip check` informó `No broken requirements found`, los cuatro workflows YAML fueron válidos
   y CLI/scripts conservaron sus comprobaciones de ayuda.
4. **Artefacto:** dos copias limpias, construidas con `SOURCE_DATE_EPOCH=0`, produjeron el mismo
   SHA-256 `93AC79D591F36188556B021CB74B97558BAB2657712A6529AAB3316754834C07`; el wheel contiene
   `304` módulos Python, `0` bytecode y conserva el entrypoint.
5. **Interpretación:** la reducción de warnings de analítica fue de `33.502` a `30.246`. Los
   restantes se concentran en llamadas todavía pendientes de migrar a unidades explícitas,
   fixtures antiguos y compatibilidad interna de pandas/NumPy; no se añadió un filtro global.
6. **Revisión de salida:** el plan queda **GO para refactor y regresión local**. Sigue **NO GO para
producción** porque no se resolvieron las compuertas ya identificadas: baseline/commit/tag de
rollback, lockfile transitivo con hashes, PostgreSQL real, Access/Excel con `pyodbc`, MLflow,
Docker operativo, `actionlint` y ejecución GitHub Actions.

## Revisión posterior a la consolidación transversal (2026-08-29)

Se esperaron los tres subagentes especializados hasta sus informes finales y se volvió a revisar
el árbol después de integrar sus hallazgos. El orden se ajustó para terminar primero las capas
locales de bajo riesgo y dejar separadas las comprobaciones que necesitan sistemas o decisiones
del equipo.

### Cambios locales integrados

1. `proyeccion/compartido` es ahora la fuente de implementación para fechas, normalización y
   serialización. Las rutas antiguas (`temporal`, `candidate_*` e `infraestructura.serializacion`)
   siguen disponibles como fachadas compatibles.
2. La implementación real de MLflow vive en `proyeccion/persistencia/mlflow.py`; `tracking.py`
   conserva únicamente la fachada histórica. Gobernanza y persistencia usan la implementación
   nueva sin invertir la dependencia.
3. Persistencia, fenología y relaciones usan directamente la capa común para serialización y
   fechas. `hibrido/replay.py` y el servicio de guardia usan módulos públicos, sin importar
   funciones privadas de otra fachada.
4. Se añadieron pruebas AST de fronteras e identidad para impedir que estas dependencias legacy
   vuelvan a aparecer. No se eliminaron aliases públicos porque aún protegen consumidores
   históricos.
5. El workflow Python limpia `__pycache__`, `.pyc` y carpetas de build antes de crear el wheel.
   `pyodbc` y `gunicorn` quedaron fijados en `constraints-analitica.txt`; el controlador Access
   sigue siendo una dependencia externa del sistema operativo.

### Evidencia final local

```text
python -m pytest --version                         pytest 9.1.1
python -m pytest packages/analitica/tests -q       679 passed, 3 skipped
python -m pytest apps/dashboard/tests -q           197 passed
PYTHONPATH=src python -m pytest domain etl -q      70 passed
python -m pytest -q                                946 passed, 3 skipped
python -m ruff check ...                            All checks passed
python -m compileall -q ...                         exit 0
python -m pip check                                No broken requirements found
workflows YAML                                     4 válidos
scripts --help                                     46/46 OK
wheel reproducible                                 hash A = hash B
wheel                                              304 módulos, 0 bytecode, entrypoint OK
```

El wheel reproducible de esta revisión produjo el SHA-256
`F2FE605445062FC200B6FA7798D47C6DC5511E4BFD8764E13882E6AD4E833218` en ambas copias. La suite
estricta de `RuntimeWarning` y `FutureWarning` pasó; permanecen avisos de deprecación de
NumPy/Pandas y de tests/dependencias, sin ocultarlos con un filtro global.

### Estado y decisión

- **GO local:** refactor Python transversal, compatibilidad pública, regresión, compilación,
  empaquetado y workflow declarado.
- **NO GO de producción:** el árbol sigue sin baseline histórica fila por fila ni commit/tag de
  rollback autorizado; SQLFluff continúa con violaciones históricas; faltan la decisión formal
  sobre el alcance SQL, el Access/Excel oficial, el DSN PostgreSQL autorizado, el backend MLflow,
  Docker con daemon, `actionlint` y una ejecución real de CI.
- Las rutas `packages/analitica/proyeccion/horizonte/` y
  `packages/analitica/proyeccion/pronostico_horizonte.py` permanecieron fuera de esta integración
  porque otro trabajo las está creando. El archivo local `mlflow.db` y otros artefactos no
  versionados fueron dejados intactos; no se hizo limpieza destructiva ni commit.

### Próximo orden de trabajo

1. Esperar el cierre del responsable de horizonte y comprobar su compatibilidad con esta capa,
   sin mezclar archivos ni atribuir sus cambios a este refactor.
2. Resolver el alcance SQL y fijar una única cifra/catálogo para Access; bloquear o etiquetar
   explícitamente snapshots parciales.
3. Obtener autorización para un baseline ejecutable y un punto de rollback versionado; después
   versionar el fixture y reemplazar solo artefactos de entrega aprobados.
4. Ejecutar PostgreSQL, Access/Excel, MLflow, Docker y CI reales, y tratar SQLFluff como gate
   visible, no como una comprobación opcional.
5. Repetir la auditoría final. Solo si desaparecen los P1 o quedan aceptados formalmente se podrá
   pasar de **GO para refactor local** a una decisión de liberación.

## Limpieza selectiva y ventana de compatibilidad (2026-08-29)

Para que el tamaño del árbol sea entendible, se separaron tres cosas que antes aparecían juntas:

1. **Generado y eliminable:** se retiraron `580` directorios claramente generados en todo el
   repositorio: cachés de pruebas/lint, `__pycache__`, carpetas `build` y metadatos
   `*.egg-info`. No se borró código fuente, pruebas, SQL ni documentación.
2. **Preservado temporalmente:** se mantienen las ruedas `.whl`, `mlflow.db`, el diagnóstico
   `.tmp_v3_diag.json`, las evidencias de auditoría y sus documentos/fixtures. También se
   mantienen sus contenedores temporales cuando contienen evidencia mezclada; solo se limpian
   dentro de ellos las subcarpetas generadas del punto anterior.
3. **Trabajo paralelo separado:** el checkpoint no incorpora ni altera
   `packages/analitica/proyeccion/horizonte/`, sus pruebas asociadas ni los scripts/servicios de
   horizonte que aún están siendo validados por otro trabajo. Esto evita que una integración
   incompleta se confunda con el refactor consolidado.

Las fachadas activas no se eliminan todavía. La matriz de consumidores y la regla de retiro están
en [19_matriz_fachadas_compatibilidad_2026-08-29.md](19_matriz_fachadas_compatibilidad_2026-08-29.md).
La ventana es la versión actual más la siguiente versión menor. Una fachada solo podrá retirarse
después de no tener consumidores internos, anunciar la deprecación, completar dos regresiones
verdes y confirmar que no existen consumidores externos conocidos; el retiro será un cambio
separado y reversible.

El checkpoint versionado debe contener únicamente la fuente/documentación de esta integración y
excluir los artefactos preservados, las salidas de datos y el trabajo paralelo reservado. La
validación mínima posterior al checkpoint será `python -m pytest`, Ruff sin caché y `python -m
pip check`; cualquier prueba que regenere cachés se ejecutará antes de la comprobación final del
árbol.

## Cierre del bloque de horizonte (2026-08-29)

La suite completa posterior a la limpieza terminó con `946 passed, 3 skipped` en `632.29s`, sin
fallos. Esto incluye las pruebas del bloque de horizonte que estaba separado temporalmente.
Sus `26` archivos se consideran código y pruebas válidos y se integran en un commit independiente,
sin mezclarlos con los artefactos preservados. Después de esa integración, los únicos archivos que
deben seguir fuera de `packages/analitica` serán artefactos/evidencias locales y no código fuente
pendiente. La retirada de fachadas seguirá esperando la ventana de compatibilidad documentada.

## Consolidación final de artefactos locales (2026-08-29)

Después de integrar horizonte se volvió a ejecutar la suite completa y volvió a terminar con
`946 passed, 3 skipped`, sin fallos. Se consolidaron los resultados temporales en el archivo local
ignorado `.artifacts/refactor-auditoria-20260829.zip` (`71` entradas), se conservaron solo los
wheels canónicos (`5`) y quedaron únicamente dos entradas operativas en `.tmp`: una para el panel
por defecto de expertos y otra para las transiciones de parámetros. Las copias de builds, smoke
tests, snapshots de código, ruedas duplicadas y logs de ejecución fueron eliminadas.

Estado final de la fuente: `packages/analitica` tiene `409` archivos fuente/pruebas y `0` archivos
no versionados pendientes; el repositorio tiene `0` cachés/builds/bytecode residuales. `mlflow.db`,
el diagnóstico temporal, los entregables y los snapshots ETL permanecen preservados y excluidos
localmente de Git. La única modificación tracked fuera de estos commits es `CODEOWNERS` eliminado
en el árbol de trabajo, que se deja intacto por ser un cambio ajeno a esta limpieza.

## Consolidación productiva de `proyeccion` (2026-08-29)

La fase pendiente de migración interna se ejecutó sin cambiar fórmulas, contratos ni rutas
históricas. Los comandos, servicios, scripts y dashboard dejaron de importar fachadas raíz y
usan las implementaciones canónicas de cada subpaquete. La comprobación sobre código productivo
encontró `0` imports hacia esas fachadas.

Se eliminaron cinco archivos que eran aliases internos sin lógica y se centralizaron los helpers
estadísticos duplicados de `relaciones_partes/packing.py` en `relaciones_partes/estadistica.py`.
Como resultado, `packages/analitica/proyeccion` queda en `115` módulos Python (`45` raíz y `70`
internos), sin caches/builds/bytecode después de la limpieza final. Se conservaron las fachadas
raíz históricas que pueden consumir notebooks o integraciones externas; su retiro sigue siendo
un cambio posterior a la ventana de compatibilidad, con regresión y rollback separados.

Validación de esta fase:

```text
python -m pytest -q                         942 passed, 3 skipped
python -m ruff check packages/analitica apps/dashboard       All checks passed
python -m compileall -q packages/analitica apps/dashboard   exit 0
python -m pip check                           No broken requirements found
importación de los 114 submódulos de proyeccion               0 fallos
```

## Compactación física posterior (2026-08-29)

La revisión solicitada sobre el exceso de archivos redujo `proyeccion` de `115` a `104`
archivos Python. Las utilidades comunes se consolidaron en `compartido/utilidades.py`, el flujo
Excel operativo en `operativo/excel.py`, Git en `infraestructura/__init__.py` y la selección de
peso en `parametros/mezcla.py`. Los imports históricos de esos micro-módulos siguen resolviendo
mediante aliases controlados, mientras el código productivo usa las entradas canónicas.

Regresión posterior a la compactación: `942 passed, 3 skipped`.

## Retiro final de fachadas históricas (2026-08-29)

El propietario confirmó que este proyecto no usa notebooks, jobs programados ni integraciones
externas que dependan de las rutas históricas. Después de migrar los imports internos y ejecutar
una búsqueda AST completa (imports absolutos, relativos y dinámicos), no quedaron consumidores
internos de las fachadas retiradas.

Se retiraron las fachadas raíz de `proyeccion` para candidatos, fenología, híbrido, parámetros,
operativo, relaciones, temporal, tracking y gobernanza. La carpeta queda en `91` archivos Python
(`32` raíz y `59` internos). Permanecen las implementaciones reales,
`candidate_residual_asof.py` y, por separado, `pronostico_horizonte.py` junto con `horizonte/`,
porque esa validación paralela no formaba parte de este cambio.

Validación del retiro:

```text
python -m pytest -q    943 passed, 3 skipped
```

Los caches, bytecode y carpetas de build se eliminan después de las comprobaciones. Se conservan
temporalmente los wheels, `mlflow.db` y la evidencia de auditoría, tal como se acordó.
