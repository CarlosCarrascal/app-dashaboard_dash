from __future__ import annotations

import dash
from dash import html

from analitica.config import VALORES_ANALITICOS
from components import ui
from pages.analitica._comun import datos, estado_fuente, frase_legible, panel_glosario

dash.register_page(
    __name__,
    path="/analitica/descubrimientos",
    name="Descubrimientos",
    order=2,
    grupo="Plataforma analítica",
)

# Qué se puede hacer con una conclusión según hasta dónde llegó su comprobación. Es lo que
# convierte la etiqueta técnica en una instrucción de uso.
ALCANCE = {
    "exploratorio": "Es una pista, no un resultado. Sirve para decidir qué mirar la próxima "
    "campaña; no para cambiar el manejo.",
    "consistente": "Resiste los filtros del propio análisis: corrección por multiplicidad, "
    "placebo de calendario, signo estable entre módulos y concordancia con "
    "el modelo mixto. **No se ha comprobado en otra campaña ni de forma "
    "prospectiva**, así que sigue siendo una asociación observada sobre los "
    "datos que ya existían.",
    # Etiqueta anterior, conservada para leer conclusiones guardadas antes del cambio. Su
    # texto decía «se repitió en condiciones distintas», que el análisis nunca verificó.
    "replicado": "Etiqueta antigua, hoy en desuso. Equivale a «consistente»: resiste los "
    "filtros internos del análisis, sin comprobación en otra campaña.",
    "predictivo": "Aporta al pronóstico: usarla mejora la anticipación de la cosecha. Eso no "
    "implica que actuar sobre ella cambie el resultado.",
    "causal": "Respaldada por un diseño que permite atribuir causa. Es la única categoría "
    "que justifica cambiar una práctica esperando un efecto.",
}


def _tarjeta(fila) -> html.Div:
    estado_claim = str(fila.estado)
    tono = "ok" if estado_claim in ("consistente", "replicado", "predictivo", "causal") else "aviso"
    clase = VALORES_ANALITICOS["clase_evidencia"].get(fila.clase_evidencia, fila.clase_evidencia)
    muestra = fila.n_efectivo
    detalle = [
        ui.semaforo(tono, frase_legible(fila.afirmacion)),
        ui.parrafo(f"**Hasta dónde llega.** {ALCANCE.get(estado_claim, estado_claim)}"),
    ]
    if muestra:
        detalle.append(
            ui.parrafo(
                f"**Sobre cuánta información se apoya.** {int(muestra)} observaciones "
                "realmente independientes. No es el número de filas: cuando el clima es "
                "común a varios módulos de una misma semana, esa semana cuenta una sola vez."
            )
        )
    if list(fila.supuestos or []):
        detalle.append(
            ui.plegable(
                "Qué se dio por supuesto y qué queda fuera",
                ui.parrafo(frase_legible("**Se supuso que:** " + "; ".join(fila.supuestos) + ".")),
                ui.parrafo(
                    frase_legible("**No cubre:** " + "; ".join(fila.limitaciones or ["—"]) + ".")
                ),
            )
        )
    return ui.panel(
        f"{fila.hipotesis}" if getattr(fila, "hipotesis", None) else str(fila.claim_id),
        *detalle,
        ayuda=f"Tipo de evidencia: {clase.lower()}. Código de la conclusión: {fila.claim_id}.",
    )


def layout():
    estado = datos()
    claims = estado["claims"]
    tarjetas = [_tarjeta(f) for f in claims.itertuples(index=False)]
    if not tarjetas:
        tarjetas = [
            ui.semaforo(
                "aviso",
                "Todavía no hay conclusiones publicadas. Aparecen acá automáticamente cuando "
                "una hipótesis pasa las comprobaciones de la página de relaciones.",
            )
        ]
    return html.Div(
        className="space-y-4",
        children=[
            ui.encabezado_pagina(
                "Lo que se puede afirmar hoy",
                "Cada conclusión con el alcance real de lo que permite decidir. Se generan "
                "desde los resultados guardados, no se redactan a mano.",
            ),
            estado_fuente(estado),
            ui.semaforo(
                "info",
                "**Por qué cada conclusión viene con una etiqueta de alcance.** La diferencia "
                "entre «esto se mueve junto a la cosecha» y «cambiar esto cambia la cosecha» "
                "es la que separa un dato interesante de una decisión de manejo. Confundirlas "
                "es la forma más cara de equivocarse, así que ninguna conclusión se publica "
                "sin decir hasta dónde llega su respaldo.",
            ),
            *tarjetas,
            panel_glosario(["clase_evidencia", "n_efectivo", "estimacion"]),
        ],
    )
