"""Contratos canónicos entre PostgreSQL/Excel, cálculo y presentación."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd


@dataclass(frozen=True)
class FuenteInfo:
    nombre: str
    firma: str
    corte: datetime | None
    fallback: bool = False
    advertencias: tuple[str, ...] = ()
    conteos: dict[str, int] = field(default_factory=dict)
    # Identificador del snapshot físico de Access cuando PostgreSQL pudo vincularlo con
    # seguridad. Es opcional para conservar compatibilidad con Excel y con snapshots antiguos.
    source_snapshot_id: int | None = None


@dataclass
class DatosProyeccion:
    """Tablas mínimas para reproducir backtest, relaciones y proyección."""

    fuente: FuenteInfo
    forecast: pd.DataFrame
    cosecha: pd.DataFrame
    forecast_campania: pd.DataFrame = field(default_factory=pd.DataFrame)
    flores: pd.DataFrame = field(default_factory=pd.DataFrame)
    estados: pd.DataFrame = field(default_factory=pd.DataFrame)
    bayas: pd.DataFrame = field(default_factory=pd.DataFrame)
    # Censos anteriores a la floración: el arranque del ciclo.
    brotes: pd.DataFrame = field(default_factory=pd.DataFrame)
    ramas: pd.DataFrame = field(default_factory=pd.DataFrame)
    # Calibre real medido en línea, al grano de módulo.
    packing: pd.DataFrame = field(default_factory=pd.DataFrame)
    poda: pd.DataFrame = field(default_factory=pd.DataFrame)
    clima: pd.DataFrame = field(default_factory=pd.DataFrame)
    riego: pd.DataFrame = field(default_factory=pd.DataFrame)
    lotes: pd.DataFrame = field(default_factory=pd.DataFrame)
    # Parámetros legacy manuales, solo si se cargan mediante un adaptador explícito. No
    # forman parte de la extracción Access estándar ni se usan como fallback silencioso.
    parametros_legacy: pd.DataFrame = field(default_factory=pd.DataFrame)


@dataclass
class ResultadoTorneo:
    predicciones: pd.DataFrame
    metricas: pd.DataFrame
    decisiones: pd.DataFrame
    advertencias: list[str] = field(default_factory=list)
    evidencia_features: pd.DataFrame = field(default_factory=pd.DataFrame)


COLUMNAS_BACKTEST = (
    "campania",
    "lote_id",
    "lote",
    "fundo",
    "modulo",
    "fecha_emision",
    "fecha_objetivo",
    "horizonte_semanas",
    "banda_horizonte",
    "version_fuente",
    "modelo",
    "p10_kg",
    "p50_kg",
    "p90_kg",
    "real_kg",
)


# Las tres piezas del rendimiento. No entran en `COLUMNAS_BACKTEST` a propósito: no todas
# las familias las publican, y exigirlas obligaría a inventarlas donde no existen.
COLUMNAS_COMPONENTES = (
    "plantas",
    "frutos_por_planta",
    "peso_baya_g",
)

# Series observadas contra las que se evalúa cada pieza. Hay dos bases de plantas porque el
# maestro se conoce siempre al emitir y la cosecha solo después; en esta operación coinciden
# —el número de plantas de un lote no cambia dentro de la campaña— pero se conservan
# separadas para que la métrica pueda declarar contra cuál compara.
COLUMNAS_COMPONENTES_REALES = (
    "peso_real_g",
    "plantas_reales",
    "frutos_reales_por_planta",
    "frutos_reales_por_planta_catalogo",
)

# Techo de peso de baya. Fijado con lo observado en `stg.v_h01_cosecha` el 2026-08-19
# (30.616 registros, rango 1,79–7,14 g) y redondeado al alza con margen. No es una constante
# biológica: si aparece una variedad de calibre mayor hay que revisarlo con la consulta, no
# subirlo a ojo.
LIMITE_PESO_BAYA_G = 15.0


def validar_backtest(tabla: pd.DataFrame) -> pd.DataFrame:
    """Valida el contrato en la frontera; Pandera no invade el núcleo de cálculo."""
    faltan = sorted(set(COLUMNAS_BACKTEST) - set(tabla.columns))
    if faltan:
        raise ValueError(f"Faltan columnas del contrato de backtest: {', '.join(faltan)}")
    try:
        import pandera.pandas as pa

        schema = pa.DataFrameSchema(
            {
                "fecha_emision": pa.Column(pa.DateTime),
                "fecha_objetivo": pa.Column(pa.DateTime),
                "horizonte_semanas": pa.Column(int, checks=pa.Check.in_range(0, 52)),
                "p50_kg": pa.Column(float, checks=pa.Check.ge(0), coerce=True),
                "real_kg": pa.Column(float, nullable=True, coerce=True),
                # `required=False` porque las familias que no estiman componentes no las
                # traen; cuando sí están, tienen que ser físicamente posibles.
                "plantas": pa.Column(
                    float, nullable=True, coerce=True, required=False, checks=pa.Check.gt(0)
                ),
                "frutos_por_planta": pa.Column(
                    float, nullable=True, coerce=True, required=False, checks=pa.Check.ge(0)
                ),
                "peso_baya_g": pa.Column(
                    float,
                    nullable=True,
                    coerce=True,
                    required=False,
                    checks=pa.Check.in_range(0, LIMITE_PESO_BAYA_G),
                ),
            },
            strict=False,
            coerce=True,
        )
        return schema.validate(tabla)
    except ImportError:
        return tabla


def validar_predicciones_componentes(tabla: pd.DataFrame, tolerancia: float = 1e-6) -> pd.DataFrame:
    """Contrato de una familia que publica las tres piezas del rendimiento.

    Falla ruidosamente en el momento del ensamblado, antes de que el número llegue a una
    métrica o a la base. `controles_componentes` comprueba lo mismo después y lo deja
    registrado como auditoría; esto lo impide de entrada.
    """
    if tabla.empty:
        return tabla
    faltan = sorted(set(COLUMNAS_COMPONENTES) - set(tabla.columns))
    if faltan:
        raise ValueError(f"Faltan componentes declarados: {', '.join(faltan)}")

    negativos = (
        tabla.plantas.le(0) | tabla.frutos_por_planta.lt(0) | tabla.peso_baya_g.lt(0)
    ).fillna(True)
    if negativos.any():
        raise ValueError(
            f"{int(negativos.sum())} filas con componentes imposibles (plantas <= 0 o "
            "frutos/peso negativos)."
        )

    producto = tabla.plantas * tabla.frutos_por_planta * tabla.peso_baya_g / 1000
    # El modelo de ocurrencia publica un valor esperado: P(cosecha) multiplica la
    # identidad condicional. Una familia puede publicar además un factor de calibración
    # de volumen aprendido as-of; no es una probabilidad ni una causa, pero sí forma
    # parte explícita de la identidad que reconstruye el p50.
    if "probabilidad_cosecha" in tabla:
        producto = producto * pd.to_numeric(tabla.probabilidad_cosecha, errors="coerce")
    if "factor_asignacion_cosecha" in tabla:
        producto = producto * pd.to_numeric(
            tabla.factor_asignacion_cosecha, errors="coerce"
        ).fillna(1.0)
    desvio = (producto - tabla.p50_kg).abs() / tabla.p50_kg.abs().clip(lower=1.0)
    if (desvio > tolerancia).any():
        raise ValueError(
            f"El producto de los componentes no reconstruye p50_kg en "
            f"{int((desvio > tolerancia).sum())} filas (desvío máximo {desvio.max():.3e})."
        )
    return tabla
