"""Ensambla el reporte HTML final de relación de variables (2025).

Inserta el JSON que produce preparar_reporte_shap_2025.py en la plantilla
(plantilla_reporte_shap_2025.html — HTML/CSS/JS autocontenido, sin dependencias
externas) y escribe el resultado en docs/modelo/. No hace ningún cálculo: solo
combina lo que ya se calculó y validó.

Orden completo para regenerar el reporte desde cero:
    python db/tools/analisis_shap_relacion_2025.py     # entrena, valida, SHAP
    python db/tools/preparar_reporte_shap_2025.py       # describe los datos de entrada
    python db/tools/generar_reporte_shap_2025.py        # ensambla el HTML
"""

from __future__ import annotations

from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
PLANTILLA = Path(__file__).resolve().parent / "plantilla_reporte_shap_2025.html"
DATOS = RAIZ / "data" / "salida" / "reporte_shap_2025_completo.json"
DESTINO = RAIZ / "docs" / "modelo" / "relacion_variables_kg_ha_2025.html"


def main() -> int:
    if not DATOS.exists():
        print(f"ERROR: no existe {DATOS}. Correr antes preparar_reporte_shap_2025.py")
        return 1

    plantilla = PLANTILLA.read_text(encoding="utf-8")
    datos = DATOS.read_text(encoding="utf-8")

    if "__DATOS_JSON__" not in plantilla:
        print("ERROR: la plantilla no tiene el marcador __DATOS_JSON__")
        return 1

    final = plantilla.replace("__DATOS_JSON__", datos)
    DESTINO.write_text(final, encoding="utf-8")
    print(f"OK  {DESTINO}  ({DESTINO.stat().st_size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
