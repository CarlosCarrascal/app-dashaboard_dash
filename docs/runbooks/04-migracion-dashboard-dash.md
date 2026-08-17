# Migración del dashboard a Dash

Dash es la aplicación oficial y se despliega de forma independiente desde `apps/dashboard`.
El núcleo analítico reutilizable vive directamente en `packages/analitica`.

## Comandos

```bash
npm run setup
npm run dashboard
npm run dashboard:dash:css
```

## Despliegue

El contexto de construcción es la raíz del repositorio:

```bash
docker build -f apps/dashboard/Dockerfile -t aquanqa-dashboard .
docker run --rm -p 8050:8050 aquanqa-dashboard
```

El contenedor solo instala `packages/analitica` y `apps/dashboard`. No incluye ETL, API,
Streamlit ni PostgreSQL.

Streamlit fue retirado del repositorio. Dash es ahora la única interfaz web mantenida y el
paquete analítico no contiene dependencias de frameworks de presentación.
