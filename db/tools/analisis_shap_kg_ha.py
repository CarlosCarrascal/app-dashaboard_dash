"""Paso 3 del plan de IA: importancia de variables (SHAP) para kg/ha a 1 semana.

Entrena un XGBoost sobre reporting.v_analitica_modulo_semana para predecir el kg_ha
de la SIGUIENTE semana ISO de un módulo a partir de las variables de ESTA semana, y
calcula SHAP para ver qué variable pesa más.

Alcance definido con el usuario (2026-08-06): sin fenología (E02-E05, solo cubren
C2026, no comparable entre campañas) y con riego real ya cargado (solo 2025).

El "1 semana adelante" se construye por FECHA, no por posición de fila: se exige que
la semana siguiente empiece exactamente al día después de que termina la actual, para
el mismo módulo. Un módulo sin cosecha una semana simplemente no tiene fila esa
semana en el panel — no se rellena con kg_ha=0, porque eso sería asumir que "sin fila"
significa "cosechó cero" y nadie lo ha confirmado. El precio de esa honestidad es que
solo se entrena con pares de semanas realmente consecutivas.

Uso:
    python db/tools/analisis_shap_kg_ha.py

Requiere el entorno `aquanqa` (pandas, xgboost, shap, psycopg).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg
import shap
import xgboost as xgb
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import GroupKFold

RAIZ = Path(__file__).resolve().parents[2]
SALIDA = RAIZ / "data" / "salida"

FEATURES_ACTUALES = [
    "kg_ha",              # autoregresivo: el propio rendimiento de esta semana
    "edad_dias",
    "poda_dispersion_dias",
    "gdd_semana", "temp_media", "temp_max", "temp_min",
    "eto_semana_mm", "lluvia_semana_mm", "humedad_media",
    "gdd_acum_poda", "eto_acum_poda_mm", "lluvia_acum_poda_mm",
    "riego_mm", "riego_m3", "riego_dias_con_registro",
    "area_ha", "n_plantas",
]
ETIQUETAS = {
    "kg_ha": "kg/ha (esta semana)",
    "edad_dias": "Edad del fruto (días desde poda)",
    "poda_dispersion_dias": "Dispersión de la poda del módulo",
    "gdd_semana": "Grados-día de la semana (clima, igual en todo el fundo)",
    "temp_media": "Temperatura media de la semana",
    "temp_max": "Temperatura máxima de la semana",
    "temp_min": "Temperatura mínima de la semana",
    "eto_semana_mm": "ETO de la semana (clima, igual en todo el fundo)",
    "lluvia_semana_mm": "Lluvia de la semana (clima, igual en todo el fundo)",
    "humedad_media": "Humedad media de la semana",
    "gdd_acum_poda": "Grados-día acumulados desde la poda de ESTE módulo",
    "eto_acum_poda_mm": "ETO acumulada desde la poda de este módulo",
    "lluvia_acum_poda_mm": "Lluvia acumulada desde la poda de este módulo",
    "riego_mm": "Lámina de riego de la semana",
    "riego_m3": "Agua total aplicada en la semana",
    "riego_dias_con_registro": "Días con registro de riego esa semana",
    "area_ha": "Área del módulo",
    "n_plantas": "Plantas del módulo",
    "modulo_id": "Módulo (identidad)",
}


def env() -> dict[str, str]:
    valores = {}
    ruta = RAIZ / ".env"
    if ruta.exists():
        for linea in ruta.read_text(encoding="utf-8").splitlines():
            linea = linea.strip()
            if not linea or linea.startswith("#") or "=" not in linea:
                continue
            clave, _, valor = linea.partition("=")
            valores[clave.strip()] = valor.strip()
    for clave in ("PGHOST", "PGPORT", "PGDATABASE", "PGUSER", "PGPASSWORD"):
        if os.environ.get(clave):
            valores[clave] = os.environ[clave]
    return valores


def cargar_panel() -> pd.DataFrame:
    cfg = env()
    conn_str = (
        f"host={cfg.get('PGHOST', 'localhost')} port={cfg.get('PGPORT', '5432')} "
        f"dbname={cfg.get('PGDATABASE', 'aquanqa')} user={cfg.get('PGUSER', 'postgres')} "
        f"password={cfg.get('PGPASSWORD', '')}"
    )
    with psycopg.connect(conn_str) as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM reporting.v_analitica_modulo_semana")
        cols = [d.name for d in cur.description]
        df = pd.DataFrame(cur.fetchall(), columns=cols)

    # psycopg devuelve los numeric de Postgres como Decimal (dtype object en pandas);
    # XGBoost solo acepta int/float/category.
    for c in FEATURES_ACTUALES + ["riego_estimado"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def construir_pares_1_semana(panel: pd.DataFrame) -> pd.DataFrame:
    """Para cada módulo+campaña, empareja la semana t con la t+1 SOLO si son
    calendario-consecutivas (fin de t + 1 día = inicio de t+1). No rellena huecos."""
    p = panel.sort_values(["modulo_id", "campania", "semana_desde"]).copy()
    p["semana_desde"] = pd.to_datetime(p["semana_desde"])
    p["semana_hasta"] = pd.to_datetime(p["semana_hasta"])

    siguiente = p.groupby(["modulo_id", "campania"], group_keys=False).shift(-1)
    consecutiva = (siguiente["semana_desde"] - p["semana_hasta"]).dt.days == 1

    pares = p.loc[consecutiva, FEATURES_ACTUALES + ["modulo_id", "modulo", "fundo", "campania", "semana_desde"]].copy()
    pares["kg_ha_siguiente"] = siguiente.loc[consecutiva, "kg_ha"].to_numpy()
    return pares.reset_index(drop=True)


def main() -> int:
    print("Cargando panel...")
    panel = cargar_panel()
    print(f"  {len(panel)} filas, {panel['modulo_id'].nunique()} módulos")

    pares = construir_pares_1_semana(panel)
    print(f"Pares de semanas consecutivas (t -> t+1): {len(pares)} de {len(panel)} filas posibles")
    print(f"  descartadas por no ser consecutivas: {len(panel) - len(pares)}")

    X = pares[FEATURES_ACTUALES + ["modulo_id"]].copy()
    X["modulo_id"] = X["modulo_id"].astype("category")
    y = pares["kg_ha_siguiente"]

    # kg_ha está muy sesgado (mediana 548, media 808, máx > 7.000): un solo corte de
    # validación es sensible a qué outliers caen del lado de test. Se reporta la
    # validación honesta de dos formas independientes, no la que salga mejor:
    #
    # (a) Corte temporal simple: entrena con el pasado, valida con lo más reciente.
    corte = pares["semana_desde"].quantile(0.85)
    es_train = pares["semana_desde"] <= corte
    modelo_holdout = xgb.XGBRegressor(
        n_estimators=300, max_depth=4, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8,
        enable_categorical=True, random_state=42,
    )
    modelo_holdout.fit(X[es_train], y[es_train])
    pred_holdout = modelo_holdout.predict(X[~es_train])
    mae_holdout = mean_absolute_error(y[~es_train], pred_holdout)
    r2_holdout = r2_score(y[~es_train], pred_holdout)
    print(f"(a) Corte temporal hasta {corte.date()}: MAE={mae_holdout:.1f} kg/ha "
          f"(media real={y[~es_train].mean():.1f}), R2={r2_holdout:.3f} "
          f"({es_train.sum()} train / {(~es_train).sum()} valida)")

    # (b) 5-fold agrupado por campaña: cada campaña sale completa de train en algún
    # fold, así que ninguna semana "ve" su propia campaña — más estable que un solo
    # corte con pocas filas de validación.
    grupos = pares["campania"]
    gkf = GroupKFold(n_splits=min(5, grupos.nunique()))
    pred_cv = np.full(len(pares), np.nan)
    for tr_idx, te_idx in gkf.split(X, y, groups=grupos):
        m = xgb.XGBRegressor(
            n_estimators=300, max_depth=4, learning_rate=0.05,
            subsample=0.8, colsample_bytree=0.8,
            enable_categorical=True, random_state=42,
        )
        m.fit(X.iloc[tr_idx], y.iloc[tr_idx])
        pred_cv[te_idx] = m.predict(X.iloc[te_idx])
    mae_cv = mean_absolute_error(y, pred_cv)
    r2_cv = r2_score(y, pred_cv)
    print(f"(b) 5-fold agrupado por campaña: MAE={mae_cv:.1f} kg/ha, R2={r2_cv:.3f} "
          f"(cada fila valida en un modelo que nunca vio su campaña)")

    mae, r2, media_y = mae_cv, r2_cv, y.mean()

    # Para la explicación (SHAP) se reentrena con TODOS los datos: el objetivo aquí no
    # es desplegar el modelo, es explicar la relación con la mayor evidencia posible.
    # La métrica de arriba, calculada SOLO con el modelo de train, es la que certifica
    # que el modelo generaliza antes de confiar en su explicación.
    modelo_completo = xgb.XGBRegressor(
        n_estimators=300, max_depth=4, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8,
        enable_categorical=True, random_state=42,
    )
    modelo_completo.fit(X, y)

    explicador = shap.TreeExplainer(modelo_completo)
    shap_values = explicador(X)

    importancia = pd.DataFrame({
        "variable": X.columns,
        "etiqueta": [ETIQUETAS.get(c, c) for c in X.columns],
        "shap_medio_abs": np.abs(shap_values.values).mean(axis=0),
        "shap_medio_con_signo": shap_values.values.mean(axis=0),
    }).sort_values("shap_medio_abs", ascending=False)

    SALIDA.mkdir(parents=True, exist_ok=True)
    ruta_json = SALIDA / "shap_importancia_kg_ha.json"
    ruta_json.write_text(
        json.dumps(
            {
                "n_pares": len(pares),
                "validacion_a_corte_temporal": {
                    "n_train": int(es_train.sum()),
                    "n_valida": int((~es_train).sum()),
                    "corte": str(corte.date()),
                    "mae": round(float(mae_holdout), 2),
                    "r2": round(float(r2_holdout), 4),
                },
                "validacion_b_5fold_por_campania": {
                    "mae": round(float(mae_cv), 2),
                    "r2": round(float(r2_cv), 4),
                },
                "media_kg_ha": round(float(media_y), 2),
                "importancia": importancia.to_dict(orient="records"),
            },
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )
    print(f"OK  {ruta_json}")

    print("\nRanking de importancia (SHAP medio absoluto):")
    print(importancia.to_string(index=False))

    # Guardamos también los shap values crudos por fila, para el beeswarm si hace falta.
    np.save(SALIDA / "shap_values.npy", shap_values.values)
    X.to_csv(SALIDA / "shap_X.csv", index=False)
    pares[["kg_ha_siguiente"]].to_csv(SALIDA / "shap_y.csv", index=False)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
