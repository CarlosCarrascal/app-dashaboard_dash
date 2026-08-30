"""Calendario de cosecha estimado con ceros históricos explícitos.

R09 solo contiene semanas para las que el equipo publicó fruta. Para no convertir esa lista
en una verdad del modelo nuevo, este módulo construye una rejilla lote-emisión-semana y marca
como cero las semanas sin ``real_kg`` observado. La clasificación se entrena únicamente con
objetivos anteriores a la emisión que se está reconstruyendo.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from analitica.dominio.modelos.componentes import FEATURES_CLIMA_ASOF, FEATURES_COMUNES

FEATURES_OCURRENCIA = [
    *FEATURES_COMUNES,
    *FEATURES_CLIMA_ASOF,
    "flores",
    "cuajo",
    "tasa_cuajo_observada",
    "frutos_muestra",
    "indice_estado",
    "prop_e1",
    "prop_e2",
    "prop_e3",
    "prop_e4",
    "prop_e5",
    "semanas_desde_ultima_cosecha",
]


@dataclass(frozen=True)
class OccurrenceConfig:
    umbral: float = 0.5
    minimo_entrenamiento: int = 100

    def __post_init__(self) -> None:
        if not 0 < self.umbral < 1:
            raise ValueError("umbral de ocurrencia debe estar entre 0 y 1")
        if self.minimo_entrenamiento < 20:
            raise ValueError("minimo_entrenamiento de ocurrencia debe ser al menos 20")


def _semanas(fecha: pd.Timestamp, horizonte: int) -> pd.DatetimeIndex:
    return pd.date_range(fecha + pd.Timedelta(weeks=1), periods=horizonte, freq="W-MON")


def _calendario_por_lote(
    base: pd.DataFrame,
    *,
    emisiones: pd.DataFrame,
    horizonte: int,
) -> pd.DataFrame:
    """Expande una fila representante por lote-emisión a todas sus semanas posibles."""

    identidad = ["campania", "lote_id", "fecha_emision"]
    representantes = (
        emisiones.sort_values([*identidad, "fecha_objetivo"]).drop_duplicates(identidad).copy()
    )
    filas = []
    for fila in representantes.itertuples(index=False):
        datos = fila._asdict()
        fecha_emision = pd.Timestamp(datos["fecha_emision"])
        for horizonte_semana, fecha_objetivo in enumerate(
            _semanas(fecha_emision, horizonte), start=1
        ):
            fila_nueva = datos.copy()
            fila_nueva["fecha_objetivo"] = fecha_objetivo
            fila_nueva["horizonte_semanas"] = horizonte_semana
            fila_nueva["banda_horizonte"] = (
                "operativo"
                if horizonte_semana <= 2
                else "planificacion"
                if horizonte_semana <= 6
                else "escenario"
            )
            fila_nueva["version_fuente"] = "rejilla_ocurrencia_asof"
            fila_nueva["p50_kg"] = np.nan
            fila_nueva["p10_kg"] = np.nan
            fila_nueva["p90_kg"] = np.nan
            fila_nueva["real_kg"] = np.nan
            filas.append(fila_nueva)
    calendario = pd.DataFrame(filas)
    if calendario.empty:
        return calendario

    reales = (
        base.dropna(subset=["real_kg"])
        .groupby(["campania", "lote_id", "fecha_objetivo"], as_index=False)["real_kg"]
        .max()
    )
    calendario = calendario.drop(columns=["real_kg"], errors="ignore").merge(
        reales,
        on=["campania", "lote_id", "fecha_objetivo"],
        how="left",
    )
    calendario["real_kg"] = calendario.real_kg.fillna(0.0)
    return calendario


def construir_rejilla_ocurrencia(
    r09: pd.DataFrame,
    *,
    emision: pd.Timestamp,
    horizonte: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Devuelve entrenamiento histórico y grilla futura para una emisión."""

    base = r09[r09.modelo == "R09_publicado"].copy()
    base["fecha_emision"] = pd.to_datetime(base.fecha_emision).dt.normalize()
    base["fecha_objetivo"] = pd.to_datetime(base.fecha_objetivo).dt.normalize()
    anteriores = base[base.fecha_emision < emision].copy()
    actual = base[base.fecha_emision == emision].copy()
    if anteriores.empty or actual.empty:
        return pd.DataFrame(), pd.DataFrame()
    entrenamiento = _calendario_por_lote(base, emisiones=anteriores, horizonte=horizonte)
    entrenamiento = entrenamiento[entrenamiento.fecha_objetivo < emision].copy()
    futuro = _calendario_por_lote(base, emisiones=actual, horizonte=horizonte)
    futuro["real_kg"] = np.nan
    # El futuro puede solaparse con filas R09 publicadas. El nuevo modelo usa una fila por
    # lote-semana y no conserva la lista de R09 como gate.
    return entrenamiento, futuro


def _preparar_features(tabla: pd.DataFrame, columnas: list[str]) -> tuple[pd.DataFrame, list[str]]:
    salida = tabla.copy()
    semana = pd.to_datetime(salida.fecha_objetivo).dt.isocalendar().week.astype(float)
    salida["semana_objetivo_sin"] = np.sin(2 * np.pi * semana / 52.18)
    salida["semana_objetivo_cos"] = np.cos(2 * np.pi * semana / 52.18)
    disponibles = [c for c in columnas if c in salida]
    disponibles = [c for c in disponibles if salida[c].notna().mean() >= 0.60]
    if not disponibles:
        return pd.DataFrame(index=salida.index), []
    marcas = []
    for columna in disponibles:
        if salida[columna].isna().any():
            marca = f"{columna}_faltante"
            salida[marca] = salida[columna].isna().astype(float)
            marcas.append(marca)
    return salida, [*disponibles, *marcas]


def estimar_ocurrencia(
    entrenamiento: pd.DataFrame,
    futuro: pd.DataFrame,
    *,
    panel_asof: pd.DataFrame | None = None,
    config: OccurrenceConfig | None = None,
) -> pd.DataFrame:
    """Estima probabilidad de cosecha para las semanas futuras de la rejilla."""

    config = config or OccurrenceConfig()
    if entrenamiento.empty or futuro.empty:
        raise ValueError("La rejilla de ocurrencia no tiene entrenamiento o futuro.")
    claves = ["campania", "lote_id", "fecha_emision"]
    if panel_asof is not None and not panel_asof.empty and set(claves) <= set(panel_asof):
        extras = [c for c in panel_asof.columns if c not in entrenamiento.columns or c in claves]
        panel = panel_asof[extras].drop_duplicates(claves)
        entrenamiento = entrenamiento.merge(panel, on=claves, how="left", validate="m:1")
        futuro = futuro.merge(panel, on=claves, how="left", validate="m:1")
    entrenamiento = entrenamiento.copy()
    futuro = futuro.copy()
    entrenamiento["activa"] = (pd.to_numeric(entrenamiento.real_kg, errors="coerce") > 0).astype(
        int
    )
    entrenamiento, columnas = _preparar_features(entrenamiento, FEATURES_OCURRENCIA)
    futuro, _ = _preparar_features(futuro, columnas)
    if len(entrenamiento) < config.minimo_entrenamiento or not columnas:
        raise ValueError("Historia insuficiente para el modelo de ocurrencia.")

    from sklearn.ensemble import RandomForestClassifier

    medianas = entrenamiento[columnas].median(numeric_only=True).fillna(0)
    x_train = entrenamiento[columnas].apply(pd.to_numeric, errors="coerce").fillna(medianas)
    x_futuro = (
        futuro.reindex(columns=columnas).apply(pd.to_numeric, errors="coerce").fillna(medianas)
    )
    y = entrenamiento.activa.to_numpy(int)
    if np.unique(y).size < 2:
        probabilidad = np.full(len(futuro), float(y.mean()))
    else:
        modelo = RandomForestClassifier(
            n_estimators=160,
            max_depth=8,
            min_samples_leaf=12,
            class_weight="balanced",
            random_state=42,
            n_jobs=1,
        )
        modelo.fit(x_train, y)
        probabilidad = modelo.predict_proba(x_futuro)[:, 1]
    salida = futuro.copy()
    salida["probabilidad_cosecha"] = np.clip(probabilidad, 0, 1)
    salida["ocurrencia_gate"] = salida.probabilidad_cosecha >= config.umbral
    salida["variables_ocurrencia"] = [list(columnas) for _ in range(len(salida))]
    return salida
