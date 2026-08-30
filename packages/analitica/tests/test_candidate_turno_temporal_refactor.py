from __future__ import annotations

from analitica.aplicacion.procesos.candidatos import (
    ConfiguracionTurnoTemporal,
    aplicar_turno_reingreso_candidate,
    auditar_universo_candidate,
    construir_nowcast_separado,
    estimar_desplazamiento_temporal_asof,
    metricas_adversariales,
    normalizar_forecast_candidate,
)
from analitica.aplicacion.procesos.candidatos import (
    turno_temporal_contratos as contratos,
)
from analitica.aplicacion.procesos.candidatos import (
    turno_temporal_nowcast as nowcast,
)
from analitica.aplicacion.procesos.candidatos import (
    turno_temporal_reingreso as reingreso,
)
from analitica.aplicacion.procesos.candidatos import (
    turno_temporal_validacion as validacion,
)


def test_api_de_turno_temporal_apunta_a_las_implementaciones_canonicas():
    assert contratos.CLAVE_FORECAST
    assert contratos.CLAVE_UNIVERSO
    assert ConfiguracionTurnoTemporal is contratos.ConfiguracionTurnoTemporal
    assert normalizar_forecast_candidate is validacion.normalizar_forecast_candidate
    assert auditar_universo_candidate is validacion.auditar_universo_candidate
    assert metricas_adversariales is validacion.metricas_adversariales
    assert (
        estimar_desplazamiento_temporal_asof
        is reingreso.estimar_desplazamiento_temporal_asof
    )
    assert (
        aplicar_turno_reingreso_candidate
        is reingreso.aplicar_turno_reingreso_candidate
    )
    assert construir_nowcast_separado is nowcast.construir_nowcast_separado
    assert contratos._semana_inicio
