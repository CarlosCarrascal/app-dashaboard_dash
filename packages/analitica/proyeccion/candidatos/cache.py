"""Cache local y serialización reproducible del preflight."""

from __future__ import annotations

import gzip
import json
import pickle
from collections.abc import Callable, Mapping
from hashlib import sha256
from pathlib import Path
from typing import Any

import pandas as pd

from ..compartido import identidad as _identidad
from .contratos import CLAVES_EVALUACION

_limpio_json = _identidad._limpio_json
json_reproducible = _identidad.json_reproducible
sha256_dataframe = _identidad.sha256_dataframe


class CacheCandidate:
    """Cache local atomica; nunca altera fuentes ni tablas de analytics."""

    def __init__(self, raiz: str | Path | None):
        self.raiz = Path(raiz) if raiz else None

    def _rutas(self, clave: str) -> tuple[Path, Path]:
        assert self.raiz is not None
        return self.raiz / f"{clave}.pkl.gz", self.raiz / f"{clave}.json"

    def cargar(self, clave: str) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]] | None:
        if self.raiz is None:
            return None
        datos_path, meta_path = self._rutas(clave)
        if not datos_path.exists() or not meta_path.exists():
            return None
        try:
            with gzip.open(datos_path, "rb") as archivo:
                predicciones, snapshots = pickle.load(archivo)  # noqa: S301 - cache local propio
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            valido = meta.get("candidate_sha256") == sha256_dataframe(
                predicciones, [*CLAVES_EVALUACION, "modelo", "p50_kg", "real_kg"]
            )
        except (
            OSError,
            ValueError,
            TypeError,
            KeyError,
            AttributeError,
            EOFError,
            pickle.PickleError,
        ):
            return None
        if not valido:
            return None
        return predicciones, snapshots, meta

    def guardar(
        self,
        clave: str,
        predicciones: pd.DataFrame,
        snapshots: pd.DataFrame,
        meta: Mapping[str, Any],
    ) -> None:
        if self.raiz is None:
            return
        self.raiz.mkdir(parents=True, exist_ok=True)
        datos_path, meta_path = self._rutas(clave)
        datos_tmp = datos_path.with_suffix(datos_path.suffix + ".tmp")
        meta_tmp = meta_path.with_suffix(meta_path.suffix + ".tmp")
        metadatos = dict(meta)
        metadatos["candidate_sha256"] = sha256_dataframe(
            predicciones, [*CLAVES_EVALUACION, "modelo", "p50_kg", "real_kg"]
        )
        with gzip.open(datos_tmp, "wb", compresslevel=3) as archivo:
            pickle.dump((predicciones, snapshots), archivo, protocol=pickle.HIGHEST_PROTOCOL)
        meta_tmp.write_text(json_reproducible(metadatos), encoding="utf-8")
        datos_tmp.replace(datos_path)
        meta_tmp.replace(meta_path)


def clave_cache_candidate(configuracion: Mapping[str, Any]) -> str:
    return sha256(json_reproducible(configuracion).encode("utf-8")).hexdigest()


def escribir_json_reproducible(resultado: Mapping[str, Any], ruta: str | Path) -> None:
    destino = Path(ruta)
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporal = destino.with_suffix(destino.suffix + ".tmp")
    temporal.write_text(json_reproducible(resultado) + "\n", encoding="utf-8")
    temporal.replace(destino)


def obtener_o_construir_cache(
    cache: CacheCandidate,
    clave: str,
    constructor: Callable[[], tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]],
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    existente = cache.cargar(clave)
    if existente is not None:
        pred, snapshots, meta = existente
        return pred, snapshots, {**meta, "cache_hit": True}
    pred, snapshots, meta = constructor()
    cache.guardar(clave, pred, snapshots, meta)
    return pred, snapshots, {**meta, "cache_hit": False}


__all__ = [
    "CacheCandidate",
    "clave_cache_candidate",
    "escribir_json_reproducible",
    "json_reproducible",
    "obtener_o_construir_cache",
    "sha256_dataframe",
]
