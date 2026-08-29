# Guía de continuidad para IA y vibecoding

**Versión:** 1.1
**Fecha de referencia:** 2026-08-20
**Repositorio:** `aquanqa-data-platform`
**Propósito:** permitir que otra IA, otro chat o una nueva sesión continúe el trabajo sin
  perder el objetivo, inventar funcionalidades ni confundir planes con implementación real.

Este documento es una guía de trabajo, no una descripción de que todo lo indicado ya exista.
Una IA debe distinguir siempre entre lo implementado, lo verificado, lo propuesto y lo que está
bloqueado por falta de datos o infraestructura.

> **Copia versionada** de `.md/guia-continuidad-ia-vibecoding.md`.
> La carpeta `.md/` está ignorada por Git
> (`.gitignore:54`), así que este archivo es el que sobrevive a un clon limpio y
> manda si ambos divergen. Replica aquí todo cambio de fondo.

## 1. Objetivo que no se puede perder

La plataforma no busca únicamente gráficos, correlaciones ni rankings de importancia. El
objetivo es construir una capa analítica y predictiva que permita:

1. entender las relaciones entre variables fenológicas, climáticas, de riego, nutrición y
   producción;
2. separar asociaciones descriptivas, correlaciones, relaciones temporales, predicción y
   causalidad;
3. predecir independientemente los componentes principales del rendimiento:
   `frutos por planta` y `peso medio de baya`;
4. proyectar el rendimiento con una identidad agronómica auditable:

   ```text
   kg = plantas productivas × frutos por planta × peso medio de baya / 1000
   ```

5. proyectar `kg por lote-semana` en horizontes de 1–2, 3–6 y 7–10 semanas;
6. comparar alternativas mediante backtesting temporal, incertidumbre y criterios de promoción;
7. explicar por qué se tomó cada decisión y permitir navegar desde una conclusión hasta sus
   datos, código, evidencia, modelo, supuestos y ejecución.

Si un cambio mejora una métrica pero no contribuye a este objetivo, debe clasificarse como
soporte técnico, diagnóstico o legacy; no debe presentarse como avance predictivo principal.

## 2. Orden obligatorio antes de tocar el código

Antes de crear, modificar, eliminar o mover archivos, la IA debe hacer una inspección mínima
del repositorio. No debe comenzar escribiendo código a partir de una suposición.

### Paso A: leer el contexto de continuidad

Leer en este orden:

1. este archivo: `docs/seguimiento/03_guia_continuidad_ia_vibecoding.md`;
2. `docs/seguimiento/02_estado_plataforma_analitica.md`;
3. el contexto específico del área que se va a cambiar, por ejemplo
   `docs/seguimiento/04_auditoria_impacto_agronomico.md`;
4. para Proyecciones, `docs/seguimiento/05_modelo_fenologico_y_mesa_cosecha_2026-08-20.md`
   y `docs/modelo/08_fuentes_predictivas.json`.
5. la documentación técnica enlazada desde esos archivos;
6. el `README` y las instrucciones del paquete o aplicación que se va a modificar;
7. el catálogo científico `docs/cientifico/catalogo_evidencia.json` si el cambio contiene una
   afirmación agronómica, estadística o causal.

Los documentos de `docs/seguimiento/` son contexto de continuidad. No sustituyen la inspección
del código, las migraciones, los contratos, los datos ni las pruebas.

### Paso B: ubicar el código y sus dependencias

Usar búsqueda del repositorio antes de editar:

```text
listar archivos:       rg --files
buscar rutas/símbolos: rg "nombre_del_modulo|nombre_de_la_funcion|tabla|endpoint"
buscar tests:          rg --files | rg "test|spec|fixture|snapshot"
buscar migraciones:    rg --files db docs | rg "migration|schema|analytics|mlflow"
```

En PowerShell, se pueden usar los equivalentes nativos si `rg` no está disponible. Registrar en
la respuesta qué archivos se revisaron y por qué eran necesarios.

### Paso C: construir un inventario antes del cambio

La IA debe identificar:

- archivo o página que contiene la lógica principal;
- funciones importadas y consumidores de esa lógica;
- contrato de entrada y salida;
- tablas, vistas, migraciones o archivos fuente involucrados;
- pruebas existentes;
- documentación que quedaría desactualizada;
- si el flujo usa PostgreSQL, Excel, MLflow u otro fallback;
- si la ejecución es oficial, diagnóstica o legacy.

Si no se puede comprobar una de estas piezas, se debe declarar como “no verificado” y no
rellenarla con una invención.

### Paso D: presentar una mini-evaluación antes de implementar

Antes del cambio, producir internamente o comunicar brevemente:

```text
Objetivo del cambio:
Archivos que deben leerse:
Archivos que probablemente cambiarán:
Contrato que no debe romperse:
Pruebas que deben ejecutarse:
Riesgos de fuga, causalidad o regresión:
Supuestos explícitos:
```

No es necesario pedir permiso para una modificación claramente solicitada y localizada, pero sí
detenerse si el cambio puede cambiar el campeón oficial, borrar datos, modificar una identidad
de rendimiento o alterar un contrato sin que exista una decisión explícita.

## 3. Estado que la IA debe distinguir

Cada afirmación sobre el proyecto debe usar una de estas categorías:

| Estado | Significado | Cómo se demuestra |
|---|---|---|
| `implementado` | Existe código para el comportamiento | archivo, símbolo y prueba o ejecución |
| `verificado` | Se ejecutó y produjo el resultado declarado | comando, fecha, salida o artefacto |
| `documentado` | Está descrito, pero no necesariamente ejecutado | documento y sección |
| `propuesto` | Es una decisión o diseño futuro | plan, ADR o issue |
| `observado` | Se vio en datos o en una ejecución exploratoria | snapshot, consulta y método |
| `inferido` | Interpretación razonable, no comprobación directa | premisas y limitaciones |
| `bloqueado` | No puede concluirse sin datos, permisos o infraestructura | bloqueo concreto |
| `legacy` | Existe, pero está fuera del flujo oficial | ruta y motivo de exclusión |

Nunca transformar `propuesto` en `implementado` por el solo hecho de que exista una página,
un botón, una función con nombre parecido o un plan escrito.

## 4. Reglas científicas y de modelado

### 4.1 Modelos y campeón

- R09 es el campeón operativo inicial mientras ningún challenger cumpla los criterios de
  promoción fuera de muestra.
- Random Forest puede ser challenger explicable; XGBoost se conserva como challenger y modelo
  de relaciones, no como campeón automático.
- Un `R²` alto en una semana dejada fuera, una simulación de eventos ya ocurridos o una métrica
  calculada dentro de la misma campaña no demuestra capacidad de proyección futura.
- No promover un modelo por una sola métrica. Revisar MASE, WAPE, MAE, sesgo, cobertura,
  interval score, desempeño por horizonte, fundo, campaña y volumen cubierto.
- Si el challenger no supera los umbrales establecidos, comunicar literalmente:
  **“sin mejora estadísticamente comprobada”**.

### 4.2 Variables y componentes

El análisis debe mantener separados, cuando los datos lo permitan:

- plantas productivas;
- estructuras productivas;
- flores y cuajado;
- frutos por planta;
- estados fenológicos E1–E5;
- peso medio de baya;
- kg por lote-semana.

No reemplazar esta descomposición por un único objetivo de kg si el cambio se presenta como
explicación agronómica. Si faltan plantas productivas, polinización, suelo, nutrición o
pronóstico meteorológico futuro, declararlo como limitación y no rellenarlo artificialmente.

### 4.3 Correlación, predicción y causalidad

- Pearson y Spearman describen asociación.
- Un rezago o precedencia temporal describe orden temporal; no prueba causa.
- SHAP, ALE, importancia de variables y permutación explican el comportamiento de un modelo;
  no miden el efecto de intervenir una variable.
- Un modelo predictivo puede usar una variable útil aunque no sea causal.
- Una conclusión causal necesita, como mínimo, una pregunta de intervención, DAG definido
  antes del análisis, confundidores, soporte/positividad, controles negativos y un diseño
  experimental o cuasi-experimental defendible.
- No copiar coeficientes de otra variedad, localidad, edad, sistema de riego o campaña.
  La literatura formula hipótesis y estructuras; la magnitud debe calibrarse localmente.

### 4.4 Tiempo y fuga de información

Toda observación de proyección debe respetar semántica `as-of`: solo puede usar información
disponible en la fecha de emisión.

Antes de aceptar un feature, preguntar:

1. ¿Se conocía en la fecha de corte?
2. ¿Se calculó usando datos futuros de la misma campaña?
3. ¿Usa el resultado observado o publicado que intenta predecir?
4. ¿El promedio o agregado incluye semanas posteriores?
5. ¿El forecast meteorológico es realmente futuro o es clima observado?

La evaluación debe ser rolling-origin temporal. No usar K-fold aleatorio para seleccionar o
publicar resultados de series temporales.

## 5. Protocolo anti-alucinación

La IA debe seguir estas reglas:

- No inventar nombres de tablas, columnas, rutas, comandos, `run_id`, métricas, resultados ni
  servicios.
- No afirmar que se ejecutó una prueba si no se ejecutó.
- No afirmar que se consultó PostgreSQL, MLflow o la web si no existe evidencia de la consulta.
- No asumir que un archivo existe porque está enlazado desde un documento.
- No inventar datos faltantes ni “rellenar” variables agronómicas con medias para simular una
  capacidad que el sistema aún no tiene.
- No presentar un ejemplo sintético como resultado real. Etiquetar siempre `ejemplo`,
  `simulado` o `observado`.
- No usar un valor de la interfaz como evidencia si no se conoce su consulta, filtro, fecha,
  snapshot y denominador.
- No esconder un fallback de Excel, una ausencia de MLflow o una falta de campaña externa.
- No cambiar silenciosamente el objetivo, el grano, la unidad, la ponderación o el campeón.
- No eliminar una pantalla o módulo antiguo sin confirmar que el usuario quiere borrarlo;
  conservarlo como `legacy` si todavía aporta contexto o comparación.

Cuando falte información, usar una de estas respuestas:

```text
No verificado: necesito revisar <archivo/tabla/comando>.
Hipótesis de trabajo: <supuesto>, porque <motivo>.
Bloqueado: no se puede demostrar <resultado> sin <dato/infraestructura>.
Propuesta: sugiero <cambio>, pero todavía no está implementado.
```

## 6. Flujo de implementación seguro

1. **Definir el resultado aceptable.** Precisar qué debe cambiar y qué no debe cambiar.
2. **Leer lo necesario.** Revisar archivos fuente, contratos, configuración, migraciones y
   pruebas relacionadas.
3. **Inspeccionar el estado actual.** Ejecutar una consulta, test o comando de diagnóstico antes
   de modificar, cuando sea posible.
4. **Elegir el cambio mínimo.** Evitar reescrituras amplias y no tocar módulos no relacionados.
5. **Implementar con trazabilidad.** Mantener nombres, unidades, versiones y origen de datos.
6. **Probar.** Ejecutar pruebas unitarias, contratos, migraciones, fugas temporales, fórmulas,
   layouts o backtesting según el riesgo.
7. **Revisar el resultado.** Comprobar que no se rompió navegación, jerarquía, fallback,
   reconciliación ni documentación.
8. **Actualizar contexto.** Si cambió una decisión, limitación, métrica, fuente o estado,
   actualizar el `.md` correspondiente y el catálogo científico si aplica.
9. **Entregar un handoff.** Informar archivos modificados, pruebas ejecutadas, resultados,
   supuestos, bloqueos y siguiente paso seguro.

Para cambios de datos o infraestructura, no usar comandos destructivos sin confirmar los
objetivos exactos. Evitar resets, borrados masivos y sobrescrituras de snapshots históricos.

## 7. Qué archivos revisar según la tarea

| Tipo de tarea | Lectura mínima adicional |
|---|---|
| Relaciones/impacto agronómico | contexto de impacto, `docs/cientifico/catalogo_evidencia.json`, núcleo de clima, consultas y tests de relaciones |
| Modelo predictivo | contexto de plataforma, pipeline de features, entrenamiento, backtesting, model card, tests temporales |
| Proyección | contrato lote-semana, servicio de proyección, jerarquía, intervalos, snapshots y tests de reconciliación |
| Base de datos | migraciones, esquema `stg`, esquema `analytics`, checks SQL y fixtures |
| Dashboard | página, componentes compartidos, servicio/API, estados vacío/error/loading y tests de layout |
| MLflow | configuración de tracking, firma, registry, exportación, estado de servidor y variables de entorno |
| Catálogo/evidencia | documento que hace la afirmación, DOI/URL primario, limitaciones y transferibilidad |
| Despliegue | configuración de runtime, variables de entorno, logs y documentación de despliegue |

La tabla no reemplaza la búsqueda. Es una guía para decidir qué leer primero.

## 8. Regla de continuidad entre chats o IAs

Una nueva sesión debe empezar con el siguiente bloque de contexto:

```text
Repositorio: aquanqa-data-platform
Objetivo no negociable: predecir frutos/planta y peso de baya para proyectar rendimiento.
Campeón operativo inicial: R09, salvo promoción demostrada por backtesting temporal.
Estado de la tarea anterior: <implementado/verificado/propuesto/bloqueado/legacy>.
Documentos de continuidad leídos: <lista>.
Archivos inspeccionados: <lista>.
Archivos modificados: <lista>.
Pruebas ejecutadas y resultado: <lista>.
Bloqueos o datos faltantes: <lista>.
Siguiente cambio solicitado: <descripción exacta>.
```

Si existen varios documentos de sesión, tomar como fuente principal el más reciente que
contenga fecha, estado verificable y archivos afectados. No asumir que una sesión antigua
describe el estado actual: comprobar `git status`, fechas de modificación y código vigente.

## 9. Formato obligatorio de entrega de una IA

Toda entrega de implementación debe terminar con:

```text
Resultado:
- qué quedó funcionando;
- qué no se modificó;

Archivos revisados:
- ruta y motivo;

Archivos modificados:
- ruta y cambio;

Verificación:
- comandos ejecutados;
- resultado real;

Interpretación:
- qué significa el resultado;
- qué no permite concluir;

Supuestos y limitaciones:
- datos, fechas, agregaciones, causalidad e infraestructura;

Pendientes:
- siguiente paso recomendado;
- bloqueos concretos.
```

Una respuesta breve es válida; una respuesta sin estado verificable, archivos, pruebas o
limitaciones no es suficiente para una tarea analítica.

## 10. Criterio final de calidad

Antes de considerar terminado un cambio, la IA debe poder responder afirmativamente:

- ¿El cambio sigue el objetivo de frutos por planta, peso y rendimiento?
- ¿Se inspeccionaron los archivos que realmente gobiernan el comportamiento?
- ¿Se respetó el contrato de datos y la semántica `as-of`?
- ¿Se evitó fuga temporal y selección post hoc?
- ¿Se distinguió asociación, predicción y causalidad?
- ¿El resultado fue probado o quedó claramente marcado como propuesta?
- ¿Se conservaron las limitaciones y el estado legacy?
- ¿Otra IA podría continuar leyendo este documento y los archivos enlazados?

La regla central es sencilla:

> **Primero comprobar el repositorio y los datos; después cambiar el código; finalmente
> documentar qué se comprobó. Nunca completar los vacíos con imaginación.**
