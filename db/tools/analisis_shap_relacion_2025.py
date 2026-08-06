"""Relación entre variables y kg/ha, a nivel módulo, SOLO 2025.

A diferencia de analisis_shap_kg_ha.py (que intentaba pronosticar la semana
SIGUIENTE y no validó — R2 negativo en dos esquemas de validación distintos), este
script no pronostica: explica el kg_ha de LA MISMA semana con las variables de esa
misma semana. Alcance fijado con el usuario (2026-08-06): solo 2025, porque es el
único año con riego real cargado — cualquier semana fuera de 2025 tendría riego_mm
en NULL y mezclaría alcance.

Sigue sin ser una relación "probada": se valida honestamente (K-fold agrupado por
módulo, para saber si el patrón generaliza a un módulo que el modelo nunca vio) y se
reporta el resultado exacto, sea el que sea.

Uso:
    python db/tools/analisis_shap_relacion_2025.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import shap
import xgboost as xgb
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import GroupKFold, KFold

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analisis_shap_kg_ha import ETIQUETAS, cargar_panel  # noqa: E402

RAIZ = Path(__file__).resolve().parents[2]
SALIDA = RAIZ / "data" / "salida"

FEATURES = [
    "edad_dias", "poda_dispersion_dias",
    "gdd_semana", "temp_media", "temp_max", "temp_min",
    "eto_semana_mm", "lluvia_semana_mm", "humedad_media",
    "gdd_acum_poda", "eto_acum_poda_mm", "lluvia_acum_poda_mm",
    "riego_mm", "riego_m3", "riego_dias_con_registro",
    "area_ha", "n_plantas",
]


def main() -> int:
    panel = cargar_panel()
    p25 = panel[panel["anio_semana"].str.match(r"^2025-")].copy()
    print(f"2025: {len(p25)} filas, {p25['modulo_id'].nunique()} módulos, "
          f"con riego: {p25['riego_mm'].notna().sum()}/{len(p25)}")

    X = p25[FEATURES + ["modulo_id"]].copy()
    X["modulo_id"] = X["modulo_id"].astype("category")
    y = pd.to_numeric(p25["kg_ha"], errors="coerce")
    mask = y.notna()
    X, y = X[mask], y[mask]
    modulo = p25.loc[mask, "modulo_id"]
    modulo_txt = p25.loc[mask, "modulo"]
    fundo_txt = p25.loc[mask, "fundo"]

    def modelo_nuevo():
        return xgb.XGBRegressor(
            n_estimators=300, max_depth=4, learning_rate=0.05,
            subsample=0.8, colsample_bytree=0.8,
            enable_categorical=True, random_state=42,
        )

    # (a) K-fold estándar: qué tan bien ajusta dentro del patrón general de 2025.
    kf = KFold(n_splits=5, shuffle=True, random_state=42)
    pred_kf = np.full(len(X), np.nan)
    for tr, te in kf.split(X):
        m = modelo_nuevo()
        m.fit(X.iloc[tr], y.iloc[tr])
        pred_kf[te] = m.predict(X.iloc[te])
    mae_kf, r2_kf = mean_absolute_error(y, pred_kf), r2_score(y, pred_kf)
    print(f"(a) 5-fold aleatorio: MAE={mae_kf:.1f} kg/ha, R2={r2_kf:.3f}")

    # (b) Deja-un-módulo-fuera: ¿el patrón generaliza a un módulo que el modelo
    # nunca vio? Es la prueba más dura y la más relevante para "por módulo".
    gkf = GroupKFold(n_splits=min(19, modulo.nunique()))
    pred_gkf = np.full(len(X), np.nan)
    for tr, te in gkf.split(X, y, groups=modulo):
        m = modelo_nuevo()
        m.fit(X.iloc[tr], y.iloc[tr])
        pred_gkf[te] = m.predict(X.iloc[te])
    mae_gkf, r2_gkf = mean_absolute_error(y, pred_gkf), r2_score(y, pred_gkf)
    print(f"(b) Deja-un-módulo-fuera: MAE={mae_gkf:.1f} kg/ha, R2={r2_gkf:.3f}")

    # Explicación: se ajusta con TODOS los datos de 2025 para tener la mejor
    # evidencia posible sobre el patrón que sí describe (a), no para pronosticar.
    modelo_completo = modelo_nuevo()
    modelo_completo.fit(X, y)
    explicador = shap.TreeExplainer(modelo_completo)
    shap_values = explicador(X)

    importancia = pd.DataFrame({
        "variable": X.columns,
        "etiqueta": [ETIQUETAS.get(c, c) for c in X.columns],
        "shap_medio_abs": np.abs(shap_values.values).mean(axis=0),
        "shap_medio_con_signo": shap_values.values.mean(axis=0),
    }).sort_values("shap_medio_abs", ascending=False).reset_index(drop=True)

    print("\nRanking de importancia (SHAP medio absoluto, 2025, por módulo):")
    print(importancia.to_string(index=False))

    SALIDA.mkdir(parents=True, exist_ok=True)
    (SALIDA / "shap_relacion_2025.json").write_text(
        json.dumps(
            {
                "alcance": "2025, a nivel módulo, kg_ha de la misma semana (no pronóstico)",
                "n_filas": len(X),
                "n_modulos": int(modulo.nunique()),
                "validacion_a_5fold_aleatorio": {"mae": round(float(mae_kf), 2), "r2": round(float(r2_kf), 4)},
                "validacion_b_deja_un_modulo_fuera": {"mae": round(float(mae_gkf), 2), "r2": round(float(r2_gkf), 4)},
                "media_kg_ha": round(float(y.mean()), 2),
                "importancia": importancia.to_dict(orient="records"),
            },
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )

    np.save(SALIDA / "shap_relacion_2025_values.npy", shap_values.values)
    X_guardar = X.copy()
    X_guardar["modulo"] = modulo_txt.to_numpy()
    X_guardar["fundo"] = fundo_txt.to_numpy()
    X_guardar["kg_ha"] = y.to_numpy()
    X_guardar.to_csv(SALIDA / "shap_relacion_2025_X.csv", index=False)

    print(f"\nOK  {SALIDA / 'shap_relacion_2025.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
