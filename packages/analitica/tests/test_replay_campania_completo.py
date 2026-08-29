from __future__ import annotations

import inspect
from types import SimpleNamespace

import pandas as pd
import pytest

from analitica.scripts import replay_campania_completo as facade
from analitica.servicios import persistir_replay_campania as persistir_replay
from analitica.servicios import replay_campania_completo as service


def _datos_sinteticos() -> SimpleNamespace:
    return SimpleNamespace(
        cosecha=pd.DataFrame(
            {
                "campania": ["C2025", "C2025"],
                "fecha": pd.to_datetime(["2025-01-12", "2025-01-19"]),
            }
        )
    )


def _macro_sintetico() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "campania": ["C2025", "C2025"],
            "lote_id": [101, 101],
            "fecha_emision": pd.to_datetime(["2025-01-06", "2025-01-13"]),
            "fecha_objetivo": pd.to_datetime(["2025-01-13", "2025-01-20"]),
            "real_kg": [100.0, 120.0],
            "p50_kg": [95.0, 115.0],
        }
    )


def _preparar_construccion(monkeypatch: pytest.MonkeyPatch) -> None:
    macro = _macro_sintetico()
    monkeypatch.setattr(service, "cargar_datos", lambda _fuente: _datos_sinteticos())
    monkeypatch.setattr(
        service,
        "emisiones_completas",
        lambda _datos, campania, max_targets: pd.DataFrame(
            {
                "campania": [campania],
                "fecha_emision": pd.to_datetime(["2025-01-06"]),
            }
        ).iloc[:max_targets],
    )
    monkeypatch.setattr(
        service,
        "backtest_macro_legacy_v1",
        lambda *_args, **_kwargs: (macro.copy(), ["advertencia-sintetica"]),
    )
    monkeypatch.setattr(
        service,
        "ejecutar_replay_hibrido_ocurrencia_v2",
        lambda tabla: (
            tabla.assign(modelo=service.MODELO_V2, p50_kg=tabla["p50_kg"] + 2),
            pd.DataFrame(),
        ),
    )
    monkeypatch.setattr(
        service,
        "ejecutar_replay_hibrido_ocurrencia",
        lambda tabla: (
            tabla[["campania", "lote_id", "fecha_objetivo", "p50_kg"]].assign(
                p50_kg=lambda frame: frame["p50_kg"] + 1,
                confianza="media",
            ),
            [],
        ),
    )
    monkeypatch.setattr(service, "_leer_anterior", lambda *_args: pd.DataFrame())
    monkeypatch.setattr(
        service,
        "metricas_pronostico",
        lambda tabla: pd.DataFrame(
            [{"modelo": tabla.iloc[0]["modelo"], "n": len(tabla), "wape": 0.0}]
        ),
    )
    monkeypatch.setattr(
        service,
        "metricas_cobertura_operacional",
        lambda _tabla: {"cobertura_operacional": 1.0},
    )


def test_fachada_y_servicio_conservan_aliases_firmas_y_construccion(monkeypatch) -> None:
    for nombre in (
        "argumentos",
        "_marcar_macro",
        "_expandir_v1",
        "_naive",
        "_metricas",
        "_leer_anterior",
        "construir",
        "persistir",
        "_semanas_cerradas",
        "_emisiones_completas",
        "_normalizar_modelo",
    ):
        assert getattr(facade, nombre) is getattr(service, nombre), nombre
        assert inspect.signature(getattr(facade, nombre)) == inspect.signature(
            getattr(service, nombre)
        )

    assert inspect.signature(service.persistir) != inspect.signature(
        persistir_replay.persistir_campania
    )
    assert service.SNAPSHOT_ID == 40
    assert service.RUN_ORIGEN == 76

    _preparar_construccion(monkeypatch)
    salida_facade = facade.construir("C2025", 1, 76)
    salida_servicio = service.construir("C2025", 1, 76)

    pd.testing.assert_frame_equal(salida_facade[0], salida_servicio[0])
    pd.testing.assert_frame_equal(salida_facade[1], salida_servicio[1])
    assert salida_facade[2] == salida_servicio[2]
    assert set(salida_facade[0]["modelo"]) == {
        service.MODELO_MACRO,
        service.MODELO_V1,
        service.MODELO_V2,
        service.MODELO_NAIVE,
    }
    assert salida_facade[2]["advertencias"] == ["advertencia-sintetica"]


def test_dry_run_no_instancia_ni_escribe_en_repositorio(monkeypatch) -> None:
    predicciones = _macro_sintetico()
    metricas = pd.DataFrame([{"modelo": service.MODELO_MACRO, "n": 2}])
    resumen = {"campania": "C2025", "emisiones_sinteticas": 1}
    monkeypatch.setattr(
        service,
        "construir",
        lambda *_args: (predicciones, metricas, resumen),
    )

    eventos: list[str] = []

    class RepositorioFalso:
        def __init__(self, *_args, **_kwargs):
            eventos.append("init")

    monkeypatch.setattr(service, "RepositorioAnalytics", RepositorioFalso)

    args = SimpleNamespace(campania="C2025", max_targets=1, keep_run=76, dry_run=True)
    assert facade.persistir(args) is resumen
    assert eventos == []


def test_persistencia_conserva_orden_snapshot_fijo_y_failed(monkeypatch) -> None:
    predicciones = _macro_sintetico()
    metricas = pd.DataFrame([{"modelo": service.MODELO_MACRO, "n": 2}])
    resumen = {"campania": "C2025"}
    monkeypatch.setattr(
        service,
        "construir",
        lambda *_args: (predicciones, metricas, resumen.copy()),
    )
    monkeypatch.setattr(service.settings, "postgres_dsn", lambda: "dsn-sintetico")
    eventos: list[tuple[object, ...]] = []

    class RepositorioFalso:
        def __init__(self, dsn):
            eventos.append(("init", dsn))

        def snapshot(self, *_args, **_kwargs):
            eventos.append(("snapshot",))
            raise AssertionError("este contrato usa SNAPSHOT_ID fijo")

        def crear_run(self, *args):
            eventos.append(("crear_run", *args))
            return 9001

        def guardar_predicciones(self, *args):
            eventos.append(("guardar_predicciones", *args))

        def guardar_metricas(self, *args):
            eventos.append(("guardar_metricas", *args))
            raise RuntimeError("fallo sintetico")

        def finalizar_run(self, *args):
            eventos.append(("finalizar_run", *args))

    monkeypatch.setattr(service, "RepositorioAnalytics", RepositorioFalso)
    args = SimpleNamespace(campania="C2025", max_targets=None, keep_run=76, dry_run=False)

    with pytest.raises(RuntimeError, match="fallo sintetico"):
        service.persistir(args)

    assert [evento[0] for evento in eventos] == [
        "init",
        "crear_run",
        "guardar_predicciones",
        "guardar_metricas",
        "finalizar_run",
    ]
    assert eventos[1][1:] == (
        service.SNAPSHOT_ID,
        "backtest",
        {
            "modelo_hibrido": service.MODELO_V2,
            "version_modelo": service.VERSION_V2,
            "campania_reconstruida": "C2025",
            "universo": "campania_completa_asof_semanal",
            "emisiones": "sinteticas_lunes_previo_al_cierre",
            "run_origen_conservado": 76,
            "r09": "referencia_publicada_no_algoritmo",
            "sin_datos_futuros": True,
        },
    )
    assert eventos[-1] == ("finalizar_run", 9001, "failed", "fallo sintetico")
