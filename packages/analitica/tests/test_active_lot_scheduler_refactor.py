from __future__ import annotations

import ast
import inspect
from pathlib import Path

from analitica.aplicacion.servicios import active_lot_scheduler as fachada
from analitica.aplicacion.servicios import active_lot_scheduler_contratos as contratos
from analitica.aplicacion.servicios import active_lot_scheduler_fuentes as fuentes
from analitica.aplicacion.servicios import active_lot_scheduler_metricas as metricas
from analitica.aplicacion.servicios import active_lot_scheduler_prediccion as prediccion
from analitica.aplicacion.servicios import active_lot_scheduler_salida as salida
from analitica.aplicacion.servicios import cross_campaign

SERVICIOS = Path(__file__).parents[1] / "aplicacion" / "servicios"


def test_fachada_conserva_aliases_historicos_por_identidad_y_firma() -> None:
    aliases = {
        contratos: (
            "CAMPANIAS",
            "CIERRE_C2026",
            "ConfiguracionScheduler",
            "FUNDOS",
            "RUTA_SALIDA",
            "RUN_ID",
            "SEMANA_DESARROLLO_FINAL",
            "SEMANAS_HOLDOUT",
            "configuraciones",
        ),
        fuentes: (
            "_distancia_periodica",
            "_intervalo_mediano",
            "_normalizar_fechas",
            "derivar_contexto_asof",
            "leer_fuentes",
        ),
        prediccion: (
            "_actividad",
            "_escala_online",
            "construir_verdad",
            "predecir_scheduler",
        ),
        metricas: (
            "_cobertura_y_ceros",
            "_metricas",
            "anexar_r09",
            "bootstrap_pareado",
            "resumir",
            "resumir_con_r09",
            "seleccionar_configuracion",
        ),
        salida: (
            "_json_default",
            "_keyset_sha256",
            "ejecutar",
            "escribir_resultado",
        ),
    }
    for modulo, nombres in aliases.items():
        for nombre in nombres:
            objeto_fachada = getattr(fachada, nombre)
            assert objeto_fachada is getattr(modulo, nombre)
            if callable(objeto_fachada):
                assert inspect.signature(objeto_fachada) == inspect.signature(
                    getattr(modulo, nombre)
                )

    assert fachada.R09_ACCESS_DEFAULT is cross_campaign.R09_ACCESS_DEFAULT
    assert fachada.leer_r09_access is cross_campaign.leer_r09_access
    assert fachada.normalizar_fundo is cross_campaign.normalizar_fundo


def test_fachada_no_contiene_implementacion_y_las_capas_no_importan_hacia_arriba() -> None:
    fachada_ast = ast.parse(
        (SERVICIOS / "active_lot_scheduler.py").read_text(encoding="utf-8")
    )
    assert not [
        nodo
        for nodo in fachada_ast.body
        if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    ]

    permitido = {
        "active_lot_scheduler_contratos.py": set(),
        "active_lot_scheduler_fuentes.py": {"active_lot_scheduler_contratos"},
        "active_lot_scheduler_prediccion.py": {
            "active_lot_scheduler_contratos",
            "active_lot_scheduler_fuentes",
        },
        "active_lot_scheduler_metricas.py": {
            "active_lot_scheduler_contratos",
            "active_lot_scheduler_prediccion",
        },
        "active_lot_scheduler_salida.py": {
            "active_lot_scheduler_contratos",
            "active_lot_scheduler_fuentes",
            "active_lot_scheduler_metricas",
            "active_lot_scheduler_prediccion",
        },
    }
    for nombre, esperadas in permitido.items():
        arbol = ast.parse((SERVICIOS / nombre).read_text(encoding="utf-8"))
        importaciones = {
            nodo.module
            for nodo in ast.walk(arbol)
            if isinstance(nodo, ast.ImportFrom)
            and nodo.level
            and nodo.module
            and nodo.module.startswith("active_lot_scheduler")
        }
        assert importaciones == esperadas


def test_contratos_y_configuracion_conservan_literales_historicos() -> None:
    assert contratos.RUN_ID == 78
    assert contratos.CAMPANIAS == ("C2024", "C2025", "C2026")
    assert contratos.FUNDOS == ("Arena", "Ayllu", "Kawsay", "Quri")
    assert contratos.SEMANA_DESARROLLO_FINAL == 30
    assert contratos.SEMANAS_HOLDOUT == (31, 32, 33)
    assert contratos.CIERRE_C2026.isoformat() == "2026-08-16T00:00:00"
    assert Path(".tmp/screening_active_lot_scheduler.json") == contratos.RUTA_SALIDA
    assert len(contratos.configuraciones()) == 109
