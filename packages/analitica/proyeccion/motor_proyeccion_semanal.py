"""Motor de Proyección Semanal Operativa de Aqu Anqa.

Replicación fiel y determinística del modelo agronómico de proyección semanal
utilizado en Excel/VBA (ProySemanal_33_*.xlsm) y Access (H01_ProdHistorica / H0104 / 0301).

Características:
- Modelo de 3 flujos/poblaciones gaussianas (Gauss Mixture Model - GMM).
- Curva exponencial de decaimiento de calibre / peso de baya.
- Reglas exactas de calendario de reingreso y saltos de fin de semana (WEEKDAY 21).
- Generación de tablas de hechos proyectados (BDProy), matrices resumen diarias/semanales
  (PDI) y reportes de estimación trisemanales.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd
from scipy.special import ndtr


def safe_float(val: Any, default: float = 0.0) -> float:
    """Convierte valores a float y usa el valor por defecto ante entradas inválidas."""
    if val is None:
        return default
    if isinstance(val, (int, float)):
        return float(val) if not (math.isnan(val) or math.isinf(val)) else default
    val_str = str(val).strip()
    if not val_str or val_str.startswith("="):
        return default
    try:
        return float(val_str)
    except (ValueError, TypeError):
        return default


def safe_date(val: Any, default: date | None = None) -> date | None:
    """Convierte de forma segura cualquier valor a objeto date."""
    if val is None or val == "":
        return default
    if isinstance(val, date) and not isinstance(val, datetime):
        return val
    if isinstance(val, (datetime, pd.Timestamp)):
        return val.date()
    val_str = str(val).strip()
    if not val_str or val_str.startswith("="):
        return default
    try:
        return datetime.strptime(val_str[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return default


def extraer_fechas_pasadas(
    fila_panel: pd.Series | dict[str, Any],
    *,
    pasadas_esperadas: int | None = None,
) -> list[date]:
    """Extrae y valida todo el calendario ``FePas1..FePasN`` de un lote.

    El número de pasadas pertenece al calendario operativo de cada corrida. No debe
    fijarse globalmente en cinco: Ayllu, por ejemplo, tiene seis. Un calendario
    incompleto, repetido o desordenado se rechaza para no producir una proyección
    silenciosamente truncada.

    ``pasadas_esperadas`` solo valida una expectativa externa; nunca recorta la lista.
    """
    columnas: dict[int, Any] = {}
    for columna in fila_panel.index:
        nombre = str(columna).strip().casefold()
        coincidencia = re.fullmatch(r"fepas(\d+)", nombre)
        if coincidencia:
            columnas[int(coincidencia.group(1))] = columna

    if not columnas:
        raise ValueError("El lote no tiene columnas FePas")

    indices = sorted(columnas)
    esperados = list(range(1, max(indices) + 1))
    if indices != esperados:
        raise ValueError(
            "El calendario FePas tiene índices incompletos: "
            f"se encontraron {indices}, se esperaba {esperados}"
        )

    fechas: list[date] = []
    for indice in indices:
        valor = fila_panel[columnas[indice]]
        fecha = safe_date(valor)
        if fecha is None:
            raise ValueError(f"FePas{indice} está vacío o no es una fecha válida")
        fechas.append(fecha)

    if len(set(fechas)) != len(fechas):
        raise ValueError("Las fechas FePas no pueden repetirse")
    if fechas != sorted(fechas):
        raise ValueError("Las fechas FePas deben estar en orden creciente")
    if pasadas_esperadas is not None and len(fechas) != pasadas_esperadas:
        raise ValueError(
            f"El calendario tiene {len(fechas)} pasadas; la fuente esperaba {pasadas_esperadas}"
        )
    return fechas


def norm_cdf(x: float, mean: float, std: float) -> float:
    """Función de distribución acumulada normal exacta (idéntica a NORM.DIST(x, mean, std, 1))."""
    if std <= 0:
        return 1.0 if x >= mean else 0.0
    return float(ndtr((x - mean) / std))


def semana_iso_21(fecha: date | datetime | pd.Timestamp) -> int:
    """Semana ISO 8601 (equivalente exacto a WorksheetFunction.WeekNum(fecha, 21))."""
    if isinstance(fecha, (datetime, pd.Timestamp)):
        fecha = fecha.date()
    return int(fecha.isocalendar()[1])


def ajustar_dia_habil(fecha: date) -> date:
    """Ajusta fecha si cae en fin de semana (Sábado -> Lunes (+2), Domingo -> Lunes (+1))."""
    wd = fecha.weekday()  # Lunes=0, ..., Sábado=5, Domingo=6
    if wd == 5:  # Sábado
        return fecha + timedelta(days=2)
    elif wd == 6:  # Domingo
        return fecha + timedelta(days=1)
    return fecha


def calcular_fechas_reingreso(
    fecha_inicio: date,
    intervalos_reingreso: list[int],
) -> list[date]:
    """Genera las fechas proyectadas de cosecha respetando días de reingreso y fines de semana."""
    fechas: list[date] = []
    fecha_actual = fecha_inicio
    for dias in intervalos_reingreso:
        fecha_siguiente = fecha_actual + timedelta(days=dias)
        fecha_siguiente = ajustar_dia_habil(fecha_siguiente)
        fechas.append(fecha_siguiente)
        fecha_actual = fecha_siguiente
    return fechas


@dataclass
class LoteParametrosProyeccion:
    """Parámetros agronómicos y biométricos completos para la proyección de un lote."""

    fundo: str
    fundo_ppto: str
    modulo: str
    turno: str
    lote: str
    area_ha: float
    n_plantas: float
    fecha_poda: date

    # Parámetros de Poblaciones Gaussianas (P1, P2, P3)
    # X = media (días desde poda), O = desviación (días), N = frutos/planta
    x1: float
    o1: float
    n1: float

    x2: float = 0.0
    o2: float = 0.0
    n2: float = 0.0

    x3: float = 0.0
    o3: float = 0.0
    n3: float = 0.0

    # Parámetros de Curva de Peso (A = base gramos, B = tasa exponencial)
    a1: float = 0.0
    b1: float = 0.0

    a2: float = 0.0
    b2: float = 0.0

    a3: float = 0.0
    b3: float = 0.0

    # Factor de caída / merma global
    factor_caida: float = 1.0


@dataclass
class RegistroBDProy:
    """Registro individual de cosecha proyectada (fila de BDProy)."""

    campana: str
    pana: float
    fundo_ppto: str
    modulo: str
    turno: str
    lote: str
    area_ha: float
    fecha_ini: date
    fecha_cos: date
    reingreso_dias: int
    semana: int
    frutos_planta: float
    peso_promedio_g: float
    rendimiento_kg_ha: float
    kg: float
    frutos_total: float
    fundo_q: str


def proyectar_lote_pasadas(
    params: LoteParametrosProyeccion,
    pana_inicial: float,
    fecha_inicio_primera_pana: date,
    fechas_cosecha_pasadas: list[date],
    factor_caida: float = 0.90,
    campana: str = "C2026",
    fundo_q: str = "Aqu Anqa",
) -> list[RegistroBDProy]:
    """Calcula la proyección completa de un lote a través de sus pasadas programadas."""
    registros: list[RegistroBDProy] = []

    fpoda = params.fecha_poda
    n_pasadas = len(fechas_cosecha_pasadas)

    for it in range(1, n_pasadas + 1):
        pana_num = pana_inicial + it - 1
        ini = fecha_inicio_primera_pana if it == 1 else fechas_cosecha_pasadas[it - 2]
        f_cos = fechas_cosecha_pasadas[it - 1]

        reire = (f_cos - ini).days
        sem = semana_iso_21(f_cos)

        t_fin = (f_cos - fpoda).days
        t_ini = (ini - fpoda).days

        # 1. Frutos por población
        frt1 = (
            norm_cdf(t_fin, params.x1, params.o1) - norm_cdf(t_ini, params.x1, params.o1)
        ) * params.n1
        frt2 = (
            (norm_cdf(t_fin, params.x2, params.o2) - norm_cdf(t_ini, params.x2, params.o2))
            * params.n2
            if params.n2 > 0
            else 0.0
        )
        frt3 = (
            (norm_cdf(t_fin, params.x3, params.o3) - norm_cdf(t_ini, params.x3, params.o3))
            * params.n3
            if params.n3 > 0
            else 0.0
        )

        frt_total_planta = (frt1 + frt2 + frt3) * factor_caida

        # 2. Peso unitario por población
        pes1 = params.a1 * math.exp(params.b1 * t_fin) if params.a1 > 0 else 0.0
        pes2 = params.a2 * math.exp(params.b2 * t_fin) if params.a2 > 0 else 0.0
        pes3 = params.a3 * math.exp(params.b3 * t_fin) if params.a3 > 0 else 0.0

        sum_frt = frt1 + frt2 + frt3
        pes_promedio = (
            (frt1 * pes1 + frt2 * pes2 + frt3 * pes3) / sum_frt if sum_frt > 0 else 0.0
        )

        # 3. Kilos, rendimientos y totales
        kg = (frt_total_planta * pes_promedio * params.n_plantas) / 1000.0
        rend = kg / params.area_ha if params.area_ha > 0 else 0.0
        frutos_totales = frt_total_planta * params.n_plantas

        reg = RegistroBDProy(
            campana=campana,
            pana=pana_num,
            fundo_ppto=params.fundo_ppto,
            modulo=params.modulo,
            turno=params.turno,
            lote=params.lote,
            area_ha=params.area_ha,
            fecha_ini=ini,
            fecha_cos=f_cos,
            reingreso_dias=reire,
            semana=sem,
            frutos_planta=frt_total_planta,
            peso_promedio_g=pes_promedio,
            rendimiento_kg_ha=rend,
            kg=kg,
            frutos_total=frutos_totales,
            fundo_q=fundo_q,
        )
        registros.append(reg)

    return registros


def ejecutar_proyeccion_semanal_dataframe(
    df_parametros: pd.DataFrame,
    df_panel: pd.DataFrame,
    campana: str = "C2026",
    fundo_nombre: str = "Aqu Anqa",
    pasadas_esperadas: int | None = None,
) -> pd.DataFrame:
    """Ejecuta el modelo operativo usando el calendario completo de cada lote.

    ``pasadas_esperadas`` es opcional y solo sirve como control de calidad. La cantidad
    efectiva siempre se obtiene de las columnas FePas presentes en cada fila del Panel.
    """
    params_dict: dict[tuple[str, str], LoteParametrosProyeccion] = {}

    for _, r in df_parametros.iterrows():
        modulo = str(r.get("Modulo", r.get("modulo", ""))).strip()
        lote = str(r.get("Lote", r.get("lote", ""))).strip()
        fundo = str(r.get("Fundo", r.get("fundo", ""))).strip()
        fundo_ppto = str(r.get("FundoPPto", r.get("fundo_ppto", fundo))).strip()
        turno = str(r.get("Turno", r.get("turno", ""))).strip()

        area_ha = safe_float(r.get("Area", r.get("area_ha", 0.0)))
        n_plantas = safe_float(r.get("NPlantas", r.get("n_plantas", 0.0)))

        if area_ha <= 0 or n_plantas <= 0 or not lote or not modulo:
            continue

        fpoda = safe_date(r.get("FPoda", r.get("fecha_poda", "2026-01-01")), date(2026, 1, 1))

        x1 = safe_float(r.get("X1", r.get("x1", 0.0)))
        o1 = safe_float(r.get("O1", r.get("o1", 0.0)))
        n1 = safe_float(r.get("N1", r.get("n1", 0.0)))

        x2 = safe_float(r.get("X2", r.get("x2", 0.0)))
        o2 = safe_float(r.get("O2", r.get("o2", 0.0)))
        n2 = safe_float(r.get("N2", r.get("n2", 0.0)))

        x3 = safe_float(r.get("X3", r.get("x3", 0.0)))
        o3 = safe_float(r.get("O3", r.get("o3", 0.0)))
        n3 = safe_float(r.get("N3", r.get("n3", 0.0)))

        a1 = safe_float(r.get("A1", r.get("a1", 0.0)))
        b1 = safe_float(r.get("B1", r.get("b1", 0.0)))

        a2 = safe_float(r.get("A2", r.get("a2", 0.0)))
        b2 = safe_float(r.get("B2", r.get("b2", 0.0)))

        a3 = safe_float(r.get("A3", r.get("a3", 0.0)))
        b3 = safe_float(r.get("B3", r.get("b3", 0.0)))

        lp = LoteParametrosProyeccion(
            fundo=fundo,
            fundo_ppto=fundo_ppto,
            modulo=modulo,
            turno=turno,
            lote=lote,
            area_ha=area_ha,
            n_plantas=n_plantas,
            fecha_poda=fpoda,
            x1=x1,
            o1=o1,
            n1=n1,
            x2=x2,
            o2=o2,
            n2=n2,
            x3=x3,
            o3=o3,
            n3=n3,
            a1=a1,
            b1=b1,
            a2=a2,
            b2=b2,
            a3=a3,
            b3=b3,
        )
        params_dict[(modulo, lote)] = lp

    todos_registros: list[dict[str, Any]] = []

    for _, prow in df_panel.iterrows():
        modulo = str(prow.get("Modulo", prow.get("modulo", ""))).strip()
        lote = str(prow.get("Lote", prow.get("lote", ""))).strip()

        if (modulo, lote) not in params_dict:
            continue

        lp = params_dict[(modulo, lote)]

        # Algunas versiones del formato ProySemanal llaman ``Fundo`` a esta primera
        # columna aunque el valor sea el número de paña. Es un alias histórico del
        # Panel, no el fundo textual de Parametros.
        pana_ini = safe_float(
            prow.get(
                "Paña",
                prow.get("pana", prow.get("Pana", prow.get("Fundo", 1.0))),
            ),
            default=1.0,
        )
        f_ini = safe_date(prow.get("Finicio", prow.get("finicio", prow.get("FechaIni", None))))
        caida = safe_float(
            prow.get("Caida", prow.get("%Caida", prow.get("caida", 0.90))), default=0.90
        )

        if f_ini is None:
            raise ValueError(f"El lote {modulo}/{lote} no tiene Finicio válido")
        try:
            fechas_pasadas = extraer_fechas_pasadas(
                prow,
                pasadas_esperadas=pasadas_esperadas,
            )
        except ValueError as exc:
            raise ValueError(f"Calendario inválido para {modulo}/{lote}: {exc}") from exc

        # Determinar FundoQ exacto según reglas de negocio de la operación
        fundo_q = fundo_nombre
        if "Arena" in fundo_nombre:
            fundo_q = "Aqu Anqa 1"
        elif "Ayllu" in fundo_nombre:
            fundo_q = "Aqu Anqa 4"
        elif "Quri" in fundo_nombre:
            fundo_q = "Aqu Anqa 2"
        elif "Kawsay" in fundo_nombre:
            if modulo in ["M06", "M07", "M08", "M09", "M10A", "M10B"]:
                fundo_q = "Aqu Anqa 3"
            else:
                fundo_q = "Aqu Anqa 5"

        regs = proyectar_lote_pasadas(
            params=lp,
            pana_inicial=pana_ini,
            fecha_inicio_primera_pana=f_ini,
            fechas_cosecha_pasadas=fechas_pasadas,
            factor_caida=caida,
            campana=campana,
            fundo_q=fundo_q,
        )

        for reg in regs:
            todos_registros.append(
                {
                    "Campaña": reg.campana,
                    "Paña": reg.pana,
                    "FundoPPto": reg.fundo_ppto,
                    "Modulo": reg.modulo,
                    "Turno": reg.turno,
                    "Lote": reg.lote,
                    "Area": reg.area_ha,
                    "Fechaini": reg.fecha_ini,
                    "FeCos": reg.fecha_cos,
                    "ReiRe": reg.reingreso_dias,
                    "Sem": reg.semana,
                    "Frtutos": reg.frutos_planta,
                    "Peso": reg.peso_promedio_g,
                    "Rend": reg.rendimiento_kg_ha,
                    "Kg": reg.kg,
                    "PersCos": "",
                    "Frutototal": reg.frutos_total,
                    "FundoQ": reg.fundo_q,
                }
            )

    return pd.DataFrame(todos_registros)


def generar_matriz_resumen_pdi(df_bdproy: pd.DataFrame) -> pd.DataFrame:
    """Genera la tabla pivote de PDI equivalente a la hoja Resumen de Excel."""
    if df_bdproy.empty:
        return pd.DataFrame()

    piv = df_bdproy.pivot_table(
        index=["FundoQ", "Modulo"],
        columns=["Sem", "FeCos"],
        values=["Kg", "Rend"],
        aggfunc="sum",
        fill_value=0.0,
    )
    return piv
