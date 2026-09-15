# Frontend en Cloudflare Pages

Producción: https://aquanqa.pages.dev/login

API: https://aquanqa.pages.dev/v1 · Swagger: https://aquanqa.pages.dev/docs

Cloudflare aloja una copia del frontend Angular. El Worker reenvía `/v1`, `/docs`, `/redoc` y `/openapi.json` al CloudFront existente en AWS. ECS y PostgreSQL RDS siguen en AWS. El enlace original https://d28iujqq12ix9m.cloudfront.net/login continúa disponible. No se modificaron los datos, usuarios ni la configuración de la aplicación móvil.

Los recursos estáticos evitan la ejecución del Worker mediante `_routes.json`. Las peticiones a la API no se almacenan en caché ni se reintentan automáticamente. Swagger utiliza el origen actual. La capa de proxy añade un salto de red; no supone una mejora garantizada de latencia. Pages Functions consume la cuota compartida de Workers del plan de Cloudflare (en Free, 100.000 solicitudes al día).

## Publicar cambios

Desde `frontend`, ejecutar `npm run build`. Desde la raíz:

```powershell
node --test infra/cloudflare/worker.test.mjs
python infra/cloudflare/package.py
npx --yes wrangler pages deploy data/salida/cloudflare-pages --project-name aquanqa --branch main --commit-dirty=true
python infra/aws/verify_panel_update.py --http
```

Requiere sesión de Wrangler en la cuenta propietaria. La publicación es manual (Direct Upload); subir cambios a GitHub no publica automáticamente. El empaquetado mantiene los archivos de Cloudflare fuera del directorio que se usa para publicar en AWS.

`infra/aws/verify_panel_update.py --http` utiliza AWS y el acceso de solo lectura configurado para pgAdmin; comprueba consultas, aislamiento por usuario, autenticación, evaluaciones, cargas, documentación, rechazo de acceso anónimo, informes semanales y exportaciones PowerPoint. Lee credenciales existentes en memoria sin registrarlas. `deployment.json` contiene resultados sin secretos.

Para volver al acceso anterior basta usar la URL de CloudFront. Para revertir una actualización de Pages, usar un despliegue anterior desde el panel de Cloudflare. No requiere restaurar ni trasladar PostgreSQL.
