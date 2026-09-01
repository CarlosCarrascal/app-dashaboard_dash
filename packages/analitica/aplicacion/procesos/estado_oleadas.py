"""Challenger de estado reciente con descomposición opcional por oleadas.

Este candidato conserva el nivel de ``R09_publicado`` y corrige únicamente su
amplitud con residuales que ya estaban cerrados antes de cada emisión. La curva
manual de oleadas no se usa como sustituto del nivel: cuando el llamador entrega
sus columnas, se usa para repartir el P50 y explicar el timing de la proyección.

La separación es deliberada. R09 tiene una señal de nivel que la curva Gaussiana
aislada no recupera bien; la hipótesis manual sí contiene una estructura útil para
explicar cuándo llega la carga. Mezclarlas en una sola regresión habría vuelto a
confundir nivel, timing y escala. Ninguna salida de este módulo constituye una
causa agronómica: ``driver_principal`` es una atribución mecánica del modelo.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from analitica.dominio.versiones import banda_horizonte

from .candidate_residual_asof import (
    ConfiguracionResidualAsOf,
    aplicar_calibracion_residual_asof,
)

NOMBRE_MODELO = "HibridoEstadoOleadas_v1"
VERSION_MODELO = "r09_estado_asof_gaussian_waves_h6_v1"

_CLAVES = ("campania", "fecha_emision", "fecha_objetivo")
_IDENTIDADES = ("lote_id", "lote")
_COLUMNAS_KG_OLA = tuple(f"kg_ola_{indice}" for indice in range(1, 4))
_COLUMNAS_PARTICIPACION_OLA = tuple(
    f"participacion_ola_{indice}" for indice in range(1, 4)
)


def _configuracion_residual_por_defecto() -> ConfiguracionResidualAsOf:
    """Configuración elegida antes del replay de retención.

    Se deja en una función para que el dataclass no comparta una instancia mutable
    por accidente si el contrato se amplía en el futuro.
    """

    return ConfiguracionResidualAsOf(
        nivel="global",
        ventana=3,
        regularizacion=0.0,
        factor_min=0.50,
        factor_max=2.00,
        por_horizonte=True,
        recencia=0.85,
        usar_campanias_previas=False,
    )


@dataclass(frozen=True)
class ConfiguracionEstadoOleadas:
    """Contrato congelable del challenger R09 + estado + oleadas."""

    residual: ConfiguracionResidualAsOf = field(
        default_factory=_configuracion_residual_por_defecto
    )
    # Seleccionada en desarrollo C2024+C2025 por score de intervalo dentro de
    # cobertura 75--85%; C2026 queda como holdout temporal.
    escala_intervalo: float = 1.30
    ancho_default_intervalo: float = 0.50

    def __post_init__(self) -> None:
        if not isinstance(self.residual, ConfiguracionResidualAsOf):
            raise TypeError("residual debe ser ConfiguracionResidualAsOf")
        if not np.isfinite(self.escala_intervalo) or self.escala_intervalo <= 0:
            raise ValueError("escala_intervalo debe ser positiva y finita")
        if not 0 < self.ancho_default_intervalo <= 1:
            raise ValueError("ancho_default_intervalo debe estar entre cero y uno")


CONFIGURACION_CONGELADA = ConfiguracionEstadoOleadas()


def _serie_numerica(tabla: pd.DataFrame, columna: str) -> pd.Series:
    return pd.to_numeric(tabla[columna], errors="coerce")


def _preparar_panel(panel: pd.DataFrame) -> pd.DataFrame:
    """Permite emitir en vivo sin exigir que todavía exista el real."""

    if not isinstance(panel, pd.DataFrame):
        raise TypeError("panel debe ser un pandas.DataFrame")
    salida = panel.copy()
    if "real_kg" not in salida:
        salida["real_kg"] = np.nan
    return salida


def _extender_horizonte(
    panel: pd.DataFrame,
    horizonte_semanas: int | None,
) -> tuple[pd.DataFrame, int]:
    """Completa como máximo la última semana con una cola R09 explícitamente marcada.

    Algunas publicaciones históricas terminan en H5. Para que una emisión viva pueda
    cumplir el contrato H1--H6 sin inventar una semana observada, se arrastra el último
    P50 disponible del mismo lote y emisión únicamente cuando esa última semana es la
    inmediatamente anterior a la solicitada. Si el lote termina antes, se conserva su
    cobertura original: ese final puede significar que no tiene cosecha programada.
    La fila queda separada de las observadas, con intervalos recalibrados después y
    ``horizonte_extendido=True``.
    """

    if horizonte_semanas is None:
        salida = panel.copy()
        salida["horizonte_extendido"] = salida.get(
            "horizonte_extendido", pd.Series(False, index=salida.index)
        ).astype("boolean").fillna(False).astype(bool)
        return salida, 0
    objetivo = int(horizonte_semanas)
    if not 1 <= objetivo <= 52:
        raise ValueError("horizonte_semanas debe estar entre 1 y 52")

    salida = panel.copy()
    for columna in ("fecha_emision", "fecha_objetivo"):
        salida[columna] = pd.to_datetime(salida[columna], errors="raise").dt.normalize()
    salida["horizonte_semanas"] = pd.to_numeric(
        salida["horizonte_semanas"], errors="raise"
    ).astype(int)
    salida["horizonte_extendido"] = salida.get(
        "horizonte_extendido", pd.Series(False, index=salida.index)
    ).astype("boolean").fillna(False).astype(bool)

    columnas_grupo = ["campania", "lote_id", "fecha_emision"]
    columnas_reales = (
        "real_kg",
        "peso_real_g",
        "plantas_reales",
        "frutos_reales_por_planta",
        "frutos_reales_por_planta_catalogo",
    )
    nuevas: list[pd.Series] = []
    for _, grupo in salida.groupby(columnas_grupo, sort=False, dropna=False):
        existentes = set(grupo.horizonte_semanas.astype(int))
        # Solo se completa la cola posterior al último horizonte que R09 realmente
        # publicó. Un hueco interno puede significar «este lote no cosecha esa semana»;
        # copiarle el P50 de H2/H3 convertiría un cero estructural en kilos inventados.
        ultimo_horizonte = max(existentes, default=0)
        if ultimo_horizonte < objetivo - 1:
            continue
        faltantes = [
            h for h in range(ultimo_horizonte + 1, objetivo + 1) if h not in existentes
        ]
        if not faltantes:
            continue
        ordenado = grupo.sort_values(["horizonte_semanas", "fecha_objetivo"])
        for horizonte in faltantes:
            previos = ordenado[ordenado.horizonte_semanas.le(horizonte)]
            fila = (previos if not previos.empty else ordenado).iloc[-1].copy()
            horizonte_origen = int(fila["horizonte_semanas"])
            fila["fecha_objetivo"] = fila["fecha_emision"] + pd.to_timedelta(
                int(horizonte) * 7, unit="D"
            )
            fila["horizonte_semanas"] = int(horizonte)
            fila["horizonte_origen_extension"] = horizonte_origen
            fila["banda_horizonte"] = banda_horizonte(int(horizonte))
            semana = int(fila["fecha_objetivo"].isocalendar().week)
            if "semana_iso" in fila.index:
                fila["semana_iso"] = semana
            if "semana_objetivo_sin" in fila.index:
                fila["semana_objetivo_sin"] = np.sin(2 * np.pi * semana / 52.18)
            if "semana_objetivo_cos" in fila.index:
                fila["semana_objetivo_cos"] = np.cos(2 * np.pi * semana / 52.18)
            for columna in columnas_reales:
                if columna in fila.index:
                    fila[columna] = np.nan
            fila["horizonte_extendido"] = True
            if "fuente_horizonte" in fila.index:
                fila["fuente_horizonte"] = "cola_r09_ultimo_horizonte"
            nuevas.append(fila)
    if nuevas:
        salida = pd.concat([salida, pd.DataFrame(nuevas)], ignore_index=True, sort=False)
    return salida, len(nuevas)


def _aplicar_intervalos(
    salida: pd.DataFrame,
    config: ConfiguracionEstadoOleadas,
) -> pd.DataFrame:
    """Recentra los intervalos del R09 sobre el P50 corregido.

    Si el R09 vintage no trae bandas válidas, se usa el ancho simétrico declarado
    en la configuración. La escala configurada es un hiperparámetro documentado,
    no una estimación que pueda aprender del propio objetivo evaluado.
    """

    p50_base = _serie_numerica(salida, "p50_base_kg").clip(lower=0)
    p50 = _serie_numerica(salida, "p50_kg").clip(lower=0)
    if "p10_kg" in salida:
        p10_base = _serie_numerica(salida, "p10_kg")
    else:
        p10_base = pd.Series(np.nan, index=salida.index, dtype=float)
    if "p90_kg" in salida:
        p90_base = _serie_numerica(salida, "p90_kg")
    else:
        p90_base = pd.Series(np.nan, index=salida.index, dtype=float)

    intervalo_valido = (
        p10_base.notna()
        & p90_base.notna()
        & p10_base.ge(0)
        & p10_base.le(p50_base)
        & p90_base.ge(p50_base)
    )
    ancho_default = config.ancho_default_intervalo * p50_base
    ancho_inferior = (p50_base - p10_base).where(intervalo_valido, ancho_default)
    ancho_superior = (p90_base - p50_base).where(intervalo_valido, ancho_default)
    salida["p10_kg"] = (p50 - config.escala_intervalo * ancho_inferior.clip(lower=0)).clip(
        lower=0
    )
    salida["p90_kg"] = p50 + config.escala_intervalo * ancho_superior.clip(lower=0)
    salida["escala_intervalo_asof"] = float(config.escala_intervalo)
    salida["intervalo_base_valido"] = intervalo_valido.astype(bool)
    return salida


def _heredar_factor_extension(
    salida: pd.DataFrame,
    config: ConfiguracionEstadoOleadas,
) -> pd.DataFrame:
    """Hereda el factor de estado de la última semana publicada.

    La extensión de horizonte se crea antes de calcular los residuales. Como una
    semana nueva no tiene historial propio, el calibrador le asigna factor uno. Eso
    sería inconsistente si H5 ya recibió una corrección de estado: la cola debe
    conservar ese factor, pero seguir marcada como no observada.
    """

    if "horizonte_origen_extension" not in salida or not salida.horizonte_extendido.any():
        return salida
    claves = ["campania", "fecha_emision"]
    if config.residual.nivel != "global":
        claves.append(config.residual.nivel)
    columnas_origen = [
        *claves,
        "horizonte_semanas",
        "factor_residual_asof",
        "n_residuos_asof",
        "nivel_residual",
    ]
    origen = (
        salida.loc[~salida.horizonte_extendido, columnas_origen]
        .drop_duplicates([*claves, "horizonte_semanas"])
        .rename(
            columns={
                "horizonte_semanas": "horizonte_origen_extension",
                "factor_residual_asof": "factor_extension",
                "n_residuos_asof": "n_residuos_extension",
                "nivel_residual": "nivel_residual_extension",
            }
        )
    )
    salida = salida.merge(
        origen,
        on=[*claves, "horizonte_origen_extension"],
        how="left",
        validate="many_to_one",
    )
    extendidas = salida.horizonte_extendido & salida.factor_extension.notna()
    salida.loc[extendidas, "factor_residual_asof"] = salida.loc[
        extendidas, "factor_extension"
    ]
    salida.loc[extendidas, "n_residuos_asof"] = salida.loc[
        extendidas, "n_residuos_extension"
    ]
    salida.loc[extendidas, "nivel_residual"] = salida.loc[
        extendidas, "nivel_residual_extension"
    ]
    return salida.drop(
        columns=[
            "factor_extension",
            "n_residuos_extension",
            "nivel_residual_extension",
        ]
    )


def _normalizar_fuente_oleadas(
    fuente: pd.DataFrame,
    salida: pd.DataFrame,
) -> tuple[pd.DataFrame, tuple[str, ...], tuple[str, ...]]:
    """Alinea la salida manual con una clave de forecast completa.

    Los libros operativos suelen identificar el lote por ``lote`` y la base analítica
    por ``lote_id``. Se acepta cualquiera de los dos, siempre que la misma identidad
    exista en ambos paneles; nunca se hace un match solo por fecha.
    """

    columnas_ola = [
        columna
        for columna in (*_COLUMNAS_KG_OLA, *_COLUMNAS_PARTICIPACION_OLA)
        if columna in fuente.columns
    ]
    if not columnas_ola:
        return pd.DataFrame(), (), ()
    faltantes = [clave for clave in _CLAVES if clave not in fuente.columns]
    if faltantes:
        raise ValueError(
            "panel_oleadas requiere las claves de forecast para no mezclar lotes: "
            + ", ".join(faltantes)
        )
    identidad = next(
        (
            columna
            for columna in _IDENTIDADES
            if columna in fuente.columns and columna in salida.columns
        ),
        None,
    )
    if identidad is None:
        raise ValueError(
            "panel_oleadas requiere una identidad compartida entre salida y fuente: "
            "lote_id o lote"
        )
    claves = (*_CLAVES, identidad)
    alineada = fuente[[*claves, *columnas_ola]].copy()
    for columna in ("fecha_emision", "fecha_objetivo"):
        alineada[columna] = pd.to_datetime(alineada[columna], errors="raise").dt.normalize()
    if alineada.duplicated(list(claves)).any():
        raise ValueError("panel_oleadas repite una clave de forecast")
    # La fuente puede haber llegado como Excel o como salida de la macro; comparar
    # fechas normalizadas evita que una hora de carga impida el match.
    return alineada, tuple(columnas_ola), claves


def _anexar_oleadas(
    salida: pd.DataFrame,
    panel_oleadas: pd.DataFrame | None,
) -> tuple[pd.DataFrame, int]:
    """Anexa participaciones y kilos por oleada, conservando sum(olas) == P50."""

    fuente = salida if panel_oleadas is None else panel_oleadas
    if not isinstance(fuente, pd.DataFrame):
        raise TypeError("panel_oleadas debe ser un pandas.DataFrame")
    fuente_n, columnas_ola, claves = _normalizar_fuente_oleadas(fuente, salida)
    trabajo = salida.copy()
    if not columnas_ola:
        for indice in range(1, 4):
            trabajo[f"kg_ola_{indice}_ajustada"] = np.nan
            trabajo[f"participacion_ola_{indice}_ajustada"] = np.nan
        trabajo["tiene_descomposicion_oleadas"] = False
        trabajo["ola_principal"] = "sin_descomposicion_oleadas"
        return trabajo, 0

    trabajo = trabajo.merge(
        fuente_n,
        on=list(claves),
        how="left",
        validate="one_to_one",
        suffixes=("", "_oleadas"),
    )
    matriz = []
    for indice in range(1, 4):
        columna_kg = f"kg_ola_{indice}"
        columna_participacion = f"participacion_ola_{indice}"
        if columna_kg in trabajo:
            valores = _serie_numerica(trabajo, columna_kg).clip(lower=0).fillna(0.0)
        elif columna_participacion in trabajo:
            valores = (
                _serie_numerica(trabajo, columna_participacion).clip(lower=0).fillna(0.0)
            )
        else:
            valores = pd.Series(0.0, index=trabajo.index)
        matriz.append(valores.to_numpy(float))
    bruto = np.vstack(matriz).T
    total = bruto.sum(axis=1)
    valido = np.isfinite(total) & (total > 0)
    participaciones = np.divide(
        bruto,
        total[:, None],
        out=np.zeros_like(bruto),
        where=valido[:, None],
    )
    kilos = participaciones * _serie_numerica(trabajo, "p50_kg").fillna(0).to_numpy(float)[:, None]
    for indice in range(1, 4):
        trabajo[f"kg_ola_{indice}_ajustada"] = kilos[:, indice - 1]
        trabajo[f"participacion_ola_{indice}_ajustada"] = participaciones[:, indice - 1]
    trabajo["tiene_descomposicion_oleadas"] = valido
    principales = np.argmax(participaciones, axis=1) + 1
    trabajo["ola_principal"] = np.where(
        valido,
        pd.Series(principales, index=trabajo.index).map(lambda valor: f"ola_{int(valor)}"),
        "sin_descomposicion_oleadas",
    )
    return trabajo, int(valido.sum())


def _componente_fila(fila: pd.Series, config: ConfiguracionEstadoOleadas) -> dict[str, Any]:
    """Construye la explicación mecánica serializable de una fila."""

    oleadas: dict[str, dict[str, float]] = {}
    for indice in range(1, 4):
        kg = fila.get(f"kg_ola_{indice}_ajustada", np.nan)
        participacion = fila.get(f"participacion_ola_{indice}_ajustada", np.nan)
        if pd.notna(kg) and pd.notna(participacion):
            oleadas[f"ola_{indice}"] = {
                "kg_ajustada": float(kg),
                "participacion": float(participacion),
            }
    factor = float(fila.factor_estado_asof)
    delta = float(fila.delta_estado_kg)
    return {
        "modelo": NOMBRE_MODELO,
        "nivel_base_kg": float(fila.p50_base_kg),
        "factor_estado_asof": factor,
        "delta_estado_kg": delta,
        "estado_asof_activo": bool(fila.estado_asof_activo),
        "horizonte_extendido": bool(fila.horizonte_extendido),
        "oleadas": oleadas,
        "ola_principal": str(fila.ola_principal),
        "driver_mecanico_principal": str(fila.driver_mecanico_principal),
        "escala_intervalo": float(config.escala_intervalo),
        "etiqueta_causal": False,
        "interpretacion": (
            "El factor de estado corrige amplitud con residuales cerrados; las oleadas "
            "solo descomponen mecánicamente el nivel y su timing. No identifica causas."
        ),
    }


def proyectar_estado_oleadas_asof(
    panel: pd.DataFrame,
    *,
    config: ConfiguracionEstadoOleadas | None = None,
    panel_oleadas: pd.DataFrame | None = None,
    horizonte_semanas: int | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Genera el challenger sobre una rejilla R09, sin depender de Excel.

    ``panel`` puede ser una emisión viva sin ``real_kg``; en ese caso el factor es
    uno hasta que existan semanas cerradas. Para replay, ``real_kg`` se usa solo si
    ``fecha_objetivo + 6 días < fecha_emision``. ``panel_oleadas`` es opcional y
    debe aportar ``campania``, emisión, objetivo y una identidad compartida
    (``lote_id`` o ``lote``), junto con ``kg_ola_1..3`` o sus participaciones.
    Puede ser la salida de ``proyectar_oleadas_horizonte`` adaptada al lote y a
    la emisión.
    ``horizonte_semanas`` completa la cola cuando el panel R09 no trae todas las
    semanas solicitadas; esas filas se marcan como ``horizonte_extendido``.
    """

    config = config or CONFIGURACION_CONGELADA
    if not isinstance(config, ConfiguracionEstadoOleadas):
        raise TypeError("config debe ser ConfiguracionEstadoOleadas")
    preparado = _preparar_panel(panel)
    preparado, n_horizontes_extendidos = _extender_horizonte(
        preparado, horizonte_semanas
    )
    salida = aplicar_calibracion_residual_asof(preparado, config.residual)
    salida = _heredar_factor_extension(salida, config)
    salida["p50_base_kg"] = pd.to_numeric(salida["p50_base_kg"], errors="coerce").clip(
        lower=0
    )
    salida["factor_estado_asof"] = pd.to_numeric(
        salida["factor_residual_asof"], errors="coerce"
    ).fillna(1.0)
    salida["horizonte_extendido"] = salida["horizonte_extendido"].fillna(False).astype(bool)
    salida["p50_kg"] = (
        salida["p50_base_kg"] * salida["factor_estado_asof"]
    ).clip(lower=0)
    salida["delta_estado_kg"] = salida["p50_kg"] - salida["p50_base_kg"]
    salida = _aplicar_intervalos(salida, config)
    fuente_oleadas = preparado if panel_oleadas is None else panel_oleadas
    salida, n_oleadas = _anexar_oleadas(salida, fuente_oleadas)
    salida["estado_asof_activo"] = ~np.isclose(
        salida["factor_estado_asof"], 1.0, rtol=0.0, atol=1e-12
    )
    salida["driver_mecanico_principal"] = np.where(
        salida["tiene_descomposicion_oleadas"],
        salida["ola_principal"],
        np.where(salida["estado_asof_activo"], "estado_asof", "nivel_r09"),
    )
    salida["modelo"] = NOMBRE_MODELO
    salida["version_modelo"] = VERSION_MODELO
    salida["version_fuente"] = VERSION_MODELO
    salida["dependencia_numerica"] = "R09_publicado + residuales_asof"
    salida["configuracion_estado_oleadas"] = [asdict(config)] * len(salida)
    salida["componentes"] = [
        _componente_fila(fila, config) for _, fila in salida.iterrows()
    ]
    metadata: dict[str, Any] = {
        "modelo": NOMBRE_MODELO,
        "version": VERSION_MODELO,
        "configuracion": asdict(config),
        "n_filas": int(len(salida)),
        "n_filas_con_oleadas": n_oleadas,
        "horizonte_solicitado": horizonte_semanas,
        "n_filas_horizonte_extendido": int(n_horizontes_extendidos),
        "regla_horizonte_extendido": (
            "arrastre del ultimo P50 R09 por lote y emision; hereda el factor de estado "
            "de la ultima semana publicada"
        ),
        "fuente_nivel": "R09_publicado",
        "usa_excel_para_calcular": False,
        "usa_excel_para_explicar_si_se_entrega": True,
        "sin_fuga": True,
        "publicable": False,
    }
    return salida, metadata


__all__ = [
    "CONFIGURACION_CONGELADA",
    "ConfiguracionEstadoOleadas",
    "NOMBRE_MODELO",
    "VERSION_MODELO",
    "proyectar_estado_oleadas_asof",
]
