"""Comprueba que la separación por capas del tablero siga siendo cierta.

Una arquitectura documentada y no verificada dura hasta el primer apuro. Esto es el
equivalente, a escala del tablero, de lo que CI hace con las fronteras de `domain/`,
`etl/` y `backend/` (ADR-0006).

Dos reglas:

  1. `nucleo/` y `config.py` no importan Streamlit ni Plotly. Es lo que permite ejecutar
     y probar el cálculo desde una consola, sin levantar la app.
  2. Las dependencias van en un solo sentido:  vistas → servicios → nucleo → config.

Uso:
    python db/tools/dashboard/verificar_capas.py
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent

# Qué capa puede importar a cuál. Una capa siempre puede importarse a sí misma.
PERMITIDO: dict[str, set[str]] = {
    "config": set(),
    "nucleo": {"config"},
    "servicios": {"config", "nucleo"},
    "vistas": {"config", "nucleo", "servicios"},
}

# Paquetes de interfaz que no pueden aparecer en las capas de cálculo.
PROHIBIDO: dict[str, set[str]] = {
    "config": {"streamlit", "plotly"},
    "nucleo": {"streamlit", "plotly"},
}


def _capa(archivo: Path) -> str | None:
    """A qué capa pertenece un archivo; None si está fuera del esquema (p. ej. app.py)."""
    relativo = archivo.relative_to(RAIZ)
    nombre = relativo.parts[0] if len(relativo.parts) > 1 else relativo.stem
    return nombre if nombre in PERMITIDO else None


def _importados(archivo: Path) -> list[str]:
    """Raíces de todos los módulos importados por un archivo."""
    arbol = ast.parse(archivo.read_text(encoding="utf-8"))
    raices = []
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            raices += [alias.name.split(".")[0] for alias in nodo.names]
        elif isinstance(nodo, ast.ImportFrom) and nodo.module:
            raices.append(nodo.module.split(".")[0])
    return raices


def revisar() -> list[str]:
    fallos = []
    for archivo in sorted(RAIZ.rglob("*.py")):
        if "__pycache__" in archivo.parts or archivo.name == Path(__file__).name:
            continue
        capa = _capa(archivo)
        if capa is None:  # app.py arma la página: puede importar de todo
            continue
        for raiz in _importados(archivo):
            ruta = archivo.relative_to(RAIZ)
            if raiz in PROHIBIDO.get(capa, set()):
                fallos.append(f"{ruta}: «{capa}» no puede importar «{raiz}»")
            elif raiz in PERMITIDO and raiz != capa and raiz not in PERMITIDO[capa]:
                fallos.append(f"{ruta}: «{capa}» no puede depender de «{raiz}»")
    return fallos


if __name__ == "__main__":
    # Marcadores ASCII a propósito: la consola de Windows es cp1252 y revienta con ✓/✗.
    problemas = revisar()
    if problemas:
        print("FALLA: la separacion por capas esta rota")
        print("\n".join(f"    {p}" for p in problemas))
        sys.exit(1)
    print("OK: nucleo y config sin Streamlit/Plotly, dependencias en un solo sentido")
