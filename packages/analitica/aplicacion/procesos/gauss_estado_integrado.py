"""Integración del nivel R09 con la forma Gaussiana y el estado as-of.

La curva de oleadas y el nivel total resuelven problemas distintos. El ajuste
automático de X/O/N/A/B describe bien una forma temporal, pero en el replay actual
subestima la escala total. R09, en cambio, ya contiene un nivel operativo que no
conviene descartar. Este módulo normaliza la forma Gaussian al total R09 disponible,
aplica opcionalmente el corrector de estado as-of y conserva la descomposición P1/P2/P3.

La salida es un challenger: no lee Excel, no usa reales posteriores a la emisión y no
declara causalidad. Cuando R09 no trae H6, la sexta semana proviene de la cola
Gaussiana escalada y queda marcada como extendida.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
import pandas as pd

from analitica.dominio.compartido import lunes_semana
from analitica.dominio.versiones import banda_horizonte

from ..parametros.oleadas_candidato import proyectar_universo_automatico_oleadas
from .estado_oleadas import (
    ConfiguracionEstadoOleadas,
    proyectar_estado_oleadas_asof,
)

NOMBRE_MODELO = "HibridoGaussEstado_v1"
VERSION_MODELO = "r09_nivel_gaussian_shape_estado_asof_h6_v1"

_CLAVES = (
    "campania",
    "lote_id",
    "fecha_emision",
    "fecha_objetivo",
    "horizonte_semanas",
)
_CLAVES_LOTE = ("campania", "modulo", "turno", "lote")
_COLUMNAS_GAUSS = (
    "kg",
    "kg_ola_1",
    "kg_ola_2",
    "kg_ola_3",
    "frutos_por_planta",
    "peso_baya_g",
)


def _texto(serie: pd.Series) -> pd.Series:
    salida = serie.astype("string").str.strip().str.upper()
    return salida.mask(
        salida.isna()
        | salida.eq("")
        | salida.str.casefold().isin({"nan", "none", "nat"})
    )


def _normalizar_panel(panel: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(panel, pd.DataFrame) or panel.empty:
        raise ValueError("panel_r09 debe ser un DataFrame no vacío")
    requeridas = {
        "campania",
        "fecha_emision",
        "fecha_objetivo",
        "horizonte_semanas",
        "p50_kg",
        "fundo",
        "modulo",
        "lote",
    }
    faltantes = sorted(requeridas - set(panel.columns))
    if faltantes:
        raise ValueError("panel_r09 no contiene: " + ", ".join(faltantes))
    salida = panel.copy()
    for columna in ("campania", "fundo", "modulo", "lote"):
        salida[columna] = _texto(salida[columna])
    if "turno" not in salida:
        salida["turno"] = pd.NA
    else:
        salida["turno"] = _texto(salida["turno"])
    if "lote_id" not in salida:
        salida["lote_id"] = (
            salida.modulo.fillna("")
            + "|"
            + salida.turno.fillna("")
            + "|"
            + salida.lote.fillna("")
        )
    salida["lote_id"] = _texto(salida["lote_id"])
    # El adaptador de exportaciones planas conserva la identidad física en
    # ``modulo|turno|lote`` y el backtest no siempre vuelve a separar el turno.
    # Recuperarlo es seguro porque solo se acepta el formato de tres segmentos;
    # un lote_id opaco no se interpreta por posición.
    partes_lote_id = salida["lote_id"].str.split("|", expand=True)
    if partes_lote_id.shape[1] >= 3:
        turno_embebido = partes_lote_id[1]
    else:
        turno_embebido = pd.Series(pd.NA, index=salida.index, dtype="string")
    salida["turno"] = salida["turno"].where(salida["turno"].notna(), turno_embebido)
    salida["fecha_emision"] = pd.to_datetime(
        salida.fecha_emision, errors="raise"
    ).dt.normalize()
    salida["fecha_objetivo"] = pd.to_datetime(
        salida.fecha_objetivo, errors="raise"
    ).dt.normalize()
    salida["horizonte_semanas"] = pd.to_numeric(
        salida.horizonte_semanas, errors="raise"
    ).astype(int)
    salida["p50_kg"] = pd.to_numeric(salida.p50_kg, errors="coerce")
    if salida.p50_kg.isna().any() or salida.p50_kg.lt(0).any():
        raise ValueError("panel_r09 contiene p50_kg inválido")
    if salida.duplicated(list(_CLAVES)).any():
        raise ValueError("panel_r09 repite una clave lote-emisión-objetivo")
    if "real_kg" not in salida:
        salida["real_kg"] = np.nan
    return salida


def _nombre_columna(valor: object) -> str:
    texto = unicodedata.normalize("NFKD", str(valor))
    texto = "".join(caracter for caracter in texto if not unicodedata.combining(caracter))
    return "".join(caracter for caracter in texto.casefold() if caracter.isalnum())


def _alias_columna(tabla: pd.DataFrame, nombres: Sequence[str]) -> str | None:
    indice = {_nombre_columna(columna): str(columna) for columna in tabla.columns}
    for nombre in nombres:
        encontrada = indice.get(_nombre_columna(nombre))
        if encontrada is not None:
            return encontrada
    return None


def _serie_texto_alias(
    tabla: pd.DataFrame,
    nombres: Sequence[str],
) -> pd.Series:
    columna = _alias_columna(tabla, nombres)
    if columna is None:
        return pd.Series(pd.NA, index=tabla.index, dtype="string")
    return _texto(tabla[columna])


def _serie_numero_alias(tabla: pd.DataFrame, nombres: Sequence[str]) -> pd.Series:
    columna = _alias_columna(tabla, nombres)
    if columna is None:
        return pd.Series(np.nan, index=tabla.index, dtype=float)
    return pd.to_numeric(tabla[columna], errors="coerce")


def _serie_fecha_alias(tabla: pd.DataFrame, nombres: Sequence[str]) -> pd.Series:
    columna = _alias_columna(tabla, nombres)
    if columna is None:
        return pd.Series(pd.NaT, index=tabla.index, dtype="datetime64[ns]")
    salida = pd.to_datetime(tabla[columna], errors="coerce").dt.normalize()
    return salida.mask(salida.dt.year.lt(2000))


def _identidad_fisica(tabla: pd.DataFrame) -> pd.Series:
    partes = [tabla[columna] for columna in ("modulo", "turno", "lote")]
    valido = pd.concat(partes, axis=1).notna().all(axis=1)
    salida = partes[0].fillna("")
    for parte in partes[1:]:
        salida = salida + "|" + parte.fillna("")
    return salida.mask(~valido)


def _completar_turno_desde_cosecha(
    panel: pd.DataFrame,
    cosecha: pd.DataFrame | None,
) -> pd.DataFrame:
    if cosecha is None or not isinstance(cosecha, pd.DataFrame) or cosecha.empty:
        return panel
    fuente = _normalizar_identidad_fuente(cosecha)
    if "turno" not in fuente or not fuente.turno.notna().any():
        return panel
    salida = panel.copy()
    if "turno" not in salida:
        salida["turno"] = pd.NA
    salida["turno"] = _texto(salida["turno"])
    por_lote_id = (
        fuente.dropna(subset=["lote_id", "turno"])
        .groupby("lote_id", dropna=False)["turno"]
        .agg(n_turnos="nunique", turno="first")
    )
    por_lote_id = por_lote_id.loc[por_lote_id.n_turnos.eq(1), "turno"]
    turno = salida["lote_id"].map(por_lote_id)
    salida["turno"] = salida["turno"].where(salida["turno"].notna(), turno)
    modulo_lote = (
        fuente.dropna(subset=["campania", "modulo", "lote", "turno"])
        .assign(
            __modulo_lote=lambda tabla: (
                tabla.campania + "|" + tabla.modulo + "|" + tabla.lote
            )
        )
        .groupby("__modulo_lote", dropna=False)["turno"]
        .agg(n_turnos="nunique", turno="first")
    )
    modulo_lote = modulo_lote.loc[modulo_lote.n_turnos.eq(1), "turno"]
    clave_modulo_lote = (
        salida["campania"].fillna("")
        + "|"
        + salida["modulo"].fillna("")
        + "|"
        + salida["lote"].fillna("")
    )
    salida["turno"] = salida["turno"].where(
        salida["turno"].notna(), clave_modulo_lote.map(modulo_lote)
    )
    return salida


def _normalizar_identidad_fuente(tabla: pd.DataFrame) -> pd.DataFrame:
    salida = tabla.copy()
    for canonico, nombres in {
        "campania": ("campania", "campaña", "campana"),
        "fundo": ("fundo", "fundo_ppto", "fundo_operativo", "fundoac"),
        "modulo": ("modulo", "módulo", "modulo_id"),
        "turno": ("turno", "turno_id"),
        "lote": ("lote", "lote_codigo"),
        "lote_id": ("lote_id", "id_lote", "loteid"),
    }.items():
        if canonico in salida:
            salida[canonico] = _texto(salida[canonico])
        else:
            salida[canonico] = _serie_texto_alias(salida, nombres)
    salida["identidad_fisica"] = _identidad_fisica(salida)
    salida["lote_id"] = salida["lote_id"].where(
        salida["lote_id"].notna(), salida["identidad_fisica"]
    )
    return salida


def _agregar_fuente_por_clave(
    fuente: pd.DataFrame,
    claves: Sequence[str],
    *,
    nombre_fecha: str,
    nombre_area: str,
) -> pd.DataFrame:
    if fuente.empty:
        return pd.DataFrame(columns=[*claves, nombre_fecha, nombre_area])
    columnas = [*claves, nombre_fecha, nombre_area]
    validas = fuente[list(claves)].notna().all(axis=1) & fuente[nombre_fecha].notna()
    trabajo = fuente.loc[validas, columnas].copy()
    if trabajo.empty:
        return pd.DataFrame(columns=columnas)
    return (
        trabajo.sort_values(nombre_fecha, kind="stable")
        .groupby(list(claves), as_index=False, dropna=False)
        .agg({nombre_fecha: "last", nombre_area: "max"})
    )


def construir_lotes_gauss_estado(
    panel_r09: pd.DataFrame,
    *,
    maestro_lotes: pd.DataFrame | None = None,
    poda: pd.DataFrame | None = None,
    cosecha: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Reconstruye el contrato físico que necesita la forma Gaussiana.

    El panel R09 aporta la identidad campaña--módulo--turno--lote y las plantas
    publicadas. El maestro aporta área/plantas cuando el backtest no las conserva y
    ``poda`` aporta el pivote del ciclo. Si poda no tiene turno, solo se permite la
    asociación cuando módulo+lote identifica un único lote dentro de la campaña. En
    algunas vistas PostgreSQL el turno solo está en H01; ``cosecha`` puede completarlo
    si el lote tiene un único turno observado.
    """

    panel_entrada = _normalizar_panel(panel_r09)
    panel_entrada = _completar_turno_desde_cosecha(panel_entrada, cosecha)
    panel = _normalizar_panel(panel_entrada)
    columnas_identidad = ["campania", "lote_id", "fundo", "modulo", "turno", "lote"]
    panel = panel.loc[panel[columnas_identidad].notna().all(axis=1)].copy()
    if panel.empty:
        raise ValueError("panel_r09 no contiene identidades físicas completas")
    agregados: dict[str, tuple[str, str]] = {
        columna: (columna, "first")
        for columna in columnas_identidad
        if columna not in {"campania", "lote_id"}
    }
    if "plantas" in panel:
        agregados["plantas_panel"] = ("plantas", "max")
    if "area_ha" in panel:
        agregados["area_panel"] = ("area_ha", "max")
    base = panel.groupby(["campania", "lote_id"], as_index=False, dropna=False).agg(
        **agregados
    )
    for columna in ("plantas_panel", "area_panel"):
        if columna not in base:
            base[columna] = np.nan
    base["__fisica"] = _identidad_fisica(base)
    base["__modulo_lote"] = (
        base["campania"].fillna("")
        + "|"
        + base["modulo"].fillna("")
        + "|"
        + base["lote"].fillna("")
    ).mask(
        base[["campania", "modulo", "lote"]].isna().any(axis=1)
    )

    advertencias: list[str] = []
    maestro_detalle = {
        "filas_entrada": 0,
        "filas_validas": 0,
        "usado": False,
    }
    if maestro_lotes is not None:
        if not isinstance(maestro_lotes, pd.DataFrame):
            raise TypeError("maestro_lotes debe ser un DataFrame o None")
        maestro_detalle["filas_entrada"] = int(len(maestro_lotes))
        maestro = _normalizar_identidad_fuente(maestro_lotes)
        maestro["__area"] = _serie_numero_alias(maestro, ("area_ha", "area", "Area"))
        maestro["__plantas"] = _serie_numero_alias(
            maestro, ("n_plantas", "plantas", "NPlantas")
        )
        maestro["__fecha_pivote"] = _serie_fecha_alias(
            maestro, ("fecha_pivote", "fecha_poda", "fecha_inicio", "FPoda")
        )
        maestro = maestro.loc[maestro.lote_id.notna()].copy()
        maestro_detalle["filas_validas"] = int(len(maestro))
        if not maestro.empty:
            maestro_id = (
                maestro.groupby("lote_id", as_index=False, dropna=False)
                .agg(
                    area_maestro=("__area", "max"),
                    plantas_maestro=("__plantas", "max"),
                    fecha_pivote_maestro=("__fecha_pivote", "max"),
                )
            )
            base = base.merge(maestro_id, on="lote_id", how="left", validate="many_to_one")
            maestro_fisico = (
                maestro.loc[maestro.identidad_fisica.notna()]
                .groupby("identidad_fisica", as_index=False, dropna=False)
                .agg(
                    area_maestro_fisico=("__area", "max"),
                    plantas_maestro_fisico=("__plantas", "max"),
                    fecha_pivote_maestro_fisico=("__fecha_pivote", "max"),
                )
                .rename(columns={"identidad_fisica": "__fisica"})
            )
            base = base.merge(maestro_fisico, on="__fisica", how="left", validate="many_to_one")
            for columna, respaldo in (
                ("area_maestro", "area_maestro_fisico"),
                ("plantas_maestro", "plantas_maestro_fisico"),
                ("fecha_pivote_maestro", "fecha_pivote_maestro_fisico"),
            ):
                base[columna] = base[columna].where(base[columna].notna(), base[respaldo])

    poda_detalle = {"filas_entrada": 0, "filas_validas": 0, "usado": False}
    if poda is not None:
        if not isinstance(poda, pd.DataFrame):
            raise TypeError("poda debe ser un DataFrame o None")
        poda_detalle["filas_entrada"] = int(len(poda))
        poda_n = _normalizar_identidad_fuente(poda)
        poda_n["__fecha_pivote"] = _serie_fecha_alias(
            poda_n, ("fecha_pivote", "fecha_inicio", "fecha_poda", "fecha_dato", "fecha")
        )
        poda_n["__area"] = _serie_numero_alias(poda_n, ("area_ha", "area", "AreaPoda"))
        poda_n["__fisica"] = _identidad_fisica(poda_n)
        poda_n["__modulo_lote"] = (
            poda_n["campania"].fillna("")
            + "|"
            + poda_n["modulo"].fillna("")
            + "|"
            + poda_n["lote"].fillna("")
        ).mask(
            poda_n[["campania", "modulo", "lote"]].isna().any(axis=1)
        )
        campanias_base = set(base.campania.dropna().astype(str))
        campanias_poda = poda_n.campania.notna()
        if not campanias_poda.any() and len(campanias_base) == 1:
            poda_n["campania"] = next(iter(campanias_base))
            campanias_poda = poda_n.campania.notna()
        elif not campanias_poda.any() and len(campanias_base) > 1:
            advertencias.append(
                "poda no contiene campaña y se descartó para evitar mezclar ciclos."
            )
        if not poda_n.empty:
            poda_n["__modulo_lote"] = (
                poda_n["campania"].fillna("")
                + "|"
                + poda_n["modulo"].fillna("")
                + "|"
                + poda_n["lote"].fillna("")
            ).mask(
                poda_n[["campania", "modulo", "lote"]].isna().any(axis=1)
            )
        # La vista SQL de poda puede no traer turno. Solo se completa el lote_id
        # cuando módulo+lote apunta a una única identidad física de la campaña.
        mapa_modulo_lote = (
            base.dropna(subset=["__modulo_lote", "lote_id"])
            .groupby("__modulo_lote", dropna=False)["lote_id"]
            .agg(n_ids="nunique", lote_id="first")
        )
        mapa_modulo_lote = mapa_modulo_lote.loc[
            mapa_modulo_lote.n_ids.eq(1), "lote_id"
        ]
        poda_n["lote_id"] = poda_n["lote_id"].where(
            poda_n["lote_id"].notna(), poda_n["__modulo_lote"].map(mapa_modulo_lote)
        )
        poda_n = poda_n.loc[
            poda_n.campania.notna() & poda_n.__fecha_pivote.notna()
        ].copy()
        poda_detalle["filas_validas"] = int(len(poda_n))
        if not poda_n.empty:
            poda_id = _agregar_fuente_por_clave(
                poda_n,
                ("campania", "lote_id"),
                nombre_fecha="__fecha_pivote",
                nombre_area="__area",
            ).rename(
                columns={
                    "__fecha_pivote": "fecha_pivote_poda",
                    "__area": "area_poda",
                }
            )
            base = base.merge(
                poda_id, on=["campania", "lote_id"], how="left", validate="many_to_one"
            )
            poda_fisica = _agregar_fuente_por_clave(
                poda_n.loc[poda_n.__fisica.notna()],
                ("campania", "__fisica"),
                nombre_fecha="__fecha_pivote",
                nombre_area="__area",
            ).rename(
                columns={
                    "__fecha_pivote": "fecha_pivote_poda_fisica",
                    "__area": "area_poda_fisica",
                }
            )
            base = base.merge(
                poda_fisica,
                on=["campania", "__fisica"],
                how="left",
                validate="many_to_one",
            )
            for columna, respaldo in (
                ("fecha_pivote_poda", "fecha_pivote_poda_fisica"),
                ("area_poda", "area_poda_fisica"),
            ):
                base[columna] = base[columna].where(base[columna].notna(), base[respaldo])

    base["area_ha"] = base["area_panel"]
    base["area_ha"] = base["area_ha"].where(base.area_ha.gt(0), base.get("area_maestro"))
    base["area_ha"] = base["area_ha"].where(base.area_ha.gt(0), base.get("area_poda"))
    base["plantas"] = base["plantas_panel"]
    base["plantas"] = base["plantas"].where(
        base.plantas.gt(0), base.get("plantas_maestro")
    )
    base["fecha_inicio"] = base.get("fecha_pivote_poda", pd.Series(pd.NaT, index=base.index))
    base["fecha_inicio"] = base["fecha_inicio"].where(
        base.fecha_inicio.notna(), base.get("fecha_pivote_maestro")
    )
    salida = base[
        [
            "campania",
            "fundo",
            "modulo",
            "turno",
            "lote",
            "lote_id",
            "area_ha",
            "plantas",
            "fecha_inicio",
        ]
    ].copy()
    validas = (
        salida[["campania", "modulo", "turno", "lote"]].notna().all(axis=1)
        & salida.area_ha.gt(0)
        & salida.plantas.gt(0)
        & salida.fecha_inicio.notna()
    )
    n_validos = int(validas.sum())
    if n_validos == 0:
        raise ValueError(
            "no se pudo reconstruir ningún lote con área, plantas y fecha de poda/inicio"
        )
    salida = salida.loc[validas].reset_index(drop=True)
    maestro_detalle["usado"] = bool(maestro_detalle["filas_validas"])
    poda_detalle["usado"] = bool(poda_detalle["filas_validas"])
    metadata = {
        "lotes_panel": int(base.shape[0]),
        "lotes_validos": n_validos,
        "lotes_descartados": int(len(base) - n_validos),
        "maestro": maestro_detalle,
        "poda": poda_detalle,
        "advertencias": advertencias,
        "sin_fuga": True,
    }
    return salida, metadata


def _normalizar_emision(fecha_emision: object) -> pd.Timestamp:
    fecha = pd.Timestamp(fecha_emision).normalize()
    if pd.isna(fecha):
        raise ValueError("fecha_emision no es válida")
    return fecha


def _contexto_emision(
    contexto_por_emision: Mapping[object, Mapping[tuple[str, ...], Mapping[str, Any]]] | None,
    fecha: pd.Timestamp,
) -> Mapping[tuple[str, ...], Mapping[str, Any]] | None:
    if contexto_por_emision is None:
        return None
    for clave, valor in contexto_por_emision.items():
        if pd.Timestamp(clave).normalize() == fecha:
            return valor
    return None


def _lote_id(tabla: pd.DataFrame) -> pd.Series:
    return (
        _texto(tabla.modulo).fillna("")
        + "|"
        + _texto(tabla.turno).fillna("")
        + "|"
        + _texto(tabla.lote).fillna("")
    )


def _normalizar_gauss(gauss: pd.DataFrame) -> pd.DataFrame:
    salida = gauss.copy()
    for columna in ("campania", "modulo", "turno", "lote"):
        salida[columna] = _texto(salida[columna])
    salida["lote_id"] = _lote_id(salida)
    salida["fecha_emision"] = pd.to_datetime(
        salida.fecha_emision, errors="raise"
    ).dt.normalize()
    salida["fecha_objetivo"] = pd.to_datetime(
        salida.fecha_objetivo, errors="raise"
    ).dt.normalize()
    salida["horizonte_semanas"] = pd.to_numeric(
        salida.horizonte_semanas, errors="raise"
    ).astype(int)
    for columna in _COLUMNAS_GAUSS:
        if columna not in salida:
            salida[columna] = np.nan
        salida[columna] = pd.to_numeric(salida[columna], errors="coerce")
    requeridas = [*_CLAVES, "kg", "kg_ola_1", "kg_ola_2", "kg_ola_3"]
    salida = salida.dropna(subset=[columna for columna in requeridas if columna in salida])
    if salida.duplicated(list(_CLAVES)).any():
        raise ValueError("la forma Gaussiana repite una clave lote-emisión-objetivo")
    return salida


def _forma_por_lote_emision(
    r09: pd.DataFrame,
    gauss: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Calcula el factor que lleva la suma Gaussiana al total R09 del lote."""

    claves = ["campania", "lote_id", "fecha_emision"]
    comun = r09.merge(
        gauss[
            [
                *_CLAVES,
                "kg",
                "kg_ola_1",
                "kg_ola_2",
                "kg_ola_3",
                "forma_fuente",
            ]
        ],
        on=list(_CLAVES),
        how="left",
        suffixes=("", "_gauss"),
        validate="one_to_one",
    )
    valido = comun.kg.notna() & comun.p50_kg.notna()
    totales = (
        comun.loc[valido]
        .groupby(claves, as_index=False, dropna=False)
        .agg(
            total_r09_kg=("p50_kg", "sum"),
            total_gauss_kg=("kg", "sum"),
            filas_comunes=("kg", "count"),
        )
    )
    totales["factor_escala_gaussiana"] = np.where(
        totales.total_gauss_kg.gt(0),
        totales.total_r09_kg / totales.total_gauss_kg,
        np.nan,
    )
    comun = comun.merge(totales, on=claves, how="left", validate="many_to_one")
    comun["kg_gauss_escalado"] = (
        comun["kg"] * comun["factor_escala_gaussiana"]
    )
    for indice in range(1, 4):
        comun[f"kg_ola_{indice}_escalado"] = (
            comun[f"kg_ola_{indice}"] * comun["factor_escala_gaussiana"]
        )
    return comun, totales


def _agregar_h6(
    base: pd.DataFrame,
    forma: pd.DataFrame,
    *,
    fecha_emision: pd.Timestamp,
    peso_forma_gaussiana: float,
) -> tuple[pd.DataFrame, int]:
    """Agrega H6 solo para lotes con forma as-of y una cola R09."""

    h6 = forma[forma.horizonte_semanas.eq(6)].copy()
    if h6.empty:
        return base, 0
    existentes = set(
        zip(
            base.campania.astype(str),
            base.lote_id.astype(str),
            base.fecha_emision,
            base.horizonte_semanas,
            strict=True,
        )
    )
    filas: list[dict[str, Any]] = []
    for _, fila in h6.iterrows():
        clave_h6 = (
            str(fila.campania),
            str(fila.lote_id),
            fecha_emision,
            6,
        )
        if clave_h6 in existentes or pd.isna(fila.factor_escala_gaussiana):
            continue
        previos = base[
            base.campania.eq(fila.campania)
            & base.lote_id.eq(fila.lote_id)
            & base.fecha_emision.eq(fecha_emision)
        ].sort_values("horizonte_semanas")
        if previos.empty:
            continue
        registro = previos.iloc[-1].to_dict()
        registro["fecha_objetivo"] = fecha_emision + pd.to_timedelta(42, unit="D")
        registro["horizonte_semanas"] = 6
        registro["banda_horizonte"] = banda_horizonte(6)
        for columna in (
            "real_kg",
            "peso_real_g",
            "plantas_reales",
            "frutos_reales_por_planta",
            "frutos_reales_por_planta_catalogo",
        ):
            if columna in registro:
                registro[columna] = np.nan
        registro["p50_r09_kg"] = np.nan
        registro["p50_gauss_kg"] = float(fila.kg)
        registro["p50_gauss_escalado_kg"] = float(fila.kg_gauss_escalado)
        registro["p50_kg"] = float(
            (1.0 - peso_forma_gaussiana) * 0.0
            + peso_forma_gaussiana * fila.kg_gauss_escalado
        )
        registro["factor_escala_gaussiana"] = float(fila.factor_escala_gaussiana)
        registro["peso_forma_gaussiana"] = float(peso_forma_gaussiana)
        registro["forma_gaussiana_asof"] = True
        registro["forma_asof"] = True
        registro["forma_fuente"] = str(fila.get("forma_fuente", "gaussiana_asof"))
        registro["horizonte_extendido"] = True
        registro["horizonte_origen_extension"] = int(previos.iloc[-1].horizonte_semanas)
        registro["fuente_horizonte"] = (
            f"cola_{registro['forma_fuente']}_escalada_asof"
        )
        filas.append(registro)
    if not filas:
        return base, 0
    return pd.concat([base, pd.DataFrame(filas)], ignore_index=True, sort=False), len(filas)


def _construir_panel_gaussiano(
    panel: pd.DataFrame,
    lotes: pd.DataFrame,
    cosecha: pd.DataFrame | None,
    fecha_emision: pd.Timestamp,
    *,
    semanas: int,
    peso_forma_gaussiana: float,
    modelo_contexto: Any | None,
    panel_oleadas_manual: pd.DataFrame | None,
    contexto_por_emision: Mapping[
        object, Mapping[tuple[str, ...], Mapping[str, Any]]
    ]
    | None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    target = panel[
        panel.fecha_emision.eq(fecha_emision)
        & panel.horizonte_semanas.between(1, int(semanas))
    ].copy().reset_index(drop=True)
    if target.empty:
        raise ValueError("panel_r09 no tiene filas para fecha_emision")
    contexto = _contexto_emision(contexto_por_emision, fecha_emision)
    formas: list[pd.DataFrame] = []
    manifiestos: list[dict[str, Any]] = []
    for campania in sorted(target.campania.dropna().astype(str).unique()):
        lotes_campania = lotes[
            lotes.campania.astype(str).str.upper().eq(campania.upper())
        ].copy()
        if lotes_campania.empty:
            continue
        forma, metadata = proyectar_universo_automatico_oleadas(
            lotes_campania,
            cosecha,
            fecha_emision,
            semanas=semanas,
            fecha_corte=fecha_emision,
            modelo_contexto=modelo_contexto,
            contexto_por_lote=contexto,
        )
        formas.append(_normalizar_gauss(forma))
        manifiestos.append(
            {
                "campania": campania,
                "lotes": int(len(lotes_campania)),
                "filas": int(len(forma)),
                "lotes_con_historia_asof": int(metadata["lotes_con_historia_asof"]),
                "lotes_con_modelo_contexto": int(
                    metadata["lotes_con_modelo_contexto"]
                ),
            }
        )
    if not formas:
        raise ValueError("no se pudo construir forma Gaussiana para la emisión")
    forma = pd.concat(formas, ignore_index=True, sort=False)
    forma["forma_fuente"] = "gaussiana_asof"
    n_forma_manual = 0
    if panel_oleadas_manual is not None:
        manual = _normalizar_gauss(panel_oleadas_manual)
        manual = manual[
            manual.fecha_emision.eq(fecha_emision)
            & manual.campania.isin(target.campania.dropna().unique())
        ].copy()
        if not manual.empty:
            manual["forma_fuente"] = "manual_excel_asof"
            manual["__clave_forma"] = manual[list(_CLAVES)].astype(str).agg(
                "|".join, axis=1
            )
            forma["__clave_forma"] = forma[list(_CLAVES)].astype(str).agg(
                "|".join, axis=1
            )
            forma = pd.concat(
                [
                    manual,
                    forma.loc[
                        ~forma["__clave_forma"].isin(
                            set(manual["__clave_forma"])
                        )
                    ],
                ],
                ignore_index=True,
                sort=False,
            )
            n_forma_manual = int(len(manual))
            forma = forma.drop(columns=["__clave_forma"])
    comun, totales = _forma_por_lote_emision(target, forma)
    claves_escala = [
        "campania",
        "lote_id",
        "fecha_emision",
        "factor_escala_gaussiana",
    ]
    forma_h6_completa = forma[forma.horizonte_semanas.eq(6)].merge(
        totales[claves_escala],
        on=["campania", "lote_id", "fecha_emision"],
        how="inner",
        validate="many_to_one",
    )
    forma_h6_completa["kg_gauss_escalado"] = (
        forma_h6_completa.kg
        * forma_h6_completa.factor_escala_gaussiana
    )
    for indice in range(1, 4):
        forma_h6_completa[f"kg_ola_{indice}_escalado"] = (
            forma_h6_completa[f"kg_ola_{indice}"]
            * forma_h6_completa.factor_escala_gaussiana
        )
    # Para extender H6 solo se necesitan las filas de la cola. Mantenerlas separadas
    # evita concatenar columnas R09 que son completamente nulas en la forma as-of.
    forma_completa = forma_h6_completa.drop_duplicates(
        list(_CLAVES), keep="first"
    )
    salida = target.copy()
    salida["p50_r09_kg"] = salida.p50_kg
    salida["p50_gauss_kg"] = comun["kg"]
    salida["p50_gauss_escalado_kg"] = comun["kg_gauss_escalado"]
    salida["factor_escala_gaussiana"] = comun["factor_escala_gaussiana"]
    salida["peso_forma_gaussiana"] = float(peso_forma_gaussiana)
    # Una forma con kilos cero en todas las semanas publicadas no tiene escala
    # identificable. En ese caso se conserva el nivel R09; marcarla como válida
    # produciría NaN al mezclar ``p50_gauss_escalado_kg``.
    forma_valida = comun.kg.notna() & comun.factor_escala_gaussiana.notna()
    salida["forma_asof"] = forma_valida
    salida["forma_fuente"] = comun["forma_fuente"].where(
        forma_valida, "sin_forma_asof"
    )
    salida["forma_gaussiana_asof"] = forma_valida & salida.forma_fuente.eq(
        "gaussiana_asof"
    )
    salida["p50_kg"] = np.where(
        forma_valida,
        (1.0 - peso_forma_gaussiana) * salida.p50_r09_kg
        + peso_forma_gaussiana * salida.p50_gauss_escalado_kg,
        salida.p50_r09_kg,
    )
    salida["p50_kg"] = pd.to_numeric(salida.p50_kg, errors="coerce").clip(lower=0)
    if "horizonte_extendido" not in salida:
        salida["horizonte_extendido"] = False
    # Se conservan solo las claves de la forma para que el estado pueda repartir el
    # P50 corregido sin inventar participaciones de lotes sin ajuste.
    panel_oleadas = comun.loc[forma_valida, list(_CLAVES)].copy()
    for indice in range(1, 4):
        panel_oleadas[f"kg_ola_{indice}"] = comun.loc[
            forma_valida, f"kg_ola_{indice}_escalado"
        ].to_numpy(float)
    salida, n_h6 = _agregar_h6(
        salida,
        forma_completa,
        fecha_emision=fecha_emision,
        peso_forma_gaussiana=peso_forma_gaussiana,
    )
    # Si el panel no tenía H6, comun sí tiene la forma y hay que anexar su
    # descomposición con las mismas claves que la fila extendida.
    h6_agregado = salida[
        salida.horizonte_semanas.eq(6) & salida.horizonte_extendido.fillna(False)
    ]
    if not h6_agregado.empty:
        forma_h6 = forma_completa[forma_completa.horizonte_semanas.eq(6)].copy()
        if not forma_h6.empty:
            forma_h6 = forma_h6.merge(
                h6_agregado[list(_CLAVES)],
                on=list(_CLAVES),
                how="inner",
                validate="one_to_one",
            )
            panel_oleadas = pd.concat(
                [panel_oleadas, forma_h6[list(_CLAVES) + [
                    f"kg_ola_{indice}_escalado" for indice in range(1, 4)
                ]].rename(columns={
                    f"kg_ola_{indice}_escalado": f"kg_ola_{indice}"
                    for indice in range(1, 4)
                })],
                ignore_index=True,
                sort=False,
            )
    if panel_oleadas.duplicated(list(_CLAVES)).any():
        panel_oleadas = panel_oleadas.drop_duplicates(list(_CLAVES), keep="last")
    metadata = {
        "emision": fecha_emision.strftime("%Y-%m-%d"),
        "filas_r09_emision": int(len(target)),
        "filas_con_forma_gaussiana": int(salida.forma_gaussiana_asof.fillna(False).sum()),
        "filas_h6_gaussianas": int(n_h6),
        "lotes_sin_forma": int(
            salida.loc[~salida.forma_asof.fillna(False), "lote_id"].nunique()
        ),
        "totales_escala": int(len(totales)),
        "filas_con_forma_asof": int(salida.forma_asof.fillna(False).sum()),
        "filas_con_forma_manual": n_forma_manual,
        "forma_por_campania": manifiestos,
        "peso_forma_gaussiana": float(peso_forma_gaussiana),
    }
    return salida, panel_oleadas, metadata


def proyectar_gauss_estado_asof(
    panel_r09: pd.DataFrame,
    lotes: pd.DataFrame,
    cosecha: pd.DataFrame | None,
    fecha_emision: object,
    *,
    semanas: int = 6,
    peso_forma_gaussiana: float = 1.0,
    config_estado: ConfiguracionEstadoOleadas | None = None,
    modelo_contexto: Any | None = None,
    panel_oleadas_manual: pd.DataFrame | None = None,
    contexto_por_emision: Mapping[
        object, Mapping[tuple[str, ...], Mapping[str, Any]]
    ]
    | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Proyecta una emisión con nivel R09, forma Gaussian/manual y estado as-of.

    ``panel_r09`` puede contener todo el histórico versionado. Solo se sustituyen las
    filas de ``fecha_emision`` solicitada; los cierres anteriores permanecen disponibles
    para el corrector de estado y se filtran as-of por su propia regla.
    ``panel_oleadas_manual`` puede aportar la forma del libro para las claves que
    contenga; las claves faltantes se completan con la forma Gaussiana as-of.
    """

    if not 6 <= int(semanas) <= 52:
        raise ValueError("semanas debe estar entre 6 y 52")
    if not 0 <= float(peso_forma_gaussiana) <= 1:
        raise ValueError("peso_forma_gaussiana debe estar entre cero y uno")
    fecha = _normalizar_emision(fecha_emision)
    panel = _normalizar_panel(panel_r09)
    salida_target, panel_oleadas, metadata_forma = _construir_panel_gaussiano(
        panel,
        lotes,
        cosecha,
        fecha,
        semanas=int(semanas),
        peso_forma_gaussiana=float(peso_forma_gaussiana),
        modelo_contexto=modelo_contexto,
        panel_oleadas_manual=panel_oleadas_manual,
        contexto_por_emision=contexto_por_emision,
    )
    claves_target = list(_CLAVES)
    # Evita depender de la semántica de índices de pandas cuando hay columnas de
    # fechas con distintos dtypes: las claves se comparan como strings estables.
    def firma(tabla: pd.DataFrame) -> pd.Series:
        return tabla[claves_target].astype(str).agg("|".join, axis=1)

    firmas_target = set(firma(salida_target))
    historico = panel.loc[~firma(panel).isin(firmas_target)].copy()
    panel_integrado = pd.concat([historico, salida_target], ignore_index=True, sort=False)
    salida_estado, metadata_estado = proyectar_estado_oleadas_asof(
        panel_integrado,
        config=config_estado,
        panel_oleadas=panel_oleadas,
        horizonte_semanas=int(semanas),
    )
    salida = salida_estado[
        salida_estado.fecha_emision.eq(fecha)
        & salida_estado.horizonte_semanas.between(1, int(semanas))
    ].copy()
    salida["modelo"] = NOMBRE_MODELO
    salida["version_modelo"] = VERSION_MODELO
    salida["version_fuente"] = VERSION_MODELO
    salida["dependencia_numerica"] = "R09_nivel + forma_gaussiana_asof + estado_asof"
    salida["usa_excel_para_calcular"] = False
    salida["etiqueta_causal"] = False
    componentes = []
    for _, fila in salida.iterrows():
        componente = dict(fila.componentes) if isinstance(fila.componentes, dict) else {}
        componente.update(
            {
                "modelo": NOMBRE_MODELO,
                "modelo_base_estado": "HibridoEstadoOleadas_v1",
                "nivel_fuente": "R09_publicado",
                "forma_fuente": str(fila.get("forma_fuente", "sin_forma_asof")),
                "forma_fuente_fila": str(fila.get("forma_fuente", "sin_forma_asof")),
                "factor_escala_gaussiana": (
                    float(fila.factor_escala_gaussiana)
                    if pd.notna(fila.get("factor_escala_gaussiana"))
                    else None
                ),
                "peso_forma_gaussiana": float(peso_forma_gaussiana),
                "etiqueta_causal": False,
                "interpretacion": (
                    "R09 fija el nivel operativo; la forma Gaussiana reparte el nivel "
                    "entre horizontes y P1/P2/P3. El estado corrige con cierres as-of; "
                    "ninguna parte prueba causalidad."
                ),
            }
        )
        componentes.append(componente)
    salida["componentes"] = componentes
    metadata: dict[str, Any] = {
        "modelo": NOMBRE_MODELO,
        "version": VERSION_MODELO,
        "fecha_emision": fecha.strftime("%Y-%m-%d"),
        "semanas": int(semanas),
        "peso_forma_gaussiana": float(peso_forma_gaussiana),
        "usa_forma_manual": panel_oleadas_manual is not None,
        "usa_excel_para_calcular": False,
        "usa_excel_para_explicar_si_se_entrega": True,
        "sin_fuga": bool(metadata_estado.get("sin_fuga", True)),
        "publicable": False,
        "forma": metadata_forma,
        "estado": metadata_estado,
        "filas_salida": int(len(salida)),
        "filas_h6_extendido": int(
            salida.get("horizonte_extendido", pd.Series(False, index=salida.index))
            .fillna(False)
            .sum()
        ),
    }
    return salida.reset_index(drop=True), metadata


def _normalizar_emisiones_replay(
    panel: pd.DataFrame,
    fechas_emision: Sequence[object] | None,
) -> tuple[pd.Timestamp, ...]:
    valores = (
        panel.fecha_emision.dropna().unique()
        if fechas_emision is None
        else fechas_emision
    )
    emisiones = tuple(sorted({pd.Timestamp(valor).normalize() for valor in valores}))
    if not emisiones or any(pd.isna(valor) for valor in emisiones):
        raise ValueError("fechas_emision debe contener fechas válidas")
    return emisiones


def _ultima_semana_completa(
    cosecha: pd.DataFrame | None,
) -> tuple[pd.Timestamp | None, pd.Timestamp | None]:
    if cosecha is None or not isinstance(cosecha, pd.DataFrame) or cosecha.empty:
        return None, None
    columna_fecha = _alias_columna(
        cosecha, ("fecha", "fecha_cosecha", "fecha_real", "fecha_dato")
    )
    if columna_fecha is None:
        return None, None
    fechas = pd.to_datetime(cosecha[columna_fecha], errors="coerce").dt.normalize()
    fecha_maxima = fechas.max()
    if pd.isna(fecha_maxima):
        return None, None
    ultima = lunes_semana(pd.Timestamp(fecha_maxima) - pd.Timedelta(days=6))
    return pd.Timestamp(fecha_maxima), ultima


def _reales_cosecha_por_clave(cosecha: pd.DataFrame | None) -> pd.DataFrame:
    """Agrega H01 al mismo lote_id que usa la salida, incluyendo la cola H6."""

    if cosecha is None or not isinstance(cosecha, pd.DataFrame) or cosecha.empty:
        return pd.DataFrame(columns=["campania", "lote_id", "fecha_objetivo", "real_cosecha_kg"])
    fuente = _normalizar_identidad_fuente(cosecha)
    columna_fecha = _alias_columna(
        fuente, ("fecha", "fecha_cosecha", "fecha_real", "fecha_dato")
    )
    columna_kg = _alias_columna(fuente, ("kg", "kilogramos", "real_kg", "volumen_kg"))
    if columna_fecha is None or columna_kg is None:
        return pd.DataFrame(columns=["campania", "lote_id", "fecha_objetivo", "real_cosecha_kg"])
    fuente["fecha"] = pd.to_datetime(fuente[columna_fecha], errors="coerce").dt.normalize()
    fuente["kg"] = pd.to_numeric(fuente[columna_kg], errors="coerce")
    validas = (
        fuente[["campania", "lote_id", "fecha"]].notna().all(axis=1)
        & fuente.kg.notna()
    )
    fuente = fuente.loc[validas, ["campania", "lote_id", "fecha", "kg"]].copy()
    if fuente.empty:
        return pd.DataFrame(columns=["campania", "lote_id", "fecha_objetivo", "real_cosecha_kg"])
    fuente["fecha_objetivo"] = lunes_semana(fuente.fecha)
    return fuente.groupby(
        ["campania", "lote_id", "fecha_objetivo"], as_index=False, dropna=False
    ).agg(real_cosecha_kg=("kg", "sum"))


def _metricas_replay(tabla: pd.DataFrame, columna: str) -> dict[str, Any]:
    if tabla.empty or columna not in tabla or "real_kg" not in tabla:
        return {
            "filas": 0,
            "lotes": 0,
            "real_kg": 0.0,
            "pred_kg": 0.0,
            "error_kg": 0.0,
            "wape": np.nan,
            "bias_pct": np.nan,
        }
    incluida = tabla.get(
        "incluye_en_metricas", pd.Series(True, index=tabla.index)
    ).fillna(False)
    pred = pd.to_numeric(tabla[columna], errors="coerce")
    real = pd.to_numeric(tabla.real_kg, errors="coerce")
    valida = tabla.loc[incluida.astype(bool) & pred.notna() & real.notna()].copy()
    if valida.empty:
        return {
            "filas": 0,
            "lotes": 0,
            "real_kg": 0.0,
            "pred_kg": 0.0,
            "error_kg": 0.0,
            "wape": np.nan,
            "bias_pct": np.nan,
        }
    error = pd.to_numeric(valida[columna], errors="coerce") - pd.to_numeric(
        valida.real_kg, errors="coerce"
    )
    real_total = float(pd.to_numeric(valida.real_kg, errors="coerce").abs().sum())
    return {
        "filas": int(len(valida)),
        "lotes": int(valida.lote_id.nunique()) if "lote_id" in valida else 0,
        "real_kg": real_total,
        "pred_kg": float(pd.to_numeric(valida[columna], errors="coerce").sum()),
        "error_kg": float(error.sum()),
        "wape": float(error.abs().sum() / real_total) if real_total else np.nan,
        "bias_pct": float(error.sum() / real_total) if real_total else np.nan,
    }


def _metricas_replay_por_grupo(
    tabla: pd.DataFrame,
    columna: str,
    grupos: Sequence[str],
) -> dict[str, dict[str, Any]]:
    if tabla.empty:
        return {}
    salida: dict[str, dict[str, Any]] = {}
    for clave, bloque in tabla.groupby(list(grupos), sort=True, dropna=False):
        valores = clave if isinstance(clave, tuple) else (clave,)
        etiqueta = "|".join(str(valor) for valor in valores)
        salida[etiqueta] = _metricas_replay(bloque, columna)
    return salida


def _comparar_r09_replay(
    predicciones: pd.DataFrame,
    panel: pd.DataFrame,
) -> dict[str, Any]:
    base = panel[
        [*_CLAVES, "p50_kg", "real_kg"]
    ].rename(columns={"p50_kg": "r09_p50_kg", "real_kg": "real_panel_kg"})
    comparacion = predicciones.merge(
        base,
        on=list(_CLAVES),
        how="inner",
        validate="one_to_one",
    )
    comparacion["real_kg"] = comparacion.real_kg.combine_first(
        comparacion.real_panel_kg
    )
    comparacion["incluye_en_metricas"] = (
        comparacion.incluye_en_metricas
        & comparacion.real_kg.notna()
    )
    r09 = comparacion.assign(p50_kg=comparacion.r09_p50_kg)
    return {
        "filas_comunes": int(len(comparacion)),
        "filas_evaluables": int(comparacion.incluye_en_metricas.sum()),
        "integrado": _metricas_replay(comparacion, "p50_kg"),
        "r09": _metricas_replay(r09, "p50_kg"),
        "integrado_por_horizonte": _metricas_replay_por_grupo(
            comparacion, "p50_kg", ("horizonte_semanas",)
        ),
        "r09_por_horizonte": _metricas_replay_por_grupo(
            r09, "p50_kg", ("horizonte_semanas",)
        ),
    }


def replay_gauss_estado_asof(
    panel_r09: pd.DataFrame,
    lotes: pd.DataFrame,
    cosecha: pd.DataFrame | None,
    fechas_emision: Sequence[object] | None = None,
    *,
    semanas: int = 6,
    peso_forma_gaussiana: float = 1.0,
    config_estado: ConfiguracionEstadoOleadas | None = None,
    modelo_contexto: Any | None = None,
    panel_oleadas_manual: pd.DataFrame | None = None,
    contexto_por_emision: Mapping[
        object, Mapping[tuple[str, ...], Mapping[str, Any]]
    ]
    | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Ejecuta el challenger en varios cortes y devuelve métricas comparables.

    Cada emisión se calcula de forma independiente: la curva automática y el estado solo
    reciben información estrictamente anterior al corte. Las filas cuyo H01 todavía no
    cerró quedan en la salida, pero no entran a las métricas; el cero de una semana
    cerrada sin cosecha sí se considera un observado válido.
    """

    panel = _normalizar_panel(panel_r09)
    emisiones = _normalizar_emisiones_replay(panel, fechas_emision)
    fecha_cierre, ultima_semana = _ultima_semana_completa(cosecha)
    reales_cosecha = _reales_cosecha_por_clave(cosecha)
    salidas: list[pd.DataFrame] = []
    detalles: list[dict[str, Any]] = []
    for emision in emisiones:
        salida, metadata = proyectar_gauss_estado_asof(
            panel,
            lotes,
            cosecha,
            emision,
            semanas=semanas,
            peso_forma_gaussiana=peso_forma_gaussiana,
            config_estado=config_estado,
            modelo_contexto=modelo_contexto,
            panel_oleadas_manual=panel_oleadas_manual,
            contexto_por_emision=contexto_por_emision,
        )
        salida = salida.copy()
        if not reales_cosecha.empty:
            salida = salida.merge(
                reales_cosecha,
                on=["campania", "lote_id", "fecha_objetivo"],
                how="left",
                validate="many_to_one",
            )
            salida["real_kg"] = salida.real_kg.combine_first(salida.real_cosecha_kg)
            salida = salida.drop(columns="real_cosecha_kg")
        if ultima_semana is None:
            salida["incluye_en_metricas"] = False
        else:
            salida["incluye_en_metricas"] = salida.fecha_objetivo.le(ultima_semana)
        salida["real_kg"] = pd.to_numeric(salida.real_kg, errors="coerce")
        salida.loc[
            salida.incluye_en_metricas & salida.real_kg.isna(), "real_kg"
        ] = 0.0
        salida.loc[~salida.incluye_en_metricas, "real_kg"] = np.nan
        salida["fecha_cierre_real"] = fecha_cierre
        salidas.append(salida)
        detalles.append(
            {
                "fecha_emision": emision.strftime("%Y-%m-%d"),
                "filas": int(len(salida)),
                "filas_evaluables": int(salida.incluye_en_metricas.sum()),
                "forma": metadata["forma"],
                "estado": metadata["estado"],
            }
        )
    predicciones = pd.concat(salidas, ignore_index=True, sort=False)
    metadata_replay: dict[str, Any] = {
        "modelo": NOMBRE_MODELO,
        "version": VERSION_MODELO,
        "semanas": int(semanas),
        "emisiones": [fecha.strftime("%Y-%m-%d") for fecha in emisiones],
        "fecha_cierre_real": fecha_cierre.strftime("%Y-%m-%d") if fecha_cierre else None,
        "ultima_semana_completa": (
            ultima_semana.strftime("%Y-%m-%d") if ultima_semana is not None else None
        ),
        "filas_predicciones": int(len(predicciones)),
        "filas_evaluables": int(predicciones.incluye_en_metricas.sum()),
        "metricas": _metricas_replay(predicciones, "p50_kg"),
        "metricas_por_horizonte": _metricas_replay_por_grupo(
            predicciones, "p50_kg", ("horizonte_semanas",)
        ),
        "metricas_por_emision": _metricas_replay_por_grupo(
            predicciones, "p50_kg", ("fecha_emision",)
        ),
        "emisiones_detalle": detalles,
        "publicable": False,
        "sin_fuga": True,
    }
    metadata_replay["comparacion_r09"] = _comparar_r09_replay(predicciones, panel)
    return predicciones, metadata_replay


__all__ = [
    "NOMBRE_MODELO",
    "VERSION_MODELO",
    "construir_lotes_gauss_estado",
    "proyectar_gauss_estado_asof",
    "replay_gauss_estado_asof",
]
