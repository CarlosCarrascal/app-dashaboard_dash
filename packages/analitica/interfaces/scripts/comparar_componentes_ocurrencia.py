from __future__ import annotations

import argparse

import numpy as np
import pandas as pd
import psycopg

from analitica import settings


def main() -> None:
    argparse.ArgumentParser(description=__doc__).parse_args()
    with psycopg.connect(settings.postgres_dsn()) as conexion:
        tabla = pd.read_sql_query(
            """
            SELECT modelo, fecha_objetivo, real_kg, p50_kg, componentes
            FROM analytics.prediction
            WHERE run_id = 79 AND campania = 'C2026'
              AND modelo IN ('MacroLegacy_v1', 'HibridoOcurrenciaOnline_v2')
            """,
            conexion,
        )
    tabla["fecha_objetivo"] = pd.to_datetime(tabla["fecha_objetivo"])
    tabla["real_kg"] = pd.to_numeric(tabla["real_kg"], errors="coerce").fillna(0.0)
    tabla["p50_kg"] = pd.to_numeric(tabla["p50_kg"], errors="coerce").fillna(0.0)
    semanal = tabla.groupby(["modelo", "fecha_objetivo"], as_index=False).agg(
        real=("real_kg", "sum"), pred=("p50_kg", "sum")
    )
    piv = semanal.pivot(index="fecha_objetivo", columns="modelo", values="pred").reset_index()
    reales = semanal.groupby("fecha_objetivo", as_index=False).real.first()
    piv = reales.merge(piv, on="fecha_objetivo", how="left")
    piv["error_macro"] = piv["MacroLegacy_v1"] - piv.real
    piv["error_v2"] = piv["HibridoOcurrenciaOnline_v2"] - piv.real
    piv["abs_macro"] = piv.error_macro.abs()
    piv["abs_v2"] = piv.error_v2.abs()
    print(piv.to_string(index=False))
    # Prueba aislada de balance de masa: solo real y predicción de semanas
    # anteriores, con shrinkage hacia factor 1.
    piv = piv.sort_values("fecha_objetivo").reset_index(drop=True)
    factores = []
    for i, _fila in piv.iterrows():
        prev = piv.iloc[:i]
        if len(prev) < 4 or prev["HibridoOcurrenciaOnline_v2"].sum() <= 0:
            factores.append(1.0)
            continue
        crudo = prev.real.sum() / prev["HibridoOcurrenciaOnline_v2"].sum()
        factor = (len(prev) * crudo + 4.0) / (len(prev) + 4.0)
        factores.append(float(np.clip(factor, 0.75, 1.40)))
    piv["factor_balance"] = factores
    piv["v2_balance"] = piv["HibridoOcurrenciaOnline_v2"] * piv.factor_balance
    print("\nBALANCE V2", abs(piv.v2_balance - piv.real).sum() / abs(piv.real).sum())


if __name__ == "__main__":
    main()
