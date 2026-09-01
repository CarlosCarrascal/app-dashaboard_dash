"""Catálogos y funciones de presentación de la plataforma analítica."""

from __future__ import annotations

ETIQUETAS: dict[str, str] = {
    # Variables originales (panel, estudio climático, auditoría)
    "DPV": "DPV (kPa)",
    "riego_lt_planta": "Riego (L/planta·sem)",
    "riego_m3_ha": "Riego (m³/ha, sin corregir)",
    "riego_agua_ha": "Agua de riego por hectárea (unidad de la fuente)",
    "Rad": "Radiación solar",
    "ETo": "ETo (mm/sem)",
    "TempMax": "Temp. máxima (°C)",
    "TempMin": "Temp. mínima (°C)",
    "VarDia": "Amplitud térmica (°C)",
    "gdd_semana": "GDD de la semana (°C·día)",
    "gdd_acum": "GDD acumulados (°C·día)",
    "poda_fecha": "Fecha de poda (promedio por área)",
    "poda_fecha_min": "Primera fecha de poda del módulo",
    "poda_fecha_max": "Última fecha de poda del módulo",
    "poda_dispersion_dias": "Dispersión de poda (días)",
    "poda_n_lotes": "Lotes que aportan la poda",
    "poda_area_ha": "Área de poda (ha)",
    "Variedad": "Variedad dominante por área",
    "FSiembra": "Fecha de siembra (promedio por área)",
    "fecha_semana_aprox": "Fecha aproximada de la semana",
    "dias_desde_poda": "Días desde poda (proxy)",
    "edad_planta_anos": "Edad de planta (años, proxy)",
    "gdd_acum_poda_obs": "GDD observado desde poda",
    "gdd_semanas_poda_obs": "Semanas de GDD observadas desde poda",
    "flores_promedio": "Flores (promedio por turno)",
    "flores_desvio": "Flores, desvío entre turnos",
    "flores_n_turnos": "Turnos evaluados (floración)",
    "flores_dispersion_relativa": "Dispersión de floración entre turnos",
    "fecha_evaluacion": "Fecha de evaluación de floración",
    "nsem": "Número de semana",
    "KgHa": "Rendimiento (kg/ha)",
    "Frutos": "Frutos (por planta)",
    "Peso": "Peso del fruto (g)",
    # Features lagged (modelo XGBoost): promedio móvil dependiente del parámetro de ventana
    "DPV_lag": "DPV (prom. móvil) (kPa)",
    "riego_lag": "Riego (prom. móvil) (L/planta)",
    "Rad_lag": "Radiación (prom. móvil)",
    "ETo_lag": "ETo (prom. móvil) (mm)",
    "gdd_lag": "GDD (prom. móvil) (°C·día)",
}

# Qué mide cada variable y cómo leerla. Alimenta los tooltips y el glosario: la interfaz
# no debe pedirle al usuario que sepa de antemano qué es el DPV.
GLOSARIO: dict[str, str] = {
    # Variables originales
    "DPV": "Déficit de presión de vapor: cuánta sed le impone el aire a la planta. "
    "Alto = aire seco y caliente, la planta transpira más y puede cerrar estomas.",
    "riego_lt_planta": "Litros de agua aplicados por planta durante la semana, promediados "
    "entre los turnos de riego del módulo.",
    "riego_m3_ha": "Metros cúbicos por hectárea tal como vienen en el archivo. En la "
    "versión vigente esta columna está sumada sobre los turnos, así que su "
    "magnitud no es una lámina de riego real.",
    "riego_agua_ha": "Agua de riego por hectárea tal como viene en la fuente. La unidad se "
    "conserva sin convertir cuando el encabezado solo dice «Agua/ha».",
    "Rad": "Radiación solar incidente: la energía disponible para la fotosíntesis.",
    "ETo": "Evapotranspiración de referencia: cuánta agua evaporaría un cultivo patrón "
    "esa semana. Es la vara con la que se mide si el riego alcanza.",
    "TempMax": "Promedio semanal de la temperatura máxima diaria.",
    "TempMin": "Promedio semanal de la temperatura mínima diaria. Es la que más "
    "correlaciona con el rendimiento, por razones que el estudio examina.",
    "VarDia": "Diferencia entre la máxima y la mínima del día, promediada en la semana.",
    "gdd_semana": "Grados-día de crecimiento acumulados en la semana: mide el desarrollo "
    "que permite la temperatura, no la temperatura en sí. Se calcula como "
    "7 x (temperatura media - 4,4 °C), y no baja de cero.",
    "gdd_acum": "Suma de los grados-día desde la primera semana del año. Es el reloj "
    "fisiológico del cultivo: dos semanas con la misma temperatura pesan "
    "distinto según cuánto desarrollo se acumuló antes.",
    "KgHa": "Kilos cosechados por hectárea en la semana. Es lo que se quiere explicar.",
    "Frutos": "Número medio de frutos por planta esa semana, según la hoja «Kg Reales». "
    "kg/ha ≈ Frutos × Peso × densidad de plantas: junto con «Peso» es la "
    "descomposición biológica del rendimiento, no una variable independiente.",
    "Peso": "Peso medio de un fruto individual esa semana, en gramos. La otra mitad de "
    "la descomposición de kg/ha junto con «Frutos».",
    # Features lagged (modelo XGBoost)
    "DPV_lag": "Promedio móvil del DPV según las semanas seleccionadas en la barra lateral. "
    "Captura el estrés hídrico atmosférico sostenido.",
    "riego_lag": "Promedio móvil del riego (L/planta) según las semanas seleccionadas. "
    "Evalúa el volumen de agua recibido durante el desarrollo o turgencia "
    "del fruto.",
    "Rad_lag": "Promedio móvil de la radiación solar según la ventana elegida. "
    "La fotosíntesis acumulada en el período previo determina la materia "
    "seca y el peso.",
    "ETo_lag": "Promedio móvil de la ETo. Representa la demanda hídrica ambiental acumulada.",
    "gdd_lag": "Promedio móvil del GDD semanal. En esta campaña es casi una transformación "
    "de la temperatura media; no debe leerse como una señal independiente sin "
    "un origen agronómico desde poda.",
    "dias_desde_poda": "Diferencia aproximada entre el punto medio de la semana y la fecha "
    "de poda ponderada por área. Es un reloj biológico proxy, no una fase "
    "fenológica observada.",
    "poda_dispersion_dias": "Días entre la primera y la última poda de los lotes del módulo. "
    "Una dispersión grande significa que una sola fecha de módulo "
    "puede ocultar estados biológicos distintos.",
    "gdd_acum_poda_obs": "Suma de GDD de las semanas con cosecha observadas después de la "
    "poda. No equivale al GDD completo desde poda si faltan semanas o "
    "clima anterior a S01.",
    "flores_promedio": "Conteo real de flores por turno, promediado entre los turnos del "
    "módulo esa semana. Es la primera fase fenológica MEDIDA del "
    "tablero, no un proxy derivado de la fecha de poda. Fuente: hoja "
    "EvFlores de «DAtos mes.xlsx».",
    "flores_dispersion_relativa": "Desvío entre turnos dividido por el promedio. Alta "
    "dispersión significa que el promedio de módulo puede "
    "ocultar turnos con floración muy distinta entre sí — no "
    "hay área por turno en esta hoja para ponderar mejor.",
}

# Configuración elegida por barrido de 108 combinaciones (2026-08-07), midiendo con
# «deja-una-semana-fuera» y reportando con «deja-un-bloque-fuera». Nunca al revés: elegir
# mirando la métrica que se reporta la infla.
#
# Contra la configuración anterior (prof 3, lr 0,03, sin regularización), promediando
# 8 semillas:
#
#     anterior : selección +0,344   honesta −0,116   MAE 757 kg/ha
#     ésta     : selección +0,402   honesta +0,053   MAE 686 kg/ha
#     baseline «predecir la media», partición honesta:  −0,147   MAE 756
#
# La anterior tenía el MAE de predecir el promedio: no medía nada. La mejora sobrevive al
# cambio de semilla con 5,1 desviaciones típicas de margen.
#
# Por qué árboles profundos con aprendizaje muy lento: la profundidad deja capturar
# interacciones entre clima y riego, y el freno viene de `min_child_weight` (ninguna hoja
# con menos de 10 observaciones) y de `reg_lambda`, no de amputar el árbol.
#
# Este barrido se hizo con las 6 variables SIN desfase. FEATURES pasó después a las 5
# variables `*_lag` más GDD (ver `docs/data/resumen_sesion.md` §6), y esta misma
# configuración —sin volver a barrer— ya mejoraba a la anterior en 21 desviaciones
# típicas (+0,204 contra −0,012) sobre el nuevo espacio.
#
# Re-barrido para las 7 variables con desfase (2026-08-07, §7 del resumen de sesión):
# 264 configuraciones (profundidad 3-8, lr 0,01-0,08, n 200-600, min_child_weight 1-20,
# reg_lambda 0-20), elegidas con «por_semana» y evaluadas con «por_bloque». Resultado:
# NINGUNA le gana a la configuración de abajo bajo la partición honesta. El mejor
# candidato por la métrica de selección (prof 7, lr 0,02, n 400) da, con 8 semillas,
# +0,1845 ± 0,0226 — empatado o levemente peor que ésta (+0,2040 ± 0,0102) y más
# inestable entre semillas. Cerrado: esta configuración ya está cerca del óptimo para
# el espacio actual de variables; no hace falta cambiarla.
PARAMS: dict[str, object] = {
    "n_estimators": 300,
    "max_depth": 6,
    "learning_rate": 0.01,
    "min_child_weight": 10,
    "reg_lambda": 5,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "random_state": 0,
    # n_jobs=1 a propósito: con 452 filas el reparto entre hilos cuesta más de lo que
    # ahorra (medido: 17,4 s contra 18,8 s con dos hilos), y además fija el resultado.
    # El paralelismo que sí rinde es entre configuraciones, y lo hace `evaluacion.py`.
    "n_jobs": 1,
}

# Hojas que el Excel de campaña tiene que traer, con sus nombres tal como vienen.
HOJAS: frozenset[str] = frozenset({"KgHa", "Temp Max-Min", "Rad y ET", "Riego", "DPV"})

# Paleta. Azul = por debajo / valor bajo, rojo = por encima / valor alto, gris = totales.
AZUL = "#3B7DD8"
ROJO = "#E8443A"
VERDE = "#7FB069"
GRIS = "#5A6472"
NARANJA = "#D9822B"

# ── Vocabulario de la plataforma analítica ───────────────────────────────────
#
# Aparte de ETIQUETAS/GLOSARIO a propósito. Esos dos describen las variables del panel
# de campaña, y `ui.glosario()` sin argumentos los recorre enteros: si se fusionaran, la
# sección «Qué significa cada variable» de Pregunta y de Datos y calidad se llenaría de
# métricas de backtesting que ahí no vienen al caso. `etiqueta()` y `glosa()` sí consultan
# los dos, para que una tabla de `/analitica/*` se traduzca con la misma función que el
# resto del tablero.
#
# Las columnas que se traducen acá las produce `proyeccion/metricas.py` y
# `proyeccion/torneo.py`. El nombre legible vive junto a quien lo genera: quien añada una
# métrica nueva tiene el glosario en el mismo paquete que está tocando.

ETIQUETAS_ANALITICAS: dict[str, str] = {
    # Proyección
    "fecha_emision": "Emitido el",
    "semana_iso": "Sem",
    # Las dos componentes con que el modelo representa la posición en el año: juntas
    # describen el calendario sin que diciembre y enero queden en extremos opuestos.
    "semana_objetivo_sin": "Momento del año (componente 1)",
    "semana_objetivo_cos": "Momento del año (componente 2)",
    "fecha_objetivo": "Semana de cosecha",
    "horizonte_semanas": "Semanas de anticipación",
    "banda_horizonte": "Uso previsto",
    "p50_kg": "Kilos esperados",
    "p10_kg": "Escenario bajo (kg)",
    "p90_kg": "Escenario alto (kg)",
    "real_kg": "Kilos cosechados",
    "plantas": "Plantas del lote",
    "frutos_por_planta": "Frutos por planta",
    "peso_baya_g": "Peso de baya (g)",
    "probabilidad_cosecha": "Probabilidad de cosecha",
    "kg_condicional": "Kg si ocurre cosecha",
    "factor_asignacion_cosecha": "Factor de calibración de volumen",
    "confianza": "Confianza",
    "rango_relativo": "Ancho del rango (% de lo esperado)",
    "kg_ha": "Rendimiento (kg/ha)",
    "kg_planta": "Kilos por planta",
    "version_fuente": "Versión del pronóstico",
    "campania": "Campaña",
    "empresa": "Empresa",
    "fundo": "Fundo",
    "modulo": "Módulo",
    "lote": "Lote",
    "turno": "Turno de riego",
    "variedad": "Variedad",
    "area_ha": "Área (ha)",
    # Desempeño del pronóstico
    "modelo": "Modelo",
    "wape": "Error de volumen (%)",
    "mase": "Error frente al método simple",
    "rmsse": "Error cuadrático relativo",
    "mae_kg": "Error medio (kg)",
    "sesgo_pct": "Sesgo (%)",
    "cobertura_80": "Aciertos dentro del rango (%)",
    "ancho_intervalo_kg": "Ancho medio del rango (kg)",
    "interval_score_80": "Penalización del rango",
    "pinball_p10": "Calidad del escenario bajo",
    "pinball_p50": "Calidad del valor central",
    "pinball_p90": "Calidad del escenario alto",
    "mae_plantas": "Error en plantas",
    "mae_frutos_por_planta": "Error en frutos por planta",
    "mae_peso_baya_g": "Error en peso de baya (g)",
    "wape_frutos_por_planta": "Error de frutos por planta (%)",
    "wape_peso_baya_g": "Error de peso de baya (%)",
    "sesgo_pct_frutos_por_planta": "Sesgo en frutos por planta (%)",
    "sesgo_pct_peso_baya_g": "Sesgo en peso de baya (%)",
    "mase_frutos_por_planta": "Frutos por planta frente al método simple",
    "mase_peso_baya_g": "Peso de baya frente al método simple",
    "n_frutos_por_planta": "Casos con frutos observados",
    "n_peso_baya_g": "Casos con peso observado",
    "residuo_identidad_pct": "Desvío del producto de componentes (%)",
    "p10_kg_mc": "Escenario bajo por componentes (kg)",
    "p90_kg_mc": "Escenario alto por componentes (kg)",
    "n_parejas_mc": "Casos usados en el diagnóstico",
    "base_plantas_evaluada": "Base de plantas usada",
    "base_plantas": "Base de plantas usada",
    "familia_frutos": "Familia elegida para frutos",
    "familia_peso": "Familia elegida para peso",
    "volumen_real_kg": "Volumen cosechado (kg)",
    "r2": "R² (solo diagnóstico)",
    "n": "Casos comparados",
    # Gobierno del modelo
    "campeon": "Modelo en uso",
    "challenger": "Modelo retador",
    "resultado": "Decisión",
    "justificacion": "Motivo",
    "decidido_en": "Decidido el",
    "decision_mejora_wape": "Mejora del error de volumen",
    "decision_mejora_mase": "Mejora frente al método simple",
    "decision_porcentaje_lotes_ganados": "Lotes donde ganó el retador",
    "decision_diferencia_wape_ic_inferior": "Diferencia de error, extremo favorable",
    "decision_diferencia_wape_ic_superior": "Diferencia de error, extremo desfavorable",
    "decision_cobertura_volumen": "Volumen cubierto por la comparación",
    "decision_campanias_ganadas": "Campañas ganadas",
    "decision_deterioro_fundo_max": "Peor empeoramiento en un fundo",
    # Trazabilidad
    "run_id": "N.º de corrida",
    "tipo": "Tipo de corrida",
    "estado": "Estado",
    "fuente": "Origen de los datos",
    "firma_snapshot": "Huella de los datos",
    "corte_datos": "Datos hasta",
    "codigo_commit": "Versión del código",
    "mlflow_run_id": "Registro en MLflow",
    "inicio": "Inicio",
    "fin": "Fin",
    "artefacto": "Contenido",
    "uri": "Ubicación del archivo",
    "sha256": "Huella del archivo",
    "bytes": "Tamaño (bytes)",
    "creado_en": "Creado el",
    "regla": "Control",
    "observados": "Casos revisados",
    "afectados": "Casos con problema",
    "detalle": "Detalle",
    # Evidencia y literatura
    "claim_id": "Código de la conclusión",
    "hipotesis": "Hipótesis",
    "clase_evidencia": "Tipo de evidencia",
    "afirmacion": "Conclusión",
    "estimacion": "Valor estimado",
    "intervalo_inferior": "Extremo inferior",
    "intervalo_superior": "Extremo superior",
    "n_efectivo": "Muestra efectiva",
    "unidad": "Unidad",
    "supuestos": "Supuestos",
    "limitaciones": "Limitaciones",
    "actualizado_en": "Actualizado el",
    "titulo": "Título",
    "autores": "Autores",
    "anio": "Año",
    "doi": "DOI",
    "url": "Enlace",
    "cultivo_variedad": "Cultivo y variedad",
    "ubicacion": "Lugar del estudio",
    "muestra": "Muestra",
    "metodo": "Método",
    "resultados": "Resultados",
    "transferibilidad": "¿Se puede trasladar acá?",
    "uso_en_plataforma": "Para qué se usa",
    # Barrido de relaciones e importancia de variables
    "hipotesis_id": "Hipótesis",
    "predictor": "Variable",
    "respuesta": "Se relaciona con",
    "rezago_semanas": "Semanas de rezago",
    "pearson": "Correlación",
    "pearson_ic_inferior": "Extremo inferior",
    "pearson_ic_superior": "Extremo superior",
    "p_pearson": "Valor p",
    "spearman": "Correlación por rangos",
    "p_spearman": "Valor p por rangos",
    "correlacion_parcial": "Correlación descontando calendario",
    "p_ajustado_bh": "Valor p corregido",
    "placebo_futuro": "Placebo (serie inventada)",
    "modulos": "Módulos evaluados",
    "estabilidad_signo_modulo": "Estabilidad entre módulos",
    "placebo_supera_estimacion": "El placebo la supera",
    "p_valor": "Valor p",
    "delta_mae": "Diferencia de error",
    "aumento_mae": "Error que añade perderlo",
    "familia": "Grupo de variables",
    "shap_abs_medio": "Peso medio en la predicción",
    "temperatura_base_c": "Temperatura base (°C)",
    # Variables del panel lote-semana. Aparecen dentro del texto de las conclusiones, que
    # el pipeline redacta con el nombre técnico de cada columna.
    "kg": "kilos cosechados",
    "temp_min": "temperatura mínima",
    "temp_max": "temperatura máxima",
    "temp_media": "temperatura media",
    "humedad": "humedad del aire",
    "eto": "demanda de agua (ETo)",
    "radiacion": "radiación solar",
    "lluvia": "lluvia",
    "agua_m3": "agua aplicada (m³)",
    "reposicion_pct": "reposición de riego (%)",
    "ramas_por_planta": "ramas por planta",
    "proporcion_ramas_gruesas": "proporción de ramas gruesas",
    "diametro_rama_mm": "diámetro de rama",
    "brotes_por_planta": "brotes por planta",
    "yemas_por_planta": "yemas por planta",
    "proporcion_yemas_abiertas": "proporción de yemas abiertas",
    "gdd_4_4": "acumulación térmica",
    "dpv_kpa": "sequedad del aire",
    "lamina_mm": "lámina de riego",
    "flores_por_planta_muestra": "flores por planta",
    "tasa_cuajo_observada": "tasa de cuajado",
    "frutos_por_planta_muestra": "frutos por planta",
    "diametro_baya_mm": "diámetro de la baya",
    "peso_real_g": "peso de la baya cosechada",
    "kg_componentes_muestra": "kilos reconstruidos desde plantas, frutos y peso",
    "velocidad_estado": "velocidad de avance fenológico",
    "indice_estado": "avance de maduración",
    "plantas_catalogo": "plantas del maestro",
    "plantas_cosechadas": "plantas cosechadas",
    "prop_e1": "proporción en estado E1",
    "prop_e2": "proporción en estado E2",
    "prop_e3": "proporción en estado E3",
    "prop_e4": "proporción en estado E4",
    "prop_e5": "proporción en estado E5",
    # Packing: lo que se mide en la línea de proceso, al grano de módulo × semana.
    "calibre_medio_mm": "calibre en línea",
    "peso_promedio_g": "peso promedio en línea",
    "proporcion_descarte": "proporción de descarte",
    "defectos_pct": "fruta con defecto (%)",
    "kg_procesados": "kilos procesados en planta",
    "kg_ha_modulo": "rendimiento del módulo",
    "n_cajas": "cajas procesadas",
}

# Qué significa cada término de la plataforma analítica, en lenguaje llano. Redactado para
# alguien que conoce el cultivo y no la estadística: primero qué mide, después cómo se lee,
# y cuando corresponde qué NO permite concluir.
GLOSARIO_ANALITICO: dict[str, str] = {
    # Proyección
    "p50_kg": "Los kilos que el pronóstico considera más probables para ese lote y esa "
    "semana. La mitad de las veces la cosecha real queda por encima y la otra "
    "mitad por debajo.",
    "p10_kg": "Escenario bajo: solo 1 de cada 10 semanas parecidas debería salir por "
    "debajo de este valor. Sirve para comprometerse sin quedar corto, pero no "
    "es un piso garantizado.",
    "p90_kg": "Escenario alto: solo 1 de cada 10 semanas parecidas debería superarlo. "
    "Sirve para dimensionar el peor caso de saturación en packing, no para "
    "prometer volumen.",
    "banda_horizonte": "Para qué sirve el número según cuánta anticipación tiene. "
    "Compromiso son 1 y 2 semanas; planificación, de 3 a 6; escenario, "
    "de 7 a 10 — este último orienta, no compromete.",
    "horizonte_semanas": "Cuántas semanas antes de la cosecha se emitió el pronóstico. "
    "Cuanto mayor es, más ancho el margen.",
    "confianza": "Cuánta historia propia tiene el lote para calibrar su margen. «Media» "
    "significa que hay suficientes semanas pasadas comparables; «baja», que "
    "el margen se apoya en pocos casos y conviene tomarlo con reserva.",
    "rango_relativo": "El ancho entre el escenario bajo y el alto, medido como porcentaje "
    "de lo esperado. Por encima del 50 % el lote es difícil de "
    "comprometer, aunque el valor central sea correcto.",
    "plantas": "Plantas registradas en el maestro del lote. Es el número de catálogo, no "
    "un conteo de plantas productivas esa semana: la diferencia entre ambas "
    "queda incorporada dentro de «frutos por planta».",
    "frutos_por_planta": "Cuántos frutos aporta en promedio cada planta del lote esa "
    "semana. Junto con el peso de baya y el número de plantas "
    "reconstruye los kilos.",
    "peso_baya_g": "Cuánto pesa en promedio un fruto, en gramos. En esta campaña lo "
    "observado va de 1,8 a 7,1 g.",
    "probabilidad_cosecha": "Probabilidad estimada de que el lote tenga cosecha esa "
    "semana. Multiplica el volumen condicional; no es una causa.",
    "kg_condicional": "Volumen previsto si efectivamente ocurre cosecha esa semana, antes "
    "de ponderarlo por la probabilidad de ocurrencia.",
    "factor_asignacion_cosecha": "Corrección de escala aprendida exclusivamente con bloques "
    "temporales anteriores. No es una probabilidad ni una causa; "
    "se publica para reconstruir el p50 y auditar el ajuste de "
    "volumen.",
    # Desempeño del pronóstico
    "wape": "De cada 100 kg cosechados, cuántos erró el pronóstico en total. Es la medida "
    "más directa de si el volumen cuadra. Más bajo es mejor.",
    "mase": "Compara el error del modelo contra el de repetir la semana anterior sin "
    "pensar. Por debajo de 1 el modelo aporta; en 1 o más, no vale más que la "
    "regla simple.",
    "rmsse": "Como el anterior, pero castigando más los errores grandes. Detecta el modelo "
    "que acierta casi siempre y falla mucho de vez en cuando.",
    "mae_kg": "Cuántos kilos se equivoca en promedio cada pronóstico, sin importar si se "
    "pasó o se quedó corto.",
    "sesgo_pct": "Si el modelo se pasa o se queda corto de forma sistemática. Positivo "
    "significa que promete más kilos de los que llegan; negativo, que "
    "subestima. Un sesgo cercano a cero es lo deseable.",
    "cobertura_80": "De cada 100 semanas, en cuántas la cosecha real cayó dentro del "
    "rango anunciado. Debería rondar 80: mucho menos significa que el "
    "rango miente, mucho más que es tan ancho que no informa.",
    "ancho_intervalo_kg": "Cuántos kilos separan el escenario bajo del alto. Un rango "
    "angosto solo es bueno si además acierta.",
    "interval_score_80": "Nota conjunta del rango: penaliza a la vez ser demasiado ancho "
    "y dejar fuera la cosecha real. Más bajo es mejor.",
    "pinball_p10": "Qué tan bien calibrado está el escenario bajo. Más bajo es mejor.",
    "pinball_p50": "Qué tan bien calibrado está el valor central. Más bajo es mejor.",
    "pinball_p90": "Qué tan bien calibrado está el escenario alto. Más bajo es mejor.",
    "mae_frutos_por_planta": "Cuántos frutos por planta se equivoca en promedio. Con un "
    "promedio cercano a 57 frutos por planta, un error de 20 es "
    "grande.",
    "mae_peso_baya_g": "Cuántos gramos se equivoca en promedio al estimar el peso de un fruto.",
    "mae_plantas": "Cuántas plantas se equivoca en promedio respecto de las que "
    "efectivamente se cosecharon.",
    "sesgo_pct_frutos_por_planta": "Si el modelo estima de más o de menos los frutos por "
    "planta de forma sistemática. Importa incluso cuando los "
    "kilos totales cuadran: un exceso de frutos compensado por "
    "un peso subestimado da el total correcto por la razón "
    "equivocada.",
    "sesgo_pct_peso_baya_g": "Si el modelo estima de más o de menos el peso del fruto de "
    "forma sistemática. Se lee junto al sesgo de frutos por planta: "
    "dos sesgos de signo contrario se anulan en el total.",
    "residuo_identidad_pct": "Cuánto se aparta el kilaje mostrado del producto de sus tres "
    "piezas. Debe ser prácticamente cero; si no lo es, los "
    "componentes que se muestran no son los que produjeron el "
    "número.",
    "base_plantas": "Sobre qué número de plantas está calculado «frutos por planta»: las del "
    "maestro del lote (catálogo) o las que efectivamente se cosecharon. Es "
    "necesario declararlo porque las dos cifras difieren y la comparación "
    "solo tiene sentido contra la misma base.",
    "r2": "Qué parte de la variación explica el modelo. Se muestra solo como diagnóstico: "
    "un R² alto no demuestra que sirva para pronosticar hacia adelante, porque se "
    "puede conseguir aprendiéndose el pasado.",
    "n": "Cuántos casos entraron en la comparación. Una diferencia calculada sobre pocos "
    "casos no es comparable con una calculada sobre miles.",
    # Gobierno del modelo
    "campeon": "El modelo que hoy produce los números oficiales de la plataforma.",
    "challenger": "El modelo que compitió contra el actual en esta comparación. Ser "
    "retador no significa ser mejor: significa haber sido evaluado.",
    "resultado": "Qué se decidió tras comparar. «Retener» mantiene el modelo actual; "
    "«promover» lo reemplaza; «experimental» lo deja disponible sin "
    "usarlo para decidir.",
    "decision_mejora_wape": "Cuánto redujo el retador el error de volumen frente al modelo "
    "en uso. Una mejora sola no basta para reemplazarlo.",
    "decision_diferencia_wape_ic_inferior": "Extremo favorable del margen de esa mejora. "
    "Si el margen cruza el cero, la ventaja puede "
    "ser casualidad de esta muestra.",
    "decision_diferencia_wape_ic_superior": "Extremo desfavorable del margen de esa "
    "mejora. Junto con el anterior define si la "
    "ventaja está resuelta o no.",
    "decision_porcentaje_lotes_ganados": "En qué porcentaje de lotes el retador acertó "
    "mejor. Un promedio bueno con pocos lotes ganados "
    "indica que la ventaja viene de unos pocos casos.",
    "decision_cobertura_volumen": "Qué parte del volumen total entró en la comparación. "
    "Un modelo que solo cubre un rincón del fundo no puede "
    "reemplazar al que cubre todo.",
    "decision_campanias_ganadas": "En cuántas campañas distintas ganó el retador. Ganar en "
    "una sola puede ser una particularidad de ese año.",
    "decision_deterioro_fundo_max": "Cuánto empeoró en el fundo donde peor le fue. Una "
    "mejora promedio que arruina un fundo concreto no se "
    "promueve.",
    # Trazabilidad
    "run_id": "Número que identifica una ejecución completa del análisis. Sirve para "
    "volver exactamente a los mismos números meses después.",
    "tipo": "Qué hizo esa ejecución: buscar relaciones, comparar modelos, entrenar, "
    "proyectar o exportar el paquete de auditoría.",
    "firma_snapshot": "Huella digital de los datos con los que se corrió. Si dos "
    "ejecuciones tienen la misma huella, partieron exactamente de los "
    "mismos datos.",
    "corte_datos": "Hasta qué momento se consideraron los datos. Nada posterior a esta "
    "fecha entró en el cálculo.",
    "codigo_commit": "Versión exacta del código con la que se produjeron estos números.",
    "sha256": "Huella digital del archivo. Permite comprobar que no fue alterado después "
    "de generarse.",
    "regla": "Control automático que se ejecuta sobre los datos y los resultados. Cada uno "
    "revisa una condición concreta y avisa si no se cumple.",
    # Evidencia
    "clase_evidencia": "Hasta dónde llega lo que permite afirmar ese resultado: describir, "
    "asociar, ordenar en el tiempo, predecir o atribuir causa. Solo la "
    "última implica que actuar sobre la variable cambie el resultado.",
    "n_efectivo": "Cuántas observaciones realmente independientes respaldan el resultado. "
    "Es menor que el número de filas: si el clima es el mismo para varios "
    "módulos de una semana, esa semana cuenta una vez, no una por módulo.",
    "estimacion": "El valor central de la relación encontrada, con su margen al lado. Si "
    "el margen cruza el cero, la relación no está resuelta.",
    "transferibilidad": "Si los números de ese estudio se pueden trasladar a este cultivo "
    "y esta zona. Casi siempre la respuesta es que sirve la hipótesis, "
    "no el coeficiente.",
}

# Cómo se traduce cada valor codificado que llega de la base de datos. Sin esto la interfaz
# muestra los enums de PostgreSQL en inglés, que no significan nada para quien la usa.
VALORES_ANALITICOS: dict[str, dict[str, str]] = {
    "tipo": {
        "relations": "Búsqueda de relaciones",
        "backtest": "Comparación de modelos",
        "train": "Entrenamiento",
        "project": "Proyección",
        "export": "Paquete de auditoría",
    },
    "estado": {
        "created": "Creada",
        "running": "En curso",
        "succeeded": "Terminada bien",
        "failed": "Terminada con error",
        "published": "Publicada",
        "ok": "Sin problemas",
        "warning": "Con advertencias",
        "error": "Con errores",
        "exploratorio": "Exploratorio",
        # «Consistente» sustituye a «replicado»: el análisis comprueba consistencia interna,
        # nunca replicación en otra campaña. La etiqueta vieja se conserva para poder leer
        # lo publicado antes del cambio.
        "consistente": "Consistente",
        "replicado": "Consistente (etiqueta antigua)",
        "predictivo": "Predictivo",
        "causal": "Causal",
    },
    "banda_horizonte": {
        "operativo": "Compromiso (1–2 semanas)",
        "planificacion": "Planificación (3–6 semanas)",
        "escenario": "Escenario (7–10 semanas)",
    },
    "resultado": {
        "retener": "Se mantiene el modelo actual",
        "promover": "Reemplaza al modelo actual",
        "experimental": "Disponible, no se usa para decidir",
    },
    "clase_evidencia": {
        "descriptiva": "Descriptiva",
        "correlacional": "Asociación",
        "temporal": "Orden temporal",
        "predictiva": "Predictiva",
        "causal": "Causal",
    },
    "confianza": {"alta": "Alta", "media": "Media", "baja": "Baja"},
    "fuente": {"postgres": "PostgreSQL", "excel": "Excel (respaldo)", "fixture": "Datos de prueba"},
    # Los identificadores de control son nombres de función, no frases. Se traducen a lo que
    # el control verifica, en voz activa, para que la tabla de calidad se pueda leer.
    "regla": {
        "fuente_principal_postgres": "Los datos vienen de la base y no del respaldo",
        "versiones_r09_parseables": "Todas las versiones del pronóstico se pudieron interpretar",
        "versiones_r09_oficiales_parseables": "Las versiones oficiales se pudieron interpretar",
        "escenarios_r09_excluidos_del_oficial": (
            "Los escenarios quedaron fuera del pronóstico oficial"
        ),
        "sin_observaciones_posteriores_a_emision": (
            "Ningún dato posterior a la emisión entró al cálculo"
        ),
        "orden_p10_p50_p90": "El escenario bajo nunca supera al alto",
        "clave_prediccion_unica": "No hay dos pronósticos para el mismo lote y semana",
        "suma_lote_igual_modulo": "Los lotes suman exactamente su módulo",
        "suma_modulo_igual_fundo": "Los módulos suman exactamente su fundo",
        "suma_fundo_igual_empresa": "Los fundos suman exactamente la empresa",
        "identidad_kg_reconstruye_componentes": "Los kilos coinciden con plantas × frutos × peso",
        "componentes_no_negativos": "Ninguna pieza del rendimiento es negativa",
        "peso_baya_g_dentro_del_rango_observado": "El peso previsto cae dentro de lo observado",
        "frutos_por_planta_dentro_del_rango_observado": (
            "Los frutos previstos caen dentro de lo observado"
        ),
        "calendario_cosecha_heredado_de_r09": "El calendario de cosecha se hereda, no se predice",
        "base_plantas_declarada": "Cada fila declara sobre qué plantas está calculada",
        "monitoreo_reales_disponibles": "Llegada de cosecha real para comparar",
        "monitoreo_cobertura_p10_p90": "La cosecha real cae dentro del margen anunciado",
        "monitoreo_deriva_variables_psi": "Las variables no se han desviado de lo entrenado",
        "monitoreo_lotes_fuera_rango_entrenamiento": "Lotes fuera del rango con que se entrenó",
        "monitoreo_degradacion_campania_horizonte": "El error no empeora por campaña ni por plazo",
        "predicciones_no_vacias": "La corrida produjo predicciones",
        "componentes_declarados_completos": "Las tres piezas del rendimiento están completas",
    },
    # Los identificadores de modelo son los que viajan a `analytics.prediction` y no deben
    # cambiar; lo que se traduce es cómo se muestran. Los métodos de serie llevan entre
    # paréntesis qué hacen, porque su nombre técnico no lo dice.
    "modelo": {
        "R09_publicado": "Proyección del equipo",
        "R09_corregido_sesgo": "Proyección del equipo, corregida por sesgo",
        "R09_componentes_publicados": "Proyección del equipo, rearmada desde sus piezas",
        "Fenologico_componentes": "Piezas publicadas por la proyección del equipo",
        "Componentes_identidad": "Modelo por piezas (frutos y peso)",
        "HibridoEstadoOleadas_v1": "Proyección del equipo, ajustada por estado y oleadas",
        "HibridoGaussEstado_v1": (
            "Challenger R09 + forma Gaussiana + estado reciente (experimental)"
        ),
        "Random_Forest": "Random Forest",
        "XGBoost": "XGBoost",
        "Ridge": "Ridge (corrección lineal)",
        "Combinacion_ponderada": "Combinación de modelos",
        "Naive": "Repetir la semana anterior",
        "SeasonalNaive": "Repetir la misma semana del año pasado",
        "HistoricAverage": "Promedio histórico",
        "CrostonClassic": "Croston (cosecha intermitente)",
        "ADIDA": "ADIDA (cosecha intermitente)",
        "AutoETS": "Suavizado exponencial automático",
        "AutoARIMA": "ARIMA automático",
    },
}
# El modelo aparece con tres nombres de columna distintos según la tabla.
VALORES_ANALITICOS["campeon"] = VALORES_ANALITICOS["modelo"]
VALORES_ANALITICOS["challenger"] = VALORES_ANALITICOS["modelo"]

# Cómo se escribe cada número. `miles0` usa punto de millar (la convención del fundo).
# Ojo con las dos escalas de porcentaje, comprobadas contra `analytics.metric` de la
# corrida 20: `wape`, `cobertura_80` y las `decision_*` llegan como fracción (0–1) y hay
# que multiplicarlas por 100 (`pct_frac`), mientras que `sesgo_pct` ya viene en puntos
# porcentuales (−88 a 49) y volver a multiplicarla daría un número absurdo (`pct_pp`).
FORMATO_ANALITICO: dict[str, str] = {
    "p50_kg": "miles0",
    "p10_kg": "miles0",
    "p90_kg": "miles0",
    "real_kg": "miles0",
    "mae_kg": "miles0",
    "ancho_intervalo_kg": "miles0",
    "volumen_real_kg": "miles0",
    "interval_score_80": "miles0",
    "bytes": "miles0",
    "plantas": "miles0",
    "kg_condicional": "miles0",
    "probabilidad_cosecha": "pct_frac",
    "kg_ha": "miles0",
    "n": "miles0",
    "n_efectivo": "miles0",
    "observados": "miles0",
    "afectados": "miles0",
    "horizonte_semanas": "miles0",
    "run_id": "entero",
    "anio": "entero",
    "uri": "archivo",
    "semana_iso": "entero",
    "wape": "pct_frac",
    "cobertura_80": "pct_frac",
    "rango_relativo": "pct_frac",
    "decision_mejora_wape": "pct_frac",
    "decision_mejora_mase": "pct_frac",
    "decision_porcentaje_lotes_ganados": "pct_frac",
    "decision_cobertura_volumen": "pct_frac",
    "decision_deterioro_fundo_max": "pct_frac",
    "sesgo_pct": "pct_pp",
    "mase": "dec2",
    "rmsse": "dec2",
    "r2": "dec2",
    "frutos_por_planta": "dec1",
    "peso_baya_g": "dec2",
    "kg_planta": "dec2",
    "area_ha": "dec2",
    "mae_frutos_por_planta": "dec2",
    "mae_peso_baya_g": "dec3",
    "mae_plantas": "dec1",
    "wape_frutos_por_planta": "pct_frac",
    "wape_peso_baya_g": "pct_frac",
    "sesgo_pct_frutos_por_planta": "pct_pp",
    "sesgo_pct_peso_baya_g": "pct_pp",
    "mase_frutos_por_planta": "dec2",
    "mase_peso_baya_g": "dec2",
    "n_frutos_por_planta": "miles0",
    "n_peso_baya_g": "miles0",
    "residuo_identidad_pct": "pct_pp",
    "p10_kg_mc": "miles0",
    "p90_kg_mc": "miles0",
    "n_parejas_mc": "miles0",
    "pinball_p10": "dec2",
    "pinball_p50": "dec2",
    "pinball_p90": "dec2",
    "estimacion": "signo3",
    "pearson": "signo3",
    "pearson_ic_inferior": "signo3",
    "pearson_ic_superior": "signo3",
    "spearman": "signo3",
    "correlacion_parcial": "signo3",
    "placebo_futuro": "signo3",
    "p_pearson": "dec3",
    "p_spearman": "dec3",
    "p_ajustado_bh": "dec3",
    "p_valor": "dec3",
    "estabilidad_signo_modulo": "pct_frac",
    "rezago_semanas": "entero",
    "modulos": "entero",
    "aumento_mae": "miles0",
    "delta_mae": "miles0",
    "shap_abs_medio": "miles0",
    "intervalo_inferior": "signo3",
    "intervalo_superior": "signo3",
    "decision_diferencia_wape_ic_inferior": "signo3",
    "decision_diferencia_wape_ic_superior": "signo3",
}


def etiqueta(col: str) -> str:
    """Nombre legible de una columna; si no está en ningún diccionario, el nombre crudo."""
    return ETIQUETAS.get(col) or ETIQUETAS_ANALITICAS.get(col, col)


def glosa(col: str) -> str | None:
    """Explicación en lenguaje llano de una variable o de un término analítico."""
    return GLOSARIO.get(col) or GLOSARIO_ANALITICO.get(col)
