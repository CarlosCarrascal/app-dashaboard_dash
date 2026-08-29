# Parámetros automáticos y Proyección operativa — 23/08/2026

## Estado implementado

La página **Proyección** usa como salida principal `ModeloOperativoActual_v1`, réplica
Python del proceso `ProySemanal`. R09 permanece únicamente como emisión publicada de
referencia y no se usa como predictor ni se presenta como algoritmo.

La corrida operativa S34 quedó persistida en PostgreSQL con:

- emisión: `17/08/2026`;
- versión: `v1-auto`;
- 817 lotes;
- 4.902 filas lote–paña;
- 6.695.789 kg proyectados en todas las semanas disponibles;
- snapshot: `9ffd48efbd1f6c0a97bfcd03f9163ee0d37b771848538ee3cddba0d18e87f790`;
- `forecast_run_id`: `60`.

El dashboard solo consulta la corrida persistida. No abre Excel ni ejecuta la
optimización durante un callback.

## Cómo se calculan ahora los parámetros

Los parámetros `X/O/N` de las tres oleadas y `A/B` del peso se calibran automáticamente
con datos de PostgreSQL disponibles hasta la fecha de corte. El ajuste se realiza en
frutos por planta, no en frutos totales.

La precedencia es:

1. cosecha actual del lote más histórico del mismo lote;
2. cosecha actual cuando no existe histórico;
3. histórico del lote cuando todavía no existe cosecha actual;
4. prior del fundo cuando el lote no tiene observaciones suficientes.

Para la corrida S34 se obtuvieron:

- 596 lotes con campaña actual más histórico;
- 96 lotes con campaña actual;
- 89 lotes con histórico;
- 79 lotes con prior de fundo.

PostgreSQL aporta identidad física, área, plantas, poda, cosecha y peso. Nueve lotes sin
fecha de poda en PostgreSQL conservaron temporalmente la fecha del Panel Excel; esta
excepción está registrada como `FuentePoda=excel_fallback` y no ocurre silenciosamente.

El calendario de pañas continúa proviniendo del `Panel` semanal porque todavía no existe
un contrato PostgreSQL equivalente y validado. R09 no se usa para reconstruir ese
calendario, ya que introduciría circularidad.

## Cambios en la interfaz

- La primera vista abre en seis semanas y empieza en la primera semana futura cerrable.
- La curva principal conserva real, real parcial y proyección Python; R09 es una capa
  opcional de referencia y nunca un selector de modelo.
- Los filtros de fundo, módulo y lote admiten selección múltiple y reutilizan en memoria
  el snapshot operativo; un cambio caliente no vuelve a consultar ni recalcular el
  modelo.
- La contribución de Arena, Ayllu, Kawsay y Quri se representa con cuatro perfiles
  semanales compactos, sincronizados y con la misma escala. Así se comparan la forma y
  el volumen sin superponer fundos ni convertir la vista en una tabla coloreada.
- La cobertura indica que los parámetros proceden de PostgreSQL. Los nombres de libros
  y hashes se retiraron de la operación diaria y permanecen solo en la exportación y la
  trazabilidad técnica.
- El detalle por lote se carga únicamente al abrir su pestaña y conserva nivel de
  calibración, fuente de parámetros y fuente de poda.
- La vista `Histórico y desviación` compara cosecha real y una serie predictiva sobre el
  mismo universo, agrupada por semana, mes o campaña. Cuando existen varios períodos,
  muestra la evolución real/proyectada y debajo las desviaciones firmadas. Cuando solo
  existe un período —o se resume por campaña— usa una comparación directa tipo
  *dumbbell*; no dibuja dos barras gigantes sin dimensión temporal.
- El replay histórico también se carga bajo demanda y abre con
  `Modelo Python actual · replay histórico` (`MacroLegacy_v1`), la reconstrucción as-of de la
  misma fórmula legacy. Esto no convierte automáticamente la emisión operativa vigente
  en una predicción ya evaluada: esa emisión se puntúa cuando cierre su semana objetivo.
- El pie lateral de Proyección identifica `PostgreSQL · 4 fundos`; no muestra
  `IA.final.xlsx`, porque ese libro no alimenta esta pantalla.
- El modo de depuración de Dash queda desactivado por defecto para no tapar la página.

## Rendimiento y gobierno de callbacks

La página usa un servicio de lectura específico para Proyección. La carga operativa no
arrastra todo el estado de Relaciones, Descubrimientos o Backtesting. Los datos se
mantienen un minuto en memoria y los resultados voluminosos se materializan al abrir su
pestaña:

- operación: corrida Python, cosecha real, R09 opcional y maestro de lotes;
- detalle: serialización diferida de lote–paña;
- histórico: replay diferido;
- Matriz SIX: consulta diferida.

Cada salida visual tiene un único callback propietario. El registro del dashboard pasa
la prueba que detecta IDs y outputs duplicados.

## Alcance científico y operativo

La automatización demuestra que el motor puede ejecutarse sin copiar manualmente los
parámetros del Excel. No demuestra todavía que esta recalibración automática sea más
precisa que el proceso publicado. Esa conclusión requiere replay ciego por emisión y
comparación contra kg reales posteriores sobre el mismo universo.

## Replay corregido del 24/08/2026

La corrida `analytics.forecast_run.run_id = 62` reconstruyó y persistió 14 emisiones
semanales de `MacroLegacy_v1`. La evaluación utiliza 13 semanas realmente cerradas,
del 18/05 al 16/08/2026, y 10.621 filas lote-semana (`817 × 13`). La semana iniciada el
17/08 se excluye porque la cosecha disponible es parcial.

Se corrigió el defecto de escala del replay anterior: el calibrador ya no interpreta la
carga observada hasta el corte como si fuese la carga total de campaña. Ahora combina
la observación as-of con el histórico cerrado del mismo lote y ajusta automáticamente
las oleadas sin utilizar cosecha posterior a la emisión.

Resultado corregido:

- real: 3.319.126 kg;
- Python: 3.092.013 kg;
- desviación acumulada: -227.112 kg;
- sesgo: -6,8 %;
- WAPE agregado por semana: 23,1 %;
- WAPE agregado por mes: 16,0 %;
- WAPE lote-semana: 107,0 %.

El WAPE cambia con el grano porque los excesos y faltantes de distintos lotes se
compensan al sumar por semana o mes. Por eso el tablero identifica explícitamente el
nivel de la métrica y conserva el WAPE lote-semana como control de asignación.

En el mismo universo fijo de 817 lotes y 13 semanas, tratando como cero una combinación
no publicada por R09, la referencia publicada obtiene WAPE semanal de 22,0 %, WAPE
lote-semana de 46,7 % y sesgo de +4,2 %. Python recupera razonablemente el volumen total,
pero aún no supera a R09 en planificación por lote.

La vista semanal abre con 12 semanas y permite ampliar a 26 o a todo el histórico. Mes
muestra `4 meses · 13 semanas cerradas`; ya no usa la etiqueta ambigua `4 períodos`.

## Ajuste operativo de semana en curso y exportación

La curva principal separa tres conceptos que antes se confundían:

- el real cerrado se ubica en el domingo de cierre;
- el avance de la semana en curso se muestra como punto parcial ámbar;
- el modelo Python puede mostrar, en ese mismo cierre, su estimación de semana completa;
- la línea de futuro comienza recién en la semana siguiente.

No se dibuja una línea artificial entre el último real y la primera proyección. Los
tooltips presentan el rango completo, kilos con formato local y el estado del dato. R09
permanece opcional y termina en la última semana que realmente publicó; no se rellena ni
se extrapola para aparentar cobertura.

Los controles se reorganizaron en tres filtros multiselección y una fila compacta de
vista: `6 semanas`, `Campaña completa`, `Comparar R09` y `Limpiar filtros`.

La descarga Excel ahora contiene portada específica, resumen por fundo, plan semanal y
detalle lote–paña. Los nombres de archivos y hashes quedaron en una hoja técnica oculta,
disponible para auditoría, pero fuera del flujo diario. El plan visible identifica la
fuente como base de datos y traduce los estados internos de calibración a etiquetas
operativas.
