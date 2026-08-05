"""La frontera de ADR-0006, como prueba en lugar de como comentario.

`domain` viaja dentro del contenedor Linux del backend en AWS, donde el driver ODBC de Access
**no existe**. Si este paquete llega a importar `pyodbc`, el backend deja de arrancar — y el
fallo aparecería en el despliegue, con la app Flutter ya apuntando ahí, no aquí.

Al revés también importa: si `domain` importara `fastapi`, el ETL arrastraría un servidor web
para leer un `.accdb`, y la regla de negocio quedaría atada a una forma concreta de exponerla.

Se comprueba sobre el AST y no con una búsqueda de texto, para que un `pyodbc` mencionado en un
comentario o en un docstring no dé un falso positivo.
"""

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"

# HTTP y servidores: eso es `backend/campo-api`. Extracción de Access: eso es `etl/`.
# Y ninguno de los dos consumidores puede aparecer aquí: `domain` no conoce a quien lo usa.
PROHIBIDAS = {
    "fastapi",
    "starlette",
    "uvicorn",
    "pyodbc",
    "aquanqa_etl",
    "aquanqa_campo_api",
}


def _importa(archivo: Path) -> set[str]:
    """Los módulos de primer nivel que importa un archivo."""
    modulos: set[str] = set()
    for nodo in ast.walk(ast.parse(archivo.read_text(encoding="utf-8"))):
        if isinstance(nodo, ast.Import):
            modulos.update(alias.name.split(".")[0] for alias in nodo.names)
        # level > 0 es un import relativo (`from .rules import x`): siempre interno.
        elif isinstance(nodo, ast.ImportFrom) and nodo.module and nodo.level == 0:
            modulos.add(nodo.module.split(".")[0])
    return modulos


def test_no_importa_http_ni_access():
    for archivo in sorted(SRC.rglob("*.py")):
        prohibidas = _importa(archivo) & PROHIBIDAS
        assert not prohibidas, (
            f"{archivo.relative_to(SRC)} importa {sorted(prohibidas)}. `domain` no puede "
            "depender de HTTP, de la extracción de Access ni de sus propios consumidores "
            "(ADR-0006)."
        )


def test_el_paquete_importa_por_si_solo():
    """Sin `fastapi` ni `pyodbc` instalados, esto tiene que funcionar."""
    import aquanqa_domain

    assert aquanqa_domain.__doc__, "el paquete debería explicar qué frontera representa"
