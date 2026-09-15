# Actualización completa, 15 de septiembre de 2026

Publicado el panel actual en Cloudflare Pages y AWS, incluyendo análisis semanal de flores/cuajos, vista previa de presentaciones, exportación PowerPoint y selección del origen más reciente de las evaluaciones.

- Cloudflare: https://aquanqa.pages.dev/login; despliegue `01ba044f.aquanqa.pages.dev`.
- AWS frontend: https://d28iujqq12ix9m.cloudfront.net/login; HTML idéntico al build local y al de Cloudflare.
- API: `aquanqa-api:7`, imagen `re093cef375d18dfd`; despliegue COMPLETED con dos tareas saludables.
- Build: `aquanqa-production:ba5e84ef-93a4-4985-bfc3-88b8aadb2b30`, SUCCEEDED.
- Versión anterior para reversión de código: `aquanqa-api:6`.
- Base activa: `aquanqa_live`, sin migraciones ni escrituras de evaluaciones durante esta actualización.

Validación: 93 pruebas frontend, 111 backend y cuatro del proxy aprobadas. Se excluyeron las 23 pruebas `db` que requieren una base de pruebas. Consultas reales de solo lectura verificaron conteos, filtros y aislamiento por usuario. Autenticación, rechazo anónimo, informes de ambos indicadores y descarga de PowerPoint con gráficos incrustados comprobados por HTTP en AWS, Cloudflare y Render. Las seis familias pasaron las comprobaciones de snapshot y tendencia desde Cloudflare. La pantalla de acceso se abrió correctamente en navegador; la validación autenticada de esta actualización se realizó por HTTP.

Cloudflare mantiene publicación manual mediante Wrangler. Subir cambios a GitHub por sí solo no actualiza Pages; el comando está documentado en `infra/cloudflare/README.md`.
