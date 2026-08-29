"""Piezas de la página de relaciones.

El prefijo `_` mantiene el paquete fuera del registro de páginas de Dash: acá no vive
ninguna ruta, solo el contenido que `pages/analitica/relaciones.py` compone.

- `textos`    — todo lo escrito a mano, separado del código que lo coloca.
- `formato`   — traducción de cifras crudas al castellano del cultivo.
- `analisis`  — consolidación de los barridos en hallazgos y recuentos.
- `graficos`  — las figuras.
- `paneles`   — los bloques visibles, cada uno con su «cómo se lee».
"""

from __future__ import annotations

from . import analisis, formato, graficos, paneles, textos

__all__ = ["analisis", "formato", "graficos", "paneles", "textos"]
