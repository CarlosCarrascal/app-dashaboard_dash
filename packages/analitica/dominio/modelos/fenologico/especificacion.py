"""Especificación estable de variables e hipótesis del modelo fenológico."""

NOMBRE_MODELO = "FenologicoComponentes_v1"

FEATURES_CONTROL = [
    "horizonte_semanas",
    "semana_objetivo_sin",
    "semana_objetivo_cos",
    "plantas",
    "dias_desde_poda",
    "semanas_desde_ultima_cosecha",
]

# La emisión no empieza desde cero: un lote ya trae kilos y pasadas observadas. Estas
# variables son acumulados estrictamente anteriores a la emisión y permiten que el modelo
# continúe la curva real en vez de volver a estimar el lote como si nunca hubiera cosechado.
FEATURES_HISTORIAL = [
    "kg_acumulado_asof",
    "kg_ultima_cosecha_asof",
    "kg_ultimas_4_semanas_asof",
    "semanas_cosecha_asof",
    "pasada_ultima_asof",
]

FEATURES_FENOLOGIA = [
    "ramas_por_planta",
    "proporcion_ramas_gruesas",
    "diametro_rama_mm",
    "brotes_por_planta",
    "yemas_por_planta",
    "proporcion_yemas_abiertas",
    "flores",
    "cuajo",
    "tasa_cuajo_observada",
    "frutos_muestra",
    "indice_estado",
    "prop_e1",
    "prop_e2",
    "prop_e3",
    "prop_e4",
    "prop_e5",
    "diametro_baya_mm",
    "sd_diametro_baya_mm",
]

FEATURES_CLIMA = [
    f"{variable}_{ventana}d"
    for ventana in (7, 28)
    for variable in (
        "temp_media",
        "temp_max",
        "temp_min",
        "humedad",
        "dpv_kpa",
        "radiacion",
        "eto",
        "lluvia",
        "gdd_0_0",
        "gdd_4_4",
        "gdd_7_0",
        "gdd_8_0",
    )
]

FEATURES_RIEGO = [
    f"riego_{variable}_{ventana}d"
    for ventana in (7, 28)
    for variable in ("agua_m3", "lamina_mm", "reposicion_pct")
]

FEATURES_OCURRENCIA = [
    *FEATURES_CONTROL,
    *FEATURES_HISTORIAL,
    *FEATURES_FENOLOGIA,
    *FEATURES_CLIMA,
    *FEATURES_RIEGO,
]
FEATURES_FRUTOS = [
    *FEATURES_CONTROL,
    *FEATURES_HISTORIAL,
    *FEATURES_FENOLOGIA,
    *FEATURES_CLIMA,
    *FEATURES_RIEGO,
    "frutos_por_planta_ultimo_asof",
]
FEATURES_PESO = [
    *FEATURES_CONTROL,
    *FEATURES_HISTORIAL,
    "indice_estado",
    "prop_e4",
    "prop_e5",
    "diametro_baya_mm",
    "sd_diametro_baya_mm",
    *FEATURES_CLIMA,
    *FEATURES_RIEGO,
    "peso_real_g_ultimo_asof",
]

FEATURES_PROHIBIDAS = {
    "p10_kg",
    "p50_kg",
    "p90_kg",
    "real_kg",
    "peso_real_g",
    "frutos_reales_por_planta_catalogo",
    "frutos_por_planta_r09",
    "peso_baya_r09",
    "kg_r09",
}

HIPOTESIS_FEATURE = {
    "dias_desde_poda": ("H1", "Poda y acumulación térmica preceden la floración."),
    "flores": ("H2", "Flores y cuajado preceden la cantidad de frutos."),
    "cuajo": ("H2", "Flores y cuajado preceden la cantidad de frutos."),
    "tasa_cuajo_observada": ("H2", "Flores y cuajado preceden la cantidad de frutos."),
    "frutos_muestra": ("H2", "El censo fenológico anticipa la carga de frutos."),
    "indice_estado": ("H3", "La distribución E1–E5 anticipa la cosecha."),
    "prop_e1": ("H3", "La distribución E1–E5 anticipa la cosecha."),
    "prop_e2": ("H3", "La distribución E1–E5 anticipa la cosecha."),
    "prop_e3": ("H3", "La distribución E1–E5 anticipa la cosecha."),
    "prop_e4": ("H3", "La distribución E1–E5 anticipa la cosecha."),
    "prop_e5": ("H3", "La distribución E1–E5 anticipa la cosecha."),
    "diametro_baya_mm": ("H4", "Diámetro y estado anticipan el peso de baya."),
    "sd_diametro_baya_mm": ("H4", "La dispersión del calibre informa el peso esperado."),
}

REFERENCIAS_HIPOTESIS = {
    "H1": ["HEAT_HARVEST_2012", "KIRK_ISAACS_2012"],
    "H2": ["GIBBS_2016_POLLINATION", "CA244NI"],
    "H3": ["HEAT_HARVEST_2012", "WAN_2024_FRUIT"],
    "H4": ["WAN_2024_FRUIT", "GIBBS_2016_POLLINATION"],
    "H6": ["HOLZAPFEL_2004_IRRIGATION"],
    "H6_R": ["HOLZAPFEL_2004_IRRIGATION"],
}

__all__ = [
    "FEATURES_CLIMA",
    "FEATURES_CONTROL",
    "FEATURES_FENOLOGIA",
    "FEATURES_FRUTOS",
    "FEATURES_HISTORIAL",
    "FEATURES_OCURRENCIA",
    "FEATURES_PESO",
    "FEATURES_PROHIBIDAS",
    "FEATURES_RIEGO",
    "HIPOTESIS_FEATURE",
    "NOMBRE_MODELO",
    "REFERENCIAS_HIPOTESIS",
]
