"""Adaptador reemplazable de clima futuro con trazabilidad del payload.

Open-Meteo se consulta solo cuando la operación entrega coordenadas. El resultado no se
rellena silenciosamente más allá de su horizonte: las semanas no cubiertas quedan marcadas
para que el llamador elija climatología, año análogo o un escenario manual.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlencode
from urllib.request import urlopen

import numpy as np
import pandas as pd

ENDPOINT_OPEN_METEO = "https://api.open-meteo.com/v1/forecast"
VARIABLES_DIARIAS = (
    "temperature_2m_mean",
    "temperature_2m_max",
    "temperature_2m_min",
    "relative_humidity_2m_mean",
    "et0_fao_evapotranspiration",
    "shortwave_radiation_sum",
    "precipitation_sum",
)


@dataclass(frozen=True)
class PronosticoClima:
    proveedor: str
    endpoint: str
    latitud: float
    longitud: float
    emitido_en: datetime
    payload: dict
    payload_sha256: str
    diario: pd.DataFrame


class AdaptadorOpenMeteo:
    """Cliente mínimo; ``transport`` permite pruebas sin red y reemplazar el proveedor."""

    def __init__(
        self,
        *,
        endpoint: str = ENDPOINT_OPEN_METEO,
        transport: Callable[[str], bytes] | None = None,
    ) -> None:
        self.endpoint = endpoint
        self.transport = transport or self._descargar

    @staticmethod
    def _descargar(url: str) -> bytes:
        with urlopen(url, timeout=20) as respuesta:  # noqa: S310 - endpoint HTTPS configurable
            return respuesta.read()

    def obtener(
        self,
        *,
        latitud: float,
        longitud: float,
        emitido_en: datetime | None = None,
        zona_horaria: str = "America/Lima",
        dias: int = 16,
    ) -> PronosticoClima:
        if not -90 <= latitud <= 90 or not -180 <= longitud <= 180:
            raise ValueError("Coordenadas fuera de rango")
        if not 1 <= dias <= 16:
            raise ValueError("Open-Meteo admite aquí entre 1 y 16 días de forecast")
        parametros = {
            "latitude": latitud,
            "longitude": longitud,
            "daily": ",".join(VARIABLES_DIARIAS),
            "timezone": zona_horaria,
            "forecast_days": dias,
        }
        url = f"{self.endpoint}?{urlencode(parametros)}"
        bruto = self.transport(url)
        payload = json.loads(bruto.decode("utf-8"))
        diario = payload.get("daily")
        if not isinstance(diario, dict) or "time" not in diario:
            raise ValueError("Open-Meteo no devolvió el bloque daily esperado")
        tamanio = len(diario["time"])
        columnas = {"fecha": pd.to_datetime(diario["time"], errors="coerce")}
        for variable in VARIABLES_DIARIAS:
            valores = diario.get(variable)
            if not isinstance(valores, list) or len(valores) != tamanio:
                columnas[variable] = np.full(tamanio, np.nan)
            else:
                columnas[variable] = pd.to_numeric(pd.Series(valores), errors="coerce")
        tabla = pd.DataFrame(columnas)
        presion = 0.6108 * np.exp(
            17.27 * tabla.temperature_2m_mean / (tabla.temperature_2m_mean + 237.3)
        )
        tabla["dpv_kpa"] = presion * (1 - tabla.relative_humidity_2m_mean / 100).clip(lower=0)
        tabla["fuente_clima_futuro"] = "open_meteo"
        return PronosticoClima(
            proveedor="open_meteo",
            endpoint=self.endpoint,
            latitud=float(latitud),
            longitud=float(longitud),
            emitido_en=emitido_en or datetime.now(UTC),
            payload=payload,
            payload_sha256=hashlib.sha256(bruto).hexdigest(),
            diario=tabla,
        )


def resolver_horizonte_climatico(
    fechas_objetivo: pd.Series,
    pronostico: PronosticoClima,
    climatologia: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Usa forecast donde existe y climatología explícita para el resto del horizonte."""

    salida = pd.DataFrame(
        {"fecha_objetivo": pd.to_datetime(fechas_objetivo, errors="coerce").dt.normalize()}
    ).drop_duplicates()
    pron = pronostico.diario.rename(columns={"fecha": "fecha_objetivo"})
    salida = salida.merge(pron, on="fecha_objetivo", how="left", validate="1:1")
    faltan = salida.fuente_clima_futuro.isna()
    if faltan.any() and climatologia is not None and not climatologia.empty:
        clima = climatologia.copy()
        if "dia_anio" not in clima:
            if "fecha" not in clima:
                raise ValueError("La climatología necesita fecha o dia_anio")
            clima["dia_anio"] = pd.to_datetime(clima.fecha).dt.dayofyear
        clima = clima.drop_duplicates("dia_anio")
        salida["dia_anio"] = salida.fecha_objetivo.dt.dayofyear
        columnas = [c for c in clima if c not in {"fecha", "dia_anio"}]
        salida = salida.merge(
            clima[["dia_anio", *columnas]],
            on="dia_anio",
            how="left",
            suffixes=("", "_climatologia"),
            validate="m:1",
        )
        for columna in columnas:
            alternativa = f"{columna}_climatologia"
            if alternativa in salida:
                salida[columna] = salida[columna].fillna(salida[alternativa])
        cobertura = columnas[0] if columnas else None
        usar = faltan & (salida[cobertura].notna() if cobertura else False)
        salida.loc[usar, "fuente_clima_futuro"] = "climatologia"
    salida["clima_futuro_disponible"] = salida.fuente_clima_futuro.notna()
    salida["payload_sha256"] = pronostico.payload_sha256
    return salida.drop(columns=["dia_anio"], errors="ignore")
