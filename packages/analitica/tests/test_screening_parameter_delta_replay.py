from __future__ import annotations

import ast
import inspect
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

from analitica.aplicacion.servicios import parameter_delta_replay as service
from analitica.aplicacion.servicios import parametros_replay
from analitica.interfaces.scripts import screening_parameter_delta_replay as facade

NOMBRES_COMPATIBLES = (
    "_conexion_access",
    "_columna_campania",
    "_libros_semana",
    "_normalizar_clave",
    "_columna",
    "_preparar_lote",
    "_aplicar_modelo",
    "_proyectar_emision_detallada",
    "_proyectar_emision",
    "_metricas",
    "conexion_access",
    "columna_campania",
    "libros_semana",
    "normalizar_clave",
    "columna",
    "preparar_lote",
    "aplicar_modelo",
    "proyectar_emision_detallada",
    "proyectar_emision",
    "cargar_reales_y_r09",
    "ejecutar",
)


@pytest.mark.parametrize("nombre", NOMBRES_COMPATIBLES)
def test_fachada_conserva_identidad_y_firma_historica(nombre: str) -> None:
    assert getattr(facade, nombre) is getattr(service, nombre)
    assert inspect.signature(getattr(facade, nombre)) == inspect.signature(
        getattr(service, nombre)
    )


def test_fachada_conserva_constantes_y_imports_publicos() -> None:
    for nombre in (
        "ACCESS_DEFAULT",
        "PARAMETROS_CALENDARIO",
        "PARAMETROS_CURVA",
        "ROOT_DEFAULT",
        "TRANSITIONS_DEFAULT",
        "CandidateParamDelta",
        "np",
        "pd",
        "ejecutar_proyeccion_semanal_dataframe",
        "seleccionar_libros_parametros",
        "leer_libro_operativo",
    ):
        assert getattr(facade, nombre) is getattr(service, nombre)
    for nombre in (
        "ACCESS_DEFAULT",
        "PARAMETROS_CALENDARIO",
        "PARAMETROS_CURVA",
        "ROOT_DEFAULT",
        "TRANSITIONS_DEFAULT",
    ):
        assert getattr(service, nombre) is getattr(parametros_replay, nombre)


def test_ejecutar_preserva_filtrado_asof_configuraciones_y_serializacion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transiciones = pd.DataFrame(
        {
            "fila_asof_utilizable": [True, False, True],
            "semana_emision_actual": [20, 2, 30],
        }
    )
    llamadas_fit: list[tuple[int, ...]] = []
    llamadas_proyeccion: list[tuple[int, str]] = []

    class ModeloFalso:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def fit(self, entrenamiento: pd.DataFrame) -> ModeloFalso:
            llamadas_fit.append(tuple(entrenamiento.semana_emision_actual.astype(int)))
            return self

    monkeypatch.setattr(service.pd, "read_parquet", lambda _ruta: transiciones.copy())
    monkeypatch.setattr(
        service,
        "cargar_reales_y_r09",
        lambda *_args: ({29: 100.0}, {(28, 29): 95.0}),
    )
    monkeypatch.setattr(service, "CandidateParamDelta", ModeloFalso)

    def proyectar_falso(*_args: object, **kwargs: object) -> tuple[float, dict[str, int]]:
        emision = int(kwargs["semana_emision"])
        bloque = str(kwargs["bloque"])
        llamadas_proyeccion.append((emision, bloque))
        return (110.0 if bloque == "ninguno" else 120.0), {"lote": 1}

    monkeypatch.setattr(service, "_proyectar_emision", proyectar_falso)

    resultado = service.ejecutar(
        root=Path("proyecciones"),
        transitions=Path("transiciones.parquet"),
        access=Path("datos.accdb"),
        emisiones=(28,),
    )

    assert llamadas_fit == [(20,), (20,)]
    assert llamadas_proyeccion == [(28, "ninguno"), (28, "parametros")]
    assert resultado["schema"] == "screening-parameter-delta-replay-v1"
    assert resultado["emisiones"] == [28]
    assert [fila["candidato_kg"] for fila in resultado["detalle"]] == [110.0, 120.0]
    assert resultado["ranking"][0]["candidato"]["n_semanas"] == 1
    assert resultado["publicable"] is False


def test_fachada_cli_conserva_argumentos_salida_y_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    salida = tmp_path / "resultado" / "screening.json"
    raiz = tmp_path / "proyecciones"
    transiciones = tmp_path / "transiciones.parquet"
    access = tmp_path / "datos.accdb"
    esperado = {"ranking": [{"configuracion_id": 1}], "detalle": []}
    llamadas: list[tuple[Path, Path, Path, str, tuple[int, ...]]] = []

    def fake_ejecutar(
        *,
        root: Path,
        transitions: Path,
        access: Path,
        campania: str,
        emisiones: tuple[int, ...],
    ) -> dict[str, object]:
        llamadas.append((root, transitions, access, campania, emisiones))
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
            "screening_parameter_delta_replay",
            "--root",
            str(raiz),
            "--transitions",
            str(transiciones),
            "--access",
            str(access),
            "--campania",
            "C2025",
            "--emisiones",
            "28",
            "31",
            "--salida",
            str(salida),
        ],
    )

    assert facade.main() == 0
    assert llamadas == [(raiz, transiciones, access, "C2025", (28, 31))]
    assert json.loads(salida.read_text(encoding="utf-8")) == esperado
    assert json.loads(capsys.readouterr().out) == esperado["ranking"]


def test_fachada_es_compuerta_cli_y_no_contiene_logica_de_negocio() -> None:
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


def test_servicio_no_depende_de_scripts() -> None:
    ruta = Path(service.__file__)
    arbol = ast.parse(ruta.read_text(encoding="utf-8"), filename=str(ruta))
    assert not [
        nodo
        for nodo in ast.walk(arbol)
        if isinstance(nodo, ast.ImportFrom)
        and nodo.module
        and nodo.module.startswith("analitica.interfaces.scripts.")
    ]
