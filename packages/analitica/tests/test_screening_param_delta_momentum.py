from __future__ import annotations

import ast
import inspect
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from analitica.aplicacion.servicios import param_delta_momentum as service
from analitica.interfaces.scripts import screening_param_delta_momentum as facade

NOMBRES_COMPATIBLES = (
    "_fundo",
    "_leer_macro_h1",
    "_columna_campania",
    "_leer_reales_r09_fundo",
    "_metricas",
    "_cobertura",
    "_hash_keyset",
    "normalizar_fundo",
    "leer_macro_h1",
    "columna_campania",
    "leer_reales_r09_fundo",
    "ejecutar",
)


@pytest.mark.parametrize("nombre", NOMBRES_COMPATIBLES)
def test_fachada_conserva_identidad_y_firma_historica(nombre: str) -> None:
    assert getattr(facade, nombre) is getattr(service, nombre)
    assert inspect.signature(getattr(facade, nombre)) == inspect.signature(
        getattr(service, nombre)
    )


def test_fachada_conserva_imports_historicos_y_constantes() -> None:
    for nombre in (
        "ACCESS_DEFAULT",
        "ROOT_DEFAULT",
        "TRANSITIONS_DEFAULT",
        "CandidateParamDelta",
        "proyectar_emision_detallada",
        "postgres_dsn",
        "np",
        "pd",
        "psycopg",
    ):
        assert getattr(facade, nombre) is getattr(service, nombre)


def _macro_falso() -> pd.DataFrame:
    filas = []
    for semana_emision, semana_objetivo in ((28, 29), (29, 30), (32, 33)):
        objetivo = pd.Timestamp("2026-07-13") + pd.Timedelta(
            weeks=semana_objetivo - 29
        )
        emision = objetivo - pd.Timedelta(days=7)
        for fundo in ("Arena", "Quri", "Kawsay", "Ayllu"):
            filas.append(
                {
                    "campania": "C2026",
                    "fecha_emision": emision,
                    "fecha_objetivo": objetivo,
                    "semana_emision": semana_emision,
                    "semana_objetivo": semana_objetivo,
                    "fundo_operativo": fundo,
                    "macro_kg": 100.0,
                    "real_pg_kg": 90.0,
                }
            )
    return pd.DataFrame(filas)


def test_ejecutar_preserva_asof_reemplazos_y_r09_como_referencia(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reales = pd.DataFrame(
        [
            {"semana_objetivo": semana, "fundo_operativo": fundo, "real_kg": 90.0}
            for semana in (29, 30, 33)
            for fundo in ("Arena", "Quri", "Kawsay", "Ayllu")
        ]
    )
    r09 = pd.DataFrame(
        {
            "semana_emision": [28],
            "semana_objetivo": [29],
            "fundo_operativo": ["Arena"],
            "r09_kg": pd.Series([0.0], dtype=object),
        }
    )
    transiciones = pd.DataFrame(
        {"semana_emision_actual": [20, 21, 22, 30], "fila_asof_utilizable": [True] * 4}
    )
    llamadas_fit: list[tuple[int, ...]] = []
    llamadas_proyeccion: list[int] = []

    class ModeloFalso:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def fit(self, entrenamiento: pd.DataFrame) -> ModeloFalso:
            llamadas_fit.append(tuple(sorted(entrenamiento.semana_emision_actual.astype(int))))
            return self

    monkeypatch.setattr(service, "_leer_macro_h1", lambda _campania: _macro_falso())
    monkeypatch.setattr(service, "_leer_reales_r09_fundo", lambda *_args: (reales, r09))
    monkeypatch.setattr(service.pd, "read_parquet", lambda _ruta: transiciones.copy())
    monkeypatch.setattr(service, "CandidateParamDelta", ModeloFalso)

    def proyectar_falso(*_args: object, **kwargs: object):
        emision = int(kwargs["semana_emision"])
        llamadas_proyeccion.append(emision)
        valores = {
            fundo: float(1000 + emision)
            for fundo in ("Arena", "Quri", "Kawsay", "Ayllu")
        }
        return valores, None

    monkeypatch.setattr(service, "proyectar_emision_detallada", proyectar_falso)

    resultado = service.ejecutar(
        root=Path("proyecciones"),
        transitions=Path("transiciones.parquet"),
        access=Path("datos.accdb"),
    )

    assert llamadas_fit == [
        (20, 21, 22),
        (20, 21, 22),
        (20, 21, 22, 30),
        (20, 21, 22, 30),
    ]
    assert llamadas_proyeccion == [28, 29, 32, 33]
    assert [fila["kg"] for fila in resultado["reemplazos"]] == (
        [1028.0] * 4 + [1029.0] * 4 + [1032.0] * 4
    )
    assert all(fila["r09_kg"] != 0.0 for fila in resultado["holdout"])
    assert all(np.isnan(fila["r09_kg"]) for fila in resultado["holdout"])
    detalle = pd.DataFrame(resultado["detalle"])
    con_r09_cero = detalle.loc[
        detalle["fundo_operativo"].eq("Arena") & detalle["semana_emision"].eq(28)
    ].iloc[0]
    sin_r09 = detalle.loc[
        detalle["fundo_operativo"].eq("Quri") & detalle["semana_emision"].eq(28)
    ].iloc[0]
    assert list(detalle.columns) == [
        "campania",
        "fecha_emision",
        "fecha_objetivo",
        "semana_emision",
        "semana_objetivo",
        "fundo_operativo",
        "macro_kg",
        "real_pg_kg",
        "real_kg",
        "real_disponible",
        "r09_kg",
        "r09_disponible",
        "macro_disponible",
        "candidate_disponible",
        "candidate_kg",
        "ruta",
    ]
    assert pd.api.types.is_float_dtype(detalle["r09_kg"])
    assert pd.api.types.is_bool_dtype(detalle["r09_disponible"])
    assert bool(con_r09_cero["r09_disponible"])
    assert con_r09_cero["r09_kg"] == 0.0
    assert not bool(sin_r09["r09_disponible"])
    assert sin_r09["r09_kg"] == 0.0
    assert all(
        fila["ruta"] == "param_delta_asof"
        for fila in resultado["detalle"]
        if fila["semana_emision"] in (28, 29, 32)
    )


def test_metricas_y_cobertura_conservan_columnas_y_ausencias() -> None:
    tabla = pd.DataFrame(
        [
            {
                "semana_objetivo": 29,
                "fundo_operativo": "Arena",
                "pred_kg": 110.0,
                "real_kg": 100.0,
                "disponible": True,
            },
            {
                "semana_objetivo": 30,
                "fundo_operativo": "Arena",
                "pred_kg": 80.0,
                "real_kg": 100.0,
                "disponible": False,
            },
        ]
    )
    assert service._metricas(tabla, "pred_kg", grano=("semana_objetivo",)) == {
        "wape": pytest.approx(0.15),
        "sesgo": pytest.approx(-0.05),
        "mae_kg": pytest.approx(15.0),
        "n": 2,
    }
    cobertura = service._cobertura(
        tabla, "disponible", grano=("semana_objetivo", "fundo_operativo")
    )
    assert cobertura == {
        "filas_disponibles": 1,
        "filas_totales": 2,
        "cobertura_filas": pytest.approx(0.5),
        "cobertura_volumen": pytest.approx(0.5),
    }


def test_fachada_cli_conserva_argumentos_serializacion_y_ruta(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    salida = tmp_path / "resultado" / "screening.json"
    raiz = tmp_path / "proyecciones"
    esperado = {
        "resumen_empresa_semana": {"candidato": {"n": 1}},
        "resumen_fundo_semana": {"candidato": {"n": 1}},
        "por_fundo": {"Arena": {"n": 1}},
    }
    llamadas: list[tuple[Path, Path, Path]] = []

    def fake_ejecutar(*, root: Path, transitions: Path, access: Path, **_kwargs: object):
        llamadas.append((root, transitions, access))
        return esperado

    def fake_escribir(resultado: dict[str, object], ruta: Path) -> None:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(json.dumps(resultado), encoding="utf-8")

    monkeypatch.setattr(facade, "ejecutar", fake_ejecutar)
    monkeypatch.setattr(facade, "escribir_json_reproducible", fake_escribir)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "screening_param_delta_momentum",
            "--root",
            str(raiz),
            "--transitions",
            str(tmp_path / "transiciones.parquet"),
            "--access",
            str(tmp_path / "datos.accdb"),
            "--salida",
            str(salida),
        ],
    )

    assert facade.main() == 0
    assert llamadas == [
        (raiz, tmp_path / "transiciones.parquet", tmp_path / "datos.accdb")
    ]
    assert json.loads(salida.read_text(encoding="utf-8")) == esperado
    assert json.loads(capsys.readouterr().out)["por_fundo"] == esperado["por_fundo"]


def test_fachada_es_compuerta_cli_sin_logica_de_negocio() -> None:
    ruta = Path(facade.__file__)
    arbol = ast.parse(ruta.read_text(encoding="utf-8"), filename=str(ruta))
    definiciones = [
        nodo.name
        for nodo in arbol.body
        if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    ]
    assert definiciones == ["main"]
    assert not [
        nodo
        for nodo in ast.walk(arbol)
        if isinstance(nodo, (ast.For, ast.While, ast.Try, ast.With, ast.AsyncWith))
    ]
    assert not [
        nodo
        for nodo in ast.walk(arbol)
        if isinstance(nodo, ast.ImportFrom)
        and nodo.module
        and ".scripts" in nodo.module
    ]
