# Acceso directo desde pgAdmin

Cambio solicitado por el propietario: RDS `aquanqa-production` es públicamente accesible. El grupo `sg-0110993164a5e3387` conserva el permiso para la API y tiene una regla TCP 5432 desde `190.187.225.232/32`. La regla de IP se administra fuera de CloudFormation. No ampliar a 0.0.0.0/0. Esta configuración reemplaza las referencias anteriores a RDS sin acceso público.

- Base: `aquanqa_live`
- Host: `aquanqa-production.culyqsqugon3.us-east-1.rds.amazonaws.com`
- Puerto: `5432`
- Usuario: `aquanqa_consulta`, solo lectura en los esquemas existentes.
- TLS: `verify-full` con el certificado regional oficial de RDS.
- Perfil local: `Aquanqa AWS - solo lectura`, grupo `AWS Produccion`.

Los parámetros y la contraseña aleatoria están en `%APPDATA%/Aquanqa/pgadmin`, con permisos de Windows restringidos al usuario. No están en Git. La contraseña del panel web no sirve para PostgreSQL. Las tablas nuevas requerirán otorgar SELECT si no heredan permisos adecuados.

Si cambia la IP pública del equipo, sustituir exclusivamente la regla /32 de consulta. Mantener el acceso de la API. Para retirar el acceso directo, quitar esa regla y devolver PubliclyAccessible a false, actualizando también la plantilla.

El acceso público de RDS puede añadir un cargo por IPv4; consultar la factura. No se creó un servidor puente ni un servicio adicional permanente.
