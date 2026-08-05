# Runbook · cambiar el esquema

Cómo modificar `core` —o cualquier capa de `db/sql`— sin romper el contrato de aceptación ni
perder la trazabilidad. Unos 5 minutos si el cambio es pequeño; el rebuild completo tarda ~1 min.

Este procedimiento es el que se siguió para [ADR-0005](../adr/0005-filas-centinela-sin-null-en-fk.md)
(hacer `NOT NULL` tres claves foráneas y añadir filas centinela). Está escrito con ese caso en
mente porque toca todos los pasos: DDL, carga, cuarentena, contrato y documentación.

## Antes de tocar nada

**Verifica el problema con una consulta real.** No con lo que el código *parece* hacer.

Es la regla que más tiempo ahorra, y la que más fácil se salta. Durante ADR-0005 aparecieron
cuatro casos donde la lectura del código y el dato real no coincidían:

- Una columna que se creía sin `COMMENT` ya lo tenía.
- `Descarte` y `DESCARTE` parecían un solo calibre y eran dos filas del catálogo.
- 624 filas de forecast parecían estar en cuarentena y no estaban registradas en ninguna parte.
- Dos motivos de cuarentena apuntaban al hallazgo equivocado (`N-13` en vez de `N-12`).

Ninguno se habría visto leyendo el SQL. Los cuatro salieron de una consulta.

```bash
npm run psql -- -c "SELECT ... "     # confirma el defecto y su magnitud exacta
```

Anota la cifra. La vas a necesitar en el paso 5 para saber si el arreglo funcionó.

## 1 · Edita el DDL, no la base

La fuente de verdad del esquema es `db/sql`. Un `ALTER TABLE` a mano en psql se pierde en el
siguiente `npm run db:reset` y deja la base y el repositorio en desacuerdo.

| Qué cambias | Dónde |
|---|---|
| Tablas de `core`, restricciones | `db/sql/20_core/` |
| Normalización, resolución de identidad | `db/sql/30_stg/` |
| Motivos y umbrales de cuarentena | `db/sql/40_qua/010_cuarentena.sql` |
| Cómo se cargan los hechos | `db/sql/50_carga_core/` |
| Dimensiones y hechos del modelo estrella | `db/sql/60_dim_fact/` |
| Vistas de compatibilidad para Power BI | `db/sql/70_reporting/` |

**Comenta el porqué en el propio SQL**, con el número de hallazgo o de ADR. Un `NOT NULL` sin
explicación es indistinguible de un descuido seis meses después.

## 2 · Si el cambio afecta a la carga, ajústala en el mismo paso

Un `NOT NULL` nuevo sin ajustar la carga hace fallar el `build` con un error de restricción, que
es exactamente lo que debe pasar — pero el arreglo es incompleto hasta que la carga sabe qué
poner. Los dos van juntos, en el mismo commit.

Si el dato no resuelve, no lo dejes nulo: apunta a la fila centinela de su dimensión (ADR-0005)
**y** regístralo en `qua.rechazos` con su motivo. Las dos cosas, no una:

- El centinela resuelve la **integridad referencial**.
- La cuarentena resuelve la **trazabilidad**.

Y si el motivo que necesitas no describe exactamente el problema, **crea uno nuevo** en
`qua.umbral` en lugar de reutilizar el que más se parezca. Reutilizar `LOTE_INEXISTENTE` para un
fallo de *módulo* infló ese contador por encima de su tope y mezcló dos problemas distintos en
una sola cifra; el arreglo fue un motivo propio, `MODULO_INEXISTENTE`, con su propio umbral.

## 3 · Reaplica solo la capa que cambió

Para iterar rápido mientras el cambio es de DDL declarativo o de una función:

```bash
npm run sql 40_qua              # o la carpeta que sea
```

Ojo con dos límites de PostgreSQL que aparecen a menudo:

- `CREATE OR REPLACE VIEW` **no** permite insertar una columna en medio ni cambiar un tipo. Hay
  que `DROP VIEW` y recrear. (Pasó dos veces en ADR-0005.)
- Reaplicar una capa **no** recarga los datos. Las filas ya cargadas conservan los valores
  viejos: si cambiaste una etiqueta que se escribe al insertar, hace falta el paso 4.

## 4 · Reconstruye desde cero

Cuando el cambio afecta a lo que se escribe en las filas, no solo a la estructura:

```bash
npm run db:reset    # borra core, stg, qua, dim, fact, reporting — NO toca raw
npm run build       # los reconstruye y recarga
```

`raw` queda intacto, así que **no** hay que repetir la extracción del `.accdb` (que son ~10
minutos). Todos los `sp_cargar_*` vacían su propio destino antes de recargar, así que el
resultado es idéntico corriendo `build` una o cinco veces.

Lee los `NOTICE` del build: dicen cuántas filas cargó cada tabla y cuántas apartó. Es la primera
señal de que algo cambió de forma inesperada.

## 5 · Corre el contrato y compáralo con antes

```bash
npm run validate
```

Y mira tres cosas, en este orden:

1. **El veredicto.** Sin comprobaciones nuevas en `error`, y sin `FALLA` que no fueran las tres
   ya conocidas del grupo `core` (ver [runbook de cierre](02-cierre-de-migracion.md) §1.1).
2. **La cuarentena.** Ningún motivo en `REVISAR`. Si uno se pasó de su tope, **no subas el tope
   sin más**: averigua por qué. Un umbral se sube solo con la explicación de por qué, en el mismo
   commit.
3. **La cifra que anotaste al principio.** Que el defecto que ibas a corregir marque ahora el
   valor esperado, no solo que "no falle nada".

Si el cambio tiene una cifra verificable, **añádela al contrato** como comprobación nueva en
`db/sql/90_checks/010_contrato.sql`. Así el arreglo queda protegido contra una regresión futura.
ADR-0005 añadió cinco.

## 6 · Documenta

| Qué añadiste | Dónde se registra |
|---|---|
| Un hallazgo nuevo verificado con datos | Sección `N-nn` en `docs/historico-access/05_ADDENDA_TECNICA.md` |
| Una decisión que cierra una alternativa razonable | Un ADR nuevo en `docs/adr/`, más su fila en el índice |
| Un cambio sin alternativa real | Basta el comentario en el SQL |

Y comitea el cambio de contenido **por separado** de cualquier movimiento de archivos. Un commit
que mezcla un `git mv` con un cambio de lógica es ilegible en `git log`.

## Lista de comprobación

```
[ ] Verifiqué el defecto con una consulta real y anoté la cifra
[ ] Edité db/sql, no la base a mano
[ ] Ajusté la carga si el cambio lo requería (centinela + cuarentena, no uno solo)
[ ] Motivo de cuarentena propio si el problema es distinto, no reutilizado
[ ] npm run db:reset && npm run build sin errores
[ ] npm run validate: veredicto sin fallas nuevas, cuarentena sin REVISAR
[ ] La cifra del principio marca ahora el valor esperado
[ ] Comprobación nueva en el contrato, si el arreglo tiene una cifra verificable
[ ] Documentado: addenda, ADR o comentario en el SQL
```
