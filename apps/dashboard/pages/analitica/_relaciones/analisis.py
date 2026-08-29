"""Consolidación de los dos barridos en una sola tabla de hallazgos.

El barrido produce una fila por (predictor, respuesta, desfase). Para leerlo hace falta lo
contrario: una fila por par, con el desfase de mayor efecto y cuántos desfases contiguos lo
respaldan. Tres desfases del mismo par son un hallazgo, no tres.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .formato import grupo_objetivo
from .textos import CLIMA, RIEGO

# Un hallazgo es sólido cuando tiene respaldo suficiente en semanas y se mantiene en varios
# desfases contiguos. Lo demás es hipótesis: sirve para decidir qué medir, no para actuar.
SEMANAS_SOLIDO = 40
DESFASES_SOLIDO = 3

# De qué panel sale cada barrido y con qué grano se estimó por defecto.
ORIGENES = (
    ("matriz", "lote × semana", "fenologia"),
    ("packing", "módulo × semana", "packing"),
)


def unidad_del_par(predictor: str, unidad_panel: str) -> str:
    """La unidad efectiva la fija el predictor, no el panel del que sale la fila.

    Un cruce climático dentro del panel de lotes sigue teniendo una sola estación detrás:
    declararlo «lote × semana» sugeriría miles de observaciones independientes cuando todos
    los lotes de una misma semana comparten exactamente el mismo dato.
    """
    if predictor in CLIMA:
        return "semana (clima común a los 5 fundos)"
    if predictor in RIEGO:
        return "módulo × semana"
    return unidad_panel


def hallazgos(estado) -> pd.DataFrame:
    """Una fila por par superviviente, con su nivel de respaldo declarado."""
    partes = []
    for clave, unidad, bloque in ORIGENES:
        tabla = estado.get(clave)
        if tabla is None or tabla.empty or "sobrevive" not in tabla:
            continue
        vivos = tabla[tabla.sobrevive].copy()
        if vivos.empty:
            continue
        vivos["magnitud"] = vivos.correlacion_parcial.abs()
        mejores = vivos.sort_values("magnitud").groupby(["predictor", "respuesta"]).tail(1)
        respaldo = (
            vivos.groupby(["predictor", "respuesta"])
            .rezago_semanas.size()
            .rename("desfases_que_sobreviven")
        )
        mejores = mejores.merge(respaldo, on=["predictor", "respuesta"])
        mejores["unidad_analisis"] = mejores.predictor.map(lambda p, u=unidad: unidad_del_par(p, u))
        mejores["bloque"] = bloque
        partes.append(mejores)
    if not partes:
        return pd.DataFrame()
    todos = pd.concat(partes, ignore_index=True, sort=False)
    todos["nivel"] = (
        (todos.n_efectivo >= SEMANAS_SOLIDO) & (todos.desfases_que_sobreviven >= DESFASES_SOLIDO)
    ).map({True: "solido", False: "hipotesis"})
    if "componente" not in todos:
        todos["componente"] = todos.respuesta.map(grupo_objetivo)
    todos["componente"] = todos.componente.fillna(todos.respuesta.map(grupo_objetivo))
    # Una corrida anterior a la traducción a unidades reales no trae estas columnas. Se
    # declaran vacías para que la página siga abriendo con lo que sí tenga.
    for columna in ("efecto_rango_iqr", "iqr_predictor", "mediana_respuesta"):
        if columna not in todos:
            todos[columna] = np.nan
    return todos.sort_values(["nivel", "magnitud"], ascending=[True, False])


@dataclass(frozen=True)
class Barrido:
    """Recuento del filtrado, que es lo que permite juzgar si lo hallado es señal."""

    pruebas: int
    pares: int
    sin_corregir: int
    tras_placebo: int
    placebo: int
    supervivientes: int
    pares_supervivientes: int = 0

    @property
    def esperados_por_azar(self) -> int:
        return round(0.05 * self.pruebas)

    @property
    def hay_datos(self) -> bool:
        return self.pruebas > 0


def resumen_barrido(estado) -> Barrido:
    pruebas = pares = sin_corregir = tras_placebo = placebo = supervivientes = 0
    pares_vivos: set[tuple[str, str]] = set()
    for clave, _, _ in ORIGENES:
        tabla = estado.get(clave)
        if tabla is None or tabla.empty:
            continue
        crudas = tabla.p_pearson < 0.05
        pruebas += len(tabla)
        pares += tabla.groupby(["predictor", "respuesta"]).ngroups
        sin_corregir += int(crudas.sum())
        tras_placebo += int((crudas & ~tabla.placebo_supera_estimacion).sum())
        placebo += int(tabla.placebo_supera_estimacion.sum())
        supervivientes += int(tabla.sobrevive.sum())
        if {"predictor", "respuesta", "sobrevive"} <= set(tabla.columns):
            pares_vivos.update(
                tabla.loc[tabla.sobrevive, ["predictor", "respuesta"]]
                .drop_duplicates()
                .itertuples(index=False, name=None)
            )
    return Barrido(
        pruebas, pares, sin_corregir, tras_placebo, placebo, supervivientes, len(pares_vivos)
    )


def matriz_completa(estado) -> pd.DataFrame:
    """Los dos barridos apilados, sin consolidar: una fila por desfase probado."""
    partes = [
        estado[clave].assign(bloque=bloque)
        for clave, _, bloque in ORIGENES
        if not (estado.get(clave) is None or estado[clave].empty)
    ]
    return pd.concat(partes, ignore_index=True, sort=False) if partes else pd.DataFrame()
