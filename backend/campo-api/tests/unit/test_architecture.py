"""Fronteras del monolito modular expresadas como pruebas."""

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "aquanqa_campo_api"


def _absolute_imports(path: Path) -> set[str]:
    imports: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            imports.add(node.module)
    return imports


def test_servicios_y_reglas_no_dependen_de_fastapi_ni_infraestructura():
    targets = [*SRC.glob("modules/*/service.py"), *SRC.glob("modules/*/rules.py")]
    for path in targets:
        imports = _absolute_imports(path)
        forbidden = ("fastapi", "aquanqa_campo_api.infrastructure")
        assert not any(name.startswith(forbidden) for name in imports)


def test_api_ya_no_importa_el_paquete_domain_compartido():
    for path in SRC.rglob("*.py"):
        assert "aquanqa_domain" not in _absolute_imports(path), path
