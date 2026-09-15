# Informes de evaluaciones — 15 de septiembre de 2026

Desplegado en https://d28iujqq12ix9m.cloudfront.net/admin/informes.

## Cambios

- El origen inicial de las evaluaciones se elige por la última fecha disponible, en lugar del volumen de registros históricos. Un origen solicitado explícitamente se conserva.
- Informes semanales de flores y cuajos observados, separados por fundo y módulo agrícola, con filtros de periodo y origen, cobertura y acceso a registros.
- Exportación PowerPoint con un fundo por diapositiva, gráficos nativos editables y libro de datos incrustado. Las presentaciones originales no se modifican.
- El promedio utiliza evaluaciones con el indicador disponible. Ausencia y cero se mantienen separados; no se mezclan orígenes históricos y capturas de campo.

Los gráficos originales de “Nacimiento” son imágenes sin fórmula disponible. Estos informes muestran conteos observados por evaluación, no nacimientos calculados ni proyecciones.

## Despliegue y comprobación

- ECS `aquanqa-api:6`, imagen `r143027d1ca06972b`: 2 tareas activas, 0 pendientes, despliegue COMPLETED.
- Frontend publicado en AWS; compilación de producción correcta.
- Backend: 111 pruebas aprobadas; 23 pruebas de base de datos excluidas para evitar escrituras en producción.
- Frontend: 91 pruebas aprobadas en 19 archivos.
- Tabla de Estadios verificada en navegador: L046 y L043, fecha 2026-09-14, visibles sin seleccionar manualmente el origen.
- Promedios y coberturas contrastados con registros reales de cuatro combinaciones indicador/semana/módulo, incluidos datos incompletos.
- Ambos PowerPoint descargados desde la API: cinco diapositivas y cinco libros incrustados por archivo. Todas las diapositivas renderizadas e inspeccionadas.
- Navegador: filtros, datos históricos, registros y disposición móvil comprobados. El botón de exportación no mostró errores; el observador de descargas del navegador integrado agotó su espera, por lo que no se acredita recepción del archivo desde ese observador. La descarga HTTP y el contenido de ambos archivos sí se verificaron.

## Uso

Abrir Informes de evaluaciones, seleccionar indicador, periodo y origen, pulsar Consultar y después Exportar PowerPoint. Para reproducir las series históricas de las referencias, seleccionar Registro histórico. Capturas de campo consulta los registros móviles.

## Integración en Evaluaciones — corrección posterior

- Flores utiliza las series semanales por fundo y módulo como análisis principal, con selector flores/cuajos, ventana de evolución y acceso a los registros de cada semana. Mantiene los filtros de ámbito y el origen de la consulta.
- Presentación reemplaza la página independiente de informes: vista previa por diapositiva, navegación entre fundos, indicador, fechas, origen y selección de todos los fundos o uno para exportar. /admin/informes redirige a /admin/presentacion.
- Estadios conserva las capturas incompletas en registros y explica por qué no se pueden calcular porcentajes, en vez de mostrar un gráfico vacío. El histórico tiene acceso visible.
- Se registraron LegendComponent y LabelLayout en el componente ECharts compartido. Las series muestran módulos identificados y etiquetas finales separadas.
- Orígenes expresados como Capturas de campo / Registro histórico.
- Validación: 93 pruebas frontend, compilación de producción y seis pruebas del componente de gráficos tras habilitar LabelLayout. Revisión real en CloudFront a 1440 y 390 px; sin desbordamiento de página. Estadios histórico, estado incompleto, Flores y selección de fundo en presentación comprobados en navegador.
- Esta corrección no modifica la API, la base de datos ni los contratos de captura.
