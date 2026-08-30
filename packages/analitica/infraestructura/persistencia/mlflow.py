"""Tracking opcional de MLflow para artefactos y corridas analíticas."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime

import numpy as np
import pandas as pd

from analitica import settings
from analitica.infraestructura import commit_actual


@contextmanager
def tracking_mlflow(tipo: str, fuente, configuracion: dict):
    """Registra una corrida solo cuando existe una URI explícita de MLflow."""
    if not settings.MLFLOW_TRACKING_URI:
        yield None
        return
    try:
        import mlflow
    except ImportError:
        yield None
        return
    mlflow.set_tracking_uri(settings.MLFLOW_TRACKING_URI)
    mlflow.set_experiment("aquanqa-analytics")
    with mlflow.start_run(run_name=f"{tipo}-{datetime.now(UTC):%Y%m%dT%H%M%SZ}") as run:
        mlflow.set_tags(
            {
                "tipo": tipo,
                "fuente": fuente.nombre,
                "snapshot_firma": fuente.firma,
                "fallback": str(fuente.fallback).lower(),
                "codigo_commit": commit_actual() or "unknown",
            }
        )
        mlflow.log_params({k: str(v)[:250] for k, v in configuracion.items()})
        resumen_fuente = pd.DataFrame(
            {
                "tabla": list(fuente.conteos),
                "filas": list(fuente.conteos.values()),
                "snapshot_firma": fuente.firma,
            }
        )
        dataset = mlflow.data.from_pandas(
            resumen_fuente,
            name=f"snapshot-{fuente.firma[:12]}",
            digest=fuente.firma[:32],
        )
        mlflow.log_input(dataset, context=tipo)
        yield run.info.run_id


def log_metricas_mlflow(metricas: pd.DataFrame):
    try:
        import mlflow
    except ImportError:
        return
    if mlflow.active_run() is None:
        return
    for fila in metricas.itertuples(index=False):
        banda = str(fila.banda_horizonte).replace(" ", "_")
        modelo = str(fila.modelo).replace(" ", "_")
        for metrica in ("wape", "mae_kg", "sesgo_pct", "mase", "rmsse", "cobertura_80"):
            valor = getattr(fila, metrica, None)
            if valor is not None and np.isfinite(valor):
                mlflow.log_metric(f"{modelo}.{banda}.{metrica}", float(valor))


def registrar_modelos_mlflow(
    modelos: dict[str, tuple[object, pd.DataFrame, pd.Series]],
    decisiones: pd.DataFrame,
) -> dict[str, object]:
    """Registra modelos, firmas y alias dentro de una corrida MLflow activa."""
    try:
        import mlflow
        from mlflow.models import infer_signature
    except ImportError:
        return {"estado": "mlflow_no_instalado", "modelos": []}
    if mlflow.active_run() is None:
        return {"estado": "mlflow_no_configurado", "modelos": []}

    registros = []
    for nombre, (modelo, x, _y) in modelos.items():
        ejemplo = x.head(min(20, len(x)))
        prediccion = modelo.predict(ejemplo)
        firma = infer_signature(ejemplo, prediccion)
        nombre_registro = f"aquanqa-forecast-{nombre.lower().replace('_', '-')}"
        info = mlflow.sklearn.log_model(
            sk_model=modelo,
            name=f"modelo-{nombre.lower().replace('_', '-')}",
            registered_model_name=nombre_registro,
            signature=firma,
            input_example=ejemplo.head(5),
            tags={"rol": "challenger", "semantica": "correccion_residual_asof"},
        )
        version = getattr(info, "registered_model_version", None)
        es_campeon = bool((decisiones.campeon == nombre).any()) if not decisiones.empty else False
        alias = "champion" if es_campeon else "challenger"
        if version is not None:
            mlflow.MlflowClient().set_registered_model_alias(nombre_registro, alias, str(version))
        registros.append(
            {
                "modelo": nombre,
                "nombre_registro": nombre_registro,
                "version": version,
                "alias": alias,
                "model_uri": info.model_uri,
                "firma": firma.to_dict(),
            }
        )
    return {"estado": "registrado", "modelos": registros}


__all__ = [
    "log_metricas_mlflow",
    "registrar_modelos_mlflow",
    "tracking_mlflow",
]

__all__ = ["log_metricas_mlflow", "registrar_modelos_mlflow", "tracking_mlflow"]
