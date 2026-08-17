"""Excel de campaña → panel Fundo × Módulo × Semana.

El grano del panel es **el módulo**: no hay lógica de turnos en ninguna parte. Si el
archivo trae la columna `Turno`, se consolida a módulo al leer y no vuelve a aparecer.

Sin Streamlit a propósito: esto es transformación de datos y se puede probar sin levantar
la app. La capa de caché vive en `servicios/`.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field

import pandas as pd

from ..config import HOJAS, TBASE_GDD
from .floracion import integrar_floracion
from .poda import integrar_poda


@dataclass(frozen=True)
class Hallazgo:
    """Un problema de calidad detectado al armar el panel."""

    clave: str
    titulo: str
    gravedad: str  # "alta" | "media" | "baja"
    detalle: str
    efecto: str


@dataclass
class Panel:
    """El panel consolidado más el registro de lo que hubo que arreglar para armarlo."""

    tabla: pd.DataFrame
    hallazgos: list[Hallazgo] = field(default_factory=list)

    @property
    def n_modulos(self) -> int:
        return int(self.tabla.celda.nunique())

    @property
    def n_semanas(self) -> int:
        return int(self.tabla.nsem.nunique())

    def graves(self) -> list[Hallazgo]:
        return [h for h in self.hallazgos if h.gravedad == "alta"]


def _norm(df: pd.DataFrame) -> pd.DataFrame:
    """Quita espacios sobrantes de los nombres de columna."""
    df.columns = [str(c).strip() for c in df.columns]
    return df


def _col(df: pd.DataFrame, nombre: str) -> str:
    """Columna cuyo nombre normalizado coincide, tolerando tildes mal codificadas."""
    for c in df.columns:
        if c.lower().replace("ó", "o").replace("�", "o") == nombre.lower():
            return c
    raise KeyError(f"No encuentro la columna «{nombre}» en {list(df.columns)}")


def _cosecha(xl: pd.ExcelFile, hallazgos: list[Hallazgo]) -> pd.DataFrame:
    """Hoja KgHa → una fila por Fundo+Módulo+Semana, con el kg/ha ponderado por área."""
    kg = _norm(xl.parse("KgHa"))
    kg = kg.rename(
        columns={
            _col(kg, "Fundo"): "Fundo",
            _col(kg, "Modulo"): "Modulo",
            _col(kg, "Semana"): "Semana",
            _col(kg, "Area"): "Area",
            _col(kg, "Kilogramos"): "Kg",
        }
    )

    sufijados = int(kg.Modulo.isin(["M10A", "M10B"]).sum())
    if sufijados:
        hallazgos.append(Hallazgo(
            "modulos_sufijados", "M10A y M10B se fusionan en M10", "baja",
            f"{sufijados} filas de cosecha usan los sufijos A/B, que el riego no "
            "distingue: allí M10 es un solo módulo.",
            "Sin fusionar, esas filas quedarían sin riego y saldrían del análisis.",
        ))
    kg["Modulo"] = kg.Modulo.replace({"M10A": "M10", "M10B": "M10"})

    n_antes = len(kg)
    panel = kg.groupby(["Fundo", "Modulo", "Semana"], as_index=False).agg(
        Kg=("Kg", "sum"), Area=("Area", "sum")
    )
    if n_antes > len(panel):
        hallazgos.append(Hallazgo(
            "cosecha_duplicada", "Filas de cosecha repetidas", "baja",
            f"{n_antes - len(panel)} filas compartían Fundo+Módulo+Semana. Se consolidan "
            "sumando kilos y área.",
            "El kg/ha resultante queda ponderado por área. Promediar los kg/ha parciales "
            "habría dado un número distinto y equivocado.",
        ))
    panel["KgHa"] = panel.Kg / panel.Area
    return panel


def _riego(xl: pd.ExcelFile, hallazgos: list[Hallazgo]) -> pd.DataFrame:
    """Hoja Riego → una fila por módulo y semana. El turno no sobrevive a esta función.

    La variable que se usa aguas abajo es **`Lt/planta`**, no `m3/ha`. El porqué está en
    `_revisar_agregacion`: en el archivo vigente las dos columnas se agregaron con
    criterios distintos y solo `Lt/planta` quedó al grano del módulo.
    """
    ri = _norm(xl.parse("Riego"))
    ri = ri.rename(
        columns={
            _col(ri, "Fundo"): "Fundo",
            _col(ri, "Modulo"): "Modulo",
            _col(ri, "Semana"): "Semana",
            _col(ri, "Lt/planta"): "riego_lt_planta",
            _col(ri, "m3/ha"): "riego_m3_ha",
        }
    )
    llave = ["Fundo", "Modulo", "Semana"]

    if "Turno" in ri.columns:
        # Formato antiguo: cada turno riega un sector distinto del módulo, así que el
        # valor del módulo es el promedio entre turnos. Sumar contaría cada hectárea
        # tantas veces como turnos tenga.
        hallazgos.append(Hallazgo(
            "riego_por_turno", "Riego consolidado desde turnos", "baja",
            f"El archivo trae {ri.Turno.nunique()} turnos por módulo. Se promedian.",
            "Promediar, no sumar: cada turno ya viene expresado por hectárea de su "
            "propio sector.",
        ))
        ri = ri.groupby(llave, as_index=False).agg(
            riego_lt_planta=("riego_lt_planta", "mean"),
            riego_m3_ha=("riego_m3_ha", "mean"),
        )
    elif ri.duplicated(subset=llave).any():
        ri = ri.groupby(llave, as_index=False).agg(
            riego_lt_planta=("riego_lt_planta", "mean"),
            riego_m3_ha=("riego_m3_ha", "mean"),
        )

    _revisar_agregacion(ri, hallazgos)
    _revisar_ceros(ri, hallazgos)
    return ri[[*llave, "riego_lt_planta", "riego_m3_ha"]]


def _revisar_agregacion(ri: pd.DataFrame, hallazgos: list[Hallazgo]) -> None:
    """Comprueba que `m3/ha` y `Lt/planta` describan el mismo riego.

    Las dos columnas miden lo mismo con distinta unidad, así que su cociente es la
    densidad de plantación: un número parecido en todo el fundo. Si en cambio es constante
    DENTRO de cada módulo pero salta entre módulos en proporción entera, es la firma de
    que una columna se sumó sobre los turnos y la otra se promedió — que es exactamente lo
    que pasaba en la versión de agosto de 2026 de este archivo.
    """
    d = ri[(ri.riego_lt_planta > 0) & (ri.riego_m3_ha > 0)].copy()
    if d.empty:
        return
    d["mod"] = d.Fundo + " · " + d.Modulo
    razon = d.groupby("mod").apply(
        lambda g: g.riego_m3_ha.sum() / g.riego_lt_planta.sum(), include_groups=False
    )
    if len(razon) < 2 or razon.min() <= 0:
        return

    relativo = float(razon.max() / razon.min())
    dispersion = float(razon.std() / razon.mean())
    plantas_ha = float(razon.mean() * 1000)

    if relativo > 1.1 and dispersion > 0.02:
        hallazgos.append(Hallazgo(
            "riego_agregacion_inconsistente",
            "«m3/ha» y «Lt/planta» se agregaron con criterios distintos", "alta",
            "El cociente m3/ha ÷ Lt/planta es constante dentro de cada módulo pero salta "
            f"entre módulos en proporción 1 a {relativo:.2f}. Si ambas columnas "
            "describieran el mismo riego, ese cociente sería la densidad de plantación y "
            "no dependería del módulo. El escalón coincide con el número de turnos: "
            "**`m3/ha` viene sumado sobre los turnos y `Lt/planta` promediado**.",
            "El análisis usa **`Lt/planta`**, que es la columna que sí quedó al grano del "
            "módulo. `m3/ha` se conserva solo para mostrar, y su magnitud absoluta no debe "
            "leerse como lámina de riego.",
        ))
        return

    hallazgos.append(Hallazgo(
        "riego_coherente", "Las dos columnas de riego son coherentes entre sí", "baja",
        f"El cociente m3/ha ÷ Lt/planta vale {razon.mean():.2f} en los {len(razon)} "
        f"módulos, con una dispersión de {dispersion:.1%}. Eso equivale a una densidad de "
        f"**{plantas_ha:,.0f} plantas/ha**".replace(",", ".") +
        ", coherente con una plantación de arándano en alta densidad.",
        "Ambas columnas describen el mismo riego, así que el análisis puede usar "
        "cualquiera de las dos. Se usa `Lt/planta` por ser la más directa de interpretar.",
    ))


def _cadencia_del_riego(
    tabla: pd.DataFrame, hallazgos: list[Hallazgo]
) -> pd.DataFrame:
    """Decide si el riego viene por día o por semana, y lo lleva a semanal.

    La ETo del archivo es semanal, así que el riego tiene que estar en la misma unidad
    para poder compararlos. La regla es física, no una preferencia: en riego por goteo de
    arándano la lámina aplicada repone entre 0,3 y 1,5 veces la ETo. Se prueban las dos
    lecturas y se adopta la que cae dentro de esa banda.
    """
    d = tabla[tabla.riego_m3_ha > 0]
    if d.empty:
        tabla["riego_mm_semana"] = tabla.riego_m3_ha / 10
        return tabla

    # 1 mm de lámina equivale a 10 m³/ha.
    ratio_semanal = float((d.riego_m3_ha / 10 / d.ETo).mean())
    ratio_diario = ratio_semanal * 7
    plausible = 0.3, 1.5

    if plausible[0] <= ratio_diario <= plausible[1] and not (
        plausible[0] <= ratio_semanal <= plausible[1]
    ):
        factor, cadencia, ratio = 7, "diario", ratio_diario
    else:
        factor, cadencia, ratio = 1, "semanal", ratio_semanal

    tabla["riego_mm_semana"] = tabla.riego_m3_ha * factor / 10
    tabla["riego_lt_planta_semana"] = tabla.riego_lt_planta * factor

    if cadencia == "diario":
        hallazgos.append(Hallazgo(
            "riego_diario", "El riego viene por día, no por semana", "baja",
            f"Leído como semanal, el riego repondría solo {ratio_semanal:.2f} veces la "
            f"ETo — imposible de sostener. Multiplicado por 7 da {ratio:.2f}, que es el "
            "rango normal del goteo en arándano. Los valores son **por día**.",
            "El panel guarda además el equivalente semanal "
            "(`riego_mm_semana`, `riego_lt_planta_semana`) para poder compararlo con la "
            "ETo, que sí es semanal. El modelo usa el valor por día: un factor constante "
            "no cambia ningún orden.",
        ))
    elif not plausible[0] <= ratio <= plausible[1]:
        hallazgos.append(Hallazgo(
            "riego_implausible", "La lámina de riego no es físicamente plausible", "alta",
            f"El riego declarado repone {ratio:.2f} veces la evapotranspiración. En goteo "
            "de arándano se espera entre 0,3 y 1,5, y ninguna de las dos lecturas "
            "—diaria o semanal— cae en ese rango.",
            "El orden de los módulos por riego se conserva, así que el análisis de "
            "relación sigue en pie; lo que no se puede leer es la magnitud absoluta.",
        ))
    return tabla


def _revisar_ceros(ri: pd.DataFrame, hallazgos: list[Hallazgo]) -> None:
    """Semanas con riego exactamente cero: ¿parada real o dato faltante?"""
    ceros = ri[ri.riego_lt_planta == 0]
    if ceros.empty:
        return
    fundos = ", ".join(sorted(ceros.Fundo.unique()))
    semanas = sorted({int(s[1:]) for s in ceros.Semana})
    tramo = (f"S{semanas[0]}–S{semanas[-1]}"
             if semanas == list(range(semanas[0], semanas[-1] + 1))
             else ", ".join(f"S{s}" for s in semanas[:6]) + "…")
    hallazgos.append(Hallazgo(
        "riego_cero", "Semanas con riego cero", "media",
        f"{len(ceros)} filas registran riego exactamente 0, todas en {fundos}, "
        f"en {tramo}.",
        "No se puede distinguir «no se regó» de «no se registró». Solo afecta al análisis "
        "si esas semanas tienen cosecha; Datos y calidad indica cuántas la tienen.",
    ))


def _clima(xl: pd.ExcelFile) -> pd.DataFrame:
    """Las tres hojas de clima → una fila por semana, para todo el fundo, con GDD."""
    tm = _norm(xl.parse("Temp Max-Min")).rename(
        columns={"Temp Max": "TempMax", "Temp Min": "TempMin", "VarDia": "VarDia"}
    )
    rad = _norm(xl.parse("Rad y ET")).rename(columns={"RadSolc": "Rad", "ET-mm": "ETo"})
    dpv = _norm(xl.parse("DPV"))
    clima = (
        tm[["Semana", "TempMax", "TempMin", "VarDia"]]
        .merge(rad[["Semana", "Rad", "ETo"]], on="Semana")
        .merge(dpv[["Semana", "DPV"]], on="Semana")
    )
    return _agregar_gdd(clima)


def _agregar_gdd(clima: pd.DataFrame) -> pd.DataFrame:
    """Grados-día de crecimiento, semanales y acumulados.

    El GDD traduce temperatura en desarrollo: por debajo de la temperatura base la planta
    no avanza, y por encima avanza en proporción al exceso. Es la forma estándar de medir
    tiempo fisiológico en vez de tiempo de calendario.

        GDD_día    = max(0, (Tmáx + Tmín) / 2 − Tbase)
        GDD_semana = 7 × GDD_día

    Las temperaturas del archivo ya son promedios semanales de los valores diarios, así
    que multiplicar por 7 reconstruye el acumulado de la semana. El acumulado corre desde
    la primera semana del año: sin la fecha de poda por módulo no hay un origen mejor, y
    ésa es justamente una de las variables que el análisis echa de menos.
    """
    clima = clima.copy()
    clima["nsem_clima"] = clima.Semana.str.extract(r"(\d+)").astype(int)
    clima = clima.sort_values("nsem_clima")

    media = (clima.TempMax + clima.TempMin) / 2
    clima["gdd_semana"] = 7 * (media - TBASE_GDD).clip(lower=0)
    clima["gdd_acum"] = clima.gdd_semana.cumsum()
    return clima.drop(columns=["nsem_clima"])


def cargar_panel(
    contenido: bytes,
    lags_config: dict | None = None,
    poda_contenido: bytes | None = None,
    floracion_contenido: bytes | None = None,
) -> Panel:
    """Excel de 5 hojas → `Panel`. Lanza ValueError si el archivo no sirve."""
    if lags_config is None:
        # Ventanas encontradas por búsqueda por coordenadas, optimizando el R² honesto
        # (deja-un-bloque-fuera) de kg/ha — no elegidas a mano. Reemplazan a
        # {"riego": 1, "Rad": 7, "ETo": 7, "DPV": 7, "gdd": 7}, que rendía +0,204 ± 0,010
        # de R² honesto (8 semillas) contra +0,340 ± 0,012 de ésta. Detalle completo,
        # incluida la verificación multi-semilla, en `docs/data/resumen_sesion.md` §10.
        lags_config = {"riego": 7, "Rad": 3, "ETo": 2, "DPV": 6, "gdd": 7}
    elif "gdd" not in lags_config:
        lags_config["gdd"] = 7
    hallazgos: list[Hallazgo] = []
    xl = pd.ExcelFile(io.BytesIO(contenido))
    faltan = HOJAS - set(xl.sheet_names)
    if faltan:
        raise ValueError(f"Al Excel le faltan hojas: {sorted(faltan)}")

    tabla = _cosecha(xl, hallazgos).merge(
        _riego(xl, hallazgos), on=["Fundo", "Modulo", "Semana"], how="left"
    )
    sin_riego = int(tabla.riego_lt_planta.isna().sum())
    if sin_riego:
        hallazgos.append(Hallazgo(
            "cosecha_sin_riego", "Cosecha sin riego registrado", "media",
            f"{sin_riego} celdas con cosecha no tienen fila de riego.",
            "Se descartan del panel: el modelo no puede usarlas.",
        ))
        tabla = tabla.dropna(subset=["riego_lt_planta"])

    # El clima se replica a cada módulo de la semana: es un dato del fundo, no del módulo.
    tabla = tabla.merge(_clima(xl), on="Semana", how="inner")

    tabla["nsem"] = tabla.Semana.str.extract(r"(\d+)").astype(int)
    tabla["celda"] = tabla.Fundo + " · " + tabla.Modulo
    tabla = tabla.sort_values(["Fundo", "Modulo", "nsem"]).reset_index(drop=True)

    if tabla.empty:
        raise ValueError("El panel quedó vacío tras cruzar las hojas.")

    # Necesita la ETo, así que va después de cruzar el clima.
    tabla = _cadencia_del_riego(tabla, hallazgos)
    _revisar_granularidad(tabla, hallazgos)
    tabla = integrar_poda(tabla, poda_contenido, hallazgos)
    tabla = integrar_floracion(tabla, floracion_contenido, hallazgos)
    tabla = _agregar_lags(tabla, lags_config, hallazgos)
    tabla = _agregar_frutos_peso(xl, tabla, hallazgos)
    return Panel(tabla=tabla, hallazgos=hallazgos)


def _agregar_frutos_peso(
    xl: pd.ExcelFile, tabla: pd.DataFrame, hallazgos: list[Hallazgo]
) -> pd.DataFrame:
    """Suma `Frutos` (conteo) y `Peso` (peso medio del fruto) desde la hoja «Kg Reales».

    Es una tabla pivote de Excel exportada sin limpiar: dos bloques de columnas lado a
    lado (uno con nombres tipo «Suma de Kg/Ha», otro ya limpio con Fundo/Modulo/Semana).
    Se lee el bloque limpio por posición (columnas 9 a 15) porque los nombres se
    duplican entre bloques y pandas los renombra de forma poco predecible.

    Si la hoja no está, o cambió de forma y las tres primeras columnas del bloque ya no
    son Fundo/Módulo/Semana, se degrada sin romper: el panel sigue sin estas dos
    columnas y se avisa por qué.
    """
    tabla["Frutos"] = pd.NA
    tabla["Peso"] = pd.NA

    if "Kg Reales" not in xl.sheet_names:
        return tabla

    crudo = _norm(xl.parse("Kg Reales", header=3))
    if crudo.shape[1] < 16:
        hallazgos.append(Hallazgo(
            "frutos_peso_formato", "«Kg Reales» no tiene el formato esperado", "baja",
            f"La hoja trae {crudo.shape[1]} columnas; se esperaban al menos 16.",
            "No se cargan Frutos ni Peso. El resto del panel no se ve afectado.",
        ))
        return tabla

    bloque = crudo.iloc[:, 9:16].copy()
    bloque.columns = ["Fundo", "Modulo", "Semana", "Kg_kgreales", "Frutos", "Peso",
                      "KgHa_kgreales"]
    bloque = bloque.dropna(subset=["Fundo", "Modulo", "Semana"])

    if bloque.empty or not bloque.Semana.astype(str).str.match(r"^S\d+$").all():
        hallazgos.append(Hallazgo(
            "frutos_peso_formato", "«Kg Reales» no tiene el formato esperado", "baja",
            "Las columnas en la posición esperada (10ª a 16ª) no tienen la forma "
            "Fundo/Módulo/Semana/Kg/Frutos/Peso/Kg·Ha que se esperaba.",
            "No se cargan Frutos ni Peso. El resto del panel no se ve afectado.",
        ))
        return tabla

    # La hoja trae Fundo+Módulo+Semana repetidos (el mismo problema de M10A/M10B que en
    # la hoja KgHa, pero sin fusionar acá). A diferencia de Kg y Área, «Frutos» y «Peso»
    # no son sumables ni promediables sin suponer una fórmula que no está documentada
    # (se comprobó: Peso ≠ Kg/Frutos). Para las llaves duplicadas, mejor NaN declarado
    # que un número inventado — y sin deduplicar, el merge multiplicaría filas del panel.
    llave = ["Fundo", "Modulo", "Semana"]
    repetidas = bloque.duplicated(subset=llave, keep=False)
    n_ambiguas = int(bloque.loc[repetidas, llave].drop_duplicates().shape[0])
    bloque.loc[repetidas, ["Frutos", "Peso"]] = pd.NA
    bloque = bloque.drop_duplicates(subset=llave, keep="first")

    tabla = tabla.drop(columns=["Frutos", "Peso"]).merge(
        bloque[["Fundo", "Modulo", "Semana", "Frutos", "Peso"]],
        on=llave, how="left",
    )
    if n_ambiguas:
        hallazgos.append(Hallazgo(
            "frutos_peso_duplicado", "Frutos/Peso ambiguos en filas repetidas", "baja",
            f"{n_ambiguas} celdas de «Kg Reales» tienen más de una fila para el mismo "
            "Fundo+Módulo+Semana, con valores de Frutos y Peso distintos entre sí y sin "
            "una regla de combinación documentada.",
            "Esas celdas quedan sin Frutos ni Peso (NaN) en vez de sumar o promediar "
            "una fórmula no verificada.",
        ))
    con_dato = int(tabla.Frutos.notna().sum())
    hallazgos.append(Hallazgo(
        "frutos_peso_agregado", "Frutos y peso del fruto, incorporados", "baja",
        f"La hoja «Kg Reales» trae el conteo de frutos y el peso medio del fruto por "
        f"módulo y semana; se emparejaron {con_dato} de {len(tabla)} celdas.",
        "kg/ha ≈ Frutos × Peso × densidad de plantas — son casi la misma información que "
        "el objetivo, vista por sus dos componentes biológicos, no dos predictores "
        "independientes. No se agregan al modelo XGBoost por esa razón: usarlas para "
        "predecir kg/ha sería casi tautológico. Sí sirven para ver si el clima o el "
        "riego afectan más al número de frutos o a su tamaño — ver «Frutos y peso» en "
        "Impacto agronómico.",
    ))
    return tabla


def _revisar_granularidad(tabla: pd.DataFrame, hallazgos: list[Hallazgo]) -> None:
    """El clima vale para toda la semana: eso limita cuánto puede explicar."""
    n_celdas, n_semanas = len(tabla), int(tabla.nsem.nunique())
    repeticion = n_celdas / n_semanas
    hallazgos.append(Hallazgo(
        "clima_semanal", "El clima se mide por semana, no por módulo", "media",
        f"Cada valor de temperatura, radiación, ETo y DPV se repite {repeticion:.1f} veces "
        f"en el panel: hay {n_celdas} celdas pero solo {n_semanas} mediciones distintas.",
        "No es un error del dato —dentro del fundo esas variables no cambian de un módulo "
        f"al vecino— pero sí limita la estadística: el n efectivo es {n_semanas}, no "
        f"{n_celdas}. Los intervalos de confianza calculados sobre {n_celdas} filas serían "
        f"{(n_celdas / n_semanas) ** 0.5:.1f} veces más estrechos de lo correcto.",
    ))


def _rolling_semanal(serie_por_semana: pd.Series, ventana: int) -> pd.Series:
    """Promedio móvil de una serie YA indexada por número de semana, sin huecos.

    `serie_por_semana` debe traer un valor por cada semana entre su mínimo y su máximo
    — reindexar antes de llamar esta función es lo que hace que el hueco cuente como
    hueco (NaN) y no como «la observación anterior que hubiera».
    """
    completa = serie_por_semana.reindex(
        range(int(serie_por_semana.index.min()), int(serie_por_semana.index.max()) + 1)
    )
    return completa.rolling(ventana, min_periods=ventana).mean()


def _rolling_climatico(tabla: pd.DataFrame, col: str, ventana: int) -> pd.Series:
    """Promedio móvil de una variable de clima: un valor por semana, para todo el fundo.

    Se rueda UNA vez sobre la serie semanal (no una vez por módulo) porque el valor ya es
    el mismo para todos los módulos de una semana. Rodar por módulo sería redundante y,
    peor, silenciosamente incorrecto: como los módulos no cosechan todas las semanas,
    "las últimas `ventana` filas de ese módulo" no son "las últimas `ventana` semanas de
    calendario" — pueden saltar meses si el módulo tuvo un hueco de cosecha.
    """
    semanal = tabla.drop_duplicates("nsem").set_index("nsem")[col].sort_index()
    rolado = _rolling_semanal(semanal, ventana)
    return tabla.nsem.map(rolado)


def _rolling_por_modulo(tabla: pd.DataFrame, col: str, ventana: int) -> pd.Series:
    """Promedio móvil de una variable que sí varía por módulo (el riego), por calendario.

    Reindexa la serie de CADA módulo a semanas de calendario consecutivas antes de rodar,
    para que un hueco de cosecha se trate como falta de dato y no como continuidad.
    """
    resultado = pd.Series(index=tabla.index, dtype=float)
    for _, grupo in tabla.groupby(["Fundo", "Modulo"]):
        semanal = grupo.set_index("nsem")[col].sort_index()
        rolado = _rolling_semanal(semanal, ventana)
        resultado.loc[grupo.index] = rolado.reindex(grupo.nsem).to_numpy()
    return resultado


def _agregar_lags(
    tabla: pd.DataFrame, lags_config: dict, hallazgos: list[Hallazgo]
) -> pd.DataFrame:
    """Aplica promedios móviles con ventanas independientes por variable.

    Cada ventana exige estar COMPLETA (`min_periods=ventana`): una semana sin las
    `ventana` semanas de calendario que terminan en ella queda en NaN, no con un promedio calculado
    sobre menos datos de los pedidos. Es una decisión deliberada — mejor perder esa fila
    del modelo que fingir una ventana que no está.
    """
    columnas_lag = []
    for col in ("DPV", "Rad", "ETo", "gdd_semana"):
        key_name = "gdd" if col == "gdd_semana" else col
        target_name = "gdd_lag" if col == "gdd_semana" else f"{col}_lag"
        v = max(1, lags_config.get(key_name, 1))
        tabla[target_name] = (
            tabla[col] if v == 1 else _rolling_climatico(tabla, col, v)
        )
        columnas_lag.append(target_name)

    v_riego = max(1, lags_config.get("riego", 1))
    tabla["riego_lag"] = (
        tabla["riego_lt_planta"] if v_riego == 1
        else _rolling_por_modulo(tabla, "riego_lt_planta", v_riego)
    )
    columnas_lag.append("riego_lag")

    incompletas = int(tabla[columnas_lag].isna().any(axis=1).sum())
    if incompletas:
        ventanas = ", ".join(
            f"{etq}={lags_config.get(k, 1)} sem." for k, etq in
            [("riego", "riego"), ("Rad", "Rad"), ("ETo", "ETo"), ("DPV", "DPV"),
             ("gdd", "GDD")] if lags_config.get(k, 1) > 1
        )
        hallazgos.append(Hallazgo(
            "lags_ventana_incompleta", "Celdas sin ventana de rezago completa", "media",
            f"{incompletas} de {len(tabla)} celdas no tienen las semanas de calendario "
            f"previas que pide la ventana configurada ({ventanas or 'todas en 1 semana'})"
            " — el módulo empezó su cosecha hace menos semanas que el largo de la ventana, "
            "o tuvo un hueco de cosecha justo antes.",
            "Esas celdas se excluyen del entrenamiento del modelo (no se rellenan con una "
            "ventana parcial): un promedio de 3 semanas cuando se pidieron 7 mediría otra "
            "cosa. Datos y calidad y la exportación indican cuántas filas quedan fuera.",
        ))
    return tabla


def diagnostico_ventanas(
    tabla: pd.DataFrame, lags_config: dict | None = None
) -> pd.DataFrame:
    """Expone cómo se construyó cada variable temporal que ve el modelo.

    La tabla no decide si una ventana es agronómicamente la correcta; deja auditable
    algo anterior y más básico: qué serie se rodó, sobre qué grano, cuántas semanas
    completas quedaron y si la columna cambia dentro de una semana. Esto evita llamar
    «fase» a una media móvil de semanas calendario.
    """
    cfg = {"riego": 7, "Rad": 3, "ETo": 2, "DPV": 6, "gdd": 7}
    cfg.update(lags_config or {})
    especificaciones = [
        ("DPV_lag", "DPV", "DPV", "clima · una serie por semana", "media móvil calendario"),
        ("riego_lag", "riego_lt_planta", "riego", "riego · Fundo + Módulo", "media móvil por módulo"),
        ("Rad_lag", "Rad", "Rad", "clima · una serie por semana", "media móvil calendario"),
        ("ETo_lag", "ETo", "ETo", "clima · una serie por semana", "media móvil calendario"),
        ("gdd_lag", "gdd_semana", "gdd", "clima · una serie por semana", "media móvil calendario"),
        ("TempMax", "TempMax", None, "clima · semana actual", "valor de la semana"),
        ("TempMin", "TempMin", None, "clima · semana actual", "valor de la semana"),
    ]
    filas = []
    for destino, fuente, clave, ambito, regla in especificaciones:
        serie = tabla[destino]
        por_semana = tabla.groupby("nsem")[destino].nunique(dropna=True)
        filas.append({
            "Columna modelo": destino,
            "Columna fuente": fuente,
            "Ventana (sem)": int(cfg[clave]) if clave else 1,
            "Cobertura temporal": (
                f"t-{int(cfg[clave]) - 1} a t" if clave and int(cfg[clave]) > 1
                else "t"
            ),
            "Incluye semana objetivo": "Si",
            "Ámbito": ambito,
            "Regla aplicada": regla,
            "Filas con valor": int(serie.notna().sum()),
            "Semanas con valor": int(tabla.loc[serie.notna(), "nsem"].nunique()),
            "Max. valores distintos por semana": int(por_semana.max()) if not por_semana.empty else 0,
        })
    return pd.DataFrame(filas)
