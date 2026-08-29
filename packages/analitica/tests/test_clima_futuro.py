from __future__ import annotations

import json

import pandas as pd

from analitica.proyeccion.clima_futuro import (
    AdaptadorOpenMeteo,
    resolver_horizonte_climatico,
)


def _payload() -> bytes:
    daily = {
        "time": ["2026-08-21", "2026-08-22"],
        "temperature_2m_mean": [19.0, 20.0],
        "temperature_2m_max": [25.0, 26.0],
        "temperature_2m_min": [13.0, 14.0],
        "relative_humidity_2m_mean": [70.0, 68.0],
        "et0_fao_evapotranspiration": [3.1, 3.3],
        "shortwave_radiation_sum": [18.0, 19.0],
        "precipitation_sum": [0.0, 0.2],
    }
    return json.dumps({"latitude": -8.1, "longitude": -79.0, "daily": daily}).encode()


def test_open_meteo_guarda_payload_hash_y_deriva_dpv_sin_red():
    urls = []

    def transporte(url: str) -> bytes:
        urls.append(url)
        return _payload()

    pronostico = AdaptadorOpenMeteo(transport=transporte).obtener(
        latitud=-8.1, longitud=-79.0, dias=2
    )
    assert urls and "forecast_days=2" in urls[0]
    assert len(pronostico.payload_sha256) == 64
    assert pronostico.diario.dpv_kpa.gt(0).all()
    assert set(pronostico.diario.fuente_clima_futuro) == {"open_meteo"}


def test_horizonte_sin_forecast_no_se_rellena_silenciosamente():
    pronostico = AdaptadorOpenMeteo(transport=lambda _: _payload()).obtener(
        latitud=-8.1, longitud=-79.0, dias=2
    )
    fechas = pd.Series(pd.to_datetime(["2026-08-21", "2026-09-15"]))
    salida = resolver_horizonte_climatico(fechas, pronostico)
    assert salida.loc[
        salida.fecha_objetivo.eq(pd.Timestamp("2026-08-21")),
        "clima_futuro_disponible",
    ].item()
    assert not salida.loc[
        salida.fecha_objetivo.eq(pd.Timestamp("2026-09-15")), "clima_futuro_disponible"
    ].item()


def test_climatologia_se_identifica_como_escenario_no_como_pronostico():
    pronostico = AdaptadorOpenMeteo(transport=lambda _: _payload()).obtener(
        latitud=-8.1, longitud=-79.0, dias=2
    )
    climatologia = pd.DataFrame(
        {"dia_anio": [258], "temperature_2m_mean": [18.5], "dpv_kpa": [0.7]}
    )
    salida = resolver_horizonte_climatico(
        pd.Series(pd.to_datetime(["2026-09-15"])), pronostico, climatologia
    )
    assert salida.fuente_clima_futuro.item() == "climatologia"
    assert salida.clima_futuro_disponible.item()
