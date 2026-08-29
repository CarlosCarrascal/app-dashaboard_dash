from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from analitica import catalogos, config, settings

CATALOG_NAMES = (
    "ETIQUETAS",
    "GLOSARIO",
    "ETIQUETAS_ANALITICAS",
    "GLOSARIO_ANALITICO",
    "VALORES_ANALITICOS",
    "FORMATO_ANALITICO",
    "etiqueta",
    "glosa",
)

SHARED_CONFIGURATION_NAMES = (
    "PARAMS",
    "HOJAS",
    "AZUL",
    "ROJO",
    "VERDE",
    "GRIS",
    "NARANJA",
)


def test_config_reexporta_los_catalogos_sin_copiar_objetos():
    for name in CATALOG_NAMES:
        assert getattr(config, name) is getattr(catalogos, name)


def test_config_reexporta_la_configuracion_compartida_sin_duplicarla():
    for name in SHARED_CONFIGURATION_NAMES:
        assert getattr(config, name) is getattr(catalogos, name)

    assert catalogos.PARAMS == {
        "n_estimators": 300,
        "max_depth": 6,
        "learning_rate": 0.01,
        "min_child_weight": 10,
        "reg_lambda": 5,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "random_state": 0,
        "n_jobs": 1,
    }
    assert {"KgHa", "Temp Max-Min", "Rad y ET", "Riego", "DPV"} == catalogos.HOJAS
    assert {
        name: getattr(catalogos, name)
        for name in ("AZUL", "ROJO", "VERDE", "GRIS", "NARANJA")
    } == {
        "AZUL": "#3B7DD8",
        "ROJO": "#E8443A",
        "VERDE": "#7FB069",
        "GRIS": "#5A6472",
        "NARANJA": "#D9822B",
    }


def test_catalogos_conservan_valores_representativos():
    assert catalogos.ETIQUETAS["DPV"] == "DPV (kPa)"
    assert catalogos.GLOSARIO["DPV"].startswith("Déficit de presión de vapor")
    assert catalogos.ETIQUETAS_ANALITICAS["p50_kg"] == "Kilos esperados"
    assert catalogos.GLOSARIO_ANALITICO["wape"].endswith("Más bajo es mejor.")
    assert catalogos.VALORES_ANALITICOS["estado"]["succeeded"] == "Terminada bien"
    assert catalogos.VALORES_ANALITICOS["campeon"] is catalogos.VALORES_ANALITICOS["modelo"]
    assert catalogos.FORMATO_ANALITICO["wape"] == "pct_frac"
    assert catalogos.etiqueta("DPV") == "DPV (kPa)"
    assert catalogos.etiqueta("p50_kg") == "Kilos esperados"
    assert catalogos.etiqueta("columna_desconocida") == "columna_desconocida"
    assert catalogos.glosa("DPV") == catalogos.GLOSARIO["DPV"]
    assert catalogos.glosa("wape") == catalogos.GLOSARIO_ANALITICO["wape"]
    assert catalogos.glosa("columna_desconocida") is None


def test_importar_config_y_catalogos_no_activa_dependencias_pesadas():
    raiz_paquete = Path(__file__).resolve().parents[2]
    codigo = """
import sys
import analitica.catalogos
import analitica.config

prohibidos = {
    "sklearn",
    "scipy",
    "statsmodels",
    "xgboost",
    "mlflow",
    "plotly",
}
activos = sorted(
    nombre for nombre in sys.modules
    if nombre.split('.', 1)[0] in prohibidos
)
assert not activos, activos
"""
    entorno = os.environ.copy()
    ruta_anterior = entorno.get("PYTHONPATH")
    entorno["PYTHONPATH"] = str(raiz_paquete) + (
        os.pathsep + ruta_anterior if ruta_anterior else ""
    )
    resultado = subprocess.run(
        [sys.executable, "-c", codigo],
        check=False,
        capture_output=True,
        text=True,
        env=entorno,
    )
    assert resultado.returncode == 0, resultado.stderr or resultado.stdout


def test_settings_conserva_rutas_relativas_absolutas_y_dsn(monkeypatch, tmp_path):
    monkeypatch.delenv("AQUANQA_CONFIG_TEST_PATH", raising=False)
    assert settings._ruta(
        "AQUANQA_CONFIG_TEST_PATH", settings._RAIZ_REPOSITORIO / "entrada.xlsx"
    ) == settings._RAIZ_REPOSITORIO / "entrada.xlsx"

    ruta_absoluta = tmp_path / "entrada.xlsx"
    monkeypatch.setenv("AQUANQA_CONFIG_TEST_PATH", str(ruta_absoluta))
    assert settings._ruta(
        "AQUANQA_CONFIG_TEST_PATH", settings._RAIZ_REPOSITORIO / "otra.xlsx"
    ) == ruta_absoluta

    monkeypatch.setattr(settings, "ANALYTICS_DATABASE_URL", "postgresql://url-directa")
    monkeypatch.delenv("PGPASSWORD", raising=False)
    assert settings.postgres_dsn() == "postgresql://url-directa"

    monkeypatch.setattr(settings, "ANALYTICS_DATABASE_URL", None)
    monkeypatch.setenv("PGUSER", "usuario de prueba")
    monkeypatch.setenv("PGPASSWORD", "clave/segura")
    monkeypatch.setenv("PGHOST", "db.local")
    monkeypatch.setenv("PGPORT", "5440")
    monkeypatch.setenv("PGDATABASE", "base de prueba")
    assert (
        settings.postgres_dsn()
        == "postgresql://usuario+de+prueba:clave%2Fsegura@db.local:5440/base+de+prueba"
    )
