# Panel administrativo Angular

Frontend principal del panel operativo agrícola. Está construido con Angular 22 standalone,
Tailwind CSS 4, Angular CDK, TanStack Table, ECharts y un cliente tipado desde el contrato OpenAPI de FastAPI.
Angular Material se conserva en las pantallas administrativas heredadas.

Evaluaciones tiene seis rutas independientes bajo `/admin/evaluaciones/`: `estadios`, `flores`,
`baya`, `pesos`, `brotes` y `ramas`. La entrada recuerda el último módulo visitado.
El tema visual está en `src/workspace.css`; Tailwind se procesa con PostCSS, separado del SCSS heredado.
La fuente Inter se incluye localmente desde `@fontsource-variable/inter`.

Los gráficos consumen `/v1/admin/evaluaciones/analitica`; requieren la versión actual del backend.
`npm start -- --port 4211` utiliza la API desplegada en Render mediante un proxy local.
`npm run start:local -- --port 4211` utiliza el backend local en el puerto 8000.
No se utiliza el servidor de fixtures anterior.

## Desarrollo local

Desde `frontend/`:

```bash
npm install --legacy-peer-deps
npm run api:types
npm start
```

Por defecto, el proxy envía `/v1` a `https://aquanqa-campo-api.onrender.com`, que consulta Neon.
Las operaciones de edición realizadas en este perfil actúan sobre los datos remotos.
Para trabajar con la API y base locales, utiliza `npm run start:local`.

El alias explícito para el mismo perfil de Render es:

```bash
npm run start:deployed
```

Ese perfil envía `/v1` a `https://aquanqa-campo-api.onrender.com`. El backend desplegado debe
contener las rutas administrativas actuales (`/v1/auth/*` y `/v1/admin/*`); si solo expone el
contrato móvil anterior, el panel puede abrirse pero no podrá iniciar sesión.

## Contrato API

`npm run api:types` regenera `src/app/core/api/generated.ts` a partir de
`../docs/api/openapi-v1.json`. Los servicios de `src/app/core/api/` consumen ese contrato mediante
HttpClient y el interceptor agrega el Bearer token a las peticiones protegidas.

## Primer alcance

El panel incluye sesión RBAC, resumen, evaluaciones server-side, maestros, calidad y
previsualización de Excel. La previsualización no escribe datos productivos. Forecast, cosecha,
riego, packing, tareo y reportes tienen navegación base preparada para crecer por dominio.

Para crear el primer usuario administrativo usa desde la raíz del monolito una conexión
privilegiada, por ejemplo `AQUANQA_PROVISION_DATABASE_URL=...`, con
`backend/campo-api/scripts/provision_user.py`. La conexión normal de la API no tiene permiso para
insertar usuarios.

## Diseño de Evaluaciones

Evaluaciones usa HTML y SCSS propios, sin Tailwind ni AG Grid. TanStack Table 8 controla las
columnas y el modelo de filas; el marcado y los estilos siguen siendo de la aplicación.
La ordenación, los filtros y la paginación se resuelven en FastAPI. La exportación CSV contiene
solo la página actual y las columnas visibles, y neutraliza fórmulas de hoja de cálculo.

- `evaluaciones.component.html` y `.scss`: composición, filtros, tarjetas y tabla.
- `evaluation-detail.scss`: panel de detalle y corrección con foco de teclado contenido.
- `evaluation-analytics.ts`: cálculos y opciones de gráficos, separados de la presentación.
- `evaluation-chart.component.ts`: ECharts modular con ResizeObserver y limpieza al destruirse.

El mosaico y la dona muestran todas las familias, aplicando la búsqueda, fechas y territorio
de la consulta completa. Seleccionar una familia restringe sus indicadores y registros; las
otras familias permanecen visibles para comparar. Los porcentajes E1–E5 usan la suma de sus
conteos. El mapa de calor indica explícitamente que representa solo la página actual.
No se infieren salud del cultivo, clima ni geografía: el contrato no incluye esos datos.

La navegación se contrae a una barra de iconos en Evaluaciones para dejar espacio al análisis.
Sesión, permisos, correcciones auditadas, importación y contratos API conservan sus capas.
`npm test -- --watch=false` verifica denominadores, coordinación de consultas, fechas y exportación.
`npm run build` comprueba tipos, plantillas y presupuestos de producción.

La instalación mantiene `--legacy-peer-deps` porque el generador OpenAPI del proyecto declara
TypeScript 5 y Angular 22 requiere TypeScript 6; no se cambió ese contrato de herramientas.
