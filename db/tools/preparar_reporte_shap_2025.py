"""Prepara los datos para el reporte HTML de relación de variables (2025).

Lee lo que ya escribió analisis_shap_relacion_2025.py (X, shap values, ranking) y
produce un único JSON con todo lo que el HTML necesita para embeber: estadística
descriptiva de cada variable de entrada, puntos de dependencia SHAP por variable
(para los gráficos de dispersión) y categorías para agrupar el ranking.

No vuelve a entrenar nada — solo describe lo que ya se entrenó y validó.

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
    "gdd_semana": "clima_semanal", "temp_media": "clima_semanal", "temp_max": "clima_semanal",
    "temp_min": "clima_semanal", "eto_semana_mm": "clima_semanal", "lluvia_semana_mm": "clima_semanal",
    "humedad_media": "clima_semanal",
    "gdd_acum_poda": "clima_acumulado", "eto_acum_poda_mm": "clima_acumulado",
    "lluvia_acum_poda_mm": "clima_acumulado",
    "edad_dias": "contexto_modulo", "poda_dispersion_dias": "contexto_modulo",
    "area_ha": "contexto_modulo", "n_plantas": "contexto_modulo",
    "modulo_id": "identidad",
}

CATEGORIA_ETIQUETA = {
    "riego": "Riego",
    "clima_semanal": "Clima semanal (igual en todo el fundo)",
    "clima_acumulado": "Clima acumulado desde la poda (varía por módulo)",
    "contexto_modulo": "Contexto del módulo (edad, poda, tamaño)",
    "identidad": "Identidad del módulo",
}

UNIDAD = {
    "riego_mm": "mm", "riego_m3": "m³", "riego_dias_con_registro": "días",
    "gdd_semana": "°D", "temp_media": "°C", "temp_max": "°C", "temp_min": "°C",
    "eto_semana_mm": "mm", "lluvia_semana_mm": "mm", "humedad_media": "%",
    "gdd_acum_poda": "°D", "eto_acum_poda_mm": "mm", "lluvia_acum_poda_mm": "mm",
    "edad_dias": "días", "poda_dispersion_dias": "días",
    "area_ha": "ha", "n_plantas": "plantas", "modulo_id": "",
}


def main() -> int:
    X = pd.read_csv(SALIDA / "shap_relacion_2025_X.csv")
    shap_values = np.load(SALIDA / "shap_relacion_2025_values.npy")
    resumen = json.loads((SALIDA / "shap_relacion_2025.json").read_text(encoding="utf-8"))

    features = [c for c in X.columns if c not in ("modulo", "fundo", "kg_ha")]
    imp_por_variable = {r["variable"]: r for r in resumen["importancia"]}

    # ── 1 · Estadística descriptiva de cada variable de entrada ──────────────
    descriptivos = []
    for f in features:
        serie = pd.to_numeric(X[f], errors="coerce") if f != "modulo_id" else None
        if f == "modulo_id":
            descriptivos.append({
                "variable": f, "categoria": CATEGORIA[f], "unidad": "",
                "n": int(X[f].notna().sum()), "n_faltante": int(X[f].isna().sum()),
                "n_niveles": int(X[f].nunique()),
            })
            continue
        descriptivos.append({
            "variable": f, "categoria": CATEGORIA[f], "unidad": UNIDAD.get(f, ""),
            "n": int(serie.notna().sum()), "n_faltante": int(serie.isna().sum()),
            "media": round(float(serie.mean()), 3) if serie.notna().any() else None,
            "desv": round(float(serie.std()), 3) if serie.notna().any() else None,
            "min": round(float(serie.min()), 3) if serie.notna().any() else None,
            "p25": round(float(serie.quantile(0.25)), 3) if serie.notna().any() else None,
            "mediana": round(float(serie.quantile(0.5)), 3) if serie.notna().any() else None,
            "p75": round(float(serie.quantile(0.75)), 3) if serie.notna().any() else None,
            "max": round(float(serie.max()), 3) if serie.notna().any() else None,
        })

    # ── 2 · Puntos de dependencia SHAP: (valor de la variable, shap, módulo) ──
    # Para las variables con mayor peso (excluida modulo_id, que no tiene un eje
    # numérico con sentido) — sirven para el gráfico de dispersión de cada una.
    top_dependencia = [
        r["variable"] for r in resumen["importancia"]
        if r["variable"] != "modulo_id"
    ][:6]
    dependencia = {}
    for f in top_dependencia:
        idx = features.index(f)
        valores = pd.to_numeric(X[f], errors="coerce")
        dependencia[f] = [
            {"x": (None if pd.isna(v) else round(float(v), 3)),
             "shap": round(float(s), 3),
             "modulo": m, "fundo": fu}
            for v, s, m, fu in zip(valores, shap_values[:, idx], X["modulo"], X["fundo"])
        ]

    # ── 3 · Ranking enriquecido con categoría y unidad ────────────────────────
    ranking = []
    for r in resumen["importancia"]:
        v = r["variable"]
        ranking.append({
            **r,
            "categoria": CATEGORIA.get(v, "otro"),
            "categoria_etiqueta": CATEGORIA_ETIQUETA.get(CATEGORIA.get(v, "otro"), "Otro"),
            "unidad": UNIDAD.get(v, ""),
        })

    # ── 4 · Muestra de filas crudas, para que se vea literalmente qué entra ───
    muestra = X.sample(n=min(10, len(X)), random_state=7).sort_values(["fundo", "modulo"])
    muestra_cols = ["fundo", "modulo", "kg_ha"] + [f for f in features if f != "modulo_id"]
    muestra_registros = muestra[muestra_cols].round(2).to_dict(orient="records")

    salida = {
        "resumen": {
            "n_filas": resumen["n_filas"],
            "n_modulos": resumen["n_modulos"],
            "validacion_a": resumen["validacion_a_5fold_aleatorio"],
            "validacion_b": resumen["validacion_b_deja_un_modulo_fuera"],
            "media_kg_ha": resumen["media_kg_ha"],
        },
        "descriptivos": descriptivos,
        "ranking": ranking,
        "dependencia": dependencia,
        "muestra": muestra_registros,
        "categorias": CATEGORIA_ETIQUETA,
    }

    ruta = SALIDA / "reporte_shap_2025_completo.json"
    ruta.write_text(json.dumps(salida, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OK  {ruta}  ({ruta.stat().st_size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
