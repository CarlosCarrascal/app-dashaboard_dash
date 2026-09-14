# Aquanqa en AWS

Despliegue en la cuenta `021686096399`, región `us-east-1`.

## Producción verificada — 2026-09-14

- Frontend: <https://d28iujqq12ix9m.cloudfront.net>
- API: <https://d28iujqq12ix9m.cloudfront.net/v1>
- Swagger: <https://d28iujqq12ix9m.cloudfront.net/docs>
- Compatibilidad móvil: <https://aquanqa-campo-api.onrender.com/v1>
- Base activa: `aquanqa_live` en RDS `aquanqa-production`.
- Copia de ensayo: `aquanqa`, separada de producción. Sus seis capturas de prueba
  nunca se copiaron a la base activa.
- Neon queda conservado en solo lectura; no es la base de la API activa.
- Snapshot RDS disponible: `aquanqa-post-migration-20260914`.

Se compararon las 110 tablas mediante conteos y hashes de contenido, incluidas
90 666 evaluaciones. Pasaron 102 pruebas de API, dos pruebas del proxy y el ciclo
HTTP de los seis módulos móviles contra el ensayo. En producción se verificaron
salud, autenticación, catálogos, evaluaciones, cargas, las seis familias analíticas
y rechazo de acceso administrativo sin token. La URL anterior pasó las mismas
comprobaciones básicas y confirmó el encabezado `X-Aquanqa-Backend: aws`.
Identificadores y resultados detallados: `deployment.json`.

## Arquitectura

CloudFront sirve Angular desde un bucket privado S3. Las rutas `/v1/*`, `/docs*`,
`/openapi.json` y `/redoc*` llegan a un ALB interno mediante un origen VPC.
Dos tareas ECS Fargate ejecutan la API. PostgreSQL RDS no tiene dirección pública;
solo el grupo de seguridad de las tareas puede conectar al puerto 5432.

La URL anterior de Render se conserva mediante `render-proxy`, que reenvía las
solicitudes a AWS conservando métodos, cuerpos, autenticación y códigos HTTP.
El proxy no reintenta escrituras automáticamente. La API mantiene `/v1` y el
secreto JWT existente para conservar las sesiones durante la transición.

## Datos y credenciales

`backup.py` exporta la base configurada en Render con un snapshot PostgreSQL
consistente, produce hashes por tabla y guarda el archivo en S3 privado.
`restore.py` exige una base destino vacía, verifica la integridad del archivo,
restaura en una transacción y compara las 110 tablas. Copia los grants explícitos
del rol `aquanqa_app`, incluidos permisos por columna y función.

La API usa `aquanqa_app` sin privilegios administrativos. Las contraseñas y el
secreto JWT se inyectan desde Secrets Manager. RDS administra su contraseña maestra.
Los artefactos y estados locales están en `data/salida/aws_deploy_20260914`, ignorado
por Git. No se incluyen contraseñas ni dumps en imágenes o commits.

RDS tiene cifrado, protección contra eliminación y respaldo automático de un día,
el máximo admitido por el plan gratuito de esta cuenta durante el despliegue.
La instancia es Single-AZ `db.t4g.micro`, con 20 GiB gp3 y crecimiento hasta 100 GiB.
La API usa dos tareas de 0,5 vCPU y 1 GiB. Este dimensionamiento inicial no representa
una garantía de alta disponibilidad de la base; revisar capacidad y plan de cuenta
según uso. Los logs se conservan 30 días.
CloudWatch tiene alarmas de CPU/espacio de RDS y errores 5xx de la API; se consultan
en la consola y no tienen destinatarios de notificación configurados.

## Operación

Requisitos locales: AWS CLI autenticado, Python con boto3/psycopg/requests/PyYAML,
PostgreSQL 18 para exportar y Node/npm para construir Angular.

```powershell
aws login
python infra/aws/deploy.py status
python infra/aws/deploy.py api_status
python infra/aws/deploy.py build_status
```

`production.json` es la plantilla CloudFormation de la infraestructura base.
CloudFront, tareas ECS y releases se administran con `deploy.py`; sus identificadores
quedan en los archivos de estado locales. El estado desplegado debe consultarse
en AWS antes de ejecutar cambios. `base` es únicamente para creación inicial.

Para una actualización de código, construir y verificar el Frontend, ejecutar
`deploy.py build`, comprobar `build_status`, y desplegar la API indicando
`DB_NAME=aquanqa_live` en el entorno (también es el valor predeterminado).
`aquanqa` es exclusivamente la restauración de ensayo y requiere selección explícita.
El comando exige evidencia de la restauración verificada. `deploy.py frontend` publica los archivos compilados
e invalida CloudFront. ECS revierte automáticamente despliegues que no superen
la comprobación de salud.

La rama `codex/aws-production-20260914` contiene la instantánea de despliegue.
`publish.py` usa un índice Git separado para preservar el trabajo local y no
activar por accidente el despliegue de la rama anterior de Render.

## Cambio de base y reversión

Realizar primero la restauración de ensayo y las pruebas HTTP. Para el corte,
detener temporalmente las escrituras del origen, exportar un respaldo final,
restaurarlo en `aquanqa_live`, verificar hashes y cambiar la API y el proxy.
No habilitar escrituras en dos bases a la vez. Conservar Neon como respaldo.

Si AWS ya recibió escrituras, no devolver tráfico a Neon sin sincronizar los datos
nuevos. Una reversión de código puede usar una revisión anterior de la tarea ECS
manteniendo la base RDS de producción.
