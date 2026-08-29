# Motor de proyección, replay histórico y escenarios

**Fecha:** 2026-08-19
**Estado:** implementado y verificado en pruebas unitarias y una ejecución sobre PostgreSQL
**Ruta oficial de código:** `packages/analitica/proyeccion/engine.py`

## Qué problema resuelve

El torneo anterior demostraba que los modelos podían compararse, pero no ofrecía una forma
operativa de reconstruir una emisión histórica, elegir cuántas semanas proyectar ni modificar
de forma controlada las piezas del rendimiento. El motor separa ahora:

1. fecha de emisión que se quiere reconstruir;
2. horizonte o semanas concretas que se quieren mostrar;
3. modelo que genera el número;
4. escenario mecánico que se quiere explorar;
5. información usada y excluida.

## Qué modelo se ejecuta

### `Componentes_identidad`

Es el modelo nuevo por piezas. Ajusta dos objetivos independientes con información disponible
antes de la emisión:

```text
frutos por planta
peso medio de baya (g)
```

Después calcula:

```text
kg = plantas del catálogo × frutos por planta × peso medio de baya / 1000
```

El modelo de frutos usa, cuando tienen cobertura suficiente:

- horizonte y estacionalidad de la semana objetivo;
- plantas del catálogo y días desde poda;
- temperatura mínima/máxima, humedad, DPV derivado, radiación, ETo, lluvia y cuatro
  acumulaciones GDD candidatas (base 0, 4,4, 7 y 8 °C) en ventanas de 7 y 28 días;
- riego acumulado por módulo cuando el contrato tiene cobertura suficiente;
- flores, cuajado, tasa de cuajado y frutos muestreados;
- índice de estado y proporciones E1–E5;
- último fruto observado antes de la emisión y semanas desde la última cosecha.

El modelo de peso usa:

- horizonte y estacionalidad;
- plantas y días desde poda;
- las mismas señales climáticas acumuladas 7 y 28 días, con las bases GDD como candidatas;
- riego acumulado por módulo cuando el contrato tiene cobertura suficiente;
- diámetro de baya, dispersión y número de bayas muestreadas;
- índice de estado y proporciones E4–E5;
- último peso observado antes de la emisión y semanas desde la última cosecha.

Los componentes publicados por R09 (`frutos_por_planta` y `peso_baya_g`) no se usan como
entradas del nuevo modelo. Son justamente las piezas que se quiere sustituir. La lista exacta
se conserva en el JSON `componentes` de cada predicción.

### `R09_publicado`

Es la proyección publicada por el equipo. Sigue siendo el baseline y campeón operativo inicial.
No es una cosecha real. La cosecha real se obtiene de `stg.v_h01_cosecha` y se incorpora solo
para evaluar emisiones históricas ya cerradas.

### Macro legacy

`packages/analitica/proyeccion/macro_legacy.py` reproduce la lógica de la macro Excel con
parámetros nombrados:

- tres olas de distribución normal para repartir frutos por ventana de pasada;
- tres curvas exponenciales para el peso;
- promedio ponderado del peso por ola;
- identidad de plantas, frutos y peso para obtener kg.

No se promueve automáticamente. Es un baseline reproducible y una referencia de negocio para
comparar la migración. La lectura de parámetros usa nombres (`X1`, `O1`, `N1`, `A1`, `B1`, ...),
no posiciones `param(1)` ... `param(27)`.

## Replay histórico ciego

Una emisión histórica puede reconstruirse con:

```text
fecha de emisión = X
entrenamiento = objetivos con fecha objetivo estrictamente anterior a X
evaluación = cosecha posterior a X, separada del entrenamiento
```

El motor conserva `real_kg` para medir el error retrospectivo, pero la función que entrena los
componentes no recibe esas filas futuras. La prueba metamórfica existente también modifica los
datos posteriores al corte y comprueba que las predicciones anteriores no cambian.

Ejemplo de uso desde CLI:

```powershell
node scripts/run.mjs analytics project `
  --source postgres `
  --modelo-proyeccion Componentes_identidad `
  --fecha-emision 2026-07-20 `
  --horizonte-semanas 6 `
  --horizontes 1,2,6 `
  --no-persist
```

`--no-persist` permite probar sin cambiar la proyección vigente. Si la corrida se persiste,
las proyecciones de `Componentes_identidad` se marcan como `experimental` y quedan separadas
en `reporting.proyeccion_experimental`; no pueden reemplazar R09 accidentalmente.

La primera evaluación real se hizo con emisión `2026-05-18`, horizonte de 6 semanas y
`minimo_entrenamiento=100`. Produjo 1.380 filas, de las cuales 270 tenían cosecha posterior
observable. El WAPE fue 86,41 % y el MAE 990,11 kg por fila; todas las filas cerraron la
identidad de kg, pero 1.148 fueron anuladas por el gate de ocurrencia. Por tanto, estos valores
son un diagnóstico de desarrollo, no una precisión publicable ni una razón para sustituir R09.
En las mismas 270 filas R09 obtuvo WAPE 80,99 % y MAE 927,95 kg; el nuevo motor fue
aproximadamente 6,7 % peor en ambas métricas y subestimó el volumen por exceso de ceros.

## Escenarios

Los escenarios admitidos son mecánicos y explícitos:

- `--escenario-frutos-pct`: modifica frutos por planta;
- `--escenario-peso-pct`: modifica peso de baya;
- `--escenario-plantas-pct`: modifica la base de plantas;
- `--desplazamiento-semanas`: desplaza la fecha objetivo.

El resultado vuelve a cerrar la identidad y registra el escenario en `componentes`. No se
permite traducir automáticamente «subir riego», «subir ETo» o «subir temperatura» a un aumento
de kilos: las relaciones observacionales no son coeficientes causales. Para eso hace falta una
estimación local de respuesta o un experimento.

## Calendario de ocurrencia

El modo predeterminado de `Componentes_identidad` construye una rejilla histórica
lote-emisión-semana. Las semanas sin `real_kg` se convierten en ceros explícitos y se entrena
un clasificador de ocurrencia con las mismas variables as-of, horizonte y estado fenológico.
La salida conserva `probabilidad_cosecha` y `ocurrencia_gate` para auditar por qué una semana
queda activa o en cero.

El modelo de ocurrencia es predictivo, no causal. Todavía debe validarse su cobertura por
campaña, módulo y horizonte antes de usarlo como calendario oficial. El modo
`--calendario-proyeccion r09_publicado` queda disponible para comparar contra el calendario
del equipo.
