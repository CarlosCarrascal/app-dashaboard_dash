"""La integración del panel debe ser verificable, no solo plausible."""

from types import SimpleNamespace

import pandas as pd
import pytest

from analitica.proyeccion.calidad import controles_ensamblaje
from analitica.proyeccion.relaciones import (
    _merge_auditado,
    construir_panel_relaciones,
)


def _datos_base(cosecha: pd.DataFrame | None = None):
    cosecha = (
        cosecha
        if cosecha is not None
        else pd.DataFrame(
            [
                {
                    "campania": "2026",
                    "lote_id": 1,
                    "empresa": "A",
                    "fundo": "F1",
                    "modulo": "M01",
                    "lote": "L01",
                    "fecha": "2026-01-05",
                    "kg": 100,
                    "peso_baya": 2.5,
                    "plantas_cosechadas": 10,
                    "area_ha": 1,
                    "plantas_maestro": 10,
                }
            ]
        )
    )
    flores = pd.DataFrame(
        [
            {
                "lote_id": 1,
                "fecha": "2026-01-05",
                "n_flores": 20,
                "cuajo": 10,
                "planta": 1,
            }
        ]
    )
    vacias = {
        nombre: pd.DataFrame()
        for nombre in ("estados", "bayas", "brotes", "ramas", "poda", "clima", "riego", "lotes")
    }
    return SimpleNamespace(cosecha=cosecha, flores=flores, **vacias)


def test_panel_auditado_deja_una_fila_por_union_y_grano_final():
    panel, auditoria = construir_panel_relaciones(_datos_base(), devolver_auditoria=True)

    assert len(panel) == 1
    assert not panel.duplicated(["lote_id", "fecha_semana"]).any()
    assert {"cosecha_agregada", "cosecha_flores"} <= set(auditoria.paso)
    assert (auditoria.estado == "ok").all()
    assert (auditoria.filas_salida_duplicadas == 0).all()

    calidad = controles_ensamblaje(auditoria)
    assert (calidad.estado == "ok").all()
    assert calidad.afectados.sum() == 0


def test_union_muchos_a_muchos_falla_y_deja_registro_de_error():
    izquierda = pd.DataFrame({"lote_id": [1], "fecha_semana": [pd.Timestamp("2026-01-05")]})
    derecha = pd.DataFrame(
        {
            "lote_id": [1, 1],
            "fecha_semana": [pd.Timestamp("2026-01-05")] * 2,
            "x": [10, 20],
        }
    )
    auditoria = []

    with pytest.raises(ValueError, match="no cumple one_to_one"):
        _merge_auditado(
            izquierda,
            derecha,
            auditoria=auditoria,
            nombre="prueba_muchos_a_muchos",
            unidad="lote-semana",
            on=["lote_id", "fecha_semana"],
            how="outer",
            validate="one_to_one",
            grano_salida=["lote_id", "fecha_semana"],
        )

    assert auditoria[0]["estado"] == "error"
    assert auditoria[0]["claves_derecha_duplicadas"] == 2


def test_panel_base_duplicado_falla_antes_de_calcular_relaciones():
    base = _datos_base().cosecha.copy()
    segunda = base.iloc[0].copy()
    segunda["empresa"] = "OTRA"
    datos = _datos_base(pd.concat([base, pd.DataFrame([segunda])], ignore_index=True))

    with pytest.raises(ValueError, match="cosecha_agregada"):
        construir_panel_relaciones(datos)
