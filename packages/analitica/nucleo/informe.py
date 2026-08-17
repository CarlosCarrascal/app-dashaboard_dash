"""Qué hojas lleva el Excel exportado, y con qué nota se explica cada una.

Vive separado de `exportar.py` porque ése sabe de formato y éste sabe de contenido:
qué merece salir del tablero y cómo se explica sin el tablero delante.
"""

from __future__ import annotations

import pandas as pd

from ..config import FEATURES, GLOSARIO, etiqueta
from . import clima as cl
from .datos import Panel
from .exportar import Hoja, construir_libro

# Las columnas *_lag (las que ve el modelo) se exportan aparte de las crudas, no en
# lugar de ellas: FEATURES ya incluye TempMax/TempMin sin sufijo, que están abajo.
COLUMNAS_LAG = tuple(f for f in FEATURES if f.endswith("_lag"))

COLUMNAS_PANEL = [
    "Fundo", "Modulo", "Semana", "nsem", "Area", "Kg", "KgHa", "Frutos", "Peso",
    "riego_lt_planta", "riego_m3_ha", "TempMax", "TempMin", "VarDia", "Rad", "ETo", "DPV",
    "poda_fecha", "poda_dispersion_dias", "dias_desde_poda", "Variedad",
    "edad_planta_anos", "gdd_acum_poda_obs",
    "flores_promedio", "flores_dispersion_relativa",
    *COLUMNAS_LAG,
]

NOMBRES_PANEL = {
    "nsem": "N° semana", "Area": "Área (ha)", "Kg": "Kilos", "KgHa": "kg/ha",
    "Frutos": "Frutos (por planta)", "Peso": "Peso del fruto (g)",
    "riego_lt_planta": "Riego (L/planta)", "riego_m3_ha": "Riego (m³/ha, sin corregir)",
    "TempMax": "Temp. máx (°C)", "TempMin": "Temp. mín (°C)",
    "VarDia": "Amplitud térmica (°C)", "Rad": "Radiación", "ETo": "ETo (mm)",
    "DPV": "DPV (kPa)", **{f: etiqueta(f) for f in COLUMNAS_LAG},
    "poda_fecha": "Fecha de poda (promedio por área)",
    "poda_dispersion_dias": "Dispersión de poda (días)",
    "dias_desde_poda": "Días desde poda (proxy)",
    "Variedad": "Variedad dominante",
    "edad_planta_anos": "Edad de planta (años, proxy)",
    "gdd_acum_poda_obs": "GDD observado desde poda",
    "flores_promedio": "Flores (promedio por turno)",
    "flores_dispersion_relativa": "Dispersión de floración entre turnos",
}


def _glosario() -> pd.DataFrame:
    return pd.DataFrame(
        [{"Variable": etiqueta(k), "Qué significa": v} for k, v in GLOSARIO.items()]
    )


def _calidad(panel: Panel) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"Gravedad": h.gravedad, "Hallazgo": h.titulo, "Detalle": h.detalle,
             "Efecto sobre el análisis": h.efecto}
            for h in panel.hallazgos
        ]
    )


def _limitaciones(panel: Panel, sem: pd.DataFrame) -> pd.DataFrame:
    ef = cl.tamano_efectivo(panel.tabla)
    ver = cl.veredicto(sem)
    filas = [
        ("Grano del clima",
         f"Temperatura, radiación, ETo y DPV traen un valor por semana, común a los "
         f"{panel.n_modulos} módulos. El n efectivo para esas variables es "
         f"{ef.n_semanas} semanas, no {ef.n_celdas} celdas."),
        ("Intervalos de confianza",
         f"Calcularlos sobre las {ef.n_celdas} celdas los estrecharía "
         f"{ef.factor_inflacion:.1f} veces de más. Las cifras de este libro usan "
         f"n = {ef.n_semanas}."),
        ("Confusión estacional",
         f"La serie sin significado físico que mejor correlaciona con el kg/ha es "
         f"«{ver.placebo_mas_fuerte}» (r = {ver.r_placebo:+.3f}). Cualquier variable con "
         "forma estacional correlaciona, tenga o no relación con la planta."),
        ("Poda agregada",
         "M_Poda se integra desde lote a módulo mediante una fecha ponderada por área. "
         "La dispersión entre lotes se conserva y limita la lectura biológica."),
        ("Causalidad",
         "Nada de este análisis establece causa y efecto. Son datos observacionales de "
         "una sola campaña; para separar el efecto del clima del calendario de poda haría "
         "falta variación experimental o varias campañas."),
        ("Variación entre módulos",
         "Las variables climáticas son idénticas para todos los módulos de una semana, "
         "así que por construcción no pueden explicar por qué dos módulos rinden distinto "
         "en la misma semana."),
        ("Una sola campaña",
         "Con 2025 solamente no se puede distinguir el efecto del clima del efecto de esa "
         "temporada en particular."),
    ]
    return pd.DataFrame(filas, columns=["Limitación", "Qué implica"])


def _metodologia(panel: Panel) -> pd.DataFrame:
    filas = [
        ("Grano del panel", "Una fila por Fundo × Módulo × Semana. No hay lógica de "
                            "turnos: el riego se consolida a módulo al leer el archivo."),
        ("Variable objetivo", "kg/ha = kilos ÷ área cosechada, ponderado por área cuando "
                              "hay varias filas para la misma celda."),
        ("Riego", "Se usa «L/planta», que es la columna agregada al grano del módulo. "
                  "«m³/ha» viene sumada sobre los turnos en el archivo vigente y su "
                  "magnitud no es una lámina de riego real."),
        ("Módulos M10A/M10B", "Se fusionan en M10, que es como se registra el riego."),
        ("Correlaciones del clima", "Se calculan sobre el panel agregado a una fila por "
                                    "semana, que es el grano al que el dato existe."),
        ("Control del calendario", f"Polinomio de grado {cl.GRADO_TENDENCIA} sobre el "
                                   "número de semana. Un control lineal no describe la "
                                   "joroba de la campaña y deja pasar la confusión."),
        ("Rezagos", f"Se prueban de 0 a {max(cl.LAGS)} semanas, siempre con y sin "
                    "tendencia. Solo la versión sin tendencia es interpretable."),
        ("Placebo", "Se contrastan las variables reales contra series inventadas con la "
                    "misma forma estacional, para medir cuánto de la correlación es forma."),
        ("Tres capas", "Asociación estadística, aporte predictivo y efecto agronómico "
                       "estimado se reportan por separado. Esta campaña cubre las dos "
                       "primeras; no identifica todavía la tercera."),
        ("SHAP", "Explica cómo XGBoost reparte una predicción. No se interpreta como "
                  "efecto causal ni como recomendación de intervención."),
        ("Fases agronómicas", "La poda y los días desde poda ya están incorporados como "
                              "reloj biológico proxy. La fase fenológica observada todavía "
                              "no está disponible."),
        ("Frutos y peso", "Se analizan como resultados biológicos secundarios. No entran "
                          "como predictores de kg/ha porque son sus componentes."),
        ("DML", "No está implementado: antes deben definirse tratamiento, confusores, "
                 "modificadores, solapamiento y partición temporal por campaña."),
    ]
    return pd.DataFrame(filas, columns=["Decisión", "Cómo se resolvió"])


def construir(
    panel: Panel,
    tabla_filtrada: pd.DataFrame,
    incluir: set[str] | None = None,
    origen: str = "IA.final.xlsx",
    fecha: str = "",
) -> bytes:
    """Arma el libro completo. `incluir` selecciona qué bloques opcionales van."""
    incluir = incluir or set()
    sem = cl.agregar_por_semana(panel.tabla)
    ef = cl.tamano_efectivo(panel.tabla)
    ver = cl.veredicto(sem)

    visible = [c for c in COLUMNAS_PANEL if c in tabla_filtrada.columns]
    hojas = [
        Hoja("Panel", "Panel consolidado (filtrado)",
             f"{len(tabla_filtrada)} celdas módulo × semana, con las columnas que usa el "
             "análisis. Refleja los filtros activos en el tablero al momento de exportar.",
             tabla_filtrada[visible].rename(columns=NOMBRES_PANEL)),
        Hoja("Resumen semanal", "El fundo agregado a una fila por semana",
             "Es el grano al que el clima existe y sobre el que se calculan todas las "
             "correlaciones climáticas de este libro.",
             sem.rename(columns={"nsem": "N° semana", "kg_ha": "kg/ha",
                                 "modulos": "Módulos", **NOMBRES_PANEL})),
        Hoja("Calidad de datos", "Qué se encontró al armar el panel",
             "Cada fila es un problema detectado automáticamente al leer el archivo, con "
             "su efecto sobre el análisis.", _calidad(panel)),
        Hoja("Metodologia", "Decisiones de método",
             "Las decisiones que cambian los números, y por qué se resolvieron así.",
             _metodologia(panel)),
        Hoja("Limitaciones", "Qué NO se puede concluir",
             "Leer antes de usar cualquier cifra de este libro para tomar una decisión.",
             _limitaciones(panel, sem)),
        Hoja("Glosario", "Qué significa cada variable",
             "En lenguaje llano, sin suponer formación en agronomía ni en estadística.",
             _glosario()),
    ]

    if "clima" in incluir:
        corr = cl.correlaciones_semanales(sem)
        hojas.insert(2, Hoja(
            "Correlaciones", "Correlación de cada variable con el kg/ha",
            f"Calculadas sobre {len(sem)} semanas. El intervalo de confianza usa ese n, no "
            f"las {ef.n_celdas} celdas del panel.",
            corr.drop(columns=["clave"]),
            porcentajes=("Varianza explicada",)))
        hojas.insert(3, Hoja(
            "Control del calendario", "¿Sobrevive la correlación al descontar la estación?",
                "«r control no lineal» retira la estación; el módulo de conclusiones añade "
                "el control proxy por días desde poda. Ninguna de las dos columnas es un "
                "efecto causal.",
            cl.correlacion_parcial(sem).drop(columns=["clave"]),
            porcentajes=("Queda",)))
        hojas.insert(4, Hoja(
            "Rezagos", "Correlación desplazando el clima k semanas",
            "«r bruto» sube con el rezago solo porque alinea dos curvas estacionales. "
            "«r sin tendencia» es la que tiene sentido leer.",
            cl.rezagos(sem).drop(columns=["clave"])))
        hojas.insert(5, Hoja(
            "Placebo", "Series sin significado físico, contra las reales",
            f"La serie inventada que mejor correlaciona es «{ver.placebo_mas_fuerte}» "
            f"(r = {ver.r_placebo:+.3f}). Si supera a las variables reales, lo que se mide "
            "es la forma estacional.", cl.placebo(sem)))
        if sem.Frutos.notna().sum() >= 10:
            hojas.insert(6, Hoja(
                "Frutos y peso", "El clima/riego, contra los dos componentes de kg/ha",
                "kg/ha ≈ Frutos × Peso × densidad. Correlacionar cada componente por "
                "separado distingue si el efecto es sobre el cuajado o sobre el tamaño "
                "del fruto — con el mismo control de calendario que el resto del libro.",
                cl.descomponer_frutos_peso(sem).drop(columns=["clave"])))
            hojas.insert(7, Hoja(
                "Trayectoria biologica", "Peak de frutos y cambio neto del peso por módulo",
                "El peak se ubica dentro de la ventana observada del módulo. La pendiente "
                "del peso resume el cambio neto; los cambios de sentido avisan cuando una "
                "recta oculta una curva ondulada. La nueva columna de días desde poda es "
                "un proxy porque la poda original está a nivel de lote.",
                cl.trayectorias_frutos_peso(panel.tabla)))

    if "modulo" in incluir:
        porm = cl.por_modulo(panel.tabla)
        hojas.insert(2, Hoja(
            "Por modulo", "La correlación calculada dentro de cada módulo",
            "Prueba de consistencia: si la relación fuera física debería repetirse en cada "
            "módulo. La columna «Inicio» es la primera semana con cosecha y explica el signo.",
            porm))
        hojas.insert(3, Hoja(
            "Signo vs ventana", "¿El signo lo decide cuándo cosecha el módulo?",
            "Correlación entre la semana en que arranca la cosecha de cada módulo y la "
            "correlación clima-rendimiento de ese módulo. Si es alta, la correlación mide "
            "el solapamiento de dos calendarios.",
            cl.signo_depende_de_la_ventana(porm).drop(columns=["clave"])))

    meta = [
        ("Generado por", "Tablero de impacto agronómico / aporte predictivo"),
        ("Archivo de origen", origen),
        ("Fecha de exportación", fecha),
        ("", None),
        ("ALCANCE", None),
        ("Celdas en el panel completo", f"{len(panel.tabla)}"),
        ("Celdas exportadas (con filtros)", f"{len(tabla_filtrada)}"),
        ("Módulos", f"{panel.n_modulos}"),
        ("Semanas", f"{panel.n_semanas}"),
        ("Variables predictoras", ", ".join(etiqueta(f) for f in FEATURES)),
        ("", None),
        ("ADVERTENCIA", None),
        ("Naturaleza del análisis",
         "Este libro describe ASOCIACIONES, no relaciones de causa y efecto."),
        ("Capacidad predictiva",
         "El tablero no pronostica. Ver la hoja «Limitaciones»."),
        ("n efectivo del clima",
         f"{ef.n_semanas} semanas (no {ef.n_celdas} celdas): cada valor de clima se "
         f"repite {ef.n_celdas / ef.n_semanas:.1f} veces en el panel."),
    ]
    if panel.graves():
        meta += [("", None), ("PROBLEMAS GRAVES DE DATOS", None)]
        meta += [(h.titulo, h.efecto) for h in panel.graves()]

    return construir_libro(hojas, meta)
