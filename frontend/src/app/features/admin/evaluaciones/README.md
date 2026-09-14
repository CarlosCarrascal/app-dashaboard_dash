# Evaluaciones: dónde cambiar cada cosa

Las seis familias comparten una página. La ruta `evaluaciones/:familia` selecciona
la configuración; no se duplican seis pantallas ni se fuerza a que todas tengan las mismas métricas.

| Necesidad | Archivo o carpeta |
|---|---|
| Nombre, descripción o columnas de una familia | `familias/evaluation-families.ts` |
| Composición de la página, encabezado y estados generales | `evaluaciones.component.*` |
| Sincronización con la URL, cambios de vista, coordinación de carga | `evaluation-workspace.service.ts` |
| Filtros, opciones territoriales y etiquetas de filtros aplicados | `filtros/` |
| Tabla, anchos, columnas visibles y paginación visual | `registros/` |
| Ficha y paginación de observaciones | `detalle/` |
| Formulario y transformación del payload de corrección | `correccion/` |
| Composición visual y estado derivado del análisis | `analisis/` |
| Fórmulas y opciones de ECharts | `field-analytics.ts` |
| Solicitudes, caché de análisis/páginas y solicitudes pendientes | `datos/evaluation-data.service.ts` |
| Formatos, etiquetas de detalle y normalización de observaciones | `evaluation-format.ts` |

## Límites

La página provee `EvaluationWorkspace` y `EvaluationData`: cada instancia tiene su
propio estado y ciclo de vida. Los componentes de sección consumen esa fachada de
Evaluaciones; no dependen del componente padre ni extienden una clase base.
Los controladores de filtros, ficha, análisis y corrección declaran mediante `Host`
las operaciones y señales de coordinación que necesitan. Sus referencias al tipo
de fachada son solo de TypeScript, sin ciclos de importación en ejecución.

Los componentes de esta carpeta son propios del dominio. Solo una pieza visual
que se use fuera de Evaluaciones debe promocionarse a `shared/ui`.
Los componentes visuales no deben añadir peticiones HTTP ni cachés propias.

`EvaluationData` conserva la caché de la sesión de pantalla, con límites y caducidad,
y protege la invalidación mediante generaciones para que una respuesta antigua no
repueble datos borrados. `ApiClient` sigue siendo el transporte común y comparte
lecturas con la precarga de navegación. La invalidación del dominio limpia ambos
niveles. `DestroyRef` cancela las lecturas pendientes al destruir la página.

Una corrección notifica a la fachada, que invalida y recarga la página actual.
La ruta conserva permisos y el contrato de la API no cambia.

## Comprobación

Ejecutar `npm test -- --watch=false` y `npm run build` desde `frontend/`.
Las pruebas existentes cubren navegación, caché, respuestas obsoletas y precarga;
`evaluation-composition.spec.ts` comprueba que las secciones comparten estado y que
la ficha y el formulario extraídos siguen conectados al flujo de corrección.
