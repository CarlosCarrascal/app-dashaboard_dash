# Validación del modelo operativo actual

## Estado

Hay dos estados que no deben confundirse:

1. La comparación estricta contra la hoja `BDProy` queda bloqueada como
   `fuente_inconsistente`, porque esa hoja conserva salidas de otra corrida o menos
   pasadas. No se declara paridad fila a fila con esa salida antigua.
2. La ejecución operativa `Panel + Parametros → motor Python` sí está disponible como
   `ModeloOperativoActual_v1` experimental. La corrida `run_id=57` fue persistida en
   PostgreSQL con 4.902 predicciones y 817 lotes; el dashboard la expone al elegir
   `Modelo operativo actual · macro agronómica` en la fuente challenger.

R09 continúa siendo el plan oficial. La corrida operativa no se promueve hasta completar
la comparación histórica y calibrar sus intervalos.

Comando reproducible:

```powershell
$env:PYTHONPATH = "packages"
python -m analitica.cli validate-operational
```

## Cambio del motor

El motor ya no limita la ejecución a cinco pasadas. Lee todas las columnas contiguas
`FePas1...FePasN` de cada fila del `Panel` y rechaza calendarios vacíos, repetidos,
desordenados o con índices intermedios faltantes.

`pasadas_esperadas`, si se proporciona, solo valida una expectativa externa; nunca recorta
el calendario.

## Resultado de los libros disponibles

| Libro | Filas `BDProy` | Filas calculadas | Estado |
|---|---:|---:|---|
| Arena | 425 | 510 | fuente_inconsistente |
| Ayllu | 1.278 | 1.278 | fuente_inconsistente |
| Kawsay Allpa | 1.645 | 1.974 | fuente_inconsistente |
| Quri | 950 | 1.140 | fuente_inconsistente |

Los cuatro `Panel` contienen `FePas1` a `FePas6`, mientras que `BDProy` conserva salidas
con menos pasadas o con otra corrida. En Ayllu, además, `BDProy` contiene campaña `C2025`
y fechas que no corresponden al `Panel` inspeccionado.

La herramienta registra SHA-256, filas de cada hoja, columnas `FePas`, claves faltantes y
claves sobrantes. Esto evita confundir una comparación de totales con paridad fila a fila.

## Persistencia y dashboard

Se añadió `analytics.operational_model_validation` y su vista
`reporting.validacion_modelo_operativo`. La persistencia del reporte es opcional mediante:

```powershell
python -m analitica.cli validate-operational --persist
```

La vista `reporting.proyeccion_vigente` sigue bloqueando una corrida de
`ModeloOperativoActual_v1` como plan oficial si su configuración no contiene
`validacion_operativa.estado = validado`. La vista
`reporting.proyeccion_experimental` sí expone la corrida `run_id=57`, separada de R09.
El dashboard muestra una advertencia explícita: está disponible para uso experimental,
pero no sustituye al plan oficial.

Comando reproducible de la emisión operativa:

```powershell
python -m analitica.cli operational-project `
  --root C:\Users\CCARRASCAL\Downloads\Proyecciones\ProyeccionSemanal_33 `
  --campania C2026 `
  --fecha-emision 2026-08-10 `
  --version-fuente ProySemanal_33
```

## Pendiente para declarar el modelo listo

Para declararlo listo para promoción se necesita una salida `BDProy` recalculada con el mismo
`Panel` y `Parametros` de cada libro, o una extracción equivalente desde Access/PostgreSQL.
Después se volverá a ejecutar la comparación fila a fila de fechas, pasadas, frutos, peso,
kg, kg/ha y frutos totales, seguida del replay histórico contra R09 y la calibración de
P10/P90. Mientras tanto, el uso correcto es: R09 para decisión oficial y
`ModeloOperativoActual_v1` para revisar la réplica del modelo Excel y comparar escenarios.
