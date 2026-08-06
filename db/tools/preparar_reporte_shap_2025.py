"""Prepara el JSON que alimenta el reporte HTML de relación de variables (2025).

Lee lo que escribió analisis_shap_relacion_2025.py (X, SHAP, ranking, validaciones) y
arma un único JSON en formato COLUMNAR: una lista por columna en vez de un objeto por
fila. Eso permite que el HTML grafique cualquier variable sin recibir 471 objetos
repetidos por cada una.

No entrena ni valida nada: solo describe y reempaqueta lo que ya se calculó.

Uso:
    python db/tools/preparar_reporte_shap_2025.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
SALIDA = RAIZ / "data" / "salida"

CATEGORIA = {
    "riego_mm": "riego", "riego_m3": "riego", "riego_dias_con_registro": "riego",
    "balance_hidrico_mm": "riego", "ratio_reposicion": "riego", "riego_por_planta_l": "riego",
    "gdd_semana": "clima_semanal", "temp_media": "clima_semanal", "temp_max": "clima_semanal",
    "temp_min": "clima_semanal", "eto_semana_mm": "clima_semanal",
    "lluvia_semana_mm": "clima_semanal", "humedad_media": "clima_semanal",
    "gdd_acum_poda": "clima_acumulado", "eto_acum_poda_mm": "clima_acumulado",
    "lluvia_acum_poda_mm": "clima_acumulado", "gdd_por_dia": "clima_acumulado",
    "eto_por_dia": "clima_acumulado",
    "edad_dias": "contexto_modulo", "poda_dispersion_dias": "contexto_modulo",
    "area_ha": "contexto_modulo", "n_plantas": "contexto_modulo",
    "semana_num": "contexto_modulo", "sem_sin": "contexto_modulo", "sem_cos": "contexto_modulo",
    "modulo_id": "identidad",
}

CATEGORIA_ETIQUETA = {
    "riego": "Riego",
    "contexto_modulo": "Contexto del módulo",
    "clima_acumulado": "Clima acumulado desde poda",
    "clima_semanal": "Clima semanal",
    "identidad": "Identidad del módulo",
}

ETIQUETA = {
    "riego_mm": "Lámina de riego aplicada en la semana",
    "riego_m3": "Volumen bruto de agua aplicado en la semana",
    "riego_dias_con_registro": "Días de la semana con registro de riego",
    "balance_hidrico_mm": "Balance hídrico: riego + lluvia − demanda (ETO)",
    "ratio_reposicion": "Fracción de la demanda hídrica cubierta por riego + lluvia",
    "riego_por_planta_l": "Litros de agua por planta en la semana",
    "gdd_semana": "Grados-día de crecimiento de la semana",
    "temp_media": "Temperatura media de la semana",
    "temp_max": "Temperatura máxima de la semana",
    "temp_min": "Temperatura mínima de la semana",
    "eto_semana_mm": "Evapotranspiración (demanda hídrica) de la semana",
    "lluvia_semana_mm": "Lluvia de la semana",
    "humedad_media": "Humedad relativa media de la semana",
    "gdd_acum_poda": "Grados-día acumulados desde la poda de este módulo",
    "eto_acum_poda_mm": "ETO acumulada desde la poda de este módulo",
    "lluvia_acum_poda_mm": "Lluvia acumulada desde la poda de este módulo",
    "gdd_por_dia": "Ritmo térmico: grados-día por día desde la poda",
    "eto_por_dia": "Demanda hídrica media por día desde la poda",
    "edad_dias": "Edad del fruto: días desde la poda",
    "poda_dispersion_dias": "Dispersión de la poda entre los lotes del módulo",
    "area_ha": "Área productiva del módulo",
    "n_plantas": "Plantas del módulo",
    "semana_num": "Número de semana del año (estacionalidad)",
    "sem_sin": "Estacionalidad cíclica (seno de la semana)",
    "sem_cos": "Estacionalidad cíclica (coseno de la semana)",
    "modulo_id": "Identidad del módulo: todo lo que lo distingue y no se mide",
}

UNIDAD = {
    "riego_mm": "mm", "riego_m3": "m³", "riego_dias_con_registro": "días",
    "balance_hidrico_mm": "mm", "ratio_reposicion": "×", "riego_por_planta_l": "l/planta",
    "gdd_semana": "°D", "temp_media": "°C", "temp_max": "°C", "temp_min": "°C",
    "eto_semana_mm": "mm", "lluvia_semana_mm": "mm", "humedad_media": "%",
    "gdd_acum_poda": "°D", "eto_acum_poda_mm": "mm", "lluvia_acum_poda_mm": "mm",
    "gdd_por_dia": "°D/día", "eto_por_dia": "mm/día",
    "edad_dias": "días", "poda_dispersion_dias": "días",
    "area_ha": "ha", "n_plantas": "plantas", "semana_num": "sem",
    "sem_sin": "", "sem_cos": "", "modulo_id": "",
}

FORMULA = {
    "balance_hidrico_mm": "riego_mm + lluvia_semana_mm − eto_semana_mm",
    "ratio_reposicion": "(riego_mm + lluvia_semana_mm) ÷ eto_semana_mm",
    "riego_por_planta_l": "riego_m3 × 1000 ÷ n_plantas",
    "gdd_por_dia": "gdd_acum_poda ÷ edad_dias",
    "eto_por_dia": "eto_acum_poda_mm ÷ edad_dias",
    "semana_num": "número de semana ISO",
    "sem_sin": "sen(2π × semana ÷ 52)",
    "sem_cos": "cos(2π × semana ÷ 52)",
}


def limpiar(v):
    """NaN/inf → None, para que el JSON sea válido y el HTML pueda filtrarlos."""
    if v is None:
        return None
    f = float(v)
    return None if (np.isnan(f) or np.isinf(f)) else round(f, 4)


def main() -> int:
    X = pd.read_csv(SALIDA / "shap_relacion_2025_X.csv")
    shap_values = np.load(SALIDA / "shap_relacion_2025_values.npy")
    resumen = json.loads((SALIDA / "shap_relacion_2025.json").read_text(encoding="utf-8"))

    no_features = {"modulo", "fundo", "kg_ha", "semana"}
    features = [c for c in X.columns if c not in no_features]
    imp = {r["variable"]: r for r in resumen["importancia"]}

    # ── Metadatos + estadística por variable ─────────────────────────────
    lista = []
    for f in features:
        cat = CATEGORIA.get(f, "contexto_modulo")
        fila = {
            "var": f,
            "etiqueta": ETIQUETA.get(f, f),
            "categoria": cat,
            "unidad": UNIDAD.get(f, ""),
            "derivada": f in FORMULA,
            "formula": FORMULA.get(f, ""),
            "shap_abs": round(float(imp[f]["shap_medio_abs"]), 3),
            "shap_signo": round(float(imp[f]["shap_medio_con_signo"]), 3),
        }
        if f != "modulo_id":
            s = pd.to_numeric(X[f], errors="coerce")
            fila["desc"] = {
                "media": limpiar(s.mean()), "desv": limpiar(s.std()),
                "min": limpiar(s.min()), "p25": limpiar(s.quantile(0.25)),
                "mediana": limpiar(s.quantile(0.5)), "p75": limpiar(s.quantile(0.75)),
                "max": limpiar(s.max()), "faltante": int(s.isna().sum()),
            }
        lista.append(fila)
    lista.sort(key=lambda d: -d["shap_abs"])

    # ── Datos columnares: una lista por columna ──────────────────────────
    idx = {f: features.index(f) for f in features}
    filas = {
        "modulo": X["modulo"].tolist(),
        "fundo": X["fundo"].tolist(),
        "semana": (X["semana"].tolist() if "semana" in X.columns else [""] * len(X)),
        "kg_ha": [limpiar(v) for v in pd.to_numeric(X["kg_ha"], errors="coerce")],
        "x": {f: [limpiar(v) for v in pd.to_numeric(X[f], errors="coerce")] for f in features if f != "modulo_id"},
        "shap": {f: [limpiar(v) for v in shap_values[:, idx[f]]] for f in features},
    }
    # modulo_id no tiene eje numérico con sentido, pero su SHAP sí se grafica en el ranking
    filas["x"]["modulo_id"] = [None] * len(X)

    # ── Muestra de filas crudas ──────────────────────────────────────────
    cols_muestra = ["fundo", "modulo"] + (["semana"] if "semana" in X.columns else []) + ["kg_ha"] + \
                   [f["var"] for f in lista if f["var"] != "modulo_id"][:8]
    muestra = X.sample(n=min(10, len(X)), random_state=7).sort_values(["fundo", "modulo"])
    registros = []
    for _, r in muestra.iterrows():
        reg = {}
        for c in cols_muestra:
            v = r[c]
            reg[c] = v if isinstance(v, str) else limpiar(v)
        registros.append(reg)

    salida = {
        "meta": {
            "n_filas": resumen["n_filas"],
            "n_modulos": resumen["n_modulos"],
            "media_kg_ha": resumen["media_kg_ha"],
            "reproducir": (
                "<b>Reproducir:</b> <code>python db/tools/analisis_shap_relacion_2025.py</code> "
                "(entrena, valida y calcula SHAP) → "
                "<code>python db/tools/preparar_reporte_shap_2025.py</code> (describe las entradas) → "
                "<code>python db/tools/generar_reporte_shap_2025.py</code> (arma este HTML). "
                "Requiere el entorno conda <code>aquanqa</code>. Documentación completa, incluido el "
                "intento de pronóstico descartado, en <code>docs/modelo/02_relacion_variables_kg_ha.md</code>."
            ),
        },
        "modelo": resumen["modelo_reporte"],
        "categorias": CATEGORIA_ETIQUETA,
        "features": lista,
        "filas": filas,
        "muestra": registros,
        "muestra_cols": cols_muestra,
        "hallazgos": resumen["hallazgos"],
        "limites": resumen["limites"],
    }

    ruta = SALIDA / "reporte_shap_2025_completo.json"
    ruta.write_text(json.dumps(salida, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"OK  {ruta}  ({ruta.stat().st_size / 1024:.0f} KB)")
    print(f"    {len(lista)} variables · {len(X)} filas · {len(filas['shap'])} series SHAP")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
