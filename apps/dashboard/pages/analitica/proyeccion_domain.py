"""Reglas puras de la página operativa de Proyección.

La interfaz trabaja temporalmente con la salida operativa ``ModeloOperativoActual_v1``
(Macro Python automática). ``HibridoOcurrenciaOnline_v2`` permanece persistido como
challenger histórico/experimental hasta corregir su tratamiento de semanas futuras.
R09 se conserva como emisión publicada de referencia, no como algoritmo.

Este módulo no importa Dash, no lee Excel y no consulta PostgreSQL; recibe
DataFrames persistidos.
"""

from __future__ import annotations

import datetime as dt
import json
import unicodedata
from collections.abc import Iterable

import numpy as np
import pandas as pd

from analitica.config import etiqueta

MODELO_OPERATIVO_BASE = "ModeloOperativoActual_v1"
MODELO_OPERATIVO_ACTUAL = "ModeloOperativoActual_v1"
R09_REFERENCIA = "R09_publicado"
FUNDOS_OPERATIVOS = ("Arena", "Ayllu", "Kawsay", "Quri")
HORIZONTE_SEMANAS = "6_semanas"
HORIZONTE_CAMPANIA = "campania"

# En la pantalla operativa solo se exponen las comparaciones que un agrónomo puede
# interpretar sin conocer la historia interna de todos los experimentos. Los demás
# modelos siguen persistidos y se consultan en Backtesting/auditoría; no se eliminan.
SERIES_HISTORICAS = {
    R09_REFERENCIA: "R09 publicado · referencia",
    "MacroLegacy_v1": "Modelo Python actual · replay histórico",
    "HibridoOcurrenciaOnline_v2": "Híbrido ocurrencia v2 · challenger",
    "HibridoParametrosAsOf_v1": "Híbrido parámetros as-of · challenger",
}

COLUMNAS_DETALLE = (
    "fundo",
    "modulo",
    "turno",
    "lote",
    "pasada",
    "fecha_inicio",
    "fecha_objetivo",
    "semana_iso",
    "frutos_por_planta",
    "peso_baya_g",
    "plantas",
    "p50_kg",
    "fuente_parametros",
    "nivel_calibracion",
    "fuente_poda",
)

COLUMNAS_TRAZABILIDAD = ("fuente_libro", "fuente_hash")


def _componentes_dict(valor) -> dict:
    if isinstance(valor, dict):
        convertido = valor
    elif isinstance(valor, str):
        try:
            convertido = json.loads(valor)
        except (json.JSONDecodeError, TypeError):
            return {}
    else:
        return {}
    if not isinstance(convertido, dict):
        return {}
    anidado = convertido.get("componentes")
    if isinstance(anidado, dict):
        return {**anidado, **{k: v for k, v in convertido.items() if k != "componentes"}}
    return convertido


def _clave_texto(valor: object) -> str:
    texto = unicodedata.normalize("NFKD", str(valor or ""))
    return " ".join(texto.encode("ascii", "ignore").decode().casefold().split())


def normalizar_fundo(valor: object) -> str | None:
    """Convierte los cinco códigos administrativos en cuatro fundos agronómicos."""
    if valor is None or pd.isna(valor):
        return None
    clave = _clave_texto(valor)
    if clave in {"aqu anqa 1", "arena", "arena azul"} or "arena" in clave:
        return "Arena"
    if clave in {"aqu anqa 4", "ayllu", "ayllu allpa", "ayllu alpa"} or "ayllu" in clave:
        return "Ayllu"
    if clave in {"aqu anqa 3", "aqu anqa 5", "kawsay", "kawsay allpa"} or "kawsay" in clave:
        return "Kawsay"
    if (
        clave in {"aqu anqa 2", "quri", "quri allpa", "qury allpa"}
        or "quri" in clave
        or "qury" in clave
    ):
        return "Quri"
    return str(valor).strip() or None


def normalizar_fundos(tabla: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(tabla, pd.DataFrame) or tabla.empty or "fundo" not in tabla:
        return tabla.copy() if isinstance(tabla, pd.DataFrame) else pd.DataFrame()
    salida = tabla.copy()
    if "fundo_fuente" not in salida:
        salida["fundo_fuente"] = salida["fundo"]
    salida["fundo"] = salida["fundo"].map(normalizar_fundo)
    return salida


def seleccionar_modelo_operativo(estado: dict) -> pd.DataFrame:
    tabla = estado.get("proyeccion_experimental", pd.DataFrame())
    if not isinstance(tabla, pd.DataFrame) or tabla.empty or "modelo" not in tabla:
        return pd.DataFrame()
    return tabla[tabla.modelo.astype(str).eq(MODELO_OPERATIVO_ACTUAL)].copy()


def seleccionar_r09_referencia(estado: dict) -> pd.DataFrame:
    tabla = estado.get("proyeccion", pd.DataFrame())
    if not isinstance(tabla, pd.DataFrame) or tabla.empty or "modelo" not in tabla:
        return pd.DataFrame()
    return tabla[tabla.modelo.astype(str).eq(R09_REFERENCIA)].copy()


def _semana_inicio(serie: pd.Series) -> pd.Series:
    fechas = pd.to_datetime(serie, errors="coerce")
    return fechas - pd.to_timedelta(fechas.dt.weekday, unit="D")


def etiqueta_semana(fecha: object) -> str:
    inicio = pd.to_datetime(fecha, errors="coerce")
    if pd.isna(inicio):
        return "—"
    cierre = inicio + pd.Timedelta(days=6)
    return f"{inicio:%d/%m}–{cierre:%d/%m/%Y}"


def enriquecer(proyeccion: pd.DataFrame, lotes: pd.DataFrame | None = None) -> pd.DataFrame:
    """Normaliza la corrida persistida y expone paña y fuente sin releer el Excel."""
    if not isinstance(proyeccion, pd.DataFrame) or proyeccion.empty:
        return pd.DataFrame() if not isinstance(proyeccion, pd.DataFrame) else proyeccion.copy()
    tabla = normalizar_fundos(proyeccion)
    for columna in ("fecha_objetivo", "fecha_emision", "generado_en"):
        if columna in tabla:
            tabla[columna] = pd.to_datetime(tabla[columna], errors="coerce")
    tabla["p50_kg"] = pd.to_numeric(tabla.get("p50_kg"), errors="coerce")

    componentes = tabla.get("componentes", pd.Series([{}] * len(tabla), index=tabla.index)).map(
        _componentes_dict
    )
    extraidos = {
        "pasada": ("pasada", "Paña"),
        "fecha_inicio": ("fecha_inicio", "Fechaini"),
        "fuente_libro": ("fuente_libro",),
        "fuente_hash": ("fuente_hash",),
        "area_ha": ("area_ha", "Area"),
        "nivel_calibracion": ("nivel_calibracion",),
        "fuente_parametros": ("fuente_parametros",),
        "fuente_poda": ("fuente_poda",),
    }
    for destino, candidatos in extraidos.items():
        valores = componentes.map(
            lambda item, nombres=candidatos: next(
                (item.get(nombre) for nombre in nombres if item.get(nombre) is not None), None
            )
        )
        if destino in tabla:
            tabla[destino] = tabla[destino].where(tabla[destino].notna(), valores)
        else:
            tabla[destino] = valores
    tabla["fecha_inicio"] = pd.to_datetime(tabla["fecha_inicio"], errors="coerce")

    if isinstance(lotes, pd.DataFrame) and not lotes.empty and "lote_id" in lotes:
        atributos = [
            c for c in ("lote_id", "variedad", "turno", "area_ha", "n_plantas") if c in lotes
        ]
        maestro = lotes[atributos].drop_duplicates("lote_id").set_index("lote_id")
        for columna in atributos:
            if columna == "lote_id":
                continue
            mapa = tabla["lote_id"].map(maestro[columna])
            if columna in tabla:
                tabla[columna] = tabla[columna].where(tabla[columna].notna(), mapa)
            else:
                tabla[columna] = mapa
    for columna in (
        "variedad",
        "turno",
        "area_ha",
        "n_plantas",
        "plantas",
        "frutos_por_planta",
        "peso_baya_g",
    ):
        if columna not in tabla:
            tabla[columna] = pd.NA

    tabla["semana_inicio"] = _semana_inicio(tabla["fecha_objetivo"])
    tabla["semana_cierre"] = tabla["semana_inicio"] + pd.Timedelta(days=6)
    tabla["semana_iso"] = tabla["semana_inicio"].dt.isocalendar().week.astype("Int64")
    tabla["rango_semana"] = tabla["semana_inicio"].map(etiqueta_semana)
    return tabla


def preparar_real(real: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(real, pd.DataFrame) or real.empty:
        return pd.DataFrame()
    tabla = normalizar_fundos(real)
    tabla["fecha_objetivo"] = pd.to_datetime(tabla["fecha_objetivo"], errors="coerce")
    tabla["real_kg"] = pd.to_numeric(tabla.get("real_kg"), errors="coerce")
    if "ultima_fecha_real" in tabla:
        tabla["ultima_fecha_real"] = pd.to_datetime(tabla["ultima_fecha_real"], errors="coerce")
    tabla["semana_inicio"] = _semana_inicio(tabla["fecha_objetivo"])
    tabla["semana_cierre"] = tabla["semana_inicio"] + pd.Timedelta(days=6)
    tabla["rango_semana"] = tabla["semana_inicio"].map(etiqueta_semana)
    return tabla


def filtrar_ubicacion(
    tabla: pd.DataFrame,
    fundo: str | Iterable[str] | None = None,
    modulo: str | Iterable[str] | None = None,
    lote: str | Iterable[str] | None = None,
) -> pd.DataFrame:
    if not isinstance(tabla, pd.DataFrame) or tabla.empty:
        return pd.DataFrame()
    salida = tabla.copy()
    for columna, valor in (("fundo", fundo), ("modulo", modulo), ("lote", lote)):
        if valor is None or columna not in salida:
            continue
        if isinstance(valor, str):
            seleccion = [] if valor in {"", "Todos"} else [valor]
        else:
            seleccion = [str(item) for item in valor if item not in (None, "", "Todos")]
        if seleccion:
            salida = salida[salida[columna].astype(str).isin(seleccion)]
    return salida


def preparar_replay_historico(tabla: pd.DataFrame) -> pd.DataFrame:
    """Normaliza predicciones históricas que ya fueron evaluadas contra cosecha real."""
    if not isinstance(tabla, pd.DataFrame) or tabla.empty:
        return pd.DataFrame()
    salida = normalizar_fundos(tabla)
    for columna in ("fecha_emision", "fecha_objetivo", "origen_emision"):
        if columna in salida:
            salida[columna] = pd.to_datetime(salida[columna], errors="coerce")
    for columna in ("p50_kg", "real_kg"):
        salida[columna] = pd.to_numeric(salida.get(columna), errors="coerce")
    # ``real_kg`` puede ser nulo en una predicción válida de una semana cerrada en la
    # que ese lote no cosechó. El cero real se completa después, contra el universo
    # común; exigirlo aquí también eliminaba cobertura antes de la alineación.
    salida = salida.dropna(subset=["modelo", "fecha_objetivo", "p50_kg"])
    return salida


def seleccionar_emision_coherente(tabla: pd.DataFrame) -> pd.DataFrame:
    """Escoge un único vintage por modelo, campaña y semana objetivo.

    La selección se hace primero al nivel de la semana y recién después conserva los
    lotes de esa emisión. Elegir el vintage lote por lote produciría una curva que nunca
    fue emitida realmente y mezclaría horizontes dentro del mismo total semanal.
    """

    if not isinstance(tabla, pd.DataFrame) or tabla.empty:
        return pd.DataFrame()
    requeridas = {"modelo", "campania", "fecha_objetivo"}
    if not requeridas.issubset(tabla.columns):
        return tabla.copy()
    if "fecha_emision" not in tabla and "origen_emision" not in tabla:
        return tabla.copy()

    salida = tabla.copy()
    salida["fecha_objetivo"] = pd.to_datetime(salida["fecha_objetivo"], errors="coerce")
    emision = pd.Series(pd.NaT, index=salida.index, dtype="datetime64[ns]")
    if "fecha_emision" in salida:
        emision = pd.to_datetime(salida["fecha_emision"], errors="coerce")
    if "origen_emision" in salida:
        origen = pd.to_datetime(salida["origen_emision"], errors="coerce")
        emision = origen.combine_first(emision)
    salida["_emision_coherente"] = emision
    salida["_semana_objetivo"] = _semana_inicio(salida["fecha_objetivo"])

    elegible = (
        salida["_emision_coherente"].notna()
        & salida["_semana_objetivo"].notna()
        & salida["_emision_coherente"].lt(salida["_semana_objetivo"])
    )
    if "horizonte_semanas" in salida:
        horizonte = pd.to_numeric(salida["horizonte_semanas"], errors="coerce")
        elegible &= horizonte.ge(1)
    salida = salida.loc[elegible].copy()
    if salida.empty:
        return salida.drop(columns=["_emision_coherente", "_semana_objetivo"])

    claves_semana = ["modelo", "campania", "_semana_objetivo"]
    vintages = (
        salida.groupby(claves_semana, dropna=False)["_emision_coherente"]
        .max()
        .rename("_vintage_elegido")
        .reset_index()
    )
    salida = salida.merge(vintages, on=claves_semana, how="inner")
    salida = salida[salida["_emision_coherente"].eq(salida["_vintage_elegido"])].copy()
    return salida.drop(columns=["_emision_coherente", "_semana_objetivo", "_vintage_elegido"])


def filtrar_periodos_cerrados(
    predicciones: pd.DataFrame,
    reales: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Limita ambos lados a semanas cerradas presentes en la fuente real.

    ``reales`` es el calendario autoritativo ya cerrado por campaña/watermark. Una
    predicción de una semana ausente de ese calendario es futura o parcial: se excluye
    antes del outer join para que nunca se convierta en un ``real_kg = 0`` artificial.
    """

    if not isinstance(reales, pd.DataFrame) or reales.empty:
        return pd.DataFrame(), pd.DataFrame()
    real = reales.copy()
    if not {"campania", "fecha_objetivo"}.issubset(real.columns):
        return pd.DataFrame(), pd.DataFrame()
    real["fecha_objetivo"] = _semana_inicio(real["fecha_objetivo"])
    real = real.dropna(subset=["campania", "fecha_objetivo"])
    periodos = real[["campania", "fecha_objetivo"]].drop_duplicates()

    if not isinstance(predicciones, pd.DataFrame) or predicciones.empty:
        return pd.DataFrame(), real
    pred = predicciones.copy()
    pred["fecha_objetivo"] = _semana_inicio(pred["fecha_objetivo"])
    pred = pred.merge(periodos, on=["campania", "fecha_objetivo"], how="inner")
    return pred, real


def alinear_replay_con_real_comun(
    predicciones: pd.DataFrame,
    reales: pd.DataFrame,
    modelo: str,
) -> pd.DataFrame:
    """Evalúa una serie contra toda la cosecha del período que quiso pronosticar.

    Una fila real sin predicción equivale a una predicción de cero. Una predicción sin
    cosecha equivale a un real de cero. De esta forma cambiar de Python a R09 no cambia
    silenciosamente el denominador del WAPE.
    """

    if not isinstance(predicciones, pd.DataFrame) or predicciones.empty:
        return pd.DataFrame()
    serie = predicciones[predicciones["modelo"].astype(str).eq(str(modelo))].copy()
    if serie.empty or not isinstance(reales, pd.DataFrame) or reales.empty:
        return preparar_replay_historico(serie)

    serie = seleccionar_emision_coherente(normalizar_fundos(serie))
    real = normalizar_fundos(reales)
    for tabla in (serie, real):
        tabla["fecha_objetivo"] = pd.to_datetime(tabla["fecha_objetivo"], errors="coerce")
    serie, real = filtrar_periodos_cerrados(serie, real)
    if serie.empty or real.empty:
        return pd.DataFrame()
    serie["p50_kg"] = pd.to_numeric(serie["p50_kg"], errors="coerce")
    real["real_kg"] = pd.to_numeric(real["real_kg"], errors="coerce")

    # El universo real se define por campaña, no por los períodos en los que el
    # modelo alcanzó a emitir. Si R09 carece de una emisión para una semana real,
    # esa semana debe permanecer en la evaluación como predicción cero; eliminarla
    # aquí hacía que una referencia incompleta pareciera tener 100 % de cobertura.
    campanias_serie = set(serie["campania"].dropna().astype(str))
    if "campania" in real and campanias_serie:
        real = real[real["campania"].astype(str).isin(campanias_serie)].copy()
    claves = ["campania", "lote_id", "fecha_objetivo"]
    ubicacion = ["empresa", "fundo", "modulo", "lote"]
    pred = serie.groupby(claves, as_index=False, dropna=False).agg(
        p50_kg=("p50_kg", "sum"),
        emitio_prediccion=("emitio_prediccion", "max")
        if "emitio_prediccion" in serie
        else ("p50_kg", lambda valores: True),
        **{columna: (columna, "first") for columna in ubicacion if columna in serie.columns},
    )
    real = real.groupby(claves, as_index=False, dropna=False).agg(
        real_kg=("real_kg", "sum"),
        **{columna: (columna, "first") for columna in ubicacion if columna in real.columns},
    )
    salida = pred.merge(real, on=claves, how="outer", suffixes=("_pred", "_real"))
    salida["p50_kg"] = pd.to_numeric(salida["p50_kg"], errors="coerce").fillna(0.0)
    salida["real_kg"] = pd.to_numeric(salida["real_kg"], errors="coerce").fillna(0.0)
    emitio_salida = salida.get("emitio_prediccion", pd.Series(False, index=salida.index))
    salida["emitio_prediccion"] = emitio_salida.map(
        lambda valor: bool(valor) if pd.notna(valor) else False
    )
    salida["modelo"] = str(modelo)
    for columna in ubicacion:
        pred_col = f"{columna}_pred"
        real_col = f"{columna}_real"
        if pred_col in salida and real_col in salida:
            salida[columna] = salida[pred_col].combine_first(salida[real_col])
        elif pred_col in salida:
            salida[columna] = salida[pred_col]
        elif real_col in salida:
            salida[columna] = salida[real_col]
    return salida


def limitar_ventana_semanal(tabla: pd.DataFrame, semanas: object) -> pd.DataFrame:
    """Conserva las últimas semanas objetivo sin alterar mes o campaña."""
    if not isinstance(tabla, pd.DataFrame) or tabla.empty or semanas in (None, "todo"):
        return tabla.copy() if isinstance(tabla, pd.DataFrame) else pd.DataFrame()
    try:
        cantidad = max(1, int(semanas))
    except (TypeError, ValueError):
        return tabla.copy()
    salida = tabla.copy()
    fechas = pd.to_datetime(salida.get("fecha_objetivo"), errors="coerce")
    ultima = fechas.max()
    if pd.isna(ultima):
        return salida.iloc[0:0].copy()
    primera = pd.Timestamp(ultima).normalize() - pd.Timedelta(weeks=cantidad - 1)
    return salida.loc[fechas.ge(primera) & fechas.le(ultima)].copy()


def agrupar_replay_historico(tabla: pd.DataFrame, granularidad: str) -> pd.DataFrame:
    """Agrega real y proyección conservando el indicador de cobertura.

    ``real_kg``/``proyectado_kg`` representan el universo operativo completo:
    una fila real sin emisión se conserva con proyección cero. Las columnas
    ``*_emitido_kg`` se usan exclusivamente para el WAPE condicionado, de modo
    que la pantalla no confunda precisión matemática con cobertura de emisión.
    """
    if not isinstance(tabla, pd.DataFrame) or tabla.empty:
        return pd.DataFrame()
    salida = preparar_replay_historico(tabla)
    if salida.empty:
        return salida
    salida["emitio_prediccion"] = (
        salida.get("emitio_prediccion", pd.Series(True, index=salida.index))
        .fillna(False)
        .astype(bool)
    )
    salida["real_emitido_kg"] = salida["real_kg"].where(salida["emitio_prediccion"], 0.0)
    salida["proyectado_emitido_kg"] = salida["p50_kg"].where(salida["emitio_prediccion"], 0.0)
    salida["semana_inicio"] = _semana_inicio(salida["fecha_objetivo"])
    if granularidad == "mes":
        salida["orden"] = salida["fecha_objetivo"].dt.to_period("M").dt.to_timestamp()
        claves = ["campania", "orden"]
    elif granularidad == "campania":
        salida["orden"] = salida["campania"].astype(str)
        claves = ["campania"]
    else:
        salida["orden"] = salida["semana_inicio"]
        claves = ["campania", "orden"]
    agrupada = (
        salida.groupby(claves, as_index=False, dropna=False)
        .agg(
            real_kg=("real_kg", "sum"),
            proyectado_kg=("p50_kg", "sum"),
            real_emitido_kg=("real_emitido_kg", "sum"),
            proyectado_emitido_kg=("proyectado_emitido_kg", "sum"),
            filas_evaluadas=("emitio_prediccion", "size"),
            filas_emitidas=("emitio_prediccion", "sum"),
            lotes=("lote_id", "nunique") if "lote_id" in salida else ("modelo", "size"),
        )
        .sort_values(claves)
    )
    if granularidad == "campania":
        agrupada["orden"] = agrupada["campania"].astype(str)
        agrupada["etiqueta"] = agrupada["campania"].astype(str)
    elif granularidad == "mes":
        meses = {
            1: "ene",
            2: "feb",
            3: "mar",
            4: "abr",
            5: "may",
            6: "jun",
            7: "jul",
            8: "ago",
            9: "sep",
            10: "oct",
            11: "nov",
            12: "dic",
        }
        agrupada["etiqueta"] = agrupada.apply(
            lambda fila: (
                f"{fila.campania} · {meses[pd.Timestamp(fila.orden).month]} "
                f"{pd.Timestamp(fila.orden).year}"
            ),
            axis=1,
        )
    else:
        agrupada["etiqueta"] = agrupada.apply(
            lambda fila: f"{fila.campania} · {etiqueta_semana(fila.orden)}", axis=1
        )
    agrupada["desviacion_kg"] = agrupada["proyectado_kg"] - agrupada["real_kg"]
    agrupada["error_abs_kg"] = agrupada["desviacion_kg"].abs()
    return agrupada


def metricas_replay_historico(
    agrupada: pd.DataFrame,
    detalle: pd.DataFrame | None = None,
) -> dict[str, float | int]:
    """Resume el nivel visible y conserva aparte el error fino lote-semana."""

    if not isinstance(agrupada, pd.DataFrame) or agrupada.empty:
        return {
            "real_kg": float("nan"),
            "proyectado_kg": float("nan"),
            "desviacion_kg": float("nan"),
            "wape": float("nan"),
            "wape_operacional": float("nan"),
            "wape_lote_semana": float("nan"),
            "wape_condicionado": float("nan"),
            "mae_kg": float("nan"),
            "rmse_kg": float("nan"),
            "bias_kg": float("nan"),
            "sesgo": float("nan"),
            "mase": float("nan"),
            "rmsse": float("nan"),
            "r2": float("nan"),
            "cobertura_lotes": float("nan"),
            "cobertura_lote_semana": float("nan"),
            "cobertura_volumen": float("nan"),
            "filas_evaluadas": 0,
            "filas_emitidas": 0,
            "periodos": 0,
            "semanas": 0,
            "meses": 0,
            "campanias": 0,
        }
    real = float(pd.to_numeric(agrupada["real_kg"], errors="coerce").sum())
    proyectado = float(pd.to_numeric(agrupada["proyectado_kg"], errors="coerce").sum())
    desviacion = proyectado - real
    denominador = abs(real)
    base_error = (
        preparar_replay_historico(detalle) if isinstance(detalle, pd.DataFrame) else pd.DataFrame()
    )
    error_nivel_visible = float(pd.to_numeric(agrupada["error_abs_kg"], errors="coerce").sum())
    if base_error.empty:
        error_lote_semana = error_nivel_visible
        semanas = meses = campanias = 0
    else:
        error_lote_semana = float(
            (
                pd.to_numeric(base_error["p50_kg"], errors="coerce")
                - pd.to_numeric(base_error["real_kg"], errors="coerce")
            )
            .abs()
            .sum()
        )
        fechas = pd.to_datetime(base_error["fecha_objetivo"], errors="coerce")
        semanas = int(
            pd.DataFrame(
                {
                    "campania": base_error["campania"].astype(str),
                    "semana": _semana_inicio(fechas),
                }
            )
            .drop_duplicates()
            .shape[0]
        )
        meses = int(
            pd.DataFrame(
                {
                    "campania": base_error["campania"].astype(str),
                    "mes": fechas.dt.to_period("M").astype(str),
                }
            )
            .drop_duplicates()
            .shape[0]
        )
        campanias = int(base_error["campania"].astype(str).nunique())
    ordenada = agrupada.sort_values([c for c in ("campania", "orden") if c in agrupada])
    escala_naive = []
    for _, grupo in ordenada.groupby("campania", dropna=False):
        valores = pd.to_numeric(grupo["real_kg"], errors="coerce").dropna().to_numpy(float)
        if len(valores) > 1:
            escala_naive.extend(abs(pd.Series(valores).diff().dropna()).tolist())
    escala = float(pd.Series(escala_naive).mean()) if escala_naive else float("nan")
    escala_rms = float(np.sqrt(np.mean(np.square(escala_naive)))) if escala_naive else float("nan")
    mae_visible = float(pd.to_numeric(agrupada["error_abs_kg"], errors="coerce").mean())
    diferencias_visibles = pd.to_numeric(
        agrupada["proyectado_kg"], errors="coerce"
    ) - pd.to_numeric(agrupada["real_kg"], errors="coerce")
    rmse_visible = float(np.sqrt(np.mean(np.square(diferencias_visibles))))
    r2_denominador = (
        float(
            np.square(
                pd.to_numeric(agrupada["real_kg"], errors="coerce") - real / len(agrupada)
            ).sum()
        )
        if len(agrupada) > 1
        else 0.0
    )
    r2_visible = (
        float(1.0 - np.square(diferencias_visibles).sum() / r2_denominador)
        if r2_denominador > 0
        else float("nan")
    )
    if base_error.empty:
        cobertura_lotes = cobertura_volumen = float("nan")
        cobertura_lote_semana = float("nan")
        wape_condicionado = float("nan")
    else:
        emitio = (
            base_error.get("emitio_prediccion", pd.Series(True, index=base_error.index))
            .fillna(False)
            .astype(bool)
        )
        total_lotes = (
            int(base_error["lote_id"].nunique()) if "lote_id" in base_error else len(base_error)
        )
        cobertura_lotes = (
            float(base_error.loc[emitio, "lote_id"].nunique() / total_lotes)
            if total_lotes and "lote_id" in base_error
            else float(emitio.mean())
        )
        cobertura_lote_semana = float(emitio.mean()) if len(base_error) else float("nan")
        total_volumen = float(base_error["real_kg"].abs().sum())
        cobertura_volumen = (
            float(base_error.loc[emitio, "real_kg"].abs().sum() / total_volumen)
            if total_volumen
            else float("nan")
        )
        agrupada_condicionada = agrupada.loc[
            pd.to_numeric(agrupada["filas_emitidas"], errors="coerce").fillna(0).gt(0)
        ]
        denominador_condicionado = float(
            pd.to_numeric(agrupada_condicionada["real_emitido_kg"], errors="coerce").abs().sum()
        )
        wape_condicionado = (
            float(
                (
                    agrupada_condicionada["proyectado_emitido_kg"]
                    - agrupada_condicionada["real_emitido_kg"]
                )
                .abs()
                .sum()
                / denominador_condicionado
            )
            if denominador_condicionado
            else float("nan")
        )
    return {
        "real_kg": real,
        "proyectado_kg": proyectado,
        "desviacion_kg": desviacion,
        "wape": float(error_nivel_visible / denominador) if denominador else float("nan"),
        "wape_operacional": (
            float(error_nivel_visible / denominador) if denominador else float("nan")
        ),
        "wape_lote_semana": (
            float(error_lote_semana / denominador) if denominador else float("nan")
        ),
        "wape_condicionado": wape_condicionado,
        "mae_kg": mae_visible,
        "rmse_kg": rmse_visible,
        "bias_kg": desviacion,
        "sesgo": float(desviacion / denominador) if denominador else float("nan"),
        "mase": float(mae_visible / escala) if escala and escala > 0 else float("nan"),
        "rmsse": (
            float(rmse_visible / escala_rms) if escala_rms and escala_rms > 0 else float("nan")
        ),
        "r2": r2_visible,
        "cobertura_lotes": cobertura_lotes,
        "cobertura_lote_semana": cobertura_lote_semana,
        "cobertura_volumen": cobertura_volumen,
        "filas_evaluadas": int(pd.to_numeric(agrupada["filas_evaluadas"], errors="coerce").sum())
        if "filas_evaluadas" in agrupada
        else 0,
        "filas_emitidas": int(pd.to_numeric(agrupada["filas_emitidas"], errors="coerce").sum())
        if "filas_emitidas" in agrupada
        else 0,
        "periodos": int(len(agrupada)),
        "semanas": semanas,
        "meses": meses,
        "campanias": campanias,
    }


def inicio_ventana_operativa(
    modelo: pd.DataFrame,
    real: pd.DataFrame | None = None,
    *,
    fecha_hoy: object | None = None,
) -> pd.Timestamp | None:
    if not isinstance(modelo, pd.DataFrame) or modelo.empty:
        return None
    hoy = pd.to_datetime(fecha_hoy, errors="coerce")
    if pd.isna(hoy):
        hoy = pd.Timestamp.now().normalize()
    semana_hoy = hoy - pd.Timedelta(days=hoy.weekday())
    # La mesa diaria debe empezar en la semana que está ocurriendo, no en la
    # siguiente. Puede existir cosecha parcial de la semana actual; esa observación
    # se compara con la estimación de cierre y no debe ocultar el plan vigente.
    inicio = semana_hoy
    disponibles = sorted(pd.to_datetime(modelo["semana_inicio"], errors="coerce").dropna().unique())
    futuras = [pd.Timestamp(fecha) for fecha in disponibles if pd.Timestamp(fecha) >= inicio]
    if futuras:
        return futuras[0]
    return pd.Timestamp(disponibles[0]) if disponibles else None


def aplicar_horizonte(
    tabla: pd.DataFrame,
    horizonte: str,
    *,
    inicio: object | None,
    semanas: int = 6,
) -> pd.DataFrame:
    if not isinstance(tabla, pd.DataFrame) or tabla.empty:
        return pd.DataFrame()
    salida = tabla.copy()
    fecha_inicio = pd.to_datetime(inicio, errors="coerce")
    if pd.notna(fecha_inicio):
        salida = salida[salida["semana_inicio"] >= fecha_inicio]
    if horizonte == HORIZONTE_SEMANAS and not salida.empty:
        permitidas = sorted(salida["semana_inicio"].dropna().unique())[:semanas]
        salida = salida[salida["semana_inicio"].isin(permitidas)]
    return salida


def plan_semanal(tabla: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(tabla, pd.DataFrame) or tabla.empty:
        return pd.DataFrame()
    agrupada = (
        tabla.dropna(subset=["semana_inicio"])
        .groupby(["semana_inicio", "fundo"], as_index=False, dropna=False)["p50_kg"]
        .sum(min_count=1)
    )
    pivot = agrupada.pivot(index="semana_inicio", columns="fundo", values="p50_kg")
    for fundo in FUNDOS_OPERATIVOS:
        if fundo not in pivot:
            pivot[fundo] = pd.NA
    pivot = pivot[list(FUNDOS_OPERATIVOS)].sort_index().reset_index()
    pivot["total_kg"] = pivot[list(FUNDOS_OPERATIVOS)].sum(axis=1, min_count=1)
    pivot["semana_cierre"] = pivot["semana_inicio"] + pd.Timedelta(days=6)
    pivot["semana_iso"] = pivot["semana_inicio"].dt.isocalendar().week.astype("Int64")
    pivot["rango_semana"] = pivot["semana_inicio"].map(etiqueta_semana)
    return pivot


def resumen_fundos(tabla: pd.DataFrame) -> pd.DataFrame:
    plan = plan_semanal(tabla)
    filas: list[dict[str, object]] = []
    primera = plan["semana_inicio"].min() if not plan.empty else pd.NaT
    for fundo in FUNDOS_OPERATIVOS:
        fuente = tabla[tabla["fundo"].eq(fundo)] if not tabla.empty else pd.DataFrame()
        serie = (
            plan[["semana_inicio", fundo]].dropna(subset=[fundo])
            if not plan.empty
            else pd.DataFrame()
        )
        disponible = not fuente.empty and not serie.empty
        pico = serie.loc[serie[fundo].idxmax()] if disponible else None
        proxima = (
            serie.loc[serie["semana_inicio"].eq(primera), fundo].sum(min_count=1)
            if disponible and pd.notna(primera)
            else pd.NA
        )
        filas.append(
            {
                "fundo": fundo,
                "proxima_semana_kg": proxima,
                "total_periodo_kg": serie[fundo].sum(min_count=1) if disponible else pd.NA,
                "semana_pico": pico["semana_inicio"] if pico is not None else pd.NaT,
                "kg_pico": pico[fundo] if pico is not None else pd.NA,
                "estado": "Disponible" if disponible else "Sin datos",
            }
        )
    return pd.DataFrame(filas)


def columnas_grid() -> list[dict]:
    nombres = {
        "fundo": "Fundo",
        "modulo": "Módulo",
        "turno": "Turno",
        "lote": "Lote",
        "pasada": "Paña",
        "fecha_inicio": "Desde",
        "fecha_objetivo": "Fecha de cosecha",
        "semana_iso": "Semana",
        "frutos_por_planta": "Frutos/planta",
        "peso_baya_g": "Peso (g)",
        "plantas": "Plantas",
        "p50_kg": "Kilos proyectados",
        "nivel_calibracion": "Cálculo de parámetros",
        "fuente_parametros": "Parámetros",
        "fuente_poda": "Poda",
    }
    numericas = {
        "pasada",
        "semana_iso",
        "frutos_por_planta",
        "peso_baya_g",
        "plantas",
        "p50_kg",
    }
    columnas = []
    for campo in COLUMNAS_DETALLE:
        definicion = {"field": campo, "headerName": nombres.get(campo, etiqueta(campo))}
        if campo in numericas:
            definicion["type"] = "numericColumn"
            formato = ",.0f" if campo in {"plantas", "p50_kg", "pasada", "semana_iso"} else ".2f"
            definicion["valueFormatter"] = {
                "function": f"params.value == null ? '' : d3.format('{formato}')(params.value)"
            }
        columnas.append(definicion)
    return columnas


def filas_grid(tabla: pd.DataFrame) -> list[dict]:
    if not isinstance(tabla, pd.DataFrame) or tabla.empty:
        return []
    vista = tabla.copy()
    for columna in ("fecha_inicio", "fecha_objetivo"):
        if columna in vista:
            vista[columna] = pd.to_datetime(vista[columna], errors="coerce").dt.strftime("%d/%m/%Y")
    if "fuente_parametros" in vista:
        vista["fuente_parametros"] = vista["fuente_parametros"].replace(
            {
                "postgresql": "PostgreSQL · automático",
                "bd": "PostgreSQL · automático",
                "excel": "Respaldo documentado",
            }
        )
    if "fuente_poda" in vista:
        vista["fuente_poda"] = vista["fuente_poda"].replace(
            {"postgresql": "PostgreSQL", "bd": "PostgreSQL", "excel": "Respaldo"}
        )
    presentes = [c for c in COLUMNAS_DETALLE if c in vista]
    orden = [c for c in ("fecha_objetivo", "fundo", "modulo", "lote") if c in vista]
    return vista[presentes].sort_values(orden).to_dict("records")


def vista_descarga(tabla: pd.DataFrame) -> pd.DataFrame:
    """Vista operativa: evita exponer nombres internos de archivos en cada fila."""
    presentes = [c for c in COLUMNAS_DETALLE if c in tabla]
    vista = tabla[presentes].copy()
    if "fuente_parametros" in vista:
        vista["fuente_parametros"] = vista["fuente_parametros"].replace(
            {
                "postgres_auto": "Automático · base de datos",
                "postgresql": "Automático · base de datos",
                "bd": "Automático · base de datos",
                "excel": "Respaldo documentado",
            }
        )
    if "nivel_calibracion" in vista:
        vista["nivel_calibracion"] = vista["nivel_calibracion"].replace(
            {
                "lote_actual_con_historico": "Lote · historia propia",
                "lote_historico": "Lote · historia previa",
                "modulo_historico": "Módulo · historia previa",
                "fundo_historico": "Fundo · historia previa",
            }
        )
    if "fuente_poda" in vista:
        vista["fuente_poda"] = vista["fuente_poda"].replace(
            {
                "postgres": "Base de datos",
                "postgresql": "Base de datos",
                "bd": "Base de datos",
                "excel": "Respaldo documentado",
            }
        )
    rotulos = {c["field"]: c["headerName"] for c in columnas_grid()}
    vista.columns = [rotulos.get(nombre, etiqueta(nombre)) for nombre in presentes]
    return vista


def vista_trazabilidad(tabla: pd.DataFrame) -> pd.DataFrame:
    """Fuentes exactas separadas del plan que consume el agrónomo."""
    columnas = [
        c
        for c in (
            "campania",
            "fecha_emision",
            "fundo",
            "fuente_libro",
            "fuente_hash",
            "fuente_parametros",
            "nivel_calibracion",
        )
        if c in tabla
    ]
    if not columnas:
        return pd.DataFrame(columns=["Estado"])
    vista = tabla[columnas].drop_duplicates().copy()
    rotulos = {
        "campania": "Campaña",
        "fecha_emision": "Emisión",
        "fundo": "Fundo",
        "fuente_libro": "Archivo fuente (auditoría)",
        "fuente_hash": "Huella SHA-256",
        "fuente_parametros": "Origen de parámetros",
        "nivel_calibracion": "Nivel de calibración",
    }
    vista = vista.rename(columns=rotulos)
    return vista.sort_values([c for c in ("Campaña", "Emisión", "Fundo") if c in vista])


def matriz_six(replay: pd.DataFrame, modelo: str = R09_REFERENCIA) -> pd.DataFrame:
    if not isinstance(replay, pd.DataFrame) or replay.empty:
        return pd.DataFrame()
    tabla = replay.copy()
    if "modelo" in tabla:
        tabla = tabla[tabla.modelo.astype(str).eq(modelo)]
    if tabla.empty:
        return pd.DataFrame()
    tabla["fecha_emision"] = pd.to_datetime(tabla["fecha_emision"], errors="coerce")
    tabla["semana_objetivo"] = _semana_inicio(tabla["fecha_objetivo"])
    tabla["p50_kg"] = pd.to_numeric(tabla["p50_kg"], errors="coerce")
    tabla = tabla.dropna(subset=["fecha_emision", "semana_objetivo", "p50_kg"])
    if tabla.empty:
        return pd.DataFrame()
    agrupada = tabla.groupby(["fecha_emision", "semana_objetivo"], as_index=False)["p50_kg"].sum()
    return agrupada.pivot(
        index="fecha_emision", columns="semana_objetivo", values="p50_kg"
    ).sort_index()


def meta_descarga(tabla: pd.DataFrame, estado: dict) -> list[tuple[str, str]]:
    runs = estado.get("runs", pd.DataFrame())
    corrida = (
        f"n.º {int(runs.iloc[0].run_id)}"
        if isinstance(runs, pd.DataFrame) and not runs.empty
        else "no registrada"
    )
    emision = (
        pd.to_datetime(tabla.get("fecha_emision"), errors="coerce").max()
        if not tabla.empty
        else pd.NaT
    )
    return [
        ("Generado", dt.datetime.now().strftime("%Y-%m-%d %H:%M")),
        ("Corrida analítica", corrida),
        ("Motor de cálculo", "Modelo operativo Python (réplica validada de ProySemanal)"),
        ("Pronóstico emitido", emision.strftime("%Y-%m-%d") if pd.notna(emision) else "—"),
        (
            "Fundos",
            ", ".join(sorted(tabla.fundo.dropna().unique())) if not tabla.empty else "—",
        ),
        (
            "Referencia comparativa",
            "R09 es una emisión publicada; no es un algoritmo ni alimenta el cálculo.",
        ),
    ]
