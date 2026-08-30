# Decisiones de arquitectura

Por qué el modelo es como es. Cada documento registra el contexto, la decisión y lo que se
descartó — para que dentro de un año se pueda saber si la razón sigue siendo válida.

| ADR | Decisión | Origen |
|---|---|---|
| [0001](0001-monorepo-por-capas.md) | Monorepo por capas, con el esquema como código · *tabla de capas superada por 0006* | H-02: las reglas no tenían dónde vivir |
| [0002](0002-grano-evaluacion-ramas.md) | La evaluación de ramas se parte en cabecera (planta) y detalle (rama) | N-1: el `UNIQUE` propuesto rechazaba el 94% de las filas |
| [0003](0003-identidad-de-lote.md) | La identidad de un lote es `(empresa, módulo, lote)`; el alias de fundo no es clave | N-3, N-4, N-5: ni el alias ni `(módulo, lote)` identifican un lote |
| [0004](0004-frontera-de-transformacion.md) | Cada transformación vive en una sola capa; Power BI solo mide | B-2, B-3, B-4, B-6: la misma lógica repartida en cuatro sitios, mal en tres |
| [0005](0005-filas-centinela-sin-null-en-fk.md) | Ninguna FK de un hecho queda NULL: apunta a una fila "Sin identificar" | N-15: 624 filas de forecast sin registro en cuarentena, 23 con doble registro |
| [0006](0006-un-solo-lenguaje-de-backend.md) | Un solo lenguaje de backend: `domain/` en Python. Fuera Drizzle, Zod y Next.js | La captura de campo pasa a Flutter, y deja sin propósito a las tres piezas TypeScript |
| [0007](0007-gobierno-analitico-y-champion-challenger.md) | Gobierno analítico y champion-challenger | R09 es campeón inicial; toda promoción exige evidencia temporal y trazabilidad |
| [0008](0008-modulo-modelo-legacy.md) | El módulo XGBoost/SHAP/R² 2025 queda como legacy | Se conserva para auditoría, pero `/analitica/*` es la única capa oficial |
| [0009](0009-refactor-interno-analitica.md) | Refactor interno de analítica, compatible y por etapas · antecedente conservado: [0009-refactor-interno-compatible.md](0009-refactor-interno-compatible.md) | Cada extracción conserva fachadas y contratos; el rollback requiere un baseline versionado |
| [0010](0010-desacoplamiento-nucleo.md) | Desacoplamiento del núcleo analítico · antecedente conservado: [0010-separacion-nucleo-persistencia-tracking.md](0010-separacion-nucleo-persistencia-tracking.md) | Los contratos y transformaciones no se cargan junto con persistencia o integraciones opcionales |
| [0011](0011-descomposicion-proyeccion.md) | Descomposición de proyección con API pública lazy · antecedente conservado: [0011-descomposicion-proyeccion-y-api-lazy.md](0011-descomposicion-proyeccion-y-api-lazy.md) | Se reducen ciclos e imports pesados sin cambiar el contrato |
| [0012](0012-maestro-lotes-access-principal.md) | `M_Lotes` de Access es el maestro primario; Excel queda como contraste | La conciliación actual muestra que Access contiene las 879 claves de Excel y agrega 3 |
| [0013](0013-trazabilidad-migracion-por-tabla.md) | La migración se controla por snapshot y por tabla desde `raw` hasta `core` | No basta con saber que Access llegó a `raw`: hay que demostrar qué tablas pasaron a cada capa |
| [0014](0014-prefijos-semanticos-core.md) | `core` usa prefijos semánticos; `raw` conserva los nombres físicos de Access | Facilita la navegación en pgAdmin sin mezclar origen, modelo canónico y dashboard |
| [0015](0015-arquitectura-actual-analitica.md) | Arquitectura actual de `packages/analitica`: modelos, procesos, infraestructura e interfaces | `nowcast` es un proceso; `híbrido`, `fenológico` y `ocurrencia` son modelos o familias de modelos |

## Cómo añadir uno

Numeración correlativa, un archivo por decisión, y solo para decisiones que **cierran una
alternativa razonable**. Si no hubo alternativa, no hace falta ADR: basta un comentario en el
código.
