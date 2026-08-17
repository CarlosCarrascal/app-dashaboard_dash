"""Caché de cálculos de páginas sobre el panel cargado.

Las páginas Dash se vuelven a montar al navegar y sus callbacks se ejecutan otra vez.
Este módulo conserva los resultados por huella del panel y, cuando conviene, los prepara
en segundo plano al entrar en una página. El callback que llegue antes al resultado espera
la misma tarea; nunca crea un segundo entrenamiento para la misma lectura.
"""

from __future__ import annotations

import hashlib
import logging
import os
import pickle
from collections.abc import Callable, Mapping
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import suppress
from pathlib import Path
from threading import Lock, get_ident

import pandas as pd

_LOGGER = logging.getLogger(__name__)

# XGBoost ya usa un hilo por ajuste. Ejecutar tres validaciones pesadas a la vez hace que
# todas tarden más y bloquea la primera pestaña que el usuario quiere leer; una cola única
# deja lista cada lectura en orden y evita competir por CPU en Render.
_POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix="aquanqa-analisis")
_CACHE: dict[tuple[str, str], object] = {}
_FUTURES: dict[tuple[str, str], Future] = {}
_LOCK = Lock()
_CACHE_VERSION = "v2"
_CACHE_DIR = Path(
    os.environ.get(
        "AQUANQA_ANALYSIS_CACHE_DIR",
        Path(__file__).resolve().parents[1] / ".cache" / "analisis",
    )
)
_CACHE_DIR.mkdir(parents=True, exist_ok=True)
_MISSING = object()


def panel_key(panel) -> str:
    """Huella estable para no mezclar cálculos entre paneles distintos."""
    # El `Panel` vive en el backend Serverside y su tabla no se modifica después de la
    # carga. Recalcular el hash de todas las columnas en cada callback era trabajo puro de
    # navegación; conservarlo en el propio objeto vuelve O(1) cada consulta posterior.
    existente = getattr(panel, "_aquanqa_analysis_key", None)
    if existente is not None:
        return existente
    tabla = panel.tabla
    # Los rezagos y las trayectorias usan también clima, riego, poda y floración. Hashar
    # solo KgHa/Frutos/Peso podía reutilizar un resultado viejo si cambiaba una exposición
    # climática manteniendo iguales los objetivos.
    serie = pd.util.hash_pandas_object(tabla, index=True)
    metadata = repr((tuple(tabla.columns), tuple(map(str, tabla.dtypes)), tabla.shape)).encode()
    hasher = hashlib.blake2b(digest_size=16)
    hasher.update(metadata)
    hasher.update(serie.to_numpy().tobytes())
    huella = hasher.hexdigest()
    clave = f"{tabla.shape}:{huella}"
    panel._aquanqa_analysis_key = clave
    return clave


def _ruta_disco(clave: tuple[str, str]) -> Path:
    """Ruta segura y versionada para un resultado analítico serializado."""
    panel, nombre = clave
    nombre_hash = hashlib.blake2b(nombre.encode("utf-8"), digest_size=12).hexdigest()
    panel_hash = hashlib.blake2b(panel.encode("utf-8"), digest_size=16).hexdigest()
    return _CACHE_DIR / f"{_CACHE_VERSION}-{panel_hash}-{nombre_hash}.pkl"


def _leer_disco(clave: tuple[str, str]):
    ruta = _ruta_disco(clave)
    if not ruta.is_file():
        return _MISSING
    try:
        with ruta.open("rb") as archivo:
            return pickle.load(archivo)
    except Exception:  # pragma: no cover - recuperación de caché local dañada
        _LOGGER.warning("Se descarta una entrada de caché dañada: %s", ruta, exc_info=True)
        with suppress(OSError):
            ruta.unlink()
        return _MISSING


def _guardar_disco(clave: tuple[str, str], resultado) -> None:
    """Guarda atómicamente para no dejar un pickle a medias si el proceso se reinicia."""
    ruta = _ruta_disco(clave)
    temporal = ruta.with_suffix(f".{os.getpid()}.{get_ident()}.tmp")
    try:
        with temporal.open("wb") as archivo:
            pickle.dump(resultado, archivo, protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(temporal, ruta)
    except Exception:  # pragma: no cover - la caché nunca debe tumbar la interfaz
        _LOGGER.warning("No se pudo persistir la caché analítica: %s", ruta, exc_info=True)
        with suppress(OSError):
            temporal.unlink()


def _terminar_futuro(clave: tuple[str, str], futuro: Future) -> None:
    try:
        resultado = futuro.result()
    except Exception:
        with _LOCK:
            _FUTURES.pop(clave, None)
        return
    with _LOCK:
        _CACHE[clave] = resultado
        _FUTURES.pop(clave, None)
    _guardar_disco(clave, resultado)


def _future(
    panel, nombre: str, builder: Callable[[], object]
) -> tuple[tuple[str, str], Future | None]:
    clave = (panel_key(panel), nombre)
    nuevo = False
    with _LOCK:
        if clave in _CACHE:
            return clave, None
        futuro = _FUTURES.get(clave)
        if futuro is None:
            resultado = _leer_disco(clave)
            if resultado is not _MISSING:
                _CACHE[clave] = resultado
                return clave, None
            futuro = _POOL.submit(builder)
            _FUTURES[clave] = futuro
            nuevo = True
    # Se registra fuera del lock: si el worker termina antes de esta línea, Future puede
    # ejecutar el callback inmediatamente en el hilo actual.
    if nuevo:
        futuro.add_done_callback(lambda terminado: _terminar_futuro(clave, terminado))
    return clave, futuro


def precargar(panel, tareas: Mapping[str, Callable[[], object]]) -> None:
    """Programa lecturas independientes sin bloquear el callback de la página."""
    for nombre, builder in tareas.items():
        _future(panel, nombre, builder)


def obtener(panel, nombre: str, builder: Callable[[], object]):
    """Devuelve un resultado cacheado, esperando la tarea única si sigue en curso."""
    clave, futuro = _future(panel, nombre, builder)
    with _LOCK:
        if clave in _CACHE:
            return _CACHE[clave]

    try:
        resultado = futuro.result()
    except Exception:
        with _LOCK:
            _FUTURES.pop(clave, None)
        raise

    with _LOCK:
        _CACHE[clave] = resultado
        _FUTURES.pop(clave, None)
    return resultado
