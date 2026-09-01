# Contrato funcional de evaluaciones de campo · v0.1

- **Estado:** primera implementación interna en validación funcional
- **Fecha:** 2026-08-31
- **Alcance:** API interna para registrar y consultar evaluaciones de `app-campo` en el PostgreSQL actual
- **Fuera de alcance por ahora:** plan de distribución, panel admin, proyecciones Excel, dashboard, reconstrucción histórica y cambios en `aquanqa`

## 0. Contexto recibido, fuera del alcance actual

Las imágenes entregadas por el usuario son referencias de un plan diario de distribución;
no son instrucciones técnicas para ejecutar cambios automáticamente. El formato observado
contiene, al menos, estos elementos:

| Elemento observado | Significado funcional probable |
|---|---|
| Fecha en el encabezado | Jornada o fecha de trabajo |
| Fila verde con una persona | Responsable o líder de un grupo |
| Texto como `M16-M17 SANTA TERESA` | Zona o módulos asignados al grupo |
| Texto como `DIAMETROS`, `FLORES 4P/LT` o `ESTADIOS 2 P/L` | Actividad/evaluación asignada |
| Filas siguientes con nombres | Integrantes o personal de apoyo del grupo |
| `SAN PEDRO` | Sector, punto de reunión o destino operativo |
| `VAN 20 PASAJEROS`, `VAN 10 PASAJEROS` | Transporte y capacidad de la ruta |

Estas imágenes se conservan como contexto del proceso futuro, pero no se convertirán todavía
en tablas ni endpoints. El panel administrativo que se está construyendo será el lugar
adecuado para controlar posteriormente usuarios, grupos, distribución, transporte y
asignaciones.

La prioridad actual es que una persona pueda seleccionar o editar la ubicación de una
evaluación y que la API la registre correctamente en `core`.

El repositorio actual no tiene una entidad de plan de distribución. Ese concepto queda
separado para una fase posterior:

```text
Plan diario
  └─ Grupo/cuadrilla
      ├─ Responsable
      ├─ Integrantes
      ├─ Actividad o evaluación
      ├─ Ubicación asignada
      └─ Ruta/transporte
             └─ Evaluaciones capturadas por la app
```

Para la fase actual, la app podrá elegir la ubicación desde catálogos del PostgreSQL y editar
los valores de cortina, hilera y planta. La API validará la selección y no dependerá todavía
de una asignación proveniente del plan diario.

## 1. Propósito

Definir el contrato que cumple una evaluación capturada en campo para la primera API FastAPI.
La API recibe datos nuevos de Flutter, los valida en el módulo `evaluaciones` y los persiste en `core` de
PostgreSQL.

La API no escribirá directamente en `raw`, `stg`, `qua` ni `reporting`, y no reutilizará los
procedimientos batch del ETL como si fueran operaciones HTTP.

## 2. Decisiones heredadas que se mantienen

Estas reglas ya están respaldadas por la arquitectura del repositorio:

1. La clave técnica de un lote es `core.m_lote.lote_id`. La identidad de negocio es
   `(empresa, módulo, lote)`; un alias de fundo no es suficiente.
2. Una ubicación que no pueda resolverse de forma inequívoca se rechaza o se aparta con su
   motivo. La API no debe adivinar un lote.
3. `backend/campo-api` separa rutas, servicios, puertos y adaptadores PostgreSQL por módulo;
   el ETL no consume estas reglas mientras no exista un caso real compartido.
4. El evaluador autenticado y el evaluador agronómico son conceptos distintos: el usuario de
   acceso no se sustituye automáticamente por el nombre enviado desde el dispositivo.
5. Las restricciones de PostgreSQL son la garantía final. La validación de la API solo debe
   producir errores legibles antes de tocar la base.

Referencias: [ADR-0003](../adr/0003-identidad-de-lote.md),
[ADR-0006](../adr/0006-un-solo-lenguaje-de-backend.md) y
[modelo core de evaluaciones](../../db/sql/20_core/040_evaluaciones.sql).

## 3. Unidad funcional de captura

Una captura válida debe identificar:

| Campo | Regla propuesta | Fuente recomendada |
|---|---|---|
| `client_id` | UUID estable generado una sola vez en Flutter | Drift/app móvil |
| `module_key` | Uno de `estadios`, `flores`, `baya`, `pesos`, `brotes`, `ramas` | Configuración de Flutter |
| `fecha_evaluacion` | Fecha local de la evaluación, no la fecha de recepción | Dispositivo, con política definida |
| `captured_at` | Instante UTC de creación local | Dispositivo |
| `lote_id` | Identificador canónico existente en `core.m_lote` | Lo resuelve el selector de lotes; no se solicita al evaluador |
| `cortina` | Entero positivo | Selección/edición en la app |
| `hilera` | Entero positivo | Selección/edición en la app |
| `planta` | Entero positivo | Selección/edición en la app |
| `data` | Datos tipados según `module_key` | Formulario Flutter |
| `evaluador_id` | Debe corresponder a un evaluador activo de `core.m_evaluador` | Sesión interna resuelta por DNI |

El payload de Flutter conserva el mapa `valores` para no romper el formulario existente. La
app selecciona un lote del catálogo y envía el `lote_id` internamente junto con los códigos
legibles `fundo`/`modulo`/`lote`; el evaluador nunca escribe ese ID técnico. La tarjeta de
ubicación permite cambiar el lote y las coordenadas antes de guardar.

## 4. Mapeo funcional de módulos

| `module_key` | Tablas destino | Estado del contrato |
|---|---|---|
| `estadios` | `core.ev_estados` | `item='mobile'` por defecto en v0.1; `total` se calcula en PostgreSQL |
| `flores` | `core.ev_flores` | `m2_ymuerta` se incorpora mediante la migración aditiva de API |
| `baya` | `core.ev_evaluacion_baya` + `core.ev_baya_observacion` | v0.1 usa `tipo='madurez'` y guarda estado/diámetro por muestra |
| `pesos` | `core.ev_evaluacion_baya` + `core.ev_baya_observacion` | v0.1 usa `tipo='peso'` y conserva peso/diámetro por muestra |
| `brotes` | `core.ev_brotes` | `piso` se recibe desde el formulario o `valores.m6_piso` |
| `ramas` | `core.ev_evaluacion_ramas` + `core.ev_rama_medicion` | La cabecera guarda conteos y el detalle una fila por rama medida |

Para nuevas capturas móviles, `core.ev_baya_medicion` se considera histórico de E05. El
modelo extensible de cabecera y observaciones es el destino preferido para `baya` y `pesos`.

## 5. Idempotencia y sincronización offline

`client_id` será la clave idempotente de la operación:

- Primer envío aceptado: la API crea el registro y devuelve `201`.
- Reenvío con el mismo `client_id` y el mismo contenido: devuelve el resultado existente,
  sin crear duplicado.
- Mismo `client_id` con contenido diferente: devuelve `409`.
- Timeout, `5xx` o `503`: Flutter conserva el estado `pendiente` y reintenta.
- `4xx` de validación, permisos o contrato: Flutter marca el registro como `error` y no lo
  reintenta automáticamente.

La migración `20_core/045_api_evaluaciones.sql` crea
`core.api_evaluacion_ingesta`, un ledger técnico común para los seis módulos. La inserción del
ledger y del recurso `core` ocurre en la misma transacción; no se confía únicamente en una
consulta previa no transaccional.

## 6. Payload propuesto

La forma HTTP propuesta es:

```json
{
  "client_id": "uuid-generado-en-flutter",
  "module_key": "baya",
  "fecha_evaluacion": "2026-08-31",
  "captured_at": "2026-08-31T15:30:00Z",
  "lote_id": 123,
  "cortina": 12,
  "hilera": 45,
  "planta": 123,
  "data": {
    "observaciones": [
      {
        "numero_muestra": 1,
        "estado_codigo": "E3",
        "diametro_mm": 12.5
      }
    ]
  }
}
```

En esta primera entrega `data/valores` mantiene compatibilidad con el mapa que ya produce
Flutter y `module_key` selecciona el normalizador correspondiente en `modules/evaluaciones`. La unión
discriminada con esquemas específicos por módulo queda como endurecimiento posterior del
contrato, una vez que se validen los formularios en campo.

El evaluador se resuelve contra `core.m_evaluador` mediante el DNI en la sesión interna; la API
no convierte el nombre enviado desde Flutter en un ID. La autenticación con `core.m_usuario`,
tokens y asignaciones administradas se agregará con el panel admin. La ubicación se valida
contra el `lote_id` seleccionado o se resuelve de forma inequívoca por sus tres códigos.

## 7. Respuesta mínima

```json
{
  "client_id": "uuid-generado-en-flutter",
  "evaluation_id": 456,
  "status": "accepted",
  "received_at": "2026-08-31T15:30:02Z"
}
```

Estados externos propuestos: `accepted`, `duplicate`, `rejected`. El estado local de Drift
(`local`, `pendiente`, `sincronizado`, `error`) continúa siendo responsabilidad de Flutter.

## 8. Endpoints necesarios

### Primera entrega

```http
GET  /v1/health/live
GET  /v1/health/ready
POST /v1/sesion/evaluador
GET  /v1/sesion/evaluadores
GET  /v1/catalogos/fundos
GET  /v1/catalogos/modulos?fundo_id={fundo_id}
GET  /v1/catalogos/lotes?modulo_id={modulo_id}
POST /v1/evaluaciones
GET  /v1/evaluaciones/{client_id}
```

### Segunda entrega

```http
POST /v1/sync/evaluaciones
GET  /v1/evaluaciones
```

`POST /v1/sesion/evaluador` es una resolución interna por DNI, no una autenticación definitiva:
no emite JWT ni reemplaza `core.m_usuario`. Se mantiene solo para que la app no use identidades
ficticias mientras el panel admin define las cuentas y credenciales reales.

## 9. Reglas de validación iniciales

- `module_key` pertenece al catálogo aprobado.
- `lote_id` existe y es elegible según el catálogo; no se utilizarán lotes
  `es_sentinel` o `es_ficticio` salvo que exista una regla funcional explícita.
- La ubicación seleccionada se valida contra el lote; los rangos agronómicos específicos de
  cortina/hilera/planta quedan pendientes porque todavía no existe ese catálogo en `core`.
- Cortina, hilera, planta y números de muestra están dentro de rangos válidos.
- Diámetros y pesos son positivos cuando están presentes.
- Estados de baya pertenecen al catálogo (`E1`–`E5`, `Desh`, `X`) mientras no se apruebe otro.
- Los campos obligatorios del módulo no pueden faltar.
- El sobre HTTP rechaza campos desconocidos; durante la transición el mapa interno
  `valores/data` conserva compatibilidad con Flutter y el normalizador solo promueve las claves
  conocidas por cada módulo.
- La suma de estadios se recalcula en backend; `total_origen` solo se conserva si el negocio
  necesita auditar el valor recibido.

## 10. Decisiones pendientes para cerrar v0.1

1. ¿La app debe persistir el catálogo remoto de lotes para poder cambiar de ubicación sin conexión?
2. ¿Cortina, hilera y planta serán siempre editables manualmente, o habrá rangos/catálogos
   específicos por lote?
3. ¿Qué proveedor o credencial se utilizará para reemplazar la resolución interna por DNI?
4. ¿`baya` representa una evaluación de `madurez` con diámetro, o deben generarse dos tipos
   lógicos?
5. ¿Cuál es el `piso` de `brotes` y cómo se selecciona en la app?
6. ¿Qué representa exactamente `item` en `estadios`?
7. ¿Cuántas muestras corresponden a `pesos` y cuál es su unidad definitiva?
8. ¿Se requiere sincronización por lotes en la primera versión o basta el envío individual?

## 11. Criterio de cierre de esta primera entrega interna

La implementación inicial queda técnicamente lista cuando la migración aditiva
`20_core/045_api_evaluaciones.sql` esté aplicada en `aquanqa_migracion`, la app pueda editar y
persistir su ubicación, y se valide una captura real controlada por cada módulo. Las decisiones
de autenticación, catálogos offline, rangos agronómicos y panel administrativo no bloquean esta
entrega; se deben cerrar antes de abrir la API fuera del entorno interno.
