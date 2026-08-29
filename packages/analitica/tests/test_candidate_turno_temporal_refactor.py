from __future__ import annotations

from analitica.proyeccion import candidate_turno_temporal as facade
from analitica.proyeccion.candidatos import turno_temporal_contratos as contratos
from analitica.proyeccion.candidatos import turno_temporal_nowcast as nowcast
from analitica.proyeccion.candidatos import turno_temporal_reingreso as reingreso
from analitica.proyeccion.candidatos import turno_temporal_validacion as validacion


def test_fachada_conserva_superficie_y_delega_sin_wrappers():
    assert facade.CLAVE_FORECAST is contratos.CLAVE_FORECAST
    assert facade.CLAVE_UNIVERSO is contratos.CLAVE_UNIVERSO
    assert facade.ConfiguracionTurnoTemporal is contratos.ConfiguracionTurnoTemporal
    assert facade.normalizar_forecast_candidate is validacion.normalizar_forecast_candidate
    assert facade.auditar_universo_candidate is validacion.auditar_universo_candidate
    assert facade.metricas_adversariales is validacion.metricas_adversariales
    assert (
        facade.estimar_desplazamiento_temporal_asof
        is reingreso.estimar_desplazamiento_temporal_asof
    )
    assert (
        facade.aplicar_turno_reingreso_candidate
        is reingreso.aplicar_turno_reingreso_candidate
    )
    assert facade.construir_nowcast_separado is nowcast.construir_nowcast_separado
    assert facade._semana_inicio is contratos._semana_inicio
