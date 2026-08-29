"""Vocabulario fijo de la página de relaciones.

Todo lo que es texto escrito a mano vive acá, separado del código que lo coloca. Así una
corrección de redacción no obliga a leer lógica, y se ve de un vistazo qué se está
afirmando en pantalla.
"""

from __future__ import annotations

# La unidad real la fija el predictor, no el panel del que sale. Un cruce climático que
# aparece en el panel de lotes sigue teniendo una sola estación detrás: sus observaciones
# independientes son semanas, no lotes, por mucho que la tabla traiga una fila por lote.
CLIMA = frozenset(
    {
        "temp_min",
        "temp_max",
        "temp_media",
        "humedad",
        "dpv_kpa",
        "eto",
        "radiacion",
        "lluvia",
        "gdd_4_4",
        "gdd_0",
        "gdd_7",
        "gdd_8",
    }
)
RIEGO = frozenset({"lamina_mm", "agua_m3", "reposicion_pct"})

# Qué mide cada objetivo, en qué unidad viene y a qué parte del rendimiento pertenece.
OBJETIVOS = {
    "frutos_por_planta_muestra": ("frutos por planta", "frutos", "frutos"),
    "flores_por_planta_muestra": ("flores por planta", "flores", "frutos"),
    "tasa_cuajo_observada": ("cuajado", "", "frutos"),
    "velocidad_estado": ("velocidad de maduración", "", "frutos"),
    # Unidad «puntos» a secas: con «puntos de avance» la frase salía «0,28 puntos de avance
    # más de avance de maduración».
    "indice_estado": ("avance de maduración", "puntos", "frutos"),
    "peso_real_g": ("peso del fruto", "g", "peso"),
    "diametro_baya_mm": ("diámetro de la baya", "mm", "peso"),
    "calibre_medio_mm": ("calibre en línea", "mm", "peso"),
    "proporcion_descarte": ("descarte", "%", "perdida"),
    "kg_ha": ("rendimiento", "kg/ha", "kilos"),
    "kg_ha_modulo": ("rendimiento del módulo", "kg/ha", "kilos"),
    "kg": ("kilos del lote", "kg", "kilos"),
}

GRUPOS_OBJETIVO = {
    "frutos": (
        "Cuántos frutos hay",
        "Todo lo que ocurre antes de que el fruto exista. Si acá se pierde carga, no "
        "se recupera después.",
    ),
    "peso": (
        "Cuánto pesa cada fruto",
        "Lo que ocurre mientras el fruto engorda. Un fruto que no engordó no se arregla "
        "teniendo más frutos.",
    ),
    "perdida": ("Cuánto se pierde", "Fruta que se cosecha y no llega a exportarse."),
    "kilos": (
        "El resultado final",
        "Los kilos son el producto de los anteriores, así que lo que aparece acá suele "
        "reflejar lo que ya se vio arriba.",
    ),
}

# Cada gráfico agrupa respuestas que comparten unidad. Mezclarlas en un solo eje obligaría a
# normalizar, y normalizar por la mediana hace estallar al descarte —su mediana es 0,3 %—
# hasta ocupar la escala entera con una variable que en kilos casi no mueve la aguja.
BLOQUES_GRAFICO = [
    (
        ["kg_ha", "kg_ha_modulo", "kg"],
        "kg/ha",
        1.0,
        "#0f766e",
        "Lo que mueve los kilos",
        "El resultado del negocio. Cada barra son los kilos por hectárea de diferencia entre "
        "un cuarto bajo y un cuarto alto de esa variable.",
    ),
    (
        ["peso_real_g"],
        "gramos por fruto",
        1.0,
        "#b45309",
        "Lo que mueve el peso del fruto",
        "La mitad del rendimiento que no depende de cuántos frutos hay. El fruto medio pesa "
        "unos 3,3 g, así que medio gramo ya es un 15 %.",
    ),
    (
        ["proporcion_descarte"],
        "puntos de descarte",
        100.0,
        "#be123c",
        "Lo que mueve la pérdida por calidad",
        "Fruta cosechada que no llega a exportarse. Parte de un 0,3 % habitual: dos puntos más "
        "es multiplicar la pérdida por siete.",
    ),
]

# ── Cómo no leer mal los números ─────────────────────────────────────────────
#
# Casos reales de la propia tabla. Un coeficiente alto con efecto nulo es la mejor prueba de
# por qué esta página no se queda en las correlaciones.
# Formato: (qué dice el número, por qué engaña, qué hacer con eso). Tres frases cortas, no
# tres párrafos: el lector llega acá después de cinco gráficos y ya no le queda paciencia.
LECCIONES = [
    (
        "Lluvia → descarte: correlación 0,41, efecto cero",
        "En la costa casi nunca llueve: el cuarto seco y el lluvioso son el mismo milímetro.",
        "Por eso los gráficos muestran kilos y gramos, no coeficientes.",
    ),
    (
        "Más flores acompaña a menos frutos, no a más",
        "Puede ser competencia dentro de la planta, o que flores y frutos no se cuenten "
        "sobre las mismas plantas.",
        "No hay dato para distinguirlo. Lo resolvería un ensayo dirigido.",
    ),
    (
        "Más riego acompaña a más kilos, y eso no prueba nada",
        "El riego no se asigna al azar: se riega más donde hay más carga que sostener.",
        "No sirve para orientar cuánto regar. Haría falta asignar láminas a propósito.",
    ),
]

# ── Qué falta medir ──────────────────────────────────────────────────────────
#
# El cierre natural de esta página: las limitaciones que expone arriba son, leídas al
# derecho, una lista priorizada de dónde invertir en medición.
# Formato: (qué hacer, cómo está hoy, qué desbloquea). Va en tabla, así que cada celda es
# una frase: leer cinco párrafos al final de la página no lo hace nadie.
MEDICION = [
    (
        "Estaciones meteorológicas por fundo",
        "Una sola para los cinco: el clima no varía entre lotes de la misma semana.",
        "Multiplica la información climática real sin tocar el análisis.",
    ),
    (
        "Censo de bayas semanal",
        "2 fechas en total sobre 36 lotes. El diámetro no sostiene ninguna serie.",
        "Vuelve el peso predecible con antelación, no solo explicable después.",
    ),
    (
        "Registrar nutrición y sanidad",
        "No existe registro de fertilización ni de aplicaciones.",
        "Explicaría parte de lo que hoy queda como ruido en todos los modelos.",
    ),
    (
        "Cargar la pérdida en campo",
        "564 t enterradas en 2025 —el 6,6 %— medidas en el Access y ausentes de la base.",
        "Permite preguntar por qué un lote entierra el 15 % y otro el 2 %.",
    ),
    (
        "Ensayos con tratamientos asignados",
        "El manejo responde al estado del cultivo, así que nada de esta página prueba causa.",
        "Único camino a afirmaciones causales. Sin él, todo queda en anticipar.",
    ),
]

# ── Inventario de lo que se mide ─────────────────────────────────────────────
INVENTARIO_VARIABLES = [
    (
        "Ciclo de la planta",
        "Poda",
        "relacion",
        "Fecha en que se podó cada lote. El punto de partida desde el que se cuenta todo.",
    ),
    (
        "Ciclo de la planta",
        "Ramas",
        "relacion",
        "Cuántas ramas tiene la planta y qué proporción supera los 5 mm.",
    ),
    (
        "Ciclo de la planta",
        "Brotes",
        "relacion",
        "Brotes por planta. Solo 2 evaluaciones por lote: insuficiente para desfases.",
    ),
    (
        "Ciclo de la planta",
        "Yemas abiertas y por abrir",
        "relacion",
        "Se cuentan junto con las flores. Una yema por abrir es una flor futura.",
    ),
    (
        "Ciclo de la planta",
        "Flores",
        "relacion",
        "Flores por planta. La primera señal medida de la carga que viene.",
    ),
    ("Ciclo de la planta", "Cuajado", "relacion", "Qué proporción de flores llegó a fruto."),
    (
        "Ciclo de la planta",
        "Estados E1 a E5",
        "relacion",
        "Cómo se reparten los frutos entre los cinco estados de maduración.",
    ),
    (
        "Ciclo de la planta",
        "Diámetro de baya en campo",
        "relacion",
        "Solo 2 fechas y 36 lotes. Prácticamente inutilizable para series.",
    ),
    (
        "Ciclo de la planta",
        "Grado de desarrollo del brote",
        "sin_dato",
        "Las columnas existen pero llegan vacías: 240 valores de 3.385 registros.",
    ),
    (
        "Fruto en planta",
        "Calibre en línea",
        "modelo",
        "Medido en packing con 3 campañas. La mejor medición del tamaño de fruto.",
    ),
    (
        "Fruto en planta",
        "Descarte y acidez",
        "relacion",
        "Pérdida por calidad, medida en planta. No incluye lo que se entierra en campo.",
    ),
    (
        "Piezas del rendimiento",
        "Plantas del lote",
        "modelo",
        "Del maestro. No cambian dentro de la campaña.",
    ),
    ("Piezas del rendimiento", "Frutos por planta", "modelo", "Se estima con su propio modelo."),
    (
        "Piezas del rendimiento",
        "Peso de baya",
        "modelo",
        "Se estima con su propio modelo, aparte de los frutos.",
    ),
    (
        "Condiciones externas",
        "Temperatura, humedad, radiación",
        "relacion",
        "Una sola estación para los 5 fundos: no varía entre lotes de una misma semana.",
    ),
    (
        "Condiciones externas",
        "Acumulación térmica (GDD)",
        "relacion",
        "Desarrollo que permite la temperatura, acumulado desde la poda.",
    ),
    (
        "Condiciones externas",
        "Sequedad del aire y demanda de agua",
        "relacion",
        "DPV y ETo, derivados de la misma estación.",
    ),
    (
        "Condiciones externas",
        "Riego aplicado",
        "relacion",
        "Agua entregada por turno, con su lámina y su reposición. Es por módulo.",
    ),
    (
        "Condiciones externas",
        "Nutrición",
        "sin_dato",
        "No existe registro de fertilización en ninguna tabla.",
    ),
    (
        "Condiciones externas",
        "Polinización",
        "sin_dato",
        "No se registra actividad de colmenas ni polinizadores.",
    ),
    ("Condiciones externas", "Suelo", "sin_dato", "Sin análisis ni humedad de suelo cargados."),
    (
        "Condiciones externas",
        "Sanidad",
        "sin_dato",
        "Plagas, enfermedades y aplicaciones no se registran.",
    ),
    (
        "Condiciones externas",
        "Pérdida en campo",
        "sin_dato",
        "El entierro de fruta existe en el Access de 2025 pero no está cargado: son 564 t, "
        "un 6,6 % de lo cosechado.",
    ),
    (
        "Condiciones externas",
        "Pronóstico del tiempo",
        "sin_dato",
        "Solo hay clima observado. Sin pronóstico futuro no se puede proyectar.",
    ),
]

ESTADOS_VARIABLE = {
    "modelo": "Entra al modelo",
    "relacion": "Se cruza en el análisis",
    "sin_usar": "Se mide, no se usa",
    "sin_dato": "No se registra",
}

# Grupos de variables del modelo de pronóstico, con lo que contiene cada uno.
FAMILIAS = {
    "estructura_productiva": (
        "Estructura productiva",
        "Las plantas del lote, los frutos por planta y el peso de la baya: las tres piezas "
        "que multiplicadas dan los kilos.",
    ),
    "volumen_r09": (
        "Volumen de la proyección del equipo",
        "El kilaje que ya publicaba la proyección semanal.",
    ),
    "calendario": ("Calendario", "En qué momento del año cae la semana."),
    "horizonte": ("Anticipación", "Cuántas semanas antes de la cosecha se emitió."),
    "clima": ("Clima", "Temperatura, humedad, radiación y evapotranspiración."),
    "riego": ("Riego", "Agua aplicada y su relación con la demanda del ambiente."),
    "fenologia": ("Fenología", "Flores, cuajado y avance por los estados E1 a E5."),
}
