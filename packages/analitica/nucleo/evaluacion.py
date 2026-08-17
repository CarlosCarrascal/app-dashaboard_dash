"""Evaluación de variables: qué se mide, contra qué, y cómo se separa train de test.

La versión anterior de esto era una función de 90 líneas con un closure y seis llamadas
copiadas a mano, cada una con su lista de columnas y su splitter incrustados. Agregar un
esquema significaba copiar un bloque; comparar dos significaba leerlos en paralelo.

Aquí las tres decisiones que definen una medición están separadas y nombradas:

    Conjunto   — QUÉ variables entran al modelo
    Particion  — CÓMO se separa entrenamiento de validación (y qué pregunta responde)
    Referencia — un predictor sin modelo, para tener piso contra el cual comparar

Una medición es el cruce de un `Conjunto` con una `Particion`. La tabla de validación es
entonces un PLAN: una lista de cruces con su etiqueta y su lectura. Agregar un esquema es
una línea en `PLAN_VALIDACION`; agregar una forma de partir los datos es una entrada en
`PARTICIONES`, y queda disponible para todos los conjuntos a la vez.

Sin Streamlit: la capa de caché vive en `servicios.py`.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import partial

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import GroupKFold, KFold

from ..config import FEATURES, OBJETIVO, PARAMS, etiqueta

Division = list[tuple[np.ndarray, np.ndarray]]

# ── Las tres piezas ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Conjunto:
    """Un subconjunto nombrado de variables predictoras."""

    clave: str
    nombre: str
    columnas: tuple[str, ...]

    def __len__(self) -> int:
        return len(self.columnas)


@dataclass(frozen=True)
class Particion:
    """Cómo se separa entrenamiento de validación, y qué pregunta responde eso.

    `dividir` recibe el panel entero y devuelve pares (índices de train, índices de test)
    como posiciones, no etiquetas: se consumen con `.iloc`.
    """

    clave: str
    nombre: str
    pregunta: str
    dividir: Callable[[pd.DataFrame], Division]


@dataclass(frozen=True)
class Referencia:
    """Un predictor sin modelo. Da el piso contra el cual cualquier R² debe compararse."""

    clave: str
    nombre: str
    lectura: str
    predecir: Callable[[pd.DataFrame], np.ndarray]


@dataclass(frozen=True)
class Medicion:
    """El resultado de una evaluación, con la trazabilidad de cómo se obtuvo."""

    etiqueta: str
    r2: float
    mae: float
    lectura: str
    n_variables: int


# ── Registro de conjuntos ────────────────────────────────────────────────────

CONJUNTOS: dict[str, Conjunto] = {
    "completo": Conjunto("completo", f"Las {len(FEATURES)} variables", FEATURES),
    "clima": Conjunto("clima", "Solo clima (sin riego)",
                      tuple(c for c in FEATURES if c != "riego_lag")),
    "riego": Conjunto("riego", "Solo riego", ("riego_lag",)),
    "calendario": Conjunto("calendario", "Solo el número de semana", ("nsem",)),
}

# Familias disjuntas con lectura agronómica. El aporte de una familia tampoco es causal:
# mide cuánto pierde este modelo cuando se retira en conjunto toda la señal compartida.
GRUPOS_AGRONOMICOS: dict[str, tuple[str, ...]] = {
    "Temperatura, DPV y desarrollo": ("TempMax", "TempMin", "DPV_lag", "gdd_lag"),
    "Radiación y demanda hídrica": ("Rad_lag", "ETo_lag"),
    "Riego": ("riego_lag",),
}


def conjunto_sin(col: str) -> Conjunto:
    """El conjunto completo menos una variable — para medir su aporte marginal."""
    return Conjunto(
        f"sin_{col}",
        f"Sin {etiqueta(col)}",
        tuple(c for c in FEATURES if c != col),
    )


def conjunto_solo(col: str) -> Conjunto:
    """Una única variable, para medir qué predice por sí sola."""
    return Conjunto(f"solo_{col}", etiqueta(col), (col,))


# ── Registro de particiones ──────────────────────────────────────────────────


def _por_grupo(columna: str, n: int = 5) -> Callable[[pd.DataFrame], Division]:
    """GroupKFold sobre una columna: ningún grupo aparece en train y test a la vez."""

    def dividir(tabla: pd.DataFrame) -> Division:
        return list(GroupKFold(n).split(tabla, tabla[OBJETIVO], tabla[columna]))

    return dividir


def _aleatoria(n: int = 5) -> Callable[[pd.DataFrame], Division]:
    def dividir(tabla: pd.DataFrame) -> Division:
        return list(KFold(n, shuffle=True, random_state=0).split(tabla))

    return dividir


def _por_bloque_de_semanas(cortes: Sequence[int]) -> Callable[[pd.DataFrame], Division]:
    """Bloques de semanas CONTIGUAS.

    Es la partición que importa: al quitar del entrenamiento también las semanas vecinas,
    deja de ser posible interpolar la curva estacional. Lo que sobreviva a esto es señal.
    """

    def dividir(tabla: pd.DataFrame) -> Division:
        bloque = pd.cut(tabla.nsem, bins=list(cortes), labels=False).to_numpy()
        pares: Division = []
        for b in sorted(pd.unique(bloque)):
            pares.append((np.where(bloque != b)[0], np.where(bloque == b)[0]))
        return pares

    return dividir


PARTICIONES: dict[str, Particion] = {
    "aleatoria": Particion(
        "aleatoria",
        "5-fold aleatorio",
        "Reparte las filas al azar. Como el clima es constante dentro de la semana, mete "
        "módulos de la misma semana en train y test: el modelo solo tiene que recordar el "
        "promedio semanal.",
        _aleatoria(),
    ),
    "por_modulo": Particion(
        "por_modulo",
        "Deja-un-módulo-fuera",
        "Cada módulo se predice con un modelo que nunca lo vio. ¿Sirve para un módulo nuevo?",
        _por_grupo("celda"),
    ),
    "por_semana": Particion(
        "por_semana",
        "Deja-una-semana-fuera",
        "Cada semana se predice sin haberla visto — pero sí habiendo visto sus vecinas, "
        "así que todavía puede interpolar.",
        _por_grupo("nsem"),
    ),
    "por_bloque": Particion(
        "por_bloque",
        "Deja-un-bloque-de-10-semanas-fuera",
        "Sin semanas vecinas en el entrenamiento. Es la partición honesta.",
        _por_bloque_de_semanas([0, 10, 20, 30, 40, 53]),
    ),
}

# Partición por omisión para las comparaciones entre variables: no puede ser la aleatoria
# (infla por la fuga semanal) ni la de bloques (tan dura que aplana las diferencias).
PARTICION_COMPARACION = "por_semana"


# ── Registro de referencias ──────────────────────────────────────────────────

REFERENCIAS: tuple[Referencia, ...] = (
    Referencia(
        "media",
        "Baseline · predecir siempre el promedio",
        "El piso. Cualquier modelo tiene que superarlo.",
        lambda t: np.full(len(t), t[OBJETIVO].mean()),
    ),
    Referencia(
        "media_semana",
        "Baseline · promedio de cada semana",
        "Sin usar ninguna variable, solo el calendario.",
        lambda t: t.groupby("nsem")[OBJETIVO].transform("mean").to_numpy(),
    ),
    Referencia(
        "media_modulo",
        "Baseline · promedio de cada módulo",
        "Cuánto se explica sabiendo solo de qué módulo se trata.",
        lambda t: t.groupby("celda")[OBJETIVO].transform("mean").to_numpy(),
    ),
)


# ── El plan de validación ────────────────────────────────────────────────────


@dataclass(frozen=True)
class Paso:
    """Una fila de la tabla de validación: un cruce conjunto × partición, con su lectura."""

    etiqueta: str
    conjunto: str
    particion: str
    lectura: str


PLAN_VALIDACION: tuple[Paso, ...] = (
    Paso("(a) 5-fold aleatorio", "completo", "aleatoria",
         "OPTIMISTA: mete módulos de la misma semana en train y test."),
    Paso("(b) Deja-un-módulo-fuera", "completo", "por_modulo",
         "¿Sirve para un módulo nuevo?"),
    Paso("(c) Deja-una-semana-fuera", "completo", "por_semana",
         "¿Sirve para una semana no vista? Aún interpola entre semanas vecinas."),
    Paso("(d) Deja-un-bloque-de-10-semanas-fuera", "completo", "por_bloque",
         "HONESTA: sin semanas vecinas en el entrenamiento."),
    Paso("(e) Solo el número de semana", "calendario", "por_semana",
         "Referencia: el calendario sin ninguna variable física."),
    Paso("(f) Solo clima (sin riego)", "clima", "por_semana",
         "Compárese contra (e): si el almanaque gana, el clima no aporta física."),
    Paso("(g) Solo riego", "riego", "por_semana",
         "La única variable que distingue un módulo de otro."),
)


# ── Motor ────────────────────────────────────────────────────────────────────


def en_paralelo(tareas: Sequence[Callable[[], object]]) -> list:
    """Ejecuta una lista de evaluaciones independientes. Hoy, en secuencia.

    Se probaron las tres opciones sobre este panel (13 configuraciones, 452 filas):

        secuencial, xgboost con 1 hilo    17,4 s   ← lo que se usa
        secuencial, xgboost con 2 hilos   18,8 s
        7 hilos de Python                 24,4 s   (el GIL y XGBoost se estorban)
        7 procesos (`loky`)               10,2 s   pero **rompe la app**

    La versión con procesos era la más rápida y daba resultados idénticos, pero cada
    proceso hijo reimporta `nucleo`, que arrastra `shap` → `numba` → `llvmlite`, y el JIT
    de LLVM aborta con «access violation» al inicializarse en un intérprete recién nacido
    en Windows. Un 1,7× no paga que el tablero se caiga.

    La firma se conserva porque el reparto en tareas independientes es correcto y deja la
    puerta abierta: el día que `shap` se cargue de forma perezosa, basta cambiar el cuerpo.
    """
    return [tarea() for tarea in tareas]


def predecir_fuera_de_muestra(
    tabla: pd.DataFrame, conjunto: Conjunto, particion: Particion,
    params: dict | None = None, objetivo: str = OBJETIVO,
) -> np.ndarray:
    """Predicción de cada fila por un modelo que no la vio durante el entrenamiento."""
    X = tabla[list(conjunto.columnas)]
    y = tabla[objetivo]
    pred = np.zeros(len(tabla))
    for train, test in particion.dividir(tabla):
        modelo = xgb.XGBRegressor(**(params or PARAMS)).fit(X.iloc[train], y.iloc[train])
        pred[test] = modelo.predict(X.iloc[test])
    return pred


def medir(
    tabla: pd.DataFrame, conjunto: Conjunto, particion: Particion,
    etiqueta_fila: str | None = None, lectura: str | None = None,
    params: dict | None = None, objetivo: str = OBJETIVO,
) -> Medicion:
    """Evalúa un conjunto de variables bajo una partición.

    Descarta antes las filas sin ventana de rezago completa (NaN en alguna columna del
    conjunto): distintos conjuntos usan distintas columnas, así que cada uno descarta
    sus propias filas — no se puede fijar de antemano cuántas.

    `objetivo` permite repetir la misma medición contra Frutos o Peso — ver
    `nucleo/sintesis.py`.
    """
    tabla = tabla.dropna(subset=[*conjunto.columnas, objetivo])
    pred = predecir_fuera_de_muestra(tabla, conjunto, particion, params, objetivo)
    y = tabla[objetivo]
    return Medicion(
        etiqueta=etiqueta_fila or f"{conjunto.nombre} · {particion.nombre}",
        r2=float(r2_score(y, pred)),
        mae=float(mean_absolute_error(y, pred)),
        lectura=lectura or particion.pregunta,
        n_variables=len(conjunto),
    )


def medir_referencia(tabla: pd.DataFrame, ref: Referencia) -> Medicion:
    """Evalúa un predictor sin modelo."""
    y = tabla[OBJETIVO]
    pred = ref.predecir(tabla)
    return Medicion(
        etiqueta=ref.nombre,
        r2=float(r2_score(y, pred)),
        mae=float(mean_absolute_error(y, pred)),
        lectura=ref.lectura,
        n_variables=0,
    )


def _a_dataframe(mediciones: Sequence[Medicion]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Esquema": m.etiqueta,
                "Variables": m.n_variables,
                "R²": m.r2,
                "MAE (kg/ha)": m.mae,
                "Lectura": m.lectura,
            }
            for m in mediciones
        ]
    )


def tabla_validacion(
    tabla: pd.DataFrame,
    plan: Sequence[Paso] = PLAN_VALIDACION,
    referencias: Sequence[Referencia] = REFERENCIAS,
) -> pd.DataFrame:
    """Las referencias y el plan completo, en una sola tabla comparable."""
    mediciones = [medir_referencia(tabla, r) for r in referencias]
    mediciones += en_paralelo([
        partial(medir, tabla, CONJUNTOS[p.conjunto], PARTICIONES[p.particion],
                p.etiqueta, p.lectura)
        for p in plan
    ])
    return _a_dataframe(mediciones)


def aporte_por_variable(
    tabla: pd.DataFrame, particion_clave: str = PARTICION_COMPARACION
) -> pd.DataFrame:
    """R² de cada variable sola contra su aporte marginal al modelo completo.

    Son dos preguntas distintas y suelen dar órdenes opuestos: una variable puede
    correlacionar fuerte con el objetivo y no aportar nada al modelo (porque otra ya lleva
    esa información), y al revés. La columna que sirve para decidir qué medir es el aporte
    marginal, no la correlación.
    """
    particion = PARTICIONES[particion_clave]
    # Todas las ablaciones deben evaluarse sobre exactamente las mismas observaciones.
    # Si cada conjunto descartara sus propios NaN, «completo» y «sin ella» medirían
    # poblaciones distintas y su diferencia no sería un aporte marginal válido.
    base = tabla.dropna(subset=[*FEATURES, OBJETIVO]).copy()
    y = base[OBJETIVO]

    # Las 13 evaluaciones (el completo, seis «sin ella» y seis «sola») son independientes,
    # así que van en paralelo. Es donde estaba el grueso del tiempo de esta sección.
    conjuntos = [CONJUNTOS["completo"]]
    conjuntos += [conjunto_sin(c) for c in FEATURES]
    conjuntos += [conjunto_solo(c) for c in FEATURES]
    medidas = en_paralelo([partial(medir, base, c, particion) for c in conjuntos])

    completo = medidas[0].r2
    n = len(FEATURES)
    filas = []
    for i, col in enumerate(FEATURES):
        r = float(base[col].corr(y))
        sin_ella = medidas[1 + i].r2
        filas.append(
            {
                "Variable": etiqueta(col),
                "r (Pearson)": r,
                "r² descriptivo": r**2,
                "R² sola": medidas[1 + n + i].r2,
                "R² del modelo sin ella": sin_ella,
                "Aporte marginal": completo - sin_ella,
            }
        )
    resultado = pd.DataFrame(filas).sort_values("Aporte marginal", ascending=False)
    resultado.attrs["completo"] = completo
    resultado.attrs["particion"] = particion.nombre
    resultado.attrs["n"] = len(base)
    resultado.attrs["semanas"] = int(base.nsem.nunique())
    return resultado


def aporte_por_grupo(
    tabla: pd.DataFrame, particion_clave: str = PARTICION_COMPARACION
) -> pd.DataFrame:
    """Ablación de familias disjuntas, con una base común de filas.

    Agrupar variables correlacionadas evita fingir que el crédito compartido entre DPV,
    temperatura y GDD puede asignarse de manera única a una sola columna.
    """
    particion = PARTICIONES[particion_clave]
    base = tabla.dropna(subset=[*FEATURES, OBJETIVO]).copy()
    completo = medir(base, CONJUNTOS["completo"], particion).r2
    filas = []
    for nombre, columnas in GRUPOS_AGRONOMICOS.items():
        restantes = tuple(c for c in FEATURES if c not in columnas)
        solo = Conjunto(f"solo_grupo_{len(filas)}", nombre, columnas)
        sin = Conjunto(f"sin_grupo_{len(filas)}", f"Sin {nombre}", restantes)
        r2_solo = medir(base, solo, particion).r2
        r2_sin = medir(base, sin, particion).r2 if restantes else 0.0
        filas.append({
            "Familia": nombre,
            "Variables": ", ".join(etiqueta(c) for c in columnas),
            "R² solo grupo": r2_solo,
            "R² del modelo sin grupo": r2_sin,
            "Aporte marginal del grupo": completo - r2_sin,
        })
    resultado = pd.DataFrame(filas).sort_values(
        "Aporte marginal del grupo", ascending=False
    )
    resultado.attrs["completo"] = completo
    resultado.attrs["particion"] = particion.nombre
    resultado.attrs["n"] = len(base)
    resultado.attrs["semanas"] = int(base.nsem.nunique())
    return resultado


# ── Análisis descriptivo (sin modelo) ────────────────────────────────────────



def descomposicion_varianza(tabla: pd.DataFrame) -> tuple[float, float]:
    """Reparto de la varianza del objetivo: (% entre semanas, % dentro de la semana).

    El primer bloque es el techo de cualquier variable que sea constante dentro de la
    semana — es decir, de todas las climáticas.
    """
    total = float(tabla[OBJETIVO].var())
    entre = float(tabla.groupby("nsem")[OBJETIVO].transform("mean").var())
    pct = 100 * entre / total
    return pct, 100 - pct



def comparar_familias(tabla: pd.DataFrame) -> pd.DataFrame:
    """Mide XGBoost contra alternativas más simples, con las mismas particiones.

    Elegir un modelo complejo sin comprobar que le gana a uno simple es una decisión
    tomada por costumbre. Acá se comprueba: si la regresión lineal empatara, la no
    linealidad no compraría nada y sí costaría opacidad.
    """
    from sklearn.base import clone
    from sklearn.dummy import DummyRegressor
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.linear_model import LinearRegression, RidgeCV
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.tree import DecisionTreeRegressor

    familias = [
        ("Predecir la media", DummyRegressor(strategy="mean"),
         "El piso: no usa ninguna variable."),
        ("Regresión lineal", make_pipeline(StandardScaler(), LinearRegression()),
         "Supone efecto lineal y aditivo de cada variable."),
        ("Ridge (lineal regularizada)",
         make_pipeline(StandardScaler(), RidgeCV(alphas=np.logspace(-3, 3, 25))),
         f"Lineal, con las {len(FEATURES)} variables colineales penalizadas."),
        ("Árbol único (prof. 3)", DecisionTreeRegressor(max_depth=3, random_state=0),
         "No lineal, pero un solo árbol: muy inestable."),
        ("Random Forest",
         RandomForestRegressor(n_estimators=300, max_depth=6, min_samples_leaf=5,
                               random_state=0, n_jobs=2),
         "Muchos árboles independientes, promediados."),
        ("XGBoost (el del tablero)", xgb.XGBRegressor(**PARAMS),
         "Árboles en secuencia, cada uno corrigiendo el error del anterior."),
    ]

    # Descarta filas sin ventana de rezago completa: LinearRegression/Ridge/RandomForest
    # no aceptan NaN, y comparar contra XGBoost solo vale si todos ven los mismos datos.
    tabla = tabla.dropna(subset=[*FEATURES, OBJETIVO])
    X, y = tabla[list(FEATURES)], tabla[OBJETIVO]

    def evaluar(estimador, clave):
        pred = np.zeros(len(tabla))
        for tr, te in PARTICIONES[clave].dividir(tabla):
            pred[te] = clone(estimador).fit(X.iloc[tr], y.iloc[tr]).predict(X.iloc[te])
        return float(r2_score(y, pred)), float(mean_absolute_error(y, pred))

    # Doce evaluaciones independientes (seis familias x dos particiones), en paralelo.
    tareas = [partial(evaluar, est, clave)
              for _, est, _ in familias
              for clave in ("por_semana", "por_bloque")]
    res = en_paralelo(tareas)

    return pd.DataFrame([
        {
            "Modelo": nombre,
            "R² deja-una-semana": res[2 * i][0],
            "R² deja-un-bloque": res[2 * i + 1][0],
            "MAE bloque (kg/ha)": res[2 * i + 1][1],
            "Qué supone": nota,
        }
        for i, (nombre, _, nota) in enumerate(familias)
    ])


def correlaciones_con_objetivo(
    tabla: pd.DataFrame, metodo: str = "pearson",
    variables: Sequence[str] = FEATURES,
) -> pd.DataFrame:
    """Matriz de correlación del objetivo contra `variables`, con etiquetas legibles.

    Por omisión usa `FEATURES` (lo que ve el modelo), pero «Impacto agronómico»
    pasa `VARIABLES_DESCRIPTIVAS` a propósito: la asociación cruda no debe mostrar ya un
    promedio móvil.
    """
    cols = [OBJETIVO, *variables]
    corr = tabla[cols].corr(method=metodo)
    nombres = ["kg/ha", *[etiqueta(f) for f in variables]]
    corr.index = nombres
    corr.columns = nombres
    return corr
