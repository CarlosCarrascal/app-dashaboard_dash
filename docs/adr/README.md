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

## Cómo añadir uno

Numeración correlativa, un archivo por decisión, y solo para decisiones que **cierran una
alternativa razonable**. Si no hubo alternativa, no hace falta ADR: basta un comentario en el
código.
