"""Estudio estadístico del clima contra el kg/ha.

Cinco preguntas, en el orden en que hay que hacérselas:

  1. ¿Cuánto correlaciona, medido al grano al que el dato existe (la semana)?
  2. ¿Sobrevive al controlar el calendario? Con un control **no lineal**, porque la
     cosecha es una joroba y una recta no la describe.
  3. ¿Hay rezago? El fruto tarda semanas en formarse, así que el clima de hace un mes
     podría explicar mejor que el de hoy — si es física y no alineación de tendencias.
  4. ¿Una serie inventada sin significado correlaciona igual de fuerte? (placebo)
  5. ¿La relación tiene la misma forma en todos los módulos, o depende de cuándo cosecha
     cada uno?

Sin Streamlit: la capa de caché vive en `servicios/`.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats

from config import CLIMA, OBJETIVO, etiqueta

GRADO_TENDENCIA = 5  # polinomio que absorbe la forma de la campaña
LAGS = range(9)


def agregar_por_semana(tabla: pd.DataFrame) -> pd.DataFrame:
    """Una fila por semana: el kg/ha del fundo (ponderado por área) y su clima.

    Es el grano al que el clima existe. Cualquier estadística climática calculada sobre
    las celdas módulo×semana repite el mismo valor una y otra vez y finge tener más
    información de la que hay.
    """
    g = tabla.groupby("nsem")
    valores = {
        "kg_ha": g.apply(lambda x: x.Kg.sum() / x.Area.sum(), include_groups=False),
        "modulos": g.celda.nunique(),
        "riego_lt_planta": g.riego_lt_planta.mean(),
        "Frutos": g.Frutos.mean(),
        "Peso": g.Peso.mean(),
        **{c: g[c].first() for c in CLIMA},
    }
    # La poda es de módulo/lote, así que su resumen semanal se marca como promedio
    # descriptivo. No reemplaza el panel de grano fino ni crea una nueva medición climática.
    # Floración (EvFlores) es lo mismo: promedio descriptivo entre módulos, no una medición
    # climática nueva — pero permite reusar `rezagos()` para preguntar si el clima de antes
    # explica la floración, la pieza que falta en la cadena clima → floración → Frutos.
    for columna in (
        "dias_desde_poda", "poda_dispersion_dias", "gdd_acum_poda_obs",
        "edad_planta_anos", "flores_promedio",
    ):
        if columna in tabla.columns:
            valores[columna] = g[columna].mean()
    sem = pd.DataFrame(valores).reset_index()
    return sem.sort_values("nsem").reset_index(drop=True)


def _sin_tendencia(v: np.ndarray, x: np.ndarray, grado: int) -> np.ndarray:
    """Residuos tras quitar una tendencia polinómica en el número de semana."""
    return v - np.polyval(np.polyfit(x, v, grado), x)


@dataclass(frozen=True)
class TamanoEfectivo:
    """Cuánta información hay realmente, contra cuánta aparenta haber."""

    n_celdas: int
    n_semanas: int

    @property
    def factor_inflacion(self) -> float:
        """Cuántas veces más estrecho sería un intervalo calculado sobre las celdas."""
        return float(np.sqrt(self.n_celdas / self.n_semanas))


def tamano_efectivo(tabla: pd.DataFrame) -> TamanoEfectivo:
    return TamanoEfectivo(len(tabla), int(tabla.nsem.nunique()))


def _ic_fisher(r: float, n: int) -> tuple[float, float]:
    """Intervalo de confianza al 95 % de una correlación, vía la z de Fisher."""
    if n <= 3:
        return (np.nan, np.nan)
    z, se = np.arctanh(r), 1 / np.sqrt(n - 3)
    return float(np.tanh(z - 1.96 * se)), float(np.tanh(z + 1.96 * se))


def correlaciones_semanales(sem: pd.DataFrame) -> pd.DataFrame:
    """Pearson y Spearman al grano semanal, con su p y su intervalo honesto."""
    filas = []
    n = len(sem)
    for c in CLIMA:
        pr, pp = stats.pearsonr(sem[c], sem.kg_ha)
        sr, sp = stats.spearmanr(sem[c], sem.kg_ha)
        lo, hi = _ic_fisher(pr, n)
        filas.append(
            {
                "Variable": etiqueta(c),
                "clave": c,
                "r (Pearson)": pr,
                "p": pp,
                "IC 95% inferior": lo,
                "IC 95% superior": hi,
                "Spearman": sr,
                "p Spearman": sp,
                "Varianza explicada": pr**2,
                "Significativa": pp < 0.05,
            }
        )
    return pd.DataFrame(filas).sort_values("Varianza explicada", ascending=False)


def correlacion_parcial(sem: pd.DataFrame) -> pd.DataFrame:
    """La correlación que queda tras descontar el calendario, lineal y no linealmente.

    La columna que importa es la del control polinómico. El lineal se muestra al lado
    justamente para que se vea que un control mal elegido deja pasar la confusión.
    """
    x = sem.nsem.to_numpy(dtype=float)
    y = sem.kg_ha.to_numpy(dtype=float)
    res_y_lin = _sin_tendencia(y, x, 1)
    res_y_pol = _sin_tendencia(y, x, GRADO_TENDENCIA)

    filas = []
    for c in CLIMA:
        v = sem[c].to_numpy(dtype=float)
        r_simple = float(np.corrcoef(v, y)[0, 1])
        r_lin, p_lin = stats.pearsonr(_sin_tendencia(v, x, 1), res_y_lin)
        r_pol, p_pol = stats.pearsonr(_sin_tendencia(v, x, GRADO_TENDENCIA), res_y_pol)
        filas.append(
            {
                "Variable": etiqueta(c),
                "clave": c,
                "r sin controlar": r_simple,
                "r control lineal": r_lin,
                "p lineal": p_lin,
                "r control no lineal": r_pol,
                "p no lineal": p_pol,
                "Sobrevive": bool(p_pol < 0.05),
                "Queda": abs(r_pol) / max(abs(r_simple), 1e-9),
            }
        )
    return pd.DataFrame(filas).sort_values("r sin controlar", key=abs, ascending=False)


def correlacion_control_poda(sem: pd.DataFrame) -> pd.DataFrame:
    """Asociación climática después de controlar el reloj de poda disponible.

    Es un control descriptivo de tiempo biológico proxy. La fecha de poda se resume por
    módulo y luego por semana; por eso se reporta aparte del control por número de semana
    y nunca como efecto causal.
    """
    if "dias_desde_poda" not in sem.columns:
        return pd.DataFrame()
    valido = sem.dropna(subset=["dias_desde_poda", "kg_ha"]).copy()
    if len(valido) < 10 or valido.dias_desde_poda.nunique() < 4:
        return pd.DataFrame()
    x = valido.dias_desde_poda.to_numpy(dtype=float)
    y = valido.kg_ha.to_numpy(dtype=float)
    grado = min(GRADO_TENDENCIA, int(valido.dias_desde_poda.nunique()) - 1)
    filas = []
    for c in CLIMA:
        m = valido[c].notna().to_numpy()
        if m.sum() < 10:
            continue
        v = valido.loc[m, c].to_numpy(dtype=float)
        xx = x[m]
        yy = y[m]
        rv = _sin_tendencia(v, xx, min(grado, len(xx) - 1))
        ry = _sin_tendencia(yy, xx, min(grado, len(xx) - 1))
        r, p = stats.pearsonr(rv, ry)
        filas.append({
            "Variable": etiqueta(c),
            "clave": c,
            "r control poda": float(r),
            "p control poda": float(p),
            "Sobrevive poda": bool(p < 0.05),
            "Grado control": min(grado, len(xx) - 1),
            "n semanas": int(m.sum()),
        })
    return pd.DataFrame(filas).sort_values("r control poda", key=abs, ascending=False)


REZAGOS_PREDICTORES: tuple[str, ...] = (
    "DPV", "riego_lt_planta", "Rad", "ETo", "TempMax", "TempMin", "gdd_semana",
)


def rezagos(sem: pd.DataFrame, objetivo: str = "kg_ha",
           variables: tuple[str, ...] = CLIMA) -> pd.DataFrame:
    """Correlación a k semanas de rezago, antes y después de quitar la tendencia.

    `objetivo` permite repetir la misma prueba contra Frutos o Peso, no solo kg/ha: el
    fruto y su tamaño pueden responder a ventanas distintas de una misma variable, y kg/ha
    solo no lo distingue.

    Sin quitar la tendencia, desplazar una serie estacional contra otra alinea mejor las
    jorobas y sube la correlación aunque no haya nada físico detrás. La fila «detrended»
    es la que decide.
    """
    s = sem.set_index("nsem").sort_index()
    filas = []
    for c in variables:
        for k in LAGS:
            desplazada = s[c].shift(k)
            m = desplazada.notna() & s[objetivo].notna()
            if m.sum() < 13:
                continue
            xi = np.asarray(s.index[m], dtype=float)
            bruto = float(desplazada[m].corr(s.loc[m, objetivo]))
            rx = _sin_tendencia(desplazada[m].to_numpy(float), xi, GRADO_TENDENCIA)
            ry = _sin_tendencia(s.loc[m, objetivo].to_numpy(float), xi, GRADO_TENDENCIA)
            filas.append(
                {
                    "Variable": etiqueta(c),
                    "clave": c,
                    "Rezago": k,
                    "r bruto": bruto,
                    "r sin tendencia": float(np.corrcoef(rx, ry)[0, 1]),
                }
            )
    return pd.DataFrame(filas)


OBJETIVOS_REZAGO: tuple[tuple[str, str], ...] = (
    ("kg_ha", "kg/ha"), ("Frutos", "Frutos"), ("Peso", "Peso"),
    ("flores_promedio", "Floración"),
)


def rezagos_todos(sem: pd.DataFrame, tabla: pd.DataFrame | None = None) -> pd.DataFrame:
    """La prueba de desfases (`rezagos`) para kg/ha, Frutos, Peso y Floración, en una tabla.

    Los objetivos comparten `REZAGOS_PREDICTORES` para que sean comparables entre sí: kg/ha
    no se compara contra un conjunto de variables distinto del que se usa para Frutos o
    Peso. GDD acumulado (`gdd_acum`) y amplitud térmica (`VarDia`) quedan fuera porque
    `rezagos` los cubre ya en la Prueba 3, y GDD acumulado en particular es un reloj de
    calendario: desplazarlo en el tiempo no prueba nada distinto de desplazar la semana.

    «Floración» completa la cadena clima → floración → Frutos, con `rezagos_floracion_
    clima` (efecto fijo de módulo) en vez de la serie semanal agregada que usan kg/ha,
    Frutos y Peso — necesita `tabla` (grano de celda) para eso; sin ella cae a la versión
    agregada, más simple pero con el sesgo entre módulos ya documentado.
    """
    piezas = []
    for objetivo, etiqueta_obj in OBJETIVOS_REZAGO:
        if objetivo == "flores_promedio" and tabla is not None:
            r = rezagos_floracion_clima(tabla)
        else:
            if objetivo not in sem.columns or sem[objetivo].notna().sum() < 13:
                continue
            r = rezagos(sem, objetivo=objetivo, variables=REZAGOS_PREDICTORES)
        if not r.empty:
            r.insert(0, "Objetivo", etiqueta_obj)
            piezas.append(r)
    return pd.concat(piezas, ignore_index=True) if piezas else pd.DataFrame()


def rezagos_frutos_peso(sem: pd.DataFrame) -> pd.DataFrame:
    """Solo Frutos y Peso, para la sección «Frutos y peso» de Impacto agronómico."""
    todos = rezagos_todos(sem)
    return todos[todos.Objetivo.isin(["Frutos", "Peso"])].reset_index(drop=True)


def mejor_rezago_por_variable(
    sem: pd.DataFrame, tabla: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Para kg/ha, Frutos, Peso y Floración: qué rezago (semanas) maximiza |r sin tendencia|.

    Es la respuesta directa a «qué promedio móvil y qué desfase explican mejor la
    variación»: el máximo se busca sobre la serie YA descontada de calendario, nunca sobre
    la bruta, por la misma razón que la Prueba 3 usa la curva azul y no la roja. `tabla`
    (grano de celda) es la que permite corregir Floración por efecto fijo de módulo — ver
    `rezagos_todos`.
    """
    todo = rezagos_todos(sem, tabla)
    if todo.empty:
        return pd.DataFrame()
    filas = []
    for (objetivo, clave), g in todo.groupby(["Objetivo", "clave"]):
        i = g["r sin tendencia"].abs().idxmax()
        mejor = g.loc[i]
        filas.append({
            "Objetivo": objetivo,
            "Variable": mejor.Variable,
            "clave": clave,
            "Mejor rezago (semanas)": int(mejor.Rezago),
            "r sin tendencia en el mejor rezago": float(mejor["r sin tendencia"]),
            "r sin tendencia en rezago 0": float(
                g.loc[g.Rezago == 0, "r sin tendencia"].iloc[0]
            ) if (g.Rezago == 0).any() else np.nan,
        })
    return pd.DataFrame(filas).sort_values(["Objetivo"]).reset_index(drop=True)


FLORACION_REZAGOS = range(9)


def _rezago_efecto_fijo(
    tabla: pd.DataFrame, predictor: str, objetivo: str, ventanas=FLORACION_REZAGOS,
) -> pd.DataFrame:
    """¿El predictor de hace k semanas explica mejor el objetivo que el de esta semana?

    Motor común para floración→Frutos y clima→floración: ambos casos comparan DOS
    mediciones al grano de la celda (módulo × semana), no series semanales del fundo —
    así que el control correcto no es solo restar la forma de la campaña, es restar
    TAMBIÉN el promedio de cada módulo (efecto fijo), para no confundir «este módulo
    produce más que otros en general» con una relación temporal real. `min_periods`
    implícito: cada módulo se reindexa a semanas de calendario consecutivas antes de
    desplazar, igual que `_rolling_por_modulo` en `datos.py`, para no desplazar sobre
    huecos de cosecha.
    """
    piezas = []
    for celda, g in tabla.groupby("celda"):
        g = g.set_index("nsem").sort_index()
        g = g.reindex(range(int(g.index.min()), int(g.index.max()) + 1))
        piezas.append(pd.DataFrame({
            "celda": celda,
            "nsem": g.index.to_numpy(dtype=float),
            "pred": g[predictor].to_numpy(dtype=float),
            "obj": g[objetivo].to_numpy(dtype=float),
        }))
    largo = pd.concat(piezas, ignore_index=True)

    filas = []
    for k in ventanas:
        d = largo.copy()
        d["pred_k"] = d.groupby("celda")["pred"].shift(k)
        d = d.dropna(subset=["pred_k", "obj"])
        if len(d) < 15 or d.celda.nunique() < 3:
            continue
        bruto, p_bruto = stats.pearsonr(d.pred_k, d.obj)

        # Efecto fijo de módulo: se resta la media de cada módulo antes de correlacionar.
        pred_m = d.pred_k - d.groupby("celda")["pred_k"].transform("mean")
        obj_m = d.obj - d.groupby("celda")["obj"].transform("mean")
        r_modulo, p_modulo = stats.pearsonr(pred_m, obj_m)

        grado = min(GRADO_TENDENCIA, d.nsem.nunique() - 1, len(d) - 2)
        pred_mc = _sin_tendencia(pred_m.to_numpy(), d.nsem.to_numpy(), max(grado, 1))
        obj_mc = _sin_tendencia(obj_m.to_numpy(), d.nsem.to_numpy(), max(grado, 1))
        r_completo, p_completo = stats.pearsonr(pred_mc, obj_mc)

        filas.append({
            "Rezago": k,
            "r bruto": float(bruto),
            "p bruto": float(p_bruto),
            "r control módulo": float(r_modulo),
            "p control módulo": float(p_modulo),
            "r control módulo y calendario": float(r_completo),
            "p control módulo y calendario": float(p_completo),
            "n": int(len(d)),
            "módulos": int(d.celda.nunique()),
        })
    return pd.DataFrame(filas)


def rezago_floracion(tabla: pd.DataFrame, objetivo: str = "Frutos") -> pd.DataFrame:
    """¿La floración de hace k semanas explica mejor el objetivo que la de esta semana?"""
    return _rezago_efecto_fijo(tabla, "flores_promedio", objetivo)


def rezagos_floracion_clima(tabla: pd.DataFrame) -> pd.DataFrame:
    """¿El clima/riego de hace k semanas explica mejor la floración que el de esta semana?

    La otra mitad de la cadena clima → floración → Frutos, con el MISMO control de
    efecto fijo de módulo que `rezago_floracion` usa para la segunda mitad — no la serie
    semanal agregada de `rezagos()`. Reemplaza esa versión agregada porque, verificado con
    los datos reales, cada módulo florece en su propia fase dentro de la misma semana
    calendario (picos entre la semana 7 y la 52 según el módulo) y promediarlos infla la
    correlación con una diferencia real ENTRE módulos, no una respuesta temporal al clima.
    Devuelve el mismo esquema de columnas que `rezagos()` para que `rezagos_todos` y
    `mejor_rezago_por_variable` no necesiten distinguir el origen.
    """
    piezas = []
    for var in REZAGOS_PREDICTORES:
        r = _rezago_efecto_fijo(tabla, var, "flores_promedio")
        if r.empty:
            continue
        r = r.rename(columns={"r control módulo y calendario": "r sin tendencia"})
        r["Variable"] = etiqueta(var)
        r["clave"] = var
        piezas.append(r[["Variable", "clave", "Rezago", "r bruto", "r sin tendencia"]])
    return pd.concat(piezas, ignore_index=True) if piezas else pd.DataFrame()


def placebo(sem: pd.DataFrame, semilla: int = 0) -> pd.DataFrame:
    """Correlación del kg/ha con series que no significan nada.

    Es la demostración más directa de por qué la correlación estacional no prueba
    relación física: si un seno anual correlaciona más fuerte que la temperatura, lo que
    se está midiendo es la forma de la curva, no la temperatura.
    """
    x = sem.nsem.to_numpy(dtype=float)
    y = sem.kg_ha.to_numpy(dtype=float)
    rng = np.random.default_rng(semilla)
    series = {
        "Onda anual (seno)": np.sin(2 * np.pi * x / 52),
        "Onda anual (coseno)": np.cos(2 * np.pi * x / 52),
        "Rampa: el número de semana": x,
        "Ruido aleatorio puro": rng.normal(size=len(x)),
    }
    filas = [
        {"Serie": nombre, "r con kg/ha": float(np.corrcoef(v, y)[0, 1]), "Real": False}
        for nombre, v in series.items()
    ]
    for c in CLIMA:
        filas.append({"Serie": etiqueta(c),
                      "r con kg/ha": float(np.corrcoef(sem[c], y)[0, 1]), "Real": True})
    return pd.DataFrame(filas).sort_values("r con kg/ha", key=abs, ascending=False)


def forma_de_la_relacion(sem: pd.DataFrame, variable: str, n_grupos: int = 5) -> pd.DataFrame:
    """Promedio del kg/ha por quintil de la variable: la forma, sin suponer que es recta."""
    q = pd.qcut(sem[variable], n_grupos, duplicates="drop")
    tab = sem.groupby(q, observed=True).agg(
        semanas=("kg_ha", "size"), kg_ha=("kg_ha", "mean"), valor=(variable, "mean")
    ).reset_index(drop=True)
    tab["Tramo"] = [f"{i + 1}º quinto" for i in range(len(tab))]
    return tab


def ganancia_cuadratica(sem: pd.DataFrame) -> pd.DataFrame:
    """¿Añadir un término al cuadrado mejora el ajuste más de lo esperable por azar?"""
    y = sem.kg_ha.to_numpy(dtype=float)
    n = len(y)
    filas = []
    for c in CLIMA:
        x = sem[c].to_numpy(dtype=float)
        r2_1 = float(np.corrcoef(np.polyval(np.polyfit(x, y, 1), x), y)[0, 1] ** 2)
        r2_2 = float(np.corrcoef(np.polyval(np.polyfit(x, y, 2), x), y)[0, 1] ** 2)
        f = ((r2_2 - r2_1) / 1) / ((1 - r2_2) / (n - 3)) if r2_2 < 1 else np.inf
        filas.append(
            {
                "Variable": etiqueta(c),
                "clave": c,
                "R² recta": r2_1,
                "R² curva": r2_2,
                "Gana": r2_2 - r2_1,
                "p": float(1 - stats.f.cdf(f, 1, n - 3)),
            }
        )
    return pd.DataFrame(filas).sort_values("Gana", ascending=False)


def por_modulo(tabla: pd.DataFrame, minimo: int = 10) -> pd.DataFrame:
    """Correlación dentro de cada módulo, con la ventana de cosecha que lo explica."""
    filas = []
    for celda, g in tabla.groupby("celda"):
        if len(g) < minimo:
            continue
        fila = {
            "Módulo": celda,
            "Semanas": len(g),
            "Inicio": int(g.nsem.min()),
            "Pico": int(g.loc[g[OBJETIVO].idxmax(), "nsem"]),
            "kg/ha medio": float(g[OBJETIVO].mean()),
        }
        fila.update({etiqueta(c): float(g[c].corr(g[OBJETIVO])) for c in CLIMA})
        fila["Riego"] = float(g.riego_lt_planta.corr(g[OBJETIVO]))
        filas.append(fila)
    return pd.DataFrame(filas).sort_values(etiqueta("TempMin"))


def signo_depende_de_la_ventana(porm: pd.DataFrame) -> pd.DataFrame:
    """¿La correlación de un módulo la decide cuándo cosecha, y no su fisiología?

    Si el signo cambia según la semana en que arranca la cosecha, lo que la correlación
    mide es el solapamiento entre dos calendarios.
    """
    filas = []
    for c in CLIMA:
        col = etiqueta(c)
        if col not in porm.columns or len(porm) < 4:
            continue
        r, p = stats.pearsonr(porm.Inicio, porm[col])
        filas.append(
            {
                "Variable": col,
                "clave": c,
                "r (inicio de cosecha ↔ correlación del módulo)": r,
                "p": p,
                "Significativa": bool(p < 0.05),
            }
        )
    return pd.DataFrame(filas).sort_values(
        "r (inicio de cosecha ↔ correlación del módulo)", key=abs, ascending=False
    )


@dataclass(frozen=True)
class Veredicto:
    """El resumen ejecutable del estudio: qué se puede afirmar y qué no."""

    variable_mas_asociada: str
    r_mas_alta: float
    sobreviven_al_control: list[str]
    placebo_mas_fuerte: str
    r_placebo: float
    n_semanas: int

    @property
    def hay_relacion_robusta(self) -> bool:
        return bool(self.sobreviven_al_control)


FRUTOS_PESO_PREDICTORES: tuple[str, ...] = (
    "DPV", "riego_lt_planta", "Rad", "ETo", "TempMax", "TempMin",
)


def descomponer_frutos_peso(sem: pd.DataFrame) -> pd.DataFrame:
    """¿El clima/riego pesa distinto sobre el número de frutos que sobre su tamaño?

    kg/ha ≈ Frutos × Peso × densidad, así que correlacionar Frutos y Peso por separado
    contra cada variable descompone el rendimiento en sus dos procesos biológicos: el
    cuajado (cuántos frutos) y el llenado (cuánto pesa cada uno). Misma prueba de fondo
    que el resto del estudio — correlación y control del calendario — aplicada a dos
    objetivos en vez de a kg/ha.
    """
    x = sem.nsem.to_numpy(dtype=float)
    filas = []
    for objetivo in ("Frutos", "Peso"):
        y = sem[objetivo].to_numpy(dtype=float)
        for c in FRUTOS_PESO_PREDICTORES:
            v = sem[c].to_numpy(dtype=float)
            m = ~np.isnan(y) & ~np.isnan(v)
            if m.sum() < 10:
                continue
            # Se detrenda DENTRO de la máscara de esta pareja (y, v): así el polinomio
            # se ajusta sobre exactamente los mismos puntos que después se correlacionan.
            r_simple, p_simple = stats.pearsonr(v[m], y[m])
            ry = _sin_tendencia(y[m], x[m], GRADO_TENDENCIA)
            rv = _sin_tendencia(v[m], x[m], GRADO_TENDENCIA)
            r_det, p_det = stats.pearsonr(rv, ry)
            r_poda, p_poda = np.nan, np.nan
            if "dias_desde_poda" in sem.columns:
                xp = sem.loc[m, "dias_desde_poda"].to_numpy(dtype=float)
                mp = np.isfinite(xp)
                if mp.sum() >= 10 and np.unique(xp[mp]).size >= 4:
                    grado_poda = min(GRADO_TENDENCIA, int(np.unique(xp[mp]).size) - 1)
                    ry_poda = _sin_tendencia(y[m][mp], xp[mp], grado_poda)
                    rv_poda = _sin_tendencia(v[m][mp], xp[mp], grado_poda)
                    r_poda, p_poda = stats.pearsonr(rv_poda, ry_poda)
            filas.append(
                {
                    "Objetivo": objetivo,
                    "Variable": etiqueta(c),
                    "clave": c,
                    "r sin controlar": r_simple,
                    "p sin controlar": p_simple,
                    "r control no lineal": r_det,
                    "p control no lineal": p_det,
                    "Sobrevive": bool(p_det < 0.05),
                    "r control poda": r_poda,
                    "p control poda": p_poda,
                    "Sobrevive poda": bool(pd.notna(p_poda) and p_poda < 0.05),
                }
            )
    return pd.DataFrame(filas)


def trayectorias_frutos_peso(tabla: pd.DataFrame) -> pd.DataFrame:
    """Resumen descriptivo de la curva biológica dentro de cada módulo.

    El peak se expresa tanto en semana calendario como en posición relativa dentro de la
    ventana observada. La pendiente del peso resume el cambio neto; los cambios de sentido
    avisan cuando esa recta oculta una curva ondulada.
    """
    filas = []
    for celda, grupo in tabla.sort_values("nsem").groupby("celda"):
        g_frutos = grupo.dropna(subset=["Frutos"]).copy()
        g_peso = grupo.dropna(subset=["Peso"]).copy()
        if len(g_frutos) < 3:
            continue
        inicio, fin = int(g_frutos.nsem.min()), int(g_frutos.nsem.max())
        i_peak = g_frutos.Frutos.idxmax()
        semana_peak = int(g_frutos.loc[i_peak, "nsem"])
        posicion = (semana_peak - inicio) / (fin - inicio) if fin > inicio else 0.5
        tramo = "Inicio" if posicion < 1 / 3 else "Medio" if posicion < 2 / 3 else "Final"
        pre_peak = grupo[grupo.nsem.between(max(inicio, semana_peak - 3), semana_peak)]
        dap_peak = (
            float(g_frutos.loc[i_peak, "dias_desde_poda"])
            if "dias_desde_poda" in g_frutos.columns and pd.notna(g_frutos.loc[i_peak, "dias_desde_poda"])
            else np.nan
        )
        dispersion_poda = (
            float(g_frutos.loc[i_peak, "poda_dispersion_dias"])
            if "poda_dispersion_dias" in g_frutos.columns
            and pd.notna(g_frutos.loc[i_peak, "poda_dispersion_dias"])
            else np.nan
        )

        x_frutos = g_frutos.nsem.to_numpy(dtype=float)
        huecos = int(np.sum(np.diff(x_frutos) > 1))
        if len(g_peso) >= 2 and g_peso.nsem.nunique() >= 2:
            x_peso = g_peso.nsem.to_numpy(dtype=float)
            peso = g_peso.Peso.to_numpy(dtype=float)
            pendiente = float(np.polyfit(x_peso, peso, 1)[0])
            peso_inicial = float(peso[0])
            peso_final = float(peso[-1])
            peso_peak = g_peso.loc[g_peso.nsem.eq(semana_peak), "Peso"]
            peso_peak = float(peso_peak.iloc[0]) if not peso_peak.empty else np.nan
        else:
            peso = np.array([], dtype=float)
            pendiente = np.nan
            peso_inicial = np.nan
            peso_final = np.nan
            peso_peak = np.nan
        diferencias = np.diff(peso)
        signos = np.sign(diferencias[np.abs(diferencias) > 1e-9])
        cambios = int(np.sum(signos[1:] != signos[:-1])) if len(signos) > 1 else 0
        filas.append({
            "Módulo": celda,
            "Semana inicial": inicio,
            "Semana final": fin,
            "Semana peak frutos": semana_peak,
            "Días desde poda peak": dap_peak,
            "Poda dispersion dias": dispersion_poda,
            "Peak frutos/planta": float(g_frutos.loc[i_peak, "Frutos"]),
            "Posición del peak": tramo,
            "Frutos acumulados observados/planta": float(g_frutos.Frutos.sum()),
            "Huecos de calendario": huecos,
            "Peso inicial (g)": peso_inicial,
            "Peso final (g)": peso_final,
            "Cambio neto peso (g)": (
                float(peso_final - peso_inicial)
                if pd.notna(peso_inicial) and pd.notna(peso_final) else np.nan
            ),
            "Pendiente peso (g/sem)": pendiente,
            "Peso peak (g)": peso_peak,
            "TempMin 4sem pre-peak": float(pre_peak.TempMin.mean()),
            "DPV 4sem pre-peak": float(pre_peak.DPV.mean()),
            "Rad 4sem pre-peak": float(pre_peak.Rad.mean()),
            "ETo 4sem pre-peak": float(pre_peak.ETo.mean()),
            "Riego 4sem pre-peak": float(pre_peak.riego_lt_planta.mean()),
            "GDD 4sem pre-peak": float(pre_peak.gdd_semana.mean()),
            "Semanas pre-peak observadas": int(len(pre_peak)),
            "Sentido de la recta": (
                "des+" if pd.notna(pendiente) and pendiente > 0
                else "des-" if pd.notna(pendiente) and pendiente < 0
                else "sin datos"
            ),
            "Cambios de sentido": cambios,
            "Semanas observadas": len(g_frutos),
            "Semanas peso observadas": len(g_peso),
        })
    return pd.DataFrame(filas).sort_values(["Semana peak frutos", "Módulo"])


def resumen_picos_frutos_peso(tabla: pd.DataFrame) -> pd.DataFrame:
    """Compara el momento del peak con el clima observado alrededor del peak."""
    trayectorias = trayectorias_frutos_peso(tabla)
    if trayectorias.empty:
        return pd.DataFrame()
    agrupado = (
        trayectorias.groupby("Posición del peak", as_index=False)
        .agg(
            Módulos=("Módulo", "size"),
            **{
                "DAP peak medio": ("Días desde poda peak", "mean"),
                "Poda dispersion dias media": ("Poda dispersion dias", "mean"),
                "Semana peak media": ("Semana peak frutos", "mean"),
                "Frutos peak medio": ("Peak frutos/planta", "mean"),
                "Peso peak medio (g)": ("Peso peak (g)", "mean"),
                "TempMin pre-peak": ("TempMin 4sem pre-peak", "mean"),
                "DPV pre-peak": ("DPV 4sem pre-peak", "mean"),
                "Rad pre-peak": ("Rad 4sem pre-peak", "mean"),
                "ETo pre-peak": ("ETo 4sem pre-peak", "mean"),
                "Riego pre-peak": ("Riego 4sem pre-peak", "mean"),
                "GDD pre-peak": ("GDD 4sem pre-peak", "mean"),
            }
        )
    )
    orden = pd.CategoricalDtype(["Inicio", "Medio", "Final"], ordered=True)
    agrupado["Posición del peak"] = agrupado["Posición del peak"].astype(orden)
    return agrupado.sort_values("Posición del peak").reset_index(drop=True)


def veredicto(sem: pd.DataFrame) -> Veredicto:
    """Junta las piezas del estudio en una conclusión que la interfaz pueda mostrar."""
    corr = correlaciones_semanales(sem)
    parcial = correlacion_parcial(sem)
    pl = placebo(sem)
    falsas = pl[~pl.Real]
    top_falsa = falsas.loc[falsas["r con kg/ha"].abs().idxmax()]
    mejor = corr.iloc[0]
    return Veredicto(
        variable_mas_asociada=str(mejor.Variable),
        r_mas_alta=float(mejor["r (Pearson)"]),
        sobreviven_al_control=[str(v) for v in parcial.loc[parcial.Sobrevive, "Variable"]],
        placebo_mas_fuerte=str(top_falsa.Serie),
        r_placebo=float(top_falsa["r con kg/ha"]),
        n_semanas=len(sem),
    )
