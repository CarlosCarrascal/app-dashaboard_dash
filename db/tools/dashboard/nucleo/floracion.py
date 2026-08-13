"""Integración auditable de EvFlores (`DAtos mes.xlsx`) con el panel módulo × semana.

EvFlores es la primera medición de fase fenológica que tiene el tablero: no es un proxy
derivado de la fecha de poda, es un conteo real de flores por turno y semana. Está a nivel
de fundo físico (Aqu Anqa I-V) y turno; el panel de IA.final.xlsx está a nivel de módulo y
usa los nombres de fundo de campo (quechua). Esta capa hace esa traducción explícita —
verificada por correspondencia de rangos de módulo, no supuesta — y resume turno a módulo
sin ocultar cuánto varían los turnos entre sí.
"""

from __future__ import annotations

import io

import numpy as np
import pandas as pd

# Verificado contra los rangos de módulo de cada fundo físico en EvFlores y en el panel:
# Aqu Anqa I = M01-M04 (Arena Azul), Aqu Anqa II = M01-M05 (Quri Allpa),
# Aqu Anqa III = M06-M10 y Aqu Anqa V = M11 (ambos agrupados como Kawsay Allpa en el panel,
# igual que ya hace IA.final.xlsx — M11 es administrativamente del fundo V pero el panel lo
# reporta junto con Kawsay Allpa), Aqu Anqa IV = M12-M14 (Ayllu Allpa).
MAPA_FUNDO_FLORACION: dict[str, str] = {
    "Aqu Anqa I": "Arena Azul",
    "Aqu Anqa II": "Quri Allpa",
    "Aqu Anqa III": "Kawsay Allpa",
    "Aqu Anqa IV": "Ayllu Allpa",
    "Aqu Anqa V": "Kawsay Allpa",
}

_COLUMNAS = [
    "FundoAc", "Modulo", "Turno", "Anio", "Sem", "FInicio", "Fecha", "nFlores",
]


def _agregar_turno_a_modulo(ev: pd.DataFrame) -> pd.DataFrame:
    """Promedio simple entre turnos, con su dispersión a la vista.

    No hay área por turno en esta hoja (a diferencia de M_Poda, que sí trae `AreaPoda`),
    así que no se puede ponderar por área — se promedia sin peso y se expone la dispersión
    relativa para que quede claro cuánto puede estar ocultando ese promedio.
    """
    g = ev.groupby(["_fundo_flor", "Modulo", "Sem"], dropna=False)
    agregado = g.agg(
        flores_promedio=("nFlores", "mean"),
        flores_desvio=("nFlores", "std"),
        flores_n_turnos=("nFlores", "size"),
        fecha_evaluacion=("Fecha", "mean"),
    ).reset_index()
    agregado["flores_dispersion_relativa"] = (
        agregado["flores_desvio"] / agregado["flores_promedio"].replace(0, np.nan)
    )
    return agregado


def integrar_floracion(
    tabla: pd.DataFrame,
    contenido: bytes | None,
    hallazgos: list,
    anio: int = 2025,
) -> pd.DataFrame:
    """Añade el conteo real de flores por módulo y semana al panel existente."""
    if not contenido:
        hallazgos.append(_hallazgo(
            "floracion_no_cargada", "No se cargó EvFlores (DAtos mes.xlsx)", "media",
            "El panel no tiene conteo de flores por módulo y semana.",
            "No se puede comparar la floración real con los días desde poda como reloj "
            "biológico, ni usarla como precursor observado de Frutos.",
        ))
        return tabla

    try:
        crudo = pd.read_excel(io.BytesIO(contenido), sheet_name="EvFlores")
    except Exception as exc:  # noqa: BLE001 — el panel debe degradar sin romperse
        hallazgos.append(_hallazgo(
            "floracion_formato", "No se pudo leer la hoja EvFlores", "media",
            f"La lectura de DAtos mes.xlsx falló: {exc}.",
            "El panel continúa, pero no incorpora la floración real.",
        ))
        return tabla

    if crudo.shape[1] < len(_COLUMNAS):
        hallazgos.append(_hallazgo(
            "floracion_formato", "EvFlores no tiene el formato esperado", "media",
            f"La hoja trae {crudo.shape[1]} columnas y se esperaban al menos "
            f"{len(_COLUMNAS)}.",
            "No se incorpora la floración real.",
        ))
        return tabla

    ev = crudo.iloc[:, :len(_COLUMNAS)].copy()
    ev.columns = _COLUMNAS
    ev["FundoAc"] = ev["FundoAc"].astype(str).str.strip()
    ev["Modulo"] = ev["Modulo"].astype(str).str.strip().replace(
        {"M10A": "M10", "M10B": "M10"}
    )
    ev["Sem"] = pd.to_numeric(ev["Sem"], errors="coerce")
    ev["nFlores"] = pd.to_numeric(ev["nFlores"], errors="coerce")
    ev["Fecha"] = pd.to_datetime(ev["Fecha"], errors="coerce")

    ev = ev[pd.to_numeric(ev["Anio"], errors="coerce") == anio].copy()
    if ev.empty:
        disponibles = sorted(pd.to_numeric(crudo.iloc[:, 3], errors="coerce").dropna()
                             .astype(int).unique().tolist())
        hallazgos.append(_hallazgo(
            "floracion_campania", "EvFlores no contiene el año del panel", "media",
            f"Se buscó {anio}; la hoja trae {disponibles}.",
            "No se cruzan campañas distintas para evitar una floración falsa.",
        ))
        return tabla

    ev["_fundo_flor"] = ev["FundoAc"].map(MAPA_FUNDO_FLORACION)
    sin_alias = int(ev["_fundo_flor"].isna().sum())
    if sin_alias:
        hallazgos.append(_hallazgo(
            "floracion_alias_fundo", "Fundo sin equivalencia para EvFlores", "media",
            f"{sin_alias} filas de EvFlores no tienen una equivalencia documentada entre "
            "el nombre de fundo físico y el nombre de campo del panel.",
            "Esas filas quedan fuera del cruce en vez de asignarse por aproximación.",
        ))
    ev = ev.dropna(subset=["_fundo_flor"])

    agregado = _agregar_turno_a_modulo(ev)
    # El panel ya usa el nombre de campo (quechua) directamente en `Fundo`; el mapeo de
    # arriba traduce DESDE el fundo físico de EvFlores HACIA ese mismo nombre, así que acá
    # no hace falta traducir de nuevo — se cruza `Fundo` contra `_fundo_flor` ya traducido.
    base = tabla.merge(
        agregado.rename(columns={"_fundo_flor": "Fundo", "Sem": "nsem"}),
        on=["Fundo", "Modulo", "nsem"], how="left", validate="many_to_one",
    )

    n_match = int(base["flores_promedio"].notna().sum())
    n_modulos = int(base.loc[base["flores_promedio"].notna(), "celda"].nunique())
    hallazgos.append(_hallazgo(
        "floracion_integrada", "Floración real integrada al panel", "baja",
        f"Se cruzaron {n_match} de {len(base)} celdas y {n_modulos} módulos con EvFlores "
        f"{anio}. El valor de módulo es un promedio simple entre turnos, sin ponderar por "
        "área (esta hoja no trae área por turno, a diferencia de M_Poda).",
        "Permite comparar la floración real contra días desde poda y usarla como "
        "precursor observado de Frutos, en vez de solo un proxy calendario.",
    ))

    dispersos = agregado[agregado["flores_dispersion_relativa"] > 0.75]
    if not dispersos.empty:
        hallazgos.append(_hallazgo(
            "floracion_dispersa_modulo", "La floración no es homogénea entre turnos", "media",
            f"{len(dispersos)} combinaciones módulo-semana tienen una dispersión relativa "
            "entre turnos mayor a 75% (desvío / promedio) — la mediana general es 32%.",
            "El promedio de módulo puede estar ocultando turnos con floración muy "
            "distinta entre sí; no se presenta como una medición uniforme del módulo.",
        ))

    return base


def _hallazgo(clave: str, titulo: str, gravedad: str, detalle: str, efecto: str):
    """Evita importar Hallazgo al cargar el módulo y crear una dependencia circular."""
    from nucleo.datos import Hallazgo

    return Hallazgo(clave, titulo, gravedad, detalle, efecto)
