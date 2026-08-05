# Runbook · carga inicial

Lleva la plataforma de cero a un modelo cargado y validado. Unos 20 minutos, casi todos de
extracción.

## Antes de empezar

| Requisito | Cómo comprobarlo |
|---|---|
| PostgreSQL accesible | `Get-Service postgresql*` debe estar `Running` |
| Contraseña en `.env` | `PGPASSWORD` con valor |
| `BD_AQUANQA_26.accdb` accesible | la ruta de `ACCESS_DB_PATH` existe |
| Driver de Access de 64 bits | `Get-OdbcDriver \| ? Name -like '*Access*'` incluye una entrada `[64-bit]` |
| Maestro de lotes | `data/entrada/M_Lotes.xlsx` |

El tareo de personal (`data/entrada/Query Tareo 2026.xlsx`) es opcional: sin él todo carga
salvo el dominio de personal.

## Pasos

```powershell
cd C:\Users\CCARRASCAL\Proyectos\aquanqa-data-platform

npm run setup      # entorno, base, esquemas, roles, decisiones parametrizadas
npm run extract    # .accdb + xlsx → data/salida/*.csv   (~10 min, solo lectura)
npm run load       # CSV → raw
npm run build      # stg → qua → dim → fact → reporting
npm run validate   # contrato de aceptación
```

`npm run setup` es idempotente: si la base ya existe, no la recrea.

## Qué debe salir

Al terminar `load`, `raw` tiene **683.180 filas** repartidas exactamente como
`docs/historico-access/evidencia/04_metricas_validacion.txt` §1. Cualquier desvío significa que la
extracción se truncó: repetirla, no continuar.

Al terminar `validate`, todas las filas del informe en `✓`. Las que deben **cambiar** respecto a
Access están marcadas como tales: son las correcciones, no errores.

## Si algo falla

| Síntoma | Causa y salida |
|---|---|
| `No encuentro psql` | PostgreSQL no está en el PATH. Poner `PSQL_EXE` en `.env` con la ruta completa |
| `Falta PGPASSWORD` | copiar `.env.example` a `.env` y completarlo |
| `[Microsoft][ODBC Driver Manager] Data source name not found` | falta el driver de Access de 64 bits — instalar *Microsoft Access Database Engine 2016 Redistributable* |
| `No se puede abrir la base de datos` al extraer | otro proceso tiene el `.accdb` con bloqueo exclusivo: cerrar Access y borrar el `.laccdb` **solo si nadie lo está usando** |
| La cuarentena supera sus umbrales | la carga se detiene a propósito. Revisar `qua.rechazos` antes de forzar nada: ver el runbook de cuarentena |
| Un `.sql` falla a mitad | `ON_ERROR_STOP` corta ahí. Los scripts son re-ejecutables: corregir y volver a lanzar la misma carpeta |

## Lo que este proceso nunca hace

- **No escribe en el `.accdb`.** Se abre en solo lectura. Access puede seguir en uso durante la
  migración.
- **No descarta filas en silencio.** Todo lo rechazado queda en `qua.rechazos` con su fila
  íntegra en `jsonb` y su motivo.
- **No adivina identidades.** Una fila cuyo lote no se puede resolver sin ambigüedad va a
  cuarentena, no al lote más parecido (ADR-0003).
