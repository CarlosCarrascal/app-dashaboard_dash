"""Controles publicables de datos, fuga, intervalos y reproducibilidad."""

from __future__ import annotations

import pandas as pd

from .asof import detectar_fuga
from .backtest import seleccionar_versiones_oficiales
from .reconciliacion import verificar_coherencia
from .versiones import parsear_version


def controles_fuente(datos) -> pd.DataFrame:
    filas = [
        {
            "regla": "fuente_principal_postgres",
            "estado": "warning" if datos.fuente.fallback else "ok",
            "observados": 1,
            "afectados": int(datos.fuente.fallback),
            "detalle": "; ".join(datos.fuente.advertencias),
        }
    ]
    if not datos.forecast.empty:
        oficiales = seleccionar_versiones_oficiales(datos.forecast)
        parsed = datos.forecast.version.map(parsear_version)
        no_parseables = sum(v.semana_emision is None for v in parsed)
        escenarios = sum(v.semana_emision is not None and v.escenario is not None for v in parsed)
        filas.extend(
            [
                {
                    "regla": "versiones_r09_parseables",
                    "estado": "ok" if not no_parseables else "error",
                    "observados": len(datos.forecast),
                    "afectados": no_parseables,
                    "detalle": "Códigos que no siguen Snn, Snn_vN o Snn_vEscenario.",
                },
                {
                    "regla": "escenarios_r09_excluidos_del_oficial",
                    "estado": "warning" if escenarios else "ok",
                    "observados": len(datos.forecast),
                    "afectados": escenarios,
                    "detalle": (
                        f"{len(oficiales)} filas sobreviven además a selección de máxima iteración."
                    ),
                },
            ]
        )
    return pd.DataFrame(filas)


def controles_ensamblaje(auditoria: pd.DataFrame) -> pd.DataFrame:
    """Publica el resultado de las uniones que forman el panel de Relaciones.

    La ausencia de una auditoría es un error de gobernanza: un panel puede tener números
    plausibles y aun así haber sido inflado por una unión muchos-a-muchos.
    """
    columnas = ["regla", "estado", "observados", "afectados", "detalle"]
    if auditoria is None or auditoria.empty:
        return pd.DataFrame(
            [
                {
                    "regla": "auditoria_ensamblaje_disponible",
                    "estado": "error",
                    "observados": 0,
                    "afectados": 0,
                    "detalle": "La corrida de Relaciones no dejó auditoría de sus uniones.",
                }
            ],
            columns=columnas,
        )
    filas = []
    for fila in auditoria.itertuples(index=False):
        afectados = int(getattr(fila, "filas_salida_duplicadas", 0) or 0)
        if getattr(fila, "estado", "ok") == "error" and afectados == 0:
            afectados = 1
        factor = getattr(fila, "factor_expansion", None)
        factor_texto = "—" if pd.isna(factor) else f"{float(factor):.3f}x"
        detalle = (
            f"{fila.tipo_union} por [{fila.claves_union}]; "
            f"filas {fila.filas_izquierda} → {fila.filas_salida}; "
            f"emparejadas={fila.filas_emparejadas}; "
            f"claves sin pareja izq/der={fila.filas_solo_izquierda}/"
            f"{fila.filas_solo_derecha}; expansión={factor_texto}."
        )
        if getattr(fila, "detalle", ""):
            detalle += f" {fila.detalle}"
        filas.append(
            {
                "regla": f"integridad_union_{fila.paso}",
                "estado": fila.estado,
                "observados": int(fila.filas_salida),
                "afectados": afectados,
                "detalle": detalle,
            }
        )
    return pd.DataFrame(filas, columns=columnas)


def controles_panel_asof(panel: pd.DataFrame) -> pd.DataFrame:
    fugas = detectar_fuga(panel)
    if fugas.empty:
        return pd.DataFrame(
            [
                {
                    "regla": "sin_observaciones_posteriores_a_emision",
                    "estado": "ok",
                    "observados": len(panel),
                    "afectados": 0,
                    "detalle": "",
                }
            ]
        )
    return pd.DataFrame(
        [
            {
                "regla": f"asof_{fila.campo}",
                "estado": "error",
                "observados": len(panel),
                "afectados": int(fila.afectados),
                "detalle": "fecha observada posterior a emisión",
            }
            for fila in fugas.itertuples()
        ]
    )


def controles_predicciones(predicciones: pd.DataFrame) -> pd.DataFrame:
    if predicciones.empty:
        return pd.DataFrame(
            [
                {
                    "regla": "predicciones_no_vacias",
                    "estado": "error",
                    "observados": 0,
                    "afectados": 0,
                    "detalle": "",
                }
            ]
        )
    malos = (
        predicciones.p50_kg.lt(0)
        | predicciones.p10_kg.gt(predicciones.p50_kg)
        | predicciones.p90_kg.lt(predicciones.p50_kg)
    ).fillna(True)
    duplicados = predicciones.duplicated(
        ["modelo", "campania", "lote_id", "fecha_emision", "fecha_objetivo", "version_fuente"],
        keep=False,
    )
    return pd.DataFrame(
        [
            {
                "regla": "orden_p10_p50_p90",
                "estado": "ok" if not malos.any() else "error",
                "observados": len(predicciones),
                "afectados": int(malos.sum()),
                "detalle": "",
            },
            {
                "regla": "clave_prediccion_unica",
                "estado": "ok" if not duplicados.any() else "error",
                "observados": len(predicciones),
                "afectados": int(duplicados.sum()),
                "detalle": "",
            },
        ]
    )


def controles_componentes(
    predicciones: pd.DataFrame, tolerancia_relativa: float = 1e-6
) -> pd.DataFrame:
    """Controles de las familias que publican las tres piezas del rendimiento.

    Solo aplican a las filas que declaran `base_plantas`: un modelo que no estima
    componentes propios no tiene nada que reconstruir y no debe salir marcado.
    """
    vacio = pd.DataFrame(columns=["regla", "estado", "observados", "afectados", "detalle"])
    if predicciones.empty or "base_plantas" not in predicciones:
        return vacio
    filas = predicciones[predicciones.base_plantas.notna()]
    if filas.empty:
        return vacio

    requeridas = {"plantas", "frutos_por_planta", "peso_baya_g", "p50_kg"}
    if requeridas - set(filas):
        return pd.DataFrame(
            [
                {
                    "regla": "componentes_declarados_completos",
                    "estado": "error",
                    "observados": len(filas),
                    "afectados": len(filas),
                    "detalle": f"faltan columnas: {sorted(requeridas - set(filas))}",
                }
            ]
        )

    producto = filas.plantas * filas.frutos_por_planta * filas.peso_baya_g / 1000
    if "probabilidad_cosecha" in filas:
        producto = producto * pd.to_numeric(filas.probabilidad_cosecha, errors="coerce")
    if "factor_asignacion_cosecha" in filas:
        producto = producto * pd.to_numeric(
            filas.factor_asignacion_cosecha, errors="coerce"
        ).fillna(1.0)
    desvio = (producto - filas.p50_kg).abs() / filas.p50_kg.abs().clip(lower=1.0)
    incoherentes = (desvio > tolerancia_relativa).fillna(True)
    negativos = (
        filas.plantas.le(0) | filas.frutos_por_planta.lt(0) | filas.peso_baya_g.lt(0)
    ).fillna(True)
    reglas = [
        {
            "regla": "identidad_kg_reconstruye_componentes",
            "estado": "ok" if not incoherentes.any() else "error",
            "observados": len(filas),
            "afectados": int(incoherentes.sum()),
            "detalle": f"desvio_relativo_max={float(desvio.max()):.3e}"
            if desvio.notna().any()
            else "",
        },
        {
            "regla": "componentes_no_negativos",
            "estado": "ok" if not negativos.any() else "error",
            "observados": len(filas),
            "afectados": int(negativos.sum()),
            "detalle": "",
        },
    ]

    # Extrapolación: predecir fuera del rango jamás observado no es un error de cálculo,
    # pero sí algo que debe verse antes de comprometer kilos sobre ese número.
    for columna, observada in (("peso_baya_g", "peso_real_g"), ("frutos_por_planta", None)):
        serie_real = (
            predicciones[observada].dropna()
            if observada and observada in predicciones
            else pd.Series(dtype=float)
        )
        if serie_real.empty or columna not in filas:
            continue
        fuera = (filas[columna].lt(serie_real.min()) | filas[columna].gt(serie_real.max())).fillna(
            False
        )
        reglas.append(
            {
                "regla": f"{columna}_dentro_del_rango_observado",
                "estado": "ok" if not fuera.any() else "warning",
                "observados": len(filas),
                "afectados": int(fuera.sum()),
                "detalle": f"rango_observado=[{serie_real.min():.3f}, {serie_real.max():.3f}]",
            }
        )

    if "filas_con_gate_cero" in filas:
        anuladas = int(pd.to_numeric(filas.filas_con_gate_cero, errors="coerce").fillna(0).max())
        reglas.append(
            {
                "regla": "calendario_cosecha_heredado_de_r09",
                "estado": "warning" if anuladas else "ok",
                "observados": len(filas),
                "afectados": anuladas,
                "detalle": "la familia no predice qué semanas tienen cosecha; hereda el "
                "calendario del forecast publicado",
            }
        )
    return pd.DataFrame(reglas)


def controles_reconciliacion(reconciliado: pd.DataFrame) -> pd.DataFrame:
    return verificar_coherencia(reconciliado)
