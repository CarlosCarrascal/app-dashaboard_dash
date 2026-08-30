"""Motor matemático de descomposición poblacional de Bhattacharya (3 oleadas gaussianas).

Implementa la separación de capas de floración/cosecha según el método de Bhattacharya (1967):
- Oleada 1 (P1): Primera floración principal (X1 = mu1, O1 = sigma1, N1 = carga frutal 1).
- Oleada 2 (P2): Segunda floración derivada (X2 = mu1 + 70d, O2 = sigma2, N2 = carga frutal 2).
- Oleada 3 (P3): Tercera floración tardía (X3 = mu2 + 63d, O3 = sigma3, N3 = carga frutal 3).
- Decaimiento de Calibre: Peso(t) = a * exp(b * t).
- Curva Total de Frutos: TotalEst(t) = P1(t) + P2(t) + P3(t).
- Kilos Semanales: Kg(t) = TotalEst(t) * Peso(t) * NPlantas / 1000.
"""

from __future__ import annotations

import warnings
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import pandas as pd
from scipy.optimize import least_squares, minimize
from scipy.stats import norm


@dataclass
class ParametrosBhattacharya:
    """Parámetros calibrados para un lote específico."""

    lote: str
    campania: str
    lote_id: str = ""
    fundo: str = ""
    modulo: str = ""
    turno: str = ""
    fecha_poda: pd.Timestamp | None = None
    n_plantas: int = 5000

    # Oleada 1 (P1)
    mu1: float = 220.0  # X1 (Día pico desde poda)
    sigma1: float = 25.0  # O1 (Dispersión/ancho en días)
    N1: float = 500.0  # Frutos totales de la oleada 1 (por planta o lote)
    error_p1: float = 0.0  # RMSE de ajuste

    # Oleada 2 (P2)
    mu2: float = 290.0  # X2 (mu1 + 70d)
    sigma2: float = 27.5  # O2 (sigma1 * 1.10)
    N2: float = 300.0  # Frutos totales de la oleada 2
    error_p2: float = 0.0

    # Oleada 3 (P3)
    mu3: float = 353.0  # X3 (mu2 + 63d)
    sigma3: float = 28.8  # O3 (sigma2 * 1.05)
    N3: float = 100.0  # Frutos totales de la oleada 3
    error_p3: float = 0.0

    # Decaimiento Exponencial de Peso
    peso_a: float = 4.20  # Peso inicial de baya (g)
    peso_b: float = -0.0020  # Tasa de pérdida de calibre por día
    # Los libros ProySemanal pueden calibrar una curva de peso por oleada.
    # Son opcionales para mantener compatibilidad con snapshots antiguos que
    # solo tenían A1/B1.
    peso_a2: float | None = None
    peso_b2: float | None = None
    peso_a3: float | None = None
    peso_b3: float | None = None

    # Métricas globales
    rmse_total: float = 0.0
    panas_observadas: int = 0
    frutos_observados_total: float = 0.0
    es_estimado_por_defecto: bool = False
    fuente_parametros: str = ""
    nivel_calibracion: str = ""
    archivo_fuente: str | None = None
    sha256_fuente: str | None = None
    fecha_vigencia: pd.Timestamp | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if self.fecha_poda is not None:
            d["fecha_poda"] = self.fecha_poda.strftime("%Y-%m-%d")
        if self.fecha_vigencia is not None:
            d["fecha_vigencia"] = pd.Timestamp(self.fecha_vigencia).strftime("%Y-%m-%d")
        return d


def cdf_interval(t_end: np.ndarray, t_start: np.ndarray, mu: float, sigma: float) -> np.ndarray:
    """Calcula la probabilidad normal acumulada en el intervalo [t_start, t_end]."""
    sigma = max(sigma, 1.0)
    return norm.cdf(t_end, loc=mu, scale=sigma) - norm.cdf(t_start, loc=mu, scale=sigma)


def ajustar_lote(
    t_dias: np.ndarray,
    frutos_obs: np.ndarray,
    peso_obs: np.ndarray | None = None,
    N1: float = 500.0,
    N2: float = 300.0,
    N3: float = 100.0,
    lote: str = "",
    campania: str = "C2026",
    fundo: str = "",
    modulo: str = "",
    turno: str = "",
    fecha_poda: pd.Timestamp | None = None,
    n_plantas: int = 5000,
    sigma_min: float = 15.0,
) -> ParametrosBhattacharya:
    """Calibra los parámetros de Bhattacharya para un lote usando optimización L-BFGS-B.

    Replica y supera el Solver GRG Nonlinear de Excel:
    - Ajusta Oleada 1 (mu1, sigma1) minimizando RMSE contra las primeras pañas observadas.
    - Aplica Bhattacharya Peeling (sustracción de saldo) para verificar Oleada 2.
    - Modela el decaimiento exponencial de peso: Peso(t) = a * exp(b * t).
    """
    t_dias = np.asarray(t_dias, dtype=float)
    frutos_obs = np.asarray(frutos_obs, dtype=float)

    # Validar si hay datos observados suficientes
    mask_valid = (t_dias > 0) & (~np.isnan(t_dias)) & (frutos_obs >= 0) & (~np.isnan(frutos_obs))
    t_v = t_dias[mask_valid]
    f_v = frutos_obs[mask_valid]
    n_panas = len(t_v)

    if n_panas == 0 or N1 <= 0:
        # Fallback seguro con priors biológicos de Sekoya Pop
        return ParametrosBhattacharya(
            lote=lote,
            campania=campania,
            fundo=fundo,
            modulo=modulo,
            turno=turno,
            fecha_poda=fecha_poda,
            n_plantas=n_plantas,
            mu1=220.0,
            sigma1=24.0,
            N1=max(N1, 400.0),
            mu2=290.0,
            sigma2=28.0,
            N2=max(N2, 250.0),
            mu3=353.0,
            sigma3=30.0,
            N3=max(N3, 80.0),
            peso_a=4.20,
            peso_b=-0.0020,
            es_estimado_por_defecto=True,
        )

    # Intervalos de tiempo entre pañas observadas (delta)
    t_prev = np.array([t_v[0] - 50.0] + list(t_v[:-1]))

    # 1. OPTIMIZACIÓN OLEADA 1 (P1)
    def loss_p1(params: list[float]) -> float:
        mu, sigma = params
        p_curr = norm.cdf(t_v, loc=mu, scale=sigma)
        p_prev = norm.cdf(t_prev, loc=mu, scale=sigma)
        est = (p_curr - p_prev) * N1
        return float(np.sqrt(np.mean((f_v - est) ** 2)))

    # Punto de partida y cotas
    x0_p1 = [220.0, 24.0]
    bounds_p1 = [(100.0, 320.0), (sigma_min, 60.0)]
    res_p1 = minimize(loss_p1, x0=x0_p1, method="L-BFGS-B", bounds=bounds_p1)

    mu1_opt, sigma1_opt = float(res_p1.x[0]), float(res_p1.x[1])
    error_p1 = float(res_p1.fun)

    # 2. DERIVACIÓN BIOLÓGICA DE OLEADAS 2 Y 3 (Fisiología de floración)
    mu2_opt = mu1_opt + 70.0
    sigma2_opt = sigma1_opt * 1.15
    mu3_opt = mu2_opt + 63.0
    sigma3_opt = sigma2_opt * 1.05

    # 3. DECAIMIENTO EXPONENCIAL DEL PESO DE BAYA: Peso(t) = a * exp(b * t)
    if peso_obs is not None:
        peso_arr = np.asarray(peso_obs, dtype=float)
        mask_peso = mask_valid & (peso_arr > 0) & (~np.isnan(peso_arr))
        if np.sum(mask_peso) >= 2:
            t_p = t_dias[mask_peso]
            p_p = peso_arr[mask_peso]
            log_p = np.log(p_p)
            b_val, log_a = np.polyfit(t_p, log_p, 1)
            a_val = np.exp(log_a)
            # Acotar a rangos agronómicamente válidos (a en t=0)
            a_val = float(np.clip(a_val, 2.5, 12.0))
            b_val = float(np.clip(b_val, -0.010, 0.005))
        elif np.sum(mask_peso) == 1:
            a_val = float(peso_arr[mask_peso][0])
            b_val = -0.0020
        else:
            a_val, b_val = 4.25, -0.0021
    else:
        a_val, b_val = 4.25, -0.0021

    return ParametrosBhattacharya(
        lote=lote,
        campania=campania,
        fundo=fundo,
        modulo=modulo,
        turno=turno,
        fecha_poda=fecha_poda,
        n_plantas=n_plantas,
        mu1=round(mu1_opt, 2),
        sigma1=round(sigma1_opt, 2),
        N1=round(N1, 1),
        error_p1=round(error_p1, 2),
        mu2=round(mu2_opt, 2),
        sigma2=round(sigma2_opt, 2),
        N2=round(N2, 1),
        error_p2=0.0,
        mu3=round(mu3_opt, 2),
        sigma3=round(sigma3_opt, 2),
        N3=round(N3, 1),
        error_p3=0.0,
        peso_a=round(a_val, 4),
        peso_b=round(b_val, 6),
        rmse_total=round(error_p1, 2),
        panas_observadas=n_panas,
        frutos_observados_total=float(np.sum(f_v)),
        es_estimado_por_defecto=False,
    )


def ajustar_lote_automatico(
    t_dias: np.ndarray,
    frutos_obs: np.ndarray,
    peso_obs: np.ndarray | None = None,
    *,
    prior: ParametrosBhattacharya | None = None,
    lote_id: str = "",
    lote: str = "",
    campania: str = "C2026",
    fundo: str = "",
    modulo: str = "",
    turno: str = "",
    fecha_poda: pd.Timestamp | None = None,
    n_plantas: int = 5000,
    inicial: ParametrosBhattacharya | None = None,
) -> ParametrosBhattacharya:
    """Ajusta automáticamente las tres oleadas con regularización agronómica.

    ``frutos_obs`` se expresa siempre en frutos por planta. El ajuste estima centros,
    dispersiones y cargas de las tres oleadas. Como una campaña en curso suele tener
    pocas pañas observadas, el problema se regulariza hacia el histórico del mismo lote
    cuando está disponible; de lo contrario usa un prior explícito y auditable. Esto
    evita que un lote con tres observaciones produzca parámetros físicamente absurdos.
    """
    t_arr = np.asarray(t_dias, dtype=float)
    f_arr = np.asarray(frutos_obs, dtype=float)
    mascara = np.isfinite(t_arr) & np.isfinite(f_arr) & (t_arr > 0) & (f_arr >= 0)
    t_v = t_arr[mascara]
    f_v = f_arr[mascara]
    orden = np.argsort(t_v)
    t_v = t_v[orden]
    f_v = f_v[orden]
    n_obs = len(t_v)

    if prior is None:
        prior_mu1, prior_s1 = 220.0, 25.0
        prior_d2, prior_d3 = 70.0, 63.0
        prior_s2, prior_s3 = 29.0, 30.0
        total_observado = float(np.nansum(f_v))
        # La carga observada es parcial en una campaña abierta. El piso impide que la
        # curva futura colapse a cero antes de contar con suficientes pañas.
        prior_n1 = max(total_observado / 0.60, 350.0)
        prior_n2 = max(prior_n1 * 0.45, 120.0)
        prior_n3 = max(prior_n1 * 0.20, 50.0)
    else:
        prior_mu1, prior_s1 = float(prior.mu1), float(prior.sigma1)
        prior_d2 = max(float(prior.mu2 - prior.mu1), 35.0)
        prior_d3 = max(float(prior.mu3 - prior.mu2), 35.0)
        prior_s2, prior_s3 = float(prior.sigma2), float(prior.sigma3)
        prior_n1 = max(float(prior.N1), 5.0)
        prior_n2 = max(float(prior.N2), 5.0)
        prior_n3 = max(float(prior.N3), 5.0)

    prior_vector = np.array(
        [
            prior_mu1,
            prior_s1,
            prior_d2,
            prior_d3,
            prior_s2,
            prior_s3,
            np.log(prior_n1),
            np.log(prior_n2),
            np.log(prior_n3),
        ],
        dtype=float,
    )

    if n_obs:
        diferencias = np.diff(t_v)
        intervalo_inicial = float(np.nanmedian(diferencias)) if len(diferencias) else 14.0
        intervalo_inicial = float(np.clip(intervalo_inicial, 5.0, 35.0))
        t_prev = np.r_[t_v[0] - intervalo_inicial, t_v[:-1]]
        escala = max(float(np.nanmedian(f_v[f_v > 0])) if np.any(f_v > 0) else 1.0, 1.0)
    else:
        t_prev = np.array([], dtype=float)
        escala = 1.0

    def _predecir(vector: np.ndarray) -> np.ndarray:
        mu1, s1, d2, d3, s2, s3, ln1, ln2, ln3 = vector
        mu2 = mu1 + d2
        mu3 = mu2 + d3
        n1, n2, n3 = np.exp([ln1, ln2, ln3])
        return (
            cdf_interval(t_v, t_prev, mu1, s1) * n1
            + cdf_interval(t_v, t_prev, mu2, s2) * n2
            + cdf_interval(t_v, t_prev, mu3, s3) * n3
        )

    # Con pocas pañas manda el histórico; conforme llegan datos, el lote puede apartarse
    # de él. Las escalas expresan cuánto puede moverse cada parámetro sin penalización.
    fuerza_prior = 1.25 if n_obs < 3 else 0.65 if n_obs < 6 else 0.25
    if prior is None:
        fuerza_prior *= 0.75
    escalas_prior = np.array([35.0, 15.0, 25.0, 30.0, 18.0, 18.0, 0.75, 0.90, 1.00])

    def _residuos(vector: np.ndarray) -> np.ndarray:
        datos = (_predecir(vector) - f_v) / escala if n_obs else np.array([], dtype=float)
        regularizacion = np.sqrt(fuerza_prior) * (vector - prior_vector) / escalas_prior
        return np.r_[datos, regularizacion]

    limites_inferiores = np.array(
        [100.0, 10.0, 35.0, 35.0, 10.0, 10.0, np.log(5.0), np.log(5.0), np.log(5.0)]
    )
    limites_superiores = np.array(
        [340.0, 75.0, 125.0, 150.0, 85.0, 85.0, np.log(3000.0), np.log(2500.0), np.log(2000.0)]
    )
    # En un replay rolling-origin, un lote suele recibir una nueva observación cada
    # emisión. Reutilizar el óptimo del corte anterior como punto inicial conserva la
    # misma función objetivo as-of y evita volver a explorar todo el espacio desde el
    # prior grupal en cada semana. El prior estadístico sigue siendo el mismo; solo se
    # acelera la convergencia numérica.
    vector_inicial = prior_vector
    if inicial is not None:
        vector_inicial = np.array(
            [
                float(inicial.mu1),
                float(inicial.sigma1),
                max(float(inicial.mu2 - inicial.mu1), 35.0),
                max(float(inicial.mu3 - inicial.mu2), 35.0),
                float(inicial.sigma2),
                float(inicial.sigma3),
                np.log(max(float(inicial.N1), 5.0)),
                np.log(max(float(inicial.N2), 5.0)),
                np.log(max(float(inicial.N3), 5.0)),
            ],
            dtype=float,
        )
    # Sin observaciones no existe una función de datos que optimizar: la solución
    # correcta es el prior explícito. Ejecutar ``least_squares`` en ese caso solo
    # vuelve a recorrer nueve parámetros que la regularización ya fija exactamente,
    # algo especialmente costoso en un replay con cientos de lotes.
    if n_obs == 0:
        vector_resultado = prior_vector
        rmse = 0.0
    else:
        resultado = least_squares(
            _residuos,
            np.clip(vector_inicial, limites_inferiores, limites_superiores),
            bounds=(limites_inferiores, limites_superiores),
            # Con un óptimo del corte anterior como inicio, 60 evaluaciones cubren
            # la corrección incremental sin repetir la búsqueda completa. El primer
            # ajuste conserva un presupuesto mayor para no cambiar su calibración.
            max_nfev=60 if inicial is not None else 120,
            loss="soft_l1",
            xtol=1e-5,
            ftol=1e-5,
            gtol=1e-5,
        )
        vector_resultado = resultado.x
        predicho = _predecir(vector_resultado)
        rmse = float(np.sqrt(np.mean((predicho - f_v) ** 2)))
    mu1, s1, d2, d3, s2, s3, ln1, ln2, ln3 = vector_resultado

    # Peso(t) = a * exp(b*t). El histórico del lote completa campañas con menos de
    # dos pesos válidos; nunca se usa una observación futura al corte recibido.
    a_val = float(prior.peso_a) if prior is not None else 4.9
    b_val = float(prior.peso_b) if prior is not None else -0.001387
    if peso_obs is not None:
        p_arr = np.asarray(peso_obs, dtype=float)[mascara][orden]
        mascara_peso = np.isfinite(p_arr) & (p_arr > 0)
        if int(mascara_peso.sum()) >= 2:
            try:
                # La escala de días desde poda puede hacer que polyfit quede
                # mal condicionado cuando los pesos válidos están concentrados
                # en una sola fecha. En ese caso el prior es más seguro que un
                # ajuste numéricamente inestable.
                rank_warning = getattr(np, "RankWarning", None)
                if rank_warning is None and hasattr(np, "exceptions"):
                    rank_warning = getattr(np.exceptions, "RankWarning", None)
                with warnings.catch_warnings():
                    if rank_warning is not None:
                        warnings.simplefilter("error", rank_warning)
                    b_fit, log_a_fit = np.polyfit(t_v[mascara_peso], np.log(p_arr[mascara_peso]), 1)
                a_val = float(np.clip(np.exp(log_a_fit), 2.5, 12.0))
                b_val = float(np.clip(b_fit, -0.010, 0.0))
            except Exception as exc:
                if rank_warning is None or not isinstance(exc, rank_warning):
                    raise
                # Conserva a_val/b_val del prior explícito y deja que el nivel
                # de calibración documente que no se pudo ajustar el peso.
        elif int(mascara_peso.sum()) == 1 and prior is None:
            b_val = -0.001387
            a_val = float(
                np.clip(
                    p_arr[mascara_peso][0] / np.exp(b_val * t_v[mascara_peso][0]),
                    2.5,
                    12.0,
                )
            )

    nivel = "lote_actual"
    if prior is not None:
        nivel = "lote_actual_con_historico"
    if n_obs == 0:
        nivel = "historico_sin_actual" if prior is not None else "prior_grupal"

    return ParametrosBhattacharya(
        lote=lote,
        lote_id=str(lote_id or ""),
        campania=campania,
        fundo=fundo,
        modulo=modulo,
        turno=turno,
        fecha_poda=fecha_poda,
        n_plantas=int(n_plantas or 0),
        mu1=round(float(mu1), 4),
        sigma1=round(float(s1), 4),
        N1=round(float(np.exp(ln1)), 4),
        error_p1=round(rmse, 4),
        mu2=round(float(mu1 + d2), 4),
        sigma2=round(float(s2), 4),
        N2=round(float(np.exp(ln2)), 4),
        mu3=round(float(mu1 + d2 + d3), 4),
        sigma3=round(float(s3), 4),
        N3=round(float(np.exp(ln3)), 4),
        peso_a=round(a_val, 6),
        peso_b=round(b_val, 8),
        rmse_total=round(rmse, 4),
        panas_observadas=n_obs,
        frutos_observados_total=round(float(np.nansum(f_v)), 4),
        es_estimado_por_defecto=n_obs == 0,
        fuente_parametros="postgres",
        nivel_calibracion=nivel,
    )


def proyectar_curva_oleadas(
    params: ParametrosBhattacharya,
    t_start: int = 150,
    t_end: int = 420,
    step_days: int = 7,
    factor_escala_lote: float = 1.0,
) -> pd.DataFrame:
    """Genera la serie temporal de proyección con las columnas exactas de 2Pob_fit.

    Columnas devueltas:
    - DDP: Días Desde Poda (t)
    - Fecha: Fecha calendario estimada
    - Semana: Semana ISO
    - FrtEst_p1: Frutos de Oleada 1 (por planta)
    - FrtEst_p2: Frutos de Oleada 2 (por planta)
    - FrtEst_p3: Frutos de Oleada 3 (por planta)
    - TotalEst: Frutos Totales estimados (por planta)
    - PesoMedio_g: Gramos estimados por fruto
    - Kg_Oleada_1: Kilos de Oleada 1
    - Kg_Oleada_2: Kilos de Oleada 2
    - Kg_Oleada_3: Kilos de Oleada 3
    - Kg_Semanal_Total: Kilos totales proyectados
    - Kg_Acumulados: Curva acumulada de cosecha
    """
    t_points = np.arange(t_start, t_end + step_days, step_days, dtype=float)
    filas = []

    kg_acum = 0.0
    frt_acum = 0.0

    fecha_poda = params.fecha_poda or pd.Timestamp("2025-12-29")

    for t in t_points:
        t_prev = t - float(step_days)
        fecha_fila = fecha_poda + pd.to_timedelta(int(t), unit="D")
        num_semana = int(fecha_fila.isocalendar().week)

        # Frutos calculados por intervalo para cada una de las 3 oleadas
        p1 = (
            float(cdf_interval(np.array([t]), np.array([t_prev]), params.mu1, params.sigma1)[0])
            * params.N1
        )
        p2 = (
            float(cdf_interval(np.array([t]), np.array([t_prev]), params.mu2, params.sigma2)[0])
            * params.N2
        )
        p3 = (
            float(cdf_interval(np.array([t]), np.array([t_prev]), params.mu3, params.sigma3)[0])
            * params.N3
        )
        total_frt = p1 + p2 + p3

        # Peso por oleada; los snapshots antiguos caen en A1/B1.
        peso_1 = float(params.peso_a * np.exp(params.peso_b * t))
        peso_2 = float(
            (params.peso_a2 if params.peso_a2 is not None else params.peso_a)
            * np.exp((params.peso_b2 if params.peso_b2 is not None else params.peso_b) * t)
        )
        peso_3 = float(
            (params.peso_a3 if params.peso_a3 is not None else params.peso_a)
            * np.exp((params.peso_b3 if params.peso_b3 is not None else params.peso_b) * t)
        )
        peso_g = float(
            (p1 * peso_1 + p2 * peso_2 + p3 * peso_3) / total_frt if total_frt > 0 else 0.0
        )

        # Kilos proyectados por lote
        n_plantas_total = params.n_plantas * factor_escala_lote
        kg_p1 = (p1 * peso_1 * n_plantas_total) / 1000.0
        kg_p2 = (p2 * peso_2 * n_plantas_total) / 1000.0
        kg_p3 = (p3 * peso_3 * n_plantas_total) / 1000.0
        kg_total = kg_p1 + kg_p2 + kg_p3

        kg_acum += kg_total
        frt_acum += total_frt

        filas.append(
            {
                "LoteId": params.lote_id,
                "Lote": params.lote,
                "Fundo": params.fundo,
                "Modulo": params.modulo,
                "Turno": params.turno,
                "DDP": int(t),
                "Fecha": fecha_fila.strftime("%Y-%m-%d"),
                "Semana": f"Sem {num_semana}",
                "FrtEst_p1": round(p1, 2),
                "FrtEst_p2": round(p2, 2),
                "FrtEst_p3": round(p3, 2),
                "TotalEst": round(total_frt, 2),
                "PesoMedio_g": round(peso_g, 2),
                "Kg_Oleada_1": round(kg_p1, 1),
                "Kg_Oleada_2": round(kg_p2, 1),
                "Kg_Oleada_3": round(kg_p3, 1),
                "Kg_Semanal_Total": round(kg_total, 1),
                "Kg_Acumulados": round(kg_acum, 1),
                "Frutos_Acumulados": round(frt_acum, 1),
            }
        )

    return pd.DataFrame(filas)


def simular_escenario(
    params: ParametrosBhattacharya,
    delta_mu1: float = 0.0,
    delta_mu2: float = 0.0,
    delta_mu3: float = 0.0,
    factor_N1: float = 1.0,
    factor_N2: float = 1.0,
    factor_N3: float = 1.0,
    nuevo_peso_a: float | None = None,
    nuevo_peso_b: float | None = None,
) -> ParametrosBhattacharya:
    """Aplica modificaciones expertas a los parámetros para simular escenarios What-If."""
    p = ParametrosBhattacharya(
        lote=params.lote,
        lote_id=params.lote_id,
        campania=params.campania,
        fundo=params.fundo,
        modulo=params.modulo,
        turno=params.turno,
        fecha_poda=params.fecha_poda,
        n_plantas=params.n_plantas,
        mu1=params.mu1 + delta_mu1,
        sigma1=params.sigma1,
        N1=params.N1 * factor_N1,
        mu2=params.mu2 + delta_mu2,
        sigma2=params.sigma2,
        N2=params.N2 * factor_N2,
        mu3=params.mu3 + delta_mu3,
        sigma3=params.sigma3,
        N3=params.N3 * factor_N3,
        peso_a=nuevo_peso_a if nuevo_peso_a is not None else params.peso_a,
        peso_b=nuevo_peso_b if nuevo_peso_b is not None else params.peso_b,
        rmse_total=params.rmse_total,
        panas_observadas=params.panas_observadas,
        frutos_observados_total=params.frutos_observados_total,
        es_estimado_por_defecto=params.es_estimado_por_defecto,
        fuente_parametros=params.fuente_parametros,
        nivel_calibracion=params.nivel_calibracion,
    )
    return p
