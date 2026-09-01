"""Candidato estructural as-of para proyectar las oleadas del proceso manual.

El libro ``ProySemanal`` ya contiene una hipótesis agronómica valiosa: tres
distribuciones normales para repartir frutos en el tiempo y una curva exponencial
de peso por oleada. Este módulo no la reemplaza por una caja negra. La convierte
en un objeto que puede:

* recibir los parámetros nombrados del libro (X/O/N y A/B);
* regularizar sus ajustes con la cosecha disponible antes del corte;
* proyectar semanas futuras sin necesitar el real de la semana corriente; y
* explicar el cambio como contribuciones mecánicas de carga, timing, dispersión,
  calibre y merma.

La explicación de parámetros es una atribución del modelo, no una afirmación
causal. Para llamar "causa" a una variable agronómica todavía hace falta una
fuente experimental o un diseño de intervención.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any

import numpy as np
import pandas as pd
from scipy.optimize import least_squares
from scipy.special import ndtr

from .macro import MacroParams, parametros_desde_fila

_ALIAS_FRUTOS = (
    "frutos_por_planta",
    "frutos_planta",
    "frutos",
    "frutos_reales_por_planta_catalogo",
    "frutos_reales_por_planta",
)
_ALIAS_PESO = ("peso_baya_g", "peso_real_g", "peso_baya", "peso")
_ALIAS_KG = ("kg", "real_kg", "volumen_kg")
_ALIAS_PLANTAS = ("plantas", "n_plantas", "NPlantas")
_ALIAS_T_FIN = ("t_fin", "dias_fin", "ddp", "DDP", "t_dias", "dias_desde_poda")
_ALIAS_T_INICIO = ("t_inicio", "dias_inicio", "ddp_inicio", "t_ini")
_ALIAS_FECHA_FIN = ("fecha_fin", "fecha_objetivo", "fecha_real", "fecha")
_ALIAS_FECHA_INICIO = ("fecha_inicio", "fecha_ini")
_ALIAS_PASADA = (
    "pana",
    "pasada",
    "pass",
    "numero_pasada",
    "n_pasada",
    "pasada_real",
)
_IDENTIDAD_PASADA = (
    "campania",
    "campaña",
    "fundo",
    "modulo",
    "módulo",
    "turno",
    "lote",
    "lote_id",
    "id",
)

_BLOQUES_EXPLICACION = {
    "amplitud_carga": (
        "ola_1_multiplicador",
        "ola_2_multiplicador",
        "ola_3_multiplicador",
    ),
    "timing": ("ola_1_media_dias", "ola_2_media_dias", "ola_3_media_dias"),
    "dispersion": ("ola_1_desvio_dias", "ola_2_desvio_dias", "ola_3_desvio_dias"),
    "calibre": (
        "peso_1_base_g",
        "peso_1_tasa",
        "peso_2_base_g",
        "peso_2_tasa",
        "peso_3_base_g",
        "peso_3_tasa",
    ),
    "merma": ("multiplicador_carga",),
}


@dataclass(frozen=True)
class ResultadoAjusteOleadasAsOf:
    """Resultado y evidencia mínima de un ajuste as-of de parámetros."""

    parametros: MacroParams
    n_observaciones: int
    n_observaciones_peso: int
    rmse_frutos_por_planta: float | None
    rmse_peso_g: float | None
    fecha_corte: pd.Timestamp | None
    fuente: str
    advertencias: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Serializa el resultado sin perder la procedencia del ajuste."""

        return {
            "parametros": {
                "area_ha": self.parametros.area_ha,
                "plantas": self.parametros.plantas,
                "fecha_pivote": self.parametros.fecha_pivote.strftime("%Y-%m-%d"),
                "X1": self.parametros.ola_1_media_dias,
                "O1": self.parametros.ola_1_desvio_dias,
                "N1": self.parametros.ola_1_multiplicador,
                "X2": self.parametros.ola_2_media_dias,
                "O2": self.parametros.ola_2_desvio_dias,
                "N2": self.parametros.ola_2_multiplicador,
                "X3": self.parametros.ola_3_media_dias,
                "O3": self.parametros.ola_3_desvio_dias,
                "N3": self.parametros.ola_3_multiplicador,
                "A1": self.parametros.peso_1_base_g,
                "B1": self.parametros.peso_1_tasa,
                "A2": self.parametros.peso_2_base_g,
                "B2": self.parametros.peso_2_tasa,
                "A3": self.parametros.peso_3_base_g,
                "B3": self.parametros.peso_3_tasa,
                "multiplicador_carga": self.parametros.multiplicador_carga,
            },
            "n_observaciones": self.n_observaciones,
            "n_observaciones_peso": self.n_observaciones_peso,
            "rmse_frutos_por_planta": self.rmse_frutos_por_planta,
            "rmse_peso_g": self.rmse_peso_g,
            "fecha_corte": self.fecha_corte.strftime("%Y-%m-%d")
            if self.fecha_corte is not None
            else None,
            "fuente": self.fuente,
            "advertencias": list(self.advertencias),
        }


def _primera_columna(tabla: pd.DataFrame, nombres: tuple[str, ...]) -> str | None:
    indice = {str(columna).strip().casefold(): columna for columna in tabla.columns}
    for nombre in nombres:
        encontrada = indice.get(nombre.casefold())
        if encontrada is not None:
            return str(encontrada)
    return None


def _serie_numerica(tabla: pd.DataFrame, columna: str | None, defecto: float) -> pd.Series:
    if columna is None:
        return pd.Series(defecto, index=tabla.index, dtype=float)
    return pd.to_numeric(tabla[columna], errors="coerce")


def _agrupar_observaciones_por_pasada(
    tabla: pd.DataFrame,
    *,
    columna_pasada: str,
    columna_fecha: str,
    columna_frutos: str | None,
    columna_peso: str | None,
    columna_kg: str | None,
) -> tuple[pd.DataFrame, bool]:
    """Reduce H01 diario a una observación por pasada, sin mezclar lotes.

    H01 puede tener varias filas para una misma ``pana`` porque la cuadrilla cosecha un
    lote en más de un día. Si cada fila se convierte directamente en una ventana de siete
    días, las ventanas se solapan y la misma carga entra varias veces al ajuste de X/O/N.
    La macro manual, en cambio, asigna una sola masa al intervalo entre dos pasadas. Aquí
    se conserva esa semántica cuando la fuente trae un identificador de pasada.

    La función solo se activa cuando todavía no vienen ``t_inicio``/``t_fin`` explícitos;
    una tabla ya agregada por el llamador no se vuelve a interpretar. Los identificadores
    de lote presentes se incluyen en la llave para que una observación con ``pana=1`` de
    dos lotes no se convierta en una sola pasada.
    """

    fecha = pd.to_datetime(tabla[columna_fecha], errors="coerce")
    if fecha.notna().sum() == 0:
        return tabla, False

    trabajo = tabla.copy()
    trabajo["__fecha_pasada"] = fecha
    trabajo["__fila_pasada"] = np.arange(len(trabajo), dtype=np.int64)
    valor_pasada = trabajo[columna_pasada]
    trabajo["__pasada_clave"] = valor_pasada.astype("string")
    faltante = valor_pasada.isna()
    trabajo.loc[faltante, "__pasada_clave"] = (
        "__sin_pasada_" + trabajo.loc[faltante, "__fila_pasada"].astype(str)
    )
    identidad: list[str] = []
    for nombre in _IDENTIDAD_PASADA:
        columna = _primera_columna(trabajo, (nombre,))
        if (
            columna is not None
            and columna not in {columna_pasada, columna_fecha}
            and columna not in identidad
        ):
            identidad.append(columna)
    llaves = [*identidad, "__pasada_clave"]

    filas: list[dict[str, object]] = []
    for _, grupo in trabajo.groupby(llaves, sort=False, dropna=False):
        grupo = grupo.sort_values(["__fecha_pasada", "__fila_pasada"])
        fila = grupo.iloc[-1].to_dict()
        fila[columna_fecha] = grupo["__fecha_pasada"].max()

        if columna_kg is not None:
            kilos = pd.to_numeric(grupo[columna_kg], errors="coerce").fillna(0.0)
            fila[columna_kg] = float(kilos.sum())
        else:
            kilos = pd.Series(0.0, index=grupo.index, dtype=float)

        if columna_frutos is not None:
            frutos = pd.to_numeric(grupo[columna_frutos], errors="coerce")
            fila[columna_frutos] = (
                float(frutos.sum(min_count=1)) if frutos.notna().any() else np.nan
            )

        if columna_peso is not None:
            pesos = pd.to_numeric(grupo[columna_peso], errors="coerce")
            validos = pesos.notna() & pesos.gt(0)
            if validos.any():
                pesos_validos = pesos.loc[validos]
                pesos_kilos = kilos.loc[validos].clip(lower=0)
                if float(pesos_kilos.sum()) > 0:
                    # Conserva los frutos implícitos: sum(kg / peso) debe ser
                    # igual a kg_agregado / peso_agregado.
                    frutos_equivalentes = float((pesos_kilos / pesos_validos).sum())
                    fila[columna_peso] = float(pesos_kilos.sum() / frutos_equivalentes)
                else:
                    fila[columna_peso] = float(pesos_validos.mean())
            else:
                fila[columna_peso] = np.nan

        fila["__grupo_pasada"] = "|".join(
            str(fila.get(columna, "")) for columna in identidad
        )
        filas.append(fila)

    agrupada = pd.DataFrame(filas)
    columnas_internas = ["__fecha_pasada", "__fila_pasada", "__pasada_clave"]
    return agrupada.drop(columns=columnas_internas, errors="ignore"), True


def _normalizar_observaciones(
    observaciones: pd.DataFrame,
    parametros: MacroParams,
    *,
    fecha_corte: object | None,
    intervalo_dias: int,
) -> tuple[pd.DataFrame, tuple[str, ...]]:
    """Normaliza cosecha a intervalos de días desde poda y aplica el corte as-of."""

    if observaciones is None or observaciones.empty:
        return (
            pd.DataFrame(
                {
                    "t_inicio": pd.Series(dtype=float),
                    "t_fin": pd.Series(dtype=float),
                    "frutos_obs": pd.Series(dtype=float),
                    "peso_obs": pd.Series(dtype=float),
                }
            ),
            (),
        )
    if intervalo_dias <= 0:
        raise ValueError("intervalo_dias debe ser positivo")

    tabla = observaciones.copy()
    advertencias: list[str] = []
    fecha_pivote = pd.Timestamp(parametros.fecha_pivote).normalize()

    fecha_filtro = _primera_columna(
        tabla,
        (
            "fecha_observacion",
            "fecha_real",
            "fecha_fin",
            "fecha_objetivo",
            "fecha",
            "fecha_inicio",
        ),
    )
    if fecha_corte is not None:
        corte = pd.Timestamp(fecha_corte).normalize()
        if fecha_filtro is None:
            raise ValueError(
                "fecha_corte requiere una columna de fecha para garantizar el corte as-of"
            )
        fecha = pd.to_datetime(tabla[fecha_filtro], errors="coerce").dt.normalize()
        tabla = tabla.loc[fecha.lt(corte)].copy()

    fecha_inicio = _primera_columna(tabla, _ALIAS_FECHA_INICIO)
    fecha_fin = _primera_columna(tabla, _ALIAS_FECHA_FIN)
    t_inicio = _primera_columna(tabla, _ALIAS_T_INICIO)
    t_fin = _primera_columna(tabla, _ALIAS_T_FIN)

    frutos_columna = _primera_columna(tabla, _ALIAS_FRUTOS)
    peso_columna = _primera_columna(tabla, _ALIAS_PESO)
    kg_columna = _primera_columna(tabla, _ALIAS_KG)
    pasada_columna = _primera_columna(tabla, _ALIAS_PASADA)
    agrupada_por_pasada = False
    if (
        pasada_columna is not None
        and fecha_fin is not None
        and t_inicio is None
        and t_fin is None
        and fecha_inicio is None
    ):
        tabla, agrupada_por_pasada = _agrupar_observaciones_por_pasada(
            tabla,
            columna_pasada=pasada_columna,
            columna_fecha=fecha_fin,
            columna_frutos=frutos_columna,
            columna_peso=peso_columna,
            columna_kg=kg_columna,
        )
        if agrupada_por_pasada:
            advertencias.append("observaciones_agrupadas_por_pasada_sin_intervalos_solapados")
            # Re-resolve names because the helper may have returned a reconstructed frame.
            fecha_inicio = _primera_columna(tabla, _ALIAS_FECHA_INICIO)
            fecha_fin = _primera_columna(tabla, _ALIAS_FECHA_FIN)
            t_inicio = _primera_columna(tabla, _ALIAS_T_INICIO)
            t_fin = _primera_columna(tabla, _ALIAS_T_FIN)
            frutos_columna = _primera_columna(tabla, _ALIAS_FRUTOS)
            peso_columna = _primera_columna(tabla, _ALIAS_PESO)
            kg_columna = _primera_columna(tabla, _ALIAS_KG)

    if t_fin is not None:
        fin = pd.to_numeric(tabla[t_fin], errors="coerce")
    elif fecha_fin is not None:
        fin = (pd.to_datetime(tabla[fecha_fin], errors="coerce") - fecha_pivote).dt.days
    else:
        fin = pd.Series(np.nan, index=tabla.index, dtype=float)

    if t_inicio is not None:
        inicio = pd.to_numeric(tabla[t_inicio], errors="coerce")
    elif fecha_inicio is not None:
        inicio = (
            pd.to_datetime(tabla[fecha_inicio], errors="coerce") - fecha_pivote
        ).dt.days
    else:
        inicio = fin - float(intervalo_dias)

    frutos = (
        pd.to_numeric(tabla[frutos_columna], errors="coerce")
        if frutos_columna is not None
        else pd.Series(np.nan, index=tabla.index, dtype=float)
    )
    peso = (
        pd.to_numeric(tabla[peso_columna], errors="coerce")
        if peso_columna is not None
        else pd.Series(np.nan, index=tabla.index, dtype=float)
    )
    if frutos_columna is None:
        if kg_columna is not None and peso_columna is not None:
            plantas_columna = _primera_columna(tabla, _ALIAS_PLANTAS)
            plantas = _serie_numerica(tabla, plantas_columna, parametros.plantas)
            kilos = pd.to_numeric(tabla[kg_columna], errors="coerce")
            frutos = kilos * 1000.0 / (plantas * peso).replace(0, np.nan)
        elif kg_columna is not None:
            # Un cero de kg sí identifica ausencia de frutos aunque el peso no se
            # haya medido. Un volumen positivo sin peso no se convierte en una
            # pseudo-observación: queda fuera hasta contar con esa unidad.
            kilos = pd.to_numeric(tabla[kg_columna], errors="coerce")
            frutos = kilos.where(kilos.eq(0), np.nan)

    salida = pd.DataFrame(
        {
            "t_inicio": inicio,
            "t_fin": fin,
            "frutos_obs": frutos,
            "peso_obs": peso,
        },
        index=tabla.index,
    )
    if agrupada_por_pasada and "__grupo_pasada" in tabla:
        salida["__grupo_pasada"] = tabla["__grupo_pasada"].to_numpy()
    validos = (
        np.isfinite(salida.t_inicio)
        & np.isfinite(salida.t_fin)
        & salida.t_fin.gt(salida.t_inicio)
        & np.isfinite(salida.frutos_obs)
        & salida.frutos_obs.ge(0)
    )
    salida = salida.loc[validos].copy()
    if agrupada_por_pasada and "__grupo_pasada" in salida:
        orden = salida.sort_values(["__grupo_pasada", "t_fin"]).copy()
        previos = orden.groupby("__grupo_pasada", sort=False).t_fin.shift(1)
        orden["t_inicio"] = previos.fillna(orden.t_fin - float(intervalo_dias))
        salida.loc[orden.index, "t_inicio"] = orden["t_inicio"]
        salida = salida.drop(columns="__grupo_pasada")
    return salida.reset_index(drop=True), tuple(advertencias)


def _fraccion_numerica(
    t_inicio: np.ndarray,
    t_fin: np.ndarray,
    media: float,
    desvio: float,
    carga: float,
) -> np.ndarray:
    escala = max(float(desvio), 1.0)
    return (ndtr((t_fin - media) / escala) - ndtr((t_inicio - media) / escala)) * carga


def _desempaquetar(vector: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, float, float]:
    mu1, delta2, delta3 = vector[:3]
    sigmas = np.exp(vector[3:6])
    cargas = np.exp(vector[6:9])
    factor_peso = float(np.exp(vector[9]))
    delta_tasa_peso = float(vector[10])
    medias = np.array([mu1, mu1 + delta2, mu1 + delta2 + delta3], dtype=float)
    return medias, sigmas, cargas, factor_peso, delta_tasa_peso


def _vector_prior(parametros: MacroParams) -> np.ndarray:
    medias = np.array(
        [
            parametros.ola_1_media_dias,
            parametros.ola_2_media_dias - parametros.ola_1_media_dias,
            parametros.ola_3_media_dias - parametros.ola_2_media_dias,
        ],
        dtype=float,
    )
    sigmas = np.array(
        [
            parametros.ola_1_desvio_dias,
            parametros.ola_2_desvio_dias,
            parametros.ola_3_desvio_dias,
        ],
        dtype=float,
    )
    cargas = np.array(
        [
            parametros.ola_1_multiplicador,
            parametros.ola_2_multiplicador,
            parametros.ola_3_multiplicador,
        ],
        dtype=float,
    )
    return np.r_[
        medias[0],
        medias[1:],
        np.log(np.maximum(sigmas, 1e-6)),
        np.log(np.maximum(cargas, 1e-6)),
        0.0,
        0.0,
    ]


def _predecir_vector(
    vector: np.ndarray,
    parametros: MacroParams,
    t_inicio: np.ndarray,
    t_fin: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    medias, sigmas, cargas, factor_peso, delta_tasa_peso = _desempaquetar(vector)
    cantidades = np.vstack(
        [
            _fraccion_numerica(t_inicio, t_fin, media, sigma, carga)
            for media, sigma, carga in zip(medias, sigmas, cargas, strict=True)
        ]
    )
    cantidades = np.maximum(cantidades, 0.0)
    total_bruto = cantidades.sum(axis=0)
    frutos = total_bruto * max(float(parametros.multiplicador_carga), 0.0)
    bases = np.array(
        [
            parametros.peso_1_base_g,
            parametros.peso_2_base_g,
            parametros.peso_3_base_g,
        ],
        dtype=float,
    )
    tasas = np.array(
        [parametros.peso_1_tasa, parametros.peso_2_tasa, parametros.peso_3_tasa],
        dtype=float,
    )
    pesos = bases[:, None] * factor_peso * np.exp(
        (tasas + delta_tasa_peso)[:, None] * t_fin[None, :]
    )
    peso = np.divide(
        (cantidades * pesos).sum(axis=0),
        total_bruto,
        out=np.zeros_like(total_bruto),
        where=total_bruto > 0,
    )
    return frutos, peso


def _parametros_vector(parametros: MacroParams, vector: np.ndarray) -> MacroParams:
    medias, sigmas, cargas, factor_peso, delta_tasa_peso = _desempaquetar(vector)
    return replace(
        parametros,
        ola_1_media_dias=float(medias[0]),
        ola_2_media_dias=float(medias[1]),
        ola_3_media_dias=float(medias[2]),
        ola_1_desvio_dias=float(sigmas[0]),
        ola_2_desvio_dias=float(sigmas[1]),
        ola_3_desvio_dias=float(sigmas[2]),
        ola_1_multiplicador=float(cargas[0]),
        ola_2_multiplicador=float(cargas[1]),
        ola_3_multiplicador=float(cargas[2]),
        peso_1_base_g=float(parametros.peso_1_base_g * factor_peso),
        peso_2_base_g=float(parametros.peso_2_base_g * factor_peso),
        peso_3_base_g=float(parametros.peso_3_base_g * factor_peso),
        peso_1_tasa=float(parametros.peso_1_tasa + delta_tasa_peso),
        peso_2_tasa=float(parametros.peso_2_tasa + delta_tasa_peso),
        peso_3_tasa=float(parametros.peso_3_tasa + delta_tasa_peso),
    )


def ajustar_oleadas_asof(
    parametros: MacroParams,
    observaciones: pd.DataFrame,
    *,
    fecha_corte: object | None = None,
    intervalo_dias: int = 7,
    fuerza_prior: float | None = None,
    fuente_prior: str = "excel_manual",
) -> ResultadoAjusteOleadasAsOf:
    """Ajusta X/O/N y un corrector común de peso usando solo historia as-of.

    ``parametros`` es el prior manual, normalmente construido con
    :func:`parametros_desde_fila` desde las columnas X/O/N/A/B. La carga de cada
    oleada, sus centros y sus dispersiones se ajustan juntos, con relaciones
    ``X2-X1`` y ``X3-X2`` positivas. El peso por oleada del Excel se conserva como
    base; solo se estima un factor y una corrección común de pendiente cuando hay
    peso observado suficiente.

    La función acepta frutos por planta directamente o los deriva de ``kg``, peso y
    plantas. Si recibe fechas y ``fecha_corte``, descarta estrictamente las filas
    posteriores al corte antes de optimizar.
    """

    if not isinstance(parametros, MacroParams):
        raise TypeError("parametros debe ser MacroParams")
    if not str(fuente_prior).strip():
        raise ValueError("fuente_prior no puede estar vacía")
    tabla, advertencias = _normalizar_observaciones(
        observaciones,
        parametros,
        fecha_corte=fecha_corte,
        intervalo_dias=intervalo_dias,
    )
    advertencias_lista = list(advertencias)
    fecha = pd.Timestamp(fecha_corte).normalize() if fecha_corte is not None else None
    n_obs = int(len(tabla))
    validos_peso = tabla.peso_obs.gt(0) & np.isfinite(tabla.peso_obs)
    n_peso = int(validos_peso.sum())
    if n_obs == 0:
        advertencias = [*advertencias_lista, "sin_historia_utilizable_asof"]
        return ResultadoAjusteOleadasAsOf(
            parametros=parametros,
            n_observaciones=0,
            n_observaciones_peso=0,
            rmse_frutos_por_planta=None,
            rmse_peso_g=None,
            fecha_corte=fecha,
            fuente=f"{fuente_prior}_prior_sin_observaciones_asof",
            advertencias=tuple(advertencias),
        )

    vector_base = _vector_prior(parametros)
    escala_frutos = max(float(np.nanmedian(tabla.frutos_obs)), 1.0)
    escala_peso = max(float(np.nanmedian(tabla.loc[validos_peso, "peso_obs"])) * 0.10, 0.10)
    # Pocas pañas no identifican once parámetros. La fuerza de prior crece en ese
    # caso y permite que el Excel/histórico mantenga la forma hasta tener señal.
    if fuerza_prior is None:
        fuerza_prior = 2.0 if n_obs < 4 else 0.8 if n_obs < 8 else 0.30
    if fuerza_prior < 0:
        raise ValueError("fuerza_prior no puede ser negativa")
    escalas = np.array([35.0, 35.0, 45.0, 0.30, 0.30, 0.30, 0.75, 0.75, 0.90, 0.15, 0.0015])
    t_inicio = tabla.t_inicio.to_numpy(float)
    t_fin = tabla.t_fin.to_numpy(float)
    frutos_obs = tabla.frutos_obs.to_numpy(float)
    peso_obs = tabla.peso_obs.to_numpy(float)

    def residuos(vector: np.ndarray) -> np.ndarray:
        frutos, peso = _predecir_vector(
            parametros=parametros,
            vector=vector,
            t_inicio=t_inicio,
            t_fin=t_fin,
        )
        datos_frutos = (frutos - frutos_obs) / escala_frutos
        bloques = [datos_frutos]
        if n_peso:
            mascara_peso = validos_peso.to_numpy()
            bloques.append((peso[mascara_peso] - peso_obs[mascara_peso]) / escala_peso)
        bloques.append(np.sqrt(fuerza_prior) * (vector - vector_base) / escalas)
        return np.concatenate(bloques)

    limites_inferiores = np.array(
        [
            60.0,
            20.0,
            20.0,
            np.log(8.0),
            np.log(8.0),
            np.log(8.0),
            np.log(1.0),
            np.log(1.0),
            np.log(1.0),
            np.log(0.50),
            -0.003,
        ]
    )
    limites_superiores = np.array(
        [
            420.0,
            180.0,
            220.0,
            np.log(90.0),
            np.log(90.0),
            np.log(90.0),
            np.log(5000.0),
            np.log(4000.0),
            np.log(3000.0),
            np.log(1.50),
            0.003,
        ]
    )
    resultado = least_squares(
        residuos,
        np.clip(vector_base, limites_inferiores, limites_superiores),
        bounds=(limites_inferiores, limites_superiores),
        loss="soft_l1",
        max_nfev=240,
        xtol=1e-6,
        ftol=1e-6,
        gtol=1e-6,
    )
    ajustados = _parametros_vector(parametros, resultado.x)
    frutos_pred, peso_pred = _predecir_vector(resultado.x, parametros, t_inicio, t_fin)
    rmse_frutos = float(np.sqrt(np.mean((frutos_pred - frutos_obs) ** 2)))
    rmse_peso = (
        float(
            np.sqrt(
                np.mean(
                    (
                        peso_pred[validos_peso.to_numpy()]
                        - peso_obs[validos_peso.to_numpy()]
                    )
                    ** 2
                )
            )
        )
        if n_peso
        else None
    )
    if n_obs < 6:
        advertencias_lista.append("pocas_observaciones_para_identificar_tres_oleadas")
    if not n_peso:
        advertencias_lista.append("peso_sin_ajuste;_se_conserva_el_excel")
    return ResultadoAjusteOleadasAsOf(
        parametros=ajustados,
        n_observaciones=n_obs,
        n_observaciones_peso=n_peso,
        rmse_frutos_por_planta=rmse_frutos,
        rmse_peso_g=rmse_peso,
        fecha_corte=fecha,
        fuente=f"{fuente_prior}_prior_ajuste_oleadas_asof",
        advertencias=tuple(advertencias_lista),
    )


def construir_prior_automatico(
    *,
    fecha_pivote: object,
    plantas: float,
    area_ha: float = 1.0,
    prior: MacroParams | None = None,
    observaciones: pd.DataFrame | None = None,
    fecha_corte: object | None = None,
    multiplicador_carga: float | None = None,
    intervalo_dias: int = 7,
    fuerza_prior: float | None = None,
) -> ResultadoAjusteOleadasAsOf:
    """Construye una proyección sin Excel y usa Excel solo como mejora opcional.

    El punto de partida automático usa priors agronómicos explícitos y los ajusta
    con la historia del lote. ``fecha_pivote`` debe venir de ``M_Poda`` o de la
    fuente operativa equivalente; no se inventa a partir de la fecha de emisión.
    Con cero observaciones todavía devuelve una curva H1–H6 válida y deja la
    advertencia en el resultado.
    """

    if prior is not None and not isinstance(prior, MacroParams):
        raise TypeError("prior debe ser MacroParams")
    factor_carga = (
        float(multiplicador_carga)
        if multiplicador_carga is not None
        else float(prior.multiplicador_carga)
        if prior is not None
        else 0.90
    )
    if not 0 <= factor_carga <= 1:
        raise ValueError("multiplicador_carga debe estar entre 0 y 1")
    if prior is None:
        base = MacroParams(
            area_ha=float(area_ha),
            plantas=float(plantas),
            fecha_pivote=pd.Timestamp(fecha_pivote).normalize(),
            ola_1_media_dias=220.0,
            ola_1_desvio_dias=25.0,
            ola_1_multiplicador=500.0,
            ola_2_media_dias=290.0,
            ola_2_desvio_dias=29.0,
            ola_2_multiplicador=225.0,
            ola_3_media_dias=353.0,
            ola_3_desvio_dias=30.0,
            ola_3_multiplicador=100.0,
            peso_1_base_g=4.90,
            peso_1_tasa=-0.001387,
            peso_2_base_g=4.90,
            peso_2_tasa=-0.001387,
            peso_3_base_g=4.90,
            peso_3_tasa=-0.001387,
            multiplicador_carga=factor_carga,
        )
        fuente_prior = "automatico"
    else:
        base = replace(
            prior,
            area_ha=float(area_ha),
            plantas=float(plantas),
            fecha_pivote=pd.Timestamp(fecha_pivote).normalize(),
            multiplicador_carga=factor_carga,
        )
        fuente_prior = "historico"
    return ajustar_oleadas_asof(
        base,
        observaciones if observaciones is not None else pd.DataFrame(),
        fecha_corte=fecha_corte,
        intervalo_dias=intervalo_dias,
        fuerza_prior=fuerza_prior,
        fuente_prior=fuente_prior,
    )


def construir_ventanas_horizonte(fecha_emision: object, semanas: int = 6) -> pd.DataFrame:
    """Construye H1...Hn con la misma convención semanal del panel operativo.

    La primera ventana empieza el lunes de la semana de emisión y termina el
    siguiente lunes. El lunes final es la llave semanal usada por el panel
    fenológico; no se consume ningún real para construirla.
    """

    if not 1 <= int(semanas) <= 52:
        raise ValueError("semanas debe estar entre 1 y 52")
    emision = pd.Timestamp(fecha_emision).normalize()
    lunes = emision - pd.to_timedelta(int(emision.weekday()), unit="D")
    inicio = [lunes + pd.to_timedelta(7 * i, unit="D") for i in range(int(semanas))]
    fin = [fecha + pd.to_timedelta(7, unit="D") for fecha in inicio]
    return pd.DataFrame(
        {
            "horizonte_semanas": range(1, int(semanas) + 1),
            "fecha_inicio": inicio,
            "fecha_objetivo": fin,
        }
    )


def _ventanas_validas(
    fecha_emision: object,
    semanas: int,
    ventanas: pd.DataFrame | None,
) -> pd.DataFrame:
    if ventanas is None:
        return construir_ventanas_horizonte(fecha_emision, semanas)
    requeridas = {"fecha_inicio", "fecha_objetivo"}
    faltantes = requeridas - set(ventanas.columns)
    if faltantes:
        raise ValueError(f"ventanas requiere: {sorted(faltantes)}")
    salida = ventanas.copy()
    salida["fecha_inicio"] = pd.to_datetime(salida.fecha_inicio, errors="raise").dt.normalize()
    salida["fecha_objetivo"] = pd.to_datetime(salida.fecha_objetivo, errors="raise").dt.normalize()
    if (salida.fecha_objetivo <= salida.fecha_inicio).any():
        raise ValueError("cada ventana debe terminar después de empezar")
    if "horizonte_semanas" not in salida:
        salida.insert(0, "horizonte_semanas", range(1, len(salida) + 1))
    if salida.empty:
        raise ValueError("ventanas no puede estar vacía")
    return salida.reset_index(drop=True)


def _proyectar_ventanas(parametros: MacroParams, ventanas: pd.DataFrame) -> pd.DataFrame:
    filas: list[dict[str, Any]] = []
    medias = np.array(
        [
            parametros.ola_1_media_dias,
            parametros.ola_2_media_dias,
            parametros.ola_3_media_dias,
        ],
        dtype=float,
    )
    desvios = np.array(
        [
            parametros.ola_1_desvio_dias,
            parametros.ola_2_desvio_dias,
            parametros.ola_3_desvio_dias,
        ],
        dtype=float,
    )
    cargas = np.array(
        [
            parametros.ola_1_multiplicador,
            parametros.ola_2_multiplicador,
            parametros.ola_3_multiplicador,
        ],
        dtype=float,
    )
    bases = np.array(
        [
            parametros.peso_1_base_g,
            parametros.peso_2_base_g,
            parametros.peso_3_base_g,
        ],
        dtype=float,
    )
    tasas = np.array(
        [parametros.peso_1_tasa, parametros.peso_2_tasa, parametros.peso_3_tasa], dtype=float
    )
    factor_carga = max(float(parametros.multiplicador_carga), 0.0)
    for fila in ventanas.itertuples(index=False):
        inicio = pd.Timestamp(fila.fecha_inicio)
        fin = pd.Timestamp(fila.fecha_objetivo)
        t_inicio = float((inicio - parametros.fecha_pivote).days)
        t_fin = float((fin - parametros.fecha_pivote).days)
        frutos_brutos = np.array(
            [
                _fraccion_numerica(
                    np.array([t_inicio]),
                    np.array([t_fin]),
                    media,
                    desvio,
                    carga,
                )[0]
                for media, desvio, carga in zip(medias, desvios, cargas, strict=True)
            ],
            dtype=float,
        )
        frutos_brutos = np.maximum(frutos_brutos, 0.0)
        frutos = frutos_brutos * factor_carga
        pesos = bases * np.exp(tasas * t_fin)
        total_bruto = float(frutos_brutos.sum())
        peso_promedio = (
            float(np.dot(frutos_brutos, pesos) / total_bruto) if total_bruto > 0 else 0.0
        )
        kg_olas = parametros.plantas * frutos * pesos / 1000.0
        kg_total = float(kg_olas.sum())
        total_frutos = float(frutos.sum())
        registro: dict[str, Any] = {
            "horizonte_semanas": int(fila.horizonte_semanas),
            "fecha_inicio": inicio,
            "fecha_objetivo": fin,
            "dias_desde_poda": t_fin,
            "frutos_por_planta": total_frutos,
            "peso_baya_g": peso_promedio,
            "plantas": float(parametros.plantas),
            "kg": kg_total,
            "kg_ha": kg_total / float(parametros.area_ha),
            "kg_acumulado": 0.0,
            "interpretacion": (
                "oleadas gaussianas manuales; la atribucion es mecanica y no causal"
            ),
        }
        for indice in range(3):
            numero = indice + 1
            registro[f"frutos_ola_{numero}"] = float(frutos[indice])
            registro[f"peso_ola_{numero}_g"] = float(pesos[indice])
            registro[f"kg_ola_{numero}"] = float(kg_olas[indice])
            registro[f"participacion_ola_{numero}"] = (
                float(kg_olas[indice] / kg_total) if kg_total > 0 else 0.0
            )
        filas.append(registro)
    salida = pd.DataFrame(filas)
    salida["kg_acumulado"] = salida.kg.cumsum()
    return salida


def proyectar_oleadas_horizonte(
    parametros: MacroParams,
    fecha_emision: object,
    *,
    semanas: int = 6,
    ventanas: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Proyecta H1...Hn por oleada sin leer resultados posteriores al corte."""

    if not isinstance(parametros, MacroParams):
        raise TypeError("parametros debe ser MacroParams")
    ventanas_validas = _ventanas_validas(fecha_emision, semanas, ventanas)
    salida = _proyectar_ventanas(parametros, ventanas_validas)
    salida.insert(0, "fecha_emision", pd.Timestamp(fecha_emision).normalize())
    return salida


def proyectar_fila_manual_horizonte(
    fila: Mapping[str, Any] | pd.Series,
    fecha_emision: object,
    *,
    semanas: int = 6,
    parametros_ajustados: Mapping[str, Any] | None = None,
    ventanas: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Atajo para integrar una fila ``Parametros`` del Excel y su ajuste opcional."""

    registro = dict(fila)
    if parametros_ajustados:
        registro.update(dict(parametros_ajustados))
    parametros = parametros_desde_fila(registro)
    return proyectar_oleadas_horizonte(
        parametros,
        fecha_emision,
        semanas=semanas,
        ventanas=ventanas,
    )


def _reemplazar_bloque(
    actual: MacroParams,
    destino: MacroParams,
    bloque: str,
) -> MacroParams:
    campos = _BLOQUES_EXPLICACION.get(bloque)
    if campos is None:
        raise ValueError(f"Bloque de explicación no soportado: {bloque}")
    valores = {campo: getattr(destino, campo) for campo in campos}
    return replace(actual, **valores)


def atribuir_cambio_oleadas(
    parametros_base: MacroParams,
    parametros_finales: MacroParams,
    fecha_emision: object,
    *,
    semanas: int = 6,
    ventanas: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Explica el cambio de una proyección por bloques de parámetros.

    La salida tiene una fila por horizonte, oleada y bloque. ``delta_kg`` es la
    diferencia incremental al cambiar un bloque sobre los bloques anteriores; por
    eso la suma de los bloques reproduce exactamente la diferencia entre el
    escenario final y el base. El orden está declarado para que la atribución sea
    reproducible y auditable.
    """

    ventanas_validas = _ventanas_validas(fecha_emision, semanas, ventanas)
    base = _proyectar_ventanas(parametros_base, ventanas_validas)
    actual = parametros_base
    filas: list[dict[str, Any]] = []
    for orden, bloque in enumerate(_BLOQUES_EXPLICACION, start=1):
        siguiente = _reemplazar_bloque(actual, parametros_finales, bloque)
        anterior_proyectado = _proyectar_ventanas(actual, ventanas_validas)
        siguiente_proyectado = _proyectar_ventanas(siguiente, ventanas_validas)
        final_proyectado = _proyectar_ventanas(parametros_finales, ventanas_validas)
        for posicion in range(len(ventanas_validas)):
            horizonte = int(base.iloc[posicion].horizonte_semanas)
            for indice in range(1, 4):
                columna = f"kg_ola_{indice}"
                delta = float(
                    siguiente_proyectado.iloc[posicion][columna]
                    - anterior_proyectado.iloc[posicion][columna]
                )
                filas.append(
                    {
                        "fecha_emision": pd.Timestamp(fecha_emision).normalize(),
                        "horizonte_semanas": horizonte,
                        "ola": indice,
                        "bloque": bloque,
                        "orden_atribucion": orden,
                        "kg_base": float(base.iloc[posicion][columna]),
                        "kg_final": float(final_proyectado.iloc[posicion][columna]),
                        "delta_kg": delta,
                        "interpretacion": "contribucion mecanica; no evidencia causal",
                    }
                )
        actual = siguiente
    return pd.DataFrame(filas)


__all__ = [
    "ResultadoAjusteOleadasAsOf",
    "ajustar_oleadas_asof",
    "atribuir_cambio_oleadas",
    "construir_prior_automatico",
    "construir_ventanas_horizonte",
    "proyectar_fila_manual_horizonte",
    "proyectar_oleadas_horizonte",
]
