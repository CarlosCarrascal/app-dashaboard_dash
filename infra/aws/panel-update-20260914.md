# Actualización del panel, 14 de septiembre de 2026

Publicado el dashboard de actividad semanal por fundo, los filtros y mejoras de navegación del panel. La API incorpora `/v1/admin/evaluaciones/conteos`, con consultas de agregación y restricciones por usuario. Se regeneró el contrato OpenAPI. Las imágenes base se obtienen del espejo oficial de Docker en Amazon ECR para evitar el límite de descargas anónimas de Docker Hub.

- API: `aquanqa-api:4`, imagen `rf35db28e11ace42c`, dos tareas saludables y despliegue COMPLETED.
- Versión anterior para reversión de código: `aquanqa-api:3`.
- Cloudflare Pages: `4240e26b.aquanqa.pages.dev`, producción `aquanqa.pages.dev`.
- AWS frontend: `d28iujqq12ix9m.cloudfront.net`, S3 actualizado e invalidación solicitada.
- Base activa: `aquanqa_live`; no se hicieron migraciones ni escrituras de evaluaciones.

Validación: 89 pruebas frontend, 104 pruebas backend sin base de datos y cuatro pruebas del proxy aprobadas. Consulta real en RDS contrastada con el total de evaluaciones vigentes, filtros vacíos y aislamiento por usuario. Comprobadas las rutas autenticadas, rechazo anónimo y OpenAPI en AWS, Cloudflare y Render. Snapshots y tendencias de las seis familias verificados por HTTP. Dashboard y análisis de estadios abiertos correctamente en navegador con sesión existente.

Las 23 pruebas marcadas `db` no se ejecutaron como suite contra producción porque incluyen escrituras. La validación contra producción fue de solo lectura.
